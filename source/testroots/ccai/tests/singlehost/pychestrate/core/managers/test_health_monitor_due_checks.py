"""
.. module:: test_health_monitor_due_checks
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for choosing and running the health checks that are due.

.. moduleauthor:: Code Craft AI LLC

Audit finding RES-12: the health-check form stored a check interval,
but nothing ever ran a check unless someone pressed the button. The
background scheduler now asks :class:`HealthMonitor` which checks are
due (enabled, with a probe URL, never run or last run an interval ago)
and runs them, longest-waiting first, until its time budget is spent.

**Feature: resources (RES-12 scheduled health checks)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import urllib.request

from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.managers import health_monitor
from ccai.pychestrate.core.managers.health_monitor import HealthMonitor
from ccai.pychestrate.core.orm import (
    HealthCheckConfig,
    PychestrateModelBase,
    Resource,
)


def _lab(configs: Dict[str, Dict[str, Any]]) -> Tuple[Any, Dict[str, int]]:
    """
        An in-memory database holding one resource per entry of
        ``configs``, each with a health check built from the entry's
        overrides of an enabled URL probe that has never run.
    """
    engine = sa.create_engine("sqlite://")
    PychestrateModelBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    ids: Dict[str, int] = {}
    for key, overrides in configs.items():
        resource = Resource(name=key, resource_type="device", metadata_json={}, sensitive_fields=[])
        session.add(resource)
        session.flush()
        values: Dict[str, Any] = {
            "probe_url": "http://10.0.4.21/health",
            "interval_seconds": 60,
            "timeout_seconds": 5,
            "enabled": True,
        }
        values.update(overrides)
        session.add(HealthCheckConfig(resource_id=resource.id, **values))
        ids[key] = resource.id
    session.commit()
    rtnval = (session, ids)
    return rtnval


class _Response:
    status: int = 200

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: Any) -> None:
        return


class _Opener:
    def __init__(self, sent: List[str]) -> None:
        self._sent = sent
        return

    def open(self, request: Any, timeout: Optional[float] = None) -> _Response:
        self._sent.append(request.full_url)
        rtnval = _Response()
        return rtnval


def _answering_probes(sent: List[str]) -> List[Any]:
    """
        Patch the probe so every target answers 200 and is recorded in
        ``sent``; returns the patches for the caller to deactivate.
    """
    guard = create_module_patch(health_monitor, "validate_probe_url")
    guard.activate().configure(return_value=None)
    opener = create_module_patch(urllib.request, "build_opener")
    opener.activate().configure(side_effect=lambda *handlers: _Opener(sent))
    rtnval = [guard, opener]
    return rtnval


def test_never_run_and_overdue_checks_are_due_and_nothing_else():
    """
    **Feature: resources (RES-12 scheduled health checks)**
    **Property: a check is due when it is enabled, has a probe URL, and
    has never run or last ran at least its interval ago; recent,
    disabled and command-only checks are not due.**
    """
    now = utc_now()
    session, ids = _lab({
        "never-run": {},
        "overdue": {"last_check_time": now - timedelta(seconds=61)},
        "recent": {"last_check_time": now - timedelta(seconds=30)},
        "disabled": {"enabled": False},
        "command-only": {"probe_url": None, "probe_command": "true"},
    })
    due = HealthMonitor(session).due_health_check_resource_ids(now=now)
    testbase.assert_equal(sorted(due), sorted([ids["never-run"], ids["overdue"]]))
    return


def test_never_run_checks_come_first_then_the_longest_waiting():
    """
    **Feature: resources (RES-12 scheduled health checks)**
    **Property: due checks are ordered never-run first, then by how long
    ago they last ran, oldest first, so a slow run cannot starve any.**
    """
    now = utc_now()
    session, ids = _lab({
        "ten-minutes": {"last_check_time": now - timedelta(minutes=10)},
        "an-hour": {"last_check_time": now - timedelta(hours=1)},
        "never-run": {},
    })
    due = HealthMonitor(session).due_health_check_resource_ids(now=now)
    testbase.assert_equal(due, [ids["never-run"], ids["an-hour"], ids["ten-minutes"]])
    return


def test_a_check_that_ran_is_not_due_again_until_its_interval_passes():
    """
    **Feature: resources (RES-12 scheduled health checks)**
    **Property: running the due checks probes each due target once and
    records the time, so the check is not due again until its interval
    has passed.**
    """
    session, ids = _lab({"switch": {"interval_seconds": 120}})
    sent: List[str] = []
    patches = _answering_probes(sent)
    try:
        summary = HealthMonitor(session).run_due_health_checks()
    finally:
        for patch in patches:
            patch.deactivate()
    monitor = HealthMonitor(session)
    later = utc_now() + timedelta(seconds=60)
    after_interval = utc_now() + timedelta(seconds=121)
    testbase.assert_equal(
        (summary.total_checked, sent,
         monitor.due_health_check_resource_ids(now=later),
         monitor.due_health_check_resource_ids(now=after_interval)),
        (1, ["http://10.0.4.21/health"], [], [ids["switch"]]),
    )
    return


def test_a_run_stops_when_its_caller_says_so_and_leaves_the_rest_due():
    """
    **Feature: resources (RES-12 scheduled health checks)**
    **Property: when ``should_continue`` turns False (time budget spent
    or lease lost) the run stops before the next probe, and the checks
    it did not reach are still due.**
    """
    session, ids = _lab({"first": {}, "second": {}, "third": {}})
    sent: List[str] = []
    answers = iter([True, False])
    patches = _answering_probes(sent)
    try:
        summary = HealthMonitor(session).run_due_health_checks(should_continue=lambda: next(answers))
    finally:
        for patch in patches:
            patch.deactivate()
    still_due = HealthMonitor(session).due_health_check_resource_ids()
    testbase.assert_equal(
        (summary.total_checked, len(sent), still_due),
        (1, 1, [ids["second"], ids["third"]]),
    )
    return
