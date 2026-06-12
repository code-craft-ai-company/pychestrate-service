"""
.. module:: test_p12d_retention_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native retention REST routes.

.. moduleauthor:: Code Craft AI LLC

The retention port has four routes (create / list / read /
publish) and four documented exception types. Tests cover the
route matrix, the 503 sweep, the per-error extension members,
the create-time selector / action-chain parsing, and the
optional list filters with their enum coercions.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timezone
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
)
from ccai.pychestrate.webservice.retention.exceptions import (
    PolicyAlreadyExistsError,
    PolicyNotFoundError,
    PolicyStateTransitionError,
    UnsupportedRetentionActionError,
)
from ccai.pychestrate.webservice.retention.models import (
    PolicyScopeLevel,
    PolicyState,
)
from ccai.pychestrate.webservice.retention.restapi.v1 import (
    retention_routes,
)


# ---------------------------------------------------------------------------
# Test stubs
# ---------------------------------------------------------------------------


class _FakeQueryParams:
    def __init__(self, *, values: Optional[Dict[str, str]] = None) -> None:
        self._values: Dict[str, str] = values if values is not None else {}
        return

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        rtnval = self._values.get(key, default)
        return rtnval


class _FakeRequest:
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


class _FakePolicy:
    def __init__(
        self,
        *,
        policy_id: str,
        name: str = "policy-x",
        data_class: str = "audit-records",
        scope_level: PolicyScopeLevel = PolicyScopeLevel.SYSTEM,
        project_id: Optional[str] = None,
        state: PolicyState = PolicyState.DRAFT,
        interval_minutes: int = 1440,
        batch_size: int = 500,
        max_attempts: int = 3,
        published_at: Optional[datetime] = None,
    ) -> None:
        self.policy_id: str = policy_id
        self.name: str = name
        self.data_class: str = data_class
        self.scope_level: PolicyScopeLevel = scope_level
        self.project_id: Optional[str] = project_id
        self.state: PolicyState = state
        self.interval_minutes: int = interval_minutes
        self.batch_size: int = batch_size
        self.max_attempts: int = max_attempts
        self.created_at: datetime = datetime(
            2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc
        )
        self.updated_at: datetime = datetime(
            2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc
        )
        self.published_at: Optional[datetime] = published_at
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


def _patch_service_attr(*, name: str, value: Any) -> Any:
    """
        Patch ``retention_routes.retention_service`` so the named
        attribute is the supplied callable / value. Returns the
        Patch so callers can ``deactivate()`` in finally blocks.
    """
    patch = create_module_patch(retention_routes, "retention_service")
    mock_module = patch.activate()
    mock_module.configure(recursive=True)
    mock_module.mock_context().set_attribute(name, value)
    return patch


def _basic_create_body() -> dict:
    rtnval = {
        "name": "p-1",
        "data_class": "audit-records",
        "scope_level": "SYSTEM",
        "selector": {"tag_expression": "team:platform", "age_days": 30},
        "action_chain": [
            {"action_name": "delete", "wait_days_after_previous": 0},
        ],
    }
    return rtnval


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_retention_routes_attaches_four_routes():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: register_retention_routes attaches the same four
    method+path pairs the flask_restx controller exposed.**
    """
    app = _FakeApp()
    retention_routes.register_retention_routes(
        app=app, version_prefix="/api/v1"
    )

    expected_pairs = (
        ("/api/v1/retention/policies", ("GET",)),
        ("/api/v1/retention/policies", ("POST",)),
        ("/api/v1/retention/policies/{policy_id}", ("GET",)),
        ("/api/v1/retention/policies/{policy_id}/publish", ("POST",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# 503 sweep
# ---------------------------------------------------------------------------


def test_handle_create_returns_503_when_session_missing():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: create handler returns 503 problem+json on missing
    session.**
    """
    request = _FakeRequest(
        path="/api/v1/retention/policies",
        body=_basic_create_body(),
        db_session=None,
    )
    response = retention_routes.handle_create_policy(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_handle_list_returns_503_when_session_missing():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: list handler returns 503 problem+json on missing
    session.**
    """
    request = _FakeRequest(
        path="/api/v1/retention/policies", db_session=None
    )
    response = retention_routes.handle_list_policies(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_read_returns_503_when_session_missing():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: read handler returns 503 problem+json.**
    """
    request = _FakeRequest(
        path="/api/v1/retention/policies/p-1",
        path_params={"policy_id": "p-1"},
        db_session=None,
    )
    response = retention_routes.handle_read_policy(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_publish_returns_503_when_session_missing():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: publish handler returns 503 problem+json.**
    """
    request = _FakeRequest(
        path="/api/v1/retention/policies/p-1/publish",
        path_params={"policy_id": "p-1"},
        db_session=None,
    )
    response = retention_routes.handle_publish_policy(request)
    testbase.assert_equal(response.status_code, 503)
    return


# ---------------------------------------------------------------------------
# handle_create_policy
# ---------------------------------------------------------------------------


def test_handle_create_returns_201_with_actor_propagation_and_parsed_selector():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: Successful create returns 201 with the policy
    dict; actor_user_id, parsed selector + action chain, and scope
    enum all propagate to retention_service.create_policy.**
    """
    captured: Dict[str, Any] = {}
    policy = _FakePolicy(policy_id="p-1", name="p-1")

    def fake_create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return policy

    patch = _patch_service_attr(name="create_policy", value=fake_create)
    try:
        request = _FakeRequest(
            path="/api/v1/retention/policies",
            db_session=object(),
            actor_user_id="user-42",
            body=_basic_create_body(),
        )
        response = retention_routes.handle_create_policy(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["policy_id"], "p-1")
    testbase.assert_equal(captured["actor_user_id"], "user-42")
    testbase.assert_equal(captured["scope_level"], PolicyScopeLevel.SYSTEM)
    selector = captured["selector"]
    testbase.assert_equal(selector.tag_expression, "team:platform")
    testbase.assert_equal(selector.age_days, 30)
    chain = captured["action_chain"]
    testbase.assert_equal(len(chain), 1)
    testbase.assert_equal(chain[0].action_name, "delete")
    return


def test_handle_create_uses_documented_defaults():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: Missing interval_minutes / batch_size /
    max_attempts default to the documented values (1440 / 500 /
    3) -- matches the flask controller.**
    """
    captured: Dict[str, Any] = {}
    policy = _FakePolicy(policy_id="p-1")

    def fake_create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return policy

    patch = _patch_service_attr(name="create_policy", value=fake_create)
    try:
        request = _FakeRequest(
            path="/api/v1/retention/policies",
            db_session=object(),
            body=_basic_create_body(),
        )
        retention_routes.handle_create_policy(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(
        captured["interval_minutes"], retention_routes.DEFAULT_INTERVAL_MINUTES
    )
    testbase.assert_equal(
        captured["batch_size"], retention_routes.DEFAULT_BATCH_SIZE
    )
    testbase.assert_equal(
        captured["max_attempts"], retention_routes.DEFAULT_MAX_ATTEMPTS
    )
    return


def test_handle_create_returns_400_on_unknown_scope_level():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: An unrecognized scope_level returns 400 problem
    +json with the raw value as an extension member.**
    """
    body = _basic_create_body()
    body["scope_level"] = "GARBAGE"
    request = _FakeRequest(
        path="/api/v1/retention/policies",
        db_session=object(),
        body=body,
    )
    response = retention_routes.handle_create_policy(request)
    testbase.assert_equal(response.status_code, 400)
    decoded = _decode_body(response)
    testbase.assert_equal(decoded["scope_level"], "GARBAGE")
    return


def test_handle_create_returns_409_on_duplicate_with_name_extension():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: PolicyAlreadyExistsError → 409 problem+json with
    the policy name as an extension member.**
    """
    patch = _patch_service_attr(
        name="create_policy",
        value=_raises(PolicyAlreadyExistsError("dup")),
    )
    try:
        body = _basic_create_body()
        body["name"] = "dup-policy"
        request = _FakeRequest(
            path="/api/v1/retention/policies",
            db_session=object(),
            body=body,
        )
        response = retention_routes.handle_create_policy(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 409)
    decoded = _decode_body(response)
    testbase.assert_equal(decoded["type"], PROBLEM_TYPE_CONFLICT)
    testbase.assert_equal(decoded["name"], "dup-policy")
    return


def test_handle_create_returns_400_on_unsupported_action():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: UnsupportedRetentionActionError → 400 problem+json
    -- distinguishable from a generic SemanticError by its own
    400 path in the flask controller, preserved here.**
    """
    patch = _patch_service_attr(
        name="create_policy",
        value=_raises(UnsupportedRetentionActionError("bad action")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/retention/policies",
            db_session=object(),
            body=_basic_create_body(),
        )
        response = retention_routes.handle_create_policy(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    return


def test_handle_create_returns_400_on_semantic_error():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: SemanticError → 400 problem+json with the policy
    name as an extension member.**
    """
    patch = _patch_service_attr(
        name="create_policy",
        value=_raises(SemanticError("invalid selector")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/retention/policies",
            db_session=object(),
            body=_basic_create_body(),
        )
        response = retention_routes.handle_create_policy(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    return


def test_handle_create_returns_400_on_undecodable_body():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: An undecodable request body returns 400, not 500.**
    """
    request = _FakeRequest(
        path="/api/v1/retention/policies",
        db_session=object(),
        body_raises=True,
    )
    response = retention_routes.handle_create_policy(request)
    testbase.assert_equal(response.status_code, 400)
    return


# ---------------------------------------------------------------------------
# handle_list_policies
# ---------------------------------------------------------------------------


def test_handle_list_returns_serialized_policies_with_no_filters():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: With no filters, list forwards
    scope_level=None / project_id=None / state=None to the
    service.**
    """
    captured: Dict[str, Any] = {}
    policies = [_FakePolicy(policy_id="p-1"), _FakePolicy(policy_id="p-2")]

    def fake_list(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return policies

    patch = _patch_service_attr(name="list_policies", value=fake_list)
    try:
        request = _FakeRequest(
            path="/api/v1/retention/policies", db_session=object()
        )
        response = retention_routes.handle_list_policies(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 2)
    testbase.assert_equal(captured["scope_level"], None)
    testbase.assert_equal(captured["project_id"], None)
    testbase.assert_equal(captured["state"], None)
    return


def test_handle_list_propagates_all_three_query_filters():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: scope_level / project_id / state query params all
    propagate; the enum ones get enum-coerced.**
    """
    captured: Dict[str, Any] = {}

    def fake_list(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return []

    patch = _patch_service_attr(name="list_policies", value=fake_list)
    try:
        request = _FakeRequest(
            path="/api/v1/retention/policies",
            db_session=object(),
            query={
                "scope_level": "PROJECT",
                "project_id": "proj-7",
                "state": "PUBLISHED",
            },
        )
        retention_routes.handle_list_policies(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(captured["scope_level"], PolicyScopeLevel.PROJECT)
    testbase.assert_equal(captured["project_id"], "proj-7")
    testbase.assert_equal(captured["state"], PolicyState.PUBLISHED)
    return


def test_handle_list_returns_400_on_unknown_state_filter():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: A garbage state query value returns 400 problem
    +json with the raw value as an extension member.**
    """
    request = _FakeRequest(
        path="/api/v1/retention/policies",
        db_session=object(),
        query={"state": "GARBAGE"},
    )
    response = retention_routes.handle_list_policies(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["state"], "GARBAGE")
    return


# ---------------------------------------------------------------------------
# handle_read_policy
# ---------------------------------------------------------------------------


def test_handle_read_returns_serialized_policy_on_match():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: A known policy_id returns 200 with the policy
    dict.**
    """
    policy = _FakePolicy(policy_id="p-1", name="weekly-purge")
    patch = _patch_service_attr(
        name="read_policy", value=lambda **kwargs: policy
    )
    try:
        request = _FakeRequest(
            path="/api/v1/retention/policies/p-1",
            path_params={"policy_id": "p-1"},
            db_session=object(),
        )
        response = retention_routes.handle_read_policy(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["policy_id"], "p-1")
    testbase.assert_equal(body["name"], "weekly-purge")
    return


def test_handle_read_returns_404_with_policy_id_extension():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: An unknown policy_id returns 404 problem+json
    with the policy_id as an extension member.**
    """
    patch = _patch_service_attr(
        name="read_policy", value=_raises(PolicyNotFoundError("no")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/retention/policies/p-missing",
            path_params={"policy_id": "p-missing"},
            db_session=object(),
        )
        response = retention_routes.handle_read_policy(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["policy_id"], "p-missing")
    return


# ---------------------------------------------------------------------------
# handle_publish_policy
# ---------------------------------------------------------------------------


def test_handle_publish_returns_200_with_updated_state():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: Successful publish returns 200 with the policy
    dict reflecting the new PUBLISHED state.**
    """
    captured: Dict[str, Any] = {}
    policy = _FakePolicy(policy_id="p-1", state=PolicyState.PUBLISHED)

    def fake_publish(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return policy

    patch = _patch_service_attr(name="publish_policy", value=fake_publish)
    try:
        request = _FakeRequest(
            path="/api/v1/retention/policies/p-1/publish",
            path_params={"policy_id": "p-1"},
            db_session=object(),
            actor_user_id="user-42",
        )
        response = retention_routes.handle_publish_policy(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["state"], "PUBLISHED")
    testbase.assert_equal(captured["actor_user_id"], "user-42")
    return


def test_handle_publish_returns_404_with_policy_id_extension():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: PolicyNotFoundError → 404 problem+json with the
    policy_id as an extension member.**
    """
    patch = _patch_service_attr(
        name="publish_policy", value=_raises(PolicyNotFoundError("no")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/retention/policies/p-missing/publish",
            path_params={"policy_id": "p-missing"},
            db_session=object(),
        )
        response = retention_routes.handle_publish_policy(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["policy_id"], "p-missing")
    return


def test_handle_publish_returns_409_on_state_transition_error():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: PolicyStateTransitionError → 409 problem+json with
    the policy_id as an extension member.**
    """
    patch = _patch_service_attr(
        name="publish_policy",
        value=_raises(PolicyStateTransitionError("already published")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/retention/policies/p-1/publish",
            path_params={"policy_id": "p-1"},
            db_session=object(),
        )
        response = retention_routes.handle_publish_policy(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_CONFLICT)
    testbase.assert_equal(body["policy_id"], "p-1")
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_retention_routes_and_calls_it():
    """
    **Feature: 2-retention-policies T1.1 (webworks routes)**
    **Property: app_pychestrate_main.py wires
    register_retention_routes into register_service_extensions.**
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
        "from ccai.pychestrate.webservice.retention.restapi.v1.retention_routes import"
        in text
    )
    has_call = "register_retention_routes(app=app, version_prefix=\"/api/v1\")" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return
