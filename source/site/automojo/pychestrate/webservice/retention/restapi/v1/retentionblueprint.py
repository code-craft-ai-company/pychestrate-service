"""
.. module:: retention.restapi.v1.retentionblueprint
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/retention/policies.

.. moduleauthor:: Automation Mojo LLC

Migrated from Flask + flask-restx to automojo-webworks.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict, List, Optional

from automojo.errors.exceptions import SemanticError

from automojo.webworks.endpoints.doc import Doc
from automojo.webworks.endpoints.restblueprint import RestBlueprint
from automojo.webworks.routing.exceptions import HTTPException
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse

from automojo.pychestrate.webservice.dbsessionmiddleware import (
    get_request_actor_user_id,
)
from automojo.pychestrate.webservice.retention import service as retention_service
from automojo.pychestrate.webservice.retention.exceptions import (
    PolicyAlreadyExistsError,
    PolicyNotFoundError,
    PolicyStateTransitionError,
    UnsupportedRetentionActionError,
)
from automojo.pychestrate.webservice.retention.models import (
    ActionStep,
    PolicyScopeLevel,
    PolicyState,
    SelectorClause,
)


RETENTION_BASE_PATH = "/api/v1/retention/policies"


def _policy_to_dict(policy) -> Dict[str, Any]:
    """
        Render a :class:`RetentionPolicy` as the REST response dict.
    """
    if policy.project_id is not None:
        project_id_field = str(policy.project_id)
    else:
        project_id_field = None
    if policy.created_at is not None:
        created_at_field = policy.created_at.isoformat()
    else:
        created_at_field = None
    if policy.updated_at is not None:
        updated_at_field = policy.updated_at.isoformat()
    else:
        updated_at_field = None
    if policy.published_at is not None:
        published_at_field = policy.published_at.isoformat()
    else:
        published_at_field = None
    rtnval = {
        "policy_id": str(policy.policy_id),
        "name": policy.name,
        "data_class": policy.data_class,
        "scope_level": policy.scope_level.value,
        "project_id": project_id_field,
        "state": policy.state.value,
        "interval_minutes": int(policy.interval_minutes),
        "batch_size": int(policy.batch_size),
        "max_attempts": int(policy.max_attempts),
        "created_at": created_at_field,
        "updated_at": updated_at_field,
        "published_at": published_at_field,
    }
    return rtnval


def _parse_selector(*, payload: Optional[Dict[str, Any]]) -> SelectorClause:
    """
        Build a :class:`SelectorClause` from the request payload.
    """
    if payload is None:
        raw = {}
    else:
        raw = payload
    tag_expression_raw = raw.get("tag_expression", "")
    if tag_expression_raw is None:
        tag_expression = ""
    else:
        tag_expression = tag_expression_raw
    age_days_raw = raw.get("age_days", 0)
    if age_days_raw is None:
        age_days = 0
    else:
        age_days = int(age_days_raw)
    size_bytes_over_raw = raw.get("size_bytes_over", 0)
    if size_bytes_over_raw is None:
        size_bytes_over = 0
    else:
        size_bytes_over = int(size_bytes_over_raw)
    project_ids_raw = raw.get("project_ids", [])
    if project_ids_raw is None:
        project_ids: List[str] = []
    else:
        project_ids = list(project_ids_raw)
    rtnval = SelectorClause(
        tag_expression=tag_expression,
        age_days=age_days,
        size_bytes_over=size_bytes_over,
        project_ids=tuple(project_ids),
    )
    return rtnval


def _parse_action_chain(
        *, payload: Optional[List[Dict[str, Any]]]
    ) -> List[ActionStep]:
    """
        Build a list of :class:`ActionStep` from the request payload.
    """
    if payload is None:
        raw_list: List[Dict[str, Any]] = []
    else:
        raw_list = payload
    rtnval: List[ActionStep] = []
    for raw in raw_list:
        parameters_raw = raw.get("parameters", {})
        if parameters_raw is None:
            parameters = {}
        else:
            parameters = parameters_raw
        wait_raw = raw.get("wait_days_after_previous", 0)
        if wait_raw is None:
            wait_days = 0
        else:
            wait_days = int(wait_raw)
        step = ActionStep(
            action_name=str(raw.get("action_name", "")),
            parameters=parameters,
            wait_days_after_previous=wait_days,
        )
        rtnval.append(step)
    return rtnval


def _require_db_session(*, request: Request) -> Any:
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        err_lines = [
            "Request-scoped db_session not configured.",
            "DbSessionMiddleware must be installed in the pipeline.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise HTTPException(status_code=503, detail=err_msg)
    return db_session


def _read_json_body(*, request: Request) -> Dict[str, Any]:
    raw_body = request.body
    if raw_body is None:
        raise HTTPException(status_code=400, detail="request body required")
    if len(raw_body) == 0:
        raise HTTPException(status_code=400, detail="request body required")
    try:
        decoded = request.json()
    except Exception as exc:
        err_msg = "request body must be valid JSON"
        raise HTTPException(status_code=400, detail=err_msg) from exc
    if not isinstance(decoded, dict):
        raise HTTPException(
            status_code=400, detail="request body must be a JSON object",
        )
    rtnval = decoded
    return rtnval


class RetentionBlueprint(RestBlueprint):
    """
        Blueprint grouping the v1 ``/api/v1/retention/policies`` endpoints.
    """

    base_path = RETENTION_BASE_PATH
    tags = ["retention", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/retention/policies",
        methods=["POST"],
        doc=Doc(
            summary="Create retention policy",
            description="Register a new retention policy in DRAFT state.",
        ),
    )
    def create_policy(request: Request) -> JSONResponse:
        """
            Create a new retention policy.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        actor_user_id = get_request_actor_user_id(request=request)

        scope_raw = str(payload.get("scope_level", "")).strip().upper()
        try:
            scope_level = PolicyScopeLevel[scope_raw]
        except KeyError as exc:
            err_msg = "Unknown scope_level: {}".format(scope_raw)
            raise HTTPException(status_code=400, detail=err_msg) from exc

        try:
            policy = retention_service.create_policy(
                db_session=db_session,
                name=payload.get("name", ""),
                data_class=payload.get("data_class", ""),
                scope_level=scope_level,
                project_id=payload.get("project_id", None),
                selector=_parse_selector(payload=payload.get("selector", None)),
                action_chain=_parse_action_chain(
                    payload=payload.get("action_chain", None),
                ),
                interval_minutes=int(payload.get("interval_minutes", 1440)),
                batch_size=int(payload.get("batch_size", 500)),
                max_attempts=int(payload.get("max_attempts", 3)),
                actor_user_id=actor_user_id,
            )
        except SemanticError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc
        except UnsupportedRetentionActionError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc
        except PolicyAlreadyExistsError as exc:
            raise HTTPException(
                status_code=409, detail=str(exc),
            ) from exc

        body = _policy_to_dict(policy=policy)
        rtnval = JSONResponse(content=body, status_code=201)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/retention/policies",
        methods=["GET"],
        doc=Doc(
            summary="List retention policies",
            description=(
                "List retention policies. Supports scope_level, "
                "project_id, and state query-string filters."
            ),
        ),
    )
    def list_policies(request: Request) -> JSONResponse:
        """
            List retention policies with optional filters.
        """
        db_session = _require_db_session(request=request)

        scope_arg = request.query_params.get("scope_level", None)
        project_arg = request.query_params.get("project_id", None)
        state_arg = request.query_params.get("state", None)

        scope_level: Optional[PolicyScopeLevel] = None
        if scope_arg is not None:
            stripped_scope = scope_arg.strip()
            if len(stripped_scope) > 0:
                try:
                    scope_level = PolicyScopeLevel[stripped_scope.upper()]
                except KeyError as exc:
                    err_msg = "Unknown scope_level: {}".format(scope_arg)
                    raise HTTPException(
                        status_code=400, detail=err_msg,
                    ) from exc

        state: Optional[PolicyState] = None
        if state_arg is not None:
            stripped_state = state_arg.strip()
            if len(stripped_state) > 0:
                try:
                    state = PolicyState[stripped_state.upper()]
                except KeyError as exc:
                    err_msg = "Unknown state: {}".format(state_arg)
                    raise HTTPException(
                        status_code=400, detail=err_msg,
                    ) from exc

        policies = retention_service.list_policies(
            db_session=db_session,
            scope_level=scope_level,
            project_id=project_arg,
            state=state,
        )
        body = [_policy_to_dict(policy=p) for p in policies]
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/retention/policies/{policy_id}",
        methods=["GET"],
        doc=Doc(
            summary="Read retention policy",
            description="Fetch one retention policy by id.",
        ),
    )
    def read_policy(request: Request) -> JSONResponse:
        """
            Fetch a single retention policy.
        """
        db_session = _require_db_session(request=request)
        policy_id = request.path_params.get("policy_id", "")

        try:
            policy = retention_service.read_policy(
                db_session=db_session, policy_id=policy_id,
            )
        except PolicyNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc

        body = _policy_to_dict(policy=policy)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/retention/policies/{policy_id}/publish",
        methods=["POST"],
        doc=Doc(
            summary="Publish retention policy",
            description="Transition a retention policy into PUBLISHED.",
        ),
    )
    def publish_policy(request: Request) -> JSONResponse:
        """
            Transition a policy into PUBLISHED.
        """
        db_session = _require_db_session(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        policy_id = request.path_params.get("policy_id", "")

        try:
            policy = retention_service.publish_policy(
                db_session=db_session,
                policy_id=policy_id,
                actor_user_id=actor_user_id,
            )
        except PolicyNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc
        except PolicyStateTransitionError as exc:
            raise HTTPException(
                status_code=409, detail=str(exc),
            ) from exc

        body = _policy_to_dict(policy=policy)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval
