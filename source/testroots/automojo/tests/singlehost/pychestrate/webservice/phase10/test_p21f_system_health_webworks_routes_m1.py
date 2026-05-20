"""
.. module:: test_p21f_system_health_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native system-health route.

.. moduleauthor:: Automation Mojo LLC

The system-health route is the read endpoint added by PR p21f
(audit items 9-admin-ui + E-extension-registry-ui) to back the
shell-native ``<pyc-system-health>`` and ``<pyc-admin-overview>``
admin views. It aggregates the in-process subsystem-health signals
the service already tracks (database reachability, feature-flag
backend probes, extension-route discovery) into one JSON document.

Tests cover:

* Route matrix: ``register_system_health_routes`` attaches the
  single ``GET /api/v1/system/health`` route.
* The success path produces the documented ``{status,
  generated_at, subsystems}`` shape with one subsystem per probe.
* The top-level status is the worst of the subsystem statuses.
* The RBAC gate denies a caller without ``system:ui.admin.view``
  with an RFC 7807 403 problem document.
* Bootstrap source-smoke: register_system_health_routes is wired
  in ``register_service_extensions``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os

from typing import Any, Callable, Dict, List, Optional, Tuple

from automojo import testbase
from automojo.testbase.mocking import create_module_patch

from automojo.pychestrate.webservice.security.rbac import (
    rbac_evaluator as rbac_evaluator_module,
)
from automojo.pychestrate.webservice.system.restapi.v1 import (
    system_health_routes,
)


# ---------------------------------------------------------------------------
# Test stubs
# ---------------------------------------------------------------------------


class _FakePrincipal:
    """
        Stand-in AuthPrincipal for the RBAC gate.
    """

    def __init__(self, *, user_id: str = "u-1") -> None:
        self.user_id: str = user_id
        return


class _FakeDecision:
    """
        Stand-in AuthzDecision; ``allowed`` defaults True so the
        handler proceeds past the ``system:ui.admin.view`` gate.
    """

    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed: bool = allowed
        return


class _FakeRequest:
    """
        Minimal duck-typed Request. The system-health handler
        touches ``path`` plus ``db_session`` / ``auth_principal``
        for the ``system:ui.admin.view`` RBAC gate.
    """

    def __init__(
        self,
        *,
        path: str = "/api/v1/system/health",
        with_session: bool = True
    ) -> None:
        self.path: str = path
        if with_session is True:
            self.db_session: Any = object()
        else:
            self.db_session = None
        self.auth_principal: Any = _FakePrincipal()
        return


class _FakeApp:
    """
        Stand-in for a webworks application; records
        ``attach_route(path, methods=...)`` calls.
    """

    def __init__(self) -> None:
        self.calls: List[Tuple[str, Tuple[str, ...], Callable]] = []
        return

    def attach_route(
        self, path: str, methods: Optional[List[str]] = None
    ) -> Callable:
        resolved_methods = tuple(methods if methods is not None else ["GET"])

        def decorator(func: Callable) -> Callable:
            self.calls.append((path, resolved_methods, func))
            rtnval = func
            return rtnval

        rtnval = decorator
        return rtnval


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


_PERMISSION_PATCH: Any = None


def _activate_permission_patch(*, allowed: bool) -> None:
    """
        Patch ``rbac_evaluator.check_permission`` to return a
        decision with the supplied ``allowed`` value.

        :param allowed: Whether the RBAC gate should allow the call.

        :returns: None.
    """
    global _PERMISSION_PATCH
    _PERMISSION_PATCH = create_module_patch(
        rbac_evaluator_module, "check_permission"
    )
    mock_permission = _PERMISSION_PATCH.activate()
    mock_permission.configure(return_value=_FakeDecision(allowed=allowed))
    return


def _deactivate_permission_patch() -> None:
    """
        Tear down the ``check_permission`` patch.

        :returns: None.
    """
    global _PERMISSION_PATCH
    if _PERMISSION_PATCH is not None:
        _PERMISSION_PATCH.deactivate()
        _PERMISSION_PATCH = None
    return


# ---------------------------------------------------------------------------
# Route registration matrix
# ---------------------------------------------------------------------------


def test_register_system_health_routes_attaches_the_health_route():
    """
    **Feature: 9-admin-ui PR p21f (system-health route)**
    **Property: register_system_health_routes attaches the single
    ``GET /api/v1/system/health`` route under the version prefix.**
    """
    app = _FakeApp()
    system_health_routes.register_system_health_routes(
        app=app, version_prefix="/api/v1"
    )

    expected_pairs = (
        ("/api/v1/system/health", ("GET",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# handle_system_health -- success path
# ---------------------------------------------------------------------------


def test_handle_system_health_returns_aggregate_document():
    """
    **Feature: 9-admin-ui PR p21f (system-health route)**
    **Property: Returns 200 with a ``{status, generated_at,
    subsystems}`` document carrying one subsystem per probe
    (database, feature-flags, extension-routes).**
    """
    _activate_permission_patch(allowed=True)
    try:
        request = _FakeRequest()
        response = system_health_routes.handle_system_health(request)
    finally:
        _deactivate_permission_patch()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal("status" in body, True)
    testbase.assert_equal("generated_at" in body, True)
    testbase.assert_equal(len(body["subsystems"]), 3)

    names = [subsystem["name"] for subsystem in body["subsystems"]]
    testbase.assert_equal("database" in names, True)
    testbase.assert_equal("feature-flags" in names, True)
    testbase.assert_equal("extension-routes" in names, True)
    return


def test_handle_system_health_database_ok_when_session_attached():
    """
    **Feature: 9-admin-ui PR p21f (system-health route)**
    **Property: The database subsystem reports ``ok`` when the
    request carries a live ``db_session``.**
    """
    _activate_permission_patch(allowed=True)
    try:
        request = _FakeRequest(with_session=True)
        document = system_health_routes.build_system_health_document(
            request=request
        )
    finally:
        _deactivate_permission_patch()

    database = None
    for subsystem in document["subsystems"]:
        if subsystem["name"] == "database":
            database = subsystem
    testbase.assert_equal(database is not None, True)
    testbase.assert_equal(database["status"], "ok")
    return


def test_worst_status_reduces_to_highest_severity():
    """
    **Feature: 9-admin-ui PR p21f (system-health route)**
    **Property: The top-level status is the worst of the
    subsystem statuses -- ``error`` beats ``degraded`` beats
    ``ok``.**
    """
    statuses = ["ok", "degraded", "ok"]
    worst = system_health_routes._worst_status(statuses=statuses)
    testbase.assert_equal(worst, "degraded")

    statuses = ["ok", "degraded", "error"]
    worst = system_health_routes._worst_status(statuses=statuses)
    testbase.assert_equal(worst, "error")

    statuses = ["ok", "ok", "ok"]
    worst = system_health_routes._worst_status(statuses=statuses)
    testbase.assert_equal(worst, "ok")
    return


# ---------------------------------------------------------------------------
# handle_system_health -- RBAC gate
# ---------------------------------------------------------------------------


def test_handle_system_health_denies_caller_without_admin_view():
    """
    **Feature: 9-admin-ui PR p21f (system-health route)**
    **Property: A caller lacking ``system:ui.admin.view`` gets an
    RFC 7807 403 problem document rather than the health
    summary.**
    """
    _activate_permission_patch(allowed=False)
    try:
        request = _FakeRequest()
        response = system_health_routes.handle_system_health(request)
    finally:
        _deactivate_permission_patch()

    testbase.assert_equal(response.status_code, 403)
    return


def test_handle_system_health_503_when_session_missing():
    """
    **Feature: 9-admin-ui PR p21f (system-health route)**
    **Property: A request with no ``db_session`` -- the
    middleware was not installed -- returns the documented 503
    problem document rather than an opaque traceback.**
    """
    request = _FakeRequest(with_session=False)
    response = system_health_routes.handle_system_health(request)
    testbase.assert_equal(response.status_code, 503)
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_register_system_health_routes_wired_in_service_extensions():
    """
    **Feature: 9-admin-ui PR p21f (system-health route)**
    **Property: ``register_service_extensions`` in
    ``app_pychestrate_main`` calls ``register_system_health_routes``
    so the route is mounted on the production webservice.**
    """
    here = os.path.dirname(os.path.abspath(__file__))
    main_path = os.path.normpath(
        os.path.join(
            here,
            "..", "..", "..", "..", "..", "..", "..", "..",
            "source", "site", "app_pychestrate_main.py",
        )
    )
    with open(main_path, "r", encoding="utf-8") as handle:
        text = handle.read()

    has_call = (
        'register_system_health_routes(app=app, version_prefix="/api/v1")'
        in text
    )
    testbase.assert_equal(has_call, True)
    return
