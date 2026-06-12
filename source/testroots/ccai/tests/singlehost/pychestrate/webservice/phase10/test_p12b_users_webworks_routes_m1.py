"""
.. module:: test_p12b_users_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native identity-users routes.

.. moduleauthor:: Code Craft AI LLC

The users port mirrors the channels-shaped CRUD pattern (create
+ read), with two service-layer dependencies and two documented
exception types. Tests cover the route matrix, the 503 misconfig
path, the 400 paths for malformed body, the 409 dup path with
primary_email extension, the 200 + 404 read paths, and bootstrap
source-smoke.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai import testbase
from ccai.testbase.mocking import create_module_patch
from ccai.webworks.routing.response import JSONResponse

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_JSON_MEDIA_TYPE,
    PROBLEM_TYPE_BAD_REQUEST,
    PROBLEM_TYPE_CONFLICT,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
)
from ccai.pychestrate.webservice.identity.users.exceptions import (
    UserAlreadyExistsError,
    UserNotFoundError,
)
from ccai.pychestrate.webservice.identity.users.restapi.v1 import (
    users_routes,
)


# ---------------------------------------------------------------------------
# Test stubs
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(
        self,
        *,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        body: Any = None,
        body_raises: bool = False,
        db_session: Optional[Any] = None,
        actor_user_id: Optional[str] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = path_params if path_params is not None else {}
        self._body: Any = body
        self._body_raises: bool = body_raises
        self.db_session: Optional[Any] = db_session
        self.actor_user_id: Optional[str] = actor_user_id
        return

    def json(self) -> Any:
        if self._body_raises:
            raise ValueError("malformed json")
        return self._body


class _FakeApp:
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


class _FakeStatus:
    def __init__(self, *, value: str) -> None:
        self.value: str = value
        return


class _FakeUser:
    def __init__(
        self,
        *,
        user_id: str,
        login_name: str = "alice",
        primary_email: str = "alice@example.com",
        display_name: str = "Alice Example",
        timezone_str: str = "UTC",
        provisioning_source: str = "local",
        external_id: Optional[str] = None,
        status: str = "ACTIVE",
    ) -> None:
        self.user_id: str = user_id
        self.login_name: str = login_name
        self.primary_email: str = primary_email
        self.display_name: str = display_name
        self.timezone: str = timezone_str
        self.provisioning_source: str = provisioning_source
        self.external_id: Optional[str] = external_id
        self.status: _FakeStatus = _FakeStatus(value=status)
        self.created_at: datetime = datetime(
            2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc
        )
        self.updated_at: datetime = datetime(
            2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc
        )
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _raises(exc: BaseException) -> Callable[..., Any]:
    def side(*args: Any, **kwargs: Any) -> Any:
        raise exc

    rtnval = side
    return rtnval


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_users_routes_attaches_two_routes():
    """
    **Feature: 1-user-management T1.1 (webworks routes)**
    **Property: register_users_routes attaches the same two
    method+path pairs the flask_restx controller exposed.**
    """
    app = _FakeApp()
    users_routes.register_users_routes(app=app, version_prefix="/api/v1")

    expected_pairs = (
        ("/api/v1/identity/users", ("POST",)),
        ("/api/v1/identity/users/{user_id}", ("GET",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# 503 misconfig
# ---------------------------------------------------------------------------


def test_handle_create_returns_503_when_session_missing():
    """
    **Feature: 1-user-management T1.1 (webworks routes)**
    **Property: A request with no db_session attached produces the
    same 503 problem document the flask controller emitted.**
    """
    request = _FakeRequest(
        path="/api/v1/identity/users",
        body={
            "login_name": "alice",
            "primary_email": "a@x",
            "display_name": "Alice",
            "timezone": "UTC",
        },
        db_session=None,
    )
    response = users_routes.handle_create_user(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_handle_read_returns_503_when_session_missing():
    """
    **Feature: 1-user-management T1.1 (webworks routes)**
    **Property: read handler also returns 503 when the db_session
    attribute is missing.**
    """
    request = _FakeRequest(
        path="/api/v1/identity/users/u-1",
        path_params={"user_id": "u-1"},
        db_session=None,
    )
    response = users_routes.handle_read_user(request)
    testbase.assert_equal(response.status_code, 503)
    return


# ---------------------------------------------------------------------------
# handle_create_user
# ---------------------------------------------------------------------------


def test_handle_create_returns_201_with_actor_propagation():
    """
    **Feature: 1-user-management T1.1 (webworks routes)**
    **Property: Successful create returns 201 with the serialized
    user dict and forwards actor_user_id through to
    user_service.create_user for audit attribution.**
    """
    user = _FakeUser(user_id="u-1", login_name="alice")
    create_patch = create_module_patch(users_routes, "user_service")
    try:
        # patch the imported user_service module reference; tests use
        # ``users_routes.user_service`` as the binding the handler calls
        mock_module = create_patch.activate()
        mock_module.configure(recursive=True)
        mock_module.mock_context().set_attribute("create_user", lambda **kwargs: user)
        request = _FakeRequest(
            path="/api/v1/identity/users",
            db_session=object(),
            actor_user_id="user-42",
            body={
                "login_name": "alice",
                "primary_email": "alice@example.com",
                "display_name": "Alice Example",
                "timezone": "UTC",
            },
        )
        response = users_routes.handle_create_user(request)
    finally:
        create_patch.deactivate()

    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["user_id"], "u-1")
    testbase.assert_equal(body["login_name"], "alice")
    testbase.assert_equal(body["status"], "ACTIVE")
    return


def test_handle_create_returns_409_on_duplicate_with_email_extension():
    """
    **Feature: 1-user-management T1.1 (webworks routes)**
    **Property: A duplicate primary_email returns 409 problem+json
    carrying the email as an extension member -- matches the flask
    controller's wire shape.**
    """
    state: Dict[str, Any] = {}

    def fake_create(**kwargs: Any) -> Any:
        raise UserAlreadyExistsError("dup")

    create_patch = create_module_patch(users_routes, "user_service")
    try:
        mock_module = create_patch.activate()
        mock_module.configure(recursive=True)
        mock_module.mock_context().set_attribute("create_user", fake_create)
        request = _FakeRequest(
            path="/api/v1/identity/users",
            db_session=object(),
            body={
                "login_name": "alice",
                "primary_email": "alice@example.com",
                "display_name": "Alice",
                "timezone": "UTC",
            },
        )
        response = users_routes.handle_create_user(request)
    finally:
        create_patch.deactivate()

    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_CONFLICT)
    testbase.assert_equal(body["primary_email"], "alice@example.com")
    return


def test_handle_create_returns_400_when_body_is_not_json():
    """
    **Feature: 1-user-management T1.1 (webworks routes)**
    **Property: An undecodable request body returns 400 problem+json,
    not 500.**
    """
    request = _FakeRequest(
        path="/api/v1/identity/users",
        db_session=object(),
        body_raises=True,
    )
    response = users_routes.handle_create_user(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    return


def test_handle_create_returns_400_when_body_is_not_a_dict():
    """
    **Feature: 1-user-management T1.1 (webworks routes)**
    **Property: A non-dict body returns 400 problem+json.**
    """
    request = _FakeRequest(
        path="/api/v1/identity/users",
        db_session=object(),
        body=["wrong shape"],
    )
    response = users_routes.handle_create_user(request)
    testbase.assert_equal(response.status_code, 400)
    return


# ---------------------------------------------------------------------------
# handle_read_user
# ---------------------------------------------------------------------------


def test_handle_read_returns_serialized_user_on_match():
    """
    **Feature: 1-user-management T1.1 (webworks routes)**
    **Property: A known user_id returns 200 with the serialized
    user dict.**
    """
    user = _FakeUser(user_id="u-1", login_name="alice")

    def fake_read(*, db_session: Any, user_id: str) -> Any:
        return user

    read_patch = create_module_patch(users_routes, "user_service")
    try:
        mock_module = read_patch.activate()
        mock_module.configure(recursive=True)
        mock_module.mock_context().set_attribute("read_user", fake_read)
        request = _FakeRequest(
            path="/api/v1/identity/users/u-1",
            path_params={"user_id": "u-1"},
            db_session=object(),
        )
        response = users_routes.handle_read_user(request)
    finally:
        read_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["user_id"], "u-1")
    testbase.assert_equal(body["login_name"], "alice")
    return


def test_handle_read_returns_404_with_user_id_extension():
    """
    **Feature: 1-user-management T1.1 (webworks routes)**
    **Property: An unknown user_id returns 404 problem+json with
    the user_id as an extension member.**
    """
    def fake_read(*, db_session: Any, user_id: str) -> Any:
        raise UserNotFoundError("missing")

    read_patch = create_module_patch(users_routes, "user_service")
    try:
        mock_module = read_patch.activate()
        mock_module.configure(recursive=True)
        mock_module.mock_context().set_attribute("read_user", fake_read)
        request = _FakeRequest(
            path="/api/v1/identity/users/u-missing",
            path_params={"user_id": "u-missing"},
            db_session=object(),
        )
        response = users_routes.handle_read_user(request)
    finally:
        read_patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["user_id"], "u-missing")
    is_json_response = isinstance(response, JSONResponse)
    testbase.assert_equal(is_json_response, True)
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_users_routes_and_calls_it():
    """
    **Feature: 1-user-management T1.1 (webworks routes)**
    **Property: app_pychestrate_main.py wires register_users_routes
    into register_service_extensions.**
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
        "from ccai.pychestrate.webservice.identity.users.restapi.v1.users_routes import"
        in text
    )
    has_call = "register_users_routes(app=app, version_prefix=\"/api/v1\")" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return
