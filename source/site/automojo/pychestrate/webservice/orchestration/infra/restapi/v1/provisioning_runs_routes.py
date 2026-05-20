"""
.. module:: orchestration.infra.restapi.v1.provisioning_runs_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the provisioning tag.

.. moduleauthor:: Automation Mojo LLC

Implements the provisioning-run operations from
``specs/openapi/pychestrate.yaml``:

* ``POST /api/v1/projects/{project_id}/provisioning-runs``
* ``GET  /api/v1/projects/{project_id}/provisioning-runs``
* ``GET  /api/v1/projects/{project_id}/provisioning-runs/{run_id}``

Each handler follows the shape of
``webservice.orchestration.build.restapi.v1.build_runs_routes``:
cookie-or-api-key session validation, RBAC permission check, JSON
body decode, then delegation to the in-tree infra-orchestration
facade (``orchestration.infra.runs.service``).

The infra-runs domain models an :class:`InfraRun` directly --
the ``plan`` / ``apply`` / ``destroy`` actions are encoded on the
run row, and a plan summary is recorded on the run itself. There
is no separate ``ProvisioningPlan`` ORM table, so this PR exposes
the provisioning-run lifecycle (trigger / read / list) rather than
a separate plan resource. ``POST /provisioning-runs`` resolves the
driver, validates inputs + action support, and persists the run in
``PENDING``. The Layer-5 dispatch handoff is M2 work (see
``orchestration.infra.runs.service.trigger_run``); until then a
triggered provisioning run stays in ``PENDING`` / queued state.

Error responses are RFC 7807 problem documents emitted via
:mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.orchestration.infra.runs import (
    service as infra_service,
)
from automojo.pychestrate.webservice.orchestration.infra.runs.errors import (
    InfraDriverUnknownError,
    InfraEnvironmentStateError,
    InfraInputsInvalidError,
    InfraRunNotFoundError,
)
from automojo.pychestrate.webservice.orchestration.infra.runs.models import (
    InfraAction,
)
from automojo.pychestrate.webservice.projects import repository as projects_repo
from automojo.pychestrate.webservice.security.rbac import rbac_evaluator


PROVISIONING_RUNS_PATH_SUFFIX = "/provisioning-runs"
PROJECTS_PATH_PREFIX = "/projects"

PROVISIONING_READ_PERMISSION_KEY = "system:provisioning.read"
PROVISIONING_CREATE_PERMISSION_KEY = "system:provisioning.create"

DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 500

_LOGGER = logging.getLogger("pychestrate.provisioning.routes")


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


def _plan_summary_to_dict(summary: Any) -> Optional[Dict[str, Any]]:
    """
        Serialize a :class:`PlanSummary` read-model.

        :param summary: Plan summary or None.

        :returns: JSON-friendly dict or None.
    """
    if summary is None:
        rtnval = None
        return rtnval
    resource_ops: List[Dict[str, Any]] = []
    for op in summary.resource_ops:
        resource_ops.append({
            "resource_address": op.resource_address,
            "op": _enum_value_or_str(op.op),
            "module_path": op.module_path,
        })
    rtnval: Optional[Dict[str, Any]] = {
        "resources_to_add": summary.resources_to_add,
        "resources_to_change": summary.resources_to_change,
        "resources_to_destroy": summary.resources_to_destroy,
        "resource_ops": resource_ops,
    }
    return rtnval


def _infra_run_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize an :class:`InfraRunView` to the OpenAPI
        ``ProvisioningRun`` schema.

        :param view: Read-model returned by the infra facade.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "run_id": str(view.run_id),
        "project_id": str(view.project_id),
        "environment_id": str(view.environment_id),
        "driver_name": view.driver_name,
        "action": _enum_value_or_str(view.action),
        "state": _enum_value_or_str(view.state),
        "layer5_run_id": view.layer5_run_id,
        "actor_id": view.actor_id,
        "actor_role_set": list(view.actor_role_set or ()),
        "inputs": dict(view.inputs or {}),
        "inputs_canonical_sha256": view.inputs_canonical_sha256,
        "plan_summary": _plan_summary_to_dict(summary=view.plan_summary),
        "plan_artifact_ref": view.plan_artifact_ref,
        "plan_diff_digest_sha256": view.plan_diff_digest_sha256,
        "plan_issued_at": _iso_or_none(view.plan_issued_at),
        "replay_of": view.replay_of,
        "output_digest_sha256": view.output_digest_sha256,
        "failing_guard_rule_id": view.failing_guard_rule_id,
        "started_at": _iso_or_none(view.started_at),
        "finished_at": _iso_or_none(view.finished_at),
        "final_state_reason": view.final_state_reason,
    }
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/projects/{project_id}/provisioning-runs
# ---------------------------------------------------------------------------


def _resolve_action_or_abort(*, request: Request, raw: Any) -> InfraAction:
    """
        Coerce the ``action`` body field into an
        :class:`InfraAction`.

        :param request: Incoming webworks request.
        :param raw: Raw action value from the body.

        :returns: Resolved InfraAction.
    """
    if not isinstance(raw, str) or len(raw) == 0:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'action' is required.",
            extensions={"missing_fields": ["action"]},
        )
    try:
        rtnval = InfraAction(raw)
    except ValueError:
        supported = [member.value for member in InfraAction]
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'action' must be one of: {}.".format(
                ", ".join(supported),
            ),
            extensions={"action": raw, "supported_actions": supported},
        )
        rtnval = InfraAction.PLAN  # unreachable
    return rtnval


def handle_trigger_provisioning_run(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/provisioning-runs``

        Triggers a provisioning run against a named environment.
        Delegates to
        :func:`orchestration.infra.runs.service.trigger_run`.

        :param request: Incoming webworks request.

        :returns: JSON response (202) carrying the freshly-created
                  :class:`ProvisioningRun`, or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=PROVISIONING_CREATE_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        body = _decode_json_object_or_abort(request=request)

        environment_id = body.get("environment_id", None)
        if not isinstance(environment_id, str) or len(environment_id) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'environment_id' is required.",
                extensions={"missing_fields": ["environment_id"]},
            )

        driver_name = body.get("driver_name", None)
        if not isinstance(driver_name, str) or len(driver_name) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'driver_name' is required.",
                extensions={"missing_fields": ["driver_name"]},
            )

        action = _resolve_action_or_abort(
            request=request, raw=body.get("action", None),
        )

        driver_inputs = body.get("driver_inputs", {})
        if isinstance(driver_inputs, dict) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'driver_inputs' must be an object.",
            )

        actor_id: Optional[str] = None
        principal_user_id = getattr(principal, "user_id", None)
        if principal_user_id is not None:
            actor_id = str(principal_user_id)

        inputs = infra_service.InfraRunInputs(
            environment_id=environment_id,
            driver_name=driver_name,
            action=action,
            driver_inputs=dict(driver_inputs),
        )
        aspects = infra_service.InfraTriggerAspects(actor_id=actor_id)

        try:
            view = infra_service.trigger_run(
                db_session=db_session,
                project_id=project_id,
                inputs=inputs,
                aspects=aspects,
            )
        except InfraEnvironmentStateError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"environment_id": environment_id},
            )
            view = None  # unreachable
        except InfraDriverUnknownError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"driver_name": driver_name},
            )
            view = None  # unreachable
        except InfraInputsInvalidError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"driver_name": driver_name},
            )
            view = None  # unreachable

        _LOGGER.info(
            "pychestrate.provisioning.trigger project_id=%s driver=%s"
            " action=%s run_id=%s",
            project_id,
            driver_name,
            action.value,
            str(view.run_id),
        )

        body_dict = _infra_run_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=202)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/provisioning-runs
# ---------------------------------------------------------------------------


def handle_list_provisioning_runs(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/provisioning-runs``

        Query params: ``state``, ``environment_id``, ``page``,
        ``per_page``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with an ``{items, meta}``
                  page or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=PROVISIONING_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        state_filter = request.query_params.get("state", None)
        environment_filter = request.query_params.get("environment_id", None)
        page = _parse_positive_int(
            request=request,
            name="page",
            raw=request.query_params.get("page", None),
            default=1,
            minimum=1,
        )
        per_page = _parse_positive_int(
            request=request,
            name="per_page",
            raw=request.query_params.get("per_page", None),
            default=DEFAULT_PAGE_SIZE,
            minimum=MIN_PAGE_SIZE,
            maximum=MAX_PAGE_SIZE,
        )

        all_views = infra_service.list_infra_runs_for_project(
            db_session=db_session,
            project_id=project_id,
            environment_id=environment_filter,
            limit=MAX_PAGE_SIZE,
        )
        if state_filter is not None and len(state_filter) > 0:
            filtered: List[Any] = []
            for view in all_views:
                if _enum_value_or_str(view.state) == state_filter:
                    filtered.append(view)
            all_views = filtered

        total = len(all_views)
        offset = (page - 1) * per_page
        window = all_views[offset:offset + per_page]

        items: List[Dict[str, Any]] = []
        for view in window:
            items.append(_infra_run_view_to_dict(view=view))

        body = {
            "items": items,
            "meta": {
                "page": page,
                "per_page": per_page,
                "total": int(total),
                "next_cursor": None,
            },
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/provisioning-runs/{run_id}
# ---------------------------------------------------------------------------


def handle_read_provisioning_run(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/provisioning-runs/{run_id}``

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the provisioning-run
                  dict or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    run_id = request.path_params.get("run_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=PROVISIONING_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        try:
            view = infra_service.get_infra_run(
                db_session=db_session,
                run_id=run_id,
            )
        except InfraRunNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"run_id": run_id},
            )
            view = None  # unreachable

        if str(view.project_id) != str(project_id):
            _abort_problem(
                request=request,
                status=404,
                detail="Provisioning run does not belong to this project.",
                extensions={"project_id": project_id, "run_id": run_id},
            )

        body = _infra_run_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_provisioning_runs_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the provisioning-runs REST routes to a webworks
        app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + PROJECTS_PATH_PREFIX + "/{project_id}"
    app.attach_route(
        base + PROVISIONING_RUNS_PATH_SUFFIX, methods=["POST"],
    )(handle_trigger_provisioning_run)
    app.attach_route(
        base + PROVISIONING_RUNS_PATH_SUFFIX, methods=["GET"],
    )(handle_list_provisioning_runs)
    app.attach_route(
        base + PROVISIONING_RUNS_PATH_SUFFIX + "/{run_id}", methods=["GET"],
    )(handle_read_provisioning_run)

    _LOGGER.warning(
        "pychestrate.provisioning.routes.dispatch_not_wired: POST"
        " /provisioning-runs persists an infra run in PENDING; the"
        " Layer-5 dispatch handoff is M2 work"
        " (orchestration.infra.runs.service.trigger_run)."
    )
    return


__all__ = [
    "PROVISIONING_RUNS_PATH_SUFFIX",
    "PROVISIONING_READ_PERMISSION_KEY",
    "PROVISIONING_CREATE_PERMISSION_KEY",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "register_provisioning_runs_routes",
    "handle_trigger_provisioning_run",
    "handle_list_provisioning_runs",
    "handle_read_provisioning_run",
]
