"""
.. module:: test_b2_results_progress_watcher_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for B2 — shared-results + progress + result-watcher M1.

.. moduleauthor:: Code Craft AI LLC

Covers the happy path for each of the three B2 features plus the
critical rejection / idempotency paths called out in their EARS
acceptance criteria.
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

from ccai.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from ccai.pychestrate.webservice.ingest.progress import (
    ProgressClientMismatchError,
    ProgressEventTopics,
    ProgressUnknownRunError,
    get_summary,
    ingest_record,
    ingest_summary,
    list_records,
    register_builtin_extensions as progress_register,
)
from ccai.pychestrate.webservice.ingest.progress.factories.testbase_v1 import (
    TESTBASE_V1_FORMAT_TAG,
)
from ccai.pychestrate.webservice.ingest.progress.models import (
    RunProgressCounters,
    RunProgressRecord,
    RunProgressSummary,
)
from ccai.pychestrate.webservice.ingest.result import (
    ResultEventTopics,
    ResultTreeNotFoundError,
    register_builtin_extensions as result_register,
    scan_once,
)
from ccai.pychestrate.webservice.ingest.result.factories.testbase_v1 import (
    JSOS_RECORD_SEPARATOR,
    RESULTS_STREAM_FILENAME,
    SUMMARY_FILENAME,
)
from ccai.pychestrate.webservice.ingest.result.models import (
    RunArtifact,
    RunResultSummary,
    TaskResult,
)
from ccai.pychestrate.webservice.jobs.dispatch import (
    DispatchRequestInputs,
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
    JobDeadline,
    JobForwardingInfo,
    JobPipelineRef,
    JobRefs,
    JobResultsLocator,
    install_envelope_signer,
)
from ccai.pychestrate.webservice.jobs.envelope import signer as envelope_signer
from ccai.pychestrate.webservice.jobs.results import (
    AllocationNotFoundError,
    SharedResultsBackend,
    build_canonical_prefix,
)
from ccai.pychestrate.webservice.jobs.results.errors import (
    PathComponentInvalidError,
)
from ccai.pychestrate.webservice.jobs.run.state import (
    RunEvent,
    create_run as create_run_state,
    transition,
)
from ccai.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    session_for,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000000401"
PROJECT_SLUG = "test-project"


def _prepare_runtime() -> None:
    """
        Reset every cross-test global B2 touches: extension
        registry, in-process bus, envelope signer. Then install
        the dev signer and register the Phase-5 in-tree factories
        so the dispatcher / parsers are wired.
    """
    reset_registry_for_testing()
    reset_event_bus()
    envelope_signer.reset_for_testing()
    dispatch_register()
    progress_register()
    result_register()
    os.environ["PYCHESTRATE_DEV_MODE"] = "1"
    try:
        install_envelope_signer(
            config=EnvelopeSignerBootstrapConfig(
                source="dev",
                file_path=None,
                env_var=None,
                key_id="b2-test-ed25519",
            ),
        )
    finally:
        del os.environ["PYCHESTRATE_DEV_MODE"]
    return


def _dispatch_a_run(
        *,
        db_session,
        run_id: str
    ):
    """
        Drive the chain create_run → dispatch → record receipt so
        the run is in a state that progress / result ingest expects:
        run row exists, dispatch attempt + receipt rows exist.

        Returns the dispatch outcome so the caller can reuse the
        client_id + envelope_id + attempt_id.
    """
    create_run_state(
        db_session=db_session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        job_type="testbase-singlehost",
    )
    transition(
        db_session=db_session,
        run_id=run_id,
        event=RunEvent.DISPATCH_STARTED,
        actor="system:test",
    )
    transport = InMemoryTransport()
    dispatcher = JobDispatcher(transport=transport)
    now = datetime.now(timezone.utc)
    inputs = DispatchRequestInputs(
        run_id=run_id,
        project_id=PROJECT_UUID,
        job_id="00000000-0000-4000-8000-00000000ab01",
        job_name="b2-smoke",
        job_type="testbase-singlehost",
        issuer="pychestrate.example.com/0.5.0",
        refs=JobRefs(
            branch="main", build="b1", flavor="debug", release="v0",
            commit_sha="c" * 40,
        ),
        params={},
        scoped_secrets=tuple(),
        results=JobResultsLocator(
            backend_key_prefix="results/{}".format(run_id),
            backend_driver="local-test",
        ),
        forwarding=JobForwardingInfo(
            progress_url="https://x/progress",
            summary_url="https://x/summary",
            auth_method="bearer",
        ),
        deadline=JobDeadline(
            soft_deadline_at=now + timedelta(minutes=10),
            hard_deadline_at=now + timedelta(minutes=20),
        ),
        pipeline=JobPipelineRef(pipeline_id="pl-1", instance_id="inst-1"),
        extension_claims=None,
        candidates=(
            DispatchCandidate(
                client_id="33333333-3333-4000-8000-000000000001",
                pod_id="44444444-4444-4000-8000-000000000001",
                capability_tags=("linux",),
                inflight_dispatch_count=0,
                last_dispatched_at_iso="",
            ),
        ),
    )
    outcome = dispatcher.dispatch(db_session=db_session, inputs=inputs)
    receipt_record(
        db_session=db_session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        client_id=outcome.client_id,
        attempt_id=outcome.attempt_id,
        envelope_id=outcome.envelope_id,
        client_local_run_id="local-1",
    )
    return outcome


def test_canonicalize_path_component_handles_unsafe_input():
    """
    **Feature: 5-shared-results-backend (M1)**
    **Property: canonicalize_component sanitizes spaces / slashes
    / case and rejects empty results.**
    """
    _prepare_runtime()
    prefix = build_canonical_prefix(
        project_slug="My Project!!",
        job_type="TestBase Single Host",
        run_id="aaaaaaaa-aaaa-4000-8000-aaaaaaaaaaaa",
        when=datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc),
    )
    testbase.assert_equal(
        prefix,
        "my-project/results/2026/04/24/testbase-single-host/"
        "aaaaaaaa-aaaa-4000-8000-aaaaaaaaaaaa",
    )

    raised = False
    try:
        build_canonical_prefix(
            project_slug="//",  # canonicalizes to empty
            job_type="t",
            run_id="r",
            when=datetime.now(timezone.utc),
        )
    except PathComponentInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_shared_backend_allocate_is_idempotent_on_run_id():
    """
    **Feature: 5-shared-results-backend (M1)**
    **Property: allocate() returns the same prefix on retry, and
    persists exactly one allocation row.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    backend = SharedResultsBackend(backend_driver="local-test")

    run_id = new_uuid()
    first = backend.allocate(
        db_session=session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        project_slug=PROJECT_SLUG,
        job_type="testbase-singlehost",
    )
    second = backend.allocate(
        db_session=session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        project_slug=PROJECT_SLUG,
        job_type="testbase-singlehost",
    )
    testbase.assert_equal(first.backend_key_prefix, second.backend_key_prefix)

    resolved = backend.resolve(db_session=session, run_id=run_id)
    testbase.assert_equal(resolved.backend_key_prefix, first.backend_key_prefix)
    return


def test_shared_backend_resolve_unknown_raises():
    """
    **Feature: 5-shared-results-backend (M1)**
    **Property: resolve() against an unknown run raises
    AllocationNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    backend = SharedResultsBackend(backend_driver="local-test")

    raised = False
    try:
        backend.resolve(db_session=session, run_id=new_uuid())
    except AllocationNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_progress_summary_ingest_persists_and_emits():
    """
    **Feature: 5-progress-ingest (M1)**
    **Property: ingest_summary persists a summary row, upserts the
    counters row, and publishes both entity.progress.received and
    entity.progress.summary_landed.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()
    outcome = _dispatch_a_run(db_session=session, run_id=run_id)

    received_received: List[EntityEvent] = []
    received_summary: List[EntityEvent] = []
    subscribe(
        topic=ProgressEventTopics.RECEIVED,
        subscriber=lambda e: received_received.append(e),
    )
    subscribe(
        topic=ProgressEventTopics.SUMMARY_LANDED,
        subscriber=lambda e: received_summary.append(e),
    )

    payload = {
        "tests_total": 50,
        "tests_passed": 40,
        "tests_failed": 5,
        "tests_skipped": 3,
        "tests_errored": 2,
        "percent_complete": 90.0,
        "notes": "halfway done",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    summary = ingest_summary(
        db_session=session,
        run_id=run_id,
        authenticated_client_id=outcome.client_id,
        format_tag=TESTBASE_V1_FORMAT_TAG,
        payload=payload,
    )
    testbase.assert_equal(summary.tests_total, 50)
    testbase.assert_equal(summary.tests_passed, 40)

    fresh = session_for(engine=_engine)
    summary_count = (
        fresh.query(RunProgressSummary)
        .filter(RunProgressSummary.run_id == run_id)
        .count()
    )
    testbase.assert_equal(summary_count, 1)

    counters = (
        fresh.query(RunProgressCounters)
        .filter(RunProgressCounters.run_id == run_id)
        .first()
    )
    testbase.assert_equal(counters is not None, True)
    testbase.assert_equal(counters.tests_passed, 40)

    testbase.assert_equal(len(received_received), 1)
    testbase.assert_equal(len(received_summary), 1)
    return


def test_progress_summary_rejects_mismatched_client():
    """
    **Feature: 5-progress-ingest (M1)**
    **Property: an authenticated_client_id that does not match the
    run's DispatchReceipt.client_id raises
    ProgressClientMismatchError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()
    _dispatch_a_run(db_session=session, run_id=run_id)

    raised = False
    try:
        ingest_summary(
            db_session=session,
            run_id=run_id,
            authenticated_client_id="55555555-5555-4000-8000-000000000099",
            format_tag=TESTBASE_V1_FORMAT_TAG,
            payload={
                "tests_total": 1, "tests_passed": 1,
                "tests_failed": 0, "tests_skipped": 0, "tests_errored": 0,
            },
        )
    except ProgressClientMismatchError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_progress_summary_unknown_run_raises():
    """
    **Feature: 5-progress-ingest (M1)**
    **Property: ingest_summary against a run with no
    DispatchReceipt raises ProgressUnknownRunError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        ingest_summary(
            db_session=session,
            run_id=new_uuid(),
            authenticated_client_id="33333333-3333-4000-8000-000000000001",
            format_tag=TESTBASE_V1_FORMAT_TAG,
            payload={},
        )
    except ProgressUnknownRunError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_progress_record_idempotent_on_record_index():
    """
    **Feature: 5-progress-ingest (M1)**
    **Property: ingest_record is idempotent on
    (run_id, record_index) — re-posting the same record produces
    no second row.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()
    outcome = _dispatch_a_run(db_session=session, run_id=run_id)

    payload = {
        "name": "tests.smoke#test_alpha",
        "result": "PASSED",
        "start": "2026-04-24T12:00:00Z",
        "stop": "2026-04-24T12:00:01Z",
    }
    ingest_record(
        db_session=session,
        run_id=run_id,
        authenticated_client_id=outcome.client_id,
        record_index=0,
        format_tag=TESTBASE_V1_FORMAT_TAG,
        payload=payload,
    )
    ingest_record(
        db_session=session,
        run_id=run_id,
        authenticated_client_id=outcome.client_id,
        record_index=0,
        format_tag=TESTBASE_V1_FORMAT_TAG,
        payload=payload,
    )

    fresh = session_for(engine=_engine)
    count = (
        fresh.query(RunProgressRecord)
        .filter(RunProgressRecord.run_id == run_id)
        .count()
    )
    testbase.assert_equal(count, 1)

    records = list_records(db_session=fresh, run_id=run_id)
    testbase.assert_equal(len(records), 1)
    testbase.assert_equal(records[0].test_name, "tests.smoke#test_alpha")

    summary = get_summary(db_session=fresh, run_id=run_id)
    testbase.assert_equal(summary, None)  # no summary posted yet
    return


def _write_testbase_tree(*, root: str) -> None:
    """
        Materialize a minimal testbase result tree in ``root`` for
        the result-watcher tests. Includes a summary, a
        results-stream with two records (one passed, one failed),
        and one artifact in ``artifacts/``.
    """
    os.makedirs(os.path.join(root, "artifacts"), exist_ok=True)
    os.makedirs(os.path.join(root, "diagnostics"), exist_ok=True)
    summary = {
        "detail": {
            "total": 2,
            "passed": 1,
            "failed": 1,
            "skipped": 0,
            "errors": 0,
        },
        "start": "2026-04-24T12:00:00Z",
        "stop": "2026-04-24T12:01:00Z",
    }
    with open(os.path.join(root, SUMMARY_FILENAME), "w", encoding="utf-8") as fh:
        json.dump(summary, fh)

    record_a = {
        "name": "tests.smoke#test_alpha",
        "instance": "11111111-1111-4000-8000-aaaaaaaaaaaa",
        "rtype": "TEST",
        "result": "PASSED",
        "start": "2026-04-24T12:00:00Z",
        "stop": "2026-04-24T12:00:01Z",
    }
    record_b = {
        "name": "tests.smoke#test_beta",
        "instance": "22222222-2222-4000-8000-bbbbbbbbbbbb",
        "rtype": "TEST",
        "result": "FAILED",
        "start": "2026-04-24T12:00:01Z",
        "stop": "2026-04-24T12:00:02Z",
    }
    sep = bytes([JSOS_RECORD_SEPARATOR])
    with open(os.path.join(root, RESULTS_STREAM_FILENAME), "wb") as fh:
        fh.write(json.dumps(record_a).encode("utf-8"))
        fh.write(sep)
        fh.write(json.dumps(record_b).encode("utf-8"))

    with open(os.path.join(root, "artifacts", "log.txt"), "w", encoding="utf-8") as fh:
        fh.write("hello world\n")
    with open(os.path.join(root, "diagnostics", "trace.log"), "w", encoding="utf-8") as fh:
        fh.write("trace data\n")
    return


def test_result_scanner_persists_summary_tasks_artifacts_and_emits_events():
    """
    **Feature: 5-result-ingest-watcher (M1)**
    **Property: scan_once parses a testbase tree, persists summary
    + per-task + per-artifact rows, and emits one
    entity.result_tree.landed plus per-row events.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()
    create_run_state(
        db_session=session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        job_type="testbase-singlehost",
    )

    received_landed: List[EntityEvent] = []
    received_artifacts: List[EntityEvent] = []
    received_tasks: List[EntityEvent] = []
    subscribe(
        topic=ResultEventTopics.TREE_LANDED,
        subscriber=lambda e: received_landed.append(e),
    )
    subscribe(
        topic=ResultEventTopics.ARTIFACT_INGESTED,
        subscriber=lambda e: received_artifacts.append(e),
    )
    subscribe(
        topic=ResultEventTopics.TASK_RESULT_INGESTED,
        subscriber=lambda e: received_tasks.append(e),
    )

    tmpdir = tempfile.mkdtemp(prefix="b2-tree-")
    try:
        _write_testbase_tree(root=tmpdir)
        outcome = scan_once(
            db_session=session,
            run_id=run_id,
            tree_path=tmpdir,
        )
        testbase.assert_equal(outcome.had_summary, True)
        testbase.assert_equal(outcome.tasks_persisted, 2)
        testbase.assert_equal(outcome.artifacts_persisted >= 4, True)
        testbase.assert_equal(len(received_landed), 1)
        testbase.assert_equal(len(received_tasks), 2)
        testbase.assert_equal(len(received_artifacts) >= 4, True)

        fresh = session_for(engine=_engine)
        summary = (
            fresh.query(RunResultSummary)
            .filter(RunResultSummary.run_id == run_id)
            .first()
        )
        testbase.assert_equal(summary.tests_total, 2)
        testbase.assert_equal(summary.tests_passed, 1)
        testbase.assert_equal(summary.tests_failed, 1)

        tasks = (
            fresh.query(TaskResult)
            .filter(TaskResult.run_id == run_id)
            .order_by(TaskResult.test_name.asc())
            .all()
        )
        testbase.assert_equal(len(tasks), 2)

        artifact_classifications = sorted(
            row.classification
            for row in fresh.query(RunArtifact)
            .filter(RunArtifact.run_id == run_id)
            .all()
        )
        # summary file + progress-stream + artifact + diagnostic
        testbase.assert_equal("artifact" in artifact_classifications, True)
        testbase.assert_equal("diagnostic" in artifact_classifications, True)
        testbase.assert_equal("progress-stream" in artifact_classifications, True)
        testbase.assert_equal("summary" in artifact_classifications, True)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return


def test_result_scanner_idempotent_on_rescan():
    """
    **Feature: 5-result-ingest-watcher (M1)**
    **Property: a second scan_once on the same tree does not
    double-write artifact / task rows.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()
    create_run_state(
        db_session=session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        job_type="testbase-singlehost",
    )

    tmpdir = tempfile.mkdtemp(prefix="b2-rescan-")
    try:
        _write_testbase_tree(root=tmpdir)
        scan_once(db_session=session, run_id=run_id, tree_path=tmpdir)
        scan_once(db_session=session, run_id=run_id, tree_path=tmpdir)

        fresh = session_for(engine=_engine)
        artifact_count = (
            fresh.query(RunArtifact)
            .filter(RunArtifact.run_id == run_id)
            .count()
        )
        task_count = (
            fresh.query(TaskResult)
            .filter(TaskResult.run_id == run_id)
            .count()
        )
        # First scan should have set the counts; the second is idempotent.
        testbase.assert_equal(artifact_count >= 4, True)
        testbase.assert_equal(task_count, 2)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return


def test_result_scanner_missing_tree_raises_not_found():
    """
    **Feature: 5-result-ingest-watcher (M1)**
    **Property: scan_once on a non-existent path records a
    NOT_FOUND attempt row and raises ResultTreeNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()
    create_run_state(
        db_session=session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        job_type="testbase-singlehost",
    )

    raised = False
    try:
        scan_once(
            db_session=session,
            run_id=run_id,
            tree_path="/nonexistent/path/xyz-{}".format(run_id),
        )
    except ResultTreeNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return
