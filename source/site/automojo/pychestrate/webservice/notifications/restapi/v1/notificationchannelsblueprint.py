"""
.. module:: notifications.restapi.v1.notificationchannelsblueprint
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/notifications/channels.

.. moduleauthor:: Automation Mojo LLC

Migrated from Flask + flask-restx to automojo-webworks.
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

from automojo.pychestrate.webservice.middleware_webworks import (
    get_request_actor_user_id,
)
from automojo.pychestrate.webservice.notifications import (
    service as notification_service,
)
from automojo.pychestrate.webservice.notifications.exceptions import (
    ChannelAlreadyExistsError,
    ChannelNotFoundError,
    UnsupportedChannelKindError,
)
from automojo.pychestrate.webservice.notifications.models import (
    ChannelScopeLevel,
)


NOTIFICATION_CHANNELS_BASE_PATH = "/api/v1/notifications/channels"


def _channel_to_dict(channel) -> Dict[str, Any]:
    """
        Render a :class:`NotificationChannel` as the REST response dict.
    """
    if channel.project_id is not None:
        project_id_field: Optional[str] = str(channel.project_id)
    else:
        project_id_field = None
    if channel.created_at is not None:
        created_at_field: Optional[str] = channel.created_at.isoformat()
    else:
        created_at_field = None
    if channel.updated_at is not None:
        updated_at_field: Optional[str] = channel.updated_at.isoformat()
    else:
        updated_at_field = None
    rtnval = {
        "channel_id": str(channel.channel_id),
        "name": channel.name,
        "kind": channel.kind,
        "scope_level": channel.scope_level.value,
        "project_id": project_id_field,
        "disabled": bool(channel.disabled),
        "created_at": created_at_field,
        "updated_at": updated_at_field,
    }
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


class NotificationChannelsBlueprint(RestBlueprint):
    """
        Blueprint grouping the v1 ``/api/v1/notifications/channels`` endpoints.
    """

    base_path = NOTIFICATION_CHANNELS_BASE_PATH
    tags = ["notifications", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/notifications/channels",
        methods=["POST"],
        doc=Doc(
            summary="Create notification channel",
            description="Create a new notification channel.",
        ),
    )
    def create_channel(request: Request) -> JSONResponse:
        """
            Create a new notification channel.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        actor_user_id = get_request_actor_user_id(request=request)

        scope_raw = str(payload.get("scope_level", "")).strip().upper()
        try:
            scope_level = ChannelScopeLevel[scope_raw]
        except KeyError as exc:
            err_msg = "Unknown scope_level: {}".format(scope_raw)
            raise HTTPException(status_code=400, detail=err_msg) from exc

        config_raw = payload.get("config", {})
        if config_raw is None:
            config_value = {}
        else:
            config_value = config_raw

        try:
            channel = notification_service.create_channel(
                db_session=db_session,
                name=payload.get("name", ""),
                kind=payload.get("kind", ""),
                scope_level=scope_level,
                project_id=payload.get("project_id", None),
                config=config_value,
                actor_user_id=actor_user_id,
            )
        except SemanticError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc
        except UnsupportedChannelKindError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc
        except ChannelAlreadyExistsError as exc:
            raise HTTPException(
                status_code=409, detail=str(exc),
            ) from exc

        body = _channel_to_dict(channel=channel)
        rtnval = JSONResponse(content=body, status_code=201)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/notifications/channels",
        methods=["GET"],
        doc=Doc(
            summary="List notification channels",
            description=(
                "List notification channels. Supports scope_level "
                "and project_id query-string filters."
            ),
        ),
    )
    def list_channels(request: Request) -> JSONResponse:
        """
            List notification channels with optional filters.
        """
        db_session = _require_db_session(request=request)

        scope_arg = request.query_params.get("scope_level", None)
        project_arg = request.query_params.get("project_id", None)

        scope_level: Optional[ChannelScopeLevel] = None
        if scope_arg is not None:
            stripped = scope_arg.strip()
            if len(stripped) > 0:
                try:
                    scope_level = ChannelScopeLevel[stripped.upper()]
                except KeyError as exc:
                    err_msg = "Unknown scope_level: {}".format(scope_arg)
                    raise HTTPException(
                        status_code=400, detail=err_msg,
                    ) from exc

        channels = notification_service.list_channels(
            db_session=db_session,
            scope_level=scope_level,
            project_id=project_arg,
        )
        body = [_channel_to_dict(channel=ch) for ch in channels]
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/notifications/channels/{channel_id}",
        methods=["GET"],
        doc=Doc(
            summary="Read notification channel",
            description="Fetch a single notification channel by id.",
        ),
    )
    def read_channel(request: Request) -> JSONResponse:
        """
            Fetch one notification channel.
        """
        db_session = _require_db_session(request=request)
        channel_id = request.path_params.get("channel_id", "")

        try:
            channel = notification_service.read_channel(
                db_session=db_session, channel_id=channel_id,
            )
        except ChannelNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc

        body = _channel_to_dict(channel=channel)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval
