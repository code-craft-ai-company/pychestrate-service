"""
.. module:: test_p20b_provisioning_runs_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the provisioning-run REST endpoints (PR p20b).

.. moduleauthor:: Code Craft AI LLC

Covers the provisioning operations attached by
``register_provisioning_runs_routes``:

* POST /api/v1/projects/{project_id}/provisioning-runs
* GET  /api/v1/projects/{project_id}/provisioning-runs
* GET  /api/v1/projects/{project_id}/provisioning-runs/{run_id}

Auth (401/403), session boundary (503), project not-found (404),
malformed body (422), pagination, and happy-path 200/202 each get
explicit coverage.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_UNAUTHENTICATED,
    PROBLEM_TYPE_VALIDATION_FAILED,
)
from ccai.pychestrate.webservice.orchestration.infra.runs.errors import (
    InfraDriverUnknownError,
    InfraRunNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.infra.runs.models import (
    InfraAction,
    InfraRunState,
)
from ccai.pychestrate.webservice.orchestration.infra.restapi.v1 import (
    provisioning_runs_routes,
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
        provisioning_runs_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _patch_project_exists(*, project: Optional[Any]) -> Any:
    patch = create_module_patch(
        provisioning_runs_routes.projects_repo, "get_project_by_id",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: project)
    return patch


def _patch_eligible_candidates(*, candidates: Optional[List[Any]] = None) -> Any:
    """
        Patch the route's capability-based eligible-pod selection so
        the trigger handler does not touch a real db_session. By
        default returns a single eligible candidate so the handler
        proceeds into ``infra_service.trigger_run``.

        :param candidates: Candidate list to return; ``None`` yields a
                           single placeholder candidate.

        :returns: The activated module patch.
    """
    resolved = candidates if candidates is not None else [object()]
    patch = create_module_patch(
        provisioning_runs_routes, "_build_eligible_pod_candidates",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: list(resolved))
    return patch


def _make_run_view(
        *,
        run_id: str = "run-1",
        project_id: str = "proj-1",
        state: Any = None
    ) -> Any:
    resolved_state = state if state is not None else InfraRunState.PENDING
    rtnval = provisioning_runs_routes.infra_service.InfraRunView(
        run_id=run_id,
        project_id=project_id,
        environment_id="env-1",
        driver_name="terraform",
        action=InfraAction.PLAN,
        state=resolved_state,
        layer5_run_id=None,
        actor_id=None,
        actor_role_set=(),
        inputs={"workspace": "default"},
        inputs_canonical_sha256="a" * 64,
        plan_summary=None,
        plan_artifact_ref=None,
        plan_diff_digest_sha256="",
        plan_issued_at=None,
        replay_of=None,
        output_digest_sha256="",
        failing_guard_rule_id=None,
        started_at=None,
        finished_at=None,
        final_state_reason="",
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_provisioning_runs_routes_attaches_three_endpoints():
    """
    **Feature: 6-infra-orchestration PR p20b**
    **Property: register_provisioning_runs_routes attaches the
    three method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    provisioning_runs_routes.register_provisioning_runs_routes(
        app=app, version_prefix="/api/v1",
    )
    expected_pairs = (
        ("/api/v1/projects/{project_id}/provisioning-runs", ("POST",)),
        ("/api/v1/projects/{project_id}/provisioning-runs", ("GET",)),
        (
            "/api/v1/projects/{project_id}/provisioning-runs/{run_id}",
            ("GET",),
        ),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# GET /provisioning-runs -- auth + session sweep
# ---------------------------------------------------------------------------


def test_list_returns_503_when_session_missing():
    """
    **Feature: 6-infra-orchestration PR p20b**
    **Property: GET provisioning-runs returns 503 when no
    db_session is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/provisioning-runs",
        path_params={"project_id": "proj-1"},
        db_session=None,
    )
    response = provisioning_runs_routes.handle_list_provisioning_runs(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_list_returns_401_when_no_principal():
    """
    **Feature: 6-infra-orchestration PR p20b**
    **Property: GET provisioning-runs returns 401 when no
    AuthPrincipal is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/provisioning-runs",
        path_params={"project_id": "proj-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = provisioning_runs_routes.handle_list_provisioning_runs(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_returns_403_when_permission_denied():
    """
    **Feature: 6-infra-orchestration PR p20b**
    **Property: GET provisioning-runs returns 403 when the
    principal does not hold system:provisioning.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/provisioning-runs",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = provisioning_runs_routes.handle_list_provisioning_runs(
            request,
        )
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(
        body["required_permission"], "system:provisioning.read",
    )
    return


def test_list_returns_404_when_project_missing():
    """
    **Feature: 6-infra-orchestration PR p20b**
    **Property: GET provisioning-runs returns 404 when the
    project does not exist.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=None)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-x/provisioning-runs",
            path_params={"project_id": "proj-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = provisioning_runs_routes.handle_list_provisioning_runs(
            request,
        )
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
    **Feature: 6-infra-orchestration PR p20b**
    **Property: GET provisioning-runs returns a {items, meta}
    page with ProvisioningRun-shaped items.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    list_patch = create_module_patch(
        provisioning_runs_routes.infra_service,
        "list_infra_runs_for_project",
    )
    list_mock = list_patch.activate()
    list_mock.configure(
        side_effect=lambda **kwargs: [_make_run_view(run_id="run-1")],
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/provisioning-runs",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            query={"page": "1", "per_page": "10"},
        )
        response = provisioning_runs_routes.handle_list_provisioning_runs(
            request,
        )
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
    **Feature: 6-infra-orchestration PR p20b**
    **Property: GET provisioning-runs filters the returned page
    by the state query param.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    list_patch = create_module_patch(
        provisioning_runs_routes.infra_service,
        "list_infra_runs_for_project",
    )
    list_mock = list_patch.activate()
    list_mock.configure(
        side_effect=lambda **kwargs: [
            _make_run_view(run_id="run-pending", state=InfraRunState.PENDING),
            _make_run_view(run_id="run-failed", state=InfraRunState.FAILED),
        ],
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/provisioning-runs",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            query={"state": "failed"},
        )
        response = provisioning_runs_routes.handle_list_provisioning_runs(
            request,
        )
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
# POST /provisioning-runs (trigger)
# ---------------------------------------------------------------------------


def test_trigger_returns_422_on_missing_body():
    """
    **Feature: 6-infra-orchestration PR p20b**
    **Property: POST provisioning-runs returns 422 when body is
    missing.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/provisioning-runs",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body=None,
        )
        response = provisioning_runs_routes.handle_trigger_provisioning_run(
            request,
        )
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_trigger_returns_422_on_missing_environment_id():
    """
    **Feature: 6-infra-orchestration PR p20b**
    **Property: POST provisioning-runs returns 422 when
    environment_id is absent.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/provisioning-runs",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"driver_name": "terraform", "action": "plan"},
        )
        response = provisioning_runs_routes.handle_trigger_provisioning_run(
            request,
        )
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal("environment_id" in body["missing_fields"], True)
    return


def test_trigger_returns_422_on_unknown_action():
    """
    **Feature: 6-infra-orchestration PR p20b**
    **Property: POST provisioning-runs returns 422 when the
    action is not a known InfraAction value.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/provisioning-runs",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "environment_id": "env-1",
                "driver_name": "terraform",
                "action": "bogus",
            },
        )
        response = provisioning_runs_routes.handle_trigger_provisioning_run(
            request,
        )
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["action"], "bogus")
    return


def test_trigger_returns_422_when_driver_unknown():
    """
    **Feature: 6-infra-orchestration PR p20b**
    **Property: POST provisioning-runs returns 422 when the
    driver has no registered factory.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    cand_patch = _patch_eligible_candidates()
    trigger_patch = create_module_patch(
        provisioning_runs_routes.infra_service, "trigger_run",
    )
    trigger_mock = trigger_patch.activate()

    def _raise(**kwargs):
        raise InfraDriverUnknownError("no driver")

    trigger_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/provisioning-runs",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "environment_id": "env-1",
                "driver_name": "bogus",
                "action": "plan",
            },
        )
        response = provisioning_runs_routes.handle_trigger_provisioning_run(
            request,
        )
    finally:
        trigger_patch.deactivate()
        cand_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["driver_name"], "bogus")
    return


def test_trigger_returns_202_on_happy_path():
    """
    **Feature: 6-infra-orchestration PR p20b**
    **Property: POST provisioning-runs returns 202 with the
    ProvisioningRun shape on a valid body.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    cand_patch = _patch_eligible_candidates()
    trigger_patch = create_module_patch(
        provisioning_runs_routes.infra_service, "trigger_run",
    )
    trigger_mock = trigger_patch.activate()
    trigger_mock.configure(
        side_effect=lambda **kwargs: _make_run_view(
            run_id="run-new", state=InfraRunState.RUNNING,
        ),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/provisioning-runs",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "environment_id": "env-1",
                "driver_name": "terraform",
                "action": "plan",
                "driver_inputs": {"workspace": "default"},
            },
        )
        response = provisioning_runs_routes.handle_trigger_provisioning_run(
            request,
        )
    finally:
        trigger_patch.deactivate()
        cand_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 202)
    body = _decode_body(response)
    testbase.assert_equal(body["run_id"], "run-new")
    testbase.assert_equal(body["action"], "plan")
    testbase.assert_equal(body["state"], "running")
    return


def test_trigger_returns_409_when_no_eligible_pod():
    """
    **Feature: 6-infra-orchestration PR p20l**
    **Property: POST provisioning-runs returns 409 when the
    project has no enrolled / REGISTERED pod to dispatch to.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    cand_patch = _patch_eligible_candidates(candidates=[])
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/provisioning-runs",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "environment_id": "env-1",
                "driver_name": "terraform",
                "action": "plan",
            },
        )
        response = provisioning_runs_routes.handle_trigger_provisioning_run(
            request,
        )
    finally:
        cand_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["reason"], "no_eligible_pod")
    return


def test_trigger_returns_403_when_permission_denied():
    """
    **Feature: 6-infra-orchestration PR p20b**
    **Property: POST provisioning-runs returns 403 when the
    principal does not hold system:provisioning.create.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/provisioning-runs",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "environment_id": "env-1",
                "driver_name": "terraform",
                "action": "plan",
            },
        )
        response = provisioning_runs_routes.handle_trigger_provisioning_run(
            request,
        )
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(
        body["required_permission"], "system:provisioning.create",
    )
    return


# ---------------------------------------------------------------------------
# GET /provisioning-runs/{run_id}
# ---------------------------------------------------------------------------


def test_read_returns_404_when_run_missing():
    """
    **Feature: 6-infra-orchestration PR p20b**
    **Property: GET provisioning-runs/{id} returns 404 when the
    run is not found.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        provisioning_runs_routes.infra_service, "get_infra_run",
    )
    get_mock = get_patch.activate()

    def _raise(**kwargs):
        raise InfraRunNotFoundError("missing")

    get_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/provisioning-runs/run-x",
            path_params={"project_id": "proj-1", "run_id": "run-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = provisioning_runs_routes.handle_read_provisioning_run(
            request,
        )
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["run_id"], "run-x")
    return


def test_read_returns_200_on_happy_path():
    """
    **Feature: 6-infra-orchestration PR p20b**
    **Property: GET provisioning-runs/{id} returns 200 with the
    ProvisioningRun shape.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        provisioning_runs_routes.infra_service, "get_infra_run",
    )
    get_mock = get_patch.activate()
    get_mock.configure(
        side_effect=lambda **kwargs: _make_run_view(run_id="run-7"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/provisioning-runs/run-7",
            path_params={"project_id": "proj-1", "run_id": "run-7"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = provisioning_runs_routes.handle_read_provisioning_run(
            request,
        )
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
    **Feature: 6-infra-orchestration PR p20b**
    **Property: GET provisioning-runs/{id} returns 404 when the
    run belongs to a different project.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        provisioning_runs_routes.infra_service, "get_infra_run",
    )
    get_mock = get_patch.activate()
    get_mock.configure(
        side_effect=lambda **kwargs: _make_run_view(
            run_id="run-9", project_id="other-proj",
        ),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/provisioning-runs/run-9",
            path_params={"project_id": "proj-1", "run_id": "run-9"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = provisioning_runs_routes.handle_read_provisioning_run(
            request,
        )
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return
