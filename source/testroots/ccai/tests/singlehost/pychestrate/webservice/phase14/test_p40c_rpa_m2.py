"""
.. module:: test_p40c_rpa_m2
    :synopsis: Tests for 6-rpa-orchestration M2 -- result-completion branch,
               progress frame kind, pipeline step kind, watch action, and
               capability tag enrichment.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict, List, Tuple

from ccai import testbase

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
    list_resource_extensions,
    reset_registry_for_testing,
)
from ccai.pychestrate.webservice.ingest.progress import FRAME_KIND_RPA, SUPPORTED_FRAME_KINDS
from ccai.pychestrate.webservice.ingest.result import completion as result_completion
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
from ccai.pychestrate.webservice.orchestration.pipelines.definition import (
    register_builtin_extensions as pipelines_register,
)
from ccai.pychestrate.webservice.orchestration.pipelines.definition.factories.rpa_step_kind import (
    RpaStepKind,
)
from ccai.pychestrate.webservice.orchestration.rpa import (
    RpaEventTopics,
    RpaJobStatus,
    RpaJobTypeInputs,
    RpaSpecInputs,
    RpaTriggerAspects,
    RpaVersionInputs,
    create_spec,
    get_job,
    publish_version,
    register_builtin_extensions as rpa_register,
    register_job_type,
    trigger_job,
)
from ccai.pychestrate.webservice.orchestration.rpa import service as rpa_service
from ccai.pychestrate.webservice.orchestration.rpa.candidates import capability_tags_for_client
from ccai.pychestrate.webservice.agents.models import ClientCapability
from ccai.pychestrate.webservice.audit import register_builtin_extensions as audit_register
from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension

from ccai.pychestrate.webservice.jobs.run.state import models as _run_state_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.dispatch import models as _dispatch_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.envelope import models as _envelope_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.results import models as _results_models  # noqa: F401
from ccai.pychestrate.webservice.ingest.progress import models as _progress_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.rpa import models as _rpa_models  # noqa: F401
from ccai.pychestrate.webservice.agents import models as _agents_models  # noqa: F401

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)

from ccai.pychestrate.core.defaults import new_uuid


PROJECT_REF = "7"
ACTOR_ID = "00000000-0000-4000-8000-000000050002"


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
                source="dev", file_path=None, env_var=None, key_id="test-rpa-p40c-ed25519",
            ),
        )
    finally:
        del os.environ["PYCHESTRATE_DEV_MODE"]
    rpa_service.set_active_job_dispatcher(dispatcher=JobDispatcher(transport=InMemoryTransport()))
    return


def _candidate() -> Tuple[DispatchCandidate, ...]:
    rtnval = (
        DispatchCandidate(
            client_id="11111111-1111-4000-8000-0000000050a1",
            pod_id="22222222-2222-4000-8000-0000000050a2",
            capability_tags=tuple(),
            inflight_dispatch_count=0,
            last_dispatched_at_iso="",
        ),
    )
    return rtnval


def _seed_type_and_spec(session: Any) -> Any:
    register_job_type(
        db_session=session,
        inputs=RpaJobTypeInputs(type_id="invoice-import", display_name="Invoice Import"),
        actor_id=ACTOR_ID,
    )
    publish_version(
        db_session=session, type_id="invoice-import",
        inputs=RpaVersionInputs(
            version="1.0.0", source_ref="https://example.com/rpa.git#v1.0.0",
            entrypoint={"command": ["python", "-m", "jobs.invoice"]},
        ),
    )
    spec = create_spec(
        db_session=session, project_id=PROJECT_REF,
        inputs=RpaSpecInputs(name="nightly", type_id="invoice-import", default_packet={"region": "eu"}),
    )
    return spec


def _trigger(session: Any, spec: Any, packet: Dict[str, Any]) -> Any:
    job = trigger_job(
        db_session=session, project_id=PROJECT_REF, spec_id=spec.spec_id, work_packet=packet,
        aspects=RpaTriggerAspects(actor_id=ACTOR_ID, candidates=_candidate(), project_slug="demo"),
    )
    return job


def _manifest(job: Any, *, outcome: str, extras: Dict[str, Any]) -> Dict[str, Any]:
    rtnval = {
        "run_id": job.job_id,
        "client_id": "11111111-1111-4000-8000-0000000050a1",
        "format_tag": result_completion.RPA_FORMAT_TAG,
        "backend_key_prefix": "runs/demo/{}".format(job.job_id),
        "backend_driver": "local-test",
        "completed_at": "2026-09-05T12:00:00+00:00",
        "terminal_outcome": outcome,
        "extras": extras,
    }
    return rtnval


# ---------------------------------------------------------------------------
# Result completion
# ---------------------------------------------------------------------------


def test_complete_rpa_run_maps_outcome_exit_code_and_result_key():
    """
    **Feature: 6-rpa-orchestration (M2)**
    **Property: an rpa.result.v1 manifest with terminal_outcome=success
    marks the job SUCCEEDED with the exit code and result prefix and
    emits job_completed; a second manifest is idempotent.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    spec = _seed_type_and_spec(session)
    job = _trigger(session, spec, {"customer_id": 1})
    completed: List[EntityEvent] = []
    subscribe(topic=RpaEventTopics.JOB_COMPLETED, subscriber=lambda e: completed.append(e))

    outcome = result_completion.complete_rpa_run(
        db_session=session, run_id=job.job_id,
        manifest=_manifest(job, outcome="success", extras={
            "exit_code": 0, "execution_mode": "process", "rpa_status": "succeeded", "file_count": 2,
            "files": [{"relative_path": "stdout.log", "size_bytes": 3, "sha256": "x"}],
        }),
    )
    testbase.assert_equal(outcome.job_kind, result_completion.RPA_FORMAT_TAG)
    testbase.assert_equal(outcome.domain_state, "succeeded")
    view = get_job(db_session=session, job_id=job.job_id)
    testbase.assert_equal(view.status, RpaJobStatus.SUCCEEDED)
    testbase.assert_equal(view.exit_code, 0)
    testbase.assert_equal(view.result_root_key, "runs/demo/{}".format(job.job_id))
    testbase.assert_equal(len(completed), 1)

    again = result_completion.complete_rpa_run(
        db_session=session, run_id=job.job_id,
        manifest=_manifest(job, outcome="failure", extras={"exit_code": 9}),
    )
    testbase.assert_equal(again.domain_state, "succeeded")
    testbase.assert_equal(len(completed), 1)
    return


def test_a_failed_rpa_job_records_the_pods_explanation_as_its_reason():
    """
    **Feature: 6-rpa-orchestration (M2)**
    **Property: the job's reason is the manifest's notes (the pod's own account, for example "RPA job exited with code 3: boom") when it gave
    some, and "rpa result manifest: outcome=failure" when it gave none; the notes are no longer tacked on after that text.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    spec = _seed_type_and_spec(session)
    noted = _trigger(session, spec, {"n": 1})
    silent = _trigger(session, spec, {"n": 2})
    noted_manifest = _manifest(noted, outcome="failure", extras={"rpa_status": "failed", "exit_code": 3})
    noted_manifest["notes"] = "RPA job exited with code 3: boom"
    result_completion.complete_rpa_run(db_session=session, run_id=noted.job_id, manifest=noted_manifest)
    result_completion.complete_rpa_run(db_session=session, run_id=silent.job_id, manifest=_manifest(silent, outcome="failure", extras={"rpa_status": "failed", "exit_code": 3}))

    testbase.assert_equal(
        (get_job(db_session=session, job_id=noted.job_id).final_state_reason, get_job(db_session=session, job_id=silent.job_id).final_state_reason),
        ("RPA job exited with code 3: boom", "rpa result manifest: outcome=failure"),
    )
    return


def test_a_job_the_pod_cancelled_is_a_cancelled_run_even_when_the_manifest_says_failure():
    """
    **Feature: 6-rpa-orchestration (M2)**
    **Property: a manifest whose ``rpa_status`` is cancelled makes the job CANCELLED and its run CANCELLED (an older pod named the outcome "failure", which left the run FAILED beside a
    cancelled job: on the dashboard's "needs attention" list and in a failed-run notification); a timeout and a plain failure still end their runs FAILED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    spec = _seed_type_and_spec(session)
    cancelled, timed_out, failed = _trigger(session, spec, {"n": 1}), _trigger(session, spec, {"n": 2}), _trigger(session, spec, {"n": 3})
    outcomes = {}
    for job, status, code in ((cancelled, "cancelled", -15), (timed_out, "timeout", None), (failed, "failed", 3)):
        outcomes[status] = result_completion.complete_rpa_run(
            db_session=session, run_id=job.job_id, manifest=_manifest(job, outcome="failure", extras={"rpa_status": status, "exit_code": code}),
        )

    testbase.assert_equal(
        {status: (outcome.domain_state, outcome.run_state) for status, outcome in outcomes.items()},
        {"cancelled": ("cancelled", "cancelled"), "timeout": ("timeout", "failed"), "failed": ("failed", "failed")},
    )
    return


def test_complete_rpa_run_maps_timeout_failure_and_cancel():
    """
    **Feature: 6-rpa-orchestration (M2)**
    **Property: extras.rpa_status=timeout yields TIMEOUT, a plain failure
    yields FAILED with its exit code, and terminal_outcome=cancelled
    yields CANCELLED; unknown runs raise RpaJobNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    spec = _seed_type_and_spec(session)

    timed_out = _trigger(session, spec, {"n": 1})
    result_completion.complete_rpa_run(
        db_session=session, run_id=timed_out.job_id,
        manifest=_manifest(timed_out, outcome="failure", extras={"rpa_status": "timeout", "exit_code": None}),
    )
    testbase.assert_equal(get_job(db_session=session, job_id=timed_out.job_id).status, RpaJobStatus.TIMEOUT)

    failed = _trigger(session, spec, {"n": 2})
    result_completion.complete_rpa_run(
        db_session=session, run_id=failed.job_id,
        manifest=_manifest(failed, outcome="failure", extras={"rpa_status": "failed", "exit_code": 3}),
    )
    failed_view = get_job(db_session=session, job_id=failed.job_id)
    testbase.assert_equal(failed_view.status, RpaJobStatus.FAILED)
    testbase.assert_equal(failed_view.exit_code, 3)

    cancelled = _trigger(session, spec, {"n": 3})
    result_completion.complete_rpa_run(
        db_session=session, run_id=cancelled.job_id,
        manifest=_manifest(cancelled, outcome="cancelled", extras={}),
    )
    testbase.assert_equal(get_job(db_session=session, job_id=cancelled.job_id).status, RpaJobStatus.CANCELLED)

    raised = False
    try:
        result_completion.complete_rpa_run(
            db_session=session, run_id=new_uuid(), manifest={"terminal_outcome": "success"},
        )
    except Exception:
        raised = True
    testbase.assert_true(raised)
    return


def test_rpa_frame_kind_is_supported_by_progress_ingest():
    """
    **Feature: 6-rpa-orchestration (M2)**
    **Property: the progress ingest vocabulary includes the rpa frame kind
    so clients can stream rpa.process.v1 line frames.**
    """
    testbase.assert_equal(FRAME_KIND_RPA, "rpa")
    testbase.assert_true(FRAME_KIND_RPA in SUPPORTED_FRAME_KINDS)
    from ccai.pychestrate.webservice.runs.restapi.v1 import runs_routes
    testbase.assert_true("rpa" in runs_routes.SUPPORTED_PROGRESS_FRAME_KINDS)
    return


# ---------------------------------------------------------------------------
# Pipeline step kind, watch action, audit kinds, capability tags
# ---------------------------------------------------------------------------


def test_rpa_step_kind_validates_and_produces_rpa_job():
    """
    **Feature: 6-rpa-orchestration (M2)**
    **Property: the rpa pipeline step requires spec_id, accepts an object
    work_packet, and produces one job_kind=rpa production.**
    """
    reset_registry_for_testing()
    pipelines_register()
    kinds = [impl.kind_name() for impl in list_factory_implementations(factory_protocol_name="pipeline_step_kind")]
    testbase.assert_true("rpa" in kinds)

    ok, issues = RpaStepKind.validate_inputs(inputs={})
    testbase.assert_equal(ok, False)
    ok, issues = RpaStepKind.validate_inputs(inputs={"spec_id": "abc", "work_packet": "nope"})
    testbase.assert_equal(ok, False)
    ok, issues = RpaStepKind.validate_inputs(inputs={"spec_id": "abc", "work_packet": {"a": 1}})
    testbase.assert_equal(ok, True)

    productions = RpaStepKind.produce_jobs(
        project_id="p", run_id="r", stage_id="s", step_id="st",
        inputs={"spec_id": "abc", "work_packet": {"a": 1}},
    )
    testbase.assert_equal(len(productions), 1)
    testbase.assert_equal(productions[0].job_kind, "rpa")
    testbase.assert_equal(productions[0].envelope_inputs["spec_id"], "abc")
    testbase.assert_equal(productions[0].envelope_inputs["work_packet"], {"a": 1})
    return


def test_watch_trigger_rpa_job_action_calls_bridge():
    """
    **Feature: 6-rpa-orchestration (M2)**
    **Property: WatchManager executes trigger_rpa_job through the injected
    bridge with the spec id and packet from the action parameters, and
    reports the missing bridge as an error.**
    """
    from ccai.pychestrate.core.managers.watch_manager import (
        WatchAction,
        WatchActionConfig,
        WatchManager,
    )

    calls: List[Dict[str, Any]] = []

    class _Job:
        job_id = "job-1"

    def _bridge(*, spec_id: str, work_packet: Dict[str, Any], user_id: str, project_id: Any = None) -> Any:
        calls.append({"spec_id": spec_id, "work_packet": work_packet, "user_id": user_id})
        return _Job()

    manager = WatchManager(None, rpa_trigger=_bridge)
    config = WatchActionConfig(
        action=WatchAction.TRIGGER_RPA_JOB, target_id=0,
        parameters={"spec_id": "spec-uuid", "work_packet": {"customer_id": 5}},
    )
    result = manager._execute_action(config, {"branch": "main"}, user_id="u-1")
    testbase.assert_equal(result["success"], True)
    testbase.assert_equal(result["result_id"], "job-1")
    testbase.assert_equal(calls[0]["spec_id"], "spec-uuid")
    testbase.assert_equal(calls[0]["work_packet"], {"customer_id": 5})
    testbase.assert_equal(calls[0]["user_id"], "u-1")

    bare = WatchManager(None)
    result = bare._execute_action(config, {}, user_id="u-1")
    testbase.assert_equal(result["success"], False)
    testbase.assert_true("RPA trigger" in str(result["error"]))
    return


def test_rpa_audit_kinds_are_registered():
    """
    **Feature: 6-rpa-orchestration (M2)**
    **Property: the audit event catalog maps every RPA bus topic to a
    canonical audit kind.**
    """
    reset_registry_for_testing()
    audit_register()
    kinds = {ext.source_topic: ext.kind for ext in list_resource_extensions(base_class=AuditEventTypeExtension)}
    for topic in (
        RpaEventTopics.JOB_STARTED, RpaEventTopics.JOB_COMPLETED, RpaEventTopics.JOB_FAILED,
        RpaEventTopics.JOB_CANCELLED, RpaEventTopics.JOB_TYPE_REGISTERED,
        RpaEventTopics.JOB_TYPE_VERSION_PUBLISHED, RpaEventTopics.JOB_TYPE_RETIRED,
    ):
        testbase.assert_true(topic in kinds, "missing audit kind for {}".format(topic))
        testbase.assert_true(kinds[topic].startswith("audit.rpa."))
    return


def test_capability_tags_flatten_client_capabilities():
    """
    **Feature: 6-rpa-orchestration (M2)**
    **Property: a client's advertised capability kinds become matcher
    tags, and the rpa kind contributes rpa:<job_type> and free-form tags.**
    """
    _engine, session = build_in_memory_session()
    client_id = "33333333-3333-4000-8000-0000000050c3"
    session.add(ClientCapability(
        capability_id=new_uuid(), client_id=client_id, kind="toolchain",
        value_json={"value": {"python": "3.12"}}, revision_token="r1",
    ))
    session.add(ClientCapability(
        capability_id=new_uuid(), client_id=client_id, kind="rpa",
        value_json={"value": {"job_types": ["invoice-import@1.0.0"], "taskplus": "1.0.2", "tags": ["browser"]}},
        revision_token="r2",
    ))
    session.commit()
    tags = capability_tags_for_client(db_session=session, client_id=client_id)
    for expected in ("toolchain", "rpa", "rpa:invoice-import@1.0.0", "browser"):
        testbase.assert_true(expected in tags, expected)
    testbase.assert_equal(capability_tags_for_client(db_session=session, client_id=new_uuid()), ())
    return


def test_watch_rpa_bridge_refuses_a_spec_from_another_project():
    """
    **Feature: 6-rpa-orchestration (PRJ-04 cross-project guard)**
    **Property: the RPA watch bridge refuses to start a job when the
    specification belongs to a different project than the watch, and
    never reaches trigger_job.**
    """
    from ccai.testbase.mocking import create_module_patch
    from ccai.pychestrate.webservice.webinterface.blueprints.projects import routes_rpa

    triggered: List[Any] = []

    class _Spec:
        project_id = "7"
        target_pod_id = None
        name = "nightly"

    class _Rpa:
        def get_spec(self, *, db_session: Any, spec_id: str) -> Any:
            return _Spec()

        def trigger_job(self, **kwargs: Any) -> Any:
            triggered.append(kwargs)
            return None

    patch = create_module_patch(routes_rpa, "_build_rpa_service")
    mock = patch.activate()
    mock.configure(side_effect=lambda: _Rpa())
    try:
        class _NoBridgeSession:
            def query(self, *args: Any, **kwargs: Any) -> "_NoBridgeSession":
                return self

            def filter(self, *args: Any, **kwargs: Any) -> "_NoBridgeSession":
                return self

            def first(self) -> Any:
                return None

        bridge = routes_rpa.build_watch_rpa_trigger(db_session=_NoBridgeSession())
        refused = False
        try:
            bridge(spec_id="spec-uuid", work_packet={}, user_id="u-1", project_id=8)
        except ValueError:
            refused = True
    finally:
        patch.deactivate()
    testbase.assert_equal((refused, triggered), (True, []))
    return
