"""
.. module:: test_p20b_environments_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the environment-registry REST endpoints (PR p20b).

.. moduleauthor:: Code Craft AI LLC

Covers the environment operations attached by
``register_environments_routes``:

* GET  /api/v1/projects/{project_id}/environments
* POST /api/v1/projects/{project_id}/environments
* GET  /api/v1/projects/{project_id}/environments/{environment_id}

Auth (401/403), session boundary (503), project not-found (404),
malformed body (422), pagination, and happy-path 200/201 each get
explicit coverage.
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

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_UNAUTHENTICATED,
    PROBLEM_TYPE_VALIDATION_FAILED,
)
from ccai.pychestrate.webservice.orchestration.infra.environment.errors import (
    EnvironmentKindUnknownError,
    EnvironmentNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.infra.environment.models import (
    EnvironmentState,
)
from ccai.pychestrate.webservice.orchestration.infra.restapi.v1 import (
    environments_routes,
)


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
            path: str,
            path_params: Optional[Dict[str, Any]] = None,
            query: Optional[Dict[str, str]] = None,
            body: Any = None,
            db_session: Optional[Any] = None,
            auth_principal: Optional[Any] = None
        ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self.query_params: _FakeQueryParams = _FakeQueryParams(values=query)
        self._body: Any = body
        self.db_session: Optional[Any] = db_session
        self.auth_principal: Optional[Any] = auth_principal
        return

    def json(self) -> Any:
        rtnval = self._body
        return rtnval


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
    def __init__(self, *, project_id: str) -> None:
        self.project_id: str = project_id
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_check_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(
        environments_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _patch_project_exists(*, project: Optional[Any]) -> Any:
    patch = create_module_patch(
        environments_routes.projects_repo, "get_project_by_id",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: project)
    return patch


def _make_env_view(
        *,
        environment_id: str = "env-1",
        project_id: str = "proj-1",
        state: Any = None
    ) -> Any:
    resolved_state = state if state is not None else EnvironmentState.ACTIVE
    rtnval = environments_routes.environment_service.EnvironmentView(
        environment_id=environment_id,
        project_id=project_id,
        kind_name="k8s_cluster",
        name="staging",
        state=resolved_state,
        attrs={"region": "us-east-1"},
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_environments_routes_attaches_four_endpoints():
    """
    **Feature: 6-environment-registry PR p20b**
    **Property: register_environments_routes attaches the four
    method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    environments_routes.register_environments_routes(
        app=app, version_prefix="/api/v1",
    )
    expected_pairs = (
        ("/api/v1/environment-kinds", ("GET",)),
        ("/api/v1/projects/{project_id}/environments", ("GET",)),
        ("/api/v1/projects/{project_id}/environments", ("POST",)),
        (
            "/api/v1/projects/{project_id}/environments/{environment_id}",
            ("GET",),
        ),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# GET /environments -- auth + session sweep
# ---------------------------------------------------------------------------


def test_list_returns_503_when_session_missing():
    """
    **Feature: 6-environment-registry PR p20b**
    **Property: GET environments returns 503 when no db_session
    is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/environments",
        path_params={"project_id": "proj-1"},
        db_session=None,
    )
    response = environments_routes.handle_list_environments(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_list_returns_401_when_no_principal():
    """
    **Feature: 6-environment-registry PR p20b**
    **Property: GET environments returns 401 when no AuthPrincipal
    is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/environments",
        path_params={"project_id": "proj-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = environments_routes.handle_list_environments(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_returns_403_when_permission_denied():
    """
    **Feature: 6-environment-registry PR p20b**
    **Property: GET environments returns 403 when the principal
    does not hold system:environments.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/environments",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = environments_routes.handle_list_environments(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(
        body["required_permission"], "system:environments.read",
    )
    return


def test_list_returns_404_when_project_missing():
    """
    **Feature: 6-environment-registry PR p20b**
    **Property: GET environments returns 404 when the project
    does not exist.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=None)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-x/environments",
            path_params={"project_id": "proj-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = environments_routes.handle_list_environments(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["project_id"], "proj-x")
    return


def test_list_returns_page_envelope_on_happy_path():
    """
    **Feature: 6-environment-registry PR p20b**
    **Property: GET environments returns a {items, meta} page
    with Environment-shaped items.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    list_patch = create_module_patch(
        environments_routes.environment_service, "list_environments",
    )
    list_mock = list_patch.activate()
    list_mock.configure(
        side_effect=lambda **kwargs: [_make_env_view(environment_id="env-1")],
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/environments",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            query={"page": "1", "per_page": "10"},
        )
        response = environments_routes.handle_list_environments(request)
    finally:
        list_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["environment_id"], "env-1")
    testbase.assert_equal(body["items"][0]["state"], "active")
    testbase.assert_equal(body["meta"]["page"], 1)
    testbase.assert_equal(body["meta"]["total"], 1)
    return


# ---------------------------------------------------------------------------
# POST /environments (register)
# ---------------------------------------------------------------------------


def test_register_returns_422_on_missing_body():
    """
    **Feature: 6-environment-registry PR p20b**
    **Property: POST environments returns 422 problem when body
    is missing.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/environments",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body=None,
        )
        response = environments_routes.handle_register_environment(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_register_returns_422_on_missing_kind_name():
    """
    **Feature: 6-environment-registry PR p20b**
    **Property: POST environments returns 422 when kind_name is
    absent.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/environments",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"name": "staging"},
        )
        response = environments_routes.handle_register_environment(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal("kind_name" in body["missing_fields"], True)
    return


def test_register_returns_422_when_kind_unknown():
    """
    **Feature: 6-environment-registry PR p20b**
    **Property: POST environments returns 422 when the kind has
    no registered factory.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    declare_patch = create_module_patch(
        environments_routes.environment_service, "declare_environment",
    )
    declare_mock = declare_patch.activate()

    def _raise(**kwargs):
        raise EnvironmentKindUnknownError("no kind")

    declare_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/environments",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"name": "staging", "kind_name": "bogus"},
        )
        response = environments_routes.handle_register_environment(request)
    finally:
        declare_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["kind_name"], "bogus")
    return


def test_register_returns_201_on_happy_path():
    """
    **Feature: 6-environment-registry PR p20b**
    **Property: POST environments returns 201 with the
    Environment shape on a valid body.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    declare_patch = create_module_patch(
        environments_routes.environment_service, "declare_environment",
    )
    declare_mock = declare_patch.activate()
    declare_mock.configure(
        side_effect=lambda **kwargs: _make_env_view(environment_id="env-new"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/environments",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "name": "staging",
                "kind_name": "k8s_cluster",
                "attrs": {"region": "us-east-1"},
            },
        )
        response = environments_routes.handle_register_environment(request)
    finally:
        declare_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["environment_id"], "env-new")
    testbase.assert_equal(body["kind_name"], "k8s_cluster")
    return


def test_register_returns_403_when_permission_denied():
    """
    **Feature: 6-environment-registry PR p20b**
    **Property: POST environments returns 403 when the principal
    lacks system:environments.write.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/environments",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"name": "staging", "kind_name": "k8s_cluster"},
        )
        response = environments_routes.handle_register_environment(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(
        body["required_permission"], "system:environments.write",
    )
    return


# ---------------------------------------------------------------------------
# GET /environments/{environment_id}
# ---------------------------------------------------------------------------


def test_read_returns_404_when_environment_missing():
    """
    **Feature: 6-environment-registry PR p20b**
    **Property: GET environments/{id} returns 404 when the
    environment is not found.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        environments_routes.environment_service, "get_environment",
    )
    get_mock = get_patch.activate()

    def _raise(**kwargs):
        raise EnvironmentNotFoundError("missing")

    get_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/environments/env-x",
            path_params={"project_id": "proj-1", "environment_id": "env-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = environments_routes.handle_read_environment(request)
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["environment_id"], "env-x")
    return


def test_read_returns_200_on_happy_path():
    """
    **Feature: 6-environment-registry PR p20b**
    **Property: GET environments/{id} returns 200 with the
    Environment shape.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        environments_routes.environment_service, "get_environment",
    )
    get_mock = get_patch.activate()
    get_mock.configure(
        side_effect=lambda **kwargs: _make_env_view(environment_id="env-7"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/environments/env-7",
            path_params={"project_id": "proj-1", "environment_id": "env-7"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = environments_routes.handle_read_environment(request)
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["environment_id"], "env-7")
    return


def test_read_returns_404_when_project_mismatch():
    """
    **Feature: 6-environment-registry PR p20b**
    **Property: GET environments/{id} returns 404 when the
    environment belongs to a different project.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        environments_routes.environment_service, "get_environment",
    )
    get_mock = get_patch.activate()
    get_mock.configure(
        side_effect=lambda **kwargs: _make_env_view(
            environment_id="env-9", project_id="other-proj",
        ),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/environments/env-9",
            path_params={"project_id": "proj-1", "environment_id": "env-9"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = environments_routes.handle_read_environment(request)
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return
