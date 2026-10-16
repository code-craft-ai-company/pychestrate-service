"""
.. module:: test_p40n_rpa_secret_references_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: RPA packets point at vault secrets instead of holding their values (ADM-07, #366).

.. moduleauthor:: Code Craft AI LLC

A packet field can be ``{"$secret": "<vault ref>"}``. The reference is checked when it is saved or supplied (as the signed-in user, through the
vault's own read path), resolved once at dispatch into the payload sent to the pod, and never stored as a value: not in the specification, its
revisions, the job row or the packet digest, and scrubbed out of the archived envelope when the job ends. The design is in
``specs/model-convergence.md`` section 11.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import dataclasses
import json
import os
import uuid

from typing import Any, Dict, List, Optional, Tuple

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid
from ccai.pychestrate.webservice.jobs.dispatch import (
    InMemoryTransport,
    JobDispatcher,
    register_builtin_extensions as dispatch_register,
)
from ccai.pychestrate.webservice.jobs.dispatch.factories.strategy import DispatchCandidate
from ccai.pychestrate.webservice.jobs.envelope import (
    EnvelopeSignerBootstrapConfig,
    install_envelope_signer,
)
from ccai.pychestrate.webservice.jobs.envelope import signer as envelope_signer
from ccai.pychestrate.webservice.jobs.envelope.models import JobEnvelopeRecord
from ccai.pychestrate.webservice.orchestration.rpa import REDACTION_MARKER, register_builtin_extensions as rpa_register
from ccai.pychestrate.webservice.orchestration.rpa import service as rpa_service
from ccai.pychestrate.webservice.orchestration.rpa.errors import PacketValidationError, RpaSecretReferenceError
from ccai.pychestrate.webservice.orchestration.rpa.models import RpaJobStatus
from ccai.pychestrate.webservice.orchestration.rpa.packet import (
    find_secret_refs,
    inline_secret_paths,
    is_secret_ref,
    packet_digest,
    redact_packet,
    substitute_secret_refs,
)
from ccai.pychestrate.webservice.orchestration.rpa.restapi.v1 import rpa_routes
from ccai.pychestrate.webservice.secrets import secrets_service
from ccai.pychestrate.webservice.secrets.kek_loader import (
    KekHandle,
    reset_active_kek_for_testing,
    set_active_kek,
)
from ccai.pychestrate.webservice.secrets.models import SecretScopeKind
from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from ccai.pychestrate.webservice.secrets.secrets_aspects import build_default_aspects
from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind
from ccai.pychestrate.webservice.security.auth.session_service import AuthPrincipal
from ccai.pychestrate.webservice.security.rbac.models import (
    BindingScope,
    PrincipalKind,
    RbacRole,
    RbacRoleBinding,
    RoleSource,
)
from ccai.pychestrate.webservice.webinterface.blueprints.projects import routes_rpa

from ccai.pychestrate.webservice.jobs.run.state import models as _run_state_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.dispatch import models as _dispatch_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.envelope import models as _envelope_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.results import models as _results_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.rpa import models as _rpa_models  # noqa: F401

from ccai.testshared.factories.webui.dataclass_fixtures import MODE_POPULATED
from ccai.testshared.factories.webui.template_contexts import build_template_context

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)
from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    strict_environment,
    undeclared_variables,
)


PROJECT_REF = "7"
DB_REF = "org:rpa.db-password"
DB_VALUE = "p4ss-from-the-vault"
TYPE_ID = "ledger-sync"
SECRET_FIELDS: List[str] = ["db_password", "/auth/token"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _principal(user_id: str) -> AuthPrincipal:
    rtnval = AuthPrincipal(user_id=user_id, session_id="sess-rpa-refs", provider_kind=AuthProviderKind.LOCAL, provider_name="local")
    return rtnval


def _bind_system_admin(*, session: Any, user_id: str) -> None:
    role = session.query(RbacRole).filter(RbacRole.role_name == "system-admin").first()
    if role is None:
        role = RbacRole(role_id=new_uuid(), role_name="system-admin", source=RoleSource.BUILTIN, source_name="CorePermissionExtension", description="")
        session.add(role)
        session.flush()
    session.add(RbacRoleBinding(
        binding_id=new_uuid(), role_id=role.role_id, principal_kind=PrincipalKind.USER, principal_id=user_id,
        scope_kind=BindingScope.SYSTEM, scope_id=None, inherits_into_project=False, created_by=None,
    ))
    session.commit()
    return


def _prepare() -> Tuple[Any, AuthPrincipal, AuthPrincipal]:
    """
        A fresh runtime with the RPA and dispatch extensions, a signer, an in-memory dispatcher, a vault key and an in-memory database holding
        an administrator and a user with no vault rights.

        :returns: ``(session, administrator principal, powerless principal)``.
    """
    reset_phase1_runtime()
    envelope_signer.reset_for_testing()
    rpa_service.set_active_job_dispatcher(dispatcher=None)
    dispatch_register()
    rpa_register()
    os.environ["PYCHESTRATE_DEV_MODE"] = "1"
    try:
        install_envelope_signer(config=EnvelopeSignerBootstrapConfig(source="dev", file_path=None, env_var=None, key_id="test-rpa-p40n-ed25519"))
    finally:
        del os.environ["PYCHESTRATE_DEV_MODE"]
    rpa_service.set_active_job_dispatcher(dispatcher=JobDispatcher(transport=InMemoryTransport()))
    reset_active_kek_for_testing()
    set_active_kek(kek=KekHandle(kek_id="test-kek-rpa-refs", key_material=SecretBytes(b"R" * 32), source="test"))
    _engine, session = build_in_memory_session()
    admin_id = str(uuid.uuid4())
    _bind_system_admin(session=session, user_id=admin_id)
    rtnval = (session, _principal(admin_id), _principal(str(uuid.uuid4())))
    return rtnval


def _put(session: Any, admin: AuthPrincipal, ref: str = DB_REF, value: str = DB_VALUE) -> None:
    secrets_service.put_secret(
        db_session=session, principal=admin, secret_ref=ref, plaintext=SecretBytes(value.encode("utf-8")),
        aspects=build_default_aspects(), scope_kind=SecretScopeKind.ORG,
    )
    return


def _type_and_version(session: Any) -> None:
    rpa_service.register_job_type(
        db_session=session,
        inputs=rpa_service.RpaJobTypeInputs(type_id=TYPE_ID, display_name="Ledger Sync", execution_mode="process", secret_fields=tuple(SECRET_FIELDS)),
        actor_id=None,
    )
    rpa_service.publish_version(
        db_session=session, type_id=TYPE_ID,
        inputs=rpa_service.RpaVersionInputs(
            version="1.0.0", source_kind="git", source_ref="https://example.com/jobs.git#v1", entrypoint={"command": ["python", "-m", "jobs.sync"]},
            environment={}, timeout_minutes=30,
        ),
        actor_id=None,
    )
    return


def _spec(session: Any, packet: Dict[str, Any], principal: Any, name: str = "nightly") -> Any:
    rtnval = rpa_service.create_spec(
        db_session=session, project_id=PROJECT_REF,
        inputs=rpa_service.RpaSpecInputs(name=name, type_id=TYPE_ID, version_selector="latest-active", default_packet=packet),
        actor_id=None, principal=principal,
    )
    return rtnval


def _aspects(**overrides: Any) -> Any:
    kwargs: Dict[str, Any] = {
        "candidates": (DispatchCandidate(
            client_id="11111111-1111-4000-8000-0000000040a1", pod_id="22222222-2222-4000-8000-0000000040a2",
            capability_tags=(), inflight_dispatch_count=0, last_dispatched_at_iso="",
        ),),
        "project_slug": "demo",
    }
    kwargs.update(overrides)
    return rpa_service.RpaTriggerAspects(**kwargs)


def _archived_packets(session: Any, job_id: str) -> List[Dict[str, Any]]:
    """The ``params.work_packet`` of every archived envelope of the job."""
    rows = session.query(JobEnvelopeRecord).filter(JobEnvelopeRecord.run_id == job_id).all()
    rtnval = [json.loads(row.canonical_payload_text)["params"]["work_packet"] for row in rows]
    return rtnval


def _issues(call: Any) -> List[Tuple[str, str]]:
    try:
        call()
    except RpaSecretReferenceError as xcpt:
        return list(xcpt.issues)
    return []


# ---------------------------------------------------------------------------
# Packet helpers
# ---------------------------------------------------------------------------


PACKET: Dict[str, Any] = {
    "user": "ada",
    "auth": {"password": {"$secret": "company/db"}, "tokens": [{"v": "plain"}, {"v": {"$secret": "a/b"}}]},
    "odd": {"$secret": "x", "other": 1},
}


def test_references_are_found_substituted_and_listed_when_inline():
    """
    **Feature: RPA secrets by reference (ADM-07)**
    **Property: an object holding only a non-empty ``$secret`` string is a reference (one with another key, or an empty name, is not);
    references are found with their JSON pointers, substituted without changing the input, and the declared secret paths holding a plain
    value (not a reference, not empty, not the marker) are listed.**
    """
    before = json.dumps(PACKET, sort_keys=True)
    replaced = substitute_secret_refs(PACKET, lambda path, ref: "<<{}|{}>>".format(path, ref))
    testbase.assert_equal(
        (
            find_secret_refs(PACKET),
            replaced["auth"]["password"], replaced["auth"]["tokens"][1]["v"], replaced["odd"],
            json.dumps(PACKET, sort_keys=True) == before,
            is_secret_ref({"$secret": ""}), is_secret_ref({"$secret": 5}), is_secret_ref("company/db"),
            inline_secret_paths(packet=PACKET, secret_fields=["auth.password", "auth.tokens.*.v", "/user", "/absent"]),
            inline_secret_paths(packet={"t": REDACTION_MARKER, "u": "", "w": None}, secret_fields=["t", "u", "w"]),
        ),
        (
            [("/auth/password", "company/db"), ("/auth/tokens/1/v", "a/b")],
            "<</auth/password|company/db>>", "<</auth/tokens/1/v|a/b>>", {"$secret": "x", "other": 1},
            True, False, False, False,
            ["/auth/tokens/0/v", "/user"],
            [],
        ),
    )
    return


def test_redaction_leaves_a_reference_in_place_and_hides_a_plain_value():
    """
    **Feature: RPA secrets by reference (ADM-07)**
    **Property: at a declared secret path, redaction replaces a plain value with the marker and leaves a vault reference alone, since a reference is not a secret.**
    """
    packet = {"db_password": {"$secret": DB_REF}, "auth": {"token": "plain-token"}}
    testbase.assert_equal(
        redact_packet(packet=packet, secret_fields=SECRET_FIELDS),
        {"db_password": {"$secret": DB_REF}, "auth": {"token": REDACTION_MARKER}},
    )
    return


# ---------------------------------------------------------------------------
# Saving a specification
# ---------------------------------------------------------------------------


def test_a_specification_keeps_the_reference_and_its_revision_does_too():
    """
    **Feature: RPA secrets by reference (ADM-07)**
    **Property: a specification whose default packet points at a vault secret the user may read is created with the reference as written; neither the stored default
    nor the revision snapshot holds the value, and the spec reports no inline secret.**
    """
    session, admin, _powerless = _prepare()
    _put(session, admin)
    _type_and_version(session)
    spec = _spec(session, {"db_password": {"$secret": DB_REF}, "host": "ledger.example.test"}, admin)
    revision = rpa_service.repository.find_spec_revision(db_session=session, spec_id=spec.spec_id, revision=1)
    stored_text = json.dumps(dict(rpa_service.get_spec(db_session=session, spec_id=spec.spec_id).default_packet), sort_keys=True)
    testbase.assert_equal(
        (dict(spec.default_packet), DB_VALUE in stored_text, DB_VALUE in json.dumps(dict(revision.snapshot), default=str), dict(revision.snapshot["default_packet"]), spec.inline_secret_fields),
        ({"db_password": {"$secret": DB_REF}, "host": "ledger.example.test"}, False, False, {"db_password": {"$secret": DB_REF}, "host": "ledger.example.test"}, ()),
    )
    return


def test_saving_a_specification_lists_every_reference_that_cannot_be_used_and_creates_nothing():
    """
    **Feature: RPA secrets by reference (ADM-07)**
    **Property: a missing secret, an expired one and one the user may not read are each listed with their packet path (no value in any message); a user with
    no vault rights is refused the existing secret; nobody signed in is refused every reference; and no specification is created.**
    """
    session, admin, powerless = _prepare()
    _put(session, admin)
    _type_and_version(session)
    missing = _issues(lambda: _spec(session, {"a": {"$secret": "org:nope"}, "b": {"$secret": DB_REF}}, admin, name="missing"))
    denied = _issues(lambda: _spec(session, {"db_password": {"$secret": DB_REF}}, powerless, name="denied"))
    anonymous = _issues(lambda: _spec(session, {"db_password": {"$secret": DB_REF}}, None, name="anonymous"))
    _specs, count = rpa_service.list_specs(db_session=session, project_id=PROJECT_REF)
    testbase.assert_equal(
        (
            [path for path, _message in missing], "org:nope" in missing[0][1],
            [path for path, _message in denied], "may not read" in denied[0][1],
            [path for path, _message in anonymous], "signed-in user" in anonymous[0][1],
            DB_VALUE in json.dumps(missing + denied + anonymous), count,
        ),
        (["/a"], True, ["/db_password"], True, ["/db_password"], True, False, 0),
    )
    return


def test_a_plain_value_at_a_declared_secret_field_is_accepted_and_listed():
    """
    **Feature: RPA secrets by reference (ADM-07)**
    **Property: an existing specification style still works: a plain value at a declared secret path is stored, and the spec lists that path (and not a path holding a
    reference) as an inline secret, so the page can say so.**
    """
    session, admin, _powerless = _prepare()
    _put(session, admin)
    _type_and_version(session)
    spec = _spec(session, {"db_password": "typed-in-plain", "auth": {"token": {"$secret": DB_REF}}}, admin)
    testbase.assert_equal(spec.inline_secret_fields, ("/db_password",))
    return


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def test_a_run_hands_the_pod_the_value_while_the_job_the_specification_and_the_digest_keep_the_reference():
    """
    **Feature: RPA secrets by reference (ADM-07)**
    **Property: the packet archived for delivery to the pod holds the secret's value; the job row shows the reference, the specification still holds the
    reference, and the packet digest is the digest of the packet with the reference in it.**
    """
    session, admin, _powerless = _prepare()
    _put(session, admin)
    _type_and_version(session)
    spec = _spec(session, {"db_password": {"$secret": DB_REF}, "host": "ledger.example.test"}, admin)
    job = rpa_service.trigger_job(
        db_session=session, project_id=PROJECT_REF, spec_id=spec.spec_id, work_packet={"batch": 4}, aspects=_aspects(),
    )
    sent = _archived_packets(session, job.job_id)
    expected_digest = packet_digest({"db_password": {"$secret": DB_REF}, "host": "ledger.example.test", "batch": 4})
    testbase.assert_equal(
        (sent, dict(job.work_packet), job.packet_digest, dict(rpa_service.get_spec(db_session=session, spec_id=spec.spec_id).default_packet)),
        (
            [{"db_password": DB_VALUE, "host": "ledger.example.test", "batch": 4}],
            {"db_password": {"$secret": DB_REF}, "host": "ledger.example.test", "batch": 4},
            expected_digest,
            {"db_password": {"$secret": DB_REF}, "host": "ledger.example.test"},
        ),
    )
    return


def test_the_archived_envelope_is_scrubbed_when_the_job_ends_and_not_before():
    """
    **Feature: RPA secrets by reference (ADM-07)**
    **Property: while the job runs, the archived envelope holds the value (the pod fetches it from there); when the job reaches a terminal state the value at a reference
    and a plain value at a declared secret field are replaced by the redaction marker, other fields are untouched, and ending the job again changes nothing.**
    """
    session, admin, _powerless = _prepare()
    _put(session, admin)
    _type_and_version(session)
    spec = _spec(session, {"db_password": {"$secret": DB_REF}, "host": "h"}, admin)
    job = rpa_service.trigger_job(
        db_session=session, project_id=PROJECT_REF, spec_id=spec.spec_id, work_packet={"auth": {"token": "typed-token"}}, aspects=_aspects(),
    )
    while_running = _archived_packets(session, job.job_id)
    rpa_service.apply_run_terminal(db_session=session, job_id=job.job_id, final_status=RpaJobStatus.SUCCEEDED, exit_code=0)
    after = _archived_packets(session, job.job_id)
    text = json.dumps(after)
    rpa_service.apply_run_terminal(db_session=session, job_id=job.job_id, final_status=RpaJobStatus.FAILED, exit_code=1)
    testbase.assert_equal(
        (while_running, after, DB_VALUE in text or "typed-token" in text, _archived_packets(session, job.job_id)),
        (
            [{"db_password": DB_VALUE, "host": "h", "auth": {"token": "typed-token"}}],
            [{"db_password": REDACTION_MARKER, "host": "h", "auth": {"token": REDACTION_MARKER}}],
            False,
            after,
        ),
    )
    return


def test_a_secret_that_has_gone_fails_the_run_before_any_job_exists():
    """
    **Feature: RPA secrets by reference (ADM-07)**
    **Property: when the secret behind a saved reference has been deleted, triggering the specification fails with the packet path and the secret's name in the
    error (never a value), and no job row, run or archived envelope is created.**
    """
    session, admin, _powerless = _prepare()
    _put(session, admin)
    _type_and_version(session)
    spec = _spec(session, {"db_password": {"$secret": DB_REF}}, admin)
    secrets_service.delete_secret(db_session=session, principal=admin, secret_ref=DB_REF, aspects=build_default_aspects())
    issues = _issues(lambda: rpa_service.trigger_job(db_session=session, project_id=PROJECT_REF, spec_id=spec.spec_id, work_packet={}, aspects=_aspects()))
    jobs = session.query(_rpa_models.RpaJob).count()
    envelopes = session.query(JobEnvelopeRecord).count()
    testbase.assert_equal(
        ([path for path, _message in issues], DB_REF in issues[0][1], jobs, envelopes),
        (["/db_password"], True, 0, 0),
    )
    return


def test_a_caller_with_no_signed_in_user_may_run_a_saved_reference_but_not_supply_one():
    """
    **Feature: RPA secrets by reference (ADM-07)**
    **Property: a pipeline step, schedule or lab tool (no principal) can run a specification whose default packet holds a reference (the user who saved it was checked), but a
    reference in the run's own packet is refused, because nobody was checked for it.**
    """
    session, admin, _powerless = _prepare()
    _put(session, admin)
    _type_and_version(session)
    spec = _spec(session, {"db_password": {"$secret": DB_REF}}, admin)
    ran = rpa_service.trigger_job(db_session=session, project_id=PROJECT_REF, spec_id=spec.spec_id, work_packet={}, aspects=_aspects())
    refused = _issues(lambda: rpa_service.trigger_job(
        db_session=session, project_id=PROJECT_REF, spec_id=spec.spec_id, work_packet={"auth": {"token": {"$secret": DB_REF}}}, aspects=_aspects(idempotency_window_seconds=0),
    ))
    testbase.assert_equal(
        (ran.status.value in ("dispatched", "running", "dispatching", "pending"), [path for path, _message in refused]),
        (True, ["/auth/token"]),
    )
    return


def test_a_signed_in_user_is_checked_for_a_reference_their_own_run_supplies():
    """
    **Feature: RPA secrets by reference (ADM-07)**
    **Property: a run that supplies a reference is accepted for a user who may read the secret and refused, listing the path, for one who may not.**
    """
    session, admin, powerless = _prepare()
    _put(session, admin)
    _type_and_version(session)
    spec = _spec(session, {"host": "h"}, admin)
    packet = {"db_password": {"$secret": DB_REF}}
    allowed = rpa_service.trigger_job(
        db_session=session, project_id=PROJECT_REF, spec_id=spec.spec_id, work_packet=packet, aspects=_aspects(principal=admin, idempotency_window_seconds=0),
    )
    refused = _issues(lambda: rpa_service.trigger_job(
        db_session=session, project_id=PROJECT_REF, spec_id=spec.spec_id, work_packet=packet, aspects=_aspects(principal=powerless, idempotency_window_seconds=0),
    ))
    testbase.assert_equal(
        (dict(allowed.work_packet).get("db_password"), [path for path, _message in refused]),
        ({"$secret": DB_REF}, ["/db_password"]),
    )
    return


def test_rotating_the_secret_neither_changes_the_digest_nor_defeats_the_idempotency_window():
    """
    **Feature: RPA secrets by reference (ADM-07)**
    **Property: the digest is computed with the reference in it, so after the secret is rotated an identical run inside the window is still recognised as a replay of the first.**
    """
    session, admin, _powerless = _prepare()
    _put(session, admin)
    _type_and_version(session)
    spec = _spec(session, {"db_password": {"$secret": DB_REF}}, admin)
    first = rpa_service.trigger_job(db_session=session, project_id=PROJECT_REF, spec_id=spec.spec_id, work_packet={}, aspects=_aspects())
    secrets_service.update_secret(
        db_session=session, principal=admin, secret_ref=DB_REF, plaintext=SecretBytes(b"rotated-value"), aspects=build_default_aspects(),
    )
    second = rpa_service.trigger_job(db_session=session, project_id=PROJECT_REF, spec_id=spec.spec_id, work_packet={}, aspects=_aspects())
    testbase.assert_equal((second.replayed, second.job_id == first.job_id, second.packet_digest == first.packet_digest), (True, True, True))
    return


def test_the_schema_is_checked_with_a_placeholder_so_a_string_field_accepts_a_reference():
    """
    **Feature: RPA secrets by reference (ADM-07)**
    **Property: a job type whose schema says ``db_password`` is a string accepts a reference there (in the early check and in the trigger itself, which then sends the pod the value), and still refuses a number, so a bad packet is reported before the vault is touched.**
    """
    session, admin, _powerless = _prepare()
    _put(session, admin)
    rpa_service.register_job_type(
        db_session=session,
        inputs=rpa_service.RpaJobTypeInputs(
            type_id=TYPE_ID, display_name="Ledger Sync", execution_mode="process", secret_fields=tuple(SECRET_FIELDS),
            packet_schema={"type": "object", "properties": {"db_password": {"type": "string"}}, "required": ["db_password"]},
        ),
        actor_id=None,
    )
    rpa_service.publish_version(
        db_session=session, type_id=TYPE_ID,
        inputs=rpa_service.RpaVersionInputs(version="1.0.0", source_kind="git", source_ref="https://example.com/jobs.git#v1", entrypoint={"command": ["python", "-m", "j"]}, environment={}, timeout_minutes=30),
        actor_id=None,
    )
    spec = _spec(session, {"db_password": {"$secret": DB_REF}}, admin)
    accepted = rpa_service.check_trigger_packet(db_session=session, project_id=PROJECT_REF, spec_id=spec.spec_id, work_packet={}, principal=admin)
    rejected = False
    try:
        rpa_service.check_trigger_packet(db_session=session, project_id=PROJECT_REF, spec_id=spec.spec_id, work_packet={"db_password": 5}, principal=admin)
    except PacketValidationError:
        rejected = True
    job = rpa_service.trigger_job(db_session=session, project_id=PROJECT_REF, spec_id=spec.spec_id, work_packet={}, aspects=_aspects())
    testbase.assert_equal(
        (accepted, rejected, dict(job.work_packet), _archived_packets(session, job.job_id)),
        ({"db_password": {"$secret": DB_REF}}, True, {"db_password": {"$secret": DB_REF}}, [{"db_password": DB_VALUE}]),
    )
    return


# ---------------------------------------------------------------------------
# REST and the specification page
# ---------------------------------------------------------------------------


class _Request:
    def __init__(self, *, db_session: Any, principal: Any, path_params: Optional[Dict[str, str]] = None, body: Any = None) -> None:
        self.db_session = db_session
        self.auth_principal = principal
        self.path_params = path_params or {}
        self.query_params = type("Q", (), {"get": lambda self, key, default=None: default})()
        self.path = "/api/v1/rpa"
        self.body = json.dumps(body).encode("utf-8") if body is not None else b""
        return


class _RoutePatches:
    """Replace the REST module's permission and project seams with fakes that let the given principal through; restore on exit."""

    def __init__(self, principal: Any) -> None:
        self._principal = principal
        self._saved: Dict[str, Any] = {}
        return

    def __enter__(self) -> "_RoutePatches":
        principal = self._principal
        self._saved["_require_permission"] = rpa_routes._require_permission
        self._saved["_require_project_exists"] = rpa_routes._require_project_exists
        project = type("Project", (), {"slug": "demo", "name": "Demo"})()
        rpa_routes._require_permission = lambda *, request, db_session, permission_key: principal
        rpa_routes._require_project_exists = lambda *, request, db_session, project_id: project
        return self

    def __exit__(self, *exc: Any) -> None:
        for name, value in self._saved.items():
            setattr(rpa_routes, name, value)
        return


def _json(response: Any) -> Dict[str, Any]:
    rtnval = json.loads(response._body.decode("utf-8"))
    return rtnval


def test_the_rest_api_checks_references_with_the_callers_own_access_and_reports_inline_secrets():
    """
    **Feature: RPA secrets by reference (ADM-07)**
    **Property: POST of a specification pointing at a missing secret answers 422 with an ``errors`` list (path and message), one pointing at a readable secret answers 201 with the
    reference as written, and a plain value at a declared secret field is listed in ``inline_secret_fields`` (the packet itself shown redacted).**
    """
    session, admin, _powerless = _prepare()
    _put(session, admin)
    with _RoutePatches(admin):
        rpa_routes.handle_create_job_type(_Request(db_session=session, principal=admin, body={
            "type_id": TYPE_ID, "display_name": "Ledger Sync", "execution_mode": "process", "secret_fields": SECRET_FIELDS,
        }))
        rpa_routes.handle_publish_version(_Request(db_session=session, principal=admin, path_params={"type_id": TYPE_ID}, body={
            "version": "1.0.0", "source": {"kind": "git", "ref": "https://x/y.git#v1"}, "entrypoint": {"command": ["python", "-m", "jobs.sync"]},
        }))
        bad = rpa_routes.handle_create_spec(_Request(db_session=session, principal=admin, path_params={"project_id": PROJECT_REF}, body={
            "name": "bad", "type_id": TYPE_ID, "default_packet": {"db_password": {"$secret": "org:nope"}},
        }))
        good = rpa_routes.handle_create_spec(_Request(db_session=session, principal=admin, path_params={"project_id": PROJECT_REF}, body={
            "name": "good", "type_id": TYPE_ID, "default_packet": {"db_password": {"$secret": DB_REF}, "auth": {"token": "typed"}},
        }))
    bad_body, good_body = _json(bad), _json(good)
    testbase.assert_equal(
        (
            bad.status_code, [error["path"] for error in bad_body.get("errors", [])], good.status_code,
            good_body["default_packet"], good_body["inline_secret_fields"],
        ),
        (422, ["/db_password"], 201, {"db_password": {"$secret": DB_REF}, "auth": {"token": REDACTION_MARKER}}, ["/auth/token"]),
    )
    return


def test_the_specification_page_says_when_a_secret_is_stored_in_plain_text():
    """
    **Feature: RPA secrets by reference (ADM-07)**
    **Property: the specification page shows a notice naming each secret path stored as a plain value and how to replace it, and shows no notice when there is none; the
    create form's packet help explains the reference syntax.**
    """
    template = "projects/rpa/spec_detail.html"
    context = build_template_context(template_name=template, variable_names=undeclared_variables(template_name=template), mode=MODE_POPULATED)
    environment = strict_environment()
    plain = environment.get_template(template).render(dict(context, spec=dataclasses.replace(context["spec"], inline_secret_fields=("/db_password", "/auth/token"))))
    clean = environment.get_template(template).render(dict(context, spec=dataclasses.replace(context["spec"], inline_secret_fields=())))
    create = "projects/rpa/spec_create.html"
    create_context = build_template_context(template_name=create, variable_names=undeclared_variables(template_name=create), mode=MODE_POPULATED)
    form = environment.get_template(create).render(create_context)
    testbase.assert_equal(
        (
            'data-role="inline-secrets"' in plain, "/db_password" in plain and "/auth/token" in plain, "2 secret values" in plain,
            'data-role="inline-secrets"' in clean, '{"$secret": "company/db-password"}' in form.replace("&#34;", '"'),
        ),
        (True, True, True, False, True),
    )
    return


def test_a_reference_problem_on_the_create_form_is_shown_next_to_the_packet():
    """
    **Feature: RPA secrets by reference (ADM-07)**
    **Property: the specification form maps a reference error onto the Default Work Packet field, listing each path and message.**
    """
    error = RpaSecretReferenceError("two", issues=[("/a", "there is no secret named x in the secrets vault"), ("/b", "you may not read the vault secret y")])
    testbase.assert_equal(
        routes_rpa._rpa_spec_field_errors(exc=error),
        {"default_packet": "/a: there is no secret named x in the secrets vault; /b: you may not read the vault secret y"},
    )
    return
