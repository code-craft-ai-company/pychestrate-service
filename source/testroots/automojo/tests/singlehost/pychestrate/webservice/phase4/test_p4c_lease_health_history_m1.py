"""
.. module:: test_p4c_lease_health_history_m1
    :synopsis: Tests for P4c — 4-lease-heartbeat + 4-resource-health
               + 4-usage-history M1.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import timedelta
from typing import List

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from automojo.pychestrate.webservice.resources.checkout import (
    ReservationMode,
    reserve,
)
from automojo.pychestrate.webservice.resources.conflict import (
    register_builtin_extensions as conflict_register,
)
from automojo.pychestrate.webservice.resources.health import (
    HealthEventTopics,
    HealthRecordConflictError,
    HealthRecordNotFoundError,
    ProbeOutcome,
    ProbeResult,
    drop_health_record,
    get_health_record,
    list_due_for_probe,
    record_probe_outcome,
    seed_health_record,
)
from automojo.pychestrate.webservice.resources.inventory import (
    register_builtin_extensions as inventory_register,
    register_resource,
)
from automojo.pychestrate.webservice.resources.lease import (
    LeaseAspects,
    LeaseAspectsInvalidError,
    LeaseEventTopics,
    LeaseNotFoundError,
    LeaseState,
    LeaseStateError,
    attach_lease,
    get_lease_for_reservation,
    heartbeat,
    release_lease,
    sweep_expired,
)
from automojo.pychestrate.webservice.resources.usage_history import (
    UsageEventType,
    UsageHistoryEventTopics,
    append_event,
    get_event,
    list_timeline,
)
from automojo.pychestrate.webservice.resources.usage_history.errors import (
    TimelineEventNotFoundError,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-0000000000c4"
ACTOR_UUID = "00000000-0000-4000-8000-0000000000c5"


def _prepare_runtime() -> None:
    """
        Reset cross-test globals + seed the inventory + conflict
        registrations needed by the integration tests.
    """
    reset_registry_for_testing()
    reset_event_bus()
    inventory_register()
    conflict_register()
    return


def _new_resource(*, session, hostname: str) -> str:
    view = register_resource(
        db_session=session,
        project_id=PROJECT_UUID,
        kind="device",
        display_name=hostname,
        attributes={"hostname": hostname},
    )
    rtnval = view.resource_id
    return rtnval


def _grant_reservation(*, session, hostname: str) -> str:
    """
        Helper: register a fresh resource and exclusively grant
        a reservation against it.
    """
    res_id = _new_resource(session=session, hostname=hostname)
    view = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )
    rtnval = view.reservation_id
    return rtnval


# -------------------------------------
# 4-lease-heartbeat tests
# -------------------------------------

def test_attach_lease_persists_active_and_emits():
    """
    **Feature: 4-lease-heartbeat (M1)**
    **Property: attach_lease persists an ACTIVE row, sets
    expires_at = attached_at + ttl, and emits
    entity.lease.attached.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=LeaseEventTopics.ATTACHED,
        subscriber=lambda e: received.append(e),
    )

    res_id = _new_resource(session=session, hostname="lease-target")
    rsv = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )
    view = attach_lease(
        db_session=session,
        reservation_id=rsv.reservation_id,
        project_id=PROJECT_UUID,
        resource_id=res_id,
        aspects=LeaseAspects(ttl_seconds=120),
    )
    testbase.assert_equal(view.state, LeaseState.ACTIVE)
    testbase.assert_equal(view.ttl_seconds, 120)
    testbase.assert_equal(view.heartbeat_count, 0)
    delta = (view.expires_at - view.attached_at).total_seconds()
    testbase.assert_equal(int(delta), 120)
    testbase.assert_equal(len(received), 1)
    return


def test_attach_lease_idempotent_when_active():
    """
    **Feature: 4-lease-heartbeat (M1)**
    **Property: attach_lease returns the existing view when one
    is already ACTIVE for the reservation.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=LeaseEventTopics.ATTACHED,
        subscriber=lambda e: received.append(e),
    )

    res_id = _new_resource(session=session, hostname="dup-attach")
    rsv = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )
    first = attach_lease(
        db_session=session, reservation_id=rsv.reservation_id,
        project_id=PROJECT_UUID, resource_id=res_id,
    )
    second = attach_lease(
        db_session=session, reservation_id=rsv.reservation_id,
        project_id=PROJECT_UUID, resource_id=res_id,
    )
    testbase.assert_equal(first.lease_id, second.lease_id)
    testbase.assert_equal(len(received), 1)
    return


def test_attach_lease_invalid_ttl_raises():
    """
    **Feature: 4-lease-heartbeat (M1)**
    **Property: a TTL outside [10, 3600] raises
    LeaseAspectsInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    res_id = _new_resource(session=session, hostname="bad-ttl")
    rsv = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )

    raised_low = False
    try:
        attach_lease(
            db_session=session, reservation_id=rsv.reservation_id,
            project_id=PROJECT_UUID, resource_id=res_id,
            aspects=LeaseAspects(ttl_seconds=2),
        )
    except LeaseAspectsInvalidError as xcpt:
        raised_low = True
        testbase.assert_equal("ttl_seconds" in str(xcpt), True)
    testbase.assert_equal(raised_low, True)

    raised_high = False
    try:
        attach_lease(
            db_session=session, reservation_id=rsv.reservation_id,
            project_id=PROJECT_UUID, resource_id=res_id,
            aspects=LeaseAspects(ttl_seconds=99999),
        )
    except LeaseAspectsInvalidError:
        raised_high = True
    testbase.assert_equal(raised_high, True)
    return


def test_heartbeat_renews_expires_and_emits():
    """
    **Feature: 4-lease-heartbeat (M1)**
    **Property: heartbeat advances expires_at, increments
    heartbeat_count, and emits entity.lease.renewed.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=LeaseEventTopics.RENEWED,
        subscriber=lambda e: received.append(e),
    )

    res_id = _new_resource(session=session, hostname="hb-target")
    rsv = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )
    initial = attach_lease(
        db_session=session, reservation_id=rsv.reservation_id,
        project_id=PROJECT_UUID, resource_id=res_id,
        aspects=LeaseAspects(ttl_seconds=30),
    )
    renewed = heartbeat(
        db_session=session, reservation_id=rsv.reservation_id,
    )
    testbase.assert_equal(renewed.heartbeat_count, 1)
    testbase.assert_equal(renewed.expires_at >= initial.expires_at, True)
    testbase.assert_equal(len(received), 1)
    return


def test_release_lease_closes_and_emits():
    """
    **Feature: 4-lease-heartbeat (M1)**
    **Property: release_lease flips ACTIVE → RELEASED, sets
    closed_at + close_reason, and emits entity.lease.released.
    Idempotent on already-released.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=LeaseEventTopics.RELEASED,
        subscriber=lambda e: received.append(e),
    )

    res_id = _new_resource(session=session, hostname="release-target")
    rsv = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )
    attach_lease(
        db_session=session, reservation_id=rsv.reservation_id,
        project_id=PROJECT_UUID, resource_id=res_id,
    )
    closed = release_lease(
        db_session=session, reservation_id=rsv.reservation_id,
        reason="released",
    )
    testbase.assert_equal(closed.state, LeaseState.RELEASED)
    testbase.assert_equal(closed.close_reason, "released")
    testbase.assert_equal(len(received), 1)

    again = release_lease(
        db_session=session, reservation_id=rsv.reservation_id,
    )
    testbase.assert_equal(again.state, LeaseState.RELEASED)
    testbase.assert_equal(len(received), 1)
    return


def test_heartbeat_against_closed_lease_raises():
    """
    **Feature: 4-lease-heartbeat (M1)**
    **Property: heartbeat against a closed lease raises
    LeaseStateError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    res_id = _new_resource(session=session, hostname="closed-hb")
    rsv = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_id,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )
    attach_lease(
        db_session=session, reservation_id=rsv.reservation_id,
        project_id=PROJECT_UUID, resource_id=res_id,
    )
    release_lease(
        db_session=session, reservation_id=rsv.reservation_id,
    )

    raised = False
    try:
        heartbeat(
            db_session=session, reservation_id=rsv.reservation_id,
        )
    except LeaseStateError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_sweep_expired_closes_overdue_leases():
    """
    **Feature: 4-lease-heartbeat (M1)**
    **Property: sweep_expired closes every ACTIVE lease whose
    expires_at <= when, emits entity.lease.expired with
    reason=lease_lost, and leaves not-yet-expired leases
    untouched.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=LeaseEventTopics.EXPIRED,
        subscriber=lambda e: received.append(e),
    )

    res_a = _new_resource(session=session, hostname="sweep-a")
    res_b = _new_resource(session=session, hostname="sweep-b")
    rsv_a = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_a,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )
    rsv_b = reserve(
        db_session=session, project_id=PROJECT_UUID, resource_id=res_b,
        requested_by=ACTOR_UUID, mode=ReservationMode.EXCLUSIVE,
    )
    lease_a = attach_lease(
        db_session=session, reservation_id=rsv_a.reservation_id,
        project_id=PROJECT_UUID, resource_id=res_a,
        aspects=LeaseAspects(ttl_seconds=10),
    )
    attach_lease(
        db_session=session, reservation_id=rsv_b.reservation_id,
        project_id=PROJECT_UUID, resource_id=res_b,
        aspects=LeaseAspects(ttl_seconds=600),
    )

    # Sweep at lease_a.expires_at + 1s — only A should close.
    cutoff = lease_a.expires_at + timedelta(seconds=1)
    closed = sweep_expired(db_session=session, when=cutoff)
    testbase.assert_equal(len(closed), 1)
    testbase.assert_equal(closed[0].reservation_id, rsv_a.reservation_id)
    testbase.assert_equal(closed[0].state, LeaseState.EXPIRED)
    testbase.assert_equal(closed[0].close_reason, "lease_lost")
    testbase.assert_equal(len(received), 1)

    # B is still ACTIVE.
    b_view = get_lease_for_reservation(
        db_session=session, reservation_id=rsv_b.reservation_id,
    )
    testbase.assert_equal(b_view.state, LeaseState.ACTIVE)
    return


def test_get_lease_for_unknown_raises():
    """
    **Feature: 4-lease-heartbeat (M1)**
    **Property: get_lease_for_reservation on a reservation with
    no lease raises LeaseNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_lease_for_reservation(
            db_session=session, reservation_id=new_uuid(),
        )
    except LeaseNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# 4-resource-health tests
# -------------------------------------

def test_seed_health_record_persists_and_emits():
    """
    **Feature: 4-resource-health (M1)**
    **Property: seed_health_record creates a row in UNKNOWN with
    zero counters, schedules next_probe_at, and emits
    entity.resource.health.seeded.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=HealthEventTopics.SEEDED,
        subscriber=lambda e: received.append(e),
    )

    res_id = _new_resource(session=session, hostname="seed-host")
    view = seed_health_record(
        db_session=session, resource_id=res_id, project_id=PROJECT_UUID,
        probe_period_seconds=30,
    )
    testbase.assert_equal(view.last_outcome, ProbeOutcome.UNKNOWN)
    testbase.assert_equal(view.pass_count, 0)
    testbase.assert_equal(view.fail_count, 0)
    testbase.assert_equal(view.consecutive_failures, 0)
    testbase.assert_equal(view.probe_period_seconds, 30)
    testbase.assert_equal(len(received), 1)
    return


def test_seed_health_record_idempotent_same_probe():
    """
    **Feature: 4-resource-health (M1)**
    **Property: seeding the same resource with the same probe is
    idempotent; seeding with a different probe raises
    HealthRecordConflictError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    res_id = _new_resource(session=session, hostname="reseed-host")
    first = seed_health_record(
        db_session=session, resource_id=res_id, project_id=PROJECT_UUID,
    )
    second = seed_health_record(
        db_session=session, resource_id=res_id, project_id=PROJECT_UUID,
    )
    testbase.assert_equal(first.health_id, second.health_id)

    raised = False
    try:
        seed_health_record(
            db_session=session, resource_id=res_id, project_id=PROJECT_UUID,
            probe_name="custom-probe",
        )
    except HealthRecordConflictError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_record_probe_outcome_updates_counters_and_emits():
    """
    **Feature: 4-resource-health (M1)**
    **Property: a PASS resets consecutive_failures and bumps
    pass_count + last_pass_at; a FAIL increments
    consecutive_failures + last_fail_at; both advance
    next_probe_at; both emit entity.resource.health.probed.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=HealthEventTopics.PROBED,
        subscriber=lambda e: received.append(e),
    )

    res_id = _new_resource(session=session, hostname="probe-host")
    seed_health_record(
        db_session=session, resource_id=res_id, project_id=PROJECT_UUID,
        probe_period_seconds=15,
    )

    after_fail = record_probe_outcome(
        db_session=session, resource_id=res_id,
        result=ProbeResult(
            outcome=ProbeOutcome.FAIL,
            error="ping timeout",
            payload={"rtt_ms": None},
        ),
    )
    testbase.assert_equal(after_fail.fail_count, 1)
    testbase.assert_equal(after_fail.consecutive_failures, 1)
    testbase.assert_equal(after_fail.last_outcome, ProbeOutcome.FAIL)
    testbase.assert_equal(after_fail.last_error, "ping timeout")

    after_fail_2 = record_probe_outcome(
        db_session=session, resource_id=res_id,
        result=ProbeResult(outcome=ProbeOutcome.FAIL),
    )
    testbase.assert_equal(after_fail_2.consecutive_failures, 2)

    after_pass = record_probe_outcome(
        db_session=session, resource_id=res_id,
        result=ProbeResult(
            outcome=ProbeOutcome.PASS,
            payload={"rtt_ms": 1.2},
        ),
    )
    testbase.assert_equal(after_pass.pass_count, 1)
    testbase.assert_equal(after_pass.consecutive_failures, 0)
    testbase.assert_equal(after_pass.last_outcome, ProbeOutcome.PASS)
    testbase.assert_equal(len(received), 3)
    return


def test_list_due_for_probe_returns_only_due_rows():
    """
    **Feature: 4-resource-health (M1)**
    **Property: list_due_for_probe returns only rows whose
    next_probe_at <= when, ordered ascending.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    res_id = _new_resource(session=session, hostname="due-host")
    view = seed_health_record(
        db_session=session, resource_id=res_id, project_id=PROJECT_UUID,
        probe_period_seconds=60,
    )

    # Sweep BEFORE the next probe → no rows due.
    early = list_due_for_probe(
        db_session=session, when=view.next_probe_at - timedelta(seconds=1),
    )
    testbase.assert_equal(len(early), 0)

    # Sweep AT the next probe → row is due.
    at_due = list_due_for_probe(
        db_session=session, when=view.next_probe_at,
    )
    testbase.assert_equal(len(at_due), 1)
    testbase.assert_equal(at_due[0].health_id, view.health_id)
    return


def test_drop_health_record_removes_and_emits():
    """
    **Feature: 4-resource-health (M1)**
    **Property: drop_health_record deletes the row, emits
    entity.resource.health.dropped, and is idempotent on a
    missing row.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=HealthEventTopics.DROPPED,
        subscriber=lambda e: received.append(e),
    )

    res_id = _new_resource(session=session, hostname="drop-host")
    seed_health_record(
        db_session=session, resource_id=res_id, project_id=PROJECT_UUID,
    )
    drop_health_record(db_session=session, resource_id=res_id)
    drop_health_record(db_session=session, resource_id=res_id)  # idempotent

    raised = False
    try:
        get_health_record(db_session=session, resource_id=res_id)
    except HealthRecordNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    testbase.assert_equal(len(received), 1)
    return


def test_record_probe_outcome_unknown_resource_raises():
    """
    **Feature: 4-resource-health (M1)**
    **Property: record_probe_outcome against an unseeded
    resource raises HealthRecordNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        record_probe_outcome(
            db_session=session, resource_id=new_uuid(),
            result=ProbeResult(outcome=ProbeOutcome.PASS),
        )
    except HealthRecordNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# 4-usage-history tests
# -------------------------------------

def test_append_event_persists_and_emits():
    """
    **Feature: 4-usage-history (M1)**
    **Property: append_event persists a timeline row and emits
    pychestrate.resource.usage.appended.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_appended: List[EntityEvent] = []
    subscribe(
        topic=UsageHistoryEventTopics.APPENDED,
        subscriber=lambda e: received_appended.append(e),
    )

    res_id = _new_resource(session=session, hostname="timeline-host")
    src_id = new_uuid()
    view = append_event(
        db_session=session,
        source_event_id=src_id,
        resource_id=res_id,
        project_id=PROJECT_UUID,
        event_type=UsageEventType.RESOURCE_REGISTERED,
        actor_id=ACTOR_UUID,
        payload={"display_name": "timeline-host"},
    )
    testbase.assert_equal(view.event_type, UsageEventType.RESOURCE_REGISTERED)
    testbase.assert_equal(view.source_event_id, src_id)
    testbase.assert_equal(view.actor_id, ACTOR_UUID)
    testbase.assert_equal(len(received_appended), 1)
    return


def test_append_event_is_idempotent_per_source_resource():
    """
    **Feature: 4-usage-history (M1)**
    **Property: redelivering the same source_event_id +
    resource_id pair returns the existing row and emits the
    duplicate-suppressed diagnostic instead of re-inserting.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_appended: List[EntityEvent] = []
    received_suppressed: List[EntityEvent] = []
    subscribe(
        topic=UsageHistoryEventTopics.APPENDED,
        subscriber=lambda e: received_appended.append(e),
    )
    subscribe(
        topic=UsageHistoryEventTopics.DUPLICATE_SUPPRESSED,
        subscriber=lambda e: received_suppressed.append(e),
    )

    res_id = _new_resource(session=session, hostname="idem-host")
    src_id = new_uuid()
    first = append_event(
        db_session=session, source_event_id=src_id, resource_id=res_id,
        project_id=PROJECT_UUID,
        event_type=UsageEventType.RESERVATION_GRANTED,
    )
    second = append_event(
        db_session=session, source_event_id=src_id, resource_id=res_id,
        project_id=PROJECT_UUID,
        event_type=UsageEventType.RESERVATION_GRANTED,
    )
    testbase.assert_equal(first.event_id, second.event_id)
    testbase.assert_equal(len(received_appended), 1)
    testbase.assert_equal(len(received_suppressed), 1)
    return


def test_list_timeline_returns_newest_first():
    """
    **Feature: 4-usage-history (M1)**
    **Property: list_timeline returns rows ordered newest-first
    and respects the limit argument.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    res_id = _new_resource(session=session, hostname="order-host")
    base_ts = utc_now()
    older = append_event(
        db_session=session, source_event_id=new_uuid(),
        resource_id=res_id, project_id=PROJECT_UUID,
        event_type=UsageEventType.RESOURCE_REGISTERED,
        at_ts=base_ts - timedelta(seconds=60),
    )
    newer = append_event(
        db_session=session, source_event_id=new_uuid(),
        resource_id=res_id, project_id=PROJECT_UUID,
        event_type=UsageEventType.RESERVATION_GRANTED,
        at_ts=base_ts,
    )

    rows = list_timeline(
        db_session=session, resource_id=res_id, limit=10,
    )
    testbase.assert_equal(len(rows), 2)
    testbase.assert_equal(rows[0].event_id, newer.event_id)
    testbase.assert_equal(rows[1].event_id, older.event_id)

    capped = list_timeline(
        db_session=session, resource_id=res_id, limit=1,
    )
    testbase.assert_equal(len(capped), 1)
    testbase.assert_equal(capped[0].event_id, newer.event_id)
    return


def test_get_event_unknown_raises():
    """
    **Feature: 4-usage-history (M1)**
    **Property: get_event on an unknown id raises
    TimelineEventNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_event(db_session=session, event_id=new_uuid())
    except TimelineEventNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_pod_event_group_id_round_trips():
    """
    **Feature: 4-usage-history (M1)**
    **Property: pod_event_group_id and annotations round-trip
    through the read-model so the M2 pod-expansion +
    hook-pipeline can attach metadata without schema changes.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    res_id = _new_resource(session=session, hostname="pod-host")
    group_id = new_uuid()
    view = append_event(
        db_session=session, source_event_id=new_uuid(),
        resource_id=res_id, project_id=PROJECT_UUID,
        event_type=UsageEventType.RESERVATION_GRANTED,
        pod_event_group_id=group_id,
        annotations={"team": "platform", "cost_center": "R&D"},
    )
    testbase.assert_equal(view.pod_event_group_id, group_id)
    testbase.assert_equal(view.annotations["team"], "platform")
    testbase.assert_equal(view.annotations["cost_center"], "R&D")
    return
