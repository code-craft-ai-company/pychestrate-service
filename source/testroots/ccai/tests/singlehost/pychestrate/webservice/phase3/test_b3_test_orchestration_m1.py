"""
.. module:: test_b3_test_orchestration_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for B3 — test-catalog + test-orchestration + live-run-view M1.

.. moduleauthor:: Code Craft AI LLC

The integration test in this module is the **Phase-3 exit-criterion
demo** — admin upserts a catalog entry, triggers a run, observes
progress and result events end-to-end through the live hub.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import shutil
import tempfile

from datetime import datetime, timedelta, timezone
from typing import List

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.errors.exceptions import SemanticError

from ccai.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from ccai.pychestrate.webservice.ingest.progress import (
    register_builtin_extensions as progress_register,
)
from ccai.pychestrate.webservice.ingest.progress.factories.testbase_v1 import (
    TESTBASE_V1_FORMAT_TAG,
)
from ccai.pychestrate.webservice.ingest.progress.service import (
    ingest_summary,
)
from ccai.pychestrate.webservice.ingest.result import (
    register_builtin_extensions as result_register,
    scan_once,
)
from ccai.pychestrate.webservice.ingest.result.factories.testbase_v1 import (
    JSOS_RECORD_SEPARATOR,
    RESULTS_STREAM_FILENAME,
    SUMMARY_FILENAME,
)
from ccai.pychestrate.webservice.jobs.dispatch import (
    InMemoryTransport,
    JobDispatcher,
    register_builtin_extensions as dispatch_register,
)
from ccai.pychestrate.webservice.jobs.dispatch.factories.strategy import (
    DispatchCandidate,
)
from ccai.pychestrate.webservice.jobs.dispatch.receipt import (
    record as receipt_record,
)
from ccai.pychestrate.webservice.jobs.envelope import (
    EnvelopeSignerBootstrapConfig,
    install_envelope_signer,
)
from ccai.pychestrate.webservice.jobs.envelope import signer as envelope_signer
from ccai.pychestrate.webservice.jobs.results import SharedResultsBackend
from ccai.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
)
from ccai.pychestrate.webservice.orchestration.test import (
    CapabilityMismatchError,
    TestOrchestrator,
    TriggerRunRequest,
    register_builtin_extensions as orchestration_register,
)
from ccai.pychestrate.webservice.orchestration.test.catalog import (
    CatalogEntryNotFoundError,
    ImporterEntryPayload,
    list_entries,
    retire_entry,
    snapshot_for_dispatch,
    upsert_entry,
)
from ccai.pychestrate.webservice.orchestration.test.live import (
    LiveRunHub,
    ProgressEvent,
    ProgressSnapshot,
    format_sse_frame,
    merge_event,
)
from ccai.pychestrate.webservice.orchestration.test.models import (
    TestRunState,
)
from ccai.pychestrate.webservice.orchestration.test.repository import (
    get_run as get_test_run,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    session_for,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000000601"
PROJECT_SLUG = "phase3-demo"


def _prepare_runtime() -> None:
    """
        Reset every cross-test global, register every Phase-5 +
        Phase-6 in-tree factory, install the dev envelope signer.
    """
    reset_registry_for_testing()
    reset_event_bus()
    envelope_signer.reset_for_testing()
    dispatch_register()
    progress_register()
    result_register()
    orchestration_register()
    os.environ["PYCHESTRATE_DEV_MODE"] = "1"
    try:
        install_envelope_signer(
            config=EnvelopeSignerBootstrapConfig(
                source="dev", file_path=None, env_var=None,
                key_id="b3-test-ed25519",
            ),
        )
    finally:
        del os.environ["PYCHESTRATE_DEV_MODE"]
    return


def _testbase_payload(*, key: str, capability_tags=("linux",)) -> ImporterEntryPayload:
    """
        Build a uniform :class:`ImporterEntryPayload` for catalog
        upsert tests.
    """
    rtnval = ImporterEntryPayload(
        entry_key=key,
        display_name="Smoke {}".format(key),
        description="phase-3 demo entry",
        required_capability_tags=tuple(capability_tags),
        param_schema={"includes": {"type": "array"}},
        raw_metadata={
            "runner_kind": "testbase",
            "root": "source/testroots/ccai",
            "branch": "main",
            "build": "demo-1",
            "flavor": "debug",
            "release": "v0",
            "commit_sha": "f" * 40,
        },
    )
    return rtnval


def _two_eligible_candidates() -> tuple:
    """
        Two candidates with the ``linux`` capability the catalog
        entry requires.
    """
    rtnval = (
        DispatchCandidate(
            client_id="33333333-3333-4000-8000-000000000051",
            pod_id="44444444-4444-4000-8000-000000000051",
            capability_tags=("linux", "x86_64"),
            inflight_dispatch_count=0,
            last_dispatched_at_iso="",
        ),
        DispatchCandidate(
            client_id="33333333-3333-4000-8000-000000000052",
            pod_id="44444444-4444-4000-8000-000000000052",
            capability_tags=("linux", "arm64"),
            inflight_dispatch_count=2,
            last_dispatched_at_iso="2026-04-24T10:00:00Z",
        ),
    )
    return rtnval


def test_catalog_upsert_idempotent_on_natural_key():
    """
    **Feature: 6-test-catalog (M1)**
    **Property: upsert_entry against the same
    (project_id, importer_tag, entry_key) overwrites in place.
    Digest changes only when content changes.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()

    first = upsert_entry(
        db_session=session,
        project_id=PROJECT_UUID,
        importer_tag="testbase-project",
        payload=_testbase_payload(key="entry-a"),
    )
    second = upsert_entry(
        db_session=session,
        project_id=PROJECT_UUID,
        importer_tag="testbase-project",
        payload=_testbase_payload(key="entry-a"),
    )
    testbase.assert_equal(first.entry_id, second.entry_id)
    testbase.assert_equal(first.canonical_digest, second.canonical_digest)

    # Modify the description; digest must change.
    third_payload = ImporterEntryPayload(
        entry_key="entry-a",
        display_name="Smoke entry-a",
        description="changed description",
        required_capability_tags=("linux",),
        param_schema={"includes": {"type": "array"}},
        raw_metadata=_testbase_payload(key="entry-a").raw_metadata,
    )
    third = upsert_entry(
        db_session=session,
        project_id=PROJECT_UUID,
        importer_tag="testbase-project",
        payload=third_payload,
    )
    testbase.assert_equal(third.entry_id, first.entry_id)
    testbase.assert_equal(third.canonical_digest != first.canonical_digest, True)
    return


def test_catalog_retire_excludes_from_default_listing():
    """
    **Feature: 6-test-catalog (M1)**
    **Property: retire_entry flips the row, list_entries (default
    filters) excludes retired rows; include_retired=True returns
    them.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()

    upsert_entry(
        db_session=session,
        project_id=PROJECT_UUID,
        importer_tag="testbase-project",
        payload=_testbase_payload(key="alive"),
    )
    retired_view = upsert_entry(
        db_session=session,
        project_id=PROJECT_UUID,
        importer_tag="testbase-project",
        payload=_testbase_payload(key="dead"),
    )
    retire_entry(db_session=session, entry_id=retired_view.entry_id)

    visible = list_entries(db_session=session, project_id=PROJECT_UUID)
    keys = sorted(v.entry_key for v in visible)
    testbase.assert_equal(keys, ["alive"])

    full = list_entries(
        db_session=session,
        project_id=PROJECT_UUID,
        include_retired=True,
    )
    full_keys = sorted(v.entry_key for v in full)
    testbase.assert_equal(full_keys, ["alive", "dead"])

    # snapshot_for_dispatch on a retired entry raises.
    raised = False
    try:
        snapshot_for_dispatch(
            db_session=session, entry_id=retired_view.entry_id,
        )
    except CatalogEntryNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_orchestrator_trigger_dispatches_and_persists_test_run():
    """
    **Feature: 6-test-orchestration (M1)**
    **Property: trigger_run runs the full chain (catalog snapshot
    → runner → results allocate → run-state-machine → dispatch)
    and persists a TestRun row in DISPATCHED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    transport = InMemoryTransport()
    dispatcher = JobDispatcher(transport=transport)

    entry = upsert_entry(
        db_session=session,
        project_id=PROJECT_UUID,
        importer_tag="testbase-project",
        payload=_testbase_payload(key="phase3-exit-demo"),
    )
    backend = SharedResultsBackend(backend_driver="local-test")
    orchestrator = TestOrchestrator(
        dispatcher=dispatcher,
        results_backend=backend,
    )

    request = TriggerRunRequest(
        project_id=PROJECT_UUID,
        project_slug=PROJECT_SLUG,
        catalog_entry_id=entry.entry_id,
        triggered_by=None,
        inputs={"includes": ["ccai.tests.singlehost"]},
        candidates=_two_eligible_candidates(),
    )
    outcome = orchestrator.trigger_run(db_session=session, request=request)

    testbase.assert_equal(outcome.test_run_state, TestRunState.DISPATCHED)
    testbase.assert_equal(outcome.catalog_entry_id, entry.entry_id)
    testbase.assert_equal(outcome.catalog_digest, entry.canonical_digest)
    testbase.assert_equal(len(transport.calls()), 1)

    fresh = session_for(engine=_engine)
    persisted = get_test_run(db_session=fresh, run_id=outcome.run_id)
    testbase.assert_equal(persisted.state, TestRunState.DISPATCHED)
    testbase.assert_equal(str(persisted.dispatch_attempt_id), outcome.dispatch.attempt_id)
    return


def test_orchestrator_signs_the_configured_public_endpoint_into_the_envelope():
    """
    **Feature: 6-test-orchestration (M1), E2E-32**
    **Property: the envelope's issuer and forwarding URLs come from
    PYCHESTRATE_PUBLIC_BASE_URL -- no placeholder host -- and the
    summary URL is the results/complete route.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    transport = InMemoryTransport()
    orchestrator = TestOrchestrator(
        dispatcher=JobDispatcher(transport=transport),
        results_backend=SharedResultsBackend(backend_driver="local-test"),
    )
    entry = upsert_entry(
        db_session=session,
        project_id=PROJECT_UUID,
        importer_tag="testbase-project",
        payload=_testbase_payload(key="public-endpoint-demo"),
    )
    request = TriggerRunRequest(
        project_id=PROJECT_UUID,
        project_slug=PROJECT_SLUG,
        catalog_entry_id=entry.entry_id,
        triggered_by=None,
        inputs={"includes": ["ccai.tests.singlehost"]},
        candidates=_two_eligible_candidates(),
    )

    previous = os.environ.get("PYCHESTRATE_PUBLIC_BASE_URL")
    os.environ["PYCHESTRATE_PUBLIC_BASE_URL"] = "https://pyc.lab.internal/"
    try:
        outcome = orchestrator.trigger_run(db_session=session, request=request)
    finally:
        if previous is None:
            os.environ.pop("PYCHESTRATE_PUBLIC_BASE_URL", None)
        else:
            os.environ["PYCHESTRATE_PUBLIC_BASE_URL"] = previous

    envelope = transport.calls()[0].signed.envelope
    run_base = "https://pyc.lab.internal/api/v1/runs/{}".format(outcome.run_id)
    testbase.assert_equal(
        (envelope.issuer.split("/")[0], envelope.forwarding.progress_url, envelope.forwarding.summary_url),
        ("pyc.lab.internal", run_base + "/progress", run_base + "/results/complete"),
    )
    return


def test_orchestrator_capability_mismatch_rejects_before_dispatch():
    """
    **Feature: 6-test-orchestration (M1)**
    **Property: trigger_run with no candidates that satisfy the
    catalog entry's capability tags raises
    CapabilityMismatchError without persisting a TestRun row.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    dispatcher = JobDispatcher(transport=InMemoryTransport())

    entry = upsert_entry(
        db_session=session,
        project_id=PROJECT_UUID,
        importer_tag="testbase-project",
        payload=_testbase_payload(key="needs-darwin", capability_tags=("darwin",)),
    )
    orchestrator = TestOrchestrator(dispatcher=dispatcher)

    request = TriggerRunRequest(
        project_id=PROJECT_UUID,
        project_slug=PROJECT_SLUG,
        catalog_entry_id=entry.entry_id,
        triggered_by=None,
        inputs={"includes": ["t"]},
        candidates=_two_eligible_candidates(),  # only "linux"
    )
    raised = False
    try:
        orchestrator.trigger_run(db_session=session, request=request)
    except CapabilityMismatchError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_orchestrator_invalid_inputs_raises_semantic_error():
    """
    **Feature: 6-test-orchestration (M1)**
    **Property: a runner that rejects inputs (testbase requires
    'includes' as a list of strings) raises SemanticError before
    dispatch.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    dispatcher = JobDispatcher(transport=InMemoryTransport())

    entry = upsert_entry(
        db_session=session,
        project_id=PROJECT_UUID,
        importer_tag="testbase-project",
        payload=_testbase_payload(key="bad-inputs"),
    )
    orchestrator = TestOrchestrator(dispatcher=dispatcher)

    request = TriggerRunRequest(
        project_id=PROJECT_UUID,
        project_slug=PROJECT_SLUG,
        catalog_entry_id=entry.entry_id,
        triggered_by=None,
        inputs={"includes": "not-a-list"},  # invalid
        candidates=_two_eligible_candidates(),
    )
    raised = False
    try:
        orchestrator.trigger_run(db_session=session, request=request)
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_live_hub_publishes_events_and_subscribers_observe_them():
    """
    **Feature: 6-live-run-view (M1)**
    **Property: LiveRunHub.publish broadcasts to every active
    subscriber. snapshot_for returns the merged state. Unsubscribed
    callbacks no longer receive events.**
    """
    _prepare_runtime()
    hub = LiveRunHub()
    run_id = new_uuid()

    received_a: List[ProgressEvent] = []
    received_b: List[ProgressEvent] = []
    unsubscribe_a = hub.subscribe_callable(
        run_id=run_id, project_id=PROJECT_UUID,
        callback=lambda e: received_a.append(e),
    )
    hub.subscribe_callable(
        run_id=run_id, project_id=PROJECT_UUID,
        callback=lambda e: received_b.append(e),
    )

    hub.publish(
        run_id=run_id, project_id=PROJECT_UUID,
        kind="progress.summary",
        payload={
            "tests_total": 10,
            "tests_passed": 5,
            "tests_failed": 0,
            "tests_skipped": 0,
            "tests_errored": 0,
        },
    )

    testbase.assert_equal(len(received_a), 1)
    testbase.assert_equal(len(received_b), 1)

    unsubscribe_a()
    hub.publish(
        run_id=run_id, project_id=PROJECT_UUID,
        kind="progress.summary",
        payload={
            "tests_total": 10,
            "tests_passed": 8,
            "tests_failed": 1,
            "tests_skipped": 0,
            "tests_errored": 1,
        },
    )

    testbase.assert_equal(len(received_a), 1)  # unsubscribed
    testbase.assert_equal(len(received_b), 2)

    snapshot = hub.snapshot_for(run_id=run_id)
    testbase.assert_equal(snapshot.tests_passed, 8)
    testbase.assert_equal(snapshot.tests_failed, 1)
    testbase.assert_equal(snapshot.sequence, 2)
    return


def test_format_sse_frame_emits_id_event_data_lines():
    """
    **Feature: 6-live-run-view (M1)**
    **Property: format_sse_frame emits id: <seq>, event: <kind>,
    data: <json>, followed by a blank line.**
    """
    _prepare_runtime()
    event = ProgressEvent(
        run_id="11111111-1111-4000-8000-000000000099",
        project_id=PROJECT_UUID,
        kind="progress.summary",
        payload={"tests_passed": 1},
        recorded_at=datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc),
        sequence=42,
    )
    frame = format_sse_frame(event=event)
    text = frame.decode("utf-8")
    testbase.assert_equal(text.startswith("id: 42\n"), True)
    testbase.assert_equal("event: progress.summary\n" in text, True)
    testbase.assert_equal("data: " in text, True)
    testbase.assert_equal(text.endswith("\n\n"), True)
    return


def _write_minimal_testbase_tree(*, root: str) -> None:
    """
        Smaller helper than B2's; just enough to drive the
        Phase-3 exit-criterion integration test.
    """
    os.makedirs(os.path.join(root, "artifacts"), exist_ok=True)
    summary = {
        "detail": {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "errors": 0},
        "start": "2026-04-24T12:00:00Z",
        "stop": "2026-04-24T12:00:30Z",
    }
    with open(os.path.join(root, SUMMARY_FILENAME), "w", encoding="utf-8") as fh:
        json.dump(summary, fh)
    record = {
        "name": "tests.smoke#test_alpha",
        "instance": "33333333-3333-4000-8000-deadbeefdead",
        "rtype": "TEST",
        "result": "PASSED",
        "start": "2026-04-24T12:00:00Z",
        "stop": "2026-04-24T12:00:01Z",
    }
    sep = bytes([JSOS_RECORD_SEPARATOR])
    with open(os.path.join(root, RESULTS_STREAM_FILENAME), "wb") as fh:
        fh.write(json.dumps(record).encode("utf-8"))
        fh.write(sep)
    with open(os.path.join(root, "artifacts", "log.txt"), "w") as fh:
        fh.write("ok\n")
    return


def test_phase3_exit_criterion_end_to_end_demo():
    """
    **Feature: B3 — integration / Phase-3 exit-criterion demo**
    **Property: catalog upsert → orchestrator trigger → progress
    summary ingested → result tree scanned, all observed end-to-end
    against the same in-memory database.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    transport = InMemoryTransport()
    dispatcher = JobDispatcher(transport=transport)
    orchestrator = TestOrchestrator(
        dispatcher=dispatcher,
        results_backend=SharedResultsBackend(backend_driver="local-test"),
    )

    entry = upsert_entry(
        db_session=session,
        project_id=PROJECT_UUID,
        importer_tag="testbase-project",
        payload=_testbase_payload(key="exit-criterion"),
    )

    outcome = orchestrator.trigger_run(
        db_session=session,
        request=TriggerRunRequest(
            project_id=PROJECT_UUID,
            project_slug=PROJECT_SLUG,
            catalog_entry_id=entry.entry_id,
            triggered_by=None,
            inputs={"includes": ["t.smoke"]},
            candidates=_two_eligible_candidates(),
        ),
    )
    testbase.assert_equal(outcome.test_run_state, TestRunState.DISPATCHED)

    # Persist the receipt so progress ingest accepts the post.
    receipt_record(
        db_session=session,
        run_id=outcome.run_id,
        project_id=PROJECT_UUID,
        client_id=outcome.dispatch.client_id,
        attempt_id=outcome.dispatch.attempt_id,
        envelope_id=outcome.dispatch.envelope_id,
        client_local_run_id="local-exit",
    )

    # Forward a progress summary.
    summary = ingest_summary(
        db_session=session,
        run_id=outcome.run_id,
        authenticated_client_id=outcome.dispatch.client_id,
        format_tag=TESTBASE_V1_FORMAT_TAG,
        payload={
            "tests_total": 1, "tests_passed": 1,
            "tests_failed": 0, "tests_skipped": 0, "tests_errored": 0,
            "percent_complete": 100.0,
        },
    )
    testbase.assert_equal(summary.tests_passed, 1)

    # Land the result tree on disk + scan.
    tmpdir = tempfile.mkdtemp(prefix="b3-exit-")
    try:
        _write_minimal_testbase_tree(root=tmpdir)
        scan = scan_once(
            db_session=session,
            run_id=outcome.run_id,
            tree_path=tmpdir,
        )
        testbase.assert_equal(scan.had_summary, True)
        testbase.assert_equal(scan.tasks_persisted, 1)
        testbase.assert_equal(scan.artifacts_persisted >= 3, True)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return


def test_progress_snapshot_merge_is_pure():
    """
    **Feature: 6-live-run-view (M1)**
    **Property: merge_event returns a new snapshot without
    mutating the input. Counts come from progress.summary; state
    transitions update the state field.**
    """
    _prepare_runtime()
    base = ProgressSnapshot(
        run_id="r1",
        project_id=PROJECT_UUID,
        tests_total=None,
        tests_passed=0,
        tests_failed=0,
        tests_skipped=0,
        tests_errored=0,
        percent_complete=None,
        state="",
        latest_event_at=datetime.now(timezone.utc),
        sequence=0,
    )
    event = ProgressEvent(
        run_id="r1",
        project_id=PROJECT_UUID,
        kind="progress.summary",
        payload={
            "tests_total": 100,
            "tests_passed": 50,
            "tests_failed": 1,
            "tests_skipped": 0,
            "tests_errored": 0,
            "percent_complete": 51.0,
        },
        recorded_at=datetime.now(timezone.utc),
        sequence=7,
    )
    merged = merge_event(snapshot=base, event=event)
    testbase.assert_equal(merged.tests_total, 100)
    testbase.assert_equal(merged.tests_passed, 50)
    testbase.assert_equal(merged.percent_complete, 51.0)
    testbase.assert_equal(merged.sequence, 7)
    # Original is untouched (frozen dataclass — assertion is
    # belt-and-braces).
    testbase.assert_equal(base.tests_passed, 0)

    state_event = ProgressEvent(
        run_id="r1",
        project_id=PROJECT_UUID,
        kind="state_changed",
        payload={"to_state": "completed"},
        recorded_at=datetime.now(timezone.utc),
        sequence=8,
    )
    next_snap = merge_event(snapshot=merged, event=state_event)
    testbase.assert_equal(next_snap.state, "completed")
    testbase.assert_equal(next_snap.sequence, 8)
    return
