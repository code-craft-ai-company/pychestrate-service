"""
.. module:: test_p20a_source_integrations_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the source-integrations REST endpoints (PR p20a).

.. moduleauthor:: Code Craft AI LLC

Covers the source-integrations operations attached by
``register_source_integrations_routes``:

* GET  /api/v1/projects/{project_id}/source-integrations
* POST /api/v1/projects/{project_id}/source-integrations
* GET  /api/v1/projects/{project_id}/source-integrations/{integration_id}

Auth (401/403), session boundary (503), project not-found (404),
malformed body (422), and happy-path 200 each get explicit
coverage.
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
from ccai.pychestrate.webservice.orchestration.source.errors import (
    ScmConfigNotFoundError,
    ScmProviderNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.source.restapi.v1 import (
    source_integrations_routes,
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
        self.path_params: Dict[str, Any] = path_params if path_params is not None else {}
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
    def __init__(self, *, project_id: str, slug: str = "proj-slug") -> None:
        self.project_id: str = project_id
        self.slug: str = slug
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_check_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(
        source_integrations_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _patch_project_exists(*, project: Optional[Any]) -> Any:
    patch = create_module_patch(
        source_integrations_routes.projects_repo, "get_project_by_id",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: project)
    return patch


def _make_config_view(*, project_id: str = "proj-1") -> Any:
    now = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    rtnval = source_integrations_routes.source_service.ScmProjectConfigView(
        project_id=project_id,
        provider_name="github",
        repo_key="owner/repo",
        pipeline_file_path=".pychestrate/pipeline.yaml",
        use_polling=False,
        polling_ref_glob="",
        last_poll_at=None,
        created_at=now,
        updated_at=now,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_source_integrations_routes_attaches_three_endpoints():
    """
    **Feature: 6-source-integrations PR p20a**
    **Property: register_source_integrations_routes attaches the
    three method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    source_integrations_routes.register_source_integrations_routes(
        app=app, version_prefix="/api/v1",
    )
    expected_pairs = (
        ("/api/v1/projects/{project_id}/source-integrations", ("GET",)),
        ("/api/v1/projects/{project_id}/source-integrations", ("POST",)),
        (
            "/api/v1/projects/{project_id}/source-integrations/{integration_id}",
            ("GET",),
        ),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# GET /source-integrations -- auth + session sweep
# ---------------------------------------------------------------------------


def test_list_returns_503_when_session_missing():
    """
    **Feature: 6-source-integrations PR p20a**
    **Property: GET source-integrations returns 503 when no
    db_session is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/source-integrations",
        path_params={"project_id": "proj-1"},
        db_session=None,
    )
    response = source_integrations_routes.handle_list_source_integrations(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_list_returns_401_when_no_principal():
    """
    **Feature: 6-source-integrations PR p20a**
    **Property: GET source-integrations returns 401 when no
    AuthPrincipal is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/source-integrations",
        path_params={"project_id": "proj-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = source_integrations_routes.handle_list_source_integrations(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_returns_403_when_permission_denied():
    """
    **Feature: 6-source-integrations PR p20a**
    **Property: GET source-integrations returns 403 when the
    principal does not hold system:source_integrations.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/source-integrations",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = source_integrations_routes.handle_list_source_integrations(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(
        body["required_permission"], "system:source_integrations.read",
    )
    return


def test_list_returns_404_when_project_missing():
    """
    **Feature: 6-source-integrations PR p20a**
    **Property: GET source-integrations returns 404 when the
    project does not exist.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=None)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-x/source-integrations",
            path_params={"project_id": "proj-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = source_integrations_routes.handle_list_source_integrations(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    return


def test_list_returns_empty_page_when_no_config():
    """
    **Feature: 6-source-integrations PR p20a**
    **Property: GET source-integrations returns an empty page when
    the project has no SCM config.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        source_integrations_routes.source_service, "get_project_config",
    )
    get_mock = get_patch.activate()

    def _raise(**kwargs):
        raise ScmConfigNotFoundError("no config")

    get_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/source-integrations",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = source_integrations_routes.handle_list_source_integrations(request)
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["items"], [])
    testbase.assert_equal(body["meta"]["total"], 0)
    return


def test_list_returns_page_with_config_on_happy_path():
    """
    **Feature: 6-source-integrations PR p20a**
    **Property: GET source-integrations returns a single-element
    page when a config is registered.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        source_integrations_routes.source_service, "get_project_config",
    )
    get_mock = get_patch.activate()
    get_mock.configure(
        side_effect=lambda **kwargs: _make_config_view(project_id="proj-1"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/source-integrations",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = source_integrations_routes.handle_list_source_integrations(request)
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["provider_name"], "github")
    testbase.assert_equal(body["items"][0]["repo_key"], "owner/repo")
    return


# ---------------------------------------------------------------------------
# POST /source-integrations (register)
# ---------------------------------------------------------------------------


def test_register_returns_422_on_missing_body():
    """
    **Feature: 6-source-integrations PR p20a**
    **Property: POST source-integrations returns 422 when body is
    missing.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/source-integrations",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body=None,
        )
        response = source_integrations_routes.handle_register_source_integration(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_register_returns_422_on_missing_required_fields():
    """
    **Feature: 6-source-integrations PR p20a**
    **Property: POST source-integrations returns 422 listing the
    missing required fields when provider_name / repo_key are
    absent.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/source-integrations",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"use_polling": False},
        )
        response = source_integrations_routes.handle_register_source_integration(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal("provider_name" in body["missing_fields"], True)
    testbase.assert_equal("repo_key" in body["missing_fields"], True)
    return


def test_register_returns_422_when_provider_unknown():
    """
    **Feature: 6-source-integrations PR p20a**
    **Property: POST source-integrations returns 422 when the
    provider has no registered factory.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    set_patch = create_module_patch(
        source_integrations_routes.source_service, "set_project_config",
    )
    set_mock = set_patch.activate()

    def _raise(**kwargs):
        raise ScmProviderNotFoundError("no provider")

    set_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/source-integrations",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"provider_name": "bogus", "repo_key": "owner/repo"},
        )
        response = source_integrations_routes.handle_register_source_integration(request)
    finally:
        set_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["provider_name"], "bogus")
    return


def test_register_returns_200_on_happy_path():
    """
    **Feature: 6-source-integrations PR p20a**
    **Property: POST source-integrations returns 200 with the
    SourceIntegration shape on a valid body.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    set_patch = create_module_patch(
        source_integrations_routes.source_service, "set_project_config",
    )
    set_mock = set_patch.activate()
    set_mock.configure(
        side_effect=lambda **kwargs: _make_config_view(project_id="proj-1"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/source-integrations",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"provider_name": "github", "repo_key": "owner/repo"},
        )
        response = source_integrations_routes.handle_register_source_integration(request)
    finally:
        set_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["provider_name"], "github")
    testbase.assert_equal(body["integration_id"], "proj-1")
    return


def test_register_returns_403_when_permission_denied():
    """
    **Feature: 6-source-integrations PR p20a**
    **Property: POST source-integrations returns 403 when the
    principal does not hold system:source_integrations.write.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/source-integrations",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"provider_name": "github", "repo_key": "owner/repo"},
        )
        response = source_integrations_routes.handle_register_source_integration(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(
        body["required_permission"], "system:source_integrations.write",
    )
    return


# ---------------------------------------------------------------------------
# GET /source-integrations/{integration_id}
# ---------------------------------------------------------------------------


def test_read_returns_404_when_config_missing():
    """
    **Feature: 6-source-integrations PR p20a**
    **Property: GET source-integrations/{id} returns 404 when the
    project has no SCM config.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        source_integrations_routes.source_service, "get_project_config",
    )
    get_mock = get_patch.activate()

    def _raise(**kwargs):
        raise ScmConfigNotFoundError("no config")

    get_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/source-integrations/proj-1",
            path_params={"project_id": "proj-1", "integration_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = source_integrations_routes.handle_read_source_integration(request)
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["integration_id"], "proj-1")
    return


def test_read_returns_404_when_integration_id_mismatch():
    """
    **Feature: 6-source-integrations PR p20a**
    **Property: GET source-integrations/{id} returns 404 when the
    integration_id does not match the project id.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/source-integrations/other",
            path_params={"project_id": "proj-1", "integration_id": "other"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = source_integrations_routes.handle_read_source_integration(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return


def test_read_returns_200_on_happy_path():
    """
    **Feature: 6-source-integrations PR p20a**
    **Property: GET source-integrations/{id} returns 200 with the
    SourceIntegration shape.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        source_integrations_routes.source_service, "get_project_config",
    )
    get_mock = get_patch.activate()
    get_mock.configure(
        side_effect=lambda **kwargs: _make_config_view(project_id="proj-1"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/source-integrations/proj-1",
            path_params={"project_id": "proj-1", "integration_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = source_integrations_routes.handle_read_source_integration(request)
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["provider_name"], "github")
    testbase.assert_equal(body["integration_id"], "proj-1")
    return
