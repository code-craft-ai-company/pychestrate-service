"""
.. module:: test_p21c_guards_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the blast-radius-guard REST endpoints (PR p21c).

.. moduleauthor:: Automation Mojo LLC

Covers the blast-radius-guard operations attached by
``register_guards_routes``:

* GET    /api/v1/projects/{project_id}/blast-radius-guards
* POST   /api/v1/projects/{project_id}/blast-radius-guards
* GET    /api/v1/projects/{project_id}/blast-radius-guards/{guard_id}
* PATCH  /api/v1/projects/{project_id}/blast-radius-guards/{guard_id}
* DELETE /api/v1/projects/{project_id}/blast-radius-guards/{guard_id}
* POST   /api/v1/projects/{project_id}/blast-radius-guards:evaluate

Auth (401/403), session boundary (503), project not-found (404),
malformed body (422), pagination, the evaluate action, and
happy-path 2xx each get explicit coverage.
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
from automojo.pychestrate.webservice.orchestration.infra.guards.errors import (
    GuardAttachmentNotFoundError,
    GuardEnvironmentNotFoundError,
    GuardRuleUnknownError,
)
from automojo.pychestrate.webservice.orchestration.infra.guards.service import (
    GuardAttachmentView,
    GuardTrace,
    GuardTraceEntry,
)
from automojo.pychestrate.webservice.orchestration.infra.guards.factories.rule_protocol import (
    GuardVerdict,
)
from automojo.pychestrate.webservice.orchestration.infra.restapi.v1 import (
    guards_routes,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_check_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(
        guards_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _patch_project_exists(*, project: Optional[Any]) -> Any:
    patch = create_module_patch(
        guards_routes.projects_repo, "get_project_by_id",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: project)
    return patch


def _make_guard_view(
        *,
        project_id: str = "proj-1",
        environment_id: str = "env-1",
        rule_id: str = "max-concurrent",
        enabled: bool = True
    ) -> Any:
    now = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
    rtnval = GuardAttachmentView(
        project_id=project_id,
        environment_id=environment_id,
        rule_id=rule_id,
        enabled=enabled,
        added_by="user-1",
        added_at=now,
        updated_at=now,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_guards_routes_attaches_six_endpoints():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: register_guards_routes attaches the six
    method+path pairs from the OpenAPI spec.**
    """
    app = _FakeApp()
    guards_routes.register_guards_routes(app=app, version_prefix="/api/v1")
    expected_pairs = (
        ("/api/v1/projects/{project_id}/blast-radius-guards", ("GET",)),
        ("/api/v1/projects/{project_id}/blast-radius-guards", ("POST",)),
        (
            "/api/v1/projects/{project_id}/blast-radius-guards:evaluate",
            ("POST",),
        ),
        (
            "/api/v1/projects/{project_id}/blast-radius-guards/{guard_id}",
            ("GET",),
        ),
        (
            "/api/v1/projects/{project_id}/blast-radius-guards/{guard_id}",
            ("PATCH",),
        ),
        (
            "/api/v1/projects/{project_id}/blast-radius-guards/{guard_id}",
            ("DELETE",),
        ),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# GET list -- auth + session sweep
# ---------------------------------------------------------------------------


def test_list_returns_503_when_session_missing():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: GET guards returns 503 when no db_session is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/blast-radius-guards",
        path_params={"project_id": "proj-1"},
        db_session=None,
    )
    response = guards_routes.handle_list_guards(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_list_returns_401_when_no_principal():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: GET guards returns 401 when no AuthPrincipal bound.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/proj-1/blast-radius-guards",
        path_params={"project_id": "proj-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = guards_routes.handle_list_guards(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_list_returns_403_when_permission_denied():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: GET guards returns 403 when the principal lacks
    system:guards.read.**
    """
    perm_patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/blast-radius-guards",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = guards_routes.handle_list_guards(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:guards.read")
    return


def test_list_returns_404_when_project_missing():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: GET guards returns 404 when the project does not
    exist.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(project=None)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-x/blast-radius-guards",
            path_params={"project_id": "proj-x"},
            query={"environment_id": "env-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = guards_routes.handle_list_guards(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    return


def test_list_returns_400_when_environment_id_missing():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: GET guards returns 400 when the required
    environment_id query param is absent.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/blast-radius-guards",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = guards_routes.handle_list_guards(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    return


def test_list_returns_page_envelope_on_happy_path():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: GET guards returns an {items, meta} page with
    BlastRadiusGuard-shaped items.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    list_patch = create_module_patch(
        guards_routes.guards_service, "list_attachments_for_environment",
    )
    list_mock = list_patch.activate()
    list_mock.configure(
        side_effect=lambda **kwargs: [_make_guard_view()],
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/blast-radius-guards",
            path_params={"project_id": "proj-1"},
            query={"environment_id": "env-1", "page": "1", "per_page": "10"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = guards_routes.handle_list_guards(request)
    finally:
        list_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["items"]), 1)
    testbase.assert_equal(body["items"][0]["guard_id"], "env-1.max-concurrent")
    testbase.assert_equal(body["meta"]["total"], 1)
    return


# ---------------------------------------------------------------------------
# POST create
# ---------------------------------------------------------------------------


def test_create_returns_422_on_missing_body():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: POST guards returns 422 when the body is missing.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/blast-radius-guards",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body=None,
        )
        response = guards_routes.handle_create_guard(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_create_returns_422_when_rule_unknown():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: POST guards returns 422 when the guard facade
    raises GuardRuleUnknownError.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    set_patch = create_module_patch(
        guards_routes.guards_service, "set_attachment",
    )
    set_mock = set_patch.activate()

    def _raise(**kwargs: Any) -> Any:
        raise GuardRuleUnknownError("no such rule")

    set_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/blast-radius-guards",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"environment_id": "env-1", "rule_id": "bogus"},
        )
        response = guards_routes.handle_create_guard(request)
    finally:
        set_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    return


def test_create_returns_201_on_happy_path():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: POST guards returns 201 with the created guard.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    set_patch = create_module_patch(
        guards_routes.guards_service, "set_attachment",
    )
    set_mock = set_patch.activate()
    set_mock.configure(side_effect=lambda **kwargs: _make_guard_view())
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/blast-radius-guards",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"environment_id": "env-1", "rule_id": "max-concurrent"},
        )
        response = guards_routes.handle_create_guard(request)
    finally:
        set_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["rule_id"], "max-concurrent")
    return


# ---------------------------------------------------------------------------
# GET read
# ---------------------------------------------------------------------------


def test_read_returns_404_on_malformed_guard_id():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: GET guard returns 404 when the guard_id has no
    environment.rule separator.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/blast-radius-guards/bogus",
            path_params={"project_id": "proj-1", "guard_id": "bogus"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = guards_routes.handle_read_guard(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return


def test_read_returns_200_on_happy_path():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: GET guard returns 200 with the matched guard.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    list_patch = create_module_patch(
        guards_routes.guards_service, "list_attachments_for_environment",
    )
    list_mock = list_patch.activate()
    list_mock.configure(side_effect=lambda **kwargs: [_make_guard_view()])
    try:
        request = _FakeRequest(
            path=(
                "/api/v1/projects/proj-1/blast-radius-guards/"
                "env-1.max-concurrent"
            ),
            path_params={
                "project_id": "proj-1",
                "guard_id": "env-1.max-concurrent",
            },
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = guards_routes.handle_read_guard(request)
    finally:
        list_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["rule_id"], "max-concurrent")
    return


# ---------------------------------------------------------------------------
# PATCH
# ---------------------------------------------------------------------------


def test_patch_returns_200_when_toggling_enabled():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: PATCH guard returns 200 with the toggled guard.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    list_patch = create_module_patch(
        guards_routes.guards_service, "list_attachments_for_environment",
    )
    list_mock = list_patch.activate()
    list_mock.configure(side_effect=lambda **kwargs: [_make_guard_view()])
    set_patch = create_module_patch(
        guards_routes.guards_service, "set_attachment",
    )
    set_mock = set_patch.activate()
    set_mock.configure(
        side_effect=lambda **kwargs: _make_guard_view(enabled=False),
    )
    try:
        request = _FakeRequest(
            path=(
                "/api/v1/projects/proj-1/blast-radius-guards/"
                "env-1.max-concurrent"
            ),
            path_params={
                "project_id": "proj-1",
                "guard_id": "env-1.max-concurrent",
            },
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"enabled": False},
        )
        response = guards_routes.handle_patch_guard(request)
    finally:
        set_patch.deactivate()
        list_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["enabled"], False)
    return


def test_patch_returns_422_when_enabled_missing():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: PATCH guard returns 422 when the enabled flag is
    absent.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    list_patch = create_module_patch(
        guards_routes.guards_service, "list_attachments_for_environment",
    )
    list_mock = list_patch.activate()
    list_mock.configure(side_effect=lambda **kwargs: [_make_guard_view()])
    try:
        request = _FakeRequest(
            path=(
                "/api/v1/projects/proj-1/blast-radius-guards/"
                "env-1.max-concurrent"
            ),
            path_params={
                "project_id": "proj-1",
                "guard_id": "env-1.max-concurrent",
            },
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={},
        )
        response = guards_routes.handle_patch_guard(request)
    finally:
        list_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    return


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


def test_delete_returns_204_on_happy_path():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: DELETE guard returns 204 on a successful disable.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    disable_patch = create_module_patch(
        guards_routes.guards_service, "disable_attachment",
    )
    disable_mock = disable_patch.activate()
    disable_mock.configure(side_effect=lambda **kwargs: _make_guard_view())
    try:
        request = _FakeRequest(
            path=(
                "/api/v1/projects/proj-1/blast-radius-guards/"
                "env-1.max-concurrent"
            ),
            path_params={
                "project_id": "proj-1",
                "guard_id": "env-1.max-concurrent",
            },
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = guards_routes.handle_delete_guard(request)
    finally:
        disable_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 204)
    return


def test_delete_returns_404_when_attachment_missing():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: DELETE guard returns 404 when the facade raises
    GuardAttachmentNotFoundError.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    disable_patch = create_module_patch(
        guards_routes.guards_service, "disable_attachment",
    )
    disable_mock = disable_patch.activate()

    def _raise(**kwargs: Any) -> Any:
        raise GuardAttachmentNotFoundError("no attachment")

    disable_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path=(
                "/api/v1/projects/proj-1/blast-radius-guards/"
                "env-1.max-concurrent"
            ),
            path_params={
                "project_id": "proj-1",
                "guard_id": "env-1.max-concurrent",
            },
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = guards_routes.handle_delete_guard(request)
    finally:
        disable_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return


# ---------------------------------------------------------------------------
# POST :evaluate
# ---------------------------------------------------------------------------


def test_evaluate_returns_422_when_action_missing():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: POST guards:evaluate returns 422 when the action
    field is absent.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/blast-radius-guards:evaluate",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"environment_id": "env-1"},
        )
        response = guards_routes.handle_evaluate_guards(request)
    finally:
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    return


def test_evaluate_returns_200_with_trace():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: POST guards:evaluate returns 200 with the per-rule
    verdict trace.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    explain_patch = create_module_patch(
        guards_routes.guards_service, "explain",
    )
    explain_mock = explain_patch.activate()
    trace = GuardTrace(
        allowed=False,
        failing_rule_id="max-concurrent",
        entries=(
            GuardTraceEntry(
                rule_id="max-concurrent",
                verdict=GuardVerdict.DENY,
                reason="over limit",
            ),
        ),
    )
    explain_mock.configure(side_effect=lambda **kwargs: trace)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/blast-radius-guards:evaluate",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"environment_id": "env-1", "action": "scale-up"},
        )
        response = guards_routes.handle_evaluate_guards(request)
    finally:
        explain_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["allowed"], False)
    testbase.assert_equal(body["failing_rule_id"], "max-concurrent")
    testbase.assert_equal(len(body["entries"]), 1)
    return


def test_evaluate_returns_404_when_environment_missing():
    """
    **Feature: 6-blast-radius-guards PR p21c**
    **Property: POST guards:evaluate returns 404 when the guard
    facade raises GuardEnvironmentNotFoundError.**
    """
    perm_patch = _patch_check_permission(allowed=True)
    proj_patch = _patch_project_exists(
        project=_FakeProject(project_id="proj-1"),
    )
    explain_patch = create_module_patch(
        guards_routes.guards_service, "explain",
    )
    explain_mock = explain_patch.activate()

    def _raise(**kwargs: Any) -> Any:
        raise GuardEnvironmentNotFoundError("no env")

    explain_mock.configure(side_effect=_raise)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/proj-1/blast-radius-guards:evaluate",
            path_params={"project_id": "proj-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
            body={"environment_id": "env-x", "action": "scale-up"},
        )
        response = guards_routes.handle_evaluate_guards(request)
    finally:
        explain_patch.deactivate()
        proj_patch.deactivate()
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return
