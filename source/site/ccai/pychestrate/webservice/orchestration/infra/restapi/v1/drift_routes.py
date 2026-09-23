"""
.. module:: orchestration.infra.restapi.v1.drift_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the drift tag.

.. moduleauthor:: Code Craft AI LLC

Implements the drift-detection operations from
``specs/openapi/pychestrate.yaml``:

* ``GET  /api/v1/projects/{project_id}/environments/{environment_id}/drift``
* ``POST /api/v1/projects/{project_id}/environments/{environment_id}/drift:check``

Each handler follows the shape of
``webservice.orchestration.build.restapi.v1.build_runs_routes``:
cookie-or-api-key session validation, RBAC permission check, then
delegation to the in-tree drift-detection facade
(``orchestration.infra.drift.service``).

The drift GET surfaces the latest drift run for an environment as
the current drift status -- the drift domain models a
:class:`DriftRun` directly; the most-recent run holds the latest
drift report. It also carries the environment's recent drift runs
(``history``), its drift schedule, and whether a manual check can
start (``check_available`` / ``check_unavailable_reason``): a manual
check borrows the schedule's checker, and nothing in this release
creates a drift schedule, so the environment detail page can say so
instead of letting "Check Drift" dead-end on a 409 (audit ORC-39). ``POST .../drift:check`` triggers a manual drift run
via :func:`orchestration.infra.drift.service.run_now`, which
borrows the environment's drift schedule's checker. The Layer-5
dispatch handoff is M2 work; until then a triggered drift run
stays in ``PENDING`` / queued state.

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
from ccai.pychestrate.webservice.orchestration.infra.drift import (
    service as drift_service,
)
from ccai.pychestrate.webservice.orchestration.infra.drift.errors import (
    DriftScheduleNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.infra.environment import (
    service as environment_service,
)
from ccai.pychestrate.webservice.orchestration.infra.environment.errors import (
    EnvironmentNotFoundError,
)
from ccai.pychestrate.webservice.projects import repository as projects_repo
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


ENVIRONMENTS_PATH_SUFFIX = "/environments"
DRIFT_PATH_SUFFIX = "/drift"
DRIFT_CHECK_PATH_SUFFIX = "/drift:check"
PROJECTS_PATH_PREFIX = "/projects"

DRIFT_READ_PERMISSION_KEY = "system:drift.read"
DRIFT_CHECK_PERMISSION_KEY = "system:drift.check"

# Honest 202 detail for POST /drift:check -- the Layer-5
# dispatch handoff is M2 work, so a recorded drift run does not
# progress past PENDING in this release. Surfaced in the
# response body so clients do not imply the check is running.
DRIFT_CHECK_RECORDED_DETAIL = (
    "Drift check recorded. Automatic processing is not available"
    " in this release; the run will remain PENDING until the"
    " dispatch handoff ships."
)

#: Why drift detection is a preview -- carried by the drift status.
DRIFT_PREVIEW_DETAIL = (
    "Drift detection is a preview: a drift check is recorded, but nothing"
    " processes it yet, so the run stays pending and reports no drift."
)

#: Why a manual drift check cannot start for an environment with no
#: drift schedule (the check borrows the schedule's checker).
DRIFT_NO_SCHEDULE_REASON = (
    "This environment has no drift schedule, and drift schedules cannot be"
    " set up from the API or the UI yet, so a drift check cannot start."
)

#: How many recent drift runs the drift status carries.
DRIFT_HISTORY_LIMIT = 20

_LOGGER = logging.getLogger("pychestrate.drift.routes")


# ---------------------------------------------------------------------------
# Problem-flow plumbing
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks
        problem response so nested helpers can signal an error
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


def _require_environment_in_project(
        *,
        request: Request,
        db_session: Any,
        project_id: str,
        environment_id: str
    ) -> Any:
    """
        Resolve the environment, aborting 404 when it is missing
        or belongs to a different project.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param project_id: Project UUID from the path.
        :param environment_id: Environment UUID from the path.

        :returns: EnvironmentView read-model.
    """
    try:
        view = environment_service.get_environment(
            db_session=db_session,
            environment_id=environment_id,
        )
    except EnvironmentNotFoundError as xcpt:
        _abort_problem(
            request=request,
            status=404,
            detail=str(xcpt),
            extensions={"environment_id": environment_id},
        )
        view = None  # unreachable

    if str(view.project_id) != str(project_id):
        _abort_problem(
            request=request,
            status=404,
            detail="Environment does not belong to this project.",
            extensions={
                "project_id": project_id,
                "environment_id": environment_id,
            },
        )
    rtnval = view
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


def _enum_value_or_str(value: Any) -> str:
    """
        Return the ``.value`` of a string-enum or its ``str``.

        :param value: Enum instance or scalar.

        :returns: String value.
    """
    extracted = getattr(value, "value", None)
    if extracted is not None:
        rtnval = str(extracted)
        return rtnval
    rtnval = str(value)
    return rtnval


def _drift_run_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`DriftRunView` to the OpenAPI
        ``DriftReport`` schema.

        :param view: Read-model returned by the drift facade.

        :returns: JSON-friendly dict.
    """
    report_payload: Optional[Dict[str, Any]] = None
    if view.report_payload is not None:
        report_payload = dict(view.report_payload)
    rtnval: Dict[str, Any] = {
        "run_id": str(view.run_id),
        "project_id": str(view.project_id),
        "environment_id": str(view.environment_id),
        "checker_name": view.checker_name,
        "state": _enum_value_or_str(view.state),
        "trigger_kind": _enum_value_or_str(view.trigger_kind),
        "layer5_run_id": view.layer5_run_id,
        "scheduled_for": _iso_or_none(view.scheduled_for),
        "ran_at": _iso_or_none(view.ran_at),
        "drift_count": view.drift_count,
        "added": view.added,
        "changed": view.changed,
        "destroyed": view.destroyed,
        "diff_digest_sha256": view.diff_digest_sha256,
        "report_blob_key": view.report_blob_key,
        "final_state_reason": view.final_state_reason,
        "report_payload": report_payload,
    }
    return rtnval


def _schedule_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`DriftScheduleView` for the drift status.

        :param view: Schedule read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "checker_name": view.checker_name,
        "cron_expression": view.cron_expression,
        "enabled": bool(view.enabled),
        "updated_at": _iso_or_none(view.updated_at),
    }
    return rtnval


def _find_schedule(*, db_session: Any, project_id: str, environment_id: str) -> Optional[Any]:
    """
        The environment's drift schedule, or ``None``.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Project UUID.
        :param environment_id: Environment UUID.

        :returns: DriftScheduleView or None.
    """
    try:
        rtnval = drift_service.get_schedule(
            db_session=db_session,
            project_id=project_id,
            environment_id=environment_id,
        )
    except DriftScheduleNotFoundError:
        rtnval = None
    return rtnval


# ---------------------------------------------------------------------------
# GET .../environments/{environment_id}/drift
# ---------------------------------------------------------------------------


def handle_get_drift_status(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/environments/{environment_id}/drift``

        Returns the latest drift run for the environment as its
        current drift status. The response carries
        ``{environment_id, has_report, latest_report}`` where
        ``latest_report`` is ``null`` until a drift run exists, plus
        ``history`` (up to :data:`DRIFT_HISTORY_LIMIT` recent runs,
        newest first), ``schedule`` (or ``null``),
        ``check_available`` / ``check_unavailable_reason``,
        ``dispatch_available`` (always ``false``) and ``detail``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the drift status or a
                  problem response.
    """
    project_id = request.path_params.get("project_id", "")
    environment_id = request.path_params.get("environment_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=DRIFT_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )
        _require_environment_in_project(
            request=request,
            db_session=db_session,
            project_id=project_id,
            environment_id=environment_id,
        )

        runs = drift_service.list_drift_runs_for_environment(
            db_session=db_session,
            environment_id=environment_id,
            limit=DRIFT_HISTORY_LIMIT,
        )
        history = [_drift_run_view_to_dict(view=run) for run in runs]

        latest_report: Optional[Dict[str, Any]] = None
        if len(history) > 0:
            latest_report = history[0]

        schedule = _find_schedule(
            db_session=db_session,
            project_id=project_id,
            environment_id=environment_id,
        )

        body = {
            "environment_id": environment_id,
            "has_report": latest_report is not None,
            "latest_report": latest_report,
            "history": history,
            "schedule": _schedule_view_to_dict(view=schedule) if schedule is not None else None,
            "check_available": schedule is not None,
            "check_unavailable_reason": None if schedule is not None else DRIFT_NO_SCHEDULE_REASON,
            "dispatch_available": False,
            "detail": DRIFT_PREVIEW_DETAIL,
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# POST .../environments/{environment_id}/drift:check
# ---------------------------------------------------------------------------


def handle_trigger_drift_check(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/environments/{environment_id}/drift:check``

        Triggers a manual drift check for the environment.
        Delegates to
        :func:`orchestration.infra.drift.service.run_now`, which
        borrows the environment's drift schedule's checker. When
        the environment has no drift schedule the facade raises
        :class:`DriftScheduleNotFoundError` and this handler
        responds 409.

        The 202 response is honest about what happened: the run
        is RECORDED (persisted in ``PENDING``) but automatic
        processing is not available in this release, so the body
        carries ``dispatch_available: false`` and a ``detail``
        message saying so alongside the ``DriftReport`` fields.

        :param request: Incoming webworks request.

        :returns: JSON response (202) carrying the freshly-created
                  :class:`DriftReport` plus the
                  ``dispatch_available`` / ``detail`` honesty
                  fields, or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    environment_id = request.path_params.get("environment_id", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=DRIFT_CHECK_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )
        _require_environment_in_project(
            request=request,
            db_session=db_session,
            project_id=project_id,
            environment_id=environment_id,
        )

        actor_id: Optional[str] = None
        principal_user_id = getattr(principal, "user_id", None)
        if principal_user_id is not None:
            actor_id = str(principal_user_id)

        try:
            view = drift_service.run_now(
                db_session=db_session,
                project_id=project_id,
                environment_id=environment_id,
                actor_id=actor_id,
            )
        except DriftScheduleNotFoundError:
            _abort_problem(
                request=request,
                status=409,
                detail=DRIFT_NO_SCHEDULE_REASON,
                extensions={"environment_id": environment_id, "reason": "no_drift_schedule"},
            )
            view = None  # unreachable

        _LOGGER.info(
            "pychestrate.drift.check project_id=%s environment_id=%s run_id=%s",
            project_id,
            environment_id,
            str(view.run_id),
        )

        body_dict = _drift_run_view_to_dict(view=view)
        body_dict["dispatch_available"] = False
        body_dict["detail"] = DRIFT_CHECK_RECORDED_DETAIL
        rtnval: Response = JSONResponse(content=body_dict, status_code=202)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_drift_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the drift-detection REST routes to a webworks app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = (
        version_prefix
        + PROJECTS_PATH_PREFIX
        + "/{project_id}"
        + ENVIRONMENTS_PATH_SUFFIX
        + "/{environment_id}"
    )
    app.attach_route(
        base + DRIFT_PATH_SUFFIX, methods=["GET"],
    )(handle_get_drift_status)
    app.attach_route(
        base + DRIFT_CHECK_PATH_SUFFIX, methods=["POST"],
    )(handle_trigger_drift_check)

    _LOGGER.warning(
        "pychestrate.drift.routes.dispatch_not_wired: POST"
        " /drift:check persists a drift run in PENDING; the"
        " Layer-5 dispatch handoff is M2 work"
        " (orchestration.infra.drift.service.run_now)."
    )
    return


__all__ = [
    "DRIFT_HISTORY_LIMIT",
    "DRIFT_NO_SCHEDULE_REASON",
    "DRIFT_PREVIEW_DETAIL",
    "DRIFT_PATH_SUFFIX",
    "DRIFT_CHECK_PATH_SUFFIX",
    "DRIFT_READ_PERMISSION_KEY",
    "DRIFT_CHECK_PERMISSION_KEY",
    "DRIFT_CHECK_RECORDED_DETAIL",
    "register_drift_routes",
    "handle_get_drift_status",
    "handle_trigger_drift_check",
]
