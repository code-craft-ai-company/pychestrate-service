"""
.. module:: test_p12a_system_health_m1
    :synopsis: Tests for P12a — 0-system-health M1.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import threading
import time

from datetime import datetime, timezone
from typing import List

from automojo import testbase

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.extensions.registry import (
    list_resource_extensions,
    reset_registry_for_testing,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from automojo.pychestrate.webservice.system_health import (
    DuplicateProbeError,
    HealthConfig,
    HealthRegistry,
    HealthScheduler,
    HealthSnapshot,
    OverallStatus,
    PostgresHealthProbe,
    ProbeKind,
    ProbeNotFoundError,
    ProbeResult,
    ProbeStatus,
    SystemHealthEventTopics,
    SystemHealthProbeExtension,
    evaluate_transitions,
    register_builtin_extensions as system_health_register,
    reset_aggregator_for_testing,
    reset_postgres_probe_for_testing,
    run_probe_now,
    set_db_session_factory,
)
from automojo.pychestrate.webservice.system_health.registry import (
    truncate_last_error,
    LAST_ERROR_MAX_CHARS,
)


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    reset_aggregator_for_testing()
    reset_postgres_probe_for_testing()
    return


def _ok_probe() -> ProbeResult:
    rtnval = ProbeResult(
        status=ProbeStatus.OK,
        duration_ms=1.0,
        observed_at=datetime.now(tz=timezone.utc),
    )
    return rtnval


def _fail_probe() -> ProbeResult:
    rtnval = ProbeResult(
        status=ProbeStatus.FAIL,
        duration_ms=1.0,
        observed_at=datetime.now(tz=timezone.utc),
        last_error="simulated_failure",
    )
    return rtnval


def _slow_probe() -> ProbeResult:
    time.sleep(2.0)
    rtnval = ProbeResult(
        status=ProbeStatus.OK,
        duration_ms=2000.0,
        observed_at=datetime.now(tz=timezone.utc),
    )
    return rtnval


def _raising_probe() -> ProbeResult:
    raise RuntimeError("boom")


# -------------------------------------
# HealthRegistry primitives
# -------------------------------------

def test_register_probe_adds_record():
    """
    **Feature: 0-system-health (M1)**
    **Property: register_probe stores a ProbeRecord; list_probes
    returns rows in registration order.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    registry.register_probe(
        name="alpha", kind=ProbeKind.READINESS, probe=_ok_probe,
        interval_seconds=1.0, timeout_seconds=0.5,
    )
    registry.register_probe(
        name="beta", kind=ProbeKind.LIVENESS, probe=_ok_probe,
        interval_seconds=2.0, timeout_seconds=0.5,
    )
    rows = registry.list_probes()
    testbase.assert_equal([r.name for r in rows], ["alpha", "beta"])
    return


def test_register_probe_duplicate_name_raises():
    """
    **Feature: 0-system-health (M1)**
    **Property: registering the same probe name twice raises
    DuplicateProbeError.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    registry.register_probe(
        name="dup", kind=ProbeKind.LIVENESS, probe=_ok_probe,
        interval_seconds=1.0, timeout_seconds=0.5,
    )
    raised = False
    try:
        registry.register_probe(
            name="dup", kind=ProbeKind.LIVENESS, probe=_ok_probe,
            interval_seconds=1.0, timeout_seconds=0.5,
        )
    except DuplicateProbeError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_register_probe_rejects_non_positive_intervals():
    """
    **Feature: 0-system-health (M1)**
    **Property: zero / negative interval_seconds or
    timeout_seconds raise ValueError.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    raised_count = 0
    for kwargs in (
        {"interval_seconds": 0.0, "timeout_seconds": 1.0},
        {"interval_seconds": 1.0, "timeout_seconds": 0.0},
        {"interval_seconds": -1.0, "timeout_seconds": 1.0},
    ):
        try:
            registry.register_probe(
                name="x", kind=ProbeKind.LIVENESS, probe=_ok_probe,
                **kwargs,
            )
        except ValueError:
            raised_count = raised_count + 1
    testbase.assert_equal(raised_count, 3)
    return


def test_unregister_probe_idempotent():
    """
    **Feature: 0-system-health (M1)**
    **Property: unregister_probe returns True on first call,
    False thereafter.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    registry.register_probe(
        name="probe", kind=ProbeKind.LIVENESS, probe=_ok_probe,
        interval_seconds=1.0, timeout_seconds=0.5,
    )
    testbase.assert_equal(
        registry.unregister_probe(name="probe"), True,
    )
    testbase.assert_equal(
        registry.unregister_probe(name="probe"), False,
    )
    return


def test_get_probe_unknown_raises():
    """
    **Feature: 0-system-health (M1)**
    **Property: get_probe on a missing name raises
    ProbeNotFoundError.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    raised = False
    try:
        registry.get_probe(name="ghost")
    except ProbeNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_truncate_last_error_caps_length():
    """
    **Feature: 0-system-health (M1)**
    **Property: truncate_last_error caps the message at
    LAST_ERROR_MAX_CHARS.**
    """
    _prepare_runtime()
    big = "x" * (LAST_ERROR_MAX_CHARS + 100)
    capped = truncate_last_error(message=big)
    testbase.assert_equal(len(capped), LAST_ERROR_MAX_CHARS)
    testbase.assert_equal(truncate_last_error(message=None), None)
    return


# -------------------------------------
# Snapshot computation
# -------------------------------------

def test_snapshot_overall_ok_when_every_probe_ok():
    """
    **Feature: 0-system-health (M1)**
    **Property: a registry where every probe has OK results
    snapshots as OverallStatus.OK.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    registry.register_probe(
        name="r1", kind=ProbeKind.READINESS, probe=_ok_probe,
        interval_seconds=1.0, timeout_seconds=0.5,
    )
    registry.register_probe(
        name="i1", kind=ProbeKind.INFORMATIONAL, probe=_ok_probe,
        interval_seconds=1.0, timeout_seconds=0.5,
    )
    run_probe_now(registry=registry, name="r1")
    run_probe_now(registry=registry, name="i1")
    snapshot = registry.snapshot()
    testbase.assert_equal(snapshot.overall, OverallStatus.OK)
    testbase.assert_equal(snapshot.failing_readiness_probes, ())
    return


def test_snapshot_overall_failing_when_readiness_fails():
    """
    **Feature: 0-system-health (M1)**
    **Property: a failing readiness probe drives overall to
    FAILING and lists the probe in failing_readiness_probes.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    registry.register_probe(
        name="r1", kind=ProbeKind.READINESS, probe=_fail_probe,
        interval_seconds=1.0, timeout_seconds=0.5,
    )
    registry.register_probe(
        name="r2", kind=ProbeKind.READINESS, probe=_ok_probe,
        interval_seconds=1.0, timeout_seconds=0.5,
    )
    run_probe_now(registry=registry, name="r1")
    run_probe_now(registry=registry, name="r2")
    snapshot = registry.snapshot()
    testbase.assert_equal(snapshot.overall, OverallStatus.FAILING)
    testbase.assert_equal(snapshot.failing_readiness_probes, ("r1",))
    return


def test_snapshot_overall_degraded_when_only_non_readiness_fails():
    """
    **Feature: 0-system-health (M1)**
    **Property: a failing informational / liveness probe with
    healthy readiness drives overall to DEGRADED.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    registry.register_probe(
        name="r1", kind=ProbeKind.READINESS, probe=_ok_probe,
        interval_seconds=1.0, timeout_seconds=0.5,
    )
    registry.register_probe(
        name="i1", kind=ProbeKind.INFORMATIONAL, probe=_fail_probe,
        interval_seconds=1.0, timeout_seconds=0.5,
    )
    run_probe_now(registry=registry, name="r1")
    run_probe_now(registry=registry, name="i1")
    snapshot = registry.snapshot()
    testbase.assert_equal(snapshot.overall, OverallStatus.DEGRADED)
    testbase.assert_equal(snapshot.failing_readiness_probes, ())
    return


# -------------------------------------
# run_probe_now + scheduler
# -------------------------------------

def test_run_probe_now_records_result():
    """
    **Feature: 0-system-health (M1)**
    **Property: run_probe_now writes the probe's result back
    to the registry and clears in_flight.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    registry.register_probe(
        name="alpha", kind=ProbeKind.LIVENESS, probe=_ok_probe,
        interval_seconds=1.0, timeout_seconds=0.5,
    )
    result = run_probe_now(registry=registry, name="alpha")
    testbase.assert_equal(result.status, ProbeStatus.OK)
    record = registry.get_probe(name="alpha")
    testbase.assert_equal(record.last_result.status, ProbeStatus.OK)
    testbase.assert_equal(record.in_flight, False)
    return


def test_run_probe_now_catches_raised_exception():
    """
    **Feature: 0-system-health (M1)**
    **Property: a probe that raises records FAIL with the
    exception class + message in last_error.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    registry.register_probe(
        name="raises", kind=ProbeKind.LIVENESS, probe=_raising_probe,
        interval_seconds=1.0, timeout_seconds=0.5,
    )
    result = run_probe_now(registry=registry, name="raises")
    testbase.assert_equal(result.status, ProbeStatus.FAIL)
    testbase.assert_equal("RuntimeError" in result.last_error, True)
    return


def test_scheduler_tick_runs_every_probe_once():
    """
    **Feature: 0-system-health (M1)**
    **Property: HealthScheduler.tick invokes every registered
    probe via the executor and stamps results.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    for i in range(3):
        registry.register_probe(
            name="p{}".format(i),
            kind=ProbeKind.LIVENESS,
            probe=_ok_probe,
            interval_seconds=1.0,
            timeout_seconds=0.5,
        )
    scheduler = HealthScheduler(
        registry=registry, config=HealthConfig(probe_worker_count=2),
    )
    scheduler.start()
    try:
        attempted = scheduler.tick()
    finally:
        scheduler.stop()
    testbase.assert_equal(attempted, 3)
    rows = registry.list_probes()
    for record in rows:
        testbase.assert_equal(record.last_result.status, ProbeStatus.OK)
    return


def test_scheduler_tick_enforces_timeout():
    """
    **Feature: 0-system-health (M1)**
    **Property: a probe that exceeds its timeout records FAIL
    with last_error='probe timeout'.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    registry.register_probe(
        name="slow", kind=ProbeKind.LIVENESS, probe=_slow_probe,
        interval_seconds=10.0, timeout_seconds=0.3,
    )
    scheduler = HealthScheduler(
        registry=registry, config=HealthConfig(probe_worker_count=2),
    )
    scheduler.start()
    try:
        scheduler.tick()
    finally:
        scheduler.stop()
    record = registry.get_probe(name="slow")
    testbase.assert_equal(record.last_result.status, ProbeStatus.FAIL)
    testbase.assert_equal(
        record.last_result.last_error, "probe timeout",
    )
    return


def test_scheduler_double_start_raises():
    """
    **Feature: 0-system-health (M1)**
    **Property: HealthScheduler.start raises SemanticError on
    a second call.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    scheduler = HealthScheduler(
        registry=registry, config=HealthConfig(probe_worker_count=1),
    )
    scheduler.start()
    raised = False
    try:
        scheduler.start()
    except SemanticError:
        raised = True
    finally:
        scheduler.stop()
    testbase.assert_equal(raised, True)
    return


def test_scheduler_stop_is_idempotent():
    """
    **Feature: 0-system-health (M1)**
    **Property: stop() can be called twice without error.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    scheduler = HealthScheduler(
        registry=registry, config=HealthConfig(probe_worker_count=1),
    )
    scheduler.start()
    scheduler.stop()
    scheduler.stop()
    testbase.assert_equal(scheduler.is_running(), False)
    return


# -------------------------------------
# PostgresHealthProbe
# -------------------------------------

def test_postgres_probe_unknown_when_factory_not_installed():
    """
    **Feature: 0-system-health (M1)**
    **Property: PostgresHealthProbe.run_probe returns UNKNOWN
    when no session factory has been installed.**
    """
    _prepare_runtime()
    result = PostgresHealthProbe.run_probe()
    testbase.assert_equal(result.status, ProbeStatus.UNKNOWN)
    testbase.assert_equal(
        result.last_error, "db_session_factory_not_installed",
    )
    return


def test_postgres_probe_ok_with_in_memory_engine():
    """
    **Feature: 0-system-health (M1)**
    **Property: PostgresHealthProbe.run_probe returns OK when
    the installed session factory is reachable.**
    """
    _prepare_runtime()
    import sqlalchemy as sa
    from sqlalchemy.orm import sessionmaker

    engine = sa.create_engine("sqlite://")
    factory = sessionmaker(bind=engine)
    set_db_session_factory(factory=factory)
    try:
        result = PostgresHealthProbe.run_probe()
        testbase.assert_equal(result.status, ProbeStatus.OK)
    finally:
        set_db_session_factory(factory=None)
    return


# -------------------------------------
# Aggregator transitions
# -------------------------------------

def test_aggregator_emits_overall_changed_on_transition():
    """
    **Feature: 0-system-health (M1)**
    **Property: evaluate_transitions emits
    OVERALL_CHANGED when the aggregate verdict flips between
    cycles.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    registry.register_probe(
        name="r1", kind=ProbeKind.READINESS, probe=_ok_probe,
        interval_seconds=1.0, timeout_seconds=0.5,
    )
    received: List[EntityEvent] = []
    subscribe(
        topic=SystemHealthEventTopics.OVERALL_CHANGED,
        subscriber=lambda e: received.append(e),
    )

    run_probe_now(registry=registry, name="r1")
    evaluate_transitions(registry=registry)

    # Swap probe to fail, run again, expect overall transition emit.
    registry._probes["r1"].probe = _fail_probe
    run_probe_now(registry=registry, name="r1")
    evaluate_transitions(registry=registry)
    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(received[0].payload["from"], "ok")
    testbase.assert_equal(received[0].payload["to"], "failing")
    return


def test_aggregator_emits_per_probe_failed_and_recovered():
    """
    **Feature: 0-system-health (M1)**
    **Property: evaluate_transitions emits PROBE_FAILED on a
    per-probe ok→fail transition and PROBE_RECOVERED on the
    fail→ok transition.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    registry.register_probe(
        name="r1", kind=ProbeKind.READINESS, probe=_ok_probe,
        interval_seconds=1.0, timeout_seconds=0.5,
    )
    failures: List[EntityEvent] = []
    recoveries: List[EntityEvent] = []
    subscribe(
        topic=SystemHealthEventTopics.PROBE_FAILED,
        subscriber=lambda e: failures.append(e),
    )
    subscribe(
        topic=SystemHealthEventTopics.PROBE_RECOVERED,
        subscriber=lambda e: recoveries.append(e),
    )

    run_probe_now(registry=registry, name="r1")
    evaluate_transitions(registry=registry)
    registry._probes["r1"].probe = _fail_probe
    run_probe_now(registry=registry, name="r1")
    evaluate_transitions(registry=registry)
    testbase.assert_equal(len(failures), 1)
    registry._probes["r1"].probe = _ok_probe
    run_probe_now(registry=registry, name="r1")
    evaluate_transitions(registry=registry)
    testbase.assert_equal(len(recoveries), 1)
    return


def test_aggregator_first_observation_does_not_emit():
    """
    **Feature: 0-system-health (M1)**
    **Property: the first evaluate_transitions call after
    bootstrap emits no transitions even when the verdict is
    not OK.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    registry.register_probe(
        name="r1", kind=ProbeKind.READINESS, probe=_fail_probe,
        interval_seconds=1.0, timeout_seconds=0.5,
    )
    received_overall: List[EntityEvent] = []
    received_failed: List[EntityEvent] = []
    subscribe(
        topic=SystemHealthEventTopics.OVERALL_CHANGED,
        subscriber=lambda e: received_overall.append(e),
    )
    subscribe(
        topic=SystemHealthEventTopics.PROBE_FAILED,
        subscriber=lambda e: received_failed.append(e),
    )
    run_probe_now(registry=registry, name="r1")
    evaluate_transitions(registry=registry)
    testbase.assert_equal(len(received_overall), 0)
    testbase.assert_equal(len(received_failed), 0)
    return


# -------------------------------------
# Bootstrap registration
# -------------------------------------

def test_register_builtin_extensions_seeds_postgres_probe():
    """
    **Feature: 0-system-health (M1)**
    **Property: register_builtin_extensions seats
    PostgresHealthProbe under SystemHealthProbeExtension.**
    """
    _prepare_runtime()
    system_health_register()
    impls = list_resource_extensions(
        base_class=SystemHealthProbeExtension,
    )
    testbase.assert_equal(PostgresHealthProbe in impls, True)
    return
