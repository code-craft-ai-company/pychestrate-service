"""
.. module:: agents.restapi.v1.agents_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controllers for Layer-3 agents.

.. moduleauthor:: Automation Mojo LLC

Collates capability read, inventory list, and agent-rollout endpoints
into a single namespace.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import request
from flask_restx import Namespace, Resource, fields

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.agents.capability_service import (
    list_capabilities_for_client,
)
from automojo.pychestrate.webservice.agents.exceptions import (
    RolloutNotFoundError,
    RolloutStateTransitionError,
)
from automojo.pychestrate.webservice.agents.inventory_service import read_inventory
from automojo.pychestrate.webservice.agents.upgrade_service import (
    draft_rollout,
    start_rollout,
)


AGENTS_NAMESPACE_PATH = ""


agents_ns = Namespace(
    "Agents v1",
    description="Layer-3 agent features: capabilities, inventory, "
                "rollout control.",
)


rollout_draft_model = agents_ns.model(
    "AgentRolloutDraft",
    {
        "version": fields.String(required=True),
        "artifact_source": fields.String(required=True),
        "artifact_ref": fields.String(required=True),
    },
)

rollout_start_model = agents_ns.model(
    "AgentRolloutStart",
    {
        "candidate_client_ids": fields.List(fields.String, required=True),
        "target_size": fields.Integer(required=False, default=10),
    },
)


def _get_request_db_session():
    from flask import g
    db_session = getattr(g, "db_session", None)
    if db_session is None:
        agents_ns.abort(503, "Request-scoped db_session not configured")
    return db_session


def _get_request_actor_user_id():
    from flask import g
    actor = getattr(g, "actor_user_id", None)
    return actor


@agents_ns.route("/clients/<string:client_id>/capabilities")
@agents_ns.param("client_id", "The client id")
class ClientCapabilitiesResource(Resource):
    def get(self, client_id: str):
        db_session = _get_request_db_session()
        rows = list_capabilities_for_client(
            db_session=db_session, client_id=client_id, include_sensitive=False,
        )
        rtnval = [
            {
                "kind": r.kind,
                "value": r.value_json.get("value") if isinstance(r.value_json, dict) else None,
                "revision_token": r.revision_token,
                "updated_at": r.updated_at.isoformat() if r.updated_at is not None else None,
            }
            for r in rows
        ]
        return rtnval


@agents_ns.route("/clients:inventory")
class ClientInventoryResource(Resource):
    def get(self):
        db_session = _get_request_db_session()
        project_id = request.args.get("project_id", None)
        liveness = request.args.get("liveness", None)
        offset = int(request.args.get("offset", 0))
        limit = int(request.args.get("limit", 100))
        page = read_inventory(
            db_session=db_session,
            project_id=project_id,
            liveness_state=liveness,
            offset=offset,
            limit=limit,
        )
        rtnval = {
            "total": int(page.total),
            "offset": int(page.offset),
            "limit": int(page.limit),
            "rows": [
                {
                    "client_id": row.client_id,
                    "project_id": row.project_id,
                    "pod_name": row.pod_name,
                    "liveness_state": row.liveness_state,
                    "agent_version": row.agent_version,
                    "last_seen": row.last_seen,
                    "capability_kinds": list(row.capability_kinds),
                }
                for row in page.rows
            ],
        }
        return rtnval


@agents_ns.route("/agent-rollouts")
class AgentRolloutsResource(Resource):
    @agents_ns.expect(rollout_draft_model, validate=True)
    def post(self):
        payload = request.get_json(force=True, silent=False)
        db_session = _get_request_db_session()
        actor = _get_request_actor_user_id()
        try:
            rollout = draft_rollout(
                db_session=db_session,
                version=payload.get("version", ""),
                artifact_source=payload.get("artifact_source", ""),
                artifact_ref=payload.get("artifact_ref", ""),
                signature=None,
                actor_user_id=actor,
            )
        except SemanticError as xcpt:
            agents_ns.abort(400, str(xcpt))
        rtnval = {
            "rollout_id": str(rollout.rollout_id),
            "version": rollout.version,
            "state": rollout.state.value,
        }
        return rtnval, 201


@agents_ns.route("/agent-rollouts/<string:rollout_id>:start")
@agents_ns.param("rollout_id", "The rollout id")
class AgentRolloutStartResource(Resource):
    @agents_ns.expect(rollout_start_model, validate=True)
    def post(self, rollout_id: str):
        payload = request.get_json(force=True, silent=False)
        db_session = _get_request_db_session()
        actor = _get_request_actor_user_id()
        try:
            offers = start_rollout(
                db_session=db_session,
                rollout_id=rollout_id,
                candidate_client_ids=list(payload.get("candidate_client_ids", []) or []),
                target_size=int(payload.get("target_size", 10)),
                actor_user_id=actor,
            )
        except RolloutNotFoundError as xcpt:
            agents_ns.abort(404, str(xcpt))
        except RolloutStateTransitionError as xcpt:
            agents_ns.abort(409, str(xcpt))

        rtnval = {
            "rollout_id": rollout_id,
            "offer_count": len(offers),
            "offers": [
                {"offer_id": str(o.offer_id), "client_id": str(o.client_id)}
                for o in offers
            ],
        }
        return rtnval, 202


def publish_namespaces(version_prefix: str):
    rtnval = [(agents_ns, version_prefix + AGENTS_NAMESPACE_PATH)]
    return rtnval
