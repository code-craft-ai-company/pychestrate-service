"""
.. module:: test_health_monitor_queue
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A person's health check is queued for the background
               worker, and a failed check says why (RES-39).

.. moduleauthor:: Code Craft AI LLC

"Run Health Check" used to probe the device inside the web request, so a
slow device held one of the server's few threads for as long as it took
to answer (up to the timeout). The request is now queued on the check's
configuration and the housekeeping worker runs it ahead of the scheduled
checks. The outcome is kept on the configuration, including why a check
failed, so the health page can show it after the request has gone.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import socket
import urllib.error
import urllib.request

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.core.managers import health_monitor
from ccai.pychestrate.core.managers.health_monitor import (
    COMMAND_PROBES_UNSUPPORTED_MESSAGE,
    HealthCheckConfigNotFoundError,
    HealthMonitor,
    InvalidHealthCheckConfigError,
    ProbeFailedError,
)


NOW = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)
PROBE_URL = "http://10.0.4.21/health"


class _FakeResource:
    def __init__(self, resource_id: int = 5, *, health_status: str = "online") -> None:
        self.id: int = resource_id
        self.name: str = "lab-switch-{}".format(resource_id)
        self.health_status: str = health_status
        return


class _FakeConfig:
    def __init__(
        self,
        resource_id: int = 5,
        *,
        probe_url: Optional[str] = PROBE_URL,
        enabled: bool = True,
        last_check_time: Optional[datetime] = None,
        check_requested_at: Optional[datetime] = None,
        interval_seconds: int = 60
    ) -> None:
        self.resource_id: int = resource_id
        self.probe_url: Optional[str] = probe_url
        self.probe_command: Optional[str] = None
        self.enabled: bool = enabled
        self.interval_seconds: int = interval_seconds
        self.timeout_seconds: int = 5
        self.failure_threshold: int = 3
        self.success_threshold: int = 1
        self.consecutive_failures: int = 0
        self.consecutive_successes: int = 0
        self.last_check_time: Optional[datetime] = last_check_time
        self.last_check_result: Optional[bool] = None
        self.last_check_message: Optional[str] = None
        self.check_requested_at: Optional[datetime] = check_requested_at
        return


class _FakeQuery:
    def __init__(self, rows: List[Any]) -> None:
        self._rows: List[Any] = rows
        return

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        return self

    def first(self) -> Any:
        return self._rows[0] if len(self._rows) > 0 else None

    def all(self) -> List[Any]:
        return list(self._rows)


class _FakeDbSession:
    """
        Answers ``query(Resource)`` and ``query(HealthCheckConfig)`` with
        the configured rows and counts commits.
    """

    def __init__(self, *, resources: List[Any], configs: List[Any]) -> None:
        self._rows = {"Resource": resources, "HealthCheckConfig": configs}
        self.commit_calls: int = 0
        return

    def query(self, model: Any) -> _FakeQuery:
        return _FakeQuery(self._rows.get(model.__name__, []))

    def commit(self) -> None:
        self.commit_calls += 1
        return


def _monitor(config: Optional[_FakeConfig], *, resource: Optional[_FakeResource] = None) -> HealthMonitor:
    resources = [resource] if resource is not None else [_FakeResource(config.resource_id if config else 5)]
    session = _FakeDbSession(resources=resources, configs=[config] if config is not None else [])
    return HealthMonitor(db_session=session)


def _refusal(action: Any) -> Any:
    try:
        action()
    except (HealthCheckConfigNotFoundError, InvalidHealthCheckConfigError) as refusal:
        return (type(refusal).__name__, refusal.error_code)
    return None


def test_a_request_is_recorded_on_the_configuration_and_repeated_ones_are_not():
    """
    **Feature: queued health checks (RES-39)**
    **Property: the first request stamps the configuration and reports it
    was queued; a second one while it waits changes nothing and says one
    was already waiting.**
    """
    config = _FakeConfig()
    monitor = _monitor(config)
    first = monitor.request_health_check(5, now=NOW)
    second = monitor.request_health_check(5, now=NOW + timedelta(seconds=30))

    testbase.assert_equal((first, second, config.check_requested_at), (True, False, NOW))
    return


def test_nothing_is_probed_when_a_check_is_requested():
    """
    **Feature: queued health checks (RES-39)**
    **Property: requesting a check never opens a connection, never
    changes the resource's status and leaves the last result alone.**
    """
    opened: List[Any] = []

    def _refuse(*args: Any, **kwargs: Any) -> Any:
        opened.append(args)
        raise AssertionError("a request must not probe")

    config = _FakeConfig()
    resource = _FakeResource(health_status="online")
    patch = create_module_patch(urllib.request, "build_opener")
    mock = patch.activate()
    mock.configure(side_effect=_refuse)
    try:
        _monitor(config, resource=resource).request_health_check(5)
    finally:
        patch.deactivate()

    testbase.assert_equal(
        (opened, resource.health_status, config.last_check_time, config.last_check_result),
        ([], "online", None, None),
    )
    return


def test_a_check_that_cannot_run_is_refused_at_the_request():
    """
    **Feature: queued health checks (RES-39)**
    **Property: no configuration, a disabled check and a check with no
    probe URL are each refused when requested, with a code the page can
    explain, and nothing is queued.**
    """
    disabled = _FakeConfig(enabled=False)
    no_url = _FakeConfig(probe_url=None)

    testbase.assert_equal(
        (
            _refusal(lambda: _monitor(None).request_health_check(5)),
            _refusal(lambda: _monitor(disabled).request_health_check(5)),
            _refusal(lambda: _monitor(no_url).request_health_check(5)),
            disabled.check_requested_at,
            no_url.check_requested_at,
        ),
        (
            ("HealthCheckConfigNotFoundError", "HEALTH_CHECK_CONFIG_NOT_FOUND"),
            ("InvalidHealthCheckConfigError", "HEALTH_CHECK_DISABLED"),
            ("InvalidHealthCheckConfigError", "HEALTH_CHECK_HAS_NO_PROBE_URL"),
            None,
            None,
        ),
    )
    return


def test_requested_checks_run_before_never_checked_and_scheduled_ones():
    """
    **Feature: queued health checks (RES-39)**
    **Property: a check a person asked for is first (the one asked for
    longest ago before a later one), then a never-checked one, then a
    scheduled one that has come due; one not yet due is left out.**
    """
    configs = [
        _FakeConfig(1, last_check_time=NOW - timedelta(hours=2)),
        _FakeConfig(2, last_check_time=None),
        _FakeConfig(3, last_check_time=NOW - timedelta(seconds=5)),
        _FakeConfig(4, last_check_time=NOW - timedelta(hours=1), check_requested_at=NOW - timedelta(seconds=10)),
        _FakeConfig(5, last_check_time=NOW - timedelta(seconds=5), check_requested_at=NOW - timedelta(seconds=40)),
    ]
    session = _FakeDbSession(resources=[], configs=configs)

    testbase.assert_equal(
        HealthMonitor(db_session=session).due_health_check_resource_ids(now=NOW),
        [5, 4, 2, 1],
    )
    return


def test_a_finished_check_clears_the_request_and_keeps_the_reason_it_failed():
    """
    **Feature: queued health checks (RES-39)**
    **Property: after the worker runs a requested check that fails, the
    request is gone and the configuration keeps the time, the result and
    the reason; a later pass clears the reason.**
    """
    config = _FakeConfig(check_requested_at=NOW)
    monitor = _monitor(config)
    reasons = ["The device answered with HTTP status 503."]

    def _probe(self: Any, url: str, timeout_seconds: int) -> bool:
        if len(reasons) > 0:
            raise ProbeFailedError(reasons.pop())
        return True

    original = HealthMonitor._execute_url_probe
    HealthMonitor._execute_url_probe = _probe
    try:
        monitor.run_health_check(5)
        after_failure = (config.check_requested_at, config.last_check_result, config.last_check_message)
        config.check_requested_at = NOW
        monitor.run_health_check(5)
    finally:
        HealthMonitor._execute_url_probe = original

    testbase.assert_equal(
        (after_failure, config.check_requested_at, config.last_check_result, config.last_check_message),
        ((None, False, "The device answered with HTTP status 503."), None, True, None),
    )
    return


def test_a_check_that_is_not_run_says_so_and_is_not_retried_at_once():
    """
    **Feature: queued health checks (RES-39)**
    **Property: a check that cannot run (a target the server may not
    call) clears the request, keeps the reason with a "not run" result,
    and is stamped so the scheduler waits for the interval instead of
    trying again on the next tick.**
    """
    config = _FakeConfig(probe_url="http://127.0.0.1:8000/", check_requested_at=NOW)
    result = _monitor(config).run_health_check(5)

    testbase.assert_equal(
        (config.check_requested_at, config.last_check_result, config.last_check_time is not None,
         config.last_check_message == result.error_message, result.error_message is not None),
        (None, None, True, True, True),
    )
    return


def test_a_config_saved_with_a_command_probe_is_settled_with_the_reason():
    """
    **Feature: queued health checks (RES-39)**
    **Property: a configuration with no probe URL that is run anyway
    keeps the "command probes are not supported" reason and clears its
    request.**
    """
    config = _FakeConfig(probe_url=None, check_requested_at=NOW)
    _monitor(config).run_health_check(5)

    testbase.assert_equal(
        (config.check_requested_at, config.last_check_message),
        (None, COMMAND_PROBES_UNSUPPORTED_MESSAGE),
    )
    return


def _probe_message(opener_behaviour: Any) -> Optional[str]:
    config = _FakeConfig()

    class _Opener:
        def open(self, request: Any, timeout: Any = None) -> Any:
            return opener_behaviour(request, timeout)

    patch = create_module_patch(urllib.request, "build_opener")
    mock = patch.activate()
    mock.configure(side_effect=lambda *args, **kwargs: _Opener())
    try:
        _monitor(config).run_health_check(5)
    finally:
        patch.deactivate()
    return config.last_check_message


def test_the_reason_names_what_the_device_did():
    """
    **Feature: queued health checks (RES-39)**
    **Property: the stored reason says the device answered with an error
    status, did not answer in time, or could not be reached; a passing
    probe stores none.**
    """
    def _answers_503(request: Any, timeout: Any) -> Any:
        raise urllib.error.HTTPError(PROBE_URL, 503, "Service Unavailable", {}, None)

    def _is_silent(request: Any, timeout: Any) -> Any:
        raise urllib.error.URLError(socket.timeout("timed out"))

    def _times_out_reading(request: Any, timeout: Any) -> Any:
        raise TimeoutError("read timed out")

    def _refuses(request: Any, timeout: Any) -> Any:
        raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))

    class _Fine:
        status = 200

        def __enter__(self) -> "_Fine":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

    testbase.assert_equal(
        (
            _probe_message(_answers_503),
            _probe_message(_is_silent),
            _probe_message(_times_out_reading),
            _probe_message(_refuses),
            _probe_message(lambda request, timeout: _Fine()),
        ),
        (
            "The device answered with HTTP status 503.",
            "The device did not answer within 5 seconds.",
            "The device did not answer within 5 seconds.",
            "The device could not be reached: [Errno 111] Connection refused.",
            None,
        ),
    )
    return


def test_a_reason_longer_than_the_column_is_clipped():
    """
    **Feature: queued health checks (RES-39)**
    **Property: a probe failure text longer than the stored column is
    cut to fit, ending with an ellipsis, so saving the outcome cannot
    fail.**
    """
    clipped = health_monitor._clip_message("x" * 2000)

    testbase.assert_equal(
        (len(clipped), clipped.endswith("…"), health_monitor._clip_message(None), health_monitor._clip_message("short")),
        (health_monitor.LAST_CHECK_MESSAGE_LIMIT, True, None, "short"),
    )
    return
