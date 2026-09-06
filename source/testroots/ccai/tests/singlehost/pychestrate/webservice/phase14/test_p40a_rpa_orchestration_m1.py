"""
.. module:: test_p40a_rpa_orchestration_m1
    :synopsis: Tests for 6-rpa-orchestration M1 -- job type registry,
               specifications, work-packet trigger + dispatch, terminal
               mirroring, and the packet helpers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import uuid

from typing import Any, Dict, List, Tuple

from ccai import testbase

from ccai.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from ccai.pychestrate.webservice.jobs.dispatch import (
    InMemoryTransport,
    JobDispatcher,
    register_builtin_extensions as dispatch_register,
)
from ccai.pychestrate.webservice.jobs.dispatch.factories.strategy import (
    DispatchCandidate,
)
from ccai.pychestrate.webservice.jobs.envelope import (
    JOB_KIND_RPA,
    EnvelopeSignerBootstrapConfig,
    install_envelope_signer,
)
from ccai.pychestrate.webservice.jobs.envelope import signer as envelope_signer
from ccai.pychestrate.webservice.jobs.envelope.repository import (
    list_envelopes_for_run,
)
from ccai.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from ccai.pychestrate.webservice.orchestration.rpa import (
    CapabilityMismatchError,
    DuplicateVersionError,
    PacketValidationError,
    RpaEventTopics,
    RpaJobStatus,
    RpaJobTypeInputs,
    RpaJobTypeInvalidError,
    RpaSpecInputs,
    RpaSpecInvalidError,
    RpaTriggerAspects,
    RpaVersionInputs,
    RpaVersionNotActiveError,
    RpaVersionState,
    REDACTION_MARKER,
    apply_run_terminal,
    cancel_job,
    canonical_project_uuid,
    create_spec,
    get_job,
    list_jobs,
    merge_packet,
    packet_digest,
    publish_version,
    redact_packet,
    register_builtin_extensions as rpa_register,
    register_job_type,
    resolve_version,
    set_version_state,
    trigger_job,
)
from ccai.pychestrate.webservice.orchestration.rpa import service as rpa_service

# Side-effect imports so the Layer-5 + RPA tables attach to the shared
# metadata before ``create_all`` runs in the in-memory fixture.
from ccai.pychestrate.webservice.jobs.run.state import models as _run_state_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.dispatch import models as _dispatch_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.envelope import models as _envelope_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.results import models as _results_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.rpa import models as _rpa_models  # noqa: F401

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


CONSUMER_PROJECT_REF = "7"
PROJECT_UUID = "00000000-0000-4000-8000-000000040001"
ACTOR_ID = "00000000-0000-4000-8000-000000040002"


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
                source="dev", file_path=None, env_var=None, key_id="test-rpa-p40a-ed25519",
            ),
        )
    finally:
        del os.environ["PYCHESTRATE_DEV_MODE"]
    rpa_service.set_active_job_dispatcher(
        dispatcher=JobDispatcher(transport=InMemoryTransport()),
    )
    return


def _one_candidate(tags: Tuple[str, ...] = ()) -> Tuple[DispatchCandidate, ...]:
    rtnval = (
        DispatchCandidate(
            client_id="11111111-1111-4000-8000-0000000040a1",
            pod_id="22222222-2222-4000-8000-0000000040a2",
            capability_tags=tags,
            inflight_dispatch_count=0,
            last_dispatched_at_iso="",
        ),
    )
    return rtnval


def _aspects(**overrides: Any) -> RpaTriggerAspects:
    kwargs: Dict[str, Any] = {
        "actor_id": ACTOR_ID,
        "candidates": _one_candidate(),
        "project_slug": "demo",
    }
    kwargs.update(overrides)
    rtnval = RpaTriggerAspects(**kwargs)
    return rtnval


def _register_process_type(session: Any, *, type_id: str = "invoice-import", schema: Any = None,
                           secret_fields: Tuple[str, ...] = ()) -> Any:
    view = register_job_type(
        db_session=session,
        inputs=RpaJobTypeInputs(
            type_id=type_id,
            display_name="Invoice Import",
            description="Imports invoices",
            execution_mode="process",
            packet_schema=schema,
            secret_fields=secret_fields,
        ),
        actor_id=ACTOR_ID,
    )
    return view


def _publish(session: Any, *, type_id: str = "invoice-import", version: str = "1.0.0") -> Any:
    view = publish_version(
        db_session=session,
        type_id=type_id,
        inputs=RpaVersionInputs(
            version=version,
            source_kind="git",
            source_ref="https://example.com/rpa-jobs.git#v{}".format(version),
            entrypoint={"command": ["python", "-m", "jobs.invoice_import"]},
            environment={"LOG_LEVEL": "info"},
            timeout_minutes=30,
        ),
        actor_id=ACTOR_ID,
    )
    return view


def _create_spec(session: Any, *, project_ref: str = CONSUMER_PROJECT_REF, name: str = "nightly",
                 type_id: str = "invoice-import", default_packet: Any = None,
                 selector: str = "latest-active") -> Any:
    view = create_spec(
        db_session=session,
        project_id=project_ref,
        inputs=RpaSpecInputs(
            name=name,
            type_id=type_id,
            version_selector=selector,
            default_packet=default_packet if default_packet is not None else {"region": "eu", "dry_run": True},
        ),
        actor_id=ACTOR_ID,
    )
    return view


# ---------------------------------------------------------------------------
# Job types + versions
# ---------------------------------------------------------------------------


def test_register_job_type_and_publish_versions():
    """
    **Feature: 6-rpa-orchestration (M1)**
    **Property: a job type registers with its execution mode, versions
    publish with driver-validated entrypoints, and latest-active
    resolves to the highest semver version.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    view = _register_process_type(session)
    testbase.assert_equal(view.type_id, "invoice-import")
    testbase.assert_equal(view.execution_mode.value, "process")
    testbase.assert_equal(view.active_version_count, 0)

    _publish(session, version="1.0.0")
    _publish(session, version="1.10.0")
    _publish(session, version="1.2.0")

    resolved = resolve_version(db_session=session, type_id="invoice-import", selector="latest-active")
    testbase.assert_equal(resolved.version, "1.10.0")

    set_version_state(
        db_session=session, type_id="invoice-import", version="1.10.0", state=RpaVersionState.DEPRECATED,
    )
    resolved = resolve_version(db_session=session, type_id="invoice-import", selector="latest-active")
    testbase.assert_equal(resolved.version, "1.2.0")

    pinned = resolve_version(db_session=session, type_id="invoice-import", selector="1.0.0")
    testbase.assert_equal(pinned.version, "1.0.0")
    return


def test_register_job_type_rejects_bad_slug_and_bad_entrypoint():
    """
    **Feature: 6-rpa-orchestration (M1)**
    **Property: type ids must be lowercase slugs; a process entrypoint
    without argv and a tasker entrypoint without workflow/tasking are
    rejected by their drivers; duplicate versions raise.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        register_job_type(
            db_session=session,
            inputs=RpaJobTypeInputs(type_id="Bad Slug!", display_name="x"),
        )
    except RpaJobTypeInvalidError:
        raised = True
    testbase.assert_true(raised)

    _register_process_type(session)
    raised = False
    try:
        publish_version(
            db_session=session, type_id="invoice-import",
            inputs=RpaVersionInputs(version="1.0.0", source_ref="https://x/y.git", entrypoint={}),
        )
    except RpaJobTypeInvalidError:
        raised = True
    testbase.assert_true(raised)

    register_job_type(
        db_session=session,
        inputs=RpaJobTypeInputs(type_id="flow-job", display_name="Flow", execution_mode="tasker"),
    )
    raised = False
    try:
        publish_version(
            db_session=session, type_id="flow-job",
            inputs=RpaVersionInputs(version="1.0.0", source_ref="https://x/y.git", entrypoint={"command": ["x"]}),
        )
    except RpaJobTypeInvalidError:
        raised = True
    testbase.assert_true(raised)

    ok = publish_version(
        db_session=session, type_id="flow-job",
        inputs=RpaVersionInputs(
            version="1.0.0", source_ref="https://x/y.git",
            entrypoint={"tasking": "jobs.flows@InvoiceFlow"},
        ),
    )
    testbase.assert_equal(ok.version, "1.0.0")

    _publish(session, version="1.0.0")
    raised = False
    try:
        _publish(session, version="1.0.0")
    except DuplicateVersionError:
        raised = True
    testbase.assert_true(raised)
    return


def test_create_spec_requires_active_version():
    """
    **Feature: 6-rpa-orchestration (M1)**
    **Property: a specification cannot bind a job type with no active
    version; once one is published the spec resolves it.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _register_process_type(session)

    raised = False
    try:
        _create_spec(session)
    except RpaVersionNotActiveError:
        raised = True
    testbase.assert_true(raised)

    _publish(session, version="2.0.0")
    spec = _create_spec(session)
    testbase.assert_equal(spec.project_id, CONSUMER_PROJECT_REF)
    testbase.assert_equal(spec.resolved_version, "2.0.0")
    testbase.assert_equal(spec.revision, 1)
    testbase.assert_equal(spec.execution_mode.value, "process")
    return


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------


def test_trigger_job_dispatches_rpa_envelope_with_merged_packet():
    """
    **Feature: 6-rpa-orchestration (M1)**
    **Property: trigger_job merges the packet over the spec defaults,
    persists a RUNNING job whose stored packet is redacted, mints a
    job_kind=rpa envelope carrying the full packet, and emits
    job_started + job_dispatched.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _register_process_type(session, secret_fields=("auth.token",))
    _publish(session, version="1.0.0")
    spec = _create_spec(session, default_packet={"region": "eu", "dry_run": True})

    received: List[EntityEvent] = []
    subscribe(topic=RpaEventTopics.JOB_STARTED, subscriber=lambda e: received.append(e))
    subscribe(topic=RpaEventTopics.JOB_DISPATCHED, subscriber=lambda e: received.append(e))

    job = trigger_job(
        db_session=session,
        project_id=CONSUMER_PROJECT_REF,
        spec_id=spec.spec_id,
        work_packet={"dry_run": False, "customer_id": 42, "auth": {"token": "s3cret"}},
        aspects=_aspects(),
    )
    testbase.assert_equal(job.status, RpaJobStatus.RUNNING)
    testbase.assert_equal(job.type_id, "invoice-import")
    testbase.assert_equal(job.resolved_version, "1.0.0")
    testbase.assert_equal(job.triggered_by_id, ACTOR_ID)
    testbase.assert_equal(job.work_packet["region"], "eu")
    testbase.assert_equal(job.work_packet["dry_run"], False)
    testbase.assert_equal(job.work_packet["customer_id"], 42)
    testbase.assert_equal(job.work_packet["auth"]["token"], REDACTION_MARKER)
    testbase.assert_true(job.envelope_id is not None)
    testbase.assert_true(job.dispatch_attempt_id is not None)
    testbase.assert_equal(len(received), 2)

    envelopes = list_envelopes_for_run(db_session=session, run_id=job.job_id)
    testbase.assert_equal(len(envelopes), 1)
    payload = json.loads(envelopes[0].canonical_payload_text)
    testbase.assert_equal(payload["job_kind"], JOB_KIND_RPA)
    testbase.assert_equal(payload["job_type"], "rpa-invoice-import")
    testbase.assert_equal(payload["params"]["execution_mode"], "process")
    testbase.assert_equal(payload["params"]["work_packet"]["auth"]["token"], "s3cret")
    testbase.assert_equal(payload["params"]["entrypoint"]["command"][0], "python")
    testbase.assert_equal(payload["project_id"], canonical_project_uuid(CONSUMER_PROJECT_REF))
    testbase.assert_equal(payload["source"]["ref"], "v1.0.0")
    return


def test_trigger_job_rejects_packet_failing_schema():
    """
    **Feature: 6-rpa-orchestration (M1)**
    **Property: a packet violating the job type's JSON schema raises
    PacketValidationError listing every failing path and persists no
    job.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    schema = {
        "type": "object",
        "required": ["customer_id"],
        "properties": {
            "customer_id": {"type": "integer"},
            "region": {"type": "string", "enum": ["eu", "us"]},
        },
    }
    _register_process_type(session, schema=schema)
    _publish(session, version="1.0.0")
    spec = _create_spec(session, default_packet={"region": "eu"})

    raised = None
    try:
        trigger_job(
            db_session=session, project_id=CONSUMER_PROJECT_REF, spec_id=spec.spec_id,
            work_packet={"region": "mars"}, aspects=_aspects(),
        )
    except PacketValidationError as xcpt:
        raised = xcpt
    testbase.assert_true(raised is not None)
    paths = sorted(p for p, _m in raised.issues)
    testbase.assert_true("/region" in paths)
    testbase.assert_true("/" in paths)

    listing = list_jobs(db_session=session, project_id=CONSUMER_PROJECT_REF)
    testbase.assert_equal(listing.total, 0)
    return


def test_trigger_job_is_idempotent_within_window():
    """
    **Feature: 6-rpa-orchestration (M1)**
    **Property: two triggers with the same packet and cause inside the
    idempotency window return the same job.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _register_process_type(session)
    _publish(session, version="1.0.0")
    spec = _create_spec(session)

    first = trigger_job(
        db_session=session, project_id=CONSUMER_PROJECT_REF, spec_id=spec.spec_id,
        work_packet={"customer_id": 1}, aspects=_aspects(),
    )
    second = trigger_job(
        db_session=session, project_id=CONSUMER_PROJECT_REF, spec_id=spec.spec_id,
        work_packet={"customer_id": 1}, aspects=_aspects(),
    )
    testbase.assert_equal(first.job_id, second.job_id)

    third = trigger_job(
        db_session=session, project_id=CONSUMER_PROJECT_REF, spec_id=spec.spec_id,
        work_packet={"customer_id": 2}, aspects=_aspects(),
    )
    testbase.assert_true(third.job_id != first.job_id)
    listing = list_jobs(db_session=session, project_id=CONSUMER_PROJECT_REF)
    testbase.assert_equal(listing.total, 2)
    return


def test_trigger_job_capability_mismatch_raises():
    """
    **Feature: 6-rpa-orchestration (M1)**
    **Property: when the job type requires a capability no candidate
    advertises, CapabilityMismatchError names both sides and nothing is
    dispatched.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    register_job_type(
        db_session=session,
        inputs=RpaJobTypeInputs(
            type_id="browser-bot", display_name="Browser bot", capability_requirements=("browser",),
        ),
    )
    _publish(session, type_id="browser-bot", version="1.0.0")
    spec = _create_spec(session, type_id="browser-bot", name="bot")

    raised = False
    try:
        trigger_job(
            db_session=session, project_id=CONSUMER_PROJECT_REF, spec_id=spec.spec_id,
            work_packet={}, aspects=_aspects(candidates=_one_candidate(tags=("gpu",))),
        )
    except CapabilityMismatchError as xcpt:
        raised = True
        testbase.assert_true("browser" in str(xcpt))
    testbase.assert_true(raised)

    job = trigger_job(
        db_session=session, project_id=CONSUMER_PROJECT_REF, spec_id=spec.spec_id,
        work_packet={}, aspects=_aspects(candidates=_one_candidate(tags=("browser", "gpu"))),
    )
    testbase.assert_equal(job.status, RpaJobStatus.RUNNING)
    return


def test_apply_run_terminal_and_cancel():
    """
    **Feature: 6-rpa-orchestration (M1)**
    **Property: apply_run_terminal records exit code + result key and
    emits job_completed once (idempotent); cancel flips an active job
    to CANCELLED and refuses on a terminal one.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _register_process_type(session)
    _publish(session, version="1.0.0")
    spec = _create_spec(session)

    completed: List[EntityEvent] = []
    subscribe(topic=RpaEventTopics.JOB_COMPLETED, subscriber=lambda e: completed.append(e))

    job = trigger_job(
        db_session=session, project_id=CONSUMER_PROJECT_REF, spec_id=spec.spec_id,
        work_packet={"customer_id": 1}, aspects=_aspects(),
    )
    done = apply_run_terminal(
        db_session=session, job_id=job.job_id, final_status=RpaJobStatus.SUCCEEDED,
        exit_code=0, result_root_key="runs/demo/x",
    )
    testbase.assert_equal(done.status, RpaJobStatus.SUCCEEDED)
    testbase.assert_equal(done.exit_code, 0)
    testbase.assert_equal(done.result_root_key, "runs/demo/x")
    testbase.assert_true(done.duration_seconds is not None)
    again = apply_run_terminal(
        db_session=session, job_id=job.job_id, final_status=RpaJobStatus.FAILED, exit_code=3,
    )
    testbase.assert_equal(again.status, RpaJobStatus.SUCCEEDED)
    testbase.assert_equal(len(completed), 1)

    raised = False
    try:
        cancel_job(db_session=session, job_id=job.job_id, actor_id=ACTOR_ID)
    except Exception:
        raised = True
    testbase.assert_true(raised)

    other = trigger_job(
        db_session=session, project_id=CONSUMER_PROJECT_REF, spec_id=spec.spec_id,
        work_packet={"customer_id": 2}, aspects=_aspects(),
    )
    cancelled = cancel_job(db_session=session, job_id=other.job_id, actor_id=ACTOR_ID)
    testbase.assert_equal(cancelled.status, RpaJobStatus.CANCELLED)
    return


def test_list_jobs_filters_and_counts():
    """
    **Feature: 6-rpa-orchestration (M1)**
    **Property: list_jobs scopes by project, spec, and status and
    reports the total before pagination.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _register_process_type(session)
    _publish(session, version="1.0.0")
    spec_a = _create_spec(session, name="a")
    spec_b = _create_spec(session, name="b", project_ref=PROJECT_UUID)

    for index in range(3):
        trigger_job(
            db_session=session, project_id=CONSUMER_PROJECT_REF, spec_id=spec_a.spec_id,
            work_packet={"n": index}, aspects=_aspects(),
        )
    other = trigger_job(
        db_session=session, project_id=PROJECT_UUID, spec_id=spec_b.spec_id,
        work_packet={"n": 9}, aspects=_aspects(),
    )
    apply_run_terminal(
        db_session=session, job_id=other.job_id, final_status=RpaJobStatus.FAILED, exit_code=1,
    )

    consumer = list_jobs(db_session=session, project_id=CONSUMER_PROJECT_REF, limit=2)
    testbase.assert_equal(consumer.total, 3)
    testbase.assert_equal(len(consumer.jobs), 2)

    failed = list_jobs(db_session=session, project_id=PROJECT_UUID, status=RpaJobStatus.FAILED)
    testbase.assert_equal(failed.total, 1)
    testbase.assert_equal(failed.jobs[0].job_id, other.job_id)

    by_spec = list_jobs(db_session=session, project_id=CONSUMER_PROJECT_REF, spec_id=spec_a.spec_id)
    testbase.assert_equal(by_spec.total, 3)
    return


# ---------------------------------------------------------------------------
# Packet helpers (property-style)
# ---------------------------------------------------------------------------


def test_merge_packet_is_deterministic_and_packet_wins():
    """
    **Feature: 6-rpa-orchestration (M1)**
    **Property 1: merged keys are the union, shared keys take the work
    packet's value, and the digest is stable across key order.**
    """
    default = {"a": 1, "b": {"x": 1}, "c": [1, 2]}
    packet = {"b": {"y": 2}, "d": "z"}
    merged = merge_packet(default_packet=default, work_packet=packet)
    testbase.assert_equal(sorted(merged.keys()), ["a", "b", "c", "d"])
    testbase.assert_equal(merged["b"], {"y": 2})
    reordered = merge_packet(default_packet=dict(reversed(list(default.items()))), work_packet=packet)
    testbase.assert_equal(packet_digest(merged), packet_digest(reordered))
    testbase.assert_equal(len(packet_digest(merged)), 64)
    return


def test_redact_packet_never_leaks_secret_values():
    """
    **Feature: 6-rpa-orchestration (M1)**
    **Property 2: every secret path carries the marker and the
    serialised copy contains none of the secret values; the input is
    untouched.**
    """
    packet = {
        "auth": {"token": "tok-123", "user": "bob"},
        "accounts": [{"password": "pw-1"}, {"password": "pw-2"}],
        "api_key": "key-9",
    }
    redacted = redact_packet(
        packet=packet, secret_fields=("auth.token", "/accounts/*/password", "api_key", "missing.path"),
    )
    text = json.dumps(redacted)
    for secret in ("tok-123", "pw-1", "pw-2", "key-9"):
        testbase.assert_true(secret not in text)
    testbase.assert_equal(redacted["auth"]["token"], REDACTION_MARKER)
    testbase.assert_equal(redacted["auth"]["user"], "bob")
    testbase.assert_equal(redacted["accounts"][1]["password"], REDACTION_MARKER)
    testbase.assert_equal(packet["auth"]["token"], "tok-123")
    return


def test_canonical_project_uuid_bridges_consumer_ids():
    """
    **Feature: 6-rpa-orchestration (M1)**
    **Property: UUID references pass through unchanged; other references
    map to a stable UUID that differs per project.**
    """
    testbase.assert_equal(canonical_project_uuid(PROJECT_UUID), PROJECT_UUID)
    seven = canonical_project_uuid("7")
    testbase.assert_equal(seven, canonical_project_uuid(" 7 "))
    testbase.assert_true(seven != canonical_project_uuid("8"))
    uuid.UUID(seven)
    return
