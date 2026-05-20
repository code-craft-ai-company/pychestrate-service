"""
.. module:: test_p12j_projects_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native projects REST routes.

.. moduleauthor:: Automation Mojo LLC

The projects port is the FINAL flask_restx controller migrated to
webworks. Ten routes covering project lifecycle (create / read /
patch / delete / archive / unarchive) plus the members surface
(list / add / two delete shapes with the last-admin safeguard
and ?force=true override).

Tests cover the route matrix, the 503 sweep, the per-error
extension members, the 422 path on MetadataFieldValidationError
(only 422 in the controller), the last-admin safeguard +
force-flag pass-through, and bootstrap source-smoke.
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
    PROBLEM_TYPE_CONFLICT,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_VALIDATION_FAILED,
)
from automojo.pychestrate.webservice.projects.exceptions import (
    LastAdminRemovalError,
    MemberBindingNotFoundError,
    MetadataFieldValidationError,
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    ProjectStateTransitionError,
    SlugValidationError,
)
from automojo.pychestrate.webservice.projects.restapi.v1 import projects_routes
from automojo.pychestrate.webservice.projects.service import PROJECT_OWNER_ROLE


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


class _FakeStateEnum:
    def __init__(self, *, value: str) -> None:
        self.value: str = value
        return


class _FakeProject:
    def __init__(
        self,
        *,
        project_id: str = "p-1",
        slug: str = "alpha",
        display_name: str = "Alpha",
        description: str = "Alpha desc",
        state: str = "ACTIVE",
        owning_group_id: Optional[str] = None,
        template_id: Optional[str] = None,
        template_version: Optional[str] = None,
        extension_fields: Optional[Dict[str, Any]] = None,
        archived_at: Optional[datetime] = None,
    ) -> None:
        self.project_id: str = project_id
        self.slug: str = slug
        self.display_name: str = display_name
        self.description: str = description
        self.state: _FakeStateEnum = _FakeStateEnum(value=state)
        self.owning_group_id: Optional[str] = owning_group_id
        self.template_id: Optional[str] = template_id
        self.template_version: Optional[str] = template_version
        self.extension_fields: Optional[Dict[str, Any]] = extension_fields
        self.created_at: datetime = datetime(
            2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc
        )
        self.updated_at: datetime = datetime(
            2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc
        )
        self.archived_at: Optional[datetime] = archived_at
        return


class _FakeBinding:
    def __init__(
        self,
        *,
        binding_id: str = "b-1",
        project_id: str = "p-1",
        user_id: str = "u-1",
        role_name: str = PROJECT_OWNER_ROLE,
        added_by_user_id: Optional[str] = None,
    ) -> None:
        self.binding_id: str = binding_id
        self.project_id: str = project_id
        self.user_id: str = user_id
        self.role_name: str = role_name
        self.added_at: datetime = datetime(
            2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc
        )
        self.added_by_user_id: Optional[str] = added_by_user_id
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


def _patch_service_attr(*, name: str, value: Any) -> Any:
    """
        Patch ``projects_routes.project_service.<name>`` to the
        supplied callable. The routes module imports the service
        as ``project_service`` (module reference), so attribute
        access on it picks up the patched callable.
    """
    patch = create_module_patch(projects_routes, "project_service")
    mock_module = patch.activate()
    mock_module.configure(recursive=True)
    mock_module.mock_context().set_attribute(name, value)
    return patch


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_projects_routes_attaches_eleven_routes():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: register_projects_routes attaches the project
    lifecycle + members method+path pairs plus the GET /projects
    list endpoint added by PR p20e.**
    """
    app = _FakeApp()
    projects_routes.register_projects_routes(
        app=app, version_prefix="/api/v1"
    )

    expected_pairs = (
        ("/api/v1/projects", ("GET",)),
        ("/api/v1/projects", ("POST",)),
        ("/api/v1/projects/{slug}", ("GET",)),
        ("/api/v1/projects/{slug}", ("PATCH",)),
        ("/api/v1/projects/{slug}", ("DELETE",)),
        ("/api/v1/projects/{slug}/archive", ("POST",)),
        ("/api/v1/projects/{slug}/unarchive", ("POST",)),
        ("/api/v1/projects/{slug}/members", ("GET",)),
        ("/api/v1/projects/{slug}/members", ("POST",)),
        ("/api/v1/projects/{slug}/members/{user_id}", ("DELETE",)),
        (
            "/api/v1/projects/{slug}/members/{user_id}/{role_name}",
            ("DELETE",),
        ),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# 503 sweep
# ---------------------------------------------------------------------------


def test_503_sweep_on_every_projects_handler():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: Every projects handler returns 503 problem+json on
    missing session.**
    """
    handlers: List[Callable[[], Any]] = [
        lambda: projects_routes.handle_list_projects(
            _FakeRequest(
                path="/api/v1/projects",
                db_session=None,
            )
        ),
        lambda: projects_routes.handle_create_project(
            _FakeRequest(
                path="/api/v1/projects",
                body={"slug": "x", "display_name": "X"},
                db_session=None,
            )
        ),
        lambda: projects_routes.handle_read_project(
            _FakeRequest(
                path="/api/v1/projects/x",
                path_params={"slug": "x"},
                db_session=None,
            )
        ),
        lambda: projects_routes.handle_patch_project(
            _FakeRequest(
                path="/api/v1/projects/x",
                path_params={"slug": "x"},
                body={"display_name": "X2"},
                db_session=None,
            )
        ),
        lambda: projects_routes.handle_delete_project(
            _FakeRequest(
                path="/api/v1/projects/x",
                path_params={"slug": "x"},
                db_session=None,
            )
        ),
        lambda: projects_routes.handle_archive_project(
            _FakeRequest(
                path="/api/v1/projects/x/archive",
                path_params={"slug": "x"},
                db_session=None,
            )
        ),
        lambda: projects_routes.handle_unarchive_project(
            _FakeRequest(
                path="/api/v1/projects/x/unarchive",
                path_params={"slug": "x"},
                db_session=None,
            )
        ),
        lambda: projects_routes.handle_list_members(
            _FakeRequest(
                path="/api/v1/projects/x/members",
                path_params={"slug": "x"},
                db_session=None,
            )
        ),
        lambda: projects_routes.handle_add_member(
            _FakeRequest(
                path="/api/v1/projects/x/members",
                path_params={"slug": "x"},
                body={"user_id": "u-1", "role_name": "viewer"},
                db_session=None,
            )
        ),
        lambda: projects_routes.handle_remove_member_owner_binding(
            _FakeRequest(
                path="/api/v1/projects/x/members/u-1",
                path_params={"slug": "x", "user_id": "u-1"},
                db_session=None,
            )
        ),
        lambda: projects_routes.handle_remove_member_specific_role(
            _FakeRequest(
                path="/api/v1/projects/x/members/u-1/viewer",
                path_params={
                    "slug": "x", "user_id": "u-1", "role_name": "viewer",
                },
                db_session=None,
            )
        ),
    ]

    for invoke in handlers:
        response = invoke()
        testbase.assert_equal(response.status_code, 503)
        body = _decode_body(response)
        testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


# ---------------------------------------------------------------------------
# handle_create_project
# ---------------------------------------------------------------------------


def test_handle_create_project_returns_201_with_actor_propagation():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: Successful create returns 201 with project dict;
    actor_user_id propagates.**
    """
    project = _FakeProject(slug="alpha")
    captured: Dict[str, Any] = {}

    def fake_create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return project

    patch = _patch_service_attr(name="create_project", value=fake_create)
    try:
        request = _FakeRequest(
            path="/api/v1/projects",
            db_session=object(),
            actor_user_id="user-42",
            body={
                "slug": "alpha",
                "display_name": "Alpha",
                "description": "Alpha desc",
                "owning_group_id": "g-1",
            },
        )
        response = projects_routes.handle_create_project(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["slug"], "alpha")
    testbase.assert_equal(captured["actor_user_id"], "user-42")
    testbase.assert_equal(captured["owning_group_id"], "g-1")
    return


def test_handle_create_project_returns_400_with_slug_extension_on_validation_error():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: SlugValidationError → 400 problem+json with the
    bad slug as an extension member.**
    """
    patch = _patch_service_attr(
        name="create_project",
        value=_raises(SlugValidationError("bad slug shape")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects",
            db_session=object(),
            body={"slug": "Bad Slug!!!", "display_name": "X"},
        )
        response = projects_routes.handle_create_project(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    testbase.assert_equal(body["slug"], "Bad Slug!!!")
    return


def test_handle_create_project_returns_409_with_slug_extension_on_dup():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: ProjectAlreadyExistsError → 409 problem+json with
    the slug as an extension member.**
    """
    patch = _patch_service_attr(
        name="create_project",
        value=_raises(ProjectAlreadyExistsError("dup")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects",
            db_session=object(),
            body={"slug": "alpha", "display_name": "X"},
        )
        response = projects_routes.handle_create_project(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_CONFLICT)
    testbase.assert_equal(body["slug"], "alpha")
    return


def test_handle_create_project_returns_400_on_undecodable_body():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: Undecodable body returns 400, not 500.**
    """
    request = _FakeRequest(
        path="/api/v1/projects", db_session=object(), body_raises=True,
    )
    response = projects_routes.handle_create_project(request)
    testbase.assert_equal(response.status_code, 400)
    return


# ---------------------------------------------------------------------------
# handle_read_project
# ---------------------------------------------------------------------------


def test_handle_read_project_returns_serialized_dict_with_extension_fields():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: read returns 200 with the project dict; extension
    fields preserved.**
    """
    project = _FakeProject(
        slug="alpha", extension_fields={"team": "platform", "tier": "prod"}
    )
    patch = _patch_service_attr(
        name="read_project_by_slug", value=lambda **kwargs: project,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/alpha",
            path_params={"slug": "alpha"},
            db_session=object(),
        )
        response = projects_routes.handle_read_project(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["extension_fields"]["team"], "platform")
    return


def test_handle_read_project_returns_400_on_slug_validation_error():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: SlugValidationError on read → 400 problem+json
    with the slug extension.**
    """
    patch = _patch_service_attr(
        name="read_project_by_slug",
        value=_raises(SlugValidationError("bad")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/!!!",
            path_params={"slug": "!!!"},
            db_session=object(),
        )
        response = projects_routes.handle_read_project(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["slug"], "!!!")
    return


def test_handle_read_project_returns_404_with_slug_extension():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: ProjectNotFoundError → 404 problem+json with slug
    extension.**
    """
    patch = _patch_service_attr(
        name="read_project_by_slug",
        value=_raises(ProjectNotFoundError("missing")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/missing",
            path_params={"slug": "missing"},
            db_session=object(),
        )
        response = projects_routes.handle_read_project(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["slug"], "missing")
    return


# ---------------------------------------------------------------------------
# handle_patch_project
# ---------------------------------------------------------------------------


def test_handle_patch_project_returns_200_on_success():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: patch returns 200 with the updated project dict.
    actor + extension_fields propagate.**
    """
    project = _FakeProject(slug="alpha", display_name="Updated")
    captured: Dict[str, Any] = {}

    def fake_patch(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return project

    patch = _patch_service_attr(name="patch_project", value=fake_patch)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/alpha",
            path_params={"slug": "alpha"},
            db_session=object(),
            actor_user_id="user-42",
            body={
                "display_name": "Updated",
                "extension_fields": {"team": "platform"},
            },
        )
        response = projects_routes.handle_patch_project(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    testbase.assert_equal(captured["display_name"], "Updated")
    testbase.assert_equal(captured["extension_fields"]["team"], "platform")
    return


def test_handle_patch_project_returns_422_on_metadata_validation_error():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: MetadataFieldValidationError → 422 problem+json
    (the only 422 in the controller, mirroring the flask
    behavior).**
    """
    patch = _patch_service_attr(
        name="patch_project",
        value=_raises(MetadataFieldValidationError("invalid metadata")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/alpha",
            path_params={"slug": "alpha"},
            db_session=object(),
            body={"extension_fields": {"team": 123}},
        )
        response = projects_routes.handle_patch_project(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 422)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    testbase.assert_equal(body["slug"], "alpha")
    return


def test_handle_patch_project_returns_404_with_slug_extension():
    patch = _patch_service_attr(
        name="patch_project",
        value=_raises(ProjectNotFoundError("missing")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/missing",
            path_params={"slug": "missing"},
            db_session=object(),
            body={"display_name": "X"},
        )
        response = projects_routes.handle_patch_project(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["slug"], "missing")
    return


# ---------------------------------------------------------------------------
# handle_delete_project
# ---------------------------------------------------------------------------


def test_handle_delete_project_returns_204_on_success():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: Successful hard-delete returns 204.**
    """
    captured: Dict[str, Any] = {}

    def fake_delete(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return None

    patch = _patch_service_attr(name="delete_project", value=fake_delete)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/alpha",
            path_params={"slug": "alpha"},
            db_session=object(),
            actor_user_id="user-42",
        )
        response = projects_routes.handle_delete_project(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 204)
    testbase.assert_equal(response.body, b"")
    testbase.assert_equal(captured["actor_user_id"], "user-42")
    return


def test_handle_delete_project_returns_409_on_state_transition_error():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: ProjectStateTransitionError (e.g., trying to
    delete an active project) → 409 problem+json with slug
    extension.**
    """
    patch = _patch_service_attr(
        name="delete_project",
        value=_raises(ProjectStateTransitionError("not archived")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/alpha",
            path_params={"slug": "alpha"},
            db_session=object(),
        )
        response = projects_routes.handle_delete_project(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_CONFLICT)
    testbase.assert_equal(body["slug"], "alpha")
    return


# ---------------------------------------------------------------------------
# Archive / unarchive
# ---------------------------------------------------------------------------


def test_handle_archive_project_returns_serialized_archived_project():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: archive returns 200 with the project in ARCHIVED
    state.**
    """
    project = _FakeProject(slug="alpha", state="ARCHIVED")
    patch = _patch_service_attr(
        name="archive_project", value=lambda **kwargs: project,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/alpha/archive",
            path_params={"slug": "alpha"},
            db_session=object(),
        )
        response = projects_routes.handle_archive_project(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["state"], "ARCHIVED")
    return


def test_handle_archive_project_returns_404_on_missing():
    patch = _patch_service_attr(
        name="archive_project",
        value=_raises(ProjectNotFoundError("missing")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/missing/archive",
            path_params={"slug": "missing"},
            db_session=object(),
        )
        response = projects_routes.handle_archive_project(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    return


def test_handle_unarchive_project_returns_serialized_active_project():
    project = _FakeProject(slug="alpha", state="ACTIVE")
    patch = _patch_service_attr(
        name="unarchive_project", value=lambda **kwargs: project,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/alpha/unarchive",
            path_params={"slug": "alpha"},
            db_session=object(),
        )
        response = projects_routes.handle_unarchive_project(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["state"], "ACTIVE")
    return


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


def test_handle_list_members_returns_serialized_bindings():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: list returns 200 with serialized binding dicts.**
    """
    bindings = [
        _FakeBinding(binding_id="b-1", role_name=PROJECT_OWNER_ROLE),
        _FakeBinding(binding_id="b-2", role_name="viewer"),
    ]
    patch = _patch_service_attr(
        name="list_members", value=lambda **kwargs: bindings,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/alpha/members",
            path_params={"slug": "alpha"},
            db_session=object(),
        )
        response = projects_routes.handle_list_members(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 2)
    testbase.assert_equal(body[0]["binding_id"], "b-1")
    return


def test_handle_list_members_returns_404_with_slug_extension():
    patch = _patch_service_attr(
        name="list_members",
        value=_raises(ProjectNotFoundError("missing")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/missing/members",
            path_params={"slug": "missing"},
            db_session=object(),
        )
        response = projects_routes.handle_list_members(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["slug"], "missing")
    return


def test_handle_add_member_returns_201_with_actor():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: add_member returns 201 with the binding dict;
    actor + user_id + role_name propagate.**
    """
    binding = _FakeBinding(binding_id="b-1", role_name="viewer")
    captured: Dict[str, Any] = {}

    def fake_add(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return binding

    patch = _patch_service_attr(name="add_member", value=fake_add)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/alpha/members",
            path_params={"slug": "alpha"},
            db_session=object(),
            actor_user_id="user-42",
            body={"user_id": "u-1", "role_name": "viewer"},
        )
        response = projects_routes.handle_add_member(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["binding_id"], "b-1")
    testbase.assert_equal(captured["user_id"], "u-1")
    testbase.assert_equal(captured["role_name"], "viewer")
    return


def test_handle_add_member_returns_400_on_semantic_error_with_full_extensions():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: SemanticError → 400 problem+json with slug,
    user_id, role_name extension members.**
    """
    patch = _patch_service_attr(
        name="add_member", value=_raises(SemanticError("bad role")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/alpha/members",
            path_params={"slug": "alpha"},
            db_session=object(),
            body={"user_id": "u-1", "role_name": "garbage"},
        )
        response = projects_routes.handle_add_member(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["slug"], "alpha")
    testbase.assert_equal(body["user_id"], "u-1")
    testbase.assert_equal(body["role_name"], "garbage")
    return


# ---------------------------------------------------------------------------
# Member removal — owner binding (last-admin safeguard)
# ---------------------------------------------------------------------------


def test_handle_remove_member_owner_binding_204_with_role_name_constant():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: Successful owner-binding remove returns 204 and
    forwards role_name=PROJECT_OWNER_ROLE to the service. The
    user_id-only DELETE shape is sugar for "remove the owner
    role".**
    """
    captured: Dict[str, Any] = {}

    def fake_remove(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return None

    patch = _patch_service_attr(name="remove_member", value=fake_remove)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/alpha/members/u-1",
            path_params={"slug": "alpha", "user_id": "u-1"},
            db_session=object(),
            actor_user_id="user-42",
        )
        response = projects_routes.handle_remove_member_owner_binding(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 204)
    testbase.assert_equal(captured["role_name"], PROJECT_OWNER_ROLE)
    testbase.assert_equal(captured["force"], False)
    return


def test_handle_remove_member_owner_binding_propagates_force_true():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: ?force=true (case-insensitive variants) coerces to
    bool True and propagates to remove_member.**
    """
    captured: Dict[str, Any] = {}

    def fake_remove(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return None

    patch = _patch_service_attr(name="remove_member", value=fake_remove)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/alpha/members/u-1",
            path_params={"slug": "alpha", "user_id": "u-1"},
            db_session=object(),
            query={"force": "TRUE"},
        )
        projects_routes.handle_remove_member_owner_binding(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(captured["force"], True)
    return


def test_handle_remove_member_owner_binding_returns_409_on_last_admin():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: LastAdminRemovalError → 409 problem+json with
    slug + user_id extension members.**
    """
    patch = _patch_service_attr(
        name="remove_member",
        value=_raises(LastAdminRemovalError("would be last admin")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/alpha/members/u-last",
            path_params={"slug": "alpha", "user_id": "u-last"},
            db_session=object(),
        )
        response = projects_routes.handle_remove_member_owner_binding(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_CONFLICT)
    testbase.assert_equal(body["slug"], "alpha")
    testbase.assert_equal(body["user_id"], "u-last")
    return


def test_handle_remove_member_owner_binding_returns_404_with_role_extension():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: MemberBindingNotFoundError → 404 problem+json
    with slug, user_id, role_name=PROJECT_OWNER_ROLE extensions.**
    """
    patch = _patch_service_attr(
        name="remove_member",
        value=_raises(MemberBindingNotFoundError("not found")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/alpha/members/u-1",
            path_params={"slug": "alpha", "user_id": "u-1"},
            db_session=object(),
        )
        response = projects_routes.handle_remove_member_owner_binding(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["role_name"], PROJECT_OWNER_ROLE)
    return


# ---------------------------------------------------------------------------
# Member removal — specific role
# ---------------------------------------------------------------------------


def test_handle_remove_member_specific_role_204_with_role_propagation():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: Successful specific-role remove returns 204 and
    forwards the URL ``role_name`` (NOT the owner constant) to
    the service.**
    """
    captured: Dict[str, Any] = {}

    def fake_remove(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return None

    patch = _patch_service_attr(name="remove_member", value=fake_remove)
    try:
        request = _FakeRequest(
            path="/api/v1/projects/alpha/members/u-1/viewer",
            path_params={
                "slug": "alpha", "user_id": "u-1", "role_name": "viewer",
            },
            db_session=object(),
        )
        response = projects_routes.handle_remove_member_specific_role(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 204)
    testbase.assert_equal(captured["role_name"], "viewer")
    return


def test_handle_remove_member_specific_role_returns_404_with_role_extension():
    patch = _patch_service_attr(
        name="remove_member",
        value=_raises(MemberBindingNotFoundError("missing")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/alpha/members/u-1/viewer",
            path_params={
                "slug": "alpha", "user_id": "u-1", "role_name": "viewer",
            },
            db_session=object(),
        )
        response = projects_routes.handle_remove_member_specific_role(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["role_name"], "viewer")
    return


def test_handle_remove_member_specific_role_returns_409_on_last_admin():
    patch = _patch_service_attr(
        name="remove_member",
        value=_raises(LastAdminRemovalError("would be last admin")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/alpha/members/u-1/" + PROJECT_OWNER_ROLE,
            path_params={
                "slug": "alpha", "user_id": "u-1",
                "role_name": PROJECT_OWNER_ROLE,
            },
            db_session=object(),
        )
        response = projects_routes.handle_remove_member_specific_role(request)
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["role_name"], PROJECT_OWNER_ROLE)
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_projects_routes_and_calls_it():
    """
    **Feature: 2-projects T1.1 (webworks routes)**
    **Property: app_pychestrate_main.py wires
    register_projects_routes into register_service_extensions.**
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
        "from automojo.pychestrate.webservice.projects.restapi.v1.projects_routes import"
        in text
    )
    has_call = "register_projects_routes(app=app, version_prefix=\"/api/v1\")" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return
