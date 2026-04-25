"""
.. module:: test_p12b_system_health_m2
    :synopsis: Tests for P12b — 0-system-health M2.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import shutil
import tempfile
import threading
import time

from datetime import datetime, timedelta, timezone

from automojo import testbase

from automojo.pychestrate.webservice.extensions.registry import (
    list_resource_extensions,
    reset_registry_for_testing,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    reset_for_testing as reset_event_bus,
)
from automojo.pychestrate.webservice.system_health import (
    DiskSpaceHealthProbe,
    HealthConfig,
    HealthRegistry,
    HealthScheduler,
    MessageBusHealthProbe,
    PostgresHealthProbe,
    ProbeKind,
    ProbeResult,
    ProbeStatus,
    SystemHealthProbeExtension,
    configure_disk_space_probe,
    register_builtin_extensions as system_health_register,
    reset_aggregator_for_testing,
    reset_disk_space_probe_for_testing,
    reset_postgres_probe_for_testing,
    run_probe_now,
)


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    reset_aggregator_for_testing()
    reset_postgres_probe_for_testing()
    reset_disk_space_probe_for_testing()
    return


# -------------------------------------
# MessageBusHealthProbe
# -------------------------------------

def test_message_bus_probe_round_trip_succeeds():
    """
    **Feature: 0-system-health (M2)**
    **Property: MessageBusHealthProbe.run_probe round-trips a
    synthetic event through the in-process bus and reports
    OK.**
    """
    _prepare_runtime()
    result = MessageBusHealthProbe.run_probe()
    testbase.assert_equal(result.status, ProbeStatus.OK)
    return


def test_message_bus_probe_advertises_readiness_kind():
    """
    **Feature: 0-system-health (M2)**
    **Property: MessageBusHealthProbe declares ProbeKind.READINESS
    so a failing bus blocks ``/__health/ready``.**
    """
    _prepare_runtime()
    testbase.assert_equal(
        MessageBusHealthProbe.kind, ProbeKind.READINESS,
    )
    testbase.assert_equal(MessageBusHealthProbe.name, "message_bus")
    return


# -------------------------------------
# DiskSpaceHealthProbe
# -------------------------------------

def test_disk_space_probe_ok_under_threshold():
    """
    **Feature: 0-system-health (M2)**
    **Property: DiskSpaceHealthProbe returns OK when used
    fraction is below the threshold.**
    """
    _prepare_runtime()
    with tempfile.TemporaryDirectory() as tmpdir:
        configure_disk_space_probe(
            watch_path=tmpdir, used_fraction_threshold=1.01,
        )
        result = DiskSpaceHealthProbe.run_probe()
    testbase.assert_equal(result.status, ProbeStatus.OK)
    testbase.assert_equal("used_fraction" in result.details, True)
    return


def test_disk_space_probe_fail_at_threshold():
    """
    **Feature: 0-system-health (M2)**
    **Property: a threshold of 0.0 forces every probe run to
    FAIL with reason='disk_threshold_exceeded'.**
    """
    _prepare_runtime()
    with tempfile.TemporaryDirectory() as tmpdir:
        configure_disk_space_probe(
            watch_path=tmpdir, used_fraction_threshold=0.0,
        )
        result = DiskSpaceHealthProbe.run_probe()
    testbase.assert_equal(result.status, ProbeStatus.FAIL)
    testbase.assert_equal(
        "disk_threshold_exceeded" in (result.last_error or ""),
        True,
    )
    return


def test_disk_space_probe_fail_when_path_missing():
    """
    **Feature: 0-system-health (M2)**
    **Property: a missing watch path surfaces FAIL with the
    OSError class name in last_error.**
    """
    _prepare_runtime()
    configure_disk_space_probe(
        watch_path="/this/path/does/not/exist/probably",
        used_fraction_threshold=0.9,
    )
    result = DiskSpaceHealthProbe.run_probe()
    testbase.assert_equal(result.status, ProbeStatus.FAIL)
    return


# -------------------------------------
# Scheduler tick_due interval scheduling
# -------------------------------------

def test_tick_due_skips_probes_not_yet_due():
    """
    **Feature: 0-system-health (M2)**
    **Property: tick_due skips probes whose
    last_started_at + interval_seconds is in the future.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    registry.register_probe(
        name="alpha", kind=ProbeKind.LIVENESS,
        probe=lambda: ProbeResult(
            status=ProbeStatus.OK, duration_ms=1.0,
            observed_at=datetime.now(tz=timezone.utc),
        ),
        interval_seconds=60.0, timeout_seconds=0.5,
    )
    scheduler = HealthScheduler(
        registry=registry, config=HealthConfig(probe_worker_count=1),
    )
    scheduler.start()
    try:
        first = scheduler.tick_due()
        # Second call right away — interval not elapsed.
        second = scheduler.tick_due()
    finally:
        scheduler.stop()
    testbase.assert_equal(first, 1)
    testbase.assert_equal(second, 0)
    return


def test_tick_due_runs_probe_when_interval_elapses():
    """
    **Feature: 0-system-health (M2)**
    **Property: a tick_due call passing a now in the future by
    interval_seconds + epsilon re-runs the probe.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    counter = {"count": 0}

    def _counting_probe() -> ProbeResult:
        counter["count"] = counter["count"] + 1
        return ProbeResult(
            status=ProbeStatus.OK, duration_ms=1.0,
            observed_at=datetime.now(tz=timezone.utc),
        )

    registry.register_probe(
        name="alpha", kind=ProbeKind.LIVENESS, probe=_counting_probe,
        interval_seconds=5.0, timeout_seconds=0.5,
    )
    scheduler = HealthScheduler(
        registry=registry, config=HealthConfig(probe_worker_count=1),
    )
    scheduler.start()
    try:
        scheduler.tick_due()
        future = datetime.now(tz=timezone.utc) + timedelta(seconds=10.0)
        scheduler.tick_due(now=future)
    finally:
        scheduler.stop()
    testbase.assert_equal(counter["count"], 2)
    return


def test_tick_due_returns_zero_for_empty_registry():
    """
    **Feature: 0-system-health (M2)**
    **Property: tick_due is a no-op against an empty registry.**
    """
    _prepare_runtime()
    registry = HealthRegistry()
    scheduler = HealthScheduler(
        registry=registry, config=HealthConfig(probe_worker_count=1),
    )
    scheduler.start()
    try:
        attempted = scheduler.tick_due()
    finally:
        scheduler.stop()
    testbase.assert_equal(attempted, 0)
    return


# -------------------------------------
# Bootstrap registration (M2 widens)
# -------------------------------------

def test_register_builtin_extensions_seeds_m2_probes():
    """
    **Feature: 0-system-health (M2)**
    **Property: register_builtin_extensions seeds Postgres,
    MessageBus, and DiskSpace probes under
    SystemHealthProbeExtension.**
    """
    _prepare_runtime()
    system_health_register()
    impls = list_resource_extensions(
        base_class=SystemHealthProbeExtension,
    )
    testbase.assert_equal(PostgresHealthProbe in impls, True)
    testbase.assert_equal(MessageBusHealthProbe in impls, True)
    testbase.assert_equal(DiskSpaceHealthProbe in impls, True)
    return
