"""
.. module:: test_p40f_rpa_run_experience_m1
    :synopsis: Tests for the RPA run experience fixes: replays are reported,
               packets are checked before pods, unknown REST fields are
               refused, failed runs keep the typed packet, and job types can
               be edited (audit issues E2E-33, E2E-34, PRJ-30, DOC-18,
               ADM-37).
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

from ccai.pychestrate.webservice.audit import register_builtin_extensions as audit_register
from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension
from ccai.pychestrate.webservice.extensions.registry import (
    list_resource_extensions,
    reset_registry_for_testing,
)
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
from ccai.pychestrate.webservice.messaging.event_bus import (
    reset_for_testing as reset_event_bus,
    subscribe,
)
from ccai.pychestrate.webservice.orchestration.rpa import (
    PacketValidationError,
    RpaEventTopics,
    RpaJobTypeInputs,
    RpaSpecInputs,
    RpaTriggerAspects,
    RpaVersionInputs,
    check_trigger_packet,
    create_spec,
    list_jobs,
    publish_version,
    register_builtin_extensions as rpa_register,
    register_job_type,
    trigger_job,
    update_job_type,
)
from ccai.pychestrate.webservice.orchestration.rpa import service as rpa_service
from ccai.pychestrate.webservice.orchestration.rpa.restapi.v1 import rpa_routes
from ccai.pychestrate.webservice.webinterface.blueprints.config import routes_rpa_types
from ccai.pychestrate.webservice.webinterface.blueprints.projects import routes_rpa
from ccai.pychestrate.webservice.webinterface.foundation import auth_guard

from ccai.pychestrate.webservice.jobs.run.state import models as _run_state_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.dispatch import models as _dispatch_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.envelope import models as _envelope_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.results import models as _results_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.rpa import models as _rpa_models  # noqa: F401

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_REF = "7"
ACTOR_ID = "00000000-0000-4000-8000-000000080002"
SCHEMA = {"type": "object", "required": ["customer_id"], "properties": {"customer_id": {"type": "integer"}}}


# ===========================================================================
# Runtime + data
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
                source="dev", file_path=None, env_var=None, key_id="test-rpa-p40f-ed25519",
            ),
        )
    finally:
        del os.environ["PYCHESTRATE_DEV_MODE"]
    rpa_service.set_active_job_dispatcher(dispatcher=JobDispatcher(transport=InMemoryTransport()))
    return


def _candidates() -> Tuple[DispatchCandidate, ...]:
    rtnval = (
        DispatchCandidate(
            client_id="11111111-1111-4000-8000-0000000080a1",
            pod_id="22222222-2222-4000-8000-0000000080a2",
            capability_tags=tuple(),
            inflight_dispatch_count=0,
            last_dispatched_at_iso="",
        ),
    )
    return rtnval


def _seed_spec(session: Any, *, schema: Any = None) -> str:
    """
        Register a job type (with ``schema``), publish a version, and
        create a specification in project 7. Returns the spec id.
    """
    register_job_type(
        db_session=session,
        inputs=RpaJobTypeInputs(type_id="invoice-import", display_name="Invoice Import", packet_schema=schema),
        actor_id=ACTOR_ID,
    )
    publish_version(
        db_session=session, type_id="invoice-import",
        inputs=RpaVersionInputs(version="1.0.0", source_kind="package", source_ref="jobs==1",
                                entrypoint={"command": ["job"]}),
        actor_id=ACTOR_ID,
    )
    spec = create_spec(
        db_session=session, project_id=PROJECT_REF,
        inputs=RpaSpecInputs(name="nightly", type_id="invoice-import"),
        actor_id=ACTOR_ID,
    )
    rtnval = spec.spec_id
    return rtnval


def _aspects(**overrides: Any) -> RpaTriggerAspects:
    kwargs: Dict[str, Any] = {"actor_id": ACTOR_ID, "candidates": _candidates(), "project_slug": "demo"}
    kwargs.update(overrides)
    rtnval = RpaTriggerAspects(**kwargs)
    return rtnval


# ===========================================================================
# Service
# ===========================================================================


def test_identical_trigger_inside_the_window_is_reported_as_a_replay():
    """
    **Feature: RPA run experience (E2E-33)**
    **Property: triggering the same packet twice inside the idempotency
    window returns the first job marked ``replayed`` instead of silently
    handing it back as if it were new.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    spec_id = _seed_spec(session)
    first = trigger_job(db_session=session, project_id=PROJECT_REF, spec_id=spec_id,
                        work_packet={"n": 1}, aspects=_aspects())
    second = trigger_job(db_session=session, project_id=PROJECT_REF, spec_id=spec_id,
                         work_packet={"n": 1}, aspects=_aspects())
    testbase.assert_equal((first.replayed, second.replayed, second.job_id), (False, True, first.job_id))
    return


def test_run_anyway_starts_a_new_job_inside_the_window():
    """
    **Feature: RPA run experience (E2E-33)**
    **Property: with the idempotency window turned off ("Run anyway") an
    identical packet starts a second job.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    spec_id = _seed_spec(session)
    trigger_job(db_session=session, project_id=PROJECT_REF, spec_id=spec_id,
                work_packet={"n": 1}, aspects=_aspects())
    again = trigger_job(db_session=session, project_id=PROJECT_REF, spec_id=spec_id,
                        work_packet={"n": 1}, aspects=_aspects(idempotency_window_seconds=0))
    total = list_jobs(db_session=session, project_id=PROJECT_REF).total
    testbase.assert_equal((again.replayed, total), (False, 2))
    return


def test_check_trigger_packet_rejects_a_bad_packet_without_creating_a_job():
    """
    **Feature: RPA run experience (DOC-18)**
    **Property: the side-effect-free packet check raises
    PacketValidationError for a packet failing the schema and creates no
    job.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    spec_id = _seed_spec(session, schema=SCHEMA)
    refused = False
    try:
        check_trigger_packet(db_session=session, project_id=PROJECT_REF, spec_id=spec_id,
                             work_packet={"customer_id": "x"})
    except PacketValidationError:
        refused = True
    total = list_jobs(db_session=session, project_id=PROJECT_REF).total
    testbase.assert_equal((refused, total), (True, 0))
    return


def test_editing_a_job_type_publishes_an_audited_update_event():
    """
    **Feature: RPA run experience (ADM-37)**
    **Property: update_job_type publishes entity.rpa.job_type_updated
    naming the changed fields and the actor, so edits reach the audit
    log.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _seed_spec(session)
    received: List[Any] = []
    subscribe(topic=RpaEventTopics.JOB_TYPE_UPDATED, subscriber=lambda evt: received.append(evt))
    update_job_type(db_session=session, type_id="invoice-import", display_name="Invoices", actor_id=ACTOR_ID)
    testbase.assert_equal(
        [(evt.payload["changed_fields"], evt.payload["actor_id"]) for evt in received],
        [(["display_name"], ACTOR_ID)],
    )
    return


def test_job_type_update_topic_has_an_audit_kind():
    """
    **Feature: RPA run experience (ADM-37)**
    **Property: the audit catalog maps entity.rpa.job_type_updated to
    audit.rpa.job_type_updated.**
    """
    reset_registry_for_testing()
    audit_register()
    kinds = {ext.source_topic: ext.kind for ext in list_resource_extensions(base_class=AuditEventTypeExtension)}
    testbase.assert_equal(kinds.get(RpaEventTopics.JOB_TYPE_UPDATED), "audit.rpa.job_type_updated")
    return


# ===========================================================================
# REST
# ===========================================================================


class _Principal:
    user_id = ACTOR_ID


class _Query:
    def get(self, key: str, default: Any = None) -> Any:
        return default


class _Request:
    def __init__(self, *, db_session: Any, path_params: Optional[Dict[str, str]] = None, body: Any = None) -> None:
        self.db_session = db_session
        self.auth_principal = _Principal()
        self.path_params = path_params or {}
        self.query_params = _Query()
        self.path = "/api/v1/rpa"
        self.body = json.dumps(body).encode("utf-8") if body is not None else b""
        return


class _Patches:
    def __init__(self, *, candidates: Tuple[DispatchCandidate, ...]) -> None:
        self._candidates = candidates
        self._saved: Dict[str, Any] = {}
        return

    def __enter__(self) -> "_Patches":
        for name in ("_require_permission", "_require_project_exists", "resolve_dispatch_candidates"):
            self._saved[name] = getattr(rpa_routes, name)

        class _Project:
            slug = "demo"
            name = "Demo"

        rpa_routes._require_permission = lambda *, request, db_session, permission_key: _Principal()
        rpa_routes._require_project_exists = lambda *, request, db_session, project_id: _Project()
        rpa_routes.resolve_dispatch_candidates = (
            lambda *, db_session, project_id, target_pod_id=None: list(self._candidates)
        )
        return self

    def __exit__(self, *exc: Any) -> None:
        for name, value in self._saved.items():
            setattr(rpa_routes, name, value)
        return


def _body(response: Any) -> Dict[str, Any]:
    rtnval = json.loads(response._body.decode("utf-8"))
    return rtnval


def _trigger(session: Any, spec_id: str, body: Dict[str, Any]) -> Any:
    rtnval = rpa_routes.handle_trigger_job(_Request(
        db_session=session, path_params={"project_id": PROJECT_REF, "spec_id": spec_id}, body=body,
    ))
    return rtnval


def test_rest_reports_a_bad_packet_even_when_no_pod_is_available():
    """
    **Feature: RPA run experience (DOC-18)**
    **Property: with no eligible pod, a packet failing the schema still
    answers 422 with its errors (the packet is checked before pods), not
    409 no_eligible_pod.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    spec_id = _seed_spec(session, schema=SCHEMA)
    with _Patches(candidates=tuple()):
        response = _trigger(session, spec_id, {"work_packet": {"customer_id": "x"}})
    testbase.assert_equal(
        (response.status_code, [e["path"] for e in _body(response)["errors"]]),
        (422, ["/customer_id"]),
    )
    return


def test_rest_refuses_unknown_fields_in_a_specification():
    """
    **Feature: RPA run experience (DOC-18)**
    **Property: creating a specification with a misspelled field
    (``timeout_seconds``) answers 422 naming the field instead of
    silently ignoring it.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _seed_spec(session)
    with _Patches(candidates=_candidates()):
        response = rpa_routes.handle_create_spec(_Request(
            db_session=session, path_params={"project_id": PROJECT_REF},
            body={"name": "typo", "type_id": "invoice-import", "timeout_seconds": 30},
        ))
    testbase.assert_equal(
        (response.status_code, _body(response).get("unknown_fields")), (422, ["timeout_seconds"]),
    )
    return


def test_rest_replay_answers_200_and_says_so():
    """
    **Feature: RPA run experience (E2E-33)**
    **Property: a second identical trigger inside the window answers
    200 with ``replayed: true`` (the first answered 202).**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    spec_id = _seed_spec(session)
    with _Patches(candidates=_candidates()):
        first = _trigger(session, spec_id, {"work_packet": {"n": 1}})
        second = _trigger(session, spec_id, {"work_packet": {"n": 1}})
    testbase.assert_equal(
        (first.status_code, second.status_code, _body(second)["replayed"]), (202, 200, True),
    )
    return


def test_rest_allow_duplicate_starts_a_new_job():
    """
    **Feature: RPA run experience (E2E-33)**
    **Property: ``allow_duplicate: true`` starts a new job (202) even
    inside the idempotency window.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    spec_id = _seed_spec(session)
    with _Patches(candidates=_candidates()):
        first = _trigger(session, spec_id, {"work_packet": {"n": 1}})
        second = _trigger(session, spec_id, {"work_packet": {"n": 1}, "allow_duplicate": True})
    testbase.assert_equal(
        (second.status_code, _body(second)["job_id"] != _body(first)["job_id"]), (202, True),
    )
    return


# ===========================================================================
# Run form (projects UI)
# ===========================================================================


class _FakeDbSession:
    def close(self) -> None:
        return


class _FakeAuth:
    redirect_response = None
    db_session = _FakeDbSession()
    session: Dict[str, Any] = {}
    csrf_token = "csrf-fresh"
    user_id = "u-member"


class _FakeSpec:
    spec_id = "spec-1"
    project_id = PROJECT_REF
    name = "nightly"
    default_packet: Dict[str, Any] = {}
    secret_fields: Tuple[str, ...] = ()
    packet_schema = None
    resolved_version = "1.0.0"
    target_pod_id = None


class _FakeProjectManager:
    slug = "demo"

    def get_project(self, project_id: int) -> Any:
        class _Project:
            id = 7
            name = "Demo"
        return _Project()


class _FakeRpa:
    """
        RPA service stand-in: ``check_error`` is raised by the packet
        check; ``replayed`` marks the triggered job; triggers are
        recorded with their aspects.
    """

    RpaTriggerAspects = RpaTriggerAspects

    def __init__(self, *, check_error: Optional[Exception] = None, replayed: bool = False) -> None:
        self.check_error = check_error
        self.replayed = replayed
        self.triggered: List[Any] = []
        return

    def get_spec(self, *, db_session: Any, spec_id: str) -> Any:
        return _FakeSpec()

    def list_jobs(self, **kwargs: Any) -> Any:
        class _Page:
            jobs: List[Any] = []
        return _Page()

    def check_trigger_packet(self, **kwargs: Any) -> Dict[str, Any]:
        if self.check_error is not None:
            raise self.check_error
        return dict(kwargs.get("work_packet") or {})

    def trigger_job(self, **kwargs: Any) -> Any:
        self.triggered.append(kwargs["aspects"])

        class _Job:
            job_id = "0f6c2c1e-1111-4000-8000-000000000009"
            replayed = self.replayed
        return _Job()


def _post_run(*, rpa: _FakeRpa, form: Dict[str, str]) -> Tuple[Any, List[Tuple[str, Dict[str, Any], int]]]:
    """
        POST the run form with every seam faked. Returns the response and
        the ``(template, context, status)`` of any page rendered.
    """
    rendered: List[Tuple[str, Dict[str, Any], int]] = []

    def _capture_render(*, template_name: str, context: Dict[str, Any], status_code: int = 200) -> HTMLResponse:
        rendered.append((template_name, context, status_code))
        return HTMLResponse(content="rendered", status_code=status_code)

    seams = {
        "_resolve_authenticated_request": lambda **kwargs: _FakeAuth(),
        "_parse_form_or_empty": lambda **kwargs: dict(form),
        "_build_project_manager": lambda **kwargs: _FakeProjectManager(),
        "_require_project_permission_or_redirect": lambda **kwargs: None,
        "_build_rpa_service": lambda **kwargs: rpa,
        "_resolve_candidates": lambda **kwargs: list(_candidates()),
        "_pod_choices": lambda **kwargs: [],
        "_can_manage": lambda **kwargs: True,
        "_build_default_template_context": lambda **kwargs: {},
        "_attach_session_to_response": lambda **kwargs: None,
        "_render": _capture_render,
        "_redirect_with_flash": lambda **kwargs: HTMLResponse(content="redirect", status_code=303),
    }
    patches = []
    try:
        for name, replacement in seams.items():
            patch = create_module_patch(routes_rpa, name)
            patch.activate().configure(side_effect=replacement)
            patches.append(patch)
        csrf_patch = create_module_patch(auth_guard, "enforce_csrf_or_redirect")
        csrf_patch.activate().configure(side_effect=lambda **kwargs: None)
        patches.append(csrf_patch)
        url_patch = create_module_patch(routes_rpa._url_for_module, "url_for")
        url_patch.activate().configure(side_effect=lambda endpoint, **kwargs: "/" + endpoint)
        patches.append(url_patch)

        class _Request:
            path_params = {"project_id": "7", "spec_id": "spec-1"}

        response = routes_rpa.handle_rpa_run(_Request())
    finally:
        for patch in reversed(patches):
            patch.deactivate()
    rtnval = (response, rendered)
    return rtnval


def test_failed_run_keeps_the_typed_packet_and_shows_the_errors():
    """
    **Feature: RPA run experience (E2E-34, PRJ-30)**
    **Property: when the packet fails validation, the run handler
    re-renders the specification page (422) with the packet exactly as
    typed and one error line per schema issue -- nothing is lost.**
    """
    typed = '{"customer_id": "abc"}'
    rpa = _FakeRpa(check_error=PacketValidationError("bad", issues=[("/customer_id", "is not an integer")]))
    response, rendered = _post_run(rpa=rpa, form={"csrf_token": "csrf-fresh", "work_packet": typed})
    _template, context, status = rendered[0]
    testbase.assert_equal(
        (status, context["run_packet_json"], context["run_errors"], rpa.triggered),
        (422, typed, ["/customer_id: is not an integer"], []),
    )
    return


def test_replayed_run_offers_run_anyway():
    """
    **Feature: RPA run experience (E2E-33)**
    **Property: when the trigger is a replay, the page is re-rendered
    with the earlier job and the replay notice (which carries the "Run
    anyway" button) instead of redirecting as if a job had started.**
    """
    rpa = _FakeRpa(replayed=True)
    response, rendered = _post_run(rpa=rpa, form={"csrf_token": "csrf-fresh", "work_packet": "{}"})
    _template, context, status = rendered[0]
    testbase.assert_equal(
        (status, context["replay_job"].job_id, context["replay_message"] != ""),
        (200, "0f6c2c1e-1111-4000-8000-000000000009", True),
    )
    return


def test_run_anyway_turns_off_the_idempotency_window():
    """
    **Feature: RPA run experience (E2E-33)**
    **Property: posting the run form with ``allow_duplicate=1`` triggers
    with the idempotency window set to zero.**
    """
    rpa = _FakeRpa()
    _post_run(rpa=rpa, form={"csrf_token": "csrf-fresh", "work_packet": "{}", "allow_duplicate": "1"})
    testbase.assert_equal([aspects.idempotency_window_seconds for aspects in rpa.triggered], [0])
    return


def test_run_on_a_chosen_pod_only_offers_that_pod_to_dispatch():
    """
    **Feature: RPA run experience (E2E-34)**
    **Property: choosing a pod in the run form limits the dispatch
    candidates to that pod.**
    """
    rpa = _FakeRpa()
    chosen = _candidates()[0].pod_id
    _post_run(rpa=rpa, form={"csrf_token": "csrf-fresh", "work_packet": "{}", "target_pod": chosen})
    testbase.assert_equal(
        [[c.pod_id for c in aspects.candidates] for aspects in rpa.triggered], [[chosen]],
    )
    return


def test_spec_page_explains_why_no_pod_can_run_the_job():
    """
    **Feature: RPA run experience (PRJ-30)**
    **Property: when no pod is eligible, the specification page says so
    before the operator fills in the form (and names what a pod needs).**
    """
    availability = {}
    patch = create_module_patch(routes_rpa, "_resolve_candidates")
    patch.activate().configure(side_effect=lambda **kwargs: [])
    try:
        availability = routes_rpa._run_availability(db_session=_FakeDbSession(), project_id=7, spec=_FakeSpec())
    finally:
        patch.deactivate()
    testbase.assert_equal(
        (availability["pods"], availability["blocked_reason"]), ([], routes_rpa.NO_ELIGIBLE_POD_MESSAGE),
    )
    return


# ===========================================================================
# Job type admin
# ===========================================================================


class _AdminAuth:
    redirect_response = None
    session: Dict[str, Any] = {}
    csrf_token = "csrf-fresh"
    user_id = ACTOR_ID

    def __init__(self, db_session: Any) -> None:
        self.db_session = db_session
        return


def _admin_call(
        *,
        handler: Any,
        session: Any,
        method: str,
        path_params: Dict[str, str],
        form: Dict[str, str]
    ) -> Tuple[Any, List[Tuple[str, Dict[str, Any], int]], List[str]]:
    """
        Call a job-type admin handler with the real RPA service on
        ``session`` and the auth, CSRF and rendering seams faked.
    """
    rendered: List[Tuple[str, Dict[str, Any], int]] = []
    redirects: List[str] = []

    def _capture_render(*, template_name: str, context: Dict[str, Any], status_code: int = 200) -> HTMLResponse:
        rendered.append((template_name, context, status_code))
        return HTMLResponse(content="rendered", status_code=status_code)

    def _capture_redirect(*, session: Any, url: str, message: str, category: str) -> Any:
        redirects.append(url)
        return HTMLResponse(content="redirect", status_code=303)

    seams = {
        "_resolve_authenticated_request": lambda **kwargs: _AdminAuth(session),
        "_deny_manage": lambda *args, **kwargs: None,
        "_parse_form_or_empty": lambda **kwargs: dict(form),
        "_parse_form_multi": lambda **kwargs: {key: [value] for key, value in form.items()},
        "_has_permission": lambda **kwargs: True,
        "_build_default_template_context": lambda **kwargs: {},
        "_attach_session_to_response": lambda **kwargs: None,
        "_render": _capture_render,
        "_redirect_with_flash": _capture_redirect,
    }
    patches = []
    try:
        for name, replacement in seams.items():
            patch = create_module_patch(routes_rpa_types, name)
            patch.activate().configure(side_effect=replacement)
            patches.append(patch)
        url_patch = create_module_patch(routes_rpa_types._url_for_module, "url_for")
        url_patch.activate().configure(side_effect=lambda endpoint, **kwargs: "/" + endpoint)
        patches.append(url_patch)
        csrf_patch = create_module_patch(auth_guard, "enforce_csrf_or_redirect")
        csrf_patch.activate().configure(side_effect=lambda **kwargs: None)
        patches.append(csrf_patch)

        class _Request:
            pass

        request = _Request()
        request.method = method
        request.path_params = path_params
        response = handler(request)
    finally:
        for patch in reversed(patches):
            patch.deactivate()
    rtnval = (response, rendered, redirects)
    return rtnval


def test_job_type_edit_saves_the_new_display_name():
    """
    **Feature: RPA run experience (ADM-37)**
    **Property: POSTing the edit form changes the registered job type's
    display name and returns to its page.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _seed_spec(session)
    _response, _rendered, redirects = _admin_call(
        handler=routes_rpa_types.handle_rpa_type_edit, session=session, method="POST",
        path_params={"type_id": "invoice-import"},
        form={"csrf_token": "csrf-fresh", "display_name": "Invoice Import v2", "description": "",
              "capability_requirements": "", "secret_fields": "", "packet_schema": ""},
    )
    stored = rpa_service.get_job_type(db_session=session, type_id="invoice-import")
    testbase.assert_equal((stored.display_name, redirects), ("Invoice Import v2", ["/config.rpa_type_detail"]))
    return


def test_failed_publish_keeps_the_typed_version_fields():
    """
    **Feature: RPA run experience (ADM-37)**
    **Property: when publishing a version fails, the job type page is
    re-rendered (400) with the submitted version, source and entrypoint
    instead of redirecting and wiping the form.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _seed_spec(session)
    form = {"csrf_token": "csrf-fresh", "version": "2.0.0", "source_kind": "git", "source_ref": "",
            "entrypoint": '{"command": ["job"]}', "environment": "", "timeout_minutes": "30"}
    _response, rendered, _redirects = _admin_call(
        handler=routes_rpa_types.handle_rpa_type_publish, session=session, method="POST",
        path_params={"type_id": "invoice-import"}, form=form,
    )
    _template, context, status = rendered[0]
    kept = context["form_data"]
    testbase.assert_equal(
        (status, kept.get("version"), kept.get("entrypoint")), (400, "2.0.0", '{"command": ["job"]}'),
    )
    return
