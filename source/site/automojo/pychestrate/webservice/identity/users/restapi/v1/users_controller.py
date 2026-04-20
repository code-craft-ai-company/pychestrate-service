"""
.. module:: identity.users.restapi.v1.users_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/identity/users.

.. moduleauthor:: Automation Mojo LLC

Implements the Phase-1 M1 endpoints:

* ``POST /api/v1/identity/users`` — create user.
* ``GET  /api/v1/identity/users/{user_id}`` — fetch user.

Downstream milestones extend this controller with list / patch /
deactivate / reactivate / group-member endpoints. The namespace is
registered against the v1 API via :func:`publish_namespaces`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import request
from flask_restx import Namespace, Resource, fields

from automojo.pychestrate.webservice.identity.users.exceptions import (
    UserAlreadyExistsError,
    UserNotFoundError,
)
from automojo.pychestrate.webservice.identity.users import user_service


IDENTITY_USERS_NAMESPACE_PATH = "/identity/users"


users_ns = Namespace(
    "Identity Users v1",
    description="Canonical identity user records (1-user-management).",
)


user_create_model = users_ns.model(
    "IdentityUserCreate",
    {
        "login_name": fields.String(required=True, description="Unique login name"),
        "primary_email": fields.String(required=True, description="Primary email address"),
        "display_name": fields.String(required=True, description="Human-facing name"),
        "timezone": fields.String(required=True, description="IANA timezone name"),
        "provisioning_source": fields.String(
            required=False, default="local", description="Provisioning source name"
        ),
        "external_id": fields.String(
            required=False, description="External id when provisioned from a directory"
        ),
    },
)

user_response_model = users_ns.model(
    "IdentityUserResponse",
    {
        "user_id": fields.String(description="Server-generated UUID"),
        "login_name": fields.String(description="Unique login name"),
        "primary_email": fields.String(description="Primary email address"),
        "display_name": fields.String(description="Human-facing name"),
        "status": fields.String(description="ACTIVE | DEACTIVATED | PENDING"),
        "provisioning_source": fields.String(description="Provisioning source"),
        "external_id": fields.String(description="External id"),
        "timezone": fields.String(description="IANA timezone name"),
        "created_at": fields.String(description="Create timestamp (ISO-8601)"),
        "updated_at": fields.String(description="Update timestamp (ISO-8601)"),
    },
)


def _model_to_dict(user) -> dict:
    """
        Render an :class:`IdentityUser` instance as the REST response dict.

        :param user: The persistent model instance.

        :returns: A plain dict suitable for JSON serialization.
    """
    rtnval = {
        "user_id": str(user.user_id),
        "login_name": user.login_name,
        "primary_email": user.primary_email,
        "display_name": user.display_name,
        "status": user.status.value if user.status is not None else None,
        "provisioning_source": user.provisioning_source,
        "external_id": user.external_id,
        "timezone": user.timezone,
        "created_at": user.created_at.isoformat() if user.created_at is not None else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at is not None else None,
    }
    return rtnval


@users_ns.route("")
class IdentityUsersList(Resource):
    """
        Resource that exposes POST ``/api/v1/identity/users`` for creation.
    """

    @users_ns.expect(user_create_model, validate=True)
    @users_ns.marshal_with(user_response_model, code=201)
    def post(self):
        """
            Create a new identity user. The session is expected to be attached
            to the Flask request via the ``db_session`` extension; controllers
            outside of this skeleton are responsible for wiring it.
        """
        payload = request.get_json(force=True, silent=False)

        db_session = _get_request_db_session()
        actor_user_id = _get_request_actor_user_id()

        try:
            user = user_service.create_user(
                db_session=db_session,
                login_name=payload.get("login_name", ""),
                primary_email=payload.get("primary_email", ""),
                display_name=payload.get("display_name", ""),
                timezone=payload.get("timezone", "UTC"),
                provisioning_source=payload.get("provisioning_source", "local"),
                external_id=payload.get("external_id", None),
                actor_user_id=actor_user_id,
            )
        except UserAlreadyExistsError as xcpt:
            users_ns.abort(409, str(xcpt))

        rtnval = _model_to_dict(user)
        return rtnval, 201


@users_ns.route("/<string:user_id>")
@users_ns.param("user_id", "The identity user id")
class IdentityUserDetail(Resource):
    """
        Resource that exposes GET ``/api/v1/identity/users/{user_id}``.
    """

    @users_ns.marshal_with(user_response_model)
    def get(self, user_id: str):
        """
            Fetch an identity user by id.

            :param user_id: The target user's id.

            :returns: The user response payload.
        """
        db_session = _get_request_db_session()
        try:
            user = user_service.read_user(db_session=db_session, user_id=user_id)
        except UserNotFoundError as xcpt:
            users_ns.abort(404, str(xcpt))

        rtnval = _model_to_dict(user)
        return rtnval


def _get_request_db_session():
    """
        Resolve the request-scoped SQLAlchemy session. The host app sets the
        attribute on :data:`flask.g`; when absent the controller raises 503
        so the misconfiguration surfaces loudly during bring-up.

        :returns: The SQLAlchemy Session.
    """
    from flask import g
    db_session = getattr(g, "db_session", None)
    if db_session is None:
        users_ns.abort(503, "Request-scoped db_session not configured")
    return db_session


def _get_request_actor_user_id():
    """
        Resolve the acting principal's user id from the request context.

        :returns: The acting user id string, or None when anonymous.
    """
    from flask import g
    actor = getattr(g, "actor_user_id", None)
    return actor


def publish_namespaces(version_prefix: str):
    """
        Return namespace registrations for the v1 API wiring.

        :param version_prefix: Version prefix string (``/1``).

        :returns: List of (namespace, path) tuples.
    """
    rtnval = [(users_ns, version_prefix + IDENTITY_USERS_NAMESPACE_PATH)]
    return rtnval
