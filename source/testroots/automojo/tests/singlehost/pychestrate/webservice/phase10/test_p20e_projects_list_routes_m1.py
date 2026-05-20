"""
.. module:: test_p20e_projects_list_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the project-management list REST endpoint (PR p20e).

.. moduleauthor:: Automation Mojo LLC

Covers ``GET /api/v1/projects`` -- the project-selector
enumeration gap surfaced by PR #220. The route is RBAC-gated on
``system:projects.read`` and returns a paginated
``Page<Project>`` (``{items, meta}``).

Auth (401/403), session boundary (503), bad query params (400),
state filtering, pagination, and the happy-path 200 each get
explicit coverage.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from automojo import testbase
from automojo.testbase.mocking import create_module_patch

from automojo.pychestrate.webservice.api.problem_json import (
    PROBLEM_TYPE_BAD_REQUEST,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_UNAUTHENTICATED,
)
from automojo.pychestrate.webservice.projects.models import ProjectState
from automojo.pychestrate.webservice.projects.restapi.v1 import projects_routes


# ---------------------------------------------------------------------------
# Fakes
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
            path: str = "/api/v1/projects",
            query: Optional[Dict[str, str]] = None,
            db_session: Optional[Any] = None,
            auth_principal: Optional[Any] = None
        ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = {}
        self.query_params: _FakeQueryParams = _FakeQueryParams(values=query)
        self.db_session: Optional[Any] = db_session
        self.auth_principal: Optional[Any] = auth_principal
        return

    def json(self) -> Any:
        return None


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


class _FakePrincipal:
    def __init__(self, *, user_id: str = "user-1") -> None:
        self.user_id: str = user_id
        return


class _FakeDecision:
    def __init__(self, *, allowed: bool, reason: str = "") -> None:
        self.allowed: bool = allowed
        self.reason: str = reason
        return


class _FakeProject:
    def __init__(
            self,
            *,
            project_id: str,
            slug: str,
            state: ProjectState = ProjectState.ACTIVE
        ) -> None:
        self.project_id: str = project_id
        self.slug: str = slug
        self.display_name: str = "Project " + slug
        self.description: str = ""
        self.state: ProjectState = state
        self.owning_group_id: Optional[str] = None
        self.template_id: Optional[str] = None
        self.template_version: Optional[str] = None
        self.extension_fields: Dict[str, Any] = {}
        self.created_at: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.updated_at: datetime = datetime(2026, 1, 2, tzinfo=timezone.utc)
        self.archived_at: Optional[datetime] = None
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_check_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(projects_routes.rbac_evaluator, "check_permission")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _patch_list_projects(*, rows: List[Any]) -> Any:
    patch = create_module_patch(
        projects_routes.project_repository, "list_projects"
    )
    mock = patch.activate()

    def _list(*, db_session: Any, state: Any, offset: int, limit: int) -> List[Any]:
        window = rows[offset:offset + limit]
        return window

    mock.configure(side_effect=_list)
    return patch


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_attaches_get_projects_list_route():
    """
    **Feature: 2-projects PR p20e**
    **Property: register_projects_routes attaches GET /api/v1/projects.**
    """
    app = _FakeApp()
    projects_routes.register_projects_routes(
        app=app, version_prefix="/api/v1"
    )

    pairs = [(path, methods) for path, methods, _ in app.calls]
    testbase.assert_true(("/api/v1/projects", ("GET",)) in pairs)
    return


# ---------------------------------------------------------------------------
# Session / auth boundary
# ---------------------------------------------------------------------------


def test_list_projects_returns_503_without_session():
    """
    **Feature: 2-projects PR p20e**
    **Property: handle_list_projects returns 503 when no db_session.**
    """
    response = projects_routes.handle_list_projects(
        _FakeRequest(db_session=None)
    )
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_list_projects_returns_401_when_anonymous():
    """
    **Feature: 2-projects PR p20e**
    **Property: handle_list_projects returns 401 when no principal.**
    """
    response = projects_routes.handle_list_projects(
        _FakeRequest(db_session=object(), auth_principal=None)
    )
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_projects_returns_403_when_permission_denied():
    """
    **Feature: 2-projects PR p20e**
    **Property: handle_list_projects returns 403 when the principal
    lacks system:projects.read.**
    """
    patch = _patch_check_permission(allowed=False)
    try:
        response = projects_routes.handle_list_projects(
            _FakeRequest(db_session=object(), auth_principal=_FakePrincipal())
        )
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(
        body["required_permission"], "system:projects.read"
    )
    return


# ---------------------------------------------------------------------------
# Happy path / pagination / filtering
# ---------------------------------------------------------------------------


def test_list_projects_returns_200_page_envelope():
    """
    **Feature: 2-projects PR p20e**
    **Property: handle_list_projects returns 200 with an
    {items, meta} page when authorized.**
    """
    rows = [
        _FakeProject(project_id="p-1", slug="alpha"),
        _FakeProject(project_id="p-2", slug="beta"),
    ]
    perm_patch = _patch_check_permission(allowed=True)
    list_patch = _patch_list_projects(rows=rows)
    try:
        response = projects_routes.handle_list_projects(
            _FakeRequest(db_session=object(), auth_principal=_FakePrincipal())
        )
    finally:
        list_patch.deactivate()
        perm_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 2)
    testbase.assert_equal(body["items"][0]["slug"], "alpha")
    testbase.assert_equal(body["meta"]["total"], 2)
    testbase.assert_equal(body["meta"]["page"], 1)
    return


def test_list_projects_applies_pagination_window():
    """
    **Feature: 2-projects PR p20e**
    **Property: page + per_page query params slice the result set.**
    """
    rows = [
        _FakeProject(project_id="p-{}".format(idx), slug="s{}".format(idx))
        for idx in range(0, 5)
    ]
    perm_patch = _patch_check_permission(allowed=True)
    list_patch = _patch_list_projects(rows=rows)
    try:
        response = projects_routes.handle_list_projects(
            _FakeRequest(
                db_session=object(),
                auth_principal=_FakePrincipal(),
                query={"page": "2", "per_page": "2"},
            )
        )
    finally:
        list_patch.deactivate()
        perm_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 2)
    testbase.assert_equal(body["items"][0]["slug"], "s2")
    testbase.assert_equal(body["meta"]["total"], 5)
    testbase.assert_equal(body["meta"]["page"], 2)
    return


def test_list_projects_returns_400_on_bad_state_filter():
    """
    **Feature: 2-projects PR p20e**
    **Property: an unknown state query value yields a 400 problem.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        response = projects_routes.handle_list_projects(
            _FakeRequest(
                db_session=object(),
                auth_principal=_FakePrincipal(),
                query={"state": "BOGUS"},
            )
        )
    finally:
        perm_patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    return


def test_list_projects_returns_400_on_non_integer_page():
    """
    **Feature: 2-projects PR p20e**
    **Property: a non-integer page query value yields a 400 problem.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    try:
        response = projects_routes.handle_list_projects(
            _FakeRequest(
                db_session=object(),
                auth_principal=_FakePrincipal(),
                query={"page": "abc"},
            )
        )
    finally:
        perm_patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    return


def test_list_projects_passes_state_filter_to_repository():
    """
    **Feature: 2-projects PR p20e**
    **Property: a valid state query value is coerced to a
    ProjectState and forwarded to the repository.**
    """
    captured: Dict[str, Any] = {}
    rows = [_FakeProject(project_id="p-1", slug="alpha")]

    perm_patch = _patch_check_permission(allowed=True)
    list_patch = create_module_patch(
        projects_routes.project_repository, "list_projects"
    )
    mock = list_patch.activate()

    def _list(*, db_session: Any, state: Any, offset: int, limit: int) -> List[Any]:
        captured["state"] = state
        return rows

    mock.configure(side_effect=_list)
    try:
        response = projects_routes.handle_list_projects(
            _FakeRequest(
                db_session=object(),
                auth_principal=_FakePrincipal(),
                query={"state": "ARCHIVED"},
            )
        )
    finally:
        list_patch.deactivate()
        perm_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    testbase.assert_equal(captured["state"], ProjectState.ARCHIVED)
    return
