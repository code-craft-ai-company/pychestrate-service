"""
.. module:: test_p20a_build_runs_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the build-orchestration REST endpoints (PR p20a).

.. moduleauthor:: Automation Mojo LLC

Covers the build operations attached by
``register_build_runs_routes``:

* POST /api/v1/projects/{project_id}/builds
* GET  /api/v1/projects/{project_id}/builds
* GET  /api/v1/projects/{project_id}/builds/{build_id}
* GET  /api/v1/projects/{project_id}/builds/{build_id}/artifacts

Auth (401/403), session boundary (503), project not-found (404),
malformed body (422), pagination, and happy-path 200/202 each get
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
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_UNAUTHENTICATED,
    PROBLEM_TYPE_VALIDATION_FAILED,
)
from automojo.pychestrate.webservice.orchestration.build.errors import (
    BuildRunnerKindUnknownError,
)
from automojo.pychestrate.webservice.orchestration.build.models import (
    BuildRunState,
)
from automojo.pychestrate.webservice.orchestration.build.restapi.v1 import (
    build_runs_routes,
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


class _FakeManifestRow:
    def __init__(self, *, manifest_id: str) -> None:
        self.manifest_id: str = manifest_id
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_check_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(build_runs_routes.rbac_evaluator, "check_permission")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _patch_project_exists(*, project: Optional[Any]) -> Any:
    patch = create_module_patch(build_runs_routes.projects_repo, "get_project_by_id")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: project)
    return patch


def _patch_eligible_candidates(*, candidates: Optional[List[Any]] = None) -> Any:
    """
        Patch the route's eligible-pod selection so the trigger
        tests do not need a real db session. Defaults to one
        candidate so the dispatch path is reached.
    """
    resolved = candidates
    if resolved is None:
        resolved = [
            build_runs_routes.DispatchCandidate(
                client_id="client-1",
                pod_id="pod-1",
                capability_tags=tuple(),
                inflight_dispatch_count=0,
                last_dispatched_at_iso="",
            )
        ]
    patch = create_module_patch(
        build_runs_routes, "_build_eligible_pod_candidates",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: list(resolved))
    return patch


def _make_build_view(
        *,
        run_id: str = "run-1",
        project_id: str = "proj-1",
        state: Any = None
    ) -> Any:
    resolved_state = state if state is not None else BuildRunState.PENDING
    rtnval = build_runs_routes.build_service.BuildRunView(
        run_id=run_id,
        project_id=project_id,
        runner_kind="makefile",
        repro_digest_sha256="a" * 64,
        state=resolved_state,
        layer5_run_id=None,
        pipeline_run_id=None,
        pipeline_step_run_id=None,
        actor_id=None,
        started_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
        finished_at=None,
        final_state_reason="",
        inputs={"targets": ["all"]},
        annotations={},
        toolchain=(),
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_build_runs_routes_attaches_four_endpoints():
    """
    **Feature: 6-build-orchestration PR p20a**
    **Property: register_build_runs_routes attaches the four
    method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    build_runs_routes.register_build_runs_routes(app=app, version_prefix="/api/v1")
    expected_pairs = (
        ("/api/v1/projects/{project_id}/builds", ("POST",)),
        ("/api/v1/projects/{project_id}/builds", ("GET",)),
        ("/api/v1/projects/{project_id}/builds/{build_id}", ("GET",)),
        ("/api/v1/projects/{project_id}/builds/{build_id}/artifacts", ("GET",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# GET /builds -- auth + session sweep
# ---------------------------------------------------------------------------


def test_list_returns_503_when_session_missing():
    """
    **Feature: 6-build-orchestration PR p20a**
    **Property: GET builds returns 503 when no db_session is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/builds",
        path_params={"project_id": "proj-1"},
        db_session=None,
    )
    response = build_runs_routes.handle_list_builds(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_list_returns_401_when_no_principal():
    """
    **Feature: 6-build-orchestration PR p20a**
    **Property: GET builds returns 401 when no AuthPrincipal is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/builds",
        path_params={"project_id": "proj-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = build_runs_routes.handle_list_builds(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_returns_403_when_permission_denied():
    """
    **Feature: 6-build-orchestration PR p20a**
    **Property: GET builds returns 403 when the principal does not
    hold system:builds.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/builds",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = build_runs_routes.handle_list_builds(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:builds.read")
    return


def test_list_returns_404_when_project_missing():
    """
    **Feature: 6-build-orchestration PR p20a**
    **Property: GET builds returns 404 when the project does not
    exist.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=None)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-x/builds",
            path_params={"project_id": "proj-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = build_runs_routes.handle_list_builds(request)
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
    **Feature: 6-build-orchestration PR p20a**
    **Property: GET builds returns a {items, meta} page with
    BuildRun-shaped items.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    list_patch = create_module_patch(
        build_runs_routes.build_service, "list_build_runs_for_project",
    )
    list_mock = list_patch.activate()
    list_mock.configure(
        side_effect=lambda **kwargs: [_make_build_view(run_id="run-1")],
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/builds",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            query={"page": "1", "per_page": "10"},
        )
        response = build_runs_routes.handle_list_builds(request)
    finally:
        list_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["run_id"], "run-1")
    testbase.assert_equal(body["items"][0]["state"], "pending")
    testbase.assert_equal(body["meta"]["page"], 1)
    testbase.assert_equal(body["meta"]["total"], 1)
    return


def test_list_filters_by_state_query_param():
    """
    **Feature: 6-build-orchestration PR p20a**
    **Property: GET builds filters the returned page by the state
    query param.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    list_patch = create_module_patch(
        build_runs_routes.build_service, "list_build_runs_for_project",
    )
    list_mock = list_patch.activate()
    list_mock.configure(
        side_effect=lambda **kwargs: [
            _make_build_view(run_id="run-pending", state=BuildRunState.PENDING),
            _make_build_view(run_id="run-failed", state=BuildRunState.FAILED),
        ],
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/builds",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            query={"state": "failed"},
        )
        response = build_runs_routes.handle_list_builds(request)
    finally:
        list_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["run_id"], "run-failed")
    return


# ---------------------------------------------------------------------------
# POST /builds (trigger)
# ---------------------------------------------------------------------------


def test_trigger_returns_422_on_missing_body():
    """
    **Feature: 6-build-orchestration PR p20a**
    **Property: POST builds returns 422 problem when body is
    missing.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/builds",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body=None,
        )
        response = build_runs_routes.handle_trigger_build(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_trigger_returns_422_on_missing_runner_kind():
    """
    **Feature: 6-build-orchestration PR p20a**
    **Property: POST builds returns 422 when runner_kind is
    absent.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/builds",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"runner_inputs": {"targets": ["all"]}},
        )
        response = build_runs_routes.handle_trigger_build(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal("runner_kind" in body["missing_fields"], True)
    return


def test_trigger_returns_422_when_runner_kind_unknown():
    """
    **Feature: 6-build-orchestration PR p20a**
    **Property: POST builds returns 422 when the runner kind has no
    registered factory.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    cand_patch = _patch_eligible_candidates()
    trigger_patch = create_module_patch(
        build_runs_routes.build_service, "trigger_run",
    )
    trigger_mock = trigger_patch.activate()

    def _raise(**kwargs):
        raise BuildRunnerKindUnknownError("no runner")

    trigger_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/builds",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"runner_kind": "bogus", "runner_inputs": {}},
        )
        response = build_runs_routes.handle_trigger_build(request)
    finally:
        trigger_patch.deactivate()
        cand_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["runner_kind"], "bogus")
    return


def test_trigger_returns_202_on_happy_path():
    """
    **Feature: 6-build-orchestration PR p20a**
    **Property: POST builds returns 202 with the BuildRun shape on
    a valid body.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    cand_patch = _patch_eligible_candidates()
    trigger_patch = create_module_patch(
        build_runs_routes.build_service, "trigger_run",
    )
    trigger_mock = trigger_patch.activate()
    trigger_mock.configure(
        side_effect=lambda **kwargs: _make_build_view(
            run_id="run-new", state=BuildRunState.RUNNING,
        ),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/builds",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "runner_kind": "makefile",
                "runner_inputs": {"targets": ["all"]},
            },
        )
        response = build_runs_routes.handle_trigger_build(request)
    finally:
        trigger_patch.deactivate()
        cand_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 202)
    body = _decode_body(response)
    testbase.assert_equal(body["run_id"], "run-new")
    testbase.assert_equal(body["runner_kind"], "makefile")
    testbase.assert_equal(body["state"], "running")
    return


def test_trigger_returns_403_when_permission_denied():
    """
    **Feature: 6-build-orchestration PR p20a**
    **Property: POST builds returns 403 when the principal does not
    hold system:builds.create.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/builds",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"runner_kind": "makefile"},
        )
        response = build_runs_routes.handle_trigger_build(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:builds.create")
    return


# ---------------------------------------------------------------------------
# GET /builds/{build_id}
# ---------------------------------------------------------------------------


def test_read_returns_404_when_build_run_missing():
    """
    **Feature: 6-build-orchestration PR p20a**
    **Property: GET builds/{id} returns 404 when the build run is
    not found.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        build_runs_routes.build_service, "get_build_run",
    )
    get_mock = get_patch.activate()

    def _raise(**kwargs):
        from automojo.pychestrate.webservice.orchestration.build.errors import (
            BuildRunNotFoundError,
        )
        raise BuildRunNotFoundError("missing")

    get_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/builds/run-x",
            path_params={"project_id": "proj-1", "build_id": "run-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = build_runs_routes.handle_read_build(request)
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["build_id"], "run-x")
    return


def test_read_returns_200_on_happy_path():
    """
    **Feature: 6-build-orchestration PR p20a**
    **Property: GET builds/{id} returns 200 with the BuildRun
    shape.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        build_runs_routes.build_service, "get_build_run",
    )
    get_mock = get_patch.activate()
    get_mock.configure(
        side_effect=lambda **kwargs: _make_build_view(run_id="run-7"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/builds/run-7",
            path_params={"project_id": "proj-1", "build_id": "run-7"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = build_runs_routes.handle_read_build(request)
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["run_id"], "run-7")
    return


def test_read_returns_404_when_project_mismatch():
    """
    **Feature: 6-build-orchestration PR p20a**
    **Property: GET builds/{id} returns 404 when the build run
    belongs to a different project.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        build_runs_routes.build_service, "get_build_run",
    )
    get_mock = get_patch.activate()
    get_mock.configure(
        side_effect=lambda **kwargs: _make_build_view(
            run_id="run-9", project_id="other-proj",
        ),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/builds/run-9",
            path_params={"project_id": "proj-1", "build_id": "run-9"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = build_runs_routes.handle_read_build(request)
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return


# ---------------------------------------------------------------------------
# GET /builds/{build_id}/artifacts
# ---------------------------------------------------------------------------


def test_list_artifacts_returns_empty_page_when_no_manifest():
    """
    **Feature: 6-build-orchestration PR p20a**
    **Property: GET builds/{id}/artifacts returns an empty page
    when the build run has no synthesized manifest.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        build_runs_routes.build_service, "get_build_run",
    )
    get_mock = get_patch.activate()
    get_mock.configure(
        side_effect=lambda **kwargs: _make_build_view(run_id="run-5"),
    )
    manifest_patch = create_module_patch(
        build_runs_routes.artifacts_repo, "find_manifest_by_build_run",
    )
    manifest_mock = manifest_patch.activate()
    manifest_mock.configure(side_effect=lambda **kwargs: None)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/builds/run-5/artifacts",
            path_params={"project_id": "proj-1", "build_id": "run-5"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = build_runs_routes.handle_list_build_artifacts(request)
    finally:
        manifest_patch.deactivate()
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["items"], [])
    testbase.assert_equal(body["manifest_id"], None)
    return


def test_list_artifacts_returns_403_when_permission_denied():
    """
    **Feature: 6-build-orchestration PR p20a**
    **Property: GET builds/{id}/artifacts returns 403 when the
    principal lacks system:builds.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/builds/run-5/artifacts",
            path_params={"project_id": "proj-1", "build_id": "run-5"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = build_runs_routes.handle_list_build_artifacts(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:builds.read")
    return
