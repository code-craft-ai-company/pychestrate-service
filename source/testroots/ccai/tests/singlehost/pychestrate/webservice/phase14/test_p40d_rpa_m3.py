"""
.. module:: test_p40d_rpa_m3
    :synopsis: Tests for Phase 11 M3 -- the REST surface end to end through
               the handlers, code-defined job types, metric and audit
               registrations, and the OpenAPI contract coverage.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os

from typing import Any, Dict, List, Optional, Tuple

from ccai import testbase

from ccai.pychestrate.webservice.extensions.registry import (
    list_resource_extensions,
    register_factory_implementation,
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
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from ccai.pychestrate.webservice.metrics.ingest import (
    register_builtin_extensions as metrics_register,
)
from ccai.pychestrate.webservice.metrics.ingest.extensions.metric_definition import (
    MetricDefinitionExtension,
)
from ccai.pychestrate.webservice.orchestration.rpa import (
    CodeDefinedVersion,
    ProcessJobType,
    RpaJobTypeInputs,
    RpaSpecInputs,
    RpaTriggerAspects,
    RpaVersionInputs,
    create_spec,
    get_job_type,
    list_job_types,
    publish_version,
    register_builtin_extensions as rpa_register,
    register_job_type,
    resolve_version,
    sync_code_defined_job_types,
    trigger_job,
)
from ccai.pychestrate.webservice.orchestration.rpa import service as rpa_service
from ccai.pychestrate.webservice.orchestration.rpa.restapi.v1 import rpa_routes
from ccai.pychestrate.webservice.webinterface.site_shell import ui_profile

from ccai.pychestrate.webservice.jobs.run.state import models as _run_state_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.dispatch import models as _dispatch_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.envelope import models as _envelope_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.results import models as _results_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.rpa import models as _rpa_models  # noqa: F401

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_REF = "7"
ACTOR_ID = "00000000-0000-4000-8000-000000060002"
CLIENT_ID = "11111111-1111-4000-8000-0000000060a1"
POD_ID = "22222222-2222-4000-8000-0000000060a2"


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
                source="dev", file_path=None, env_var=None, key_id="test-rpa-p40d-ed25519",
            ),
        )
    finally:
        del os.environ["PYCHESTRATE_DEV_MODE"]
    rpa_service.set_active_job_dispatcher(dispatcher=JobDispatcher(transport=InMemoryTransport()))
    return


# ---------------------------------------------------------------------------
# REST harness
# ---------------------------------------------------------------------------


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
                 body: Any = None, query: Optional[Dict[str, str]] = None, path: str = "/api/v1/rpa") -> None:
        self.db_session = db_session
        self.auth_principal = _Principal()
        self.path_params = path_params or {}
        self.query_params = _Query(query)
        self.path = path
        self.body = json.dumps(body).encode("utf-8") if body is not None else b""
        return


class _Patches:
    """
        Swap the route module's permission, project, and candidate seams
        for fakes; restore on exit.
    """

    def __init__(self, *, candidates: Tuple[DispatchCandidate, ...]) -> None:
        self._candidates = candidates
        self._saved: Dict[str, Any] = {}
        return

    def __enter__(self) -> "_Patches":
        self._saved["_require_permission"] = rpa_routes._require_permission
        self._saved["_require_project_exists"] = rpa_routes._require_project_exists
        self._saved["resolve_dispatch_candidates"] = rpa_routes.resolve_dispatch_candidates

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


def _candidate() -> Tuple[DispatchCandidate, ...]:
    rtnval = (
        DispatchCandidate(
            client_id=CLIENT_ID, pod_id=POD_ID, capability_tags=tuple(),
            inflight_dispatch_count=0, last_dispatched_at_iso="",
        ),
    )
    return rtnval


def test_rest_registry_spec_and_trigger_round_trip():
    """
    **Feature: 6-rpa-orchestration (M3)**
    **Property: through the REST handlers an operator can register a job
    type (201), publish a version (201), create a specification (201),
    trigger a job (202), list and read it (200), read its logs (200),
    cancel it (200), and cancelling again answers 409.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    with _Patches(candidates=_candidate()):
        response = rpa_routes.handle_create_job_type(_Request(db_session=session, body={
            "type_id": "invoice-import", "display_name": "Invoice Import",
            "execution_mode": "process",
            "packet_schema": {"type": "object", "required": ["customer_id"]},
            "secret_fields": ["auth.token"],
        }))
        testbase.assert_equal(response.status_code, 201)
        testbase.assert_equal(_body(response)["type_id"], "invoice-import")

        response = rpa_routes.handle_publish_version(_Request(
            db_session=session, path_params={"type_id": "invoice-import"},
            body={"version": "1.0.0", "source": {"kind": "git", "ref": "https://x/y.git#v1"},
                  "entrypoint": {"command": ["python", "-m", "jobs.invoice"]}},
        ))
        testbase.assert_equal(response.status_code, 201)

        response = rpa_routes.handle_create_spec(_Request(
            db_session=session, path_params={"project_id": PROJECT_REF},
            body={"name": "nightly", "type_id": "invoice-import", "default_packet": {"region": "eu"}},
        ))
        testbase.assert_equal(response.status_code, 201)
        spec_id = _body(response)["spec_id"]

        response = rpa_routes.handle_trigger_job(_Request(
            db_session=session, path_params={"project_id": PROJECT_REF, "spec_id": spec_id},
            body={"work_packet": {"customer_id": 42, "auth": {"token": "s3cret"}}},
        ))
        testbase.assert_equal(response.status_code, 202)
        job = _body(response)
        testbase.assert_equal(job["status"], "running")
        testbase.assert_equal(job["work_packet"]["auth"]["token"], "***REDACTED***")
        testbase.assert_equal(job["trigger_cause"]["kind"], "api")

        response = rpa_routes.handle_list_jobs(_Request(
            db_session=session, path_params={"project_id": PROJECT_REF},
        ))
        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(_body(response)["total"], 1)

        response = rpa_routes.handle_read_job(_Request(
            db_session=session, path_params={"project_id": PROJECT_REF, "job_id": job["job_id"]},
        ))
        testbase.assert_equal(response.status_code, 200)

        response = rpa_routes.handle_read_job_logs(_Request(
            db_session=session, path_params={"project_id": PROJECT_REF, "job_id": job["job_id"]},
        ))
        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(_body(response)["status"], "running")

        response = rpa_routes.handle_cancel_job(_Request(
            db_session=session, path_params={"project_id": PROJECT_REF, "job_id": job["job_id"]},
        ))
        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(_body(response)["status"], "cancelled")

        response = rpa_routes.handle_cancel_job(_Request(
            db_session=session, path_params={"project_id": PROJECT_REF, "job_id": job["job_id"]},
        ))
        testbase.assert_equal(response.status_code, 409)
    return


def test_rest_trigger_error_mapping():
    """
    **Feature: 6-rpa-orchestration (M3)**
    **Property: a packet failing the schema answers 422 with per-path
    errors; no eligible pod answers 409; an unknown specification 404;
    an unknown job type on spec creation 404; a duplicate type 409.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    with _Patches(candidates=_candidate()):
        rpa_routes.handle_create_job_type(_Request(db_session=session, body={
            "type_id": "strict-job", "display_name": "Strict",
            "packet_schema": {"type": "object", "required": ["customer_id"],
                              "properties": {"customer_id": {"type": "integer"}}},
        }))
        response = rpa_routes.handle_create_job_type(_Request(db_session=session, body={
            "type_id": "strict-job", "display_name": "Strict again",
        }))
        testbase.assert_equal(response.status_code, 409)

        rpa_routes.handle_publish_version(_Request(
            db_session=session, path_params={"type_id": "strict-job"},
            body={"version": "1.0.0", "source_kind": "package", "source_ref": "jobs==1",
                  "entrypoint": {"command": ["job"]}},
        ))
        response = rpa_routes.handle_create_spec(_Request(
            db_session=session, path_params={"project_id": PROJECT_REF},
            body={"name": "s", "type_id": "strict-job"},
        ))
        spec_id = _body(response)["spec_id"]

        response = rpa_routes.handle_trigger_job(_Request(
            db_session=session, path_params={"project_id": PROJECT_REF, "spec_id": spec_id},
            body={"work_packet": {"customer_id": "not-an-int"}},
        ))
        testbase.assert_equal(response.status_code, 422)
        problem = _body(response)
        testbase.assert_true(any(e["path"] == "/customer_id" for e in problem["errors"]))

        response = rpa_routes.handle_trigger_job(_Request(
            db_session=session, path_params={"project_id": PROJECT_REF, "spec_id": "not-a-spec"},
            body={"work_packet": {}},
        ))
        testbase.assert_equal(response.status_code, 404)

        response = rpa_routes.handle_create_spec(_Request(
            db_session=session, path_params={"project_id": PROJECT_REF},
            body={"name": "orphan", "type_id": "no-such-type"},
        ))
        testbase.assert_equal(response.status_code, 404)

    with _Patches(candidates=tuple()):
        response = rpa_routes.handle_trigger_job(_Request(
            db_session=session, path_params={"project_id": PROJECT_REF, "spec_id": spec_id},
            body={"work_packet": {"customer_id": 1}},
        ))
        testbase.assert_equal(response.status_code, 409)
        testbase.assert_equal(_body(response).get("reason"), "no_eligible_pod")
    return


# ---------------------------------------------------------------------------
# Code-defined job types
# ---------------------------------------------------------------------------


class _InvoiceImportType(ProcessJobType):
    @classmethod
    def type_id(cls) -> str:
        return "code-invoice"

    @classmethod
    def display_name(cls) -> str:
        return "Code Invoice Import"

    @classmethod
    def packet_schema(cls):
        return {"type": "object", "required": ["customer_id"]}

    @classmethod
    def versions(cls):
        return (
            CodeDefinedVersion(
                version="1.0.0", source_kind="package", source_ref="jobs==1.0.0",
                entrypoint={"command": ["python", "-m", "jobs.invoice"]},
            ),
            CodeDefinedVersion(
                version="1.1.0", source_kind="package", source_ref="jobs==1.1.0",
                entrypoint={"command": ["python", "-m", "jobs.invoice"]},
            ),
        )


def test_code_defined_job_types_are_mirrored_and_database_wins():
    """
    **Feature: 6-rpa-orchestration (M3)**
    **Property: a registered rpa_job_type implementation appears in the
    registry with its versions on first read; an administrator's row
    for the same slug keeps its fields and only gains missing versions;
    a specification can bind and trigger the code-defined type.**
    """
    _prepare_runtime()
    register_factory_implementation(implementation=_InvoiceImportType)
    _engine, session = build_in_memory_session()

    types = list_job_types(db_session=session)
    ids = [t.type_id for t in types]
    testbase.assert_true("code-invoice" in ids)
    view = get_job_type(db_session=session, type_id="code-invoice")
    testbase.assert_equal(view.display_name, "Code Invoice Import")
    testbase.assert_equal(view.active_version_count, 2)
    testbase.assert_equal(view.latest_active_version, "1.1.0")
    testbase.assert_true(str(view.created_by_id).startswith("extension:"))

    # Database wins on conflict: rename the type and add an admin version;
    # a re-sync leaves both alone and adds nothing new.
    rpa_service.update_job_type(db_session=session, type_id="code-invoice", display_name="Renamed")
    publish_version(
        db_session=session, type_id="code-invoice",
        inputs=RpaVersionInputs(version="2.0.0", source_kind="package", source_ref="jobs==2",
                                entrypoint={"command": ["job"]}),
    )
    changed = sync_code_defined_job_types(db_session=session)
    testbase.assert_equal(changed, [])
    view = get_job_type(db_session=session, type_id="code-invoice")
    testbase.assert_equal(view.display_name, "Renamed")
    testbase.assert_equal(view.active_version_count, 3)

    spec = create_spec(
        db_session=session, project_id=PROJECT_REF,
        inputs=RpaSpecInputs(name="code", type_id="code-invoice"),
    )
    job = trigger_job(
        db_session=session, project_id=PROJECT_REF, spec_id=spec.spec_id,
        work_packet={"customer_id": 1},
        aspects=RpaTriggerAspects(actor_id=ACTOR_ID, candidates=_candidate(), project_slug="demo"),
    )
    testbase.assert_equal(job.resolved_version, "2.0.0")

    # A fresh database sees the code-defined type on the first miss too.
    _engine2, session2 = build_in_memory_session()
    resolved = resolve_version(db_session=session2, type_id="code-invoice", selector="latest-active")
    testbase.assert_equal(resolved.version, "1.1.0")
    return


# ---------------------------------------------------------------------------
# Observability registrations + OpenAPI coverage
# ---------------------------------------------------------------------------


def test_phase11_metric_extensions_are_registered():
    """
    **Feature: Phase 11 (M3)**
    **Property: the metric registry declares counters for RPA triggers,
    completions, failures, and UI-profile deployment changes, each bound
    to its bus topic.**
    """
    reset_registry_for_testing()
    metrics_register()
    by_topic = {
        ext.source_topic(): ext.metric_name()
        for ext in list_resource_extensions(base_class=MetricDefinitionExtension)
    }
    testbase.assert_equal(by_topic.get("entity.rpa.job_started"), "pychestrate_rpa_jobs_triggered_total")
    testbase.assert_equal(by_topic.get("entity.rpa.job_completed"), "pychestrate_rpa_jobs_completed_total")
    testbase.assert_equal(by_topic.get("entity.rpa.job_failed"), "pychestrate_rpa_jobs_failed_total")
    testbase.assert_equal(
        by_topic.get("entity.ui_profile.deployment_changed"),
        "pychestrate_ui_profile_deployment_changed_total",
    )
    return


def test_deployment_profile_change_emits_bus_event():
    """
    **Feature: 9-ui-profiles (M3)**
    **Property: saving the deployment profile emits
    entity.ui_profile.deployment_changed with the new surfaces.**
    """
    import sqlalchemy as sa
    from sqlalchemy.orm import sessionmaker
    from ccai.pychestrate.core.orm import PychestrateModelBase
    from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base

    reset_event_bus()
    engine = sa.create_engine("sqlite://")
    PychestrateModelBase.metadata.create_all(engine)
    PychestratePhase1Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    received: List[EntityEvent] = []
    subscribe(topic=ui_profile.DEPLOYMENT_CHANGED_TOPIC, subscriber=lambda e: received.append(e))
    ui_profile.invalidate_deployment_cache()
    ui_profile.set_deployment_surfaces(db_session=session, surfaces=["rpa", "build"], actor_id="00000000-0000-4000-8000-0000000600ad")
    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(received[0].payload["surfaces"], ["build", "rpa"])
    testbase.assert_equal(received[0].payload["actor_id"], "00000000-0000-4000-8000-0000000600ad")
    ui_profile.invalidate_deployment_cache()
    session.close()
    return


def test_openapi_contract_covers_every_rpa_and_profile_route():
    """
    **Feature: Phase 11 (M3)**
    **Property: every RPA and UI-profile REST path the service attaches
    is described in specs/openapi/pychestrate.yaml with matching
    methods.**
    """
    import yaml
    from ccai.pychestrate.webservice.security.auth.restapi.v1 import me_routes
    from ccai.pychestrate.webservice.webinterface.site_shell import ui_profile_routes

    class _App:
        def __init__(self) -> None:
            self.routes: Dict[str, set] = {}

        def attach_route(self, path: str, methods: Optional[List[str]] = None):
            def _decorator(func):
                self.routes.setdefault(path, set()).update(m.lower() for m in (methods or ["GET"]))
                return func
            return _decorator

    app = _App()
    rpa_routes.register_rpa_routes(app=app, version_prefix="/api/v1")
    ui_profile_routes.register_ui_profile_api_routes(app=app, version_prefix="/api/v1")
    me_routes.register_me_routes(app=app, version_prefix="/api/v1")

    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = here
    while not os.path.isdir(os.path.join(repo_root, "specs")) and repo_root != os.path.dirname(repo_root):
        repo_root = os.path.dirname(repo_root)
    with open(os.path.join(repo_root, "specs", "openapi", "pychestrate.yaml"), "r", encoding="utf-8") as fh:
        document = yaml.safe_load(fh)
    documented = document["paths"]

    missing: List[str] = []
    for path, methods in app.routes.items():
        if "/rpa" not in path and "ui-profile" not in path and "ui.surfaces" not in path:
            continue
        relative = path[len("/api/v1"):]
        entry = documented.get(relative, None)
        if entry is None:
            missing.append(relative)
            continue
        for method in methods:
            if method not in entry:
                missing.append("{} {}".format(method.upper(), relative))
    testbase.assert_equal(missing, [], "undocumented routes: {}".format(missing))
    return


def test_audit_wiring_is_idempotent_across_bootstraps():
    """
    **Feature: Phase 11 (M3) -- audit regression**
    **Property: calling the audit wire_bus_subscribers twice (as the
    phase-1 and phase-2 bootstraps do) subscribes each topic once, so a
    published RPA event yields exactly one audit record instead of a
    unique-constraint failure on the duplicate.**
    """
    from ccai.pychestrate.webservice.audit import bus_subscriber as audit_bus
    from ccai.pychestrate.webservice.audit import register_builtin_extensions as audit_register
    from ccai.pychestrate.webservice.audit.models import AuditRecord
    from ccai.pychestrate.webservice.messaging import event_bus
    from ccai.pychestrate.core.defaults import new_uuid

    reset_registry_for_testing()
    reset_event_bus()
    audit_bus.reset_wiring_for_testing()
    audit_register()
    engine, session = build_in_memory_session()
    from sqlalchemy.orm import sessionmaker
    factory = sessionmaker(bind=engine)

    audit_bus.wire_bus_subscribers(session_factory=factory)
    audit_bus.wire_bus_subscribers(session_factory=factory)
    topic = "entity.rpa.job_type_published"
    bucket = event_bus._SUBSCRIBERS.get(topic, [])
    testbase.assert_equal(len(bucket), 1)

    event_bus.publish(event=EntityEvent(
        topic=topic,
        payload={"type_id": "invoice-import", "version": "1.0.0", "actor_id": None},
        source_event_id=new_uuid(),
    ))
    records = session.query(AuditRecord).filter(AuditRecord.source_topic == topic).all()
    testbase.assert_equal(len(records), 1)
    testbase.assert_equal(records[0].kind, "audit.rpa.job_type_published")

    # A bus reset drops the handler; wiring again re-subscribes once.
    reset_event_bus()
    audit_bus.wire_bus_subscribers(session_factory=factory)
    testbase.assert_equal(len(event_bus._SUBSCRIBERS.get(topic, [])), 1)
    audit_bus.reset_wiring_for_testing()
    reset_event_bus()
    return


def test_pod_capability_advertisement_route_persists_rpa_kind():
    """
    **Feature: 6-rpa-orchestration (M3) -- pod-side capability advertisement**
    **Property: PUT /clients/{id}/capabilities (mTLS-matched pod) replaces
    the client's capability rows, rejects unknown kinds with 422, and the
    persisted rpa value feeds the dispatch-matcher tags.**
    """
    from ccai.pychestrate.webservice.agents import register_builtin_extensions as agents_register
    from ccai.pychestrate.webservice.clients.restapi.v1 import client_dispatch_routes as routes
    from ccai.pychestrate.webservice.orchestration.rpa.candidates import capability_tags_for_client
    from ccai.pychestrate.webservice.agents import models as _agents_models  # noqa: F401

    reset_registry_for_testing()
    reset_event_bus()
    agents_register()
    _engine, session = build_in_memory_session()

    saved = (routes._validate_client_id_or_abort, routes._require_mtls_client_cn,
             routes._require_cert_matches_client_id)
    routes._validate_client_id_or_abort = lambda *, request, client_id: None
    routes._require_mtls_client_cn = lambda *, request: "cn"
    routes._require_cert_matches_client_id = lambda *, request, client_cn, client_id: None
    try:
        request = _Request(
            db_session=session, path_params={"client_id": CLIENT_ID},
            body={"advertisements": [
                {"kind": "rpa", "value": {"job_types": ["invoice-import@1.0.0"], "taskplus": "1.0.2", "tags": ["browser"]}},
                {"kind": "toolchain", "value": {"python": "3.12"}},
            ]},
            path="/api/v1/clients/{}/capabilities".format(CLIENT_ID),
        )
        response = routes.handle_put_client_capabilities(request)
        testbase.assert_equal(response.status_code, 200)
        kinds = sorted(entry["kind"] for entry in _body(response))
        testbase.assert_equal(kinds, ["rpa", "toolchain"])

        tags = capability_tags_for_client(db_session=session, client_id=CLIENT_ID)
        for expected in ("rpa", "rpa:invoice-import@1.0.0", "browser", "toolchain"):
            testbase.assert_true(expected in tags, expected)

        bad = _Request(
            db_session=session, path_params={"client_id": CLIENT_ID},
            body={"advertisements": [{"kind": "teleport", "value": {}}]},
        )
        response = routes.handle_put_client_capabilities(bad)
        testbase.assert_equal(response.status_code, 422)

        malformed = _Request(db_session=session, path_params={"client_id": CLIENT_ID}, body={"nope": 1})
        response = routes.handle_put_client_capabilities(malformed)
        testbase.assert_equal(response.status_code, 422)
    finally:
        (routes._validate_client_id_or_abort, routes._require_mtls_client_cn,
         routes._require_cert_matches_client_id) = saved
    return
