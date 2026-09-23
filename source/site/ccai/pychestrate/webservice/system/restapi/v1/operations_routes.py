"""
.. module:: system.restapi.v1.operations_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks routes for liveness, readiness and Prometheus
               metrics.

.. moduleauthor:: Code Craft AI LLC

Top-level operator endpoints (not under ``/api/v1``, where probes and
scrapers conventionally look); see :mod:`system.operations` for what
each reports and why it needs no session:

* ``GET /livez`` and ``GET /__health/live`` -- ``{"status": "live"}``.
* ``GET /readyz``, ``GET /healthz`` and ``GET /__health/ready`` --
  200 ``{"status": "ready", ...}`` or 503
  ``{"status": "not_ready", "failing": [...]}``.
* ``GET /metrics`` -- Prometheus text exposition, gated by the scrape
  token or an explicit public opt-in.

They are listed, with reasons, in
:data:`security.auth.anonymous_access.ANONYMOUS_OPERATIONS_ENDPOINTS`
and pass the first-run setup gate.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.system import operations
from ccai.pychestrate.webservice.system.prometheus import EXPOSITION_CONTENT_TYPE


def _runtime_environment() -> str:
    """
        The configured runtime environment, for the metrics info
        family.

        :returns: Environment name, ``unknown`` when unresolvable.
    """
    try:
        from ccai.thisapp.wellknown import ThisApplicationSingleton
        from ccai.pychestrate.webservice.pychestrate_variables import (
            PychestrateVariablesDesc,
        )

        value = ThisApplicationSingleton().get_variable_value(
            PychestrateVariablesDesc.PYCHESTRATE_RUNTIME_ENVIRONMENT
        )
        rtnval = str(value) if value else "unknown"
    except Exception:  # noqa: BLE001 -- a label must never fail the scrape
        rtnval = "unknown"
    return rtnval


def handle_liveness(request: Request) -> Response:
    """
        ``GET /livez`` -- the process answers.

        :param request: Incoming webworks request.

        :returns: 200 ``{"status": "live"}``.
    """
    rtnval: Response = JSONResponse(content={"status": "live"}, status_code=200)
    return rtnval


def handle_readiness(request: Request) -> Response:
    """
        ``GET /readyz`` -- the process can serve (database reachable).

        :param request: Incoming webworks request.

        :returns: 200 when ready, 503 with the failing check names.
    """
    result = operations.evaluate_readiness()
    checks = {name: ("ok" if passed else "failing") for name, passed in sorted(result.checks.items())}
    if result.ready is True:
        body: Dict[str, Any] = {"status": "ready", "checks": checks}
        rtnval: Response = JSONResponse(content=body, status_code=200)
        return rtnval
    body = {"status": "not_ready", "failing": result.failing(), "checks": checks}
    rtnval = JSONResponse(content=body, status_code=503)
    return rtnval


def handle_metrics(request: Request) -> Response:
    """
        ``GET /metrics`` -- Prometheus text exposition.

        :param request: Incoming webworks request.

        :returns: 200 exposition text, or a 401 / 403 problem response.
    """
    authorization = None
    try:
        authorization = request.headers.get("Authorization", None)
    except Exception:  # noqa: BLE001 -- treat as no credentials
        authorization = None

    decision = operations.metrics_access(authorization=authorization)
    if decision.allowed is False:
        rtnval = problem_response_for_http_status(
            status=decision.status,
            detail=decision.detail,
            instance=request.path,
        )
        if decision.status == 401:
            rtnval.headers["WWW-Authenticate"] = 'Bearer realm="pychestrate-metrics"'
        return rtnval

    body = operations.render_metrics(runtime_environment=_runtime_environment())
    rtnval = Response(
        status_code=200,
        body=body.encode("utf-8"),
        headers={
            "Content-Type": EXPOSITION_CONTENT_TYPE,
            "Cache-Control": "no-store",
        },
    )
    return rtnval


def register_operations_routes(*, app: Any) -> None:
    """
        Attach the liveness, readiness and metrics routes.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.

        :returns: None.
    """
    for path in operations.LIVENESS_PATHS:
        app.attach_route(path, methods=["GET"])(handle_liveness)
    for path in operations.READINESS_PATHS:
        app.attach_route(path, methods=["GET"])(handle_readiness)
    app.attach_route(operations.METRICS_PATH, methods=["GET"])(handle_metrics)
    return


__all__ = [
    "handle_liveness",
    "handle_metrics",
    "handle_readiness",
    "register_operations_routes",
]
