"""
.. module:: system.restapi.v1.system_health_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST route for /api/v1/system/health.

.. moduleauthor:: Code Craft AI LLC

The production webservice runs on ``ccai.webworks`` (see
:mod:`app_pychestrate_main`). This module exposes a single
operator-facing read endpoint that aggregates the in-process
subsystem-health signals the service already tracks into one
JSON document for the shell-native ``<pyc-system-health>`` and
``<pyc-admin-overview>`` admin views.

One route:

* ``GET /api/v1/system/health``
  — aggregate subsystem-health summary.

The document reports three subsystem probes drawn from state the
service already maintains:

* ``database`` — whether the per-request middleware attached a
  live ``request.db_session``.
* ``feature-flags`` — the feature-flag backend health-prober
  results (one probe per registered backend).
* ``extension-routes`` — the count of extension-contributed REST
  routes the host discovered at startup.

Each subsystem reports a coarse ``status`` of ``ok`` |
``degraded`` | ``error``; the top-level ``status`` is the worst
of the subsystem statuses.

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`. The endpoint is RBAC-gated
on ``system:ui.admin.view`` — the same permission key that gates
the admin sidebar group — since the health summary is an
admin-surface read view.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


SYSTEM_HEALTH_PATH = "/system/health"

SYSTEM_HEALTH_PERMISSION_KEY = "system:ui.admin.view"

STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_ERROR = "error"

_STATUS_RANK = {
    STATUS_OK: 0,
    STATUS_DEGRADED: 1,
    STATUS_ERROR: 2,
}


class _ProblemAbort(Exception):
    """
        Internal control-flow exception carrying a webworks problem
        response so the RBAC gate can signal a 401/403 once and the
        top-level handler converts it at the boundary.
    """

    def __init__(self, response: Response) -> None:
        super().__init__("problem abort")
        self.response: Response = response
        return


def _abort_problem(
        *,
        request: Request,
        status: int,
        detail: str,
        extensions: Optional[Dict[str, Any]] = None
    ) -> None:
    """
        Build a problem response and raise :class:`_ProblemAbort`.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param extensions: Optional namespaced extension members.

        :returns: Never returns.
        :raises: :class:`_ProblemAbort`.
    """
    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _require_admin_view(request: Request) -> None:
    """
        Require the calling principal to hold
        ``system:ui.admin.view``. The system-health summary is a
        read-only admin-surface view but still operator-gated.

        :param request: Incoming webworks request.

        :returns: None.
        :raises: :class:`_ProblemAbort` on missing session /
                 principal / permission.
    """
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        _abort_problem(
            request=request,
            status=503,
            detail="Request-scoped db_session not configured",
        )

    principal = getattr(request, "auth_principal", None)
    if principal is None:
        _abort_problem(
            request=request,
            status=401,
            detail="Authentication required.",
        )

    now = datetime.now(timezone.utc)
    decision = rbac_evaluator.check_permission(
        db_session=db_session,
        principal=principal,
        permission_key=SYSTEM_HEALTH_PERMISSION_KEY,
        now=now,
    )
    if decision.allowed is False:
        _abort_problem(
            request=request,
            status=403,
            detail="Permission denied: {}".format(
                SYSTEM_HEALTH_PERMISSION_KEY
            ),
            extensions={
                "required_permission": SYSTEM_HEALTH_PERMISSION_KEY
            },
        )
    return


def _worst_status(*, statuses: List[str]) -> str:
    """
        Reduce a list of subsystem statuses to the worst (highest
        severity) one.

        :param statuses: Per-subsystem coarse status strings.

        :returns: The worst status; ``ok`` when the list is empty.
    """
    worst = STATUS_OK
    worst_rank = _STATUS_RANK[STATUS_OK]
    for status in statuses:
        rank = _STATUS_RANK.get(status, _STATUS_RANK[STATUS_ERROR])
        if rank > worst_rank:
            worst_rank = rank
            worst = status
    rtnval = worst
    return rtnval


def _probe_database(*, request: Request) -> Dict[str, Any]:
    """
        Probe database reachability. The per-request middleware
        attaches a live session as ``request.db_session`` when the
        connection pool is healthy; its presence is the cheapest
        in-process reachability signal available to a read handler.

        :param request: Incoming webworks request.

        :returns: A subsystem-health dict.
    """
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        rtnval = {
            "name": "database",
            "label": "Database",
            "status": STATUS_ERROR,
            "detail": "No request-scoped db_session attached.",
        }
        return rtnval

    rtnval = {
        "name": "database",
        "label": "Database",
        "status": STATUS_OK,
        "detail": "Request-scoped session attached.",
    }
    return rtnval


def _probe_feature_flags() -> Dict[str, Any]:
    """
        Probe feature-flag backend health via the flag health
        prober. Each registered backend is probed once; a backend
        reporting unhealthy degrades the subsystem.

        :returns: A subsystem-health dict carrying a ``backends``
                  list extension member.
    """
    backends: List[Dict[str, Any]] = []
    subsystem_status = STATUS_OK
    detail = "All feature-flag backends healthy."
    try:
        from ccai.pychestrate.webservice.identity.flags import (
            health_prober,
        )
        results = health_prober.probe_once()
        for backend_name, health in results:
            if health.healthy is True:
                backend_status = STATUS_OK
            else:
                backend_status = STATUS_DEGRADED
            backends.append({
                "name": backend_name,
                "status": backend_status,
                "reason": health.reason,
            })
        unhealthy = [b for b in backends if b["status"] != STATUS_OK]
        if len(unhealthy) > 0:
            subsystem_status = STATUS_DEGRADED
            detail = "{} of {} feature-flag backends unhealthy.".format(
                len(unhealthy), len(backends)
            )
        elif len(backends) == 0:
            detail = "No feature-flag backends registered."
    except Exception as xcpt:  # noqa: BLE001 — purposeful probe isolation
        subsystem_status = STATUS_ERROR
        detail = "Feature-flag probe failed: {}".format(
            type(xcpt).__name__
        )

    rtnval = {
        "name": "feature-flags",
        "label": "Feature Flags",
        "status": subsystem_status,
        "detail": detail,
        "backends": backends,
    }
    return rtnval


def _probe_extension_routes() -> Dict[str, Any]:
    """
        Probe the extension-route host. Reports the count of
        extension-contributed REST routes discovered at startup.

        :returns: A subsystem-health dict carrying a ``route_count``
                  extension member.
    """
    subsystem_status = STATUS_OK
    route_count = 0
    detail = "Extension-route host discovered routes."
    try:
        from ccai.pychestrate.webservice.extensions.ext_router import (
            mount_extension_routes,
        )
        manifest = mount_extension_routes(extensions=None)
        route_count = len(manifest.routes)
        detail = "{} extension route(s) discovered.".format(route_count)
    except Exception as xcpt:  # noqa: BLE001 — purposeful probe isolation
        subsystem_status = STATUS_ERROR
        detail = "Extension-route discovery failed: {}".format(
            type(xcpt).__name__
        )

    rtnval = {
        "name": "extension-routes",
        "label": "Extension Routes",
        "status": subsystem_status,
        "detail": detail,
        "route_count": route_count,
    }
    return rtnval


def build_system_health_document(*, request: Request) -> Dict[str, Any]:
    """
        Build the aggregate system-health document. Exposed at module
        level so unit tests can build the document directly without
        a route round-trip.

        :param request: Incoming webworks request.

        :returns: A JSON-friendly system-health dict.
    """
    subsystems: List[Dict[str, Any]] = []
    subsystems.append(_probe_database(request=request))
    subsystems.append(_probe_feature_flags())
    subsystems.append(_probe_extension_routes())

    statuses = [subsystem["status"] for subsystem in subsystems]
    overall = _worst_status(statuses=statuses)

    generated_at = datetime.now(timezone.utc).isoformat()
    rtnval = {
        "status": overall,
        "generated_at": generated_at,
        "subsystems": subsystems,
    }
    return rtnval


def handle_system_health(request: Request) -> Response:
    """
        ``GET /api/v1/system/health`` — aggregate subsystem-health
        summary for the admin surface.

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying the system-health
                  document, or an RFC 7807 problem response.
    """
    try:
        _require_admin_view(request)
        body = build_system_health_document(request=request)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def register_system_health_routes(
        *,
        app: Any,
        version_prefix: str
    ) -> None:
    """
        Attach the system-health route to a webworks application.

        Called from :func:`register_service_extensions` in
        :mod:`app_pychestrate_main` before ``app.startup``. Routes
        are queued until the infrastructure-ready phase and flushed
        there.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + SYSTEM_HEALTH_PATH
    app.attach_route(base, methods=["GET"])(handle_system_health)
    return


__all__ = [
    "SYSTEM_HEALTH_PATH",
    "SYSTEM_HEALTH_PERMISSION_KEY",
    "build_system_health_document",
    "handle_system_health",
    "register_system_health_routes",
]
