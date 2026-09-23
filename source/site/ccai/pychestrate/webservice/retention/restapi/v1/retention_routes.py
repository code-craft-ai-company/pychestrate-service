"""
.. module:: retention.restapi.v1.retention_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/retention/policies.

.. moduleauthor:: Code Craft AI LLC

The production webservice runs on ``ccai.webworks`` (see
:mod:`app_pychestrate_main`). This module provides the
webworks-native ``retention`` controller.

Four routes:

* ``POST /api/v1/retention/policies``
  — create a new retention policy.
* ``GET  /api/v1/retention/policies``
  — list policies (optional ``scope_level`` / ``project_id`` /
  ``state`` query filters).
* ``GET  /api/v1/retention/policies/{policy_id}``
  — read one policy.
* ``POST /api/v1/retention/policies/{policy_id}/publish``
  — transition a policy into PUBLISHED.

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Optional

from ccai.errors.exceptions import SemanticError
from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.rest_authz import AUTHENTICATED_ONLY, require_rest_permission
from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.retention import (
    service as retention_service,
)
from ccai.pychestrate.webservice.retention.exceptions import (
    PolicyAlreadyExistsError,
    PolicyNotFoundError,
    PolicyStateTransitionError,
    UnsupportedRetentionActionError,
)
from ccai.pychestrate.webservice.retention.models import (
    ActionStep,
    PolicyScopeLevel,
    PolicyState,
    SelectorClause,
)


RETENTION_PATH = "/retention/policies"

DEFAULT_INTERVAL_MINUTES = 1440
DEFAULT_BATCH_SIZE = 500
DEFAULT_MAX_ATTEMPTS = 3


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks problem
        response so nested helpers can signal an error condition once
        and the handler can convert it to a return at the boundary.
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
        extensions: Optional[dict] = None
    ) -> None:
    """
        Build a problem response and raise :class:`_ProblemAbort`.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param extensions: Optional extension members.

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
        Return the request-scoped db session.

        :param request: Incoming webworks request.

        :returns: Session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _resolve_actor_user_id(request: Request) -> Optional[str]:
    """
        Return the authenticated actor's user id.

        :param request: Incoming webworks request.

        :returns: User id string or None.
    """
    rtnval = getattr(request, "actor_user_id", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort with a 503.

        :param request: Incoming webworks request.

        :returns: Session.
        :raises: :class:`_ProblemAbort` (503).
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


def _decode_json_or_abort(*, request: Request) -> dict:
    """
        Decode the request body as JSON, aborting with a 400 when
        the body is missing or non-dict.

        :param request: Incoming webworks request.

        :returns: Decoded dict.
        :raises: :class:`_ProblemAbort` (400).
    """
    try:
        payload = request.json()
    except Exception:
        payload = None

    if payload is None:
        _abort_problem(
            request=request, status=400, detail="Request body must be JSON"
        )
    if not isinstance(payload, dict):
        _abort_problem(
            request=request,
            status=400,
            detail="Request body must be a JSON object",
        )

    rtnval = payload
    return rtnval


def _parse_scope_level_or_abort(
        *, request: Request, raw: str
    ) -> PolicyScopeLevel:
    """
        Coerce a ``scope_level`` string to the enum, aborting 400
        with the raw value as an extension on unknown values.

        :param request: Incoming webworks request.
        :param raw: Raw string value.

        :returns: :class:`PolicyScopeLevel`.
    """
    normalized = raw.strip().upper()
    try:
        scope_level = PolicyScopeLevel[normalized]
    except KeyError:
        _abort_problem(
            request=request,
            status=400,
            detail="Unknown scope_level: {}".format(raw),
            extensions={"scope_level": raw},
        )

    rtnval = scope_level
    return rtnval


def _parse_state_or_abort(
        *, request: Request, raw: str
    ) -> PolicyState:
    """
        Coerce a ``state`` string to the enum, aborting 400 on
        unknown values.

        :param request: Incoming webworks request.
        :param raw: Raw string value.

        :returns: :class:`PolicyState`.
    """
    normalized = raw.strip().upper()
    try:
        state = PolicyState[normalized]
    except KeyError:
        _abort_problem(
            request=request,
            status=400,
            detail="Unknown state: {}".format(raw),
            extensions={"state": raw},
        )

    rtnval = state
    return rtnval


def _parse_selector(*, payload: Optional[dict]) -> SelectorClause:
    """
        Build a :class:`SelectorClause` from a payload subobject.
        ``None`` collapses to an all-defaults selector when the
        body field is missing.

        :param payload: Selector subobject from the request body.

        :returns: :class:`SelectorClause`.
    """
    raw = payload if payload is not None else {}
    rtnval = SelectorClause(
        tag_expression=raw.get("tag_expression", "") or "",
        age_days=int(raw.get("age_days", 0) or 0),
        size_bytes_over=int(raw.get("size_bytes_over", 0) or 0),
        project_ids=tuple(raw.get("project_ids", []) or []),
    )
    return rtnval


def _parse_action_chain(*, payload: Optional[list]) -> List[ActionStep]:
    """
        Build a list of :class:`ActionStep` from the payload
        subarray. ``None`` / empty produces an empty chain — the
        service layer will reject empty chains with SemanticError.

        :param payload: Action-chain subarray from the body.

        :returns: List of :class:`ActionStep`.
    """
    rtnval: List[ActionStep] = []
    raw_steps = payload if payload is not None else []
    for raw in raw_steps:
        step = ActionStep(
            action_name=str(raw.get("action_name", "")),
            parameters=raw.get("parameters", {}) or {},
            wait_days_after_previous=int(
                raw.get("wait_days_after_previous", 0) or 0
            ),
        )
        rtnval.append(step)
    return rtnval


def _policy_to_dict(policy: Any) -> dict:
    """
        Render a :class:`RetentionPolicy` ORM row as the response
        dict.

        :param policy: ORM row.

        :returns: JSON-friendly dict.
    """
    rtnval = {
        "policy_id": str(policy.policy_id),
        "name": policy.name,
        "data_class": policy.data_class,
        "scope_level": policy.scope_level.value,
        "project_id": (
            str(policy.project_id) if policy.project_id is not None else None
        ),
        "state": policy.state.value,
        "interval_minutes": int(policy.interval_minutes),
        "batch_size": int(policy.batch_size),
        "max_attempts": int(policy.max_attempts),
        "created_at": (
            policy.created_at.isoformat()
            if policy.created_at is not None else None
        ),
        "updated_at": (
            policy.updated_at.isoformat()
            if policy.updated_at is not None else None
        ),
        "published_at": (
            policy.published_at.isoformat()
            if policy.published_at is not None else None
        ),
    }
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_create_policy(request: Request) -> Response:
    """
        ``POST /api/v1/retention/policies`` — create a new
        retention policy.

        :param request: Incoming webworks request.

        :returns: JSON response (201) with the policy dict, or
                  problem response on failure.
    """
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor_user_id = _resolve_actor_user_id(request=request)

        raw_scope = str(payload.get("scope_level", ""))
        scope_level = _parse_scope_level_or_abort(
            request=request, raw=raw_scope
        )

        try:
            policy = retention_service.create_policy(
                db_session=db_session,
                name=payload.get("name", ""),
                data_class=payload.get("data_class", ""),
                scope_level=scope_level,
                project_id=payload.get("project_id", None),
                selector=_parse_selector(
                    payload=payload.get("selector", None)
                ),
                action_chain=_parse_action_chain(
                    payload=payload.get("action_chain", None)
                ),
                interval_minutes=int(
                    payload.get("interval_minutes", DEFAULT_INTERVAL_MINUTES)
                ),
                batch_size=int(
                    payload.get("batch_size", DEFAULT_BATCH_SIZE)
                ),
                max_attempts=int(
                    payload.get("max_attempts", DEFAULT_MAX_ATTEMPTS)
                ),
                actor_user_id=actor_user_id,
            )
        except SemanticError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={"name": payload.get("name", "")},
            )
        except UnsupportedRetentionActionError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={"name": payload.get("name", "")},
            )
        except PolicyAlreadyExistsError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"name": payload.get("name", "")},
            )

        body = _policy_to_dict(policy)
        rtnval: Response = JSONResponse(content=body, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_list_policies(request: Request) -> Response:
    """
        ``GET /api/v1/retention/policies`` — list policies with
        optional ``scope_level`` / ``project_id`` / ``state``
        filters.

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying a list of policy
                  dicts, or problem response on failure.
    """
    try:
        db_session = _require_session(request=request)

        scope_arg = request.query_params.get("scope_level", None)
        project_arg = request.query_params.get("project_id", None)
        state_arg = request.query_params.get("state", None)

        scope_level: Optional[PolicyScopeLevel] = None
        if scope_arg is not None and len(scope_arg.strip()) > 0:
            scope_level = _parse_scope_level_or_abort(
                request=request, raw=scope_arg
            )

        state: Optional[PolicyState] = None
        if state_arg is not None and len(state_arg.strip()) > 0:
            state = _parse_state_or_abort(
                request=request, raw=state_arg
            )

        policies = retention_service.list_policies(
            db_session=db_session,
            scope_level=scope_level,
            project_id=project_arg,
            state=state,
        )
        body = [_policy_to_dict(policy) for policy in policies]
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_read_policy(request: Request) -> Response:
    """
        ``GET /api/v1/retention/policies/{policy_id}`` — read one
        policy. Returns 404 problem+json with the policy_id as an
        extension member when the policy does not exist.

        :param request: Incoming webworks request.

        :returns: JSON response (200) or problem response.
    """
    policy_id = request.path_params.get("policy_id", "")
    try:
        db_session = _require_session(request=request)

        try:
            policy = retention_service.read_policy(
                db_session=db_session, policy_id=policy_id,
            )
        except PolicyNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"policy_id": policy_id},
            )

        body = _policy_to_dict(policy)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_publish_policy(request: Request) -> Response:
    """
        ``POST /api/v1/retention/policies/{policy_id}/publish`` —
        transition a policy into PUBLISHED.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the updated policy
                  dict, or problem response on failure.
    """
    policy_id = request.path_params.get("policy_id", "")
    try:
        db_session = _require_session(request=request)
        actor_user_id = _resolve_actor_user_id(request=request)

        try:
            policy = retention_service.publish_policy(
                db_session=db_session,
                policy_id=policy_id,
                actor_user_id=actor_user_id,
            )
        except PolicyNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"policy_id": policy_id},
            )
        except PolicyStateTransitionError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"policy_id": policy_id},
            )

        body = _policy_to_dict(policy)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_retention_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the retention-policies routes to a webworks
        application.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix.

        :returns: None.
    """
    base = version_prefix + RETENTION_PATH

    app.attach_route(base, methods=["GET"])(require_rest_permission(handle_list_policies, permission_key=AUTHENTICATED_ONLY))
    app.attach_route(base, methods=["POST"])(require_rest_permission(handle_create_policy, permission_key="system:ui.admin.view"))
    app.attach_route(
        base + "/{policy_id}", methods=["GET"]
    )(require_rest_permission(handle_read_policy, permission_key=AUTHENTICATED_ONLY))
    app.attach_route(
        base + "/{policy_id}/publish", methods=["POST"]
    )(require_rest_permission(handle_publish_policy, permission_key="system:ui.admin.view"))

    return


__all__ = [
    "RETENTION_PATH",
    "DEFAULT_INTERVAL_MINUTES",
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_MAX_ATTEMPTS",
    "register_retention_routes",
    "handle_create_policy",
    "handle_list_policies",
    "handle_read_policy",
    "handle_publish_policy",
]
