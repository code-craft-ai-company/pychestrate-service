"""
.. module:: resources.restapi.v1.resources_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the per-resource surface.

.. moduleauthor:: Code Craft AI LLC

Exposes the per-resource read operations from the resources domain
(:mod:`webservice.resources.inventory`,
:mod:`...resources.health`, :mod:`...resources.usage_history`).

Routes attached by :func:`register_resources_routes`:

* ``GET /api/v1/resources/{resource_id}`` -- read one resource
* ``GET /api/v1/resources/{resource_id}/health`` -- current health
  record
* ``GET /api/v1/resources/{resource_id}/usage-history`` -- the
  resource usage timeline (newest first)

The health record is seeded on ``entity.resource.registered`` by the
M2 bus subscriber -- a resource that has never been probed answers
``404`` from the health endpoint.

Error responses are RFC 7807 problem documents emitted via
:mod:`api.problem_json_webworks`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.resources.health import (
    service as health_service,
)
from ccai.pychestrate.webservice.resources.health.errors import (
    HealthRecordNotFoundError,
)
from ccai.pychestrate.webservice.resources.inventory import (
    service as inventory_service,
)
from ccai.pychestrate.webservice.resources.inventory.errors import (
    ResourceNotFoundError,
)
from ccai.pychestrate.webservice.resources.usage_history import (
    service as usage_history_service,
)
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


RESOURCES_PATH = "/resources"

RESOURCES_READ_PERMISSION_KEY = "system:resources.read"

DEFAULT_TIMELINE_LIMIT = 200
MIN_TIMELINE_LIMIT = 1
MAX_TIMELINE_LIMIT = 1000

_LOGGER = logging.getLogger("pychestrate.resources.routes")


# ---------------------------------------------------------------------------
# Problem-flow plumbing
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks problem
        response so nested helpers can signal an error condition
        once and the top-level handler can convert it to a return
        value at the boundary.
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
    """
    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _resolve_db_session(request: Request) -> Optional[Any]:
    """
        Return the request-scoped db session or ``None``.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort 503.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session.
    """
    db_session = _resolve_db_session(request=request)
    if db_session is None:
        _abort_problem(
            request=request,
            status=503,
            detail="Request-scoped db_session not configured",
        )
    rtnval = db_session
    return rtnval


def _resolve_auth_principal(request: Request) -> Optional[Any]:
    """
        Return the ``AuthPrincipal`` attached by the session
        middleware, or ``None`` when the request is anonymous.

        :param request: Incoming webworks request.

        :returns: AuthPrincipal or None.
    """
    rtnval = getattr(request, "auth_principal", None)
    return rtnval


def _require_permission(
        *,
        request: Request,
        db_session: Any,
        permission_key: str
    ) -> Any:
    """
        Require the calling principal to hold ``permission_key``.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param permission_key: Required ``system:*`` permission key.

        :returns: The :class:`AuthPrincipal`.
    """
    principal = _resolve_auth_principal(request=request)
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
        permission_key=permission_key,
        now=now,
    )
    if decision.allowed is False:
        _abort_problem(
            request=request,
            status=403,
            detail="Permission denied: {}".format(permission_key),
            extensions={"required_permission": permission_key},
        )
    rtnval = principal
    return rtnval


def _parse_positive_int(
        *,
        request: Request,
        name: str,
        raw: Optional[str],
        default: int,
        minimum: int,
        maximum: Optional[int] = None
    ) -> int:
    """
        Coerce a positive-integer query param with bounds checking.

        :param request: Incoming webworks request.
        :param name: Query-param name (for error context).
        :param raw: Raw query value or None.
        :param default: Fallback when the param is absent.
        :param minimum: Lower bound (inclusive).
        :param maximum: Optional upper bound (inclusive).

        :returns: Coerced integer.
    """
    if raw is None or len(raw) == 0:
        rtnval = default
        return rtnval

    try:
        candidate = int(raw)
    except ValueError:
        _abort_problem(
            request=request,
            status=400,
            detail="Query param '{}' must be an integer.".format(name),
            extensions={"query_param": name, "raw_value": raw},
        )
        candidate = default  # unreachable

    if candidate < minimum:
        _abort_problem(
            request=request,
            status=400,
            detail="Query param '{}' must be >= {}.".format(name, minimum),
            extensions={"query_param": name, "raw_value": raw},
        )
    if maximum is not None and candidate > maximum:
        _abort_problem(
            request=request,
            status=400,
            detail="Query param '{}' must be <= {}.".format(name, maximum),
            extensions={"query_param": name, "raw_value": raw},
        )

    rtnval = candidate
    return rtnval


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _iso_or_none(value: Any) -> Optional[str]:
    """
        ISO-8601 serialize a datetime or return ``None``.

        :param value: Datetime or None.

        :returns: ISO-formatted string or None.
    """
    if value is None:
        rtnval = None
        return rtnval
    if isinstance(value, datetime):
        rtnval = value.isoformat()
        return rtnval
    rtnval = str(value)
    return rtnval


def _enum_value_or_str(value: Any) -> Optional[str]:
    """
        Return the ``.value`` of a string-enum or its ``str``.

        :param value: Enum instance or scalar.

        :returns: String value or None.
    """
    if value is None:
        rtnval = None
        return rtnval
    extracted = getattr(value, "value", None)
    if extracted is not None:
        rtnval = str(extracted)
        return rtnval
    rtnval = str(value)
    return rtnval


def _resource_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`ResourceView` to the OpenAPI ``Resource``
        schema.

        :param view: Resource read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "resource_id": str(view.resource_id),
        "project_id": str(view.project_id),
        "kind": view.kind,
        "display_name": view.display_name,
        "description": view.description,
        "identity_hash": view.identity_hash,
        "state": _enum_value_or_str(view.state),
        "tags": list(view.tags or ()),
        "attributes": dict(view.attributes or {}),
        "created_at": _iso_or_none(view.created_at),
        "updated_at": _iso_or_none(view.updated_at),
    }
    return rtnval


def _health_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`HealthView` to the OpenAPI
        ``ResourceHealth`` schema.

        :param view: Health read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "health_id": str(view.health_id),
        "resource_id": str(view.resource_id),
        "project_id": str(view.project_id),
        "probe_name": view.probe_name,
        "probe_period_seconds": int(view.probe_period_seconds),
        "last_outcome": _enum_value_or_str(view.last_outcome),
        "last_probe_at": _iso_or_none(view.last_probe_at),
        "last_pass_at": _iso_or_none(view.last_pass_at),
        "last_fail_at": _iso_or_none(view.last_fail_at),
        "next_probe_at": _iso_or_none(view.next_probe_at),
        "pass_count": int(view.pass_count),
        "fail_count": int(view.fail_count),
        "consecutive_failures": int(view.consecutive_failures),
        "last_error": view.last_error,
        "last_payload": dict(view.last_payload or {}),
    }
    return rtnval


def _usage_record_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`TimelineEventView` to the OpenAPI
        ``UsageRecord`` schema.

        :param view: Timeline-event read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "event_id": str(view.event_id),
        "source_event_id": str(view.source_event_id),
        "resource_id": str(view.resource_id),
        "project_id": str(view.project_id),
        "event_type": _enum_value_or_str(view.event_type),
        "actor_id": view.actor_id,
        "pod_event_group_id": view.pod_event_group_id,
        "at_ts": _iso_or_none(view.at_ts),
        "payload": dict(view.payload or {}),
        "annotations": dict(view.annotations or {}),
    }
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/resources/{resource_id}
# ---------------------------------------------------------------------------


def handle_read_resource(request: Request) -> Response:
    """
        ``GET /api/v1/resources/{resource_id}`` -- read one resource.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the ``Resource`` dict, or
                  a problem response.
    """
    resource_id = request.path_params.get("resource_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RESOURCES_READ_PERMISSION_KEY,
        )

        try:
            view = inventory_service.get_resource(
                db_session=db_session, resource_id=resource_id,
            )
        except ResourceNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"resource_id": resource_id},
            )
            view = None  # unreachable

        body_dict = _resource_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/resources/{resource_id}/health
# ---------------------------------------------------------------------------


def handle_read_resource_health(request: Request) -> Response:
    """
        ``GET /api/v1/resources/{resource_id}/health`` -- read the
        current health record for a resource.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the ``ResourceHealth``
                  dict, or a problem response.
    """
    resource_id = request.path_params.get("resource_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RESOURCES_READ_PERMISSION_KEY,
        )

        try:
            view = health_service.get_health_record(
                db_session=db_session, resource_id=resource_id,
            )
        except HealthRecordNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"resource_id": resource_id},
            )
            view = None  # unreachable

        body_dict = _health_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/resources/{resource_id}/usage-history
# ---------------------------------------------------------------------------


def handle_list_resource_usage_history(request: Request) -> Response:
    """
        ``GET /api/v1/resources/{resource_id}/usage-history`` -- list
        the usage timeline for a resource (newest first).

        Query param: ``limit`` (1..1000, default 200).

        :param request: Incoming webworks request.

        :returns: JSON response (200) with a ``{items, meta}`` page,
                  or a problem response.
    """
    resource_id = request.path_params.get("resource_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RESOURCES_READ_PERMISSION_KEY,
        )

        limit = _parse_positive_int(
            request=request,
            name="limit",
            raw=request.query_params.get("limit", None),
            default=DEFAULT_TIMELINE_LIMIT,
            minimum=MIN_TIMELINE_LIMIT,
            maximum=MAX_TIMELINE_LIMIT,
        )

        views = usage_history_service.list_timeline(
            db_session=db_session,
            resource_id=resource_id,
            limit=limit,
        )
        items: List[Dict[str, Any]] = []
        for view in views:
            items.append(_usage_record_view_to_dict(view=view))

        body = {
            "items": items,
            "meta": {
                "page": 1,
                "per_page": len(items),
                "total": len(items),
                "next_cursor": None,
            },
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_resources_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the per-resource REST routes to a webworks app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + RESOURCES_PATH

    app.attach_route(
        base + "/{resource_id}", methods=["GET"],
    )(handle_read_resource)
    app.attach_route(
        base + "/{resource_id}/health", methods=["GET"],
    )(handle_read_resource_health)
    app.attach_route(
        base + "/{resource_id}/usage-history", methods=["GET"],
    )(handle_list_resource_usage_history)

    _LOGGER.info(
        "pychestrate.resources.routes registered: 3 routes under %s",
        base,
    )
    return


__all__ = [
    "RESOURCES_PATH",
    "RESOURCES_READ_PERMISSION_KEY",
    "DEFAULT_TIMELINE_LIMIT",
    "MAX_TIMELINE_LIMIT",
    "register_resources_routes",
    "handle_read_resource",
    "handle_read_resource_health",
    "handle_list_resource_usage_history",
]
