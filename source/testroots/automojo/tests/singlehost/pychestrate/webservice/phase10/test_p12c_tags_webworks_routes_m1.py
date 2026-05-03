"""
.. module:: test_p12c_tags_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native tags REST routes.

.. moduleauthor:: Automation Mojo LLC

The tags port has the most exception-paths of any port so far —
SemanticError + TaxonomyNotFoundError + TagValueValidationError
+ TagAssignmentNotFoundError on the assign / remove handlers,
plus search and taxonomies endpoints. Tests cover the route
matrix (5 routes, two with the ``:path`` converter for tags),
the 503 sweep, the per-error extension members, and the
bootstrap source-smoke.
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
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
)
from automojo.pychestrate.webservice.tagging.exceptions import (
    TagAssignmentNotFoundError,
    TagValueValidationError,
    TaxonomyNotFoundError,
)
from automojo.pychestrate.webservice.tagging.restapi.v1 import tags_routes


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


class _FakeAssignment:
    def __init__(
        self,
        *,
        assignment_id: str,
        entity_kind: str = "project",
        entity_id: str = "p-1",
        taxonomy_name: str = "team",
        canonical_value: str = "platform",
    ) -> None:
        self.assignment_id: str = assignment_id
        self.entity_kind: str = entity_kind
        self.entity_id: str = entity_id
        self.taxonomy_name: str = taxonomy_name
        self.canonical_value: str = canonical_value
        self.assigned_at: datetime = datetime(
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


def test_register_tags_routes_attaches_five_routes_with_path_converter():
    """
    **Feature: 2-tagging T1.1 (webworks routes)**
    **Property: register_tags_routes attaches the same five
    method+path pairs the flask_restx controller exposed, with the
    ``:path`` converter on the DELETE tag-removal route so
    multi-segment ``taxonomy:value`` tags route correctly.**
    """
    app = _FakeApp()
    tags_routes.register_tags_routes(app=app, version_prefix="/api/v1")

    expected_pairs = (
        ("/api/v1/tags/search", ("GET",)),
        ("/api/v1/tags/taxonomies", ("GET",)),
        ("/api/v1/tags/{entity_kind}/{entity_id}", ("POST",)),
        ("/api/v1/tags/{entity_kind}/{entity_id}", ("GET",)),
        ("/api/v1/tags/{entity_kind}/{entity_id}/{tag:path}", ("DELETE",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


def test_register_tags_routes_declares_fixed_paths_before_parameterized():
    """
    **Feature: 2-tagging T1.1 (webworks routes)**
    **Property: ``/search`` and ``/taxonomies`` register before the
    parameterized routes for self-documenting registration order.**
    """
    app = _FakeApp()
    tags_routes.register_tags_routes(app=app, version_prefix="/api/v1")

    search_index = None
    taxonomies_index = None
    parameterized_index = None
    for index, (path, _, _) in enumerate(app.calls):
        if path == "/api/v1/tags/search" and search_index is None:
            search_index = index
        if path == "/api/v1/tags/taxonomies" and taxonomies_index is None:
            taxonomies_index = index
        if path == "/api/v1/tags/{entity_kind}/{entity_id}" and parameterized_index is None:
            parameterized_index = index

    testbase.assert_equal(search_index < parameterized_index, True)
    testbase.assert_equal(taxonomies_index < parameterized_index, True)
    return


# ---------------------------------------------------------------------------
# 503 sweep
# ---------------------------------------------------------------------------


def test_handle_assign_returns_503_when_session_missing():
    """
    **Feature: 2-tagging T1.1 (webworks routes)**
    **Property: assign handler returns 503 problem+json on missing
    session.**
    """
    request = _FakeRequest(
        path="/api/v1/tags/project/p-1",
        path_params={"entity_kind": "project", "entity_id": "p-1"},
        body={"tag": "team:platform"},
        db_session=None,
    )
    response = tags_routes.handle_assign_tag(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_handle_list_returns_503_when_session_missing():
    """
    **Feature: 2-tagging T1.1 (webworks routes)**
    **Property: list handler returns 503 problem+json on missing
    session.**
    """
    request = _FakeRequest(
        path="/api/v1/tags/project/p-1",
        path_params={"entity_kind": "project", "entity_id": "p-1"},
        db_session=None,
    )
    response = tags_routes.handle_list_tags(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_remove_returns_503_when_session_missing():
    """
    **Feature: 2-tagging T1.1 (webworks routes)**
    **Property: remove handler returns 503 problem+json on missing
    session.**
    """
    request = _FakeRequest(
        path="/api/v1/tags/project/p-1/team:platform",
        path_params={"entity_kind": "project", "entity_id": "p-1", "tag": "team:platform"},
        db_session=None,
    )
    response = tags_routes.handle_remove_tag(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_search_returns_503_when_session_missing():
    """
    **Feature: 2-tagging T1.1 (webworks routes)**
    **Property: search handler returns 503 problem+json on missing
    session.**
    """
    request = _FakeRequest(
        path="/api/v1/tags/search",
        query={"kind": "project", "expr": "team:platform"},
        db_session=None,
    )
    response = tags_routes.handle_search_tags(request)
    testbase.assert_equal(response.status_code, 503)
    return


# ---------------------------------------------------------------------------
# handle_assign_tag
# ---------------------------------------------------------------------------


def test_handle_assign_returns_201_with_actor_propagation():
    """
    **Feature: 2-tagging T1.1 (webworks routes)**
    **Property: Successful assign returns 201 with the assignment
    dict and forwards actor_user_id to tag_service.assign_tag.**
    """
    assignment = _FakeAssignment(assignment_id="a-1")
    assign_patch = create_module_patch(tags_routes, "tag_service")
    try:
        mock_module = assign_patch.activate()
        mock_module.configure(recursive=True)
        captured: Dict[str, Any] = {}

        def fake_assign(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return assignment

        mock_module.mock_context().set_attribute("assign_tag", fake_assign)
        request = _FakeRequest(
            path="/api/v1/tags/project/p-1",
            path_params={"entity_kind": "project", "entity_id": "p-1"},
            db_session=object(),
            actor_user_id="user-42",
            body={"tag": "team:platform"},
        )
        response = tags_routes.handle_assign_tag(request)
    finally:
        assign_patch.deactivate()

    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["assignment_id"], "a-1")
    testbase.assert_equal(captured["actor_user_id"], "user-42")
    testbase.assert_equal(captured["raw_tag"], "team:platform")
    return


def test_handle_assign_returns_404_on_taxonomy_not_found_with_extensions():
    """
    **Feature: 2-tagging T1.1 (webworks routes)**
    **Property: TaxonomyNotFoundError → 404 problem+json with
    entity_kind, entity_id, and raw_tag carried as extension
    members.**
    """
    assign_patch = create_module_patch(tags_routes, "tag_service")
    try:
        mock_module = assign_patch.activate()
        mock_module.configure(recursive=True)
        mock_module.mock_context().set_attribute(
            "assign_tag",
            _raises(TaxonomyNotFoundError("no such taxonomy")),
        )
        request = _FakeRequest(
            path="/api/v1/tags/project/p-1",
            path_params={"entity_kind": "project", "entity_id": "p-1"},
            db_session=object(),
            body={"tag": "unknown:value"},
        )
        response = tags_routes.handle_assign_tag(request)
    finally:
        assign_patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["entity_kind"], "project")
    testbase.assert_equal(body["entity_id"], "p-1")
    testbase.assert_equal(body["raw_tag"], "unknown:value")
    return


def test_handle_assign_returns_400_on_value_validation_error():
    """
    **Feature: 2-tagging T1.1 (webworks routes)**
    **Property: TagValueValidationError → 400 problem+json with
    raw_tag extension.**
    """
    assign_patch = create_module_patch(tags_routes, "tag_service")
    try:
        mock_module = assign_patch.activate()
        mock_module.configure(recursive=True)
        mock_module.mock_context().set_attribute(
            "assign_tag",
            _raises(TagValueValidationError("invalid value")),
        )
        request = _FakeRequest(
            path="/api/v1/tags/project/p-1",
            path_params={"entity_kind": "project", "entity_id": "p-1"},
            db_session=object(),
            body={"tag": "team:!!!"},
        )
        response = tags_routes.handle_assign_tag(request)
    finally:
        assign_patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    testbase.assert_equal(body["raw_tag"], "team:!!!")
    return


def test_handle_assign_returns_400_on_semantic_error():
    """
    **Feature: 2-tagging T1.1 (webworks routes)**
    **Property: SemanticError from the service → 400 problem+json
    with the entity context as extension members.**
    """
    assign_patch = create_module_patch(tags_routes, "tag_service")
    try:
        mock_module = assign_patch.activate()
        mock_module.configure(recursive=True)
        mock_module.mock_context().set_attribute(
            "assign_tag", _raises(SemanticError("bad input")),
        )
        request = _FakeRequest(
            path="/api/v1/tags/project/p-1",
            path_params={"entity_kind": "project", "entity_id": "p-1"},
            db_session=object(),
            body={"tag": "x"},
        )
        response = tags_routes.handle_assign_tag(request)
    finally:
        assign_patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    return


# ---------------------------------------------------------------------------
# handle_list_tags
# ---------------------------------------------------------------------------


def test_handle_list_returns_serialized_assignments():
    """
    **Feature: 2-tagging T1.1 (webworks routes)**
    **Property: list returns 200 with assignments serialized.**
    """
    rows = [
        _FakeAssignment(assignment_id="a-1", taxonomy_name="team"),
        _FakeAssignment(assignment_id="a-2", taxonomy_name="env"),
    ]
    list_patch = create_module_patch(tags_routes, "tag_service")
    try:
        mock_module = list_patch.activate()
        mock_module.configure(recursive=True)
        mock_module.mock_context().set_attribute(
            "list_tags", lambda **kwargs: rows
        )
        request = _FakeRequest(
            path="/api/v1/tags/project/p-1",
            path_params={"entity_kind": "project", "entity_id": "p-1"},
            db_session=object(),
        )
        response = tags_routes.handle_list_tags(request)
    finally:
        list_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 2)
    testbase.assert_equal(body[0]["assignment_id"], "a-1")
    return


# ---------------------------------------------------------------------------
# handle_remove_tag
# ---------------------------------------------------------------------------


def test_handle_remove_returns_204_on_success():
    """
    **Feature: 2-tagging T1.1 (webworks routes)**
    **Property: Successful remove returns 204 with empty body.**
    """
    remove_patch = create_module_patch(tags_routes, "tag_service")
    try:
        mock_module = remove_patch.activate()
        mock_module.configure(recursive=True)
        mock_module.mock_context().set_attribute(
            "remove_tag", lambda **kwargs: None
        )
        request = _FakeRequest(
            path="/api/v1/tags/project/p-1/team:platform",
            path_params={"entity_kind": "project", "entity_id": "p-1", "tag": "team:platform"},
            db_session=object(),
        )
        response = tags_routes.handle_remove_tag(request)
    finally:
        remove_patch.deactivate()

    testbase.assert_equal(response.status_code, 204)
    testbase.assert_equal(response.body, b"")
    return


def test_handle_remove_returns_404_with_raw_tag_extension_on_assignment_not_found():
    """
    **Feature: 2-tagging T1.1 (webworks routes)**
    **Property: TagAssignmentNotFoundError → 404 problem+json with
    the raw_tag carried as an extension member.**
    """
    remove_patch = create_module_patch(tags_routes, "tag_service")
    try:
        mock_module = remove_patch.activate()
        mock_module.configure(recursive=True)
        mock_module.mock_context().set_attribute(
            "remove_tag", _raises(TagAssignmentNotFoundError("not assigned"))
        )
        request = _FakeRequest(
            path="/api/v1/tags/project/p-1/team:platform",
            path_params={"entity_kind": "project", "entity_id": "p-1", "tag": "team:platform"},
            db_session=object(),
        )
        response = tags_routes.handle_remove_tag(request)
    finally:
        remove_patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["raw_tag"], "team:platform")
    return


# ---------------------------------------------------------------------------
# handle_search_tags
# ---------------------------------------------------------------------------


def test_handle_search_returns_entity_ids_with_kind_echoed():
    """
    **Feature: 2-tagging T1.1 (webworks routes)**
    **Property: search returns 200 with
    ``{entity_kind, entity_ids}``. The kind echoes the query
    parameter; entity_ids comes from tag_service.search_entities.**
    """
    search_patch = create_module_patch(tags_routes, "tag_service")
    try:
        mock_module = search_patch.activate()
        mock_module.configure(recursive=True)
        mock_module.mock_context().set_attribute(
            "search_entities", lambda **kwargs: ["p-1", "p-2"]
        )
        request = _FakeRequest(
            path="/api/v1/tags/search",
            db_session=object(),
            query={"kind": "project", "expr": "team:platform"},
        )
        response = tags_routes.handle_search_tags(request)
    finally:
        search_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["entity_kind"], "project")
    testbase.assert_equal(body["entity_ids"], ["p-1", "p-2"])
    return


def test_handle_search_returns_400_on_semantic_error():
    """
    **Feature: 2-tagging T1.1 (webworks routes)**
    **Property: SemanticError from search → 400 problem+json with
    entity_kind and expression as extension members.**
    """
    search_patch = create_module_patch(tags_routes, "tag_service")
    try:
        mock_module = search_patch.activate()
        mock_module.configure(recursive=True)
        mock_module.mock_context().set_attribute(
            "search_entities", _raises(SemanticError("bad expression")),
        )
        request = _FakeRequest(
            path="/api/v1/tags/search",
            db_session=object(),
            query={"kind": "project", "expr": "@@@"},
        )
        response = tags_routes.handle_search_tags(request)
    finally:
        search_patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["entity_kind"], "project")
    testbase.assert_equal(body["expression"], "@@@")
    return


# ---------------------------------------------------------------------------
# handle_list_taxonomies
# ---------------------------------------------------------------------------


class _FakeTaxPack:
    def __init__(
        self,
        *,
        allowed_values: Optional[Any] = None,
        case_sensitive_value: bool = False,
        color_hex: str = "#888888",
        description: str = "",
    ) -> None:
        self.allowed_values = allowed_values
        self.case_sensitive_value = case_sensitive_value
        self.color_hex = color_hex
        self.description = description
        return


def test_handle_list_taxonomies_returns_descriptors_sorted_by_name():
    """
    **Feature: 2-tagging T1.1 (webworks routes)**
    **Property: taxonomies endpoint returns descriptors sorted by
    name. Allowed values list is itself sorted; color_hex / case
    flags / description are included.**
    """
    registry = {
        "team": _FakeTaxPack(
            allowed_values=["platform", "data"],
            case_sensitive_value=False,
            color_hex="#aabbcc",
            description="team",
        ),
        "env": _FakeTaxPack(
            allowed_values=None,
            case_sensitive_value=True,
            color_hex="#112233",
            description="env",
        ),
    }
    registry_patch = create_module_patch(
        __import__(
            "automojo.pychestrate.webservice.tagging.registry",
            fromlist=["load_registered_taxonomies"],
        ),
        "load_registered_taxonomies",
    )
    try:
        mock_load = registry_patch.activate()
        mock_load.configure(return_value=registry)
        request = _FakeRequest(path="/api/v1/tags/taxonomies")
        response = tags_routes.handle_list_taxonomies(request)
    finally:
        registry_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 2)
    testbase.assert_equal(body[0]["taxonomy_name"], "env")
    testbase.assert_equal(body[1]["taxonomy_name"], "team")
    testbase.assert_equal(body[1]["allowed_values"], ["data", "platform"])
    testbase.assert_equal(body[0]["allowed_values"], None)
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_tags_routes_and_calls_it():
    """
    **Feature: 2-tagging T1.1 (webworks routes)**
    **Property: app_pychestrate_main.py wires register_tags_routes
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
        "from automojo.pychestrate.webservice.tagging.restapi.v1.tags_routes import"
        in text
    )
    has_call = "register_tags_routes(app=app, version_prefix=\"/api/v1\")" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return
