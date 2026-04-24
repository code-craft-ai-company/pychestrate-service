"""
.. module:: notifications.restapi.v1.channels_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/notifications/channels.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import request
from flask_restx import Namespace, Resource, fields

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.notifications import service as notification_service
from automojo.pychestrate.webservice.notifications.exceptions import (
    ChannelAlreadyExistsError,
    ChannelNotFoundError,
    UnsupportedChannelKindError,
)
from automojo.pychestrate.webservice.notifications.models import ChannelScopeLevel


NOTIFICATION_CHANNELS_NAMESPACE_PATH = "/notifications/channels"


channels_ns = Namespace(
    "Notification Channels v1",
    description="Notification channel CRUD (2-notification-hub).",
)


channel_create_model = channels_ns.model(
    "NotificationChannelCreate",
    {
        "name": fields.String(required=True, description="Channel name unique in scope"),
        "kind": fields.String(required=True, description="Channel kind (``smtp_email`` at M1)"),
        "scope_level": fields.String(required=True, description="SYSTEM | PROJECT"),
        "project_id": fields.String(required=False, description="Project id when scope_level=PROJECT"),
        "config": fields.Raw(required=False, description="Channel configuration mapping"),
    },
)


channel_response_model = channels_ns.model(
    "NotificationChannelResponse",
    {
        "channel_id": fields.String(description="Server-generated UUID"),
        "name": fields.String(description="Channel name"),
        "kind": fields.String(description="Channel kind"),
        "scope_level": fields.String(description="Scope level"),
        "project_id": fields.String(description="Project id or null"),
        "disabled": fields.Boolean(description="Whether the channel is disabled"),
        "created_at": fields.String(description="ISO-8601 timestamp"),
        "updated_at": fields.String(description="ISO-8601 timestamp"),
    },
)


def _channel_to_dict(channel) -> dict:
    """
        Render a :class:`NotificationChannel` as the REST response dict.
    """
    rtnval = {
        "channel_id": str(channel.channel_id),
        "name": channel.name,
        "kind": channel.kind,
        "scope_level": channel.scope_level.value,
        "project_id": str(channel.project_id) if channel.project_id is not None else None,
        "disabled": bool(channel.disabled),
        "created_at": channel.created_at.isoformat() if channel.created_at is not None else None,
        "updated_at": channel.updated_at.isoformat() if channel.updated_at is not None else None,
    }
    return rtnval


@channels_ns.route("")
class ChannelsList(Resource):
    """
        Resource exposing POST / GET on the channel collection.
    """

    @channels_ns.expect(channel_create_model, validate=True)
    @channels_ns.marshal_with(channel_response_model, code=201)
    def post(self):
        """
            Create a new channel.
        """
        payload = request.get_json(force=True, silent=False)
        db_session = _get_request_db_session()
        actor_user_id = _get_request_actor_user_id()

        raw_scope = str(payload.get("scope_level", "")).strip().upper()
        try:
            scope_level = ChannelScopeLevel[raw_scope]
        except KeyError:
            channels_ns.abort(400, "Unknown scope_level: {}".format(raw_scope))

        try:
            channel = notification_service.create_channel(
                db_session=db_session,
                name=payload.get("name", ""),
                kind=payload.get("kind", ""),
                scope_level=scope_level,
                project_id=payload.get("project_id", None),
                config=payload.get("config", {}) or {},
                actor_user_id=actor_user_id,
            )
        except SemanticError as xcpt:
            channels_ns.abort(400, str(xcpt))
        except UnsupportedChannelKindError as xcpt:
            channels_ns.abort(400, str(xcpt))
        except ChannelAlreadyExistsError as xcpt:
            channels_ns.abort(409, str(xcpt))

        rtnval = _channel_to_dict(channel)
        return rtnval, 201

    @channels_ns.marshal_list_with(channel_response_model)
    def get(self):
        """
            List channels. Optional query params: ``scope_level``, ``project_id``.
        """
        db_session = _get_request_db_session()

        scope_arg = request.args.get("scope_level", None)
        project_arg = request.args.get("project_id", None)

        scope_level = None
        if scope_arg is not None and len(scope_arg.strip()) > 0:
            try:
                scope_level = ChannelScopeLevel[scope_arg.strip().upper()]
            except KeyError:
                channels_ns.abort(400, "Unknown scope_level: {}".format(scope_arg))

        channels = notification_service.list_channels(
            db_session=db_session,
            scope_level=scope_level,
            project_id=project_arg,
        )
        rtnval = [_channel_to_dict(ch) for ch in channels]
        return rtnval


@channels_ns.route("/<string:channel_id>")
@channels_ns.param("channel_id", "The channel id")
class ChannelDetail(Resource):
    """
        Resource exposing GET on a single channel.
    """

    @channels_ns.marshal_with(channel_response_model)
    def get(self, channel_id: str):
        """
            Fetch one channel.
        """
        db_session = _get_request_db_session()
        try:
            channel = notification_service.read_channel(
                db_session=db_session, channel_id=channel_id,
            )
        except ChannelNotFoundError as xcpt:
            channels_ns.abort(404, str(xcpt))

        rtnval = _channel_to_dict(channel)
        return rtnval


def _get_request_db_session():
    """
        Resolve the request-scoped SQLAlchemy session.
    """
    from flask import g
    db_session = getattr(g, "db_session", None)
    if db_session is None:
        channels_ns.abort(503, "Request-scoped db_session not configured")
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
    rtnval = [(channels_ns, version_prefix + NOTIFICATION_CHANNELS_NAMESPACE_PATH)]
    return rtnval
