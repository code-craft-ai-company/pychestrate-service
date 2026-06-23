"""
.. module:: test_p10w_flags_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native flag REST routes.

.. moduleauthor:: Code Craft AI LLC

The webworks port of the flag REST surface is the first webworks
route module in the tree. Tests cover three layers:

* The route matrix matches the original flask_restx
  ``flags_controller`` (8 method+path pairs).
* Each handler's success path produces the documented JSON shape
  with the right status code.
* Each handler's error paths produce RFC 7807 problem responses
  served as ``application/problem+json``.

Service-layer functions are patched via
``ccai.testbase.mocking.create_module_patch`` so the handlers
are exercised without a real database. The route registration is
tested against a stub app that records ``attach_route`` calls.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai import testbase
from ccai.errors.exceptions import SemanticError
from ccai.testbase.mocking import create_module_patch
from ccai.webworks.routing.response import JSONResponse

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_JSON_MEDIA_TYPE,
    PROBLEM_TYPE_BAD_REQUEST,
    PROBLEM_TYPE_CONFLICT,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_VALIDATION_FAILED,
)
from ccai.pychestrate.webservice.identity.flags import (
    backend_router as backend_router_module,
    flag_evaluator as flag_evaluator_module,
    flag_service as flag_service_module,
)
from ccai.pychestrate.webservice.identity.flags.exceptions import (
    FlagAlreadyExistsError,
    FlagNotFoundError,
)
from ccai.pychestrate.webservice.identity.flags.models import FlagKind
from ccai.pychestrate.webservice.identity.flags.restapi.v1 import (
    flags_routes,
)


# ---------------------------------------------------------------------------
# Test stubs
# ---------------------------------------------------------------------------


class _FakeRequest:
    """
        Minimal duck-typed Request for the handlers. The handlers
        only touch ``path``, ``path_params``, ``json()``, and the
        attribute-style ``db_session`` / ``actor_user_id`` lookups.
    """

    def __init__(
        self,
        *,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        body: Optional[Any] = None,
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


class _FakeFlag:
    """
        Stand-in for a :class:`FeatureFlag` ORM row. Attributes match
        the keys that ``_flag_to_dict`` reads.
    """

    def __init__(
        self,
        *,
        flag_key: str,
        flag_kind: FlagKind,
        current_version: int = 1,
    ) -> None:
        self.flag_key: str = flag_key
        self.flag_kind: FlagKind = flag_kind
        self.current_version: int = current_version
        self.state = None
        self.retired_at = None
        self.grace_expires_at = None
        self.created_at = None
        self.updated_at = None
        return


class _FakeVersion:
    """
        Stand-in for a :class:`FeatureFlagVersion` ORM row.
    """

    def __init__(
        self,
        *,
        flag_key: str,
        version: int,
        default_value: Any,
        rules_json: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.flag_key: str = flag_key
        self.version: int = version
        self.default_value: Any = default_value
        self.rules_json: Optional[Dict[str, Any]] = rules_json
        self.created_at = None
        return


class _FakeApp:
    """
        Stand-in for a webworks application; records the
        ``attach_route(path, methods=...)`` calls so registration
        tests can assert on the route matrix.
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


def _decode_problem_body(response: Any) -> Dict[str, Any]:
    """
        Decode a problem+json response's wire body into a dict.

        :param response: The :class:`JSONResponse` returned by a
                         handler.

        :returns: Parsed body dict.
    """
    body_bytes = response.body
    body_text = body_bytes.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _decode_json_body(response: Any) -> Any:
    """
        Decode any JSONResponse's body to a Python value.

        :param response: The :class:`JSONResponse` returned by a
                         handler.

        :returns: Parsed body.
    """
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _raises(exc: BaseException) -> Callable[..., Any]:
    """
        Return a callable that raises the supplied exception when
        invoked. The testbase mocking framework requires
        ``side_effect`` to be a callable (or a SideEffect instance);
        passing an exception instance directly is not supported.

        :param exc: Exception to raise on invocation.

        :returns: Callable that always raises ``exc``.
    """
    def side(*args: Any, **kwargs: Any) -> Any:
        raise exc

    rtnval = side
    return rtnval


# ---------------------------------------------------------------------------
# Route registration matrix
# ---------------------------------------------------------------------------


def test_register_flags_routes_attaches_eight_routes_under_version_prefix():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: register_flags_routes attaches the same eight
    method+path pairs the flask_restx controller exposed, prefixed
    with the supplied version path.**
    """
    app = _FakeApp()
    flags_routes.register_flags_routes(app=app, version_prefix="/api/v1")

    expected_pairs = (
        ("/api/v1/flags/backends", ("GET",)),
        ("/api/v1/flags", ("GET",)),
        ("/api/v1/flags", ("POST",)),
        ("/api/v1/flags/{flag_key}", ("GET",)),
        ("/api/v1/flags/{flag_key}", ("PATCH",)),
        ("/api/v1/flags/{flag_key}/retire", ("POST",)),
        ("/api/v1/flags/{flag_key}/history", ("GET",)),
        ("/api/v1/flags/{flag_key}/evaluate", ("POST",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


def test_register_flags_routes_declares_backends_before_flag_key_to_avoid_greedy_match():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: ``/backends`` is registered before the
    ``/{flag_key}`` route so the webworks router matches it
    deterministically. This guards a real wiring bug — without the
    ordering, ``GET /api/v1/flags/backends`` would route to
    ``handle_read_flag`` with ``flag_key="backends"``.**
    """
    app = _FakeApp()
    flags_routes.register_flags_routes(app=app, version_prefix="/api/v1")

    backends_index = None
    flag_key_index = None
    for index, (path, _, _) in enumerate(app.calls):
        if path == "/api/v1/flags/backends" and backends_index is None:
            backends_index = index
        if path == "/api/v1/flags/{flag_key}" and flag_key_index is None:
            flag_key_index = index

    testbase.assert_equal(backends_index is not None, True)
    testbase.assert_equal(flag_key_index is not None, True)
    testbase.assert_equal(backends_index < flag_key_index, True)
    return


# ---------------------------------------------------------------------------
# Misconfigured / 503 path
# ---------------------------------------------------------------------------


def test_handle_list_flags_returns_503_when_session_missing():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: When the request has no db_session attached the
    handler returns a 503 problem document mirroring the flask
    controller's "Request-scoped db_session not configured"
    response.**
    """
    request = _FakeRequest(path="/api/v1/flags", db_session=None)
    response = flags_routes.handle_list_flags(request)
    testbase.assert_equal(response.status_code, 503)
    testbase.assert_equal(
        response.headers["Content-Type"], PROBLEM_JSON_MEDIA_TYPE
    )
    body = _decode_problem_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    testbase.assert_equal(body["status"], 503)
    testbase.assert_equal(body["instance"], "/api/v1/flags")
    return


# ---------------------------------------------------------------------------
# handle_list_flags happy path
# ---------------------------------------------------------------------------


def test_handle_list_flags_returns_200_with_serialized_flags():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: Returns 200 with a JSON list of flag dicts derived
    from flag_service.list_flags(). Verifies the success path of the
    primary collection endpoint.**
    """
    flags_in = [
        _FakeFlag(flag_key="auth.local", flag_kind=FlagKind.BOOLEAN),
        _FakeFlag(flag_key="ui.theme", flag_kind=FlagKind.STRING),
    ]
    list_patch = create_module_patch(flag_service_module, "list_flags")
    mock_list = list_patch.activate()
    mock_list.configure(return_value=flags_in)
    try:
        request = _FakeRequest(path="/api/v1/flags", db_session=object())
        response = flags_routes.handle_list_flags(request)
    finally:
        list_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_json_body(response)
    testbase.assert_equal(len(body), 2)
    testbase.assert_equal(body[0]["flag_key"], "auth.local")
    testbase.assert_equal(body[0]["flag_kind"], "BOOLEAN")
    testbase.assert_equal(body[1]["flag_key"], "ui.theme")
    testbase.assert_equal(body[1]["flag_kind"], "STRING")
    return


# ---------------------------------------------------------------------------
# handle_create_flag — error paths
# ---------------------------------------------------------------------------


def test_handle_create_flag_returns_409_on_duplicate_with_flag_key_extension():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: Duplicate-create raises FlagAlreadyExistsError;
    handler returns 409 problem document carrying the flag_key as an
    extension member so wire consumers can correlate the error
    without re-parsing the detail string.**
    """
    create_patch = create_module_patch(flag_service_module, "create_flag")
    try:
        mock_create = create_patch.activate()
        mock_create.configure(side_effect=_raises(FlagAlreadyExistsError("dupe")))
        request = _FakeRequest(
            path="/api/v1/flags",
            db_session=object(),
            body={
                "flag_key": "auth.local",
                "flag_kind": "BOOLEAN",
                "default_value": False,
            },
        )
        response = flags_routes.handle_create_flag(request)
    finally:
        create_patch.deactivate()

    testbase.assert_equal(response.status_code, 409)
    body = _decode_problem_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_CONFLICT)
    testbase.assert_equal(body["flag_key"], "auth.local")
    testbase.assert_equal(body["instance"], "/api/v1/flags")
    return


def test_handle_create_flag_returns_422_on_unknown_flag_kind():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: An unknown flag_kind value returns 422 (not 400) and
    routes through the documented validation-failed problem type.**
    """
    request = _FakeRequest(
        path="/api/v1/flags",
        db_session=object(),
        body={
            "flag_key": "auth.local",
            "flag_kind": "GARBAGE",
            "default_value": True,
        },
    )
    response = flags_routes.handle_create_flag(request)
    testbase.assert_equal(response.status_code, 422)
    body = _decode_problem_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_handle_create_flag_returns_422_on_service_layer_semantic_error():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: SemanticError raised by the service layer (e.g.,
    invalid rules payload) bubbles to a 422 with the flag_key
    extension attached.**
    """
    create_patch = create_module_patch(flag_service_module, "create_flag")
    try:
        mock_create = create_patch.activate()
        mock_create.configure(side_effect=_raises(SemanticError("bad rules")))
        request = _FakeRequest(
            path="/api/v1/flags",
            db_session=object(),
            body={
                "flag_key": "auth.local",
                "flag_kind": "BOOLEAN",
                "default_value": True,
            },
        )
        response = flags_routes.handle_create_flag(request)
    finally:
        create_patch.deactivate()

    testbase.assert_equal(response.status_code, 422)
    body = _decode_problem_body(response)
    testbase.assert_equal(body["flag_key"], "auth.local")
    return


def test_handle_create_flag_returns_400_when_body_is_not_json():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: An undecodable request body returns 400; never 500.
    The flask controller relied on Flask's force=True parsing which
    raised, becoming a Flask 400 -- the webworks port catches the
    decode failure explicitly.**
    """
    request = _FakeRequest(
        path="/api/v1/flags", db_session=object(), body_raises=True
    )
    response = flags_routes.handle_create_flag(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_problem_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    return


# ---------------------------------------------------------------------------
# handle_create_flag — happy path
# ---------------------------------------------------------------------------


def test_handle_create_flag_returns_201_with_serialized_flag_and_actor_propagation():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: Successful create returns 201 with the serialized
    flag dict, and the actor_user_id from the request propagates to
    the service-layer call so audit trail attribution is preserved.**
    """
    flag = _FakeFlag(flag_key="auth.local", flag_kind=FlagKind.BOOLEAN)
    create_patch = create_module_patch(flag_service_module, "create_flag")
    mock_create = create_patch.activate()
    mock_create.configure(return_value=flag)
    try:
        request = _FakeRequest(
            path="/api/v1/flags",
            db_session=object(),
            actor_user_id="user-42",
            body={
                "flag_key": "auth.local",
                "flag_kind": "BOOLEAN",
                "default_value": True,
            },
        )
        response = flags_routes.handle_create_flag(request)
    finally:
        create_patch.deactivate()

    testbase.assert_equal(response.status_code, 201)
    body = _decode_json_body(response)
    testbase.assert_equal(body["flag_key"], "auth.local")
    mock_create.mock_context().assert_called_once()
    positional_args, keyword_args = mock_create.call_args_list[0]
    testbase.assert_equal(keyword_args["actor_user_id"], "user-42")
    return


# ---------------------------------------------------------------------------
# handle_read_flag, handle_update_flag — error coverage
# ---------------------------------------------------------------------------


def test_handle_update_flag_returns_404_with_flag_key_extension_when_missing():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: A PATCH against an unknown flag_key returns 404 with
    the flag_key carried as an extension member.**
    """
    update_patch = create_module_patch(flag_service_module, "update_flag_rules")
    try:
        mock_update = update_patch.activate()
        mock_update.configure(side_effect=_raises(FlagNotFoundError("missing")))
        request = _FakeRequest(
            path="/api/v1/flags/auth.local",
            path_params={"flag_key": "auth.local"},
            db_session=object(),
            body={"default_value": False},
        )
        response = flags_routes.handle_update_flag(request)
    finally:
        update_patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_problem_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["flag_key"], "auth.local")
    return


# ---------------------------------------------------------------------------
# handle_retire_flag — body coercion
# ---------------------------------------------------------------------------


def test_handle_retire_flag_returns_400_on_non_integer_grace_seconds():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: A non-integer grace_seconds value returns 400 — the
    service layer never sees the bad input.**
    """
    request = _FakeRequest(
        path="/api/v1/flags/auth.local/retire",
        path_params={"flag_key": "auth.local"},
        db_session=object(),
        body={"grace_seconds": "soon"},
    )
    response = flags_routes.handle_retire_flag(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_problem_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    return


def test_handle_retire_flag_uses_default_grace_seconds_when_body_missing():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: An empty / missing body falls through to the
    documented default grace window — same as the flask
    controller.**
    """
    flag = _FakeFlag(flag_key="auth.local", flag_kind=FlagKind.BOOLEAN)
    retire_patch = create_module_patch(flag_service_module, "retire_flag")
    mock_retire = retire_patch.activate()
    mock_retire.configure(return_value=flag)
    try:
        request = _FakeRequest(
            path="/api/v1/flags/auth.local/retire",
            path_params={"flag_key": "auth.local"},
            db_session=object(),
            body=None,
        )
        response = flags_routes.handle_retire_flag(request)
    finally:
        retire_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    positional_args, keyword_args = mock_retire.call_args_list[0]
    testbase.assert_equal(
        keyword_args["grace_seconds"], flag_service_module.DEFAULT_GRACE_SECONDS
    )
    return


# ---------------------------------------------------------------------------
# handle_list_flag_versions — 404 path
# ---------------------------------------------------------------------------


def test_handle_list_flag_versions_returns_404_when_flag_unknown():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: history endpoint returns 404 for unknown flags
    instead of an empty list — matches the flask controller and
    avoids ambiguity for clients that want to distinguish "no
    versions yet" from "no such flag".**
    """
    list_versions_patch = create_module_patch(
        flag_service_module, "list_flag_versions"
    )
    try:
        mock_list = list_versions_patch.activate()
        mock_list.configure(side_effect=_raises(FlagNotFoundError("missing")))
        request = _FakeRequest(
            path="/api/v1/flags/auth.local/history",
            path_params={"flag_key": "auth.local"},
            db_session=object(),
        )
        response = flags_routes.handle_list_flag_versions(request)
    finally:
        list_versions_patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_problem_body(response)
    testbase.assert_equal(body["flag_key"], "auth.local")
    return


def test_handle_list_flag_versions_returns_serialized_versions_on_success():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: history returns 200 with the rendered version list
    derived from flag_service.list_flag_versions().**
    """
    versions = [
        _FakeVersion(flag_key="auth.local", version=1, default_value=False),
        _FakeVersion(flag_key="auth.local", version=2, default_value=True),
    ]
    list_versions_patch = create_module_patch(
        flag_service_module, "list_flag_versions"
    )
    mock_list = list_versions_patch.activate()
    mock_list.configure(return_value=versions)
    try:
        request = _FakeRequest(
            path="/api/v1/flags/auth.local/history",
            path_params={"flag_key": "auth.local"},
            db_session=object(),
        )
        response = flags_routes.handle_list_flag_versions(request)
    finally:
        list_versions_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_json_body(response)
    testbase.assert_equal(len(body), 2)
    testbase.assert_equal(body[0]["version"], 1)
    testbase.assert_equal(body[1]["version"], 2)
    return


# ---------------------------------------------------------------------------
# handle_evaluate_flag — context validation
# ---------------------------------------------------------------------------


def test_handle_evaluate_flag_returns_400_when_bucketing_key_missing():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: An evaluate request without a bucketing_key returns
    400 with the flag_key carried as an extension member.**
    """
    request = _FakeRequest(
        path="/api/v1/flags/auth.local/evaluate",
        path_params={"flag_key": "auth.local"},
        db_session=object(),
        body={},
    )
    response = flags_routes.handle_evaluate_flag(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_problem_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    testbase.assert_equal(body["flag_key"], "auth.local")
    return


def test_handle_evaluate_flag_returns_400_when_attributes_not_object():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: A non-object attributes payload returns 400. The
    flask controller had the same guard.**
    """
    request = _FakeRequest(
        path="/api/v1/flags/auth.local/evaluate",
        path_params={"flag_key": "auth.local"},
        db_session=object(),
        body={"bucketing_key": "u-1", "attributes": ["wrong shape"]},
    )
    response = flags_routes.handle_evaluate_flag(request)
    testbase.assert_equal(response.status_code, 400)
    return


# ---------------------------------------------------------------------------
# handle_list_flag_backends
# ---------------------------------------------------------------------------


def test_handle_list_flag_backends_returns_entries_sorted_by_precedence():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: The backends endpoint sorts entries by ``precedence``
    ascending so callers see the documented "lower-wins" order.**
    """
    snapshot = {
        "remote": {"backend_name": "remote", "precedence": 200},
        "local":  {"backend_name": "local",  "precedence": 100},
    }
    snap_patch = create_module_patch(
        backend_router_module, "diagnostic_snapshot"
    )
    mock_snap = snap_patch.activate()
    mock_snap.configure(return_value=snapshot)
    try:
        request = _FakeRequest(path="/api/v1/flags/backends")
        response = flags_routes.handle_list_flag_backends(request)
    finally:
        snap_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_json_body(response)
    testbase.assert_equal(body[0]["backend_name"], "local")
    testbase.assert_equal(body[1]["backend_name"], "remote")
    return


# ---------------------------------------------------------------------------
# Wiring smoke -- bootstrap registers the routes
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_flags_routes_and_calls_it_in_register_service_extensions():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: app_pychestrate_main wires register_flags_routes
    into register_service_extensions so the routes are queued before
    app.startup. Source-level smoke -- a full app boot is out of
    scope for the singlehost suite.**
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

    has_import = "from ccai.pychestrate.webservice.identity.flags.restapi.v1.flags_routes import" in text
    has_call = "register_flags_routes(app=app, version_prefix=\"/api/v1\")" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return


# ---------------------------------------------------------------------------
# Evaluator success path — happy version-echo
# ---------------------------------------------------------------------------


class _FakeQuery:
    """
        Stand-in for SQLAlchemy's chained .query().filter().first()
        flow. The evaluate handler reads the flag back to echo its
        ``current_version`` -- this stub returns a configured flag.
    """

    def __init__(self, *, flag: Any) -> None:
        self._flag = flag
        return

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        return self

    def first(self) -> Any:
        return self._flag


class _FakeSession:
    """
        Minimal SQLAlchemy session stub returning a fixed flag from
        any .query().filter().first() chain.
    """

    def __init__(self, *, flag: Any) -> None:
        self._flag = flag
        return

    def query(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        rtnval = _FakeQuery(flag=self._flag)
        return rtnval


def test_handle_evaluate_flag_returns_value_and_version_on_success():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: Successful evaluate returns 200 with
    ``{flag_key, value, version}`` -- the same wire shape the flask
    controller emitted.**
    """
    flag = _FakeFlag(
        flag_key="auth.local", flag_kind=FlagKind.BOOLEAN, current_version=3
    )
    session = _FakeSession(flag=flag)
    eval_patch = create_module_patch(flag_evaluator_module, "evaluate_flag")
    mock_eval = eval_patch.activate()
    mock_eval.configure(return_value=True)
    try:
        request = _FakeRequest(
            path="/api/v1/flags/auth.local/evaluate",
            path_params={"flag_key": "auth.local"},
            db_session=session,
            body={"bucketing_key": "user-42"},
        )
        response = flags_routes.handle_evaluate_flag(request)
    finally:
        eval_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_json_body(response)
    testbase.assert_equal(body["flag_key"], "auth.local")
    testbase.assert_equal(body["value"], True)
    testbase.assert_equal(body["version"], 3)
    return


# ---------------------------------------------------------------------------
# Wire-shape: every error path uses application/problem+json
# ---------------------------------------------------------------------------


def test_every_error_response_is_application_problem_json():
    """
    **Feature: 1-feature-flags T2.1 (webworks routes)**
    **Property: 503 / 400 / 404 / 422 all carry the documented
    ``application/problem+json`` content type. Sweeps several
    representative error sites.**
    """
    cases = []

    request_503 = _FakeRequest(path="/api/v1/flags", db_session=None)
    cases.append(flags_routes.handle_list_flags(request_503))

    request_400 = _FakeRequest(
        path="/api/v1/flags/auth.local/evaluate",
        path_params={"flag_key": "auth.local"},
        db_session=object(),
        body={},
    )
    cases.append(flags_routes.handle_evaluate_flag(request_400))

    update_patch = create_module_patch(flag_service_module, "update_flag_rules")
    try:
        mock_update = update_patch.activate()
        mock_update.configure(side_effect=_raises(FlagNotFoundError("missing")))
        request_404 = _FakeRequest(
            path="/api/v1/flags/auth.local",
            path_params={"flag_key": "auth.local"},
            db_session=object(),
            body={"default_value": False},
        )
        cases.append(flags_routes.handle_update_flag(request_404))
    finally:
        update_patch.deactivate()

    request_422 = _FakeRequest(
        path="/api/v1/flags",
        db_session=object(),
        body={
            "flag_key": "x", "flag_kind": "GARBAGE", "default_value": True
        },
    )
    cases.append(flags_routes.handle_create_flag(request_422))

    for response in cases:
        testbase.assert_equal(
            response.headers["Content-Type"], PROBLEM_JSON_MEDIA_TYPE
        )
        is_json_response = isinstance(response, JSONResponse)
        testbase.assert_equal(is_json_response, True)
    return
