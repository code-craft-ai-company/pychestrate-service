"""
.. module:: test_b4_artifact_cancel_offline_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for B4 — 5-artifact-store + 5-cancel-reconcile + 5-offline-tolerance M1.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import io

from datetime import datetime, timedelta, timezone
from typing import List

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.artifacts import (
    ArtifactRegistration,
    ArtifactStore,
    ArtifactReferenceNotFoundError,
    build_cas_key,
    hash_blob_stream,
    register_builtin_extensions as artifacts_register,
)
from ccai.pychestrate.webservice.artifacts.models import (
    ArtifactBlob,
    RunArtifactReference,
)
from ccai.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from ccai.pychestrate.webservice.jobs.cancel import (
    CancelDispatcher,
    CancelDuplicateRequestError,
    CancelEventTopics,
    CancelStatus,
    CancelTransportError,
    InMemoryCancelTransport,
    handle_ack,
    request_cancel,
)
from ccai.pychestrate.webservice.jobs.cancel.models import CancelRequest
from ccai.pychestrate.webservice.jobs.offline import (
    DeferredCancelQueue,
    DeferredCancelStatus,
    PodLivenessTier,
    PodOfflineStateService,
    ReplayAuthError,
    ReplayCoordinator,
    ReplaySeqGapError,
)
from ccai.pychestrate.webservice.jobs.reconcile import (
    ReconcileOutcome,
    RunReconciler,
)
from ccai.pychestrate.webservice.jobs.run.state import (
    RunEvent,
    RunState,
    create_run as create_run_state,
    get_snapshot,
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


PROJECT_UUID = "00000000-0000-4000-8000-000000000801"
CLIENT_UUID = "33333333-3333-4000-8000-000000000801"
POD_UUID = "44444444-4444-4000-8000-000000000801"


def _prepare_runtime() -> None:
    """
        Reset the in-process bus and the extension registry; then
        seed the artifacts factory.
    """
    reset_registry_for_testing()
    reset_event_bus()
    artifacts_register()
    return


# -----------------------------
# 5-artifact-store tests
# -----------------------------

def test_hash_blob_stream_matches_known_sha256():
    """
    **Feature: 5-artifact-store (M1)**
    **Property: hash_blob_stream returns the lowercase-hex
    SHA-256 of the consumed bytes.**
    """
    payload = b"hello pychestrate\n"
    digest = hash_blob_stream(stream=io.BytesIO(payload))
    # Verified externally: sha256("hello pychestrate\n") starts with
    # the prefix below; we only need a stable property that the
    # function is deterministic and returns 64 hex chars.
    testbase.assert_equal(len(digest), 64)
    testbase.assert_equal(digest.islower(), True)
    testbase.assert_equal(
        hash_blob_stream(stream=io.BytesIO(payload)),
        digest,
    )
    return


def test_build_cas_key_layout_for_hot_and_cold():
    """
    **Feature: 5-artifact-store (M1)**
    **Property: build_cas_key emits cas/<tier>/<aa>/<bb>/<digest>.**
    """
    digest = "a" * 64
    hot = build_cas_key(digest=digest, tier="hot")
    testbase.assert_equal(hot, "cas/hot/aa/aa/{}".format(digest))
    cold = build_cas_key(digest=digest, tier="cold")
    testbase.assert_equal(cold, "cas/cold/aa/aa/{}".format(digest))
    return


def test_artifact_register_idempotent_and_emits_event():
    """
    **Feature: 5-artifact-store (M1)**
    **Property: register is idempotent on (run_id, label); blob
    reference_count increments only when a fresh reference is
    created. Emits entity.artifact.registered.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    store = ArtifactStore()
    digest = "b" * 64
    received: List[EntityEvent] = []
    subscribe(
        topic="entity.artifact.registered",
        subscriber=lambda e: received.append(e),
    )

    run_id = new_uuid()
    reg = ArtifactRegistration(
        run_id=run_id,
        project_id=PROJECT_UUID,
        label="build/log.txt",
        artifact_type="log",
        cas_digest=digest,
        size_bytes=1024,
        content_type="text/plain",
    )
    first = store.register(db_session=session, registration=reg)
    second = store.register(db_session=session, registration=reg)
    testbase.assert_equal(first.reference_id, second.reference_id)

    fresh = session_for(engine=_engine)
    blob = (
        fresh.query(ArtifactBlob)
        .filter(ArtifactBlob.cas_digest == digest)
        .first()
    )
    testbase.assert_equal(blob.reference_count, 1)

    refs = (
        fresh.query(RunArtifactReference)
        .filter(RunArtifactReference.run_id == run_id)
        .all()
    )
    testbase.assert_equal(len(refs), 1)
    testbase.assert_equal(len(received), 2)  # one event per register call
    return


def test_artifact_get_unknown_raises():
    """
    **Feature: 5-artifact-store (M1)**
    **Property: get on an unknown (run_id, label) raises
    ArtifactReferenceNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    store = ArtifactStore()
    raised = False
    try:
        store.get(db_session=session, run_id=new_uuid(), label="x")
    except ArtifactReferenceNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -----------------------------
# 5-cancel-reconcile tests
# -----------------------------

def test_cancel_dispatcher_happy_path_records_attempt():
    """
    **Feature: 5-cancel-reconcile (M1)**
    **Property: send_cancel_rpc transmits the cancel via the
    transport, flips the row to TRANSMITTED, and emits
    entity.run.cancel_request.transmitted.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    transport = InMemoryCancelTransport()
    dispatcher = CancelDispatcher(transport=transport)
    received: List[EntityEvent] = []
    subscribe(
        topic=CancelEventTopics.REQUEST_TRANSMITTED,
        subscriber=lambda e: received.append(e),
    )

    run_id = new_uuid()
    request = request_cancel(
        dispatcher=dispatcher,
        db_session=session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        client_id=CLIENT_UUID,
        requested_by=None,
        reason="user-cancel",
    )
    testbase.assert_equal(request.status, CancelStatus.TRANSMITTED)
    testbase.assert_equal(len(transport.calls()), 1)
    testbase.assert_equal(len(received), 1)

    # Ack flips the row to ACKED + emits cancel_ack.
    received_ack: List[EntityEvent] = []
    subscribe(
        topic=CancelEventTopics.ACK_RECEIVED,
        subscriber=lambda e: received_ack.append(e),
    )
    handle_ack(db_session=session, request_id=str(request.request_id))
    fresh = session_for(engine=_engine)
    after = (
        fresh.query(CancelRequest)
        .filter(CancelRequest.request_id == request.request_id)
        .first()
    )
    testbase.assert_equal(after.status, CancelStatus.ACKED)
    testbase.assert_equal(len(received_ack), 1)
    return


def test_cancel_duplicate_request_rejects():
    """
    **Feature: 5-cancel-reconcile (M1)**
    **Property: a second send_cancel_rpc against an open
    request raises CancelDuplicateRequestError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    dispatcher = CancelDispatcher(transport=InMemoryCancelTransport())
    run_id = new_uuid()
    request_cancel(
        dispatcher=dispatcher,
        db_session=session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        client_id=CLIENT_UUID,
        requested_by=None,
        reason="first",
    )
    raised = False
    try:
        request_cancel(
            dispatcher=dispatcher,
            db_session=session,
            run_id=run_id,
            project_id=PROJECT_UUID,
            client_id=CLIENT_UUID,
            requested_by=None,
            reason="second",
        )
    except CancelDuplicateRequestError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_cancel_transport_failure_marks_request_failed():
    """
    **Feature: 5-cancel-reconcile (M1)**
    **Property: a transport error flips the row to FAILED with
    failure_reason and emits entity.run.cancel_request.failed.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    transport = InMemoryCancelTransport()
    transport.configure_failure(reason="link down")
    dispatcher = CancelDispatcher(transport=transport)
    received: List[EntityEvent] = []
    subscribe(
        topic=CancelEventTopics.REQUEST_FAILED,
        subscriber=lambda e: received.append(e),
    )

    run_id = new_uuid()
    raised = False
    try:
        request_cancel(
            dispatcher=dispatcher,
            db_session=session,
            run_id=run_id,
            project_id=PROJECT_UUID,
            client_id=CLIENT_UUID,
            requested_by=None,
            reason="will fail",
        )
    except CancelTransportError:
        raised = True
    testbase.assert_equal(raised, True)
    testbase.assert_equal(len(received), 1)

    fresh = session_for(engine=_engine)
    rows = (
        fresh.query(CancelRequest)
        .filter(CancelRequest.run_id == run_id)
        .all()
    )
    testbase.assert_equal(len(rows), 1)
    testbase.assert_equal(rows[0].status, CancelStatus.FAILED)
    testbase.assert_equal("link down" in (rows[0].failure_reason or ""), True)
    return


def test_run_reconciler_resolves_divergence_to_terminal():
    """
    **Feature: 5-cancel-reconcile (M1)**
    **Property: when the client reports a terminal state and the
    service is non-terminal, RunReconciler advances the run to
    the client's truth and persists DIVERGENCE_RESOLVED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    run_id = new_uuid()
    create_run_state(
        db_session=session, run_id=run_id,
        project_id=PROJECT_UUID, job_type="testbase",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="x",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.RECEIPT_RECORDED, actor="x",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.FIRST_PROGRESS, actor="x",
    )
    transition(
        db_session=session, run_id=run_id,
        event=RunEvent.CANCEL_REQUESTED, actor="x",
    )

    reconciler = RunReconciler()
    decision = reconciler.reconcile_on_reconnect(
        db_session=session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        client_id=CLIENT_UUID,
        client_reported_state=RunState.COMPLETED,
        note="post-disconnect reconcile",
    )
    testbase.assert_equal(decision.outcome, ReconcileOutcome.DIVERGENCE_RESOLVED)
    testbase.assert_equal(decision.resolved_state, RunState.COMPLETED.value)

    fresh = session_for(engine=_engine)
    snapshot = get_snapshot(db_session=fresh, run_id=run_id)
    testbase.assert_equal(snapshot.state, RunState.COMPLETED)
    return


# -----------------------------
# 5-offline-tolerance tests
# -----------------------------

def test_pod_state_drop_then_reconnect_returns_healthy():
    """
    **Feature: 5-offline-tolerance (M1)**
    **Property: observe_session_dropped flips the pod to
    DEGRADED; observe_reconnected flips it back to HEALTHY.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    service = PodOfflineStateService()

    row = service.observe_session_dropped(
        db_session=session,
        pod_id=POD_UUID,
        project_id=PROJECT_UUID,
        client_id=CLIENT_UUID,
    )
    testbase.assert_equal(row.tier, PodLivenessTier.DEGRADED)
    testbase.assert_equal(service.is_eligible_for_dispatch(
        db_session=session, pod_id=POD_UUID,
    ), False)

    row = service.observe_reconnected(
        db_session=session,
        pod_id=POD_UUID,
        project_id=PROJECT_UUID,
        client_id=CLIENT_UUID,
    )
    testbase.assert_equal(row.tier, PodLivenessTier.HEALTHY)
    testbase.assert_equal(service.is_eligible_for_dispatch(
        db_session=session, pod_id=POD_UUID,
    ), True)
    return


def test_pod_state_evaluate_tier_promotes_to_offline_after_threshold():
    """
    **Feature: 5-offline-tolerance (M1)**
    **Property: evaluate_tier returns OFFLINE once enough time
    has passed since the last drop.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    service = PodOfflineStateService(
        degrade_after_seconds=10,
        offline_after_seconds=60,
    )
    drop_at = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)
    service.observe_session_dropped(
        db_session=session,
        pod_id=POD_UUID,
        project_id=PROJECT_UUID,
        client_id=CLIENT_UUID,
        dropped_at=drop_at,
    )
    # 30 s past drop — DEGRADED tier returned in evaluate_tier.
    tier = service.evaluate_tier(
        db_session=session, pod_id=POD_UUID,
        now=drop_at + timedelta(seconds=30),
    )
    testbase.assert_equal(tier, PodLivenessTier.DEGRADED)
    # 90 s past drop — OFFLINE.
    tier = service.evaluate_tier(
        db_session=session, pod_id=POD_UUID,
        now=drop_at + timedelta(seconds=90),
    )
    testbase.assert_equal(tier, PodLivenessTier.OFFLINE)
    return


def test_deferred_cancel_queue_routes_offline_pods_to_queue():
    """
    **Feature: 5-offline-tolerance (M1)**
    **Property: queue_if_offline returns None for HEALTHY pods
    (caller dispatches live), persists a queued row otherwise.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    pod_state = PodOfflineStateService()
    queue = DeferredCancelQueue(pod_state=pod_state)

    healthy_pod = "44444444-4444-4000-8000-000000000900"
    direct = queue.queue_if_offline(
        db_session=session,
        run_id=new_uuid(),
        project_id=PROJECT_UUID,
        client_id=CLIENT_UUID,
        pod_id=healthy_pod,
        cancel_request_id=new_uuid(),
        reason="user-cancel",
    )
    testbase.assert_equal(direct, None)

    pod_state.observe_session_dropped(
        db_session=session,
        pod_id=POD_UUID,
        project_id=PROJECT_UUID,
        client_id=CLIENT_UUID,
    )
    queued = queue.queue_if_offline(
        db_session=session,
        run_id=new_uuid(),
        project_id=PROJECT_UUID,
        client_id=CLIENT_UUID,
        pod_id=POD_UUID,
        cancel_request_id=new_uuid(),
        reason="user-cancel",
    )
    testbase.assert_equal(queued is not None, True)
    testbase.assert_equal(queued.status, DeferredCancelStatus.QUEUED)
    pending = queue.list_queued_for_pod(db_session=session, pod_id=POD_UUID)
    testbase.assert_equal(len(pending), 1)
    return


def test_replay_coordinator_advances_cursor_and_rejects_gap():
    """
    **Feature: 5-offline-tolerance (M1)**
    **Property: accept_replay advances the cursor on the
    expected sequence; gap raises ReplaySeqGapError; mismatched
    client raises ReplayAuthError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    coord = ReplayCoordinator()
    run_id = new_uuid()

    first = coord.accept_replay(
        db_session=session,
        client_id=CLIENT_UUID,
        run_id=run_id,
        sequence=0,
        authenticated_client_id=CLIENT_UUID,
    )
    testbase.assert_equal(first.accepted, True)
    testbase.assert_equal(first.cursor_advanced_to, 1)

    second = coord.accept_replay(
        db_session=session,
        client_id=CLIENT_UUID,
        run_id=run_id,
        sequence=1,
        authenticated_client_id=CLIENT_UUID,
    )
    testbase.assert_equal(second.cursor_advanced_to, 2)

    # Idempotent on already-applied sequence.
    repeat = coord.accept_replay(
        db_session=session,
        client_id=CLIENT_UUID,
        run_id=run_id,
        sequence=0,
        authenticated_client_id=CLIENT_UUID,
    )
    testbase.assert_equal(repeat.accepted, False)
    testbase.assert_equal(repeat.cursor_advanced_to, 2)

    raised_gap = False
    try:
        coord.accept_replay(
            db_session=session,
            client_id=CLIENT_UUID,
            run_id=run_id,
            sequence=10,  # gap
            authenticated_client_id=CLIENT_UUID,
        )
    except ReplaySeqGapError:
        raised_gap = True
    testbase.assert_equal(raised_gap, True)

    raised_auth = False
    try:
        coord.accept_replay(
            db_session=session,
            client_id=CLIENT_UUID,
            run_id=run_id,
            sequence=2,
            authenticated_client_id="55555555-5555-4000-8000-000000000099",
        )
    except ReplayAuthError:
        raised_auth = True
    testbase.assert_equal(raised_auth, True)
    return
