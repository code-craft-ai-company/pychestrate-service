"""
.. module:: notifications.restapi.v1.channels_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/notifications/channels.

.. moduleauthor:: Automation Mojo LLC

The production webservice runs on ``automojo.webworks`` (see
:mod:`app_pychestrate_main`). This module is the webworks-native
REST surface for the notification channel CRUD endpoints,
replacing the flask_restx ``channels_controller`` next to it.

Three routes mirror the flask_restx controller's matrix:

* ``POST /api/v1/notifications/channels``
  — create a channel.
* ``GET  /api/v1/notifications/channels``
  — list channels with optional ``scope_level`` and ``project_id``
  query filters.
* ``GET  /api/v1/notifications/channels/{channel_id}``
  — read one channel.

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`. The flask controller's
``channels_ns.abort(400|404|409, ...)`` calls (which produced
flask's ``{"message": "..."}`` body) become documented problem
documents with the channel id / scope level / kind carried as
extension members where they apply.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Optional

from automojo.errors.exceptions import SemanticError
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
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


CHANNELS_PATH = "/notifications/channels"


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks problem
        response so nested helpers can signal an error condition once
        and the handler can convert it to a return at the boundary.

        Never escapes this module.
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
        Build a problem response from the request context and raise
        :class:`_ProblemAbort` so the handler returns the response.

        :param request: Incoming webworks request (used for the
                        ``instance`` URI).
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param extensions: Optional namespaced extension members.

        :returns: Never returns; raises :class:`_ProblemAbort`.
        :raises: :class:`_ProblemAbort` always.
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
        Return the request-scoped db session attached by
        :class:`PychestrateSessionMiddleware`, or ``None`` when no
        middleware has populated it.

        Module-level so tests can patch this rather than constructing
        a full middleware stack.

        :param request: Incoming webworks request.

        :returns: Session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _resolve_actor_user_id(request: Request) -> Optional[str]:
    """
        Return the authenticated actor's user id from the request, or
        ``None`` when no auth middleware has populated it.

        :param request: Incoming webworks request.

        :returns: User id string or None.
    """
    rtnval = getattr(request, "actor_user_id", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort with a 503
        problem document. Mirrors the flask controller's
        ``"Request-scoped db_session not configured"`` wire response
        on misconfigured deployments.

        :param request: Incoming webworks request.

        :returns: Session.
        :raises: :class:`_ProblemAbort` (503) when no session is
                 attached.
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


def _parse_scope_level_or_abort(
        *, request: Request, raw: str
    ) -> ChannelScopeLevel:
    """
        Coerce a ``scope_level`` string to a :class:`ChannelScopeLevel`
        enum, aborting with a 400 problem document on unknown values.

        :param request: Incoming webworks request (for the instance
                        URI).
        :param raw: Raw value from the request payload or query
                    parameter.

        :returns: The matching :class:`ChannelScopeLevel`.
        :raises: :class:`_ProblemAbort` (400) on unknown values.
    """
    normalized = raw.strip().upper()
    try:
        scope_level = ChannelScopeLevel[normalized]
    except KeyError:
        _abort_problem(
            request=request,
            status=400,
            detail="Unknown scope_level: {}".format(raw),
            extensions={"scope_level": raw},
        )

    rtnval = scope_level
    return rtnval


def _decode_json_or_abort(*, request: Request) -> dict:
    """
        Decode the request body as JSON, aborting with a 400 when the
        body is missing or malformed.

        :param request: Incoming webworks request.

        :returns: Decoded JSON object (always a dict; non-dict
                  bodies abort).
        :raises: :class:`_ProblemAbort` (400) on bad input.
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


def _channel_to_dict(channel: Any) -> dict:
    """
        Render a :class:`NotificationChannel` ORM row as the REST
        response dict.

        :param channel: ORM channel instance.

        :returns: JSON-friendly dict.
    """
    rtnval = {
        "channel_id": str(channel.channel_id),
        "name": channel.name,
        "kind": channel.kind,
        "scope_level": channel.scope_level.value,
        "project_id": (
            str(channel.project_id) if channel.project_id is not None else None
        ),
        "disabled": bool(channel.disabled),
        "created_at": (
            channel.created_at.isoformat() if channel.created_at is not None else None
        ),
        "updated_at": (
            channel.updated_at.isoformat() if channel.updated_at is not None else None
        ),
    }
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_create_channel(request: Request) -> Response:
    """
        ``POST /api/v1/notifications/channels`` — create a new
        channel. Returns 201 with the serialized channel dict.

        :param request: Incoming webworks request.

        :returns: JSON response (201) carrying the channel dict, or
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

        config_value = payload.get("config", None)
        if config_value is None:
            config_value = {}

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
        except SemanticError as xcpt:
            _abort_problem(
                request=request, status=400, detail=str(xcpt)
            )
        except UnsupportedChannelKindError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={"kind": payload.get("kind", "")},
            )
        except ChannelAlreadyExistsError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"name": payload.get("name", "")},
            )

        body = _channel_to_dict(channel)
        rtnval: Response = JSONResponse(content=body, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_list_channels(request: Request) -> Response:
    """
        ``GET /api/v1/notifications/channels`` — list channels.
        Optional ``scope_level`` and ``project_id`` query params filter
        the result.

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying a list of channel
                  dicts, or problem response on failure.
    """
    try:
        db_session = _require_session(request=request)

        scope_arg = request.query_params.get("scope_level", None)
        project_arg = request.query_params.get("project_id", None)

        scope_level: Optional[ChannelScopeLevel] = None
        if scope_arg is not None and len(scope_arg.strip()) > 0:
            scope_level = _parse_scope_level_or_abort(
                request=request, raw=scope_arg
            )

        channels = notification_service.list_channels(
            db_session=db_session,
            scope_level=scope_level,
            project_id=project_arg,
        )
        body = [_channel_to_dict(channel) for channel in channels]
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_read_channel(request: Request) -> Response:
    """
        ``GET /api/v1/notifications/channels/{channel_id}`` — read a
        single channel. Returns 404 problem+json with the channel id
        as an extension member when the channel does not exist.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the channel dict, or
                  problem response on failure.
    """
    channel_id = request.path_params.get("channel_id", "")
    try:
        db_session = _require_session(request=request)

        try:
            channel = notification_service.read_channel(
                db_session=db_session, channel_id=channel_id,
            )
        except ChannelNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"channel_id": channel_id},
            )

        body = _channel_to_dict(channel)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_channels_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the notification-channel routes to a webworks
        application.

        Called from :func:`pychestrate_website_main` -
        :func:`register_service_extensions` before
        ``app.startup``. Routes are queued until the
        infrastructure-ready phase and flushed there.

        Note that the fixed channels collection path is registered
        BEFORE the ``/{channel_id}`` parameterized route. The webworks
        router resolves overlapping patterns by registration order.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + CHANNELS_PATH

    app.attach_route(base, methods=["GET"])(handle_list_channels)
    app.attach_route(base, methods=["POST"])(handle_create_channel)
    app.attach_route(
        base + "/{channel_id}", methods=["GET"]
    )(handle_read_channel)

    return


__all__ = [
    "CHANNELS_PATH",
    "register_channels_routes",
    "handle_create_channel",
    "handle_list_channels",
    "handle_read_channel",
]
