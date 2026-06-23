"""
.. module:: test_p4b_checkout_conflict_scheduler_m1
    :synopsis: Tests for P4b — 4-checkout-checkin +
               4-conflict-deconfliction + 4-reservation-scheduler M1.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from ccai.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from ccai.pychestrate.webservice.resources.checkout import (
    ReservationConflictError,
    ReservationEventTopics,
    ReservationMode,
    ReservationNotFoundError,
    ReservationState,
    get_reservation,
    list_reservations_for_resource,
    release,
    reserve,
)
from ccai.pychestrate.webservice.resources.conflict import (
    ActiveReservationSnapshot,
    CandidateReservation,
    ExclusiveModeRule,
    SharedModeRule,
    evaluate,
    register_builtin_extensions as conflict_register,
)
from ccai.pychestrate.webservice.resources.inventory import (
    register_builtin_extensions as inventory_register,
    register_resource,
)
from ccai.pychestrate.webservice.resources.pools import (
    add_member,
    create_pool,
)
from ccai.pychestrate.webservice.resources.scheduler import (
    SchedulerAspects,
    SchedulerAspectsInvalidError,
    SchedulerEntryNotFoundError,
    SchedulerEntryState,
    SchedulerEventTopics,
    cancel as scheduler_cancel,
    enqueue as scheduler_enqueue,
    get_entry as scheduler_get_entry,
    list_queued_for_pool as scheduler_list_queued,
    mark_dispatched as scheduler_mark_dispatched,
    pick_next_for_pool as scheduler_pick_next,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-0000000000b4"
ACTOR_UUID = "00000000-0000-4000-8000-0000000000b5"


def _prepare_runtime() -> None:
    """
        Reset cross-test globals + register the in-tree
        :class:`DeviceResourceKind` and the conflict rules.
    """
    reset_registry_for_testing()
    reset_event_bus()
    inventory_register()
    conflict_register()
    return


def _new_resource(*, session, hostname: str) -> str:
    """
        Helper: register a single device resource and return its
        id.
    """
    view = register_resource(
        db_session=session,
        project_id=PROJECT_UUID,
        kind="device",
        display_name=hostname,
        attributes={"hostname": hostname},
    )
    rtnval = view.resource_id
    return rtnval


# -------------------------------------
# 4-checkout-checkin tests
# -------------------------------------

def test_reserve_persists_granted_and_emits_events():
    """
    **Feature: 4-checkout-checkin (M1)**
    **Property: reserve on an idle resource commits a GRANTED
    row and emits both entity.reservation.created and
    entity.reservation.granted.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_created: List[EntityEvent] = []
    received_granted: List[EntityEvent] = []
    subscribe(
        topic=ReservationEventTopics.CREATED,
        subscriber=lambda e: received_created.append(e),
    )
    subscribe(
        topic=ReservationEventTopics.GRANTED,
        subscriber=lambda e: received_granted.append(e),
    )

    res_id = _new_resource(session=session, hostname="reserve-host")
    view = reserve(
        db_session=session,
        project_id=PROJECT_UUID,
        resource_id=res_id,
        requested_by=ACTOR_UUID,
        mode=ReservationMode.EXCLUSIVE,
    )
    testbase.assert_equal(view.state, ReservationState.GRANTED)
    testbase.assert_equal(view.mode, ReservationMode.EXCLUSIVE)
    testbase.assert_equal(view.granted_at is not None, True)
    testbase.assert_equal(len(received_created), 1)
    testbase.assert_equal(len(received_granted), 1)
    return


def test_release_transitions_to_released_and_emits():
    """
    **Feature: 4-checkout-checkin (M1)**
    **Property: release flips a GRANTED row to RELEASED and emits
    entity.reservation.released; subsequent release calls are
    idempotent.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_released: List[EntityEvent] = []
    subscribe(
        topic=ReservationEventTopics.RELEASED,
        subscriber=lambda e: received_released.append(e),
    )

    res_id = _new_resource(session=session, hostname="release-host")
    granted = reserve(
        db_session=session,
        project_id=PROJECT_UUID,
        resource_id=res_id,
        requested_by=ACTOR_UUID,
        mode=ReservationMode.EXCLUSIVE,
    )
    released = release(
        db_session=session, reservation_id=granted.reservation_id,
    )
    testbase.assert_equal(released.state, ReservationState.RELEASED)
    testbase.assert_equal(released.released_at is not None, True)
    testbase.assert_equal(len(received_released), 1)

    # Idempotent: second release is a no-op.
    again = release(
        db_session=session, reservation_id=granted.reservation_id,
    )
    testbase.assert_equal(again.state, ReservationState.RELEASED)
    testbase.assert_equal(len(received_released), 1)
    return


def test_release_forced_emits_forced_topic():
    """
    **Feature: 4-checkout-checkin (M1)**
    **Property: release(forced=True) emits
    entity.reservation.forced_released, not the standard
    .released.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_forced: List[EntityEvent] = []
    received_normal: List[EntityEvent] = []
    subscribe(
        topic=ReservationEventTopics.FORCED_RELEASED,
        subscriber=lambda e: received_forced.append(e),
    )
    subscribe(
        topic=ReservationEventTopics.RELEASED,
        subscriber=lambda e: received_normal.append(e),
    )

    res_id = _new_resource(session=session, hostname="forced-host")
    granted = reserve(
        db_session=session,
        project_id=PROJECT_UUID,
        resource_id=res_id,
        requested_by=ACTOR_UUID,
        mode=ReservationMode.EXCLUSIVE,
    )
    view = release(
        db_session=session, reservation_id=granted.reservation_id,
        forced=True,
    )
    testbase.assert_equal(view.state, ReservationState.FORCED_RELEASED)
    testbase.assert_equal(len(received_forced), 1)
    testbase.assert_equal(len(received_normal), 0)
    return


def test_get_reservation_unknown_raises():
    """
    **Feature: 4-checkout-checkin (M1)**
    **Property: get_reservation on an unknown id raises
    ReservationNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_reservation(db_session=session, reservation_id=new_uuid())
    except ReservationNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_list_reservations_orders_by_requested_at():
    """
    **Feature: 4-checkout-checkin (M1)**
    **Property: list_reservations_for_resource returns every
    reservation against a resource ordered by request time.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    res_id = _new_resource(session=session, hostname="list-host")
    first = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
        requested_by=ACTOR_UUID, mode=ReservationMode.SHARED,
    )
    release(db_session=session, reservation_id=first.reservation_id)
    second = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
        requested_by=ACTOR_UUID, mode=ReservationMode.SHARED,
    )

    rows = list_reservations_for_resource(
        db_session=session, resource_id=res_id,
    )
    testbase.assert_equal(len(rows), 2)
    testbase.assert_equal(rows[0].reservation_id, first.reservation_id)
    testbase.assert_equal(rows[1].reservation_id, second.reservation_id)
    return


# -------------------------------------
# 4-conflict-deconfliction tests
# -------------------------------------

def test_exclusive_rule_vetoes_exclusive_when_already_active():
    """
    **Feature: 4-conflict-deconfliction (M1)**
    **Property: ExclusiveModeRule vetoes an exclusive candidate
    when any active reservation exists.**
    """
    _prepare_runtime()
    res_id = "00000000-0000-4000-8000-0000000000c1"
    candidate = CandidateReservation(
        project_id=PROJECT_UUID, resource_id=res_id,
        mode="exclusive", requested_by=ACTOR_UUID,
    )
    active = [
        ActiveReservationSnapshot(
            reservation_id=new_uuid(), project_id=PROJECT_UUID,
            resource_id=res_id, mode="shared",
            requested_by=ACTOR_UUID,
        ),
    ]
    decision = ExclusiveModeRule.evaluate(
        candidate=candidate, active_reservations=tuple(active),
    )
    testbase.assert_equal(decision.accepted, False)
    testbase.assert_equal(decision.rule_name, "exclusive-mode")
    return


def test_exclusive_rule_vetoes_shared_when_active_is_exclusive():
    """
    **Feature: 4-conflict-deconfliction (M1)**
    **Property: ExclusiveModeRule vetoes a shared candidate when
    any active reservation is exclusive.**
    """
    _prepare_runtime()
    res_id = "00000000-0000-4000-8000-0000000000c2"
    candidate = CandidateReservation(
        project_id=PROJECT_UUID, resource_id=res_id,
        mode="shared", requested_by=ACTOR_UUID,
    )
    active = [
        ActiveReservationSnapshot(
            reservation_id=new_uuid(), project_id=PROJECT_UUID,
            resource_id=res_id, mode="exclusive",
            requested_by=ACTOR_UUID,
        ),
    ]
    decision = ExclusiveModeRule.evaluate(
        candidate=candidate, active_reservations=tuple(active),
    )
    testbase.assert_equal(decision.accepted, False)
    return


def test_shared_rule_accepts_shared_when_active_is_shared():
    """
    **Feature: 4-conflict-deconfliction (M1)**
    **Property: SharedModeRule accepts a shared candidate against
    an existing shared reservation.**
    """
    _prepare_runtime()
    res_id = "00000000-0000-4000-8000-0000000000c3"
    candidate = CandidateReservation(
        project_id=PROJECT_UUID, resource_id=res_id,
        mode="shared", requested_by=ACTOR_UUID,
    )
    active = [
        ActiveReservationSnapshot(
            reservation_id=new_uuid(), project_id=PROJECT_UUID,
            resource_id=res_id, mode="shared",
            requested_by=ACTOR_UUID,
        ),
    ]
    excl_decision = ExclusiveModeRule.evaluate(
        candidate=candidate, active_reservations=tuple(active),
    )
    shared_decision = SharedModeRule.evaluate(
        candidate=candidate, active_reservations=tuple(active),
    )
    testbase.assert_equal(excl_decision.accepted, True)
    testbase.assert_equal(shared_decision.accepted, True)
    return


def test_evaluator_first_veto_wins():
    """
    **Feature: 4-conflict-deconfliction (M1)**
    **Property: the evaluator walks rules in PRECEDENCE order and
    short-circuits at the first veto, surfacing vetoed_by.**
    """
    _prepare_runtime()
    res_id = "00000000-0000-4000-8000-0000000000c4"
    candidate = CandidateReservation(
        project_id=PROJECT_UUID, resource_id=res_id,
        mode="exclusive", requested_by=ACTOR_UUID,
    )
    active = [
        ActiveReservationSnapshot(
            reservation_id=new_uuid(), project_id=PROJECT_UUID,
            resource_id=res_id, mode="shared",
            requested_by=ACTOR_UUID,
        ),
    ]
    evaluation = evaluate(
        candidate=candidate, active_reservations=active,
    )
    testbase.assert_equal(evaluation.accepted, False)
    testbase.assert_equal(evaluation.vetoed_by, "exclusive-mode")
    # Only the vetoing rule's decision is recorded — short-circuit.
    testbase.assert_equal(len(evaluation.decisions), 1)
    return


def test_evaluator_accepts_when_no_active_reservations():
    """
    **Feature: 4-conflict-deconfliction (M1)**
    **Property: the evaluator accepts a candidate against an
    empty active set; vetoed_by stays empty.**
    """
    _prepare_runtime()
    res_id = "00000000-0000-4000-8000-0000000000c5"
    candidate = CandidateReservation(
        project_id=PROJECT_UUID, resource_id=res_id,
        mode="exclusive", requested_by=ACTOR_UUID,
    )
    evaluation = evaluate(
        candidate=candidate, active_reservations=[],
    )
    testbase.assert_equal(evaluation.accepted, True)
    testbase.assert_equal(evaluation.vetoed_by, "")
    # Both registered rules ran.
    testbase.assert_equal(len(evaluation.decisions), 2)
    return


# -------------------------------------
# checkout × conflict integration tests
# -------------------------------------

def test_reserve_rejected_when_exclusive_conflict():
    """
    **Feature: 4-checkout-checkin × 4-conflict-deconfliction (M1)**
    **Property: when the conflict evaluator vetoes, reserve
    persists a REJECTED row, emits
    entity.reservation.conflict_rejected, and raises
    ReservationConflictError. The first GRANTED row stays
    untouched.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_rejected: List[EntityEvent] = []
    subscribe(
        topic=ReservationEventTopics.CONFLICT_REJECTED,
        subscriber=lambda e: received_rejected.append(e),
    )

    res_id = _new_resource(session=session, hostname="conflict-host")
    granted = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )

    raised = False
    try:
        reserve(
            db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
            requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
        )
    except ReservationConflictError as xcpt:
        raised = True
        testbase.assert_equal("exclusive-mode" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    testbase.assert_equal(len(received_rejected), 1)

    # The first reservation is still GRANTED; the rejected row is
    # persisted alongside it.
    rows = list_reservations_for_resource(
        db_session=session, resource_id=res_id,
    )
    states = sorted(r.state.value for r in rows)
    testbase.assert_equal(states, ["granted", "rejected"])

    # The original grant is untouched.
    refreshed = get_reservation(
        db_session=session, reservation_id=granted.reservation_id,
    )
    testbase.assert_equal(refreshed.state, ReservationState.GRANTED)
    return


def test_reserve_after_release_succeeds():
    """
    **Feature: 4-checkout-checkin × 4-conflict-deconfliction (M1)**
    **Property: a fresh reserve after a prior release on the same
    resource is granted — released reservations are not active.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    res_id = _new_resource(session=session, hostname="serial-host")
    first = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )
    release(db_session=session, reservation_id=first.reservation_id)

    second = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )
    testbase.assert_equal(second.state, ReservationState.GRANTED)
    return


# -------------------------------------
# 4-reservation-scheduler tests
# -------------------------------------

def _seed_pool_with_one_member(*, session) -> str:
    """
        Helper: create a one-member pool and return its id.
    """
    res_id = _new_resource(session=session, hostname="sched-pool-host")
    pool = create_pool(
        db_session=session, project_id=PROJECT_UUID,
        name="sched-pool",
    )
    add_member(
        db_session=session, pool_id=pool.pool_id, resource_id=res_id,
    )
    rtnval = pool.pool_id
    return rtnval


def test_scheduler_enqueue_persists_and_emits():
    """
    **Feature: 4-reservation-scheduler (M1)**
    **Property: enqueue inserts a SchedulerEntry in QUEUED and
    emits pychestrate.scheduler.enqueued. Aspect knobs round-trip
    onto the persisted row.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=SchedulerEventTopics.ENQUEUED,
        subscriber=lambda e: received.append(e),
    )

    pool_id = _seed_pool_with_one_member(session=session)
    res_id = _new_resource(session=session, hostname="enqueue-target")
    candidate = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )
    entry = scheduler_enqueue(
        db_session=session,
        reservation_id=candidate.reservation_id,
        pool_id=pool_id,
        project_id=PROJECT_UUID,
        aspects=SchedulerAspects(
            algorithm="fifo", priority=25,
            fair_share_key=ACTOR_UUID, fair_share_weight=2.0,
        ),
    )
    testbase.assert_equal(entry.state, SchedulerEntryState.QUEUED)
    testbase.assert_equal(entry.priority, 25)
    testbase.assert_equal(entry.fair_share_weight, 2.0)
    testbase.assert_equal(entry.fair_share_key, ACTOR_UUID)
    testbase.assert_equal(len(received), 1)
    return


def test_scheduler_enqueue_idempotent_when_queued():
    """
    **Feature: 4-reservation-scheduler (M1)**
    **Property: a duplicate enqueue against a still-queued entry
    returns the existing view without re-emitting the topic.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=SchedulerEventTopics.ENQUEUED,
        subscriber=lambda e: received.append(e),
    )

    pool_id = _seed_pool_with_one_member(session=session)
    res_id = _new_resource(session=session, hostname="dup-enqueue-target")
    reservation = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )
    first = scheduler_enqueue(
        db_session=session, reservation_id=reservation.reservation_id,
        pool_id=pool_id, project_id=PROJECT_UUID,
    )
    second = scheduler_enqueue(
        db_session=session, reservation_id=reservation.reservation_id,
        pool_id=pool_id, project_id=PROJECT_UUID,
    )
    testbase.assert_equal(first.entry_id, second.entry_id)
    testbase.assert_equal(len(received), 1)
    return


def test_scheduler_enqueue_invalid_aspects_raise():
    """
    **Feature: 4-reservation-scheduler (M1)**
    **Property: aspects outside the allowed range raise
    SchedulerAspectsInvalidError naming the offending field.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    pool_id = _seed_pool_with_one_member(session=session)
    res_id = _new_resource(session=session, hostname="bad-aspect-target")
    reservation = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )

    raised_priority = False
    try:
        scheduler_enqueue(
            db_session=session,
            reservation_id=reservation.reservation_id,
            pool_id=pool_id, project_id=PROJECT_UUID,
            aspects=SchedulerAspects(priority=999),
        )
    except SchedulerAspectsInvalidError as xcpt:
        raised_priority = True
        testbase.assert_equal("priority" in str(xcpt), True)
    testbase.assert_equal(raised_priority, True)

    raised_weight = False
    try:
        scheduler_enqueue(
            db_session=session,
            reservation_id=reservation.reservation_id,
            pool_id=pool_id, project_id=PROJECT_UUID,
            aspects=SchedulerAspects(fair_share_weight=0.0),
        )
    except SchedulerAspectsInvalidError as xcpt:
        raised_weight = True
        testbase.assert_equal("fair_share_weight" in str(xcpt), True)
    testbase.assert_equal(raised_weight, True)
    return


def test_scheduler_pick_next_returns_fifo_or_none():
    """
    **Feature: 4-reservation-scheduler (M1)**
    **Property: pick_next_for_pool returns the earliest-enqueued
    QUEUED entry; a pool with no queued entries returns None.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    pool_id = _seed_pool_with_one_member(session=session)

    # Empty pool → None.
    testbase.assert_equal(
        scheduler_pick_next(db_session=session, pool_id=pool_id) is None,
        True,
    )

    # Two queued entries — first one in is first one out.
    res_a = _new_resource(session=session, hostname="fifo-q-a")
    res_b = _new_resource(session=session, hostname="fifo-q-b")
    rsv_a = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_a,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )
    rsv_b = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_b,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )
    entry_a = scheduler_enqueue(
        db_session=session, reservation_id=rsv_a.reservation_id,
        pool_id=pool_id, project_id=PROJECT_UUID,
    )
    scheduler_enqueue(
        db_session=session, reservation_id=rsv_b.reservation_id,
        pool_id=pool_id, project_id=PROJECT_UUID,
    )
    next_entry = scheduler_pick_next(db_session=session, pool_id=pool_id)
    testbase.assert_equal(next_entry is not None, True)
    testbase.assert_equal(next_entry.entry_id, entry_a.entry_id)
    return


def test_scheduler_cancel_transitions_and_emits():
    """
    **Feature: 4-reservation-scheduler (M1)**
    **Property: cancel transitions QUEUED → CANCELLED, emits
    pychestrate.scheduler.cancelled, removes the entry from the
    queue head, and is idempotent on a second call.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=SchedulerEventTopics.CANCELLED,
        subscriber=lambda e: received.append(e),
    )

    pool_id = _seed_pool_with_one_member(session=session)
    res_id = _new_resource(session=session, hostname="cancel-target")
    reservation = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )
    scheduler_enqueue(
        db_session=session, reservation_id=reservation.reservation_id,
        pool_id=pool_id, project_id=PROJECT_UUID,
    )
    cancelled = scheduler_cancel(
        db_session=session, reservation_id=reservation.reservation_id,
        actor=ACTOR_UUID,
    )
    testbase.assert_equal(cancelled.state, SchedulerEntryState.CANCELLED)
    testbase.assert_equal(cancelled.cancelled_at is not None, True)
    testbase.assert_equal(len(received), 1)
    # Cancelled entries are gone from the queued list.
    queued = scheduler_list_queued(db_session=session, pool_id=pool_id)
    testbase.assert_equal(len(queued), 0)

    # Idempotent second call.
    again = scheduler_cancel(
        db_session=session, reservation_id=reservation.reservation_id,
    )
    testbase.assert_equal(again.state, SchedulerEntryState.CANCELLED)
    testbase.assert_equal(len(received), 1)
    return


def test_scheduler_mark_dispatched_transitions_and_emits():
    """
    **Feature: 4-reservation-scheduler (M1)**
    **Property: mark_dispatched transitions QUEUED → DISPATCHED
    and emits pychestrate.scheduler.dispatched.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=SchedulerEventTopics.DISPATCHED,
        subscriber=lambda e: received.append(e),
    )

    pool_id = _seed_pool_with_one_member(session=session)
    res_id = _new_resource(session=session, hostname="dispatch-target")
    reservation = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )
    entry = scheduler_enqueue(
        db_session=session, reservation_id=reservation.reservation_id,
        pool_id=pool_id, project_id=PROJECT_UUID,
    )
    dispatched = scheduler_mark_dispatched(
        db_session=session, entry_id=entry.entry_id,
    )
    testbase.assert_equal(dispatched.state, SchedulerEntryState.DISPATCHED)
    testbase.assert_equal(dispatched.dispatched_at is not None, True)
    testbase.assert_equal(len(received), 1)

    # No longer queued.
    queued = scheduler_list_queued(db_session=session, pool_id=pool_id)
    testbase.assert_equal(len(queued), 0)
    return


def test_scheduler_get_entry_unknown_raises():
    """
    **Feature: 4-reservation-scheduler (M1)**
    **Property: get_entry on an unknown id raises
    SchedulerEntryNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        scheduler_get_entry(db_session=session, entry_id=new_uuid())
    except SchedulerEntryNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_scheduler_cancel_unknown_raises():
    """
    **Feature: 4-reservation-scheduler (M1)**
    **Property: cancel against a reservation with no entry raises
    SchedulerEntryNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        scheduler_cancel(db_session=session, reservation_id=new_uuid())
    except SchedulerEntryNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return
