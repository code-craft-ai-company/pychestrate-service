"""
.. module:: retention.restapi.v1.retention_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/retention/policies.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import request
from flask_restx import Namespace, Resource, fields

from automojo.errors.exceptions import SemanticError

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


RETENTION_NAMESPACE_PATH = "/retention/policies"


retention_ns = Namespace(
    "Retention Policies v1",
    description="Retention policy CRUD (2-retention-policies).",
)


selector_model = retention_ns.model(
    "RetentionSelector",
    {
        "tag_expression": fields.String(required=False, default=""),
        "age_days": fields.Integer(required=False, default=0),
        "size_bytes_over": fields.Integer(required=False, default=0),
        "project_ids": fields.List(fields.String, required=False),
    },
)

action_step_model = retention_ns.model(
    "RetentionActionStep",
    {
        "action_name": fields.String(required=True),
        "parameters": fields.Raw(required=False),
        "wait_days_after_previous": fields.Integer(required=False, default=0),
    },
)

policy_create_model = retention_ns.model(
    "RetentionPolicyCreate",
    {
        "name": fields.String(required=True),
        "data_class": fields.String(required=True),
        "scope_level": fields.String(required=True, description="SYSTEM | PROJECT"),
        "project_id": fields.String(required=False),
        "selector": fields.Nested(selector_model, required=False),
        "action_chain": fields.List(fields.Nested(action_step_model), required=True),
        "interval_minutes": fields.Integer(required=False, default=1440),
        "batch_size": fields.Integer(required=False, default=500),
        "max_attempts": fields.Integer(required=False, default=3),
    },
)

policy_response_model = retention_ns.model(
    "RetentionPolicyResponse",
    {
        "policy_id": fields.String(description="Server-generated UUID"),
        "name": fields.String,
        "data_class": fields.String,
        "scope_level": fields.String,
        "project_id": fields.String,
        "state": fields.String,
        "interval_minutes": fields.Integer,
        "batch_size": fields.Integer,
        "max_attempts": fields.Integer,
        "created_at": fields.String,
        "updated_at": fields.String,
        "published_at": fields.String,
    },
)


def _policy_to_dict(policy) -> dict:
    """
        Render a :class:`RetentionPolicy` as the REST response dict.
    """
    rtnval = {
        "policy_id": str(policy.policy_id),
        "name": policy.name,
        "data_class": policy.data_class,
        "scope_level": policy.scope_level.value,
        "project_id": str(policy.project_id) if policy.project_id is not None else None,
        "state": policy.state.value,
        "interval_minutes": int(policy.interval_minutes),
        "batch_size": int(policy.batch_size),
        "max_attempts": int(policy.max_attempts),
        "created_at": policy.created_at.isoformat() if policy.created_at is not None else None,
        "updated_at": policy.updated_at.isoformat() if policy.updated_at is not None else None,
        "published_at": policy.published_at.isoformat() if policy.published_at is not None else None,
    }
    return rtnval


def _parse_selector(*, payload):
    """
        Build a :class:`SelectorClause` from the request payload.
    """
    raw = payload if payload is not None else {}
    rtnval = SelectorClause(
        tag_expression=raw.get("tag_expression", "") or "",
        age_days=int(raw.get("age_days", 0) or 0),
        size_bytes_over=int(raw.get("size_bytes_over", 0) or 0),
        project_ids=tuple(raw.get("project_ids", []) or []),
    )
    return rtnval


def _parse_action_chain(*, payload):
    """
        Build a list of :class:`ActionStep` from the request payload.
    """
    rtnval = []
    for raw in payload or []:
        step = ActionStep(
            action_name=str(raw.get("action_name", "")),
            parameters=raw.get("parameters", {}) or {},
            wait_days_after_previous=int(raw.get("wait_days_after_previous", 0) or 0),
        )
        rtnval.append(step)
    return rtnval


@retention_ns.route("")
class PolicyListResource(Resource):
    """
        Resource for the policy collection.
    """

    @retention_ns.expect(policy_create_model, validate=True)
    @retention_ns.marshal_with(policy_response_model, code=201)
    def post(self):
        """
            Create a new retention policy.
        """
        payload = request.get_json(force=True, silent=False)
        db_session = _get_request_db_session()
        actor_user_id = _get_request_actor_user_id()

        raw_scope = str(payload.get("scope_level", "")).strip().upper()
        try:
            scope_level = PolicyScopeLevel[raw_scope]
        except KeyError:
            retention_ns.abort(400, "Unknown scope_level: {}".format(raw_scope))

        try:
            policy = retention_service.create_policy(
                db_session=db_session,
                name=payload.get("name", ""),
                data_class=payload.get("data_class", ""),
                scope_level=scope_level,
                project_id=payload.get("project_id", None),
                selector=_parse_selector(payload=payload.get("selector", None)),
                action_chain=_parse_action_chain(payload=payload.get("action_chain", None)),
                interval_minutes=int(payload.get("interval_minutes", 1440)),
                batch_size=int(payload.get("batch_size", 500)),
                max_attempts=int(payload.get("max_attempts", 3)),
                actor_user_id=actor_user_id,
            )
        except SemanticError as xcpt:
            retention_ns.abort(400, str(xcpt))
        except UnsupportedRetentionActionError as xcpt:
            retention_ns.abort(400, str(xcpt))
        except PolicyAlreadyExistsError as xcpt:
            retention_ns.abort(409, str(xcpt))

        rtnval = _policy_to_dict(policy)
        return rtnval, 201

    @retention_ns.marshal_list_with(policy_response_model)
    def get(self):
        """
            List policies. Optional query params: ``scope_level``,
            ``project_id``, ``state``.
        """
        db_session = _get_request_db_session()

        scope_arg = request.args.get("scope_level", None)
        project_arg = request.args.get("project_id", None)
        state_arg = request.args.get("state", None)

        scope_level = None
        if scope_arg is not None and len(scope_arg.strip()) > 0:
            try:
                scope_level = PolicyScopeLevel[scope_arg.strip().upper()]
            except KeyError:
                retention_ns.abort(400, "Unknown scope_level: {}".format(scope_arg))

        state = None
        if state_arg is not None and len(state_arg.strip()) > 0:
            try:
                state = PolicyState[state_arg.strip().upper()]
            except KeyError:
                retention_ns.abort(400, "Unknown state: {}".format(state_arg))

        policies = retention_service.list_policies(
            db_session=db_session,
            scope_level=scope_level,
            project_id=project_arg,
            state=state,
        )
        rtnval = [_policy_to_dict(p) for p in policies]
        return rtnval


@retention_ns.route("/<string:policy_id>")
@retention_ns.param("policy_id", "The policy id")
class PolicyDetail(Resource):
    """
        Resource for a single policy.
    """

    @retention_ns.marshal_with(policy_response_model)
    def get(self, policy_id: str):
        """
            Fetch one policy.
        """
        db_session = _get_request_db_session()
        try:
            policy = retention_service.read_policy(
                db_session=db_session, policy_id=policy_id,
            )
        except PolicyNotFoundError as xcpt:
            retention_ns.abort(404, str(xcpt))

        rtnval = _policy_to_dict(policy)
        return rtnval


@retention_ns.route("/<string:policy_id>/publish")
@retention_ns.param("policy_id", "The policy id")
class PolicyPublish(Resource):
    """
        Resource that exposes POST ``/api/v1/retention/policies/{id}/publish``.
    """

    @retention_ns.marshal_with(policy_response_model)
    def post(self, policy_id: str):
        """
            Transition a policy into PUBLISHED.
        """
        db_session = _get_request_db_session()
        actor_user_id = _get_request_actor_user_id()

        try:
            policy = retention_service.publish_policy(
                db_session=db_session,
                policy_id=policy_id,
                actor_user_id=actor_user_id,
            )
        except PolicyNotFoundError as xcpt:
            retention_ns.abort(404, str(xcpt))
        except PolicyStateTransitionError as xcpt:
            retention_ns.abort(409, str(xcpt))

        rtnval = _policy_to_dict(policy)
        return rtnval


def _get_request_db_session():
    """
        Resolve the request-scoped SQLAlchemy session.
    """
    from flask import g
    db_session = getattr(g, "db_session", None)
    if db_session is None:
        retention_ns.abort(503, "Request-scoped db_session not configured")
    return db_session


def _get_request_actor_user_id():
    """
        Resolve the acting principal's user id.
    """
    from flask import g
    actor = getattr(g, "actor_user_id", None)
    return actor


def publish_namespaces(version_prefix: str):
    """
        Return namespace registrations for v1 wiring.

        :param version_prefix: Version prefix.

        :returns: List of (namespace, path) tuples.
    """
    rtnval = [(retention_ns, version_prefix + RETENTION_NAMESPACE_PATH)]
    return rtnval
