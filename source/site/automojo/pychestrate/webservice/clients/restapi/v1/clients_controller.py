"""
.. module:: clients.restapi.v1.clients_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/clients.

.. moduleauthor:: Automation Mojo LLC

M1 routes:

* ``GET    /api/v1/clients`` — list with optional filters.
* ``GET    /api/v1/clients/{client_id}`` — single client view.
* ``POST   /api/v1/clients/{client_id}/revoke`` — admin revoke.
* ``PUT    /api/v1/clients/{client_id}/attributes`` — admin attribute override.

Agent-side routes (``/api/v1/clients/enrollment`` for redemption,
``/api/v1/clients/{id}/heartbeat`` for liveness) land in the
paired ``enrollment_controller.py``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import g, request
from flask_restx import Namespace, Resource, fields

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.clients.enrollment.service import (
    revoke_client,
)
from automojo.pychestrate.webservice.clients.enums import (
    ClientStatus,
    LivenessState,
    RevocationReason,
)
from automojo.pychestrate.webservice.clients.exceptions import (
    ClientNotFoundError,
    InvalidAttributeValueError,
    UnknownAttributeKindError,
)
from automojo.pychestrate.webservice.clients.registry.service import (
    AttributeUpdate,
    ClientView,
    get_client,
    list_clients,
    update_attributes,
)


CLIENTS_NAMESPACE_PATH = "/clients"


clients_ns = Namespace(
    "Clients v1",
    description="Client registry admin endpoints (3-client-registry).",
)


client_view_model = clients_ns.model(
    "ClientsClientView",
    {
        "client_id": fields.String(description="Client UUID"),
        "project_id": fields.String(description="Owning project UUID"),
        "pod_name": fields.String(description="Pod this client registered under"),
        "status": fields.String(description="ACTIVE | SUSPENDED | REVOKED"),
        "liveness_state": fields.String(description="ALIVE | DEGRADED | LOST"),
        "enrolled_at": fields.String(description="ISO-8601 enrollment timestamp"),
        "last_seen": fields.String(description="Last heartbeat timestamp"),
        "last_agent_version": fields.String(description="Reported agent version"),
        "transport_name": fields.String(description="Last-observed transport"),
        "degraded_at": fields.String(description="DEGRADED timestamp"),
        "revision_token": fields.String(description="Monotonic update token"),
        "attributes": fields.Raw(description="Kind -> value map"),
    },
)


revoke_request_model = clients_ns.model(
    "ClientsRevokeRequest",
    {
        "reason": fields.String(
            required=True,
            description="ROTATED | DECOMMISSIONED | COMPROMISED | ADMIN_REQUEST",
        ),
        "note": fields.String(required=False, default="", description="Operator note"),
    },
)


attribute_update_model = clients_ns.model(
    "ClientsAttributeUpdate",
    {
        "kind": fields.String(required=True, description="Attribute kind name"),
        "value": fields.Raw(required=True, description="JSON-serializable value"),
    },
)


attribute_batch_model = clients_ns.model(
    "ClientsAttributeBatch",
    {
        "expected_revision_token": fields.String(
            required=False,
            description="Current revision_token for optimistic concurrency",
        ),
        "updates": fields.List(
            fields.Nested(attribute_update_model),
            required=True,
            description="One or more kind/value pairs",
        ),
    },
)


def _view_to_dict(view: ClientView) -> dict:
    rtnval = {
        "client_id": view.client_id,
        "project_id": view.project_id,
        "pod_name": view.pod_name,
        "status": view.status.value,
        "liveness_state": view.liveness_state.value,
        "enrolled_at": view.enrolled_at_iso,
        "last_seen": view.last_seen_iso,
        "last_agent_version": view.last_agent_version,
        "transport_name": view.transport_name,
        "degraded_at": view.degraded_at_iso,
        "revision_token": view.revision_token,
        "attributes": dict(view.attributes),
    }
    return rtnval


def _get_db_session():
    db_session = getattr(g, "db_session", None)
    if db_session is None:
        clients_ns.abort(503, "Request-scoped db_session not configured")
    return db_session


def _parse_client_status(raw: str):
    if raw is None or len(raw) == 0:
        return None
    try:
        rtnval = ClientStatus(raw)
    except ValueError:
        clients_ns.abort(400, "Unknown status: {}".format(raw))
    return rtnval


def _parse_liveness_state(raw: str):
    if raw is None or len(raw) == 0:
        return None
    try:
        rtnval = LivenessState(raw)
    except ValueError:
        clients_ns.abort(400, "Unknown liveness_state: {}".format(raw))
    return rtnval


def _parse_revocation_reason(raw: str) -> RevocationReason:
    try:
        rtnval = RevocationReason(raw)
    except ValueError:
        raise SemanticError("Unknown revocation reason: {}".format(raw))
    return rtnval


@clients_ns.route("")
class ClientsList(Resource):
    """
        GET ``/api/v1/clients`` — list with optional filters.
    """

    @clients_ns.marshal_list_with(client_view_model)
    def get(self):
        db_session = _get_db_session()
        project_id = request.args.get("project_id", None)
        status = _parse_client_status(request.args.get("status", ""))
        liveness_state = _parse_liveness_state(request.args.get("liveness_state", ""))
        views = list_clients(
            db_session=db_session,
            project_id=project_id,
            status=status,
            liveness_state=liveness_state,
        )
        rtnval = [_view_to_dict(v) for v in views]
        return rtnval


@clients_ns.route("/<string:client_id>")
@clients_ns.param("client_id", "Client UUID")
class ClientsDetail(Resource):
    """
        GET ``/api/v1/clients/{client_id}`` — single client view.
    """

    @clients_ns.marshal_with(client_view_model)
    def get(self, client_id: str):
        db_session = _get_db_session()
        try:
            view = get_client(db_session=db_session, client_id=client_id)
        except ClientNotFoundError as xcpt:
            clients_ns.abort(404, str(xcpt))
        rtnval = _view_to_dict(view)
        return rtnval


@clients_ns.route("/<string:client_id>/revoke")
@clients_ns.param("client_id", "Client UUID")
class ClientsRevoke(Resource):
    """
        POST ``/api/v1/clients/{client_id}/revoke`` — admin revoke.
    """

    @clients_ns.expect(revoke_request_model, validate=True)
    def post(self, client_id: str):
        db_session = _get_db_session()
        payload = request.get_json(force=True, silent=False)
        actor = getattr(g, "actor_user_id", None)

        try:
            reason = _parse_revocation_reason(payload.get("reason", ""))
        except SemanticError as xcpt:
            clients_ns.abort(400, str(xcpt))

        try:
            revoke_client(
                db_session=db_session,
                client_id=client_id,
                reason=reason,
                revoked_by=actor,
                note=payload.get("note", ""),
            )
        except ClientNotFoundError as xcpt:
            clients_ns.abort(404, str(xcpt))

        rtnval = ({"client_id": client_id, "status": "revoked"}, 200)
        return rtnval


@clients_ns.route("/<string:client_id>/attributes")
@clients_ns.param("client_id", "Client UUID")
class ClientsAttributes(Resource):
    """
        PUT ``/api/v1/clients/{client_id}/attributes`` — admin upsert batch.
    """

    @clients_ns.expect(attribute_batch_model, validate=True)
    def put(self, client_id: str):
        db_session = _get_db_session()
        payload = request.get_json(force=True, silent=False)

        raw_updates = payload.get("updates", [])
        if isinstance(raw_updates, list) is False:
            clients_ns.abort(400, "'updates' must be a list of {kind, value} objects")

        updates = []
        for item in raw_updates:
            if isinstance(item, dict) is False:
                clients_ns.abort(400, "Each update must be an object")
            kind = item.get("kind", "")
            if isinstance(kind, str) is False or len(kind) == 0:
                clients_ns.abort(400, "Each update must include a non-empty 'kind'")
            updates.append(AttributeUpdate(kind=kind, value=item.get("value", None)))

        expected_token = payload.get("expected_revision_token", None)

        try:
            written = update_attributes(
                db_session=db_session,
                client_id=client_id,
                updates=updates,
                expected_revision_token=expected_token,
            )
        except ClientNotFoundError as xcpt:
            clients_ns.abort(404, str(xcpt))
        except UnknownAttributeKindError as xcpt:
            clients_ns.abort(400, str(xcpt))
        except InvalidAttributeValueError as xcpt:
            clients_ns.abort(400, str(xcpt))

        rtnval = ({"client_id": client_id, "kinds_written": list(written)}, 200)
        return rtnval


def publish_namespaces(version_prefix: str):
    """
        Return namespace registrations for the v1 API wiring.

        :param version_prefix: Version prefix string (``/1``).

        :returns: List of (namespace, path) tuples.
    """
    rtnval = [(clients_ns, version_prefix + CLIENTS_NAMESPACE_PATH)]
    return rtnval
