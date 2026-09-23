"""
.. module:: test_health_monitor_probe_guard
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the health-check probe guard: command probes
               are refused and URL probes may not target the server.

.. moduleauthor:: Code Craft AI LLC

Audit finding RES-03: a health check could carry a ``probe_command``
that the server ran with ``subprocess.run(..., shell=True)`` as the
service account, and a ``probe_url`` could point at the server
itself or the cloud metadata endpoint. Command probes are now
refused at configuration and never executed, and every URL probe
(and each redirect it follows) is checked by
:func:`validate_probe_url`.

**Feature: resources**
**Property: health probes cannot run commands on, or reach into,
the Pychestrate server**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import socket
import tempfile
import urllib.request

from typing import Any, List, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.core.managers import health_monitor
from ccai.pychestrate.core.managers.health_monitor import (
    COMMAND_PROBES_UNSUPPORTED_MESSAGE,
    HealthCheckConfigRequest,
    HealthMonitor,
    InvalidHealthCheckConfigError,
    ProbeTargetRejectedError,
    validate_probe_url,
)


# =============================================================================
# Fakes
# =============================================================================


class _FakeResource:
    def __init__(self, *, health_status: str = "online") -> None:
        self.id: int = 5
        self.name: str = "lab-switch-5"
        self.health_status: str = health_status
        return


class _FakeConfig:
    def __init__(
        self,
        *,
        probe_url: Optional[str],
        probe_command: Optional[str] = None
    ) -> None:
        self.resource_id: int = 5
        self.probe_url: Optional[str] = probe_url
        self.probe_command: Optional[str] = probe_command
        self.enabled: bool = True
        self.timeout_seconds: int = 5
        self.failure_threshold: int = 3
        self.success_threshold: int = 1
        self.consecutive_failures: int = 0
        self.consecutive_successes: int = 0
        self.last_check_time: Any = None
        self.last_check_result: Any = None
        return


class _FakeQuery:
    def __init__(self, result: Any) -> None:
        self._result: Any = result
        return

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        return self

    def first(self) -> Any:
        return self._result


class _FakeDbSession:
    """
        Answers ``query(Resource)`` and ``query(HealthCheckConfig)``
        with the configured rows and records commits.
    """

    def __init__(
        self, *, resource: Optional[_FakeResource], config: Optional[_FakeConfig]
    ) -> None:
        self._rows = {"Resource": resource, "HealthCheckConfig": config}
        self.commit_calls: int = 0
        return

    def query(self, model: Any) -> _FakeQuery:
        return _FakeQuery(self._rows.get(model.__name__))

    def commit(self) -> None:
        self.commit_calls += 1
        return


def _run_check(*, config: _FakeConfig) -> Any:
    session = _FakeDbSession(resource=_FakeResource(), config=config)
    rtnval = HealthMonitor(db_session=session).run_health_check(5)
    return rtnval


def _configure(**overrides: Any) -> Optional[str]:
    """
        Call configure_health_check with a valid request plus
        ``overrides`` and return the refusal message, or None when
        the request passed validation (the fake database then
        reports the resource missing, which ends the call).
    """
    fields = {"resource_id": 5, "probe_url": "http://10.0.4.21/health"}
    fields.update(overrides)
    monitor = HealthMonitor(db_session=_FakeDbSession(resource=None, config=None))
    try:
        monitor.configure_health_check(HealthCheckConfigRequest(**fields))
    except InvalidHealthCheckConfigError as refusal:
        return str(refusal)
    except health_monitor.ResourceNotFoundError:
        return None
    return None


# =============================================================================
# validate_probe_url
# =============================================================================


def test_probe_url_must_use_http_or_https():
    """
    **Feature: resource health probes (RES-03)**
    **Property: a probe URL with any other scheme (file://) is refused.**
    """
    testbase.assert_equal(
        validate_probe_url("file:///etc/passwd", resolve=False) is not None, True
    )
    return


def test_probe_url_may_not_target_localhost_by_name():
    """
    **Feature: resource health probes (RES-03)**
    **Property: "localhost" (the Pychestrate server itself) is refused.**
    """
    testbase.assert_equal(
        validate_probe_url("http://localhost:8080/", resolve=False) is not None, True
    )
    return


def test_probe_url_may_not_target_a_loopback_address():
    """
    **Feature: resource health probes (RES-03)**
    **Property: an IPv4 loopback literal is refused.**
    """
    testbase.assert_equal(
        validate_probe_url("http://127.0.0.1:8000/admin", resolve=False) is not None, True
    )
    return


def test_probe_url_may_not_target_the_ipv6_loopback():
    """
    **Feature: resource health probes (RES-03)**
    **Property: the IPv6 loopback literal is refused.**
    """
    testbase.assert_equal(
        validate_probe_url("http://[::1]/", resolve=False) is not None, True
    )
    return


def test_probe_url_may_not_target_a_loopback_mapped_into_ipv6():
    """
    **Feature: resource health probes (RES-03)**
    **Property: an IPv4-mapped IPv6 loopback (::ffff:127.0.0.1) is
    refused like the IPv4 address it maps.**
    """
    testbase.assert_equal(
        validate_probe_url("http://[::ffff:127.0.0.1]/", resolve=False) is not None, True
    )
    return


def test_probe_url_may_not_target_the_cloud_metadata_endpoint():
    """
    **Feature: resource health probes (RES-03)**
    **Property: the link-local metadata address 169.254.169.254 is
    refused.**
    """
    testbase.assert_equal(
        validate_probe_url(
            "http://169.254.169.254/latest/meta-data/", resolve=False
        ) is not None,
        True,
    )
    return


def test_probe_url_may_target_a_private_lab_address():
    """
    **Feature: resource health probes (RES-03)**
    **Property: private ranges stay allowed -- lab devices live
    there.**
    """
    testbase.assert_equal(
        validate_probe_url("http://10.0.4.21/health", resolve=False), None
    )
    return


def test_probe_host_that_resolves_to_loopback_is_refused():
    """
    **Feature: resource health probes (RES-03)**
    **Property: with resolution on (probe time), a host name that
    resolves to a loopback address is refused.**
    """

    def _resolve_to_loopback(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    patch = create_module_patch(socket, "getaddrinfo")
    mock = patch.activate()
    mock.configure(side_effect=_resolve_to_loopback)
    try:
        problem = validate_probe_url("http://device.lab.example/health", resolve=True)
    finally:
        patch.deactivate()
    testbase.assert_equal(problem is not None, True)
    return


def test_probe_redirect_to_loopback_is_refused():
    """
    **Feature: resource health probes (RES-03)**
    **Property: the probe's redirect handler refuses to follow a
    redirect to a loopback address.**
    """
    handler = health_monitor._GuardedRedirectHandler()
    request = urllib.request.Request("http://10.0.4.21/health")
    refused = False
    try:
        handler.redirect_request(
            request, None, 302, "Found", {}, "http://127.0.0.1:8000/admin"
        )
    except ProbeTargetRejectedError:
        refused = True
    testbase.assert_equal(refused, True)
    return


# =============================================================================
# configure_health_check
# =============================================================================


def test_configure_refuses_a_command_probe():
    """
    **Feature: resource health probes (RES-03)**
    **Property: a configuration carrying a probe_command is refused
    with the explanation that command probes are unsupported.**
    """
    testbase.assert_equal(
        _configure(probe_url=None, probe_command="curl -fs http://10.0.4.21/"),
        COMMAND_PROBES_UNSUPPORTED_MESSAGE,
    )
    return


def test_configure_requires_a_probe_url():
    """
    **Feature: resource health probes (RES-03)**
    **Property: a configuration without a probe URL is refused.**
    """
    testbase.assert_equal(_configure(probe_url=None) is not None, True)
    return


def test_configure_refuses_a_probe_url_aimed_at_the_server():
    """
    **Feature: resource health probes (RES-03)**
    **Property: a probe URL aimed at the loopback interface is
    refused when the configuration is saved.**
    """
    testbase.assert_equal(
        _configure(probe_url="http://127.0.0.1:8000/") is not None, True
    )
    return


def test_configure_caps_the_probe_timeout():
    """
    **Feature: resource health probes (RES-03)**
    **Property: a timeout above MAX_PROBE_TIMEOUT_SECONDS is refused,
    so a probe cannot hold a worker thread for minutes.**
    """
    testbase.assert_equal(
        _configure(
            timeout_seconds=health_monitor.MAX_PROBE_TIMEOUT_SECONDS + 1
        ) is not None,
        True,
    )
    return


def test_configure_accepts_a_lab_device_probe():
    """
    **Feature: resource health probes (RES-03)**
    **Property: a URL probe aimed at a private lab address passes
    validation.**
    """
    testbase.assert_equal(_configure(), None)
    return


# =============================================================================
# run_health_check
# =============================================================================


def test_saved_command_probe_is_never_executed():
    """
    **Feature: resource health probes (RES-03)**
    **Property: a configuration saved before command probes were
    withdrawn is not run -- the command's side effect never happens.**
    """
    marker_dir = tempfile.mkdtemp(prefix="probe-guard-")
    marker = os.path.join(marker_dir, "command-ran")
    try:
        _run_check(
            config=_FakeConfig(probe_url=None, probe_command="touch {}".format(marker))
        )
        testbase.assert_equal(os.path.exists(marker), False)
    finally:
        if os.path.exists(marker):
            os.unlink(marker)
        os.rmdir(marker_dir)
    return


def test_saved_command_probe_leaves_the_status_unchanged():
    """
    **Feature: resource health probes (RES-03)**
    **Property: running a legacy command-probe configuration changes
    nothing and reports how to reconfigure it.**
    """
    result = _run_check(
        config=_FakeConfig(probe_url=None, probe_command="true")
    )
    testbase.assert_equal(
        (result.status_changed, result.error_message),
        (False, COMMAND_PROBES_UNSUPPORTED_MESSAGE),
    )
    return


def test_probe_aimed_at_loopback_is_not_sent():
    """
    **Feature: resource health probes (RES-03)**
    **Property: at probe time, a URL aimed at the loopback interface
    is refused before any HTTP request is built, and the resource's
    status does not change.**
    """
    opened: List[Any] = []

    def _record_build_opener(*args: Any, **kwargs: Any) -> Any:
        opened.append(args)
        raise AssertionError("the probe must not build an opener")

    patch = create_module_patch(urllib.request, "build_opener")
    mock = patch.activate()
    mock.configure(side_effect=_record_build_opener)
    try:
        result = _run_check(config=_FakeConfig(probe_url="http://127.0.0.1:8000/"))
    finally:
        patch.deactivate()
    testbase.assert_equal((result.status_changed, opened), (False, []))
    return
