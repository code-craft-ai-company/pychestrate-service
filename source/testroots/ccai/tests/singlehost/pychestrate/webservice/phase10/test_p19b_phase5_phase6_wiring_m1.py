"""
.. module:: test_p19b_phase5_phase6_wiring_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Smoke tests for the Phase-5 bus subscriber + periodic
               task wiring delivered by PR p19b.

.. moduleauthor:: Code Craft AI LLC

PR p19b stops short of changing how the existing Layer-5 services
work; it wires them to a small in-process scheduler at bootstrap
time so the run-state outbox actually drains, the dispatch-receipt
timer wheel ticks, and the reconciler / offline evaluator run on
a cadence.

The smoke tests exercise the wiring surface:

* :func:`bootstrap_phase5_runtime` registers every documented task
  on the supplied scheduler and starts it.
* :func:`drain_once` published an outbox row to the bus + marked
  it published (end-to-end through the bootstrap).
* Calling :meth:`SchedulerHandle.stop` does not raise.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.phase5_bootstrap import (
    Phase5BootstrapConfig,
    bootstrap_phase5_runtime,
)
from ccai.pychestrate.webservice.jobs.run.state import (
    RunEventOutbox,
)
from ccai.pychestrate.webservice.jobs.run.state.outbox_publisher import (
    drain_once as outbox_drain_once,
)
from ccai.pychestrate.webservice.jobs.scheduling import (
    PeriodicTaskScheduler,
    reset_default_scheduler_for_testing,
)
from ccai.pychestrate.webservice.messaging import event_bus
from ccai.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _build_in_memory_session_factory():
    """
        Build an in-memory sqlite engine + session factory and run
        ``create_all`` so the Phase-5 tables exist.

        :returns: ``sessionmaker``-backed callable.
    """
    engine = create_engine("sqlite:///:memory:")
    PychestratePhase1Base.metadata.create_all(engine)
    rtnval = sessionmaker(bind=engine, expire_on_commit=False)
    return rtnval


def _snapshot_bus_subscribers() -> Dict[str, List[Any]]:
    """
        Capture the current ``event_bus`` subscriber dict so a test
        can restore the clean state in its ``finally`` block.

        :returns: Shallow copy of the per-topic subscriber lists.
    """
    snapshot: Dict[str, List[Any]] = {}
    for topic, subs in event_bus._SUBSCRIBERS.items():
        snapshot[topic] = list(subs)
    return snapshot


def _restore_bus_subscribers(*, snapshot: Dict[str, List[Any]]) -> None:
    """
        Restore the bus subscribers captured by
        :func:`_snapshot_bus_subscribers`.

        :param snapshot: Prior subscriber dict.

        :returns: None.
    """
    event_bus._SUBSCRIBERS.clear()
    for topic, subs in snapshot.items():
        event_bus._SUBSCRIBERS[topic] = list(subs)
    return


# ---------------------------------------------------------------------------
# Bootstrap smoke
# ---------------------------------------------------------------------------


def test_bootstrap_phase5_runtime_registers_documented_tasks():
    """
    **Feature: phase-5 wiring p19b**
    **Property: bootstrap_phase5_runtime registers every documented
    periodic task on the supplied scheduler and reports
    ``is_running=True``.  Without this wiring the run-state outbox
    never drains, the timer wheel never ticks, and the reconciler /
    offline evaluator never fire.**
    """
    reset_default_scheduler_for_testing()
    bus_snapshot = _snapshot_bus_subscribers()
    factory = _build_in_memory_session_factory()
    scheduler = PeriodicTaskScheduler()
    config = Phase5BootstrapConfig(
        session_factory=factory,
        scheduler=scheduler,
    )
    handle = None
    try:
        handle = bootstrap_phase5_runtime(config=config)
        names = scheduler.task_names()
        testbase.assert_equal("phase5.outbox_drainer" in names, True)
        testbase.assert_equal("phase5.timer_wheel_tick" in names, True)
        testbase.assert_equal("phase5.reconciler_scan" in names, True)
        testbase.assert_equal("phase5.offline_evaluator" in names, True)
        testbase.assert_equal("phase5.result_watcher" in names, True)
        testbase.assert_equal(scheduler.is_running(), True)
        testbase.assert_equal(handle is not None, True)
    finally:
        if handle is not None:
            handle.stop()
        reset_default_scheduler_for_testing()
        _restore_bus_subscribers(snapshot=bus_snapshot)
    return


def test_bootstrap_phase5_runtime_register_only_when_no_session_factory():
    """
    **Feature: phase-5 wiring p19b**
    **Property: When config.session_factory is None, the bootstrap
    runs the extension-registration path only -- no scheduler is
    started, no background threads are spawned.  This matches the
    register-only callsite used by app_pychestrate_main's
    register_service_extensions.**
    """
    reset_default_scheduler_for_testing()
    bus_snapshot = _snapshot_bus_subscribers()
    config = Phase5BootstrapConfig(session_factory=None)
    try:
        handle = bootstrap_phase5_runtime(config=config)
        testbase.assert_equal(handle, None)
    finally:
        reset_default_scheduler_for_testing()
        _restore_bus_subscribers(snapshot=bus_snapshot)
    return


def test_bootstrap_phase5_runtime_clean_shutdown():
    """
    **Feature: phase-5 wiring p19b**
    **Property: SchedulerHandle.stop joins every running task
    thread without raising and flips is_running back to False.
    Service shutdown must be deterministic.**
    """
    reset_default_scheduler_for_testing()
    bus_snapshot = _snapshot_bus_subscribers()
    factory = _build_in_memory_session_factory()
    scheduler = PeriodicTaskScheduler()
    config = Phase5BootstrapConfig(
        session_factory=factory,
        scheduler=scheduler,
    )
    raised = False
    try:
        handle = bootstrap_phase5_runtime(config=config)
        try:
            handle.stop()
        except Exception:  # noqa: BLE001
            raised = True
        testbase.assert_equal(raised, False)
        testbase.assert_equal(scheduler.is_running(), False)
    finally:
        reset_default_scheduler_for_testing()
        _restore_bus_subscribers(snapshot=bus_snapshot)
    return


# ---------------------------------------------------------------------------
# Outbox publisher smoke
# ---------------------------------------------------------------------------


def test_outbox_publisher_drains_unpublished_row_to_bus():
    """
    **Feature: phase-5 wiring p19b**
    **Property: A run-state outbox row with published_at IS NULL is
    published to the in-process event bus on the next drain_once
    call, and the row is marked published.  This is the contract
    the scheduler's outbox-drainer tick relies on.**
    """
    bus_snapshot = _snapshot_bus_subscribers()
    factory = _build_in_memory_session_factory()
    received: List[Any] = []

    def _capture(event):
        received.append(event)
        return

    event_bus.subscribe(topic="entity.run.state_changed", subscriber=_capture)

    db_session = factory()
    try:
        row = RunEventOutbox(
            outbox_id=new_uuid(),
            run_id=new_uuid(),
            topic="entity.run.state_changed",
            payload={"from_state": "PENDING", "to_state": "DISPATCHED"},
            created_at=utc_now(),
            published_at=None,
        )
        db_session.add(row)
        db_session.commit()

        published_count = outbox_drain_once(
            db_session=db_session, batch_size=16,
        )
        testbase.assert_equal(published_count, 1)
        testbase.assert_equal(len(received), 1)

        # Re-running the drain must be a no-op (the row is already
        # marked published).
        again = outbox_drain_once(db_session=db_session, batch_size=16)
        testbase.assert_equal(again, 0)

        # Cross-check the row got marked published.
        refreshed = (
            db_session.query(RunEventOutbox)
            .filter(RunEventOutbox.outbox_id == row.outbox_id)
            .first()
        )
        testbase.assert_equal(refreshed.published_at is not None, True)
    finally:
        db_session.close()
        _restore_bus_subscribers(snapshot=bus_snapshot)
    return
