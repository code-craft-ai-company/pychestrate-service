"""
.. module:: test_p20b_drift_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the drift-detection REST endpoints (PR p20b).

.. moduleauthor:: Code Craft AI LLC

Covers the drift operations attached by
``register_drift_routes``:

* GET  /api/v1/projects/{project_id}/environments/{environment_id}/drift
* POST /api/v1/projects/{project_id}/environments/{environment_id}/drift:check

Auth (401/403), session boundary (503), project + environment
not-found (404), schedule-missing (409), and happy-path 200/202
each get explicit coverage.
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
)
from ccai.pychestrate.webservice.orchestration.infra.drift.errors import (
    DriftScheduleNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.infra.drift.models import (
    DriftRunState,
    DriftTriggerKind,
)
from ccai.pychestrate.webservice.orchestration.infra.environment.errors import (
    EnvironmentNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.infra.environment.models import (
    EnvironmentState,
)
from ccai.pychestrate.webservice.orchestration.infra.restapi.v1 import (
    drift_routes,
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
        drift_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _patch_project_exists(*, project: Optional[Any]) -> Any:
    patch = create_module_patch(
        drift_routes.projects_repo, "get_project_by_id",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: project)
    return patch


def _make_env_view(
        *,
        environment_id: str = "env-1",
        project_id: str = "proj-1"
    ) -> Any:
    rtnval = drift_routes.environment_service.EnvironmentView(
        environment_id=environment_id,
        project_id=project_id,
        kind_name="k8s_cluster",
        name="staging",
        state=EnvironmentState.ACTIVE,
        attrs={},
    )
    return rtnval


def _patch_environment(*, view: Any = None, raise_missing: bool = False) -> Any:
    patch = create_module_patch(
        drift_routes.environment_service, "get_environment",
    )
    mock = patch.activate()
    if raise_missing is True:
        def _raise(**kwargs):
            raise EnvironmentNotFoundError("missing")
        mock.configure(side_effect=_raise)
    else:
        resolved = view if view is not None else _make_env_view()
        mock.configure(side_effect=lambda **kwargs: resolved)
    return patch


def _make_drift_view(
        *,
        run_id: str = "drift-1",
        project_id: str = "proj-1",
        environment_id: str = "env-1"
    ) -> Any:
    rtnval = drift_routes.drift_service.DriftRunView(
        run_id=run_id,
        project_id=project_id,
        environment_id=environment_id,
        checker_name="terraform",
        state=DriftRunState.PENDING,
        trigger_kind=DriftTriggerKind.MANUAL,
        layer5_run_id=None,
        scheduled_for=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
        ran_at=None,
        drift_count=None,
        added=None,
        changed=None,
        destroyed=None,
        diff_digest_sha256="",
        report_blob_key=None,
        final_state_reason="",
        report_payload=None,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_drift_routes_attaches_two_endpoints():
    """
    **Feature: 6-drift-detection PR p20b**
    **Property: register_drift_routes attaches the two
    method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    drift_routes.register_drift_routes(app=app, version_prefix="/api/v1")
    expected_pairs = (
        (
            "/api/v1/projects/{project_id}/environments/{environment_id}/drift",
            ("GET",),
        ),
        (
            "/api/v1/projects/{project_id}/environments/{environment_id}"
            "/drift:check",
            ("POST",),
        ),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# GET .../drift -- auth + session sweep
# ---------------------------------------------------------------------------


def test_get_drift_returns_503_when_session_missing():
    """
    **Feature: 6-drift-detection PR p20b**
    **Property: GET drift returns 503 when no db_session is
    bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/environments/env-1/drift",
        path_params={"project_id": "proj-1", "environment_id": "env-1"},
        db_session=None,
    )
    response = drift_routes.handle_get_drift_status(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_get_drift_returns_401_when_no_principal():
    """
    **Feature: 6-drift-detection PR p20b**
    **Property: GET drift returns 401 when no AuthPrincipal is
    bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/environments/env-1/drift",
        path_params={"project_id": "proj-1", "environment_id": "env-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = drift_routes.handle_get_drift_status(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_get_drift_returns_403_when_permission_denied():
    """
    **Feature: 6-drift-detection PR p20b**
    **Property: GET drift returns 403 when the principal does not
    hold system:drift.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/environments/env-1/drift",
            path_params={"project_id": "proj-1", "environment_id": "env-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = drift_routes.handle_get_drift_status(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:drift.read")
    return


def test_get_drift_returns_404_when_project_missing():
    """
    **Feature: 6-drift-detection PR p20b**
    **Property: GET drift returns 404 when the project does not
    exist.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=None)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-x/environments/env-1/drift",
            path_params={"project_id": "proj-x", "environment_id": "env-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = drift_routes.handle_get_drift_status(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["project_id"], "proj-x")
    return


def test_get_drift_returns_404_when_environment_missing():
    """
    **Feature: 6-drift-detection PR p20b**
    **Property: GET drift returns 404 when the environment is not
    found.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    env_patch = _patch_environment(raise_missing=True)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/environments/env-x/drift",
            path_params={"project_id": "proj-1", "environment_id": "env-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = drift_routes.handle_get_drift_status(request)
    finally:
        env_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["environment_id"], "env-x")
    return


def test_get_drift_returns_empty_status_when_no_runs():
    """
    **Feature: 6-drift-detection PR p20b**
    **Property: GET drift returns has_report=false when the
    environment has no recorded drift run.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    env_patch = _patch_environment()
    list_patch = create_module_patch(
        drift_routes.drift_service, "list_drift_runs_for_environment",
    )
    list_mock = list_patch.activate()
    list_mock.configure(side_effect=lambda **kwargs: [])
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/environments/env-1/drift",
            path_params={"project_id": "proj-1", "environment_id": "env-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = drift_routes.handle_get_drift_status(request)
    finally:
        list_patch.deactivate()
        env_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["has_report"], False)
    testbase.assert_equal(body["latest_report"], None)
    return


def test_get_drift_returns_latest_report_when_run_exists():
    """
    **Feature: 6-drift-detection PR p20b**
    **Property: GET drift returns the latest drift run as the
    current drift status.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    env_patch = _patch_environment()
    list_patch = create_module_patch(
        drift_routes.drift_service, "list_drift_runs_for_environment",
    )
    list_mock = list_patch.activate()
    list_mock.configure(
        side_effect=lambda **kwargs: [_make_drift_view(run_id="drift-7")],
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/environments/env-1/drift",
            path_params={"project_id": "proj-1", "environment_id": "env-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = drift_routes.handle_get_drift_status(request)
    finally:
        list_patch.deactivate()
        env_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["has_report"], True)
    testbase.assert_equal(body["latest_report"]["run_id"], "drift-7")
    return


# ---------------------------------------------------------------------------
# POST .../drift:check (trigger)
# ---------------------------------------------------------------------------


def test_drift_check_returns_403_when_permission_denied():
    """
    **Feature: 6-drift-detection PR p20b**
    **Property: POST drift:check returns 403 when the principal
    does not hold system:drift.check.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/environments/env-1/drift:check",
            path_params={"project_id": "proj-1", "environment_id": "env-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = drift_routes.handle_trigger_drift_check(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:drift.check")
    return


def test_drift_check_returns_409_when_no_schedule():
    """
    **Feature: 6-drift-detection PR p20b**
    **Property: POST drift:check returns 409 when the environment
    has no drift schedule.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    env_patch = _patch_environment()
    run_patch = create_module_patch(drift_routes.drift_service, "run_now")
    run_mock = run_patch.activate()

    def _raise(**kwargs):
        raise DriftScheduleNotFoundError("no schedule")

    run_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/environments/env-1/drift:check",
            path_params={"project_id": "proj-1", "environment_id": "env-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = drift_routes.handle_trigger_drift_check(request)
    finally:
        run_patch.deactivate()
        env_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["environment_id"], "env-1")
    return


def test_drift_check_returns_202_on_happy_path():
    """
    **Feature: 6-drift-detection PR p20b**
    **Property: POST drift:check returns 202 with the DriftReport
    shape on a valid trigger.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    env_patch = _patch_environment()
    run_patch = create_module_patch(drift_routes.drift_service, "run_now")
    run_mock = run_patch.activate()
    run_mock.configure(
        side_effect=lambda **kwargs: _make_drift_view(run_id="drift-new"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/environments/env-1/drift:check",
            path_params={"project_id": "proj-1", "environment_id": "env-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = drift_routes.handle_trigger_drift_check(request)
    finally:
        run_patch.deactivate()
        env_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 202)
    body = _decode_body(response)
    testbase.assert_equal(body["run_id"], "drift-new")
    testbase.assert_equal(body["state"], "pending")
    return
