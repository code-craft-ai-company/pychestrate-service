"""
.. module:: test_p12i_pods_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native pods REST routes.

.. moduleauthor:: Automation Mojo LLC

The pods port has the largest single-controller surface in the
migration -- 13 routes across four logical groupings, six
service modules patched independently, and the most exception
types after the enrollment port. Tests cover the route matrix,
the 503 sweep on every handler, the per-grouping happy paths,
the per-error extension members, and bootstrap source-smoke.
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
)
from automojo.pychestrate.webservice.pods.exceptions import (
    MaterializationError,
    MemberKindNotRegisteredError,
    PodDefinitionAlreadyExistsError,
    PodDefinitionNotFoundError,
    PodSpecValidationError,
    PodTemplateNotFoundError,
)
from automojo.pychestrate.webservice.pods.restapi.v1 import pods_routes


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


class _FakeDefinition:
    def __init__(
        self,
        *,
        pod_id: str,
        project_id: str = "p-1",
        pod_name: str = "pod-x",
        current_version: int = 1,
    ) -> None:
        self.pod_id: str = pod_id
        self.project_id: str = project_id
        self.pod_name: str = pod_name
        self.current_version: int = current_version
        self.created_at: datetime = datetime(
            2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc
        )
        return


class _FakeVersion:
    def __init__(
        self,
        *,
        spec_json: Optional[Dict[str, Any]] = None,
        spec_hash: str = "sh-1",
    ) -> None:
        self.spec_json: Optional[Dict[str, Any]] = (
            spec_json if spec_json is not None else {"name": "x"}
        )
        self.spec_hash: str = spec_hash
        return


class _FakeStateRow:
    def __init__(
        self,
        *,
        pod_id: str = "pod-1",
        state: str = "ACTIVE",
        previous_state: Optional[str] = "PENDING",
        last_transition_event: str = "registration_succeeded",
        transition_cursor: int = 7,
    ) -> None:
        self.pod_id: str = pod_id
        self.state: _FakeStateEnum = _FakeStateEnum(value=state)
        self.previous_state: Optional[_FakeStateEnum] = (
            _FakeStateEnum(value=previous_state)
            if previous_state is not None else None
        )
        self.last_transition_at: datetime = datetime(
            2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc
        )
        self.last_transition_event: str = last_transition_event
        self.transition_cursor: int = transition_cursor
        return


class _FakeLogRow:
    def __init__(
        self,
        *,
        log_id: str,
        from_state: Optional[str] = "PENDING",
        to_state: str = "ACTIVE",
        event_kind: str = "registration_succeeded",
        actor: str = "system",
    ) -> None:
        self.log_id: str = log_id
        self.from_state: Optional[_FakeStateEnum] = (
            _FakeStateEnum(value=from_state)
            if from_state is not None else None
        )
        self.to_state: _FakeStateEnum = _FakeStateEnum(value=to_state)
        self.event_kind: str = event_kind
        self.actor: str = actor
        self.applied_at: datetime = datetime(
            2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc
        )
        return


class _FakeRegistration:
    def __init__(
        self,
        *,
        registration_id: str = "reg-1",
        pod_id: str = "pod-1",
        pod_definition_version: int = 1,
        client_id: Optional[str] = "c-1",
        state: str = "ACTIVE",
        report_hash: str = "rh-1",
        deregistered_at: Optional[datetime] = None,
        deregister_reason: Optional[str] = None,
    ) -> None:
        self.registration_id: str = registration_id
        self.pod_id: str = pod_id
        self.pod_definition_version: int = pod_definition_version
        self.client_id: Optional[str] = client_id
        self.state: _FakeStateEnum = _FakeStateEnum(value=state)
        self.report_hash: str = report_hash
        self.registered_at: datetime = datetime(
            2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc
        )
        self.deregistered_at: Optional[datetime] = deregistered_at
        self.deregister_reason: Optional[str] = deregister_reason
        return


class _FakeTemplate:
    def __init__(
        self,
        *,
        template_id: str = "t-1",
        project_id: str = "p-1",
        name: str = "tmpl",
        template_kind: str = "static",
        source_version: int = 1,
    ) -> None:
        self.template_id: str = template_id
        self.project_id: str = project_id
        self.name: str = name
        self.template_kind: str = template_kind
        self.source_version: int = source_version
        return


class _FakeMaterialization:
    def __init__(
        self,
        *,
        materialization_id: str = "m-1",
        template_id: str = "t-1",
        state: str = "PENDING",
        pod_id: Optional[str] = None,
    ) -> None:
        self.materialization_id: str = materialization_id
        self.template_id: str = template_id
        self.state: _FakeStateEnum = _FakeStateEnum(value=state)
        self.pod_id: Optional[str] = pod_id
        return


class _FakeScopedVariable:
    def __init__(
        self,
        *,
        variable_id: str = "v-1",
        run_id: str = "r-1",
        pod_id: str = "pod-1",
        name: str = "var-x",
        locked: bool = False,
    ) -> None:
        self.variable_id: str = variable_id
        self.run_id: str = run_id
        self.pod_id: str = pod_id
        self.name: str = name
        self.locked: bool = locked
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


def _patch_routes_attr(*, name: str, value: Any) -> Any:
    """
        Patch ``pods_routes.<name>`` to the supplied callable.
    """
    patch = create_module_patch(pods_routes, name)
    mock = patch.activate()
    mock.configure(side_effect=value)
    return patch


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_pods_routes_attaches_thirteen_routes_across_four_groupings():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: register_pods_routes attaches the same thirteen
    method+path pairs the flask_restx controller exposed.**
    """
    app = _FakeApp()
    pods_routes.register_pods_routes(app=app, version_prefix="/api/v1")

    expected_pairs = (
        # Definitions
        ("/api/v1/projects/{project_id}/pod-definitions", ("GET",)),
        ("/api/v1/projects/{project_id}/pod-definitions", ("POST",)),
        ("/api/v1/projects/{project_id}/pod-definitions/{pod_id}", ("GET",)),
        # Lifecycle
        ("/api/v1/projects/{project_id}/pods/{pod_id}/state", ("GET",)),
        ("/api/v1/projects/{project_id}/pods/{pod_id}/state/history", ("GET",)),
        # Registration + topology
        ("/api/v1/projects/{project_id}/pods/{pod_id}/registration", ("GET",)),
        ("/api/v1/projects/{project_id}/pods/{pod_id}/registrations", ("GET",)),
        ("/api/v1/projects/{project_id}/pods/{pod_id}/topology", ("GET",)),
        # Templates
        ("/api/v1/projects/{project_id}/pod-templates", ("GET",)),
        ("/api/v1/projects/{project_id}/pod-templates", ("POST",)),
        (
            "/api/v1/projects/{project_id}/pod-templates/{template_id}:materialize",
            ("POST",),
        ),
        # Run-scoped variables
        (
            "/api/v1/projects/{project_id}/runs/{run_id}/variables/{name}",
            ("PUT",),
        ),
        (
            "/api/v1/projects/{project_id}/runs/{run_id}/variables/{name}",
            ("DELETE",),
        ),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# 503 sweep across every handler
# ---------------------------------------------------------------------------


def test_503_sweep_on_every_pods_handler():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: Every pods handler returns 503 problem+json on
    missing session. One pass over all 13 routes' handlers.**
    """
    handlers_with_setup: List[Callable[[], Any]] = [
        # definitions
        lambda: pods_routes.handle_create_pod_definition(
            _FakeRequest(
                path="/api/v1/projects/p-1/pod-definitions",
                path_params={"project_id": "p-1"},
                body={"pod_name": "pod-x", "spec": {}},
                db_session=None,
            )
        ),
        lambda: pods_routes.handle_list_pod_definitions(
            _FakeRequest(
                path="/api/v1/projects/p-1/pod-definitions",
                path_params={"project_id": "p-1"},
                db_session=None,
            )
        ),
        lambda: pods_routes.handle_read_pod_definition(
            _FakeRequest(
                path="/api/v1/projects/p-1/pod-definitions/pod-1",
                path_params={"project_id": "p-1", "pod_id": "pod-1"},
                db_session=None,
            )
        ),
        # lifecycle
        lambda: pods_routes.handle_read_pod_state(
            _FakeRequest(
                path="/api/v1/projects/p-1/pods/pod-1/state",
                path_params={"project_id": "p-1", "pod_id": "pod-1"},
                db_session=None,
            )
        ),
        lambda: pods_routes.handle_read_pod_state_history(
            _FakeRequest(
                path="/api/v1/projects/p-1/pods/pod-1/state/history",
                path_params={"project_id": "p-1", "pod_id": "pod-1"},
                db_session=None,
            )
        ),
        # registration + topology
        lambda: pods_routes.handle_read_pod_registration(
            _FakeRequest(
                path="/api/v1/projects/p-1/pods/pod-1/registration",
                path_params={"project_id": "p-1", "pod_id": "pod-1"},
                db_session=None,
            )
        ),
        lambda: pods_routes.handle_list_pod_registrations(
            _FakeRequest(
                path="/api/v1/projects/p-1/pods/pod-1/registrations",
                path_params={"project_id": "p-1", "pod_id": "pod-1"},
                db_session=None,
            )
        ),
        lambda: pods_routes.handle_read_pod_topology(
            _FakeRequest(
                path="/api/v1/projects/p-1/pods/pod-1/topology",
                path_params={"project_id": "p-1", "pod_id": "pod-1"},
                db_session=None,
            )
        ),
        # templates
        lambda: pods_routes.handle_create_pod_template(
            _FakeRequest(
                path="/api/v1/projects/p-1/pod-templates",
                path_params={"project_id": "p-1"},
                body={
                    "name": "tmpl", "template_kind": "static",
                    "source_json": {},
                },
                db_session=None,
            )
        ),
        lambda: pods_routes.handle_list_pod_templates(
            _FakeRequest(
                path="/api/v1/projects/p-1/pod-templates",
                path_params={"project_id": "p-1"},
                db_session=None,
            )
        ),
        lambda: pods_routes.handle_materialize_pod_template(
            _FakeRequest(
                path="/api/v1/projects/p-1/pod-templates/t-1:materialize",
                path_params={"project_id": "p-1", "template_id": "t-1"},
                body={},
                db_session=None,
            )
        ),
        # variables
        lambda: pods_routes.handle_set_scoped_variable(
            _FakeRequest(
                path="/api/v1/projects/p-1/runs/r-1/variables/var-x",
                path_params={"run_id": "r-1", "name": "var-x"},
                body={"value": 1},
                db_session=None,
            )
        ),
        lambda: pods_routes.handle_delete_scoped_variable(
            _FakeRequest(
                path="/api/v1/projects/p-1/runs/r-1/variables/var-x",
                path_params={"run_id": "r-1", "name": "var-x"},
                db_session=None,
            )
        ),
    ]

    for invoke in handlers_with_setup:
        response = invoke()
        testbase.assert_equal(response.status_code, 503)
        body = _decode_body(response)
        testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


# ---------------------------------------------------------------------------
# Pod definitions: create
# ---------------------------------------------------------------------------


def test_handle_create_pod_definition_returns_201_with_actor_propagation():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: Successful create returns 201 with the definition
    + version dict; actor_user_id propagates.**
    """
    captured: Dict[str, Any] = {}

    def fake_create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return _FakeDefinition(pod_id="pod-1")

    create_patch = _patch_routes_attr(
        name="create_pod_definition", value=fake_create
    )
    version_patch = _patch_routes_attr(
        name="read_pod_definition_version",
        value=lambda **kwargs: _FakeVersion(),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pod-definitions",
            path_params={"project_id": "p-1"},
            db_session=object(),
            actor_user_id="user-42",
            body={"pod_name": "pod-x", "spec": {"image": "x"}},
        )
        response = pods_routes.handle_create_pod_definition(request)
    finally:
        version_patch.deactivate()
        create_patch.deactivate()

    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["pod_id"], "pod-1")
    testbase.assert_equal(captured["actor_user_id"], "user-42")
    return


def test_handle_create_pod_definition_returns_409_with_pod_name_extension():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: PodDefinitionAlreadyExistsError → 409 problem+json
    with project_id + pod_name as extension members.**
    """
    create_patch = _patch_routes_attr(
        name="create_pod_definition",
        value=_raises(PodDefinitionAlreadyExistsError("dup")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pod-definitions",
            path_params={"project_id": "p-1"},
            db_session=object(),
            body={"pod_name": "dup-pod", "spec": {}},
        )
        response = pods_routes.handle_create_pod_definition(request)
    finally:
        create_patch.deactivate()

    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["pod_name"], "dup-pod")
    testbase.assert_equal(body["project_id"], "p-1")
    return


def test_handle_create_pod_definition_returns_400_on_pod_spec_validation_error():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: PodSpecValidationError → 400 problem+json with
    project_id extension.**
    """
    create_patch = _patch_routes_attr(
        name="create_pod_definition",
        value=_raises(PodSpecValidationError("invalid spec")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pod-definitions",
            path_params={"project_id": "p-1"},
            db_session=object(),
            body={"pod_name": "pod-x", "spec": {}},
        )
        response = pods_routes.handle_create_pod_definition(request)
    finally:
        create_patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    testbase.assert_equal(body["project_id"], "p-1")
    return


def test_handle_create_pod_definition_returns_400_on_member_kind_not_registered():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: MemberKindNotRegisteredError → 400 problem+json.**
    """
    create_patch = _patch_routes_attr(
        name="create_pod_definition",
        value=_raises(MemberKindNotRegisteredError("unknown kind")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pod-definitions",
            path_params={"project_id": "p-1"},
            db_session=object(),
            body={"pod_name": "pod-x", "spec": {}},
        )
        response = pods_routes.handle_create_pod_definition(request)
    finally:
        create_patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    return


# ---------------------------------------------------------------------------
# Pod definitions: list, read
# ---------------------------------------------------------------------------


def test_handle_list_pod_definitions_returns_serialized_rows():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: list returns 200 with a serialized definition+
    version list.**
    """
    definitions = [
        _FakeDefinition(pod_id="pod-1", pod_name="alpha"),
        _FakeDefinition(pod_id="pod-2", pod_name="beta"),
    ]
    list_patch = _patch_routes_attr(
        name="list_pod_definitions", value=lambda **kwargs: definitions
    )
    version_patch = _patch_routes_attr(
        name="read_pod_definition_version",
        value=lambda **kwargs: _FakeVersion(),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pod-definitions",
            path_params={"project_id": "p-1"},
            db_session=object(),
        )
        response = pods_routes.handle_list_pod_definitions(request)
    finally:
        version_patch.deactivate()
        list_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 2)
    testbase.assert_equal(body[0]["pod_id"], "pod-1")
    return


def test_handle_read_pod_definition_returns_404_with_extensions():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: PodDefinitionNotFoundError → 404 problem+json with
    project_id + pod_id extensions.**
    """
    read_patch = _patch_routes_attr(
        name="read_pod_definition",
        value=_raises(PodDefinitionNotFoundError("missing")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pod-definitions/pod-missing",
            path_params={"project_id": "p-1", "pod_id": "pod-missing"},
            db_session=object(),
        )
        response = pods_routes.handle_read_pod_definition(request)
    finally:
        read_patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["pod_id"], "pod-missing")
    testbase.assert_equal(body["project_id"], "p-1")
    return


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_handle_read_pod_state_returns_serialized_state():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: state returns 200 with the documented state shape.**
    """
    state_patch = _patch_routes_attr(
        name="read_state",
        value=lambda **kwargs: _FakeStateRow(state="ACTIVE"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pods/pod-1/state",
            path_params={"project_id": "p-1", "pod_id": "pod-1"},
            db_session=object(),
        )
        response = pods_routes.handle_read_pod_state(request)
    finally:
        state_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["state"], "ACTIVE")
    testbase.assert_equal(body["previous_state"], "PENDING")
    testbase.assert_equal(body["transition_cursor"], 7)
    return


def test_handle_read_pod_state_history_propagates_pagination_with_400_on_bad_int():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: history forwards offset / limit (with documented
    defaults); a non-integer offset returns 400 problem+json with
    the bad value as an extension member.**
    """
    captured: Dict[str, Any] = {}

    def fake_history(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return [_FakeLogRow(log_id="log-1")]

    hist_patch = _patch_routes_attr(
        name="read_state_history", value=fake_history
    )
    try:
        # Happy path with explicit pagination.
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pods/pod-1/state/history",
            path_params={"project_id": "p-1", "pod_id": "pod-1"},
            db_session=object(),
            query={"offset": "5", "limit": "20"},
        )
        response = pods_routes.handle_read_pod_state_history(request)
        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(captured["offset"], 5)
        testbase.assert_equal(captured["limit"], 20)
    finally:
        hist_patch.deactivate()

    # 400 branch on non-integer offset.
    request_bad = _FakeRequest(
        path="/api/v1/projects/p-1/pods/pod-1/state/history",
        path_params={"project_id": "p-1", "pod_id": "pod-1"},
        db_session=object(),
        query={"offset": "abc"},
    )
    response_bad = pods_routes.handle_read_pod_state_history(request_bad)
    testbase.assert_equal(response_bad.status_code, 400)
    body_bad = _decode_body(response_bad)
    testbase.assert_equal(body_bad["offset"], "abc")
    return


def test_handle_read_pod_state_history_uses_documented_defaults():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: With no pagination query, offset=0 and limit=100
    pass through to read_state_history.**
    """
    captured: Dict[str, Any] = {}

    def fake_history(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return []

    hist_patch = _patch_routes_attr(
        name="read_state_history", value=fake_history
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pods/pod-1/state/history",
            path_params={"project_id": "p-1", "pod_id": "pod-1"},
            db_session=object(),
        )
        pods_routes.handle_read_pod_state_history(request)
    finally:
        hist_patch.deactivate()

    testbase.assert_equal(captured["offset"], pods_routes.DEFAULT_HISTORY_OFFSET)
    testbase.assert_equal(captured["limit"], pods_routes.DEFAULT_HISTORY_LIMIT)
    return


# ---------------------------------------------------------------------------
# Registration + topology
# ---------------------------------------------------------------------------


def test_handle_read_pod_registration_returns_404_when_no_active_row():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: When read_active_registration returns None, the
    handler emits 404 problem+json with project_id + pod_id
    extensions.**
    """
    reg_patch = _patch_routes_attr(
        name="read_active_registration", value=lambda **kwargs: None,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pods/pod-1/registration",
            path_params={"project_id": "p-1", "pod_id": "pod-1"},
            db_session=object(),
        )
        response = pods_routes.handle_read_pod_registration(request)
    finally:
        reg_patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["pod_id"], "pod-1")
    testbase.assert_equal(body["project_id"], "p-1")
    return


def test_handle_read_pod_registration_returns_serialized_row():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: An active registration returns 200 with the
    documented shape including report_hash and registered_at.**
    """
    row = _FakeRegistration(report_hash="rh-2026")
    reg_patch = _patch_routes_attr(
        name="read_active_registration", value=lambda **kwargs: row,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pods/pod-1/registration",
            path_params={"project_id": "p-1", "pod_id": "pod-1"},
            db_session=object(),
        )
        response = pods_routes.handle_read_pod_registration(request)
    finally:
        reg_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["report_hash"], "rh-2026")
    return


def test_handle_list_pod_registrations_returns_history():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: registrations returns 200 with the history list.**
    """
    rows = [
        _FakeRegistration(registration_id="reg-1"),
        _FakeRegistration(
            registration_id="reg-2",
            deregister_reason="rotated",
        ),
    ]
    hist_patch = _patch_routes_attr(
        name="list_registration_history", value=lambda **kwargs: rows,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pods/pod-1/registrations",
            path_params={"project_id": "p-1", "pod_id": "pod-1"},
            db_session=object(),
        )
        response = pods_routes.handle_list_pod_registrations(request)
    finally:
        hist_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 2)
    testbase.assert_equal(body[1]["deregister_reason"], "rotated")
    return


def test_handle_read_pod_topology_returns_404_with_extensions():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: PodDefinitionNotFoundError from compose_topology →
    404 problem+json with project_id + pod_id extensions.**
    """
    topo_patch = _patch_routes_attr(
        name="compose_topology",
        value=_raises(PodDefinitionNotFoundError("missing")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pods/pod-1/topology",
            path_params={"project_id": "p-1", "pod_id": "pod-1"},
            db_session=object(),
        )
        response = pods_routes.handle_read_pod_topology(request)
    finally:
        topo_patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["pod_id"], "pod-1")
    return


def test_handle_read_pod_topology_returns_dict_via_topology_as_dict():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: topology returns 200 with the dict produced by
    topology_as_dict.**
    """
    topo_patch = _patch_routes_attr(
        name="compose_topology", value=lambda **kwargs: object(),
    )
    as_dict_patch = _patch_routes_attr(
        name="topology_as_dict",
        value=lambda graph: {"nodes": ["a", "b"], "edges": []},
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pods/pod-1/topology",
            path_params={"project_id": "p-1", "pod_id": "pod-1"},
            db_session=object(),
        )
        response = pods_routes.handle_read_pod_topology(request)
    finally:
        as_dict_patch.deactivate()
        topo_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["nodes"], ["a", "b"])
    return


# ---------------------------------------------------------------------------
# Pod templates
# ---------------------------------------------------------------------------


def test_handle_create_pod_template_returns_201_with_actor():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: Successful template create returns 201 with the
    template summary; actor_user_id propagates.**
    """
    captured: Dict[str, Any] = {}

    def fake_create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return _FakeTemplate(template_id="t-1")

    create_patch = _patch_routes_attr(
        name="create_pod_template", value=fake_create
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pod-templates",
            path_params={"project_id": "p-1"},
            db_session=object(),
            actor_user_id="user-42",
            body={
                "name": "tmpl",
                "template_kind": "static",
                "source_json": {"x": 1},
            },
        )
        response = pods_routes.handle_create_pod_template(request)
    finally:
        create_patch.deactivate()

    testbase.assert_equal(response.status_code, 201)
    body = _decode_body(response)
    testbase.assert_equal(body["template_id"], "t-1")
    testbase.assert_equal(captured["actor_user_id"], "user-42")
    return


def test_handle_list_pod_templates_returns_summaries():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: list returns 200 with template summaries.**
    """
    rows = [_FakeTemplate(template_id="t-1"), _FakeTemplate(template_id="t-2")]
    list_patch = _patch_routes_attr(
        name="list_pod_templates", value=lambda **kwargs: rows
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pod-templates",
            path_params={"project_id": "p-1"},
            db_session=object(),
        )
        response = pods_routes.handle_list_pod_templates(request)
    finally:
        list_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 2)
    return


def test_handle_materialize_pod_template_returns_202_on_success():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: Successful materialize returns 202 with the
    materialization summary -- async start uses 202 (not 200/201)
    matching the flask controller.**
    """
    materialization = _FakeMaterialization(
        materialization_id="m-1", state="STARTING"
    )
    mat_patch = _patch_routes_attr(
        name="start_materialization",
        value=lambda **kwargs: materialization,
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pod-templates/t-1:materialize",
            path_params={"project_id": "p-1", "template_id": "t-1"},
            db_session=object(),
            body={"parameters": {"size": 3}},
        )
        response = pods_routes.handle_materialize_pod_template(request)
    finally:
        mat_patch.deactivate()

    testbase.assert_equal(response.status_code, 202)
    body = _decode_body(response)
    testbase.assert_equal(body["materialization_id"], "m-1")
    testbase.assert_equal(body["state"], "STARTING")
    return


def test_handle_materialize_returns_404_on_template_not_found():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: PodTemplateNotFoundError → 404 problem+json with
    project_id + template_id extensions.**
    """
    mat_patch = _patch_routes_attr(
        name="start_materialization",
        value=_raises(PodTemplateNotFoundError("no such template")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pod-templates/t-missing:materialize",
            path_params={"project_id": "p-1", "template_id": "t-missing"},
            db_session=object(),
            body={},
        )
        response = pods_routes.handle_materialize_pod_template(request)
    finally:
        mat_patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["template_id"], "t-missing")
    testbase.assert_equal(body["project_id"], "p-1")
    return


def test_handle_materialize_returns_409_on_materialization_error():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: MaterializationError → 409 problem+json with
    template_id extension.**
    """
    mat_patch = _patch_routes_attr(
        name="start_materialization",
        value=_raises(MaterializationError("conflict")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/pod-templates/t-1:materialize",
            path_params={"project_id": "p-1", "template_id": "t-1"},
            db_session=object(),
            body={},
        )
        response = pods_routes.handle_materialize_pod_template(request)
    finally:
        mat_patch.deactivate()

    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_CONFLICT)
    return


# ---------------------------------------------------------------------------
# Run-scoped variables
# ---------------------------------------------------------------------------


def test_handle_set_scoped_variable_requires_pod_id_query_param():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: Missing pod_id query returns 400 problem+json.
    Mirrors the flask controller's required-query guard.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/p-1/runs/r-1/variables/var-x",
        path_params={"run_id": "r-1", "name": "var-x"},
        db_session=object(),
        body={"value": 1},
    )
    response = pods_routes.handle_set_scoped_variable(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    return


def test_handle_set_scoped_variable_returns_serialized_row_on_success():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: Successful set returns 200 with the variable row
    + locked flag; pod_id/run_id/name + actor propagate.**
    """
    captured: Dict[str, Any] = {}
    row = _FakeScopedVariable(
        variable_id="v-1", run_id="r-1", pod_id="pod-1", name="var-x", locked=True
    )

    def fake_set(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return row

    set_patch = _patch_routes_attr(
        name="set_scoped_variable", value=fake_set
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/runs/r-1/variables/var-x",
            path_params={"run_id": "r-1", "name": "var-x"},
            db_session=object(),
            actor_user_id="user-42",
            query={"pod_id": "pod-1"},
            body={"value": 1, "locked": True},
        )
        response = pods_routes.handle_set_scoped_variable(request)
    finally:
        set_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["variable_id"], "v-1")
    testbase.assert_equal(body["locked"], True)
    testbase.assert_equal(captured["pod_id"], "pod-1")
    testbase.assert_equal(captured["actor_user_id"], "user-42")
    return


def test_handle_set_scoped_variable_returns_400_on_semantic_error():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: SemanticError → 400 problem+json with run_id /
    pod_id / name extensions.**
    """
    set_patch = _patch_routes_attr(
        name="set_scoped_variable",
        value=_raises(SemanticError("bad input")),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/runs/r-1/variables/var-x",
            path_params={"run_id": "r-1", "name": "var-x"},
            db_session=object(),
            query={"pod_id": "pod-1"},
            body={"value": 1},
        )
        response = pods_routes.handle_set_scoped_variable(request)
    finally:
        set_patch.deactivate()

    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["run_id"], "r-1")
    testbase.assert_equal(body["pod_id"], "pod-1")
    testbase.assert_equal(body["name"], "var-x")
    return


def test_handle_delete_scoped_variable_returns_204_on_success():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: Successful delete returns 204 with empty body.
    pod_id query + actor propagate.**
    """
    captured: Dict[str, Any] = {}

    def fake_delete(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return None

    del_patch = _patch_routes_attr(
        name="delete_scoped_variable", value=fake_delete
    )
    try:
        request = _FakeRequest(
            path="/api/v1/projects/p-1/runs/r-1/variables/var-x",
            path_params={"run_id": "r-1", "name": "var-x"},
            db_session=object(),
            actor_user_id="user-42",
            query={"pod_id": "pod-1"},
        )
        response = pods_routes.handle_delete_scoped_variable(request)
    finally:
        del_patch.deactivate()

    testbase.assert_equal(response.status_code, 204)
    testbase.assert_equal(response.body, b"")
    testbase.assert_equal(captured["pod_id"], "pod-1")
    testbase.assert_equal(captured["actor_user_id"], "user-42")
    return


def test_handle_delete_scoped_variable_requires_pod_id_query_param():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: delete also requires pod_id; returns 400 when
    missing.**
    """
    request = _FakeRequest(
        path="/api/v1/projects/p-1/runs/r-1/variables/var-x",
        path_params={"run_id": "r-1", "name": "var-x"},
        db_session=object(),
    )
    response = pods_routes.handle_delete_scoped_variable(request)
    testbase.assert_equal(response.status_code, 400)
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_pods_routes_and_calls_it():
    """
    **Feature: 3-pods T1.1 (webworks routes)**
    **Property: app_pychestrate_main.py wires register_pods_routes
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
        "from automojo.pychestrate.webservice.pods.restapi.v1.pods_routes import"
        in text
    )
    has_call = "register_pods_routes(app=app, version_prefix=\"/api/v1\")" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return
