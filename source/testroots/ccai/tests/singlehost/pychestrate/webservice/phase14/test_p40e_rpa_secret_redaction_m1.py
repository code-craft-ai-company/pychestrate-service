"""
.. module:: test_p40e_rpa_secret_redaction_m1
    :synopsis: Tests that RPA specification defaults never expose the
               packet paths a job type declares secret -- through the
               REST API or the spec page -- and that saving back a
               redacted packet keeps the stored secrets.

Audit finding PRJ-05: a specification's ``default_packet`` was
returned verbatim by ``GET /api/v1/projects/{id}/rpa/specs/{id}`` and
printed on the spec page (and pre-filled into its Run form), secret
fields included. Redaction had only been applied to job records.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os

from typing import Any, Dict, List, Optional, Tuple

from ccai import testbase
from ccai.testbase.mocking import create_module_patch
from ccai.webworks.routing.response import HTMLResponse

from ccai.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from ccai.pychestrate.webservice.jobs.dispatch import (
    InMemoryTransport,
    JobDispatcher,
    register_builtin_extensions as dispatch_register,
)
from ccai.pychestrate.webservice.jobs.envelope import (
    EnvelopeSignerBootstrapConfig,
    install_envelope_signer,
)
from ccai.pychestrate.webservice.jobs.envelope import signer as envelope_signer
from ccai.pychestrate.webservice.messaging.event_bus import (
    reset_for_testing as reset_event_bus,
)
from ccai.pychestrate.webservice.orchestration.rpa import (
    REDACTION_MARKER,
    register_builtin_extensions as rpa_register,
)
from ccai.pychestrate.webservice.orchestration.rpa import service as rpa_service
from ccai.pychestrate.webservice.orchestration.rpa.packet import (
    restore_redacted_secrets,
    secret_top_level_keys,
)
from ccai.pychestrate.webservice.orchestration.rpa.restapi.v1 import rpa_routes
from ccai.pychestrate.webservice.webinterface.blueprints.projects import routes_rpa
from ccai.pychestrate.webservice.webinterface.foundation import url_for as url_for_module

from ccai.pychestrate.webservice.jobs.run.state import models as _run_state_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.dispatch import models as _dispatch_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.envelope import models as _envelope_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.results import models as _results_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.rpa import models as _rpa_models  # noqa: F401

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_REF = "7"
ACTOR_ID = "00000000-0000-4000-8000-000000070002"

SECRET_FIELDS: List[str] = ["api_token", "/auth/password"]
STORED_PACKET: Dict[str, Any] = {
    "api_token": "s3cr3t-token",
    "count": 3,
    "auth": {"user": "svc-user", "password": "pa55word"},
}
REDACTED_PACKET: Dict[str, Any] = {
    "api_token": REDACTION_MARKER,
    "count": 3,
    "auth": {"user": "svc-user", "password": REDACTION_MARKER},
}


# ===========================================================================
# Packet helpers
# ===========================================================================


def test_restore_puts_the_stored_secret_back_at_a_dotted_path():
    """
    **Feature: RPA secret redaction (PRJ-05)**
    **Property: a redaction marker submitted at a secret path is
    replaced with the stored value.**
    """
    restored = restore_redacted_secrets(
        incoming={"api_token": REDACTION_MARKER, "count": 4},
        stored={"api_token": "s3cr3t-token", "count": 3},
        secret_fields=["api_token"],
    )
    testbase.assert_equal(restored, {"api_token": "s3cr3t-token", "count": 4})
    return


def test_restore_puts_the_stored_secret_back_at_a_json_pointer():
    """
    **Feature: RPA secret redaction (PRJ-05)**
    **Property: nested secret paths given as JSON pointers are
    restored too.**
    """
    restored = restore_redacted_secrets(
        incoming={"auth": {"user": "u", "password": REDACTION_MARKER}},
        stored={"auth": {"user": "u", "password": "pa55word"}},
        secret_fields=["/auth/password"],
    )
    testbase.assert_equal(restored["auth"]["password"], "pa55word")
    return


def test_restore_keeps_a_newly_submitted_secret():
    """
    **Feature: RPA secret redaction (PRJ-05)**
    **Property: a secret path carrying a real value (the caller is
    rotating the secret) keeps the submitted value.**
    """
    restored = restore_redacted_secrets(
        incoming={"api_token": "rotated-token"},
        stored={"api_token": "s3cr3t-token"},
        secret_fields=["api_token"],
    )
    testbase.assert_equal(restored["api_token"], "rotated-token")
    return


def test_restore_does_not_add_a_secret_the_caller_left_out():
    """
    **Feature: RPA secret redaction (PRJ-05)**
    **Property: a secret path absent from the submitted packet stays
    absent -- restoring never inserts keys.**
    """
    restored = restore_redacted_secrets(
        incoming={"count": 4},
        stored={"api_token": "s3cr3t-token", "count": 3},
        secret_fields=["api_token"],
    )
    testbase.assert_equal(restored, {"count": 4})
    return


def test_restore_skips_wildcard_paths():
    """
    **Feature: RPA secret redaction (PRJ-05)**
    **Property: wildcard secret paths (``/accounts/*/password``) are
    not restored, because list positions may have changed.**
    """
    restored = restore_redacted_secrets(
        incoming={"accounts": [{"password": REDACTION_MARKER}]},
        stored={"accounts": [{"password": "pw-1"}]},
        secret_fields=["/accounts/*/password"],
    )
    testbase.assert_equal(restored["accounts"][0]["password"], REDACTION_MARKER)
    return


def test_restore_does_not_modify_its_input():
    """
    **Feature: RPA secret redaction (PRJ-05)**
    **Property: the submitted packet object is left unchanged; the
    restored packet is a copy.**
    """
    incoming = {"api_token": REDACTION_MARKER}
    restore_redacted_secrets(
        incoming=incoming,
        stored={"api_token": "s3cr3t-token"},
        secret_fields=["api_token"],
    )
    testbase.assert_equal(incoming, {"api_token": REDACTION_MARKER})
    return


def test_secret_top_level_keys_lists_each_key_holding_a_secret_once():
    """
    **Feature: RPA secret redaction (PRJ-05)**
    **Property: secret_top_level_keys returns the sorted, de-duplicated
    top-level keys under which any secret path lives.**
    """
    keys = secret_top_level_keys(
        secret_fields=["/auth/password", "auth.token", "api_token", ""]
    )
    testbase.assert_equal(keys, ["api_token", "auth"])
    return


# ===========================================================================
# REST handlers
# ===========================================================================


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    envelope_signer.reset_for_testing()
    rpa_service.set_active_job_dispatcher(dispatcher=None)
    dispatch_register()
    rpa_register()
    os.environ["PYCHESTRATE_DEV_MODE"] = "1"
    try:
        install_envelope_signer(
            config=EnvelopeSignerBootstrapConfig(
                source="dev", file_path=None, env_var=None, key_id="test-rpa-p40e-ed25519",
            ),
        )
    finally:
        del os.environ["PYCHESTRATE_DEV_MODE"]
    rpa_service.set_active_job_dispatcher(dispatcher=JobDispatcher(transport=InMemoryTransport()))
    return


class _Principal:
    user_id = ACTOR_ID


class _Query:
    def __init__(self, mapping: Optional[Dict[str, str]] = None) -> None:
        self._m = mapping or {}
        return

    def get(self, key: str, default: Any = None) -> Any:
        return self._m.get(key, default)


class _Request:
    def __init__(self, *, db_session: Any, path_params: Optional[Dict[str, str]] = None,
                 body: Any = None) -> None:
        self.db_session = db_session
        self.auth_principal = _Principal()
        self.path_params = path_params or {}
        self.query_params = _Query()
        self.path = "/api/v1/rpa"
        self.body = json.dumps(body).encode("utf-8") if body is not None else b""
        return


class _Patches:
    """
        Swap the route module's permission and project seams for fakes;
        restore on exit.
    """

    def __init__(self) -> None:
        self._saved: Dict[str, Any] = {}
        return

    def __enter__(self) -> "_Patches":
        self._saved["_require_permission"] = rpa_routes._require_permission
        self._saved["_require_project_exists"] = rpa_routes._require_project_exists

        class _Project:
            slug = "demo"
            name = "Demo"

        rpa_routes._require_permission = lambda *, request, db_session, permission_key: _Principal()
        rpa_routes._require_project_exists = lambda *, request, db_session, project_id: _Project()
        return self

    def __exit__(self, *exc: Any) -> None:
        for name, value in self._saved.items():
            setattr(rpa_routes, name, value)
        return


def _body(response: Any) -> Dict[str, Any]:
    rtnval = json.loads(response._body.decode("utf-8"))
    return rtnval


def _create_spec_with_secrets(session: Any) -> Any:
    """
        Register a job type declaring two secret paths, publish a
        version, and create a specification whose defaults carry both
        secrets. Returns the create response.
    """
    rpa_routes.handle_create_job_type(_Request(db_session=session, body={
        "type_id": "vault-sync", "display_name": "Vault Sync",
        "execution_mode": "process", "secret_fields": SECRET_FIELDS,
    }))
    rpa_routes.handle_publish_version(_Request(
        db_session=session, path_params={"type_id": "vault-sync"},
        body={"version": "1.0.0", "source": {"kind": "git", "ref": "https://x/y.git#v1"},
              "entrypoint": {"command": ["python", "-m", "jobs.sync"]}},
    ))
    rtnval = rpa_routes.handle_create_spec(_Request(
        db_session=session, path_params={"project_id": PROJECT_REF},
        body={"name": "nightly", "type_id": "vault-sync", "default_packet": STORED_PACKET},
    ))
    return rtnval


def test_create_spec_response_redacts_secret_defaults():
    """
    **Feature: RPA secret redaction (PRJ-05)**
    **Property: the 201 body returned when a specification is created
    carries the redaction marker at every secret path.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    with _Patches():
        response = _create_spec_with_secrets(session)
    testbase.assert_equal(_body(response)["default_packet"], REDACTED_PACKET)
    return


def test_read_spec_redacts_secret_defaults():
    """
    **Feature: RPA secret redaction (PRJ-05)**
    **Property: GET on a specification returns its defaults with the
    secret paths redacted.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    with _Patches():
        spec_id = _body(_create_spec_with_secrets(session))["spec_id"]
        response = rpa_routes.handle_read_spec(_Request(
            db_session=session, path_params={"project_id": PROJECT_REF, "spec_id": spec_id},
        ))
    testbase.assert_equal(_body(response)["default_packet"], REDACTED_PACKET)
    return


def test_list_specs_redacts_secret_defaults():
    """
    **Feature: RPA secret redaction (PRJ-05)**
    **Property: the specification list returns every entry's defaults
    with the secret paths redacted.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    with _Patches():
        _create_spec_with_secrets(session)
        response = rpa_routes.handle_list_specs(_Request(
            db_session=session, path_params={"project_id": PROJECT_REF},
        ))
    testbase.assert_equal(
        [spec["default_packet"] for spec in _body(response)["specs"]], [REDACTED_PACKET]
    )
    return


def test_saving_back_a_redacted_spec_keeps_the_stored_secrets():
    """
    **Feature: RPA secret redaction (PRJ-05)**
    **Property: PATCHing a specification with the redacted defaults it
    read (one non-secret value changed) stores the change and keeps
    the real secrets, not the marker.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    with _Patches():
        spec_id = _body(_create_spec_with_secrets(session))["spec_id"]
        edited = dict(REDACTED_PACKET)
        edited["count"] = 4
        rpa_routes.handle_update_spec(_Request(
            db_session=session, path_params={"project_id": PROJECT_REF, "spec_id": spec_id},
            body={"default_packet": edited},
        ))
    stored = dict(rpa_service.get_spec(db_session=session, spec_id=spec_id).default_packet)
    expected = dict(STORED_PACKET)
    expected["count"] = 4
    testbase.assert_equal(stored, expected)
    return


def test_saving_a_new_secret_value_replaces_the_stored_one():
    """
    **Feature: RPA secret redaction (PRJ-05)**
    **Property: PATCHing a specification with a real value at a secret
    path stores that value (secrets can still be rotated).**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    with _Patches():
        spec_id = _body(_create_spec_with_secrets(session))["spec_id"]
        edited = dict(REDACTED_PACKET)
        edited["api_token"] = "rotated-token"
        rpa_routes.handle_update_spec(_Request(
            db_session=session, path_params={"project_id": PROJECT_REF, "spec_id": spec_id},
            body={"default_packet": edited},
        ))
    stored = dict(rpa_service.get_spec(db_session=session, spec_id=spec_id).default_packet)
    testbase.assert_equal(stored["api_token"], "rotated-token")
    return


# ===========================================================================
# Spec page
# ===========================================================================


class _FakeSpec:
    spec_id = "spec-1"
    project_id = PROJECT_REF
    default_packet = STORED_PACKET
    secret_fields = tuple(SECRET_FIELDS)
    packet_schema = None
    resolved_version = "1.0.0"


class _FakeRpaService:
    def get_spec(self, *, db_session: Any, spec_id: str) -> _FakeSpec:
        return _FakeSpec()

    def list_jobs(self, **kwargs: Any) -> Any:
        class _Page:
            jobs: List[Any] = []
        return _Page()


class _FakeDbSession:
    def close(self) -> None:
        return


class _FakeAuth:
    redirect_response = None
    db_session = _FakeDbSession()
    session: Dict[str, Any] = {}
    csrf_token = "csrf-fresh"
    user_id = "u-member"


def _spec_page_context() -> Dict[str, Any]:
    """
        Render ``GET /projects/7/rpa/specs/spec-1`` with every data seam
        faked and return the template context the handler built.
    """
    rendered: List[Tuple[str, Dict[str, Any]]] = []

    def _capture_render(*, template_name: str, context: Dict[str, Any], **kwargs: Any) -> HTMLResponse:
        rendered.append((template_name, context))
        return HTMLResponse(content="rendered", status_code=200)

    seams = {
        "_resolve_authenticated_request": lambda **kwargs: _FakeAuth(),
        "_resolve_view_authorized_project": lambda **kwargs: (7, None, object()),
        "_build_rpa_service": lambda **kwargs: _FakeRpaService(),
        "_can_manage": lambda **kwargs: True,
        "_build_default_template_context": lambda **kwargs: {},
        "_attach_session_to_response": lambda **kwargs: None,
        "_render": _capture_render,
    }
    patches = []
    url_for_module.register_endpoint(
        endpoint="projects.rpa_spec_list", pattern="/projects/{project_id}/rpa/specs",
    )
    try:
        for name, replacement in seams.items():
            patch = create_module_patch(routes_rpa, name)
            mock = patch.activate()
            mock.configure(side_effect=replacement)
            patches.append(patch)

        class _Request:
            path_params = {"project_id": "7", "spec_id": "spec-1"}

        routes_rpa.handle_rpa_spec_detail(_Request())
    finally:
        for patch in reversed(patches):
            patch.deactivate()
        url_for_module.reset_registry_for_testing()
    rtnval = rendered[0][1]
    return rtnval


def test_spec_page_shows_the_defaults_redacted():
    """
    **Feature: RPA secret redaction (PRJ-05)**
    **Property: the defaults panel on the spec page shows the marker,
    never the stored secret values.**
    """
    shown = json.loads(_spec_page_context()["default_packet_json"])
    testbase.assert_equal(shown, REDACTED_PACKET)
    return


def test_spec_page_run_form_leaves_out_keys_holding_secrets():
    """
    **Feature: RPA secret redaction (PRJ-05)**
    **Property: the Run form is pre-filled without the top-level keys
    that hold secrets, so the stored secrets apply unless the operator
    types new values (packets merge at the top level).**
    """
    prefill = json.loads(_spec_page_context()["run_packet_json"])
    testbase.assert_equal(prefill, {"count": 3})
    return


def test_spec_page_names_the_secret_keys_it_left_out():
    """
    **Feature: RPA secret redaction (PRJ-05)**
    **Property: the page context names the secret keys left out of
    the Run form so the help text can explain them.**
    """
    testbase.assert_equal(
        _spec_page_context()["secret_packet_keys"], ["api_token", "auth"]
    )
    return
