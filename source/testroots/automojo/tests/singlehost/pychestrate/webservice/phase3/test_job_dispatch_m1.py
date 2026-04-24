"""
.. module:: test_job_dispatch_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 5-job-dispatch + 5-dispatch-receipt M1.

.. moduleauthor:: Automation Mojo LLC

Covers the happy path + the most important rejection / idempotency
paths for the dispatch facade, the receipt service, and the
in-memory timer wheel.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import Tuple

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
    reset_registry_for_testing,
)
from automojo.pychestrate.webservice.jobs.dispatch import (
    DispatchAttempt,
    DispatchNoCandidatesError,
    DispatchOutcome,
    DispatchRequestInputs,
    DispatchStrategyProtocol,
    DispatchTransportError,
    FifoDispatchStrategy,
    InMemoryTransport,
    JobDispatcher,
    register_builtin_extensions as dispatch_register,
)
from automojo.pychestrate.webservice.jobs.dispatch.factories.strategy import (
    DispatchCandidate,
)
from automojo.pychestrate.webservice.jobs.dispatch.models import (
    DispatchAttemptStatus,
)
from automojo.pychestrate.webservice.jobs.dispatch.receipt import (
    DispatchReceipt,
    DuplicateRunReceiptError,
    ReceiptEnvelopeMismatchError,
    TimerWheel,
    lookup_by_local,
    lookup_by_run,
    record,
)
from automojo.pychestrate.webservice.jobs.envelope import (
    EnvelopeSignerBootstrapConfig,
    JobDeadline,
    JobForwardingInfo,
    JobPipelineRef,
    JobRefs,
    JobResultsLocator,
    ScopedSecret,
    install_envelope_signer,
)
from automojo.pychestrate.webservice.jobs.envelope import signer as envelope_signer
from automojo.pychestrate.webservice.messaging.event_bus import (
    reset_for_testing as reset_event_bus,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    session_for,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000000301"


def _prepare_runtime() -> None:
    """
        Reset all cross-test globals used by these cases: the
        extension registry (so FifoDispatchStrategy is the only
        strategy), the in-process event bus, and the envelope
        signer. Registers ``FifoDispatchStrategy`` + installs an
        ephemeral signing key.
    """
    import os
    reset_registry_for_testing()
    reset_event_bus()
    envelope_signer.reset_for_testing()
    dispatch_register()
    os.environ["PYCHESTRATE_DEV_MODE"] = "1"
    try:
        install_envelope_signer(
            config=EnvelopeSignerBootstrapConfig(
                source="dev",
                file_path=None,
                env_var=None,
                key_id="test-dispatch-ed25519",
            ),
        )
    finally:
        del os.environ["PYCHESTRATE_DEV_MODE"]
    return


def _build_inputs(
        *,
        run_id: str,
        candidates: Tuple[DispatchCandidate, ...]
    ) -> DispatchRequestInputs:
    """
        Produce a populated :class:`DispatchRequestInputs` with
        sensible defaults. Test cases override only what matters
        to their case.
    """
    now = datetime.now(timezone.utc)
    rtnval = DispatchRequestInputs(
        run_id=run_id,
        project_id=PROJECT_UUID,
        job_id="00000000-0000-4000-8000-000000abcd01",
        job_name="regression-smoke",
        job_type="testbase-singlehost",
        issuer="pychestrate.example.com/0.4.0",
        refs=JobRefs(
            branch="main",
            build="build-5530",
            flavor="debug",
            release="v2.1",
            commit_sha="b" * 40,
        ),
        params={"timeout_seconds": 120},
        scoped_secrets=tuple(),
        results=JobResultsLocator(
            backend_key_prefix="runs/2026/04/24/{}".format(run_id),
            backend_driver="s3",
        ),
        forwarding=JobForwardingInfo(
            progress_url="https://pychestrate.example.com/api/v1/runs/progress",
            summary_url="https://pychestrate.example.com/api/v1/runs/summary",
            auth_method="bearer",
        ),
        deadline=JobDeadline(
            soft_deadline_at=now + timedelta(minutes=30),
            hard_deadline_at=now + timedelta(minutes=60),
        ),
        pipeline=JobPipelineRef(pipeline_id="pl-1", instance_id="inst-1"),
        extension_claims=None,
        candidates=candidates,
    )
    return rtnval


def _two_candidates() -> Tuple[DispatchCandidate, ...]:
    """
        A fixed two-candidate tuple. FIFO picks the first (its
        ``last_dispatched_at_iso`` is empty, so it sorts earliest).
    """
    rtnval = (
        DispatchCandidate(
            client_id="11111111-1111-4000-8000-000000000001",
            pod_id="22222222-2222-4000-8000-000000000001",
            capability_tags=("linux", "arm64"),
            inflight_dispatch_count=0,
            last_dispatched_at_iso="",
        ),
        DispatchCandidate(
            client_id="11111111-1111-4000-8000-000000000002",
            pod_id="22222222-2222-4000-8000-000000000002",
            capability_tags=("linux", "x86_64"),
            inflight_dispatch_count=2,
            last_dispatched_at_iso="2026-04-24T10:00:00Z",
        ),
    )
    return rtnval


def test_dispatch_happy_path_transmits_and_records_attempt():
    """
    **Feature: 5-job-dispatch (M1)**
    **Property: dispatch builds a signed envelope, records an
    attempt row in TRANSMITTED, and hands the envelope to the
    transport.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    transport = InMemoryTransport()
    dispatcher = JobDispatcher(transport=transport)

    run_id = new_uuid()
    outcome = dispatcher.dispatch(
        db_session=session,
        inputs=_build_inputs(run_id=run_id, candidates=_two_candidates()),
    )

    testbase.assert_equal(outcome.status, DispatchAttemptStatus.TRANSMITTED)
    testbase.assert_equal(outcome.strategy_name, "fifo")
    testbase.assert_equal(outcome.transport_name, "in-memory")
    # FIFO picks the first candidate (empty last_dispatched sorts earliest).
    testbase.assert_equal(outcome.client_id, "11111111-1111-4000-8000-000000000001")
    testbase.assert_equal(outcome.pod_id, "22222222-2222-4000-8000-000000000001")

    fresh = session_for(engine=_engine)
    attempts = (
        fresh.query(DispatchAttempt)
        .filter(DispatchAttempt.run_id == run_id)
        .all()
    )
    testbase.assert_equal(len(attempts), 1)
    testbase.assert_equal(attempts[0].status, DispatchAttemptStatus.TRANSMITTED)

    calls = transport.calls()
    testbase.assert_equal(len(calls), 1)
    testbase.assert_equal(calls[0].client_id, outcome.client_id)
    testbase.assert_equal(calls[0].envelope_id, outcome.envelope_id)
    return


def test_dispatch_rejects_when_no_candidates():
    """
    **Feature: 5-job-dispatch (M1)**
    **Property: empty candidates raises DispatchNoCandidatesError
    before any row is persisted.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    dispatcher = JobDispatcher(transport=InMemoryTransport())

    run_id = new_uuid()
    raised = False
    try:
        dispatcher.dispatch(
            db_session=session,
            inputs=_build_inputs(run_id=run_id, candidates=tuple()),
        )
    except DispatchNoCandidatesError as xcpt:
        raised = True
        testbase.assert_equal("no eligible candidates" in str(xcpt).lower(), True)
    testbase.assert_equal(raised, True)

    fresh = session_for(engine=_engine)
    attempt_count = (
        fresh.query(DispatchAttempt)
        .filter(DispatchAttempt.run_id == run_id)
        .count()
    )
    testbase.assert_equal(attempt_count, 0)
    return


def test_dispatch_transport_failure_records_attempt_as_transport_failed():
    """
    **Feature: 5-job-dispatch (M1)**
    **Property: when the transport raises DispatchTransportError,
    the attempt row is committed in TRANSPORT_FAILED with the
    failure_reason populated, and the error propagates.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    transport = InMemoryTransport()
    transport.configure_failure(reason="conn-refused: host down")
    dispatcher = JobDispatcher(transport=transport)

    run_id = new_uuid()
    raised = False
    try:
        dispatcher.dispatch(
            db_session=session,
            inputs=_build_inputs(run_id=run_id, candidates=_two_candidates()),
        )
    except DispatchTransportError:
        raised = True
    testbase.assert_equal(raised, True)

    fresh = session_for(engine=_engine)
    attempts = (
        fresh.query(DispatchAttempt)
        .filter(DispatchAttempt.run_id == run_id)
        .all()
    )
    testbase.assert_equal(len(attempts), 1)
    testbase.assert_equal(attempts[0].status, DispatchAttemptStatus.TRANSPORT_FAILED)
    testbase.assert_equal("conn-refused" in (attempts[0].failure_reason or ""), True)
    return


def test_fifo_strategy_is_deterministic_across_reruns():
    """
    **Feature: 5-job-dispatch (M1)**
    **Property: FifoDispatchStrategy returns the same candidate
    for the same input list on every call.**
    """
    _prepare_runtime()
    candidates = _two_candidates()
    first = FifoDispatchStrategy.pick(candidates=candidates)
    second = FifoDispatchStrategy.pick(candidates=candidates)
    testbase.assert_equal(first.client_id, second.client_id)
    testbase.assert_equal(first.pod_id, second.pod_id)
    return


def test_receipt_record_is_idempotent_on_local_key():
    """
    **Feature: 5-dispatch-receipt (M1)**
    **Property: record() against an already-persisted
    (client_id, client_local_run_id) pair returns the original
    row instead of creating a second.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    dispatcher = JobDispatcher(transport=InMemoryTransport())
    run_id = new_uuid()
    outcome = dispatcher.dispatch(
        db_session=session,
        inputs=_build_inputs(run_id=run_id, candidates=_two_candidates()),
    )

    first = record(
        db_session=session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        client_id=outcome.client_id,
        attempt_id=outcome.attempt_id,
        envelope_id=outcome.envelope_id,
        client_local_run_id="client-local-42",
    )
    second = record(
        db_session=session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        client_id=outcome.client_id,
        attempt_id=outcome.attempt_id,
        envelope_id=outcome.envelope_id,
        client_local_run_id="client-local-42",
    )
    testbase.assert_equal(first.receipt_id, second.receipt_id)

    fresh = session_for(engine=_engine)
    receipt_count = (
        fresh.query(DispatchReceipt)
        .filter(DispatchReceipt.run_id == run_id)
        .count()
    )
    testbase.assert_equal(receipt_count, 1)
    return


def test_receipt_distinct_local_for_same_run_raises_duplicate():
    """
    **Feature: 5-dispatch-receipt (M1)**
    **Property: A second receipt for the same run_id with a
    DIFFERENT client_local_run_id raises DuplicateRunReceiptError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    dispatcher = JobDispatcher(transport=InMemoryTransport())
    run_id = new_uuid()
    outcome = dispatcher.dispatch(
        db_session=session,
        inputs=_build_inputs(run_id=run_id, candidates=_two_candidates()),
    )

    record(
        db_session=session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        client_id=outcome.client_id,
        attempt_id=outcome.attempt_id,
        envelope_id=outcome.envelope_id,
        client_local_run_id="first-local",
    )

    raised = False
    try:
        record(
            db_session=session,
            run_id=run_id,
            project_id=PROJECT_UUID,
            client_id=outcome.client_id,
            attempt_id=outcome.attempt_id,
            envelope_id=outcome.envelope_id,
            client_local_run_id="second-distinct-local",
        )
    except DuplicateRunReceiptError as xcpt:
        raised = True
        testbase.assert_equal("first-local" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    return


def test_receipt_mismatched_envelope_rejected():
    """
    **Feature: 5-dispatch-receipt (M1)**
    **Property: a receipt carrying an envelope_id that does not
    match any attempt of the run raises
    ReceiptEnvelopeMismatchError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    dispatcher = JobDispatcher(transport=InMemoryTransport())
    run_id = new_uuid()
    outcome = dispatcher.dispatch(
        db_session=session,
        inputs=_build_inputs(run_id=run_id, candidates=_two_candidates()),
    )

    raised = False
    try:
        record(
            db_session=session,
            run_id=run_id,
            project_id=PROJECT_UUID,
            client_id=outcome.client_id,
            attempt_id=outcome.attempt_id,
            envelope_id="99999999-9999-4000-8000-999999999999",
            client_local_run_id="local-xyz",
        )
    except ReceiptEnvelopeMismatchError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_receipt_late_arrival_flag_set_when_past_deadline():
    """
    **Feature: 5-dispatch-receipt (M1)**
    **Property: received_at > deadline_at sets late_arrival=True
    on the persisted row.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    dispatcher = JobDispatcher(transport=InMemoryTransport())
    run_id = new_uuid()
    outcome = dispatcher.dispatch(
        db_session=session,
        inputs=_build_inputs(run_id=run_id, candidates=_two_candidates()),
    )

    base = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)
    past_deadline = base - timedelta(minutes=5)
    record(
        db_session=session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        client_id=outcome.client_id,
        attempt_id=outcome.attempt_id,
        envelope_id=outcome.envelope_id,
        client_local_run_id="late-local",
        received_at=base,
        deadline_at=past_deadline,
    )

    fetched = lookup_by_run(db_session=session, run_id=run_id)
    testbase.assert_equal(fetched.late_arrival, True)

    same_by_local = lookup_by_local(
        db_session=session,
        client_id=outcome.client_id,
        client_local_run_id="late-local",
    )
    testbase.assert_equal(same_by_local.receipt_id, fetched.receipt_id)
    return


def test_timer_wheel_expect_cancel_and_fire_expired():
    """
    **Feature: 5-dispatch-receipt (M1)**
    **Property: TimerWheel arms with expect, removes on cancel,
    fires entries whose deadline has passed, and ignores unrelated
    cancels.**
    """
    _prepare_runtime()
    wheel = TimerWheel()
    now = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)

    wheel.expect(
        attempt_id="a1", run_id="r1", project_id=PROJECT_UUID,
        deadline_at=now + timedelta(seconds=30),
    )
    wheel.expect(
        attempt_id="a2", run_id="r2", project_id=PROJECT_UUID,
        deadline_at=now - timedelta(seconds=5),  # already expired
    )
    testbase.assert_equal(wheel.pending_count(), 2)

    # cancel an unrelated id — returns False, nothing removed
    testbase.assert_equal(wheel.cancel(attempt_id="nope"), False)
    testbase.assert_equal(wheel.pending_count(), 2)

    fired = wheel.fire_expired(now=now)
    testbase.assert_equal(len(fired), 1)
    testbase.assert_equal(fired[0].attempt_id, "a2")
    testbase.assert_equal(wheel.pending_count(), 1)

    # remaining pending cancels cleanly
    testbase.assert_equal(wheel.cancel(attempt_id="a1"), True)
    testbase.assert_equal(wheel.pending_count(), 0)
    return


def test_dispatch_strategy_not_registered_is_surfaced():
    """
    **Feature: 5-job-dispatch (M1)**
    **Property: when no dispatch_strategy implementation is
    registered, the dispatcher surfaces a DispatchError naming
    the missing registration.**
    """
    from automojo.pychestrate.webservice.jobs.dispatch.errors import (
        DispatchStrategyNotRegisteredError,
    )
    reset_registry_for_testing()  # strip every factory
    reset_event_bus()
    envelope_signer.reset_for_testing()

    import os
    os.environ["PYCHESTRATE_DEV_MODE"] = "1"
    try:
        install_envelope_signer(
            config=EnvelopeSignerBootstrapConfig(
                source="dev",
                file_path=None,
                env_var=None,
                key_id="test-no-strategy-ed25519",
            ),
        )
    finally:
        del os.environ["PYCHESTRATE_DEV_MODE"]

    _engine, session = build_in_memory_session()
    dispatcher = JobDispatcher(transport=InMemoryTransport())

    raised = False
    try:
        dispatcher.dispatch(
            db_session=session,
            inputs=_build_inputs(run_id=new_uuid(), candidates=_two_candidates()),
        )
    except DispatchStrategyNotRegisteredError as xcpt:
        raised = True
        testbase.assert_equal("dispatch_strategy" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    return
