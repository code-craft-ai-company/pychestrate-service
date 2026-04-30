"""
.. module:: agents.restapi.v1.agentsblueprint
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for Layer-3 agent endpoints.

.. moduleauthor:: Automation Mojo LLC

Migrated from Flask + flask-restx to automojo-webworks.

Endpoint surface (mounted absolutely; the blueprint base_path is the
v1 prefix and these endpoints span more than one resource subtree):

* GET  /api/v1/clients/{client_id}/capabilities
* GET  /api/v1/clients-inventory
* POST /api/v1/agent-rollouts
* POST /api/v1/agent-rollouts/{rollout_id}/start

The legacy Flask URLs used colon-action verbs (``/clients:inventory``
and ``/{rollout_id}:start``); the migration normalizes those to
slash-segment paths since webworks path matching does not split on
colons within a segment.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict, Optional

from automojo.errors.exceptions import SemanticError

from automojo.webworks.endpoints.doc import Doc
from automojo.webworks.endpoints.restblueprint import RestBlueprint
from automojo.webworks.routing.exceptions import HTTPException
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse

from automojo.pychestrate.webservice.agents.capability_service import (
    list_capabilities_for_client,
)
from automojo.pychestrate.webservice.agents.exceptions import (
    RolloutNotFoundError,
    RolloutStateTransitionError,
)
from automojo.pychestrate.webservice.agents.inventory_service import (
    read_inventory,
)
from automojo.pychestrate.webservice.agents.upgrade_service import (
    draft_rollout,
    start_rollout,
)
from automojo.pychestrate.webservice.middleware_webworks import (
    get_request_actor_user_id,
)


AGENTS_BASE_PATH = "/api/v1"


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


class AgentsBlueprint(RestBlueprint):
    """
        Blueprint grouping the v1 agent-related endpoints (client
        capabilities, inventory, agent-rollout draft + start).
    """

    base_path = AGENTS_BASE_PATH
    tags = ["agents", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/clients/{client_id}/capabilities",
        methods=["GET"],
        doc=Doc(
            summary="List client capabilities",
            description="Return the registered capabilities for a client.",
        ),
    )
    def list_client_capabilities(request: Request) -> JSONResponse:
        """
            List capabilities for the named client.
        """
        db_session = _require_db_session(request=request)
        client_id = request.path_params.get("client_id", "")

        rows = list_capabilities_for_client(
            db_session=db_session,
            client_id=client_id,
            include_sensitive=False,
        )
        entries = []
        for row in rows:
            if isinstance(row.value_json, dict):
                value_field = row.value_json.get("value")
            else:
                value_field = None
            if row.updated_at is not None:
                updated_at_field: Optional[str] = row.updated_at.isoformat()
            else:
                updated_at_field = None
            entry = {
                "kind": row.kind,
                "value": value_field,
                "revision_token": row.revision_token,
                "updated_at": updated_at_field,
            }
            entries.append(entry)
        rtnval = JSONResponse(content=entries, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/clients-inventory",
        methods=["GET"],
        doc=Doc(
            summary="Read client inventory page",
            description=(
                "Page the client inventory across all projects. "
                "Supports project_id, liveness, offset, limit query "
                "params."
            ),
        ),
    )
    def read_client_inventory(request: Request) -> JSONResponse:
        """
            Page the client inventory.
        """
        db_session = _require_db_session(request=request)
        project_id = request.query_params.get("project_id", None)
        liveness = request.query_params.get("liveness", None)
        offset_raw = request.query_params.get("offset", "0")
        limit_raw = request.query_params.get("limit", "100")
        try:
            offset = int(offset_raw)
            limit = int(limit_raw)
        except (TypeError, ValueError) as exc:
            err_msg = "offset and limit must be integers"
            raise HTTPException(status_code=400, detail=err_msg) from exc

        page = read_inventory(
            db_session=db_session,
            project_id=project_id,
            liveness_state=liveness,
            offset=offset,
            limit=limit,
        )
        rows = []
        for row in page.rows:
            entry = {
                "client_id": row.client_id,
                "project_id": row.project_id,
                "pod_name": row.pod_name,
                "liveness_state": row.liveness_state,
                "agent_version": row.agent_version,
                "last_seen": row.last_seen,
                "capability_kinds": list(row.capability_kinds),
            }
            rows.append(entry)
        body = {
            "total": int(page.total),
            "offset": int(page.offset),
            "limit": int(page.limit),
            "rows": rows,
        }
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/agent-rollouts",
        methods=["POST"],
        doc=Doc(
            summary="Draft an agent rollout",
            description="Stage a new agent rollout in DRAFT state.",
        ),
    )
    def draft_agent_rollout(request: Request) -> JSONResponse:
        """
            Draft a new agent rollout.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        actor_user_id = get_request_actor_user_id(request=request)

        try:
            rollout = draft_rollout(
                db_session=db_session,
                version=payload.get("version", ""),
                artifact_source=payload.get("artifact_source", ""),
                artifact_ref=payload.get("artifact_ref", ""),
                signature=None,
                actor_user_id=actor_user_id,
            )
        except SemanticError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc

        body = {
            "rollout_id": str(rollout.rollout_id),
            "version": rollout.version,
            "state": rollout.state.value,
        }
        rtnval = JSONResponse(content=body, status_code=201)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/agent-rollouts/{rollout_id}/start",
        methods=["POST"],
        doc=Doc(
            summary="Start an agent rollout",
            description=(
                "Transition a DRAFT rollout to STARTED and queue "
                "upgrade offers to candidate clients."
            ),
        ),
    )
    def start_agent_rollout(request: Request) -> JSONResponse:
        """
            Start an agent rollout.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        rollout_id = request.path_params.get("rollout_id", "")

        candidate_raw = payload.get("candidate_client_ids", [])
        if candidate_raw is None:
            candidate_client_ids = []
        else:
            candidate_client_ids = list(candidate_raw)

        target_size_raw = payload.get("target_size", 10)
        try:
            target_size = int(target_size_raw)
        except (TypeError, ValueError) as exc:
            err_msg = "target_size must be an integer"
            raise HTTPException(status_code=400, detail=err_msg) from exc

        try:
            offers = start_rollout(
                db_session=db_session,
                rollout_id=rollout_id,
                candidate_client_ids=candidate_client_ids,
                target_size=target_size,
                actor_user_id=actor_user_id,
            )
        except RolloutNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc
        except RolloutStateTransitionError as exc:
            raise HTTPException(
                status_code=409, detail=str(exc),
            ) from exc

        offer_entries = []
        for offer in offers:
            offer_entries.append({
                "offer_id": str(offer.offer_id),
                "client_id": str(offer.client_id),
            })
        body = {
            "rollout_id": rollout_id,
            "offer_count": len(offers),
            "offers": offer_entries,
        }
        rtnval = JSONResponse(content=body, status_code=202)
        return rtnval
