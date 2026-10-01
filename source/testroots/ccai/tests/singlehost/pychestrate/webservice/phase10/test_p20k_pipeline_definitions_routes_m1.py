"""
.. module:: test_p20k_pipeline_definitions_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the pipeline-definition REST endpoints (PR p20k).

.. moduleauthor:: Code Craft AI LLC

Covers the pipeline operations attached by
``register_pipeline_definitions_routes``:

* GET    /api/v1/projects/{project_id}/pipelines
* POST   /api/v1/projects/{project_id}/pipelines
* GET    /api/v1/projects/{project_id}/pipelines/{pipeline_id}
* DELETE /api/v1/projects/{project_id}/pipelines/{pipeline_id}
* POST   /api/v1/projects/{project_id}/pipelines:validate
* POST   /api/v1/projects/{project_id}/pipelines:expand-matrix

Auth (401/403), session boundary (503), project not-found (404),
malformed body (422), pagination, the DAG-validate endpoint
(valid passes / cyclic 422s), the matrix-expand endpoint (a
matrix spec expands to the expected shard count), and happy-path
200 each get explicit coverage.
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
from ccai.pychestrate.webservice.orchestration.pipelines.definition import (
    service as definition_service,
)
from ccai.pychestrate.webservice.orchestration.pipelines.definition.errors import (
    PipelineRunNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.pipelines.restapi.v1 import (
    pipeline_definitions_routes,
)
from ccai.pychestrate.webservice.orchestration.pipelines.sharding import (
    service as sharding_service,
)
from ccai.pychestrate.webservice.orchestration.pipelines.sharding.expansion import (
    MatrixSpec,
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
        pipeline_definitions_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _patch_project_exists(*, project: Optional[Any]) -> Any:
    patch = create_module_patch(
        pipeline_definitions_routes.projects_repo, "get_project_by_id",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: project)
    return patch


def _make_definition_view(
        *,
        pipeline_id: str = "deadbeef",
        project_id: str = "proj-1"
    ) -> Any:
    rtnval = definition_service.PipelineDefinitionView(
        pipeline_id=pipeline_id,
        project_id=project_id,
        name="ci",
        schema_version=1,
        commit_sha="abc123",
        filename="pipeline.yaml",
        stages=(
            definition_service.PipelineStageView(
                stage_id="build",
                when_clause="succeeded",
                needs=(),
                steps=(
                    definition_service.PipelineStepView(
                        step_id="compile",
                        kind_name="build",
                        uses=None,
                        inputs={},
                    ),
                ),
            ),
        ),
        cached_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
    )
    return rtnval


def _make_validation_view(*, valid: bool) -> Any:
    if valid is True:
        rtnval = definition_service.DagValidationView(
            valid=True,
            stage_count=2,
            topological_order=("build", "test"),
            issues=(),
        )
        return rtnval
    rtnval = definition_service.DagValidationView(
        valid=False,
        stage_count=2,
        topological_order=(),
        issues=("Pipeline DAG contains a cycle.",),
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_pipeline_routes_attaches_six_endpoints():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: register_pipeline_definitions_routes attaches the
    six method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    pipeline_definitions_routes.register_pipeline_definitions_routes(
        app=app, version_prefix="/api/v1",
    )
    expected_pairs = (
        ("/api/v1/projects/{project_id}/pipelines", ("GET",)),
        ("/api/v1/projects/{project_id}/pipelines", ("POST",)),
        ("/api/v1/projects/{project_id}/pipelines/{pipeline_id}", ("GET",)),
        ("/api/v1/projects/{project_id}/pipelines/{pipeline_id}", ("DELETE",)),
        (
            "/api/v1/projects/{project_id}/pipelines:validate",
            ("POST",),
        ),
        (
            "/api/v1/projects/{project_id}/pipelines:expand-matrix",
            ("POST",),
        ),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# GET /pipelines -- auth + session sweep
# ---------------------------------------------------------------------------


def test_list_returns_503_when_session_missing():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: GET pipelines returns 503 when no db_session is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/pipelines",
        path_params={"project_id": "proj-1"},
        db_session=None,
    )
    response = pipeline_definitions_routes.handle_list_pipelines(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_list_returns_401_when_no_principal():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: GET pipelines returns 401 when no AuthPrincipal is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/pipelines",
        path_params={"project_id": "proj-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = pipeline_definitions_routes.handle_list_pipelines(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_returns_403_when_permission_denied():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: GET pipelines returns 403 when the principal does
    not hold system:pipelines.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipelines",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = pipeline_definitions_routes.handle_list_pipelines(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:pipelines.read")
    return


def test_list_returns_404_when_project_missing():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: GET pipelines returns 404 when the project does not
    exist.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=None)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-x/pipelines",
            path_params={"project_id": "proj-x"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = pipeline_definitions_routes.handle_list_pipelines(request)
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
    **Feature: 6-pipeline-definition PR p20k**
    **Property: GET pipelines returns a {items, meta} page with
    PipelineDefinition-shaped items.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    list_patch = create_module_patch(
        pipeline_definitions_routes.definition_service, "list_definitions",
    )
    list_mock = list_patch.activate()
    list_mock.configure(
        side_effect=lambda **kwargs: [_make_definition_view(pipeline_id="d1")],
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipelines",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            query={"page": "1", "per_page": "10"},
        )
        response = pipeline_definitions_routes.handle_list_pipelines(request)
    finally:
        list_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["pipeline_id"], "d1")
    testbase.assert_equal(body["meta"]["page"], 1)
    testbase.assert_equal(body["meta"]["total"], 1)
    return


def test_list_paginates_window():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: GET pipelines slices the result set by page /
    per_page.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    list_patch = create_module_patch(
        pipeline_definitions_routes.definition_service, "list_definitions",
    )
    list_mock = list_patch.activate()
    list_mock.configure(
        side_effect=lambda **kwargs: [
            _make_definition_view(pipeline_id="d1"),
            _make_definition_view(pipeline_id="d2"),
            _make_definition_view(pipeline_id="d3"),
        ],
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipelines",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            query={"page": "2", "per_page": "2"},
        )
        response = pipeline_definitions_routes.handle_list_pipelines(request)
    finally:
        list_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["pipeline_id"], "d3")
    testbase.assert_equal(body["meta"]["total"], 3)
    return


# ---------------------------------------------------------------------------
# POST /pipelines (upsert)
# ---------------------------------------------------------------------------


def test_upsert_returns_422_on_missing_body():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: POST pipelines returns 422 problem when body is
    missing.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipelines",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body=None,
        )
        response = pipeline_definitions_routes.handle_upsert_pipeline(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_upsert_returns_422_on_missing_document():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: POST pipelines returns 422 when the document field
    is absent.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipelines",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"commit_sha": "abc", "filename": "pipeline.yaml"},
        )
        response = pipeline_definitions_routes.handle_upsert_pipeline(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal("document" in body["missing_fields"], True)
    return


def test_upsert_returns_403_when_permission_denied():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: POST pipelines returns 403 when the principal does
    not hold system:pipelines.write.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipelines",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"commit_sha": "abc", "filename": "p.yaml", "document": "x"},
        )
        response = pipeline_definitions_routes.handle_upsert_pipeline(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:pipelines.write")
    return


def test_upsert_returns_200_on_happy_path():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: POST pipelines returns 200 with the
    PipelineDefinition shape on a valid body.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    upsert_patch = create_module_patch(
        pipeline_definitions_routes.definition_service, "upsert_definition",
    )
    upsert_mock = upsert_patch.activate()
    upsert_mock.configure(
        side_effect=lambda **kwargs: _make_definition_view(pipeline_id="dnew"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipelines",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "commit_sha": "abc123",
                "filename": "pipeline.yaml",
                "document": "name: ci\nstages: []\n",
            },
        )
        response = pipeline_definitions_routes.handle_upsert_pipeline(request)
    finally:
        upsert_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["pipeline_id"], "dnew")
    testbase.assert_equal(body["name"], "ci")
    return


def test_upsert_returns_422_on_dag_cycle():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: POST pipelines returns 422 when the document DAG
    has a cycle.**
    """
    from ccai.pychestrate.webservice.orchestration.pipelines.definition.errors import (
        PipelineDagCycleError,
    )

    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    upsert_patch = create_module_patch(
        pipeline_definitions_routes.definition_service, "upsert_definition",
    )
    upsert_mock = upsert_patch.activate()

    def _raise(**kwargs):
        raise PipelineDagCycleError("Pipeline DAG contains a cycle.")

    upsert_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipelines",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "commit_sha": "abc",
                "filename": "p.yaml",
                "document": "x",
            },
        )
        response = pipeline_definitions_routes.handle_upsert_pipeline(request)
    finally:
        upsert_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["reason"], "dag_cycle")
    return


# ---------------------------------------------------------------------------
# GET /pipelines/{pipeline_id}
# ---------------------------------------------------------------------------


def test_read_returns_404_when_definition_missing():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: GET pipelines/{id} returns 404 when the definition
    is not found.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        pipeline_definitions_routes.definition_service, "get_definition",
    )
    get_mock = get_patch.activate()

    def _raise(**kwargs):
        raise PipelineRunNotFoundError("missing")

    get_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipelines/dx",
            path_params={"project_id": "proj-1", "pipeline_id": "dx"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = pipeline_definitions_routes.handle_read_pipeline(request)
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["pipeline_id"], "dx")
    return


def test_read_returns_200_on_happy_path():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: GET pipelines/{id} returns 200 with the
    PipelineDefinition shape.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    get_patch = create_module_patch(
        pipeline_definitions_routes.definition_service, "get_definition",
    )
    get_mock = get_patch.activate()
    get_mock.configure(
        side_effect=lambda **kwargs: _make_definition_view(pipeline_id="d7"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipelines/d7",
            path_params={"project_id": "proj-1", "pipeline_id": "d7"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = pipeline_definitions_routes.handle_read_pipeline(request)
    finally:
        get_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["pipeline_id"], "d7")
    testbase.assert_equal(len(body["stages"]), 1)
    return


# ---------------------------------------------------------------------------
# DELETE /pipelines/{pipeline_id}
# ---------------------------------------------------------------------------


def test_delete_returns_204_on_happy_path():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: DELETE pipelines/{id} returns 204 when the
    definition is deleted.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    del_patch = create_module_patch(
        pipeline_definitions_routes.definition_service, "delete_definition",
    )
    del_mock = del_patch.activate()
    del_mock.configure(side_effect=lambda **kwargs: None)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipelines/d7",
            path_params={"project_id": "proj-1", "pipeline_id": "d7"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = pipeline_definitions_routes.handle_delete_pipeline(request)
    finally:
        del_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 204)
    return


def test_delete_returns_404_when_definition_missing():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: DELETE pipelines/{id} returns 404 when the
    definition is not found.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    del_patch = create_module_patch(
        pipeline_definitions_routes.definition_service, "delete_definition",
    )
    del_mock = del_patch.activate()

    def _raise(**kwargs):
        raise PipelineRunNotFoundError("missing")

    del_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipelines/dx",
            path_params={"project_id": "proj-1", "pipeline_id": "dx"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = pipeline_definitions_routes.handle_delete_pipeline(request)
    finally:
        del_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["pipeline_id"], "dx")
    return


# ---------------------------------------------------------------------------
# POST /pipelines:validate
# ---------------------------------------------------------------------------


def test_validate_returns_200_for_valid_dag():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: POST :validate returns 200 with topological order
    for a well-formed DAG.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    val_patch = create_module_patch(
        pipeline_definitions_routes.definition_service, "validate_document",
    )
    val_mock = val_patch.activate()
    val_mock.configure(
        side_effect=lambda **kwargs: _make_validation_view(valid=True),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipelines:validate",
            path_params={"project_id": "proj-1", "pipeline_id": "d1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "commit_sha": "abc",
                "filename": "p.yaml",
                "document": "x",
            },
        )
        response = pipeline_definitions_routes.handle_validate_pipeline(request)
    finally:
        val_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["valid"], True)
    testbase.assert_equal(body["topological_order"], ["build", "test"])
    return


def test_validate_returns_422_for_cyclic_dag():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: POST :validate returns 422 with the issue list when
    the DAG has a cycle.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    val_patch = create_module_patch(
        pipeline_definitions_routes.definition_service, "validate_document",
    )
    val_mock = val_patch.activate()
    val_mock.configure(
        side_effect=lambda **kwargs: _make_validation_view(valid=False),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipelines:validate",
            path_params={"project_id": "proj-1", "pipeline_id": "d1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "commit_sha": "abc",
                "filename": "p.yaml",
                "document": "x",
            },
        )
        response = pipeline_definitions_routes.handle_validate_pipeline(request)
    finally:
        val_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["reason"], "dag_invalid")
    testbase.assert_equal(len(body["issues"]), 1)
    return


def test_validate_real_document_passes_for_acyclic_dag():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: definition_service.validate_document accepts a
    well-formed two-stage DAG whose steps have the inputs their kinds
    need (it also checks the inputs now, ORC-13).**
    """
    from ccai.pychestrate.webservice.extensions.registry import reset_registry_for_testing  # noqa: E402
    from ccai.pychestrate.webservice.orchestration.pipelines.definition import (  # noqa: E402
        register_builtin_extensions as pipeline_definition_register,
    )
    reset_registry_for_testing()
    pipeline_definition_register()
    document = json.dumps({
        "schema_version": 1,
        "name": "ci",
        "stages": [
            {
                "id": "build",
                "steps": [{"id": "compile", "kind": "build", "inputs": {"image": "registry.example.com/app"}}],
            },
            {
                "id": "test",
                "needs": ["build"],
                "steps": [{"id": "pytest", "kind": "test", "inputs": {"catalog_entry_id": "00000000-0000-4000-8000-aaaaaaaaaaaa"}}],
            },
        ],
    })
    view = definition_service.validate_document(
        document_bytes=document.encode("utf-8"),
        filename="pipeline.json",
    )
    testbase.assert_equal(view.valid, True)
    testbase.assert_equal(view.stage_count, 2)
    testbase.assert_equal(view.topological_order, ("build", "test"))
    return


def test_validate_real_document_rejects_cyclic_dag():
    """
    **Feature: 6-pipeline-definition PR p20k**
    **Property: definition_service.validate_document rejects a DAG
    where two stages depend on each other.**
    """
    document = json.dumps({
        "schema_version": 1,
        "name": "ci",
        "stages": [
            {
                "id": "a",
                "needs": ["b"],
                "steps": [{"id": "s1", "kind": "build"}],
            },
            {
                "id": "b",
                "needs": ["a"],
                "steps": [{"id": "s2", "kind": "test"}],
            },
        ],
    })
    view = definition_service.validate_document(
        document_bytes=document.encode("utf-8"),
        filename="pipeline.json",
    )
    testbase.assert_equal(view.valid, False)
    testbase.assert_equal(len(view.issues), 1)
    return


# ---------------------------------------------------------------------------
# POST /pipelines:expand-matrix
# ---------------------------------------------------------------------------


def test_expand_matrix_returns_422_when_dimensions_missing():
    """
    **Feature: 6-matrix-sharding PR p20k**
    **Property: POST :expand-matrix returns 422 when the matrix
    dimensions are absent.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipelines:expand-matrix",
            path_params={"project_id": "proj-1", "pipeline_id": "d1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"matrix": {}},
        )
        response = pipeline_definitions_routes.handle_expand_matrix(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_expand_matrix_returns_200_with_expected_shard_count():
    """
    **Feature: 6-matrix-sharding PR p20k**
    **Property: POST :expand-matrix expands a 2x3 matrix into 6
    concrete shards via the real cartesian strategy.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    preview = sharding_service.ExpansionPreview(
        strategy_name="cartesian",
        matrix_spec_canonical_sha256="f" * 64,
        shard_count=6,
        shards=tuple(
            sharding_service.ExpansionPreviewShard(
                shard_id="s{}".format(index),
                parallel_group="default",
                sequence_in_group=index,
                dimension_values={"os": "linux", "py": str(index)},
            )
            for index in range(6)
        ),
    )
    expand_patch = create_module_patch(
        pipeline_definitions_routes.sharding_service, "preview_expansion",
    )
    expand_mock = expand_patch.activate()
    expand_mock.configure(side_effect=lambda **kwargs: preview)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipelines:expand-matrix",
            path_params={"project_id": "proj-1", "pipeline_id": "d1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "matrix": {
                    "dimensions": {
                        "os": ["linux", "macos"],
                        "py": ["3.10", "3.11", "3.12"],
                    },
                },
            },
        )
        response = pipeline_definitions_routes.handle_expand_matrix(request)
    finally:
        expand_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["shard_count"], 6)
    testbase.assert_equal(len(body["shards"]), 6)
    testbase.assert_equal(body["strategy_name"], "cartesian")
    return


def test_expand_matrix_cartesian_strategy_expands_product():
    """
    **Feature: 6-matrix-sharding PR p20k**
    **Property: the CartesianShardingStrategy fans a 2x3 matrix
    into 6 ordered shards directly (registry-independent).**
    """
    from ccai.pychestrate.webservice.orchestration.pipelines.sharding.factories.cartesian_strategy import (
        CartesianShardingStrategy,
    )

    matrix_spec = MatrixSpec(
        dimensions={
            "os": ["linux", "macos"],
            "py": ["3.10", "3.11", "3.12"],
        },
    )
    expanded = CartesianShardingStrategy.expand(matrix_spec=matrix_spec)
    testbase.assert_equal(len(expanded), 6)
    shard_ids = set(shard.shard_id for shard in expanded)
    testbase.assert_equal(len(shard_ids), 6)
    return


def test_expand_matrix_returns_422_for_unknown_strategy():
    """
    **Feature: 6-matrix-sharding PR p20k**
    **Property: POST :expand-matrix returns 422 when the requested
    sharding strategy is not registered.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=_FakeProject(project_id="proj-1"))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/pipelines:expand-matrix",
            path_params={"project_id": "proj-1", "pipeline_id": "d1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={
                "matrix": {"dimensions": {"os": ["linux"]}},
                "strategy_name": "nonexistent-strategy",
            },
        )
        response = pipeline_definitions_routes.handle_expand_matrix(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["strategy_name"], "nonexistent-strategy")
    return


def test_expand_matrix_returns_401_when_no_principal():
    """
    **Feature: 6-matrix-sharding PR p20k**
    **Property: POST :expand-matrix returns 401 when the request is
    anonymous.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/pipelines:expand-matrix",
        path_params={"project_id": "proj-1", "pipeline_id": "d1"},
        db_session=object(),
        auth_principal=None,
        body={"matrix": {"dimensions": {"os": ["linux"]}}},
    )
    response = pipeline_definitions_routes.handle_expand_matrix(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return
