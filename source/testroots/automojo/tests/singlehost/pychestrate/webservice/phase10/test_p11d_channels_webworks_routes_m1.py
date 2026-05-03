"""
.. module:: test_p11d_channels_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native notification-channel routes.

.. moduleauthor:: Automation Mojo LLC

The channels port is the fourth feature ported to webworks (after
flags in #115, audit in #120, and catalog in #121). It exercises
the full create / list / read CRUD shape against a service-layer
module, with optional query-parameter filtering on the list
endpoint and per-error extension members on the wire body.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from automojo import testbase
from automojo.errors.exceptions import SemanticError
from automojo.testbase.mocking import create_module_patch
from automojo.webworks.routing.response import JSONResponse

from automojo.pychestrate.webservice.api.problem_json import (
    PROBLEM_JSON_MEDIA_TYPE,
    PROBLEM_TYPE_BAD_REQUEST,
    PROBLEM_TYPE_CONFLICT,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
)
from automojo.pychestrate.webservice.notifications import (
    service as notification_service_module,
)
from automojo.pychestrate.webservice.notifications.exceptions import (
    ChannelAlreadyExistsError,
    ChannelNotFoundError,
    UnsupportedChannelKindError,
)
from automojo.pychestrate.webservice.notifications.models import (
    ChannelScopeLevel,
)
from automojo.pychestrate.webservice.notifications.restapi.v1 import (
    channels_routes,
)


# ---------------------------------------------------------------------------
# Test stubs
# ---------------------------------------------------------------------------


class _FakeQueryParams:
    """
        Stand-in for webworks ``QueryParams.get``.
    """

    def __init__(self, *, values: Optional[Dict[str, str]] = None) -> None:
        self._values: Dict[str, str] = values if values is not None else {}
        return

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        rtnval = self._values.get(key, default)
        return rtnval


class _FakeRequest:
    """
        Minimal duck-typed Request. Channels handlers touch
        ``path``, ``path_params``, ``query_params``, ``json()``, and
        the attribute-style ``db_session`` / ``actor_user_id``.
    """

    def __init__(
        self,
        *,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, str]] = None,
        body: Any = None,
        body_raises: bool = False,
        db_session: Optional[Any] = None,
        actor_user_id: Optional[str] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = path_params if path_params is not None else {}
        self.query_params: _FakeQueryParams = _FakeQueryParams(values=query)
        self._body: Any = body
        self._body_raises: bool = body_raises
        self.db_session: Optional[Any] = db_session
        self.actor_user_id: Optional[str] = actor_user_id
        return

    def json(self) -> Any:
        if self._body_raises:
            raise ValueError("malformed json")
        return self._body


class _FakeChannel:
    """
        Stand-in for a :class:`NotificationChannel` ORM row. Attribute
        names match what ``_channel_to_dict`` reads.
    """

    def __init__(
        self,
        *,
        channel_id: str,
        name: str = "ch-x",
        kind: str = "smtp_email",
        scope_level: ChannelScopeLevel = ChannelScopeLevel.SYSTEM,
        project_id: Optional[str] = None,
        disabled: bool = False,
    ) -> None:
        self.channel_id: str = channel_id
        self.name: str = name
        self.kind: str = kind
        self.scope_level: ChannelScopeLevel = scope_level
        self.project_id: Optional[str] = project_id
        self.disabled: bool = disabled
        self.created_at: datetime = datetime(
            2026, 5, 2, 12, 0, 0, tzinfo=timezone.utc
        )
        self.updated_at: datetime = datetime(
            2026, 5, 2, 12, 0, 0, tzinfo=timezone.utc
        )
        return


class _FakeApp:
    """
        Stand-in for a webworks application; records
        ``attach_route(path, methods=...)`` calls.
    """

    def __init__(self) -> None:
        self.calls: List[Tuple[str, Tuple[str, ...], Callable]] = []
        return

    def attach_route(
        self, path: str, methods: Optional[List[str]] = None
    ) -> Callable:
        resolved_methods = tuple(methods if methods is not None else ["GET"])

        def decorator(func: Callable) -> Callable:
            self.calls.append((path, resolved_methods, func))
            rtnval = func
            return rtnval

        rtnval = decorator
        return rtnval


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _raises(exc: BaseException) -> Callable[..., Any]:
    """
        Return a callable that raises ``exc`` when invoked. testbase
        Mock side_effect requires a callable.
    """
    def side(*args: Any, **kwargs: Any) -> Any:
        raise exc

    rtnval = side
    return rtnval


# ---------------------------------------------------------------------------
# Route registration matrix
# ---------------------------------------------------------------------------


def test_register_channels_routes_attaches_three_routes_under_version_prefix():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: register_channels_routes attaches the same three
    method+path pairs the flask_restx controller exposed.**
    """
    app = _FakeApp()
    channels_routes.register_channels_routes(app=app, version_prefix="/api/v1")

    expected_pairs = (
        ("/api/v1/notifications/channels", ("GET",)),
        ("/api/v1/notifications/channels", ("POST",)),
        ("/api/v1/notifications/channels/{channel_id}", ("GET",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


def test_register_channels_routes_declares_collection_before_parameterized():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: The collection routes register before the
    parameterized ``/{channel_id}`` route. Without that ordering the
    webworks router could match GET on the collection to the detail
    handler with an empty path param.**
    """
    app = _FakeApp()
    channels_routes.register_channels_routes(app=app, version_prefix="/api/v1")

    fixed_index = None
    parameterized_index = None
    for index, (path, _, _) in enumerate(app.calls):
        if path == "/api/v1/notifications/channels" and fixed_index is None:
            fixed_index = index
        if (
            path == "/api/v1/notifications/channels/{channel_id}"
            and parameterized_index is None
        ):
            parameterized_index = index

    testbase.assert_equal(fixed_index is not None, True)
    testbase.assert_equal(parameterized_index is not None, True)
    testbase.assert_equal(fixed_index < parameterized_index, True)
    return


# ---------------------------------------------------------------------------
# 503 misconfig path
# ---------------------------------------------------------------------------


def test_handle_list_returns_503_when_session_missing():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: A request with no db_session attached produces the
    same 503 problem document the flask controller emitted.**
    """
    request = _FakeRequest(
        path="/api/v1/notifications/channels", db_session=None
    )
    response = channels_routes.handle_list_channels(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


# ---------------------------------------------------------------------------
# handle_create_channel
# ---------------------------------------------------------------------------


def test_handle_create_returns_201_with_serialized_channel_and_actor_propagation():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: Successful create returns 201 with the serialized
    channel dict and the ``actor_user_id`` from the request
    propagates to ``notification_service.create_channel`` so audit
    attribution is preserved.**
    """
    channel = _FakeChannel(
        channel_id="ch-1", name="ops-alerts", scope_level=ChannelScopeLevel.SYSTEM
    )
    create_patch = create_module_patch(
        notification_service_module, "create_channel"
    )
    try:
        mock_create = create_patch.activate()
        mock_create.configure(return_value=channel)
        request = _FakeRequest(
            path="/api/v1/notifications/channels",
            db_session=object(),
            actor_user_id="user-42",
            body={
                "name": "ops-alerts",
                "kind": "smtp_email",
                "scope_level": "SYSTEM",
                "config": {"smtp_host": "mail"},
            },
        )
        response = channels_routes.handle_create_channel(request)
    finally:
        create_patch.deactivate()

    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["channel_id"], "ch-1")
    testbase.assert_equal(body["name"], "ops-alerts")
    positional_args, keyword_args = mock_create.call_args_list[0]
    testbase.assert_equal(keyword_args["actor_user_id"], "user-42")
    testbase.assert_equal(keyword_args["scope_level"], ChannelScopeLevel.SYSTEM)
    return


def test_handle_create_returns_400_on_unknown_scope_level():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: An unrecognized scope_level returns 400 problem+json
    with the supplied raw value carried as an extension member —
    upgrade from the flask controller's plain ``message`` body.**
    """
    request = _FakeRequest(
        path="/api/v1/notifications/channels",
        db_session=object(),
        body={
            "name": "x",
            "kind": "smtp_email",
            "scope_level": "GARBAGE",
        },
    )
    response = channels_routes.handle_create_channel(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    testbase.assert_equal(body["scope_level"], "GARBAGE")
    return


def test_handle_create_returns_400_on_service_layer_semantic_error():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: A SemanticError from the service layer (e.g.,
    invalid name format) returns 400 problem+json.**
    """
    create_patch = create_module_patch(
        notification_service_module, "create_channel"
    )
    try:
        mock_create = create_patch.activate()
        mock_create.configure(side_effect=_raises(SemanticError("bad name")))
        request = _FakeRequest(
            path="/api/v1/notifications/channels",
            db_session=object(),
            body={
                "name": "$$$",
                "kind": "smtp_email",
                "scope_level": "SYSTEM",
            },
        )
        response = channels_routes.handle_create_channel(request)
    finally:
        create_patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    return


def test_handle_create_returns_400_on_unsupported_channel_kind():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: An unsupported channel kind returns 400 problem+json
    with the kind carried as an extension member.**
    """
    create_patch = create_module_patch(
        notification_service_module, "create_channel"
    )
    try:
        mock_create = create_patch.activate()
        mock_create.configure(
            side_effect=_raises(UnsupportedChannelKindError("no such kind"))
        )
        request = _FakeRequest(
            path="/api/v1/notifications/channels",
            db_session=object(),
            body={
                "name": "x",
                "kind": "carrier_pigeon",
                "scope_level": "SYSTEM",
            },
        )
        response = channels_routes.handle_create_channel(request)
    finally:
        create_patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["kind"], "carrier_pigeon")
    return


def test_handle_create_returns_409_on_duplicate_with_name_extension():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: A duplicate channel name returns 409 problem+json
    carrying the name as an extension member.**
    """
    create_patch = create_module_patch(
        notification_service_module, "create_channel"
    )
    try:
        mock_create = create_patch.activate()
        mock_create.configure(
            side_effect=_raises(ChannelAlreadyExistsError("dupe"))
        )
        request = _FakeRequest(
            path="/api/v1/notifications/channels",
            db_session=object(),
            body={
                "name": "ops-alerts",
                "kind": "smtp_email",
                "scope_level": "SYSTEM",
            },
        )
        response = channels_routes.handle_create_channel(request)
    finally:
        create_patch.deactivate()

    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_CONFLICT)
    testbase.assert_equal(body["name"], "ops-alerts")
    return


def test_handle_create_returns_400_when_body_is_not_json():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: An undecodable request body returns 400 problem+json,
    not 500.**
    """
    request = _FakeRequest(
        path="/api/v1/notifications/channels",
        db_session=object(),
        body_raises=True,
    )
    response = channels_routes.handle_create_channel(request)
    testbase.assert_equal(response.status_code, 400)
    return


def test_handle_create_defaults_config_to_empty_dict_when_omitted():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: When the payload omits ``config`` (or sets it to
    null), the handler passes an empty dict to the service layer.
    Mirrors the flask controller's ``payload.get('config', {}) or {}``
    coalesce.**
    """
    channel = _FakeChannel(channel_id="ch-1")
    create_patch = create_module_patch(
        notification_service_module, "create_channel"
    )
    try:
        mock_create = create_patch.activate()
        mock_create.configure(return_value=channel)
        request = _FakeRequest(
            path="/api/v1/notifications/channels",
            db_session=object(),
            body={
                "name": "ops",
                "kind": "smtp_email",
                "scope_level": "SYSTEM",
            },
        )
        channels_routes.handle_create_channel(request)
        positional_args, keyword_args = mock_create.call_args_list[0]
        testbase.assert_equal(keyword_args["config"], {})
    finally:
        create_patch.deactivate()
    return


# ---------------------------------------------------------------------------
# handle_list_channels
# ---------------------------------------------------------------------------


def test_handle_list_returns_serialized_channels_with_no_filters():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: With no query filters, the handler returns 200 with
    a JSON list derived from ``notification_service.list_channels``
    called with scope_level=None and project_id=None.**
    """
    channels = [
        _FakeChannel(channel_id="ch-1", name="ops-alerts"),
        _FakeChannel(channel_id="ch-2", name="release-notes"),
    ]
    list_patch = create_module_patch(
        notification_service_module, "list_channels"
    )
    try:
        mock_list = list_patch.activate()
        mock_list.configure(return_value=channels)
        request = _FakeRequest(
            path="/api/v1/notifications/channels", db_session=object()
        )
        response = channels_routes.handle_list_channels(request)

        testbase.assert_equal(response.status_code, 200)
        body = _decode_body(response)
        testbase.assert_equal(len(body), 2)
        testbase.assert_equal(body[0]["channel_id"], "ch-1")
        positional_args, keyword_args = mock_list.call_args_list[0]
        testbase.assert_equal(keyword_args["scope_level"], None)
        testbase.assert_equal(keyword_args["project_id"], None)
    finally:
        list_patch.deactivate()
    return


def test_handle_list_propagates_scope_and_project_filters():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: The scope_level + project_id query parameters are
    coerced and forwarded to ``notification_service.list_channels``
    so wire callers can scope the result.**
    """
    list_patch = create_module_patch(
        notification_service_module, "list_channels"
    )
    try:
        mock_list = list_patch.activate()
        mock_list.configure(return_value=[])
        request = _FakeRequest(
            path="/api/v1/notifications/channels",
            db_session=object(),
            query={"scope_level": "PROJECT", "project_id": "proj-7"},
        )
        channels_routes.handle_list_channels(request)
        positional_args, keyword_args = mock_list.call_args_list[0]
        testbase.assert_equal(
            keyword_args["scope_level"], ChannelScopeLevel.PROJECT
        )
        testbase.assert_equal(keyword_args["project_id"], "proj-7")
    finally:
        list_patch.deactivate()
    return


def test_handle_list_returns_400_on_unknown_scope_filter():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: A garbage scope_level query param returns 400
    problem+json with the raw value as an extension member.**
    """
    request = _FakeRequest(
        path="/api/v1/notifications/channels",
        db_session=object(),
        query={"scope_level": "GARBAGE"},
    )
    response = channels_routes.handle_list_channels(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["scope_level"], "GARBAGE")
    return


def test_handle_list_treats_blank_scope_filter_as_unset():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: A whitespace-only scope_level query is treated as
    unset (no filter), matching the flask controller's
    ``len(scope_arg.strip()) > 0`` guard.**
    """
    list_patch = create_module_patch(
        notification_service_module, "list_channels"
    )
    try:
        mock_list = list_patch.activate()
        mock_list.configure(return_value=[])
        request = _FakeRequest(
            path="/api/v1/notifications/channels",
            db_session=object(),
            query={"scope_level": "   "},
        )
        channels_routes.handle_list_channels(request)
        positional_args, keyword_args = mock_list.call_args_list[0]
        testbase.assert_equal(keyword_args["scope_level"], None)
    finally:
        list_patch.deactivate()
    return


# ---------------------------------------------------------------------------
# handle_read_channel
# ---------------------------------------------------------------------------


def test_handle_read_returns_serialized_channel_on_match():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: A known channel id returns 200 with the serialized
    channel dict.**
    """
    channel = _FakeChannel(channel_id="ch-1", name="ops-alerts")
    read_patch = create_module_patch(
        notification_service_module, "read_channel"
    )
    try:
        mock_read = read_patch.activate()
        mock_read.configure(return_value=channel)
        request = _FakeRequest(
            path="/api/v1/notifications/channels/ch-1",
            path_params={"channel_id": "ch-1"},
            db_session=object(),
        )
        response = channels_routes.handle_read_channel(request)
    finally:
        read_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["channel_id"], "ch-1")
    return


def test_handle_read_returns_404_with_channel_id_extension():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: An unknown channel id returns 404 problem+json with
    the channel id as an extension member — upgrade from the flask
    controller's plain ``message`` body.**
    """
    read_patch = create_module_patch(
        notification_service_module, "read_channel"
    )
    try:
        mock_read = read_patch.activate()
        mock_read.configure(
            side_effect=_raises(ChannelNotFoundError("no such channel"))
        )
        request = _FakeRequest(
            path="/api/v1/notifications/channels/ch-missing",
            path_params={"channel_id": "ch-missing"},
            db_session=object(),
        )
        response = channels_routes.handle_read_channel(request)
    finally:
        read_patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["channel_id"], "ch-missing")
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_channels_routes_and_calls_it():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: app_pychestrate_main.py wires
    register_channels_routes into register_service_extensions so the
    routes are queued before app.startup. Source-level smoke; full
    app boot is out of scope for the singlehost suite.**
    """
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    repo_source_root = os.path.normpath(
        os.path.join(
            here, "..", "..", "..", "..", "..", "..", "..", "..",
            "source", "site",
        )
    )
    bootstrap_path = os.path.join(repo_source_root, "app_pychestrate_main.py")
    with open(bootstrap_path, "r", encoding="utf-8") as fh:
        text = fh.read()

    has_import = (
        "from automojo.pychestrate.webservice.notifications.restapi.v1.channels_routes import"
        in text
    )
    has_call = "register_channels_routes(app=app, version_prefix=\"/api/v1\")" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return


# ---------------------------------------------------------------------------
# Wire-shape sweep
# ---------------------------------------------------------------------------


def test_every_error_response_is_application_problem_json():
    """
    **Feature: 2-notification-hub T1.1 (webworks routes)**
    **Property: 503 / 400 / 404 / 409 all carry the documented
    ``application/problem+json`` content type and round-trip through
    the real ``JSONResponse``.**
    """
    cases: List[Any] = []

    cases.append(channels_routes.handle_list_channels(
        _FakeRequest(path="/api/v1/notifications/channels", db_session=None)
    ))

    cases.append(channels_routes.handle_create_channel(
        _FakeRequest(
            path="/api/v1/notifications/channels",
            db_session=object(),
            body={"name": "x", "kind": "smtp_email", "scope_level": "GARBAGE"},
        )
    ))

    create_patch = create_module_patch(
        notification_service_module, "create_channel"
    )
    try:
        mock_create = create_patch.activate()
        mock_create.configure(
            side_effect=_raises(ChannelAlreadyExistsError("dupe"))
        )
        cases.append(channels_routes.handle_create_channel(
            _FakeRequest(
                path="/api/v1/notifications/channels",
                db_session=object(),
                body={
                    "name": "x", "kind": "smtp_email", "scope_level": "SYSTEM"
                },
            )
        ))
    finally:
        create_patch.deactivate()

    read_patch = create_module_patch(
        notification_service_module, "read_channel"
    )
    try:
        mock_read = read_patch.activate()
        mock_read.configure(
            side_effect=_raises(ChannelNotFoundError("missing"))
        )
        cases.append(channels_routes.handle_read_channel(
            _FakeRequest(
                path="/api/v1/notifications/channels/x",
                path_params={"channel_id": "x"},
                db_session=object(),
            )
        ))
    finally:
        read_patch.deactivate()

    for response in cases:
        testbase.assert_equal(
            response.headers["Content-Type"], PROBLEM_JSON_MEDIA_TYPE
        )
        is_json_response = isinstance(response, JSONResponse)
        testbase.assert_equal(is_json_response, True)
    return
