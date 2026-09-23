"""
.. module:: metrics.restapi.v1.metric_alerts_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the metric_alerts tag.

.. moduleauthor:: Code Craft AI LLC

Implements the metric-alert-rule operations from
``specs/openapi/pychestrate.yaml``:

* ``GET  /api/v1/projects/{project_id}/metric-alerts``
* ``POST /api/v1/projects/{project_id}/metric-alerts``

Each handler follows the shape of
``orchestration.build.restapi.v1.build_runs_routes`` and delegates
to the in-tree alerts facade (``metrics.alerts.service``). Error
responses are RFC 7807 problem documents emitted via
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
from ccai.pychestrate.webservice.metrics.alerts import (
    service as alerts_service,
)
from ccai.pychestrate.webservice.metrics.alerts.errors import (
    AlertRuleConfigInvalidError,
    AlertRuleConflictError,
    AlertRuleKindUnknownError,
)
from ccai.pychestrate.webservice.metrics.alerts.models import (
    AlertSeverity,
)
from ccai.pychestrate.webservice.projects import repository as projects_repo
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


PROJECTS_PATH_PREFIX = "/projects"
ALERTS_PATH_SUFFIX = "/metric-alerts"

METRIC_ALERTS_READ_PERMISSION_KEY = "system:metric_alerts.read"
METRIC_ALERTS_WRITE_PERMISSION_KEY = "system:metric_alerts.write"

_LOGGER = logging.getLogger("pychestrate.metric_alerts.routes")


# ---------------------------------------------------------------------------
# Problem-flow plumbing
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
    """
        Internal control-flow exception carrying a webworks
        problem response.
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


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort 503.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session.
    """
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        _abort_problem(
            request=request,
            status=503,
            detail="Request-scoped db_session not configured",
        )
    rtnval = db_session
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


def _require_project_exists(
        *,
        request: Request,
        db_session: Any,
        project_id: str
    ) -> Any:
    """
        Look up the project row, aborting 404 when not found.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param project_id: Project UUID from the path.

        :returns: Project ORM row.
    """
    row = projects_repo.get_project_by_id(
        db_session=db_session,
        project_id=project_id,
    )
    if row is None:
        _abort_problem(
            request=request,
            status=404,
            detail="Project not found.",
            extensions={"project_id": project_id},
        )
    rtnval = row
    return rtnval


def _decode_json_object_or_abort(*, request: Request) -> Dict[str, Any]:
    """
        Decode the request body as a JSON object, aborting with
        422 on missing / malformed / non-dict bodies.

        :param request: Incoming webworks request.

        :returns: Decoded dict.
    """
    try:
        payload = request.json()
    except Exception:
        payload = None

    if payload is None:
        _abort_problem(
            request=request,
            status=422,
            detail="Request body must be JSON.",
        )
    if isinstance(payload, dict) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Request body must be a JSON object.",
        )

    rtnval = payload
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


def _live_state_to_dict(live: Any) -> Dict[str, Any]:
    """
        Serialize an :class:`AlertLiveStateView` to the OpenAPI
        ``MetricAlertLiveState`` schema.

        :param live: Live-state read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "state": live.state.value,
        "last_value": live.last_value,
        "last_threshold": live.last_threshold,
        "last_reason": live.last_reason,
        "last_evaluated_at": _iso_or_none(live.last_evaluated_at),
        "last_state_changed_at": _iso_or_none(live.last_state_changed_at),
        "fired_at": _iso_or_none(live.fired_at),
        "resolved_at": _iso_or_none(live.resolved_at),
        "fire_count": int(live.fire_count),
        "resolve_count": int(live.resolve_count),
    }
    return rtnval


def _alert_rule_view_to_dict(view: Any, *, live: Any) -> Dict[str, Any]:
    """
        Serialize an :class:`AlertRuleView` to the OpenAPI
        ``MetricAlertRule`` schema.

        :param view: Alert-rule read-model.
        :param live: The rule's :class:`AlertLiveStateView` (state
                     ``unknown`` until the evaluator has run).

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "rule_id": str(view.rule_id),
        "project_id": str(view.project_id),
        "name": view.name,
        "description": view.description,
        "kind": view.kind,
        "config": dict(view.config or {}),
        "severity": view.severity.value,
        "enabled": bool(view.enabled),
        "notification_targets": list(view.notification_targets or ()),
        "created_by": view.created_by,
        "created_at": _iso_or_none(view.created_at),
        "updated_at": _iso_or_none(view.updated_at),
        "live_state": _live_state_to_dict(live=live),
    }
    return rtnval


def _rule_to_dict(*, db_session: Any, view: Any) -> Dict[str, Any]:
    """
        Serialize a rule together with its live state.

        :param db_session: Active SQLAlchemy session.
        :param view: Alert-rule read-model.

        :returns: JSON-friendly dict.
    """
    live = alerts_service.get_live_state(
        db_session=db_session,
        rule_id=str(view.rule_id),
    )
    rtnval = _alert_rule_view_to_dict(view=view, live=live)
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/metric-alerts
# ---------------------------------------------------------------------------


def handle_list_metric_alerts(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/metric-alerts``

        Query param: ``enabled_only`` (``"true"`` filters to
        enabled rules). Each item carries ``live_state``: the
        evaluator's latest verdict (``unknown`` until the rule has
        been evaluated).

        :param request: Incoming webworks request.

        :returns: JSON response (200) with an ``{items, meta}``
                  page, or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=METRIC_ALERTS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        enabled_only_raw = request.query_params.get("enabled_only", None)
        enabled_only = False
        if enabled_only_raw is not None and enabled_only_raw.lower() == "true":
            enabled_only = True

        views = alerts_service.list_alert_rules_for_project(
            db_session=db_session,
            project_id=project_id,
            enabled_only=enabled_only,
        )
        items: List[Dict[str, Any]] = []
        for view in views:
            items.append(_rule_to_dict(db_session=db_session, view=view))

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
# POST /api/v1/projects/{project_id}/metric-alerts
# ---------------------------------------------------------------------------


def _resolve_severity(
        *,
        request: Request,
        raw: Any
    ) -> AlertSeverity:
    """
        Coerce the ``severity`` field to an :class:`AlertSeverity`.

        :param request: Incoming webworks request.
        :param raw: Raw ``severity`` value from the body.

        :returns: AlertSeverity enum member.
    """
    if raw is None:
        rtnval = AlertSeverity.WARNING
        return rtnval
    if isinstance(raw, str) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'severity' must be a string.",
        )
    for member in AlertSeverity:
        if member.value == raw:
            rtnval = member
            return rtnval
    _abort_problem(
        request=request,
        status=422,
        detail="Field 'severity' must be one of: info, warning, critical.",
        extensions={"severity": raw},
    )
    rtnval = AlertSeverity.WARNING  # unreachable
    return rtnval


def handle_create_metric_alert(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/metric-alerts``

        Creates a metric-alert rule. Delegates to
        :func:`metrics.alerts.service.create_alert_rule`.

        :param request: Incoming webworks request.

        :returns: JSON response (201) with the ``MetricAlertRule``
                  shape, or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=METRIC_ALERTS_WRITE_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        body = _decode_json_object_or_abort(request=request)

        name = body.get("name", None)
        if not isinstance(name, str) or len(name) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'name' is required.",
                extensions={"missing_fields": ["name"]},
            )

        kind = body.get("kind", None)
        if not isinstance(kind, str) or len(kind) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'kind' is required.",
                extensions={"missing_fields": ["kind"]},
            )

        config = body.get("config", {})
        if isinstance(config, dict) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'config' must be an object.",
            )

        description = body.get("description", "")
        if isinstance(description, str) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'description' must be a string.",
            )

        severity = _resolve_severity(
            request=request,
            raw=body.get("severity", None),
        )

        enabled = body.get("enabled", True)
        if isinstance(enabled, bool) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'enabled' must be a boolean.",
            )

        notification_targets = body.get("notification_targets", [])
        if isinstance(notification_targets, list) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'notification_targets' must be an array.",
            )

        actor_id: Optional[str] = None
        principal_user_id = getattr(principal, "user_id", None)
        if principal_user_id is not None:
            actor_id = str(principal_user_id)

        try:
            view = alerts_service.create_alert_rule(
                db_session=db_session,
                project_id=project_id,
                name=name,
                kind=kind,
                config=dict(config),
                description=description,
                severity=severity,
                enabled=enabled,
                notification_targets=list(notification_targets),
                actor_id=actor_id,
            )
        except AlertRuleConflictError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"name": name},
            )
            view = None  # unreachable
        except AlertRuleKindUnknownError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"kind": kind},
            )
            view = None  # unreachable
        except AlertRuleConfigInvalidError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
            )
            view = None  # unreachable

        _LOGGER.info(
            "pychestrate.metric_alerts.create project_id=%s rule_id=%s",
            project_id,
            str(view.rule_id),
        )

        body_dict = _rule_to_dict(db_session=db_session, view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_metric_alerts_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the metric-alerts REST routes to a webworks app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + PROJECTS_PATH_PREFIX + "/{project_id}"
    app.attach_route(
        base + ALERTS_PATH_SUFFIX, methods=["GET"],
    )(handle_list_metric_alerts)
    app.attach_route(
        base + ALERTS_PATH_SUFFIX, methods=["POST"],
    )(handle_create_metric_alert)
    return


__all__ = [
    "ALERTS_PATH_SUFFIX",
    "METRIC_ALERTS_READ_PERMISSION_KEY",
    "METRIC_ALERTS_WRITE_PERMISSION_KEY",
    "register_metric_alerts_routes",
    "handle_list_metric_alerts",
    "handle_create_metric_alert",
]
