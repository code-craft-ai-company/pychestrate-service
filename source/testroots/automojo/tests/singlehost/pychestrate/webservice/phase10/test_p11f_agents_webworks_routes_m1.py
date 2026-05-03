"""
.. module:: test_p11f_agents_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native agents REST routes.

.. moduleauthor:: Automation Mojo LLC

The agents port spans both ``/clients`` and ``/agent-rollouts``
URL prefixes (the namespace was a logical grouping, not a path
prefix) and exercises Google AIP-style colon action verbs
(``:inventory``, ``:start``). Tests cover the route matrix, the
503 misconfig path on every handler that uses the session,
happy-path serialization for each handler, and the documented
4xx error paths (400 / 404 / 409).
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

from automojo.pychestrate.webservice.agents.exceptions import (
    RolloutNotFoundError,
    RolloutStateTransitionError,
)
from automojo.pychestrate.webservice.agents.restapi.v1 import agents_routes
from automojo.pychestrate.webservice.api.problem_json import (
    PROBLEM_JSON_MEDIA_TYPE,
    PROBLEM_TYPE_BAD_REQUEST,
    PROBLEM_TYPE_CONFLICT,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
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


class _FakeCapabilityRow:
    def __init__(
        self,
        *,
        kind: str,
        value: Any = None,
        revision_token: str = "rev-1",
    ) -> None:
        self.kind: str = kind
        self.value_json: Any = (
            {"value": value} if value is not None else None
        )
        self.revision_token: str = revision_token
        self.updated_at: datetime = datetime(
            2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc
        )
        return


class _FakeInventoryRow:
    def __init__(
        self,
        *,
        client_id: str,
        project_id: str = "proj-1",
        pod_name: str = "pod-x",
        liveness_state: str = "ALIVE",
        agent_version: str = "1.0.0",
        last_seen: str = "2026-05-03T12:00:00+00:00",
        capability_kinds: Optional[List[str]] = None,
    ) -> None:
        self.client_id: str = client_id
        self.project_id: str = project_id
        self.pod_name: str = pod_name
        self.liveness_state: str = liveness_state
        self.agent_version: str = agent_version
        self.last_seen: str = last_seen
        self.capability_kinds: List[str] = (
            capability_kinds if capability_kinds is not None else []
        )
        return


class _FakeInventoryPage:
    def __init__(
        self,
        *,
        rows: List[_FakeInventoryRow],
        total: int,
        offset: int = 0,
        limit: int = 100,
    ) -> None:
        self.rows: List[_FakeInventoryRow] = rows
        self.total: int = total
        self.offset: int = offset
        self.limit: int = limit
        return


class _FakeRolloutState:
    def __init__(self, *, value: str) -> None:
        self.value: str = value
        return


class _FakeRollout:
    def __init__(
        self,
        *,
        rollout_id: str,
        version: str,
        state: str,
    ) -> None:
        self.rollout_id: str = rollout_id
        self.version: str = version
        self.state: _FakeRolloutState = _FakeRolloutState(value=state)
        return


class _FakeOffer:
    def __init__(self, *, offer_id: str, client_id: str) -> None:
        self.offer_id: str = offer_id
        self.client_id: str = client_id
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


def test_register_agents_routes_attaches_four_routes_across_two_prefixes():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: register_agents_routes attaches the four
    method+path pairs the flask_restx controller exposed, spanning
    both ``/clients`` and ``/agent-rollouts`` URL prefixes.**
    """
    app = _FakeApp()
    agents_routes.register_agents_routes(
        app=app, version_prefix="/api/v1"
    )
    expected_pairs = (
        ("/api/v1/clients:inventory", ("GET",)),
        ("/api/v1/clients/{client_id}/capabilities", ("GET",)),
        ("/api/v1/agent-rollouts", ("POST",)),
        ("/api/v1/agent-rollouts/{rollout_id}:start", ("POST",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# 503 misconfig sweep
# ---------------------------------------------------------------------------


def test_handle_list_capabilities_returns_503_when_session_missing():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: capabilities handler returns the 503 problem
    document on misconfigured deployments.**
    """
    request = _FakeRequest(
        path="/api/v1/clients/c-1/capabilities",
        path_params={"client_id": "c-1"},
        db_session=None,
    )
    response = agents_routes.handle_list_client_capabilities(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_handle_inventory_returns_503_when_session_missing():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: inventory handler returns 503 on missing session.**
    """
    request = _FakeRequest(
        path="/api/v1/clients:inventory", db_session=None
    )
    response = agents_routes.handle_list_client_inventory(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_draft_rollout_returns_503_when_session_missing():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: rollout-draft handler returns 503 on missing
    session.**
    """
    request = _FakeRequest(
        path="/api/v1/agent-rollouts",
        body={"version": "1.0", "artifact_source": "ghcr",
              "artifact_ref": "ghcr.io/x:1"},
        db_session=None,
    )
    response = agents_routes.handle_draft_agent_rollout(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_start_rollout_returns_503_when_session_missing():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: rollout-start handler returns 503 on missing
    session.**
    """
    request = _FakeRequest(
        path="/api/v1/agent-rollouts/r-1:start",
        path_params={"rollout_id": "r-1"},
        body={"candidate_client_ids": []},
        db_session=None,
    )
    response = agents_routes.handle_start_agent_rollout(request)
    testbase.assert_equal(response.status_code, 503)
    return


# ---------------------------------------------------------------------------
# handle_list_client_capabilities
# ---------------------------------------------------------------------------


def test_handle_list_capabilities_returns_serialized_rows():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: capabilities returns 200 with rows serialized to
    {kind, value, revision_token, updated_at}. Sensitive values
    are excluded by the include_sensitive=False arg propagated to
    the service.**
    """
    rows = [
        _FakeCapabilityRow(
            kind="toolchain", value="python-3.12", revision_token="rev-1"
        ),
        _FakeCapabilityRow(
            kind="concurrency", value=4, revision_token="rev-2"
        ),
    ]
    list_patch = create_module_patch(
        agents_routes, "list_capabilities_for_client"
    )
    try:
        mock_list = list_patch.activate()
        mock_list.configure(return_value=rows)
        request = _FakeRequest(
            path="/api/v1/clients/c-1/capabilities",
            path_params={"client_id": "c-1"},
            db_session=object(),
        )
        response = agents_routes.handle_list_client_capabilities(request)
    finally:
        list_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 2)
    testbase.assert_equal(body[0]["kind"], "toolchain")
    testbase.assert_equal(body[0]["value"], "python-3.12")
    positional_args, keyword_args = mock_list.call_args_list[0]
    testbase.assert_equal(keyword_args["client_id"], "c-1")
    testbase.assert_equal(keyword_args["include_sensitive"], False)
    return


def test_handle_list_capabilities_emits_null_value_when_value_json_missing():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: A row whose value_json is non-dict (or None)
    serializes ``value`` as null rather than crashing.**
    """
    row = _FakeCapabilityRow(kind="opaque")
    row.value_json = None  # non-dict path
    list_patch = create_module_patch(
        agents_routes, "list_capabilities_for_client"
    )
    try:
        mock_list = list_patch.activate()
        mock_list.configure(return_value=[row])
        request = _FakeRequest(
            path="/api/v1/clients/c-1/capabilities",
            path_params={"client_id": "c-1"},
            db_session=object(),
        )
        response = agents_routes.handle_list_client_capabilities(request)
    finally:
        list_patch.deactivate()

    body = _decode_body(response)
    testbase.assert_equal(body[0]["value"], None)
    return


# ---------------------------------------------------------------------------
# handle_list_client_inventory
# ---------------------------------------------------------------------------


def test_handle_inventory_returns_paged_response_with_filters_propagated():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: inventory propagates project_id / liveness / offset
    / limit query params through to ``read_inventory`` and returns
    the paginated dict shape with total / offset / limit / rows.**
    """
    inv_row = _FakeInventoryRow(
        client_id="c-1",
        project_id="proj-2",
        capability_kinds=["toolchain", "concurrency"],
    )
    page = _FakeInventoryPage(rows=[inv_row], total=1, offset=10, limit=20)
    inv_patch = create_module_patch(
        agents_routes, "read_inventory"
    )
    try:
        mock_inv = inv_patch.activate()
        mock_inv.configure(return_value=page)
        request = _FakeRequest(
            path="/api/v1/clients:inventory",
            db_session=object(),
            query={
                "project_id": "proj-2",
                "liveness": "ALIVE",
                "offset": "10",
                "limit": "20",
            },
        )
        response = agents_routes.handle_list_client_inventory(request)
    finally:
        inv_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["total"], 1)
    testbase.assert_equal(body["offset"], 10)
    testbase.assert_equal(body["limit"], 20)
    testbase.assert_equal(len(body["rows"]), 1)
    testbase.assert_equal(body["rows"][0]["client_id"], "c-1")
    testbase.assert_equal(
        body["rows"][0]["capability_kinds"],
        ["toolchain", "concurrency"],
    )
    positional_args, keyword_args = mock_inv.call_args_list[0]
    testbase.assert_equal(keyword_args["project_id"], "proj-2")
    testbase.assert_equal(keyword_args["liveness_state"], "ALIVE")
    testbase.assert_equal(keyword_args["offset"], 10)
    testbase.assert_equal(keyword_args["limit"], 20)
    return


def test_handle_inventory_uses_documented_defaults_when_no_filters():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: With no query params, offset defaults to 0 and
    limit defaults to 100 (matches the flask controller).**
    """
    page = _FakeInventoryPage(rows=[], total=0)
    inv_patch = create_module_patch(
        agents_routes, "read_inventory"
    )
    try:
        mock_inv = inv_patch.activate()
        mock_inv.configure(return_value=page)
        request = _FakeRequest(
            path="/api/v1/clients:inventory", db_session=object()
        )
        agents_routes.handle_list_client_inventory(request)
    finally:
        inv_patch.deactivate()

    positional_args, keyword_args = mock_inv.call_args_list[0]
    testbase.assert_equal(
        keyword_args["offset"], agents_routes.DEFAULT_INVENTORY_OFFSET
    )
    testbase.assert_equal(
        keyword_args["limit"], agents_routes.DEFAULT_INVENTORY_LIMIT
    )
    return


def test_handle_inventory_returns_400_on_non_integer_offset():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: A non-integer offset returns 400 problem+json with
    the bad value as an extension member. The flask controller
    raised at ``int(...)`` and 500ed; the webworks port catches
    the coercion failure.**
    """
    request = _FakeRequest(
        path="/api/v1/clients:inventory",
        db_session=object(),
        query={"offset": "abc"},
    )
    response = agents_routes.handle_list_client_inventory(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    testbase.assert_equal(body["offset"], "abc")
    return


def test_handle_inventory_returns_400_on_non_integer_limit():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: A non-integer limit returns 400 problem+json.**
    """
    request = _FakeRequest(
        path="/api/v1/clients:inventory",
        db_session=object(),
        query={"limit": "lots"},
    )
    response = agents_routes.handle_list_client_inventory(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["limit"], "lots")
    return


# ---------------------------------------------------------------------------
# handle_draft_agent_rollout
# ---------------------------------------------------------------------------


def test_handle_draft_rollout_returns_201_with_actor_propagation():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: A successful draft returns 201 with
    {rollout_id, version, state} and the actor_user_id is forwarded
    to ``draft_rollout`` for audit attribution.**
    """
    rollout = _FakeRollout(
        rollout_id="r-1", version="1.0.0", state="DRAFT"
    )
    draft_patch = create_module_patch(
        agents_routes, "draft_rollout"
    )
    try:
        mock_draft = draft_patch.activate()
        mock_draft.configure(return_value=rollout)
        request = _FakeRequest(
            path="/api/v1/agent-rollouts",
            db_session=object(),
            actor_user_id="user-42",
            body={
                "version": "1.0.0",
                "artifact_source": "ghcr",
                "artifact_ref": "ghcr.io/automojo/agent:1.0.0",
            },
        )
        response = agents_routes.handle_draft_agent_rollout(request)
    finally:
        draft_patch.deactivate()

    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["rollout_id"], "r-1")
    testbase.assert_equal(body["version"], "1.0.0")
    testbase.assert_equal(body["state"], "DRAFT")
    positional_args, keyword_args = mock_draft.call_args_list[0]
    testbase.assert_equal(keyword_args["actor_user_id"], "user-42")
    return


def test_handle_draft_rollout_returns_400_on_semantic_error():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: A SemanticError from draft_rollout (e.g., bad
    artifact_ref shape) returns 400 problem+json.**
    """
    draft_patch = create_module_patch(
        agents_routes, "draft_rollout"
    )
    try:
        mock_draft = draft_patch.activate()
        mock_draft.configure(
            side_effect=_raises(SemanticError("invalid artifact"))
        )
        request = _FakeRequest(
            path="/api/v1/agent-rollouts",
            db_session=object(),
            body={
                "version": "x", "artifact_source": "ghcr",
                "artifact_ref": "bad",
            },
        )
        response = agents_routes.handle_draft_agent_rollout(request)
    finally:
        draft_patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    return


def test_handle_draft_rollout_returns_400_on_non_dict_body():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: A non-dict request body returns 400 problem+json,
    not 500.**
    """
    request = _FakeRequest(
        path="/api/v1/agent-rollouts",
        db_session=object(),
        body_raises=True,
    )
    response = agents_routes.handle_draft_agent_rollout(request)
    testbase.assert_equal(response.status_code, 400)
    return


# ---------------------------------------------------------------------------
# handle_start_agent_rollout
# ---------------------------------------------------------------------------


def test_handle_start_rollout_returns_202_with_offer_manifest():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: A successful start returns 202 with
    ``{rollout_id, offer_count, offers}``. The status code 202 (not
    201/200) matches the flask controller -- ``start`` is async.**
    """
    offers = [
        _FakeOffer(offer_id="o-1", client_id="c-a"),
        _FakeOffer(offer_id="o-2", client_id="c-b"),
    ]
    start_patch = create_module_patch(
        agents_routes, "start_rollout"
    )
    try:
        mock_start = start_patch.activate()
        mock_start.configure(return_value=offers)
        request = _FakeRequest(
            path="/api/v1/agent-rollouts/r-1:start",
            path_params={"rollout_id": "r-1"},
            db_session=object(),
            body={"candidate_client_ids": ["c-a", "c-b"], "target_size": 5},
        )
        response = agents_routes.handle_start_agent_rollout(request)
    finally:
        start_patch.deactivate()

    testbase.assert_equal(response.status_code, 202)
    body = _decode_body(response)
    testbase.assert_equal(body["rollout_id"], "r-1")
    testbase.assert_equal(body["offer_count"], 2)
    testbase.assert_equal(body["offers"][0]["offer_id"], "o-1")
    testbase.assert_equal(body["offers"][1]["client_id"], "c-b")
    positional_args, keyword_args = mock_start.call_args_list[0]
    testbase.assert_equal(keyword_args["target_size"], 5)
    return


def test_handle_start_rollout_returns_404_with_rollout_id_extension():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: An unknown rollout_id returns 404 problem+json with
    the rollout_id as an extension member.**
    """
    start_patch = create_module_patch(
        agents_routes, "start_rollout"
    )
    try:
        mock_start = start_patch.activate()
        mock_start.configure(
            side_effect=_raises(RolloutNotFoundError("missing"))
        )
        request = _FakeRequest(
            path="/api/v1/agent-rollouts/r-missing:start",
            path_params={"rollout_id": "r-missing"},
            db_session=object(),
            body={"candidate_client_ids": []},
        )
        response = agents_routes.handle_start_agent_rollout(request)
    finally:
        start_patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["rollout_id"], "r-missing")
    return


def test_handle_start_rollout_returns_409_on_state_transition_error():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: A RolloutStateTransitionError (e.g., already
    started, or terminated) returns 409 problem+json with the
    rollout_id as an extension member.**
    """
    start_patch = create_module_patch(
        agents_routes, "start_rollout"
    )
    try:
        mock_start = start_patch.activate()
        mock_start.configure(
            side_effect=_raises(
                RolloutStateTransitionError("already running")
            )
        )
        request = _FakeRequest(
            path="/api/v1/agent-rollouts/r-1:start",
            path_params={"rollout_id": "r-1"},
            db_session=object(),
            body={"candidate_client_ids": []},
        )
        response = agents_routes.handle_start_agent_rollout(request)
    finally:
        start_patch.deactivate()

    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_CONFLICT)
    testbase.assert_equal(body["rollout_id"], "r-1")
    return


def test_handle_start_rollout_returns_400_on_non_integer_target_size():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: A non-integer target_size returns 400 problem+json
    rather than 500. The flask controller raised at ``int(...)``.**
    """
    request = _FakeRequest(
        path="/api/v1/agent-rollouts/r-1:start",
        path_params={"rollout_id": "r-1"},
        db_session=object(),
        body={"candidate_client_ids": [], "target_size": "many"},
    )
    response = agents_routes.handle_start_agent_rollout(request)
    testbase.assert_equal(response.status_code, 400)
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_agents_routes_and_calls_it():
    """
    **Feature: 3-agents T1.1 (webworks routes)**
    **Property: app_pychestrate_main.py wires register_agents_routes
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
        "from automojo.pychestrate.webservice.agents.restapi.v1.agents_routes import"
        in text
    )
    has_call = "register_agents_routes(app=app, version_prefix=\"/api/v1\")" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return
