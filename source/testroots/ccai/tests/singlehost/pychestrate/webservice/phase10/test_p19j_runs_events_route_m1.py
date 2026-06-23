"""
.. module:: test_p19j_runs_events_route_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the run live-events SSE endpoint (GET /api/v1/runs/{id}/events).

.. moduleauthor:: Code Craft AI LLC

Covers the operator-facing SSE surface added in PR p19j:

* register_runs_events_routes attaches the GET /events route.
* 503 when no db session is bound / no live bridge configured.
* 401 when no AuthPrincipal is bound.
* 403 when the principal lacks system:runs.read.
* 404 problem when the run is unknown.
* 200 text/event-stream on the happy path.
* The streaming generator emits an initial snapshot frame.
* A published run-state change reaches a subscribed stream.
* A published progress event reaches a subscribed stream.
* An idle stream emits a heartbeat frame.
* Closing the generator unsubscribes from the hub relay.
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
from ccai.pychestrate.webservice.orchestration.test.live.bus_bridge import (
    LiveRunBusBridge,
)
from ccai.pychestrate.webservice.orchestration.test.live.hub import (
    LiveRunHub,
)
from ccai.pychestrate.webservice.runs.restapi.v1 import runs_events_routes


# ---------------------------------------------------------------------------
# Stubs
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
        db_session: Optional[Any] = None,
        auth_principal: Optional[Any] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self.query_params: _FakeQueryParams = _FakeQueryParams()
        self.db_session: Optional[Any] = db_session
        self.auth_principal: Optional[Any] = auth_principal
        return


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


class _FakeRun:
    def __init__(self, *, run_id: str = "run-1", project_id: str = "proj-1") -> None:
        self.run_id: str = run_id
        self.project_id: str = project_id
        return


class _FakeDecision:
    def __init__(self, *, allowed: bool) -> None:
        self.allowed: bool = allowed
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_check_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(
        runs_events_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _patch_find_run(*, run_row: Optional[Any]) -> Any:
    patch = create_module_patch(runs_events_routes.run_repo, "find_run")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: run_row)
    return patch


def _install_bridge() -> LiveRunBusBridge:
    bridge = LiveRunBusBridge(hub=LiveRunHub())
    runs_events_routes.set_active_live_run_bridge(bridge=bridge)
    return bridge


def _clear_bridge() -> None:
    runs_events_routes.set_active_live_run_bridge(bridge=None)
    return


def _parse_sse_frame(frame: bytes) -> Tuple[str, Dict[str, Any]]:
    """
        Parse one SSE frame into (event_type, data_dict).
    """
    text = frame.decode("utf-8")
    event_type = ""
    data_obj: Dict[str, Any] = {}
    for line in text.splitlines():
        if line.startswith("event: "):
            event_type = line[len("event: "):]
        elif line.startswith("data: "):
            data_obj = json.loads(line[len("data: "):])
    rtnval = (event_type, data_obj)
    return rtnval


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_runs_events_routes_attaches_events_endpoint():
    """
    **Feature: 6-live-run-view PR p19j**
    **Property: register_runs_events_routes attaches the GET
    /api/v1/runs/{run_id}/events method+path pair.**
    """
    app = _FakeApp()
    runs_events_routes.register_runs_events_routes(
        app=app, version_prefix="/api/v1",
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    expected_pairs = (("/api/v1/runs/{run_id}/events", ("GET",)),)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# 503 / 401 / 403 sweep
# ---------------------------------------------------------------------------


def test_handle_run_events_returns_503_when_session_missing():
    """
    **Feature: 6-live-run-view PR p19j**
    **Property: GET /events returns 503 when no db session is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/runs/run-1/events",
        path_params={"run_id": "run-1"},
        db_session=None,
    )
    response = runs_events_routes.handle_run_events(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_handle_run_events_returns_401_when_no_principal():
    """
    **Feature: 6-live-run-view PR p19j**
    **Property: GET /events returns 401 when no AuthPrincipal is bound.**
    """
    request = _FakeRequest(
        path="/api/v1/runs/run-1/events",
        path_params={"run_id": "run-1"},
        db_session=object(),
        auth_principal=None,
    )
    response = runs_events_routes.handle_run_events(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_handle_run_events_returns_403_when_permission_denied():
    """
    **Feature: 6-live-run-view PR p19j**
    **Property: GET /events returns 403 when the principal lacks
    system:runs.read.**
    """
    patch = _patch_check_permission(allowed=False)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/events",
            path_params={"run_id": "run-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = runs_events_routes.handle_run_events(request)
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:runs.read")
    return


def test_handle_run_events_returns_503_when_bridge_not_configured():
    """
    **Feature: 6-live-run-view PR p19j**
    **Property: GET /events returns 503 when the live-run bridge
    has not been constructed by the bootstrap.**
    """
    _clear_bridge()
    perm_patch = _patch_check_permission(allowed=True)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/events",
            path_params={"run_id": "run-1"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = runs_events_routes.handle_run_events(request)
    finally:
        perm_patch.deactivate()
    testbase.assert_equal(response.status_code, 503)
    return


def test_handle_run_events_returns_404_on_unknown_run():
    """
    **Feature: 6-live-run-view PR p19j**
    **Property: GET /events returns 404 problem+json carrying the
    run_id when the run does not exist.**
    """
    _install_bridge()
    perm_patch = _patch_check_permission(allowed=True)
    find_patch = _patch_find_run(run_row=None)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-missing/events",
            path_params={"run_id": "run-missing"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = runs_events_routes.handle_run_events(request)
    finally:
        find_patch.deactivate()
        perm_patch.deactivate()
        _clear_bridge()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["run_id"], "run-missing")
    return


# ---------------------------------------------------------------------------
# Happy path -- 200 text/event-stream
# ---------------------------------------------------------------------------


def test_handle_run_events_returns_event_stream_on_match():
    """
    **Feature: 6-live-run-view PR p19j**
    **Property: GET /events returns 200 with a text/event-stream
    Content-Type when the run exists and auth passes.**
    """
    _install_bridge()
    perm_patch = _patch_check_permission(allowed=True)
    find_patch = _patch_find_run(run_row=_FakeRun(run_id="run-7", project_id="proj-9"))
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-7/events",
            path_params={"run_id": "run-7"},
            db_session=object(),
            auth_principal=_FakePrincipal(),
        )
        response = runs_events_routes.handle_run_events(request)
    finally:
        find_patch.deactivate()
        perm_patch.deactivate()
        _clear_bridge()

    testbase.assert_equal(response.status_code, 200)
    content_type = response._get_all_headers()
    header_map = {key.lower(): value for key, value in content_type}
    testbase.assert_equal(header_map["content-type"], "text/event-stream")
    return


# ---------------------------------------------------------------------------
# Streaming generator -- tested in isolation
# ---------------------------------------------------------------------------


def test_stream_emits_initial_snapshot_frame():
    """
    **Feature: 6-live-run-view PR p19j**
    **Property: The streaming generator yields an initial
    state_changed RunEvent frame so a late-joining client is
    immediately consistent.**
    """
    bridge = LiveRunBusBridge(hub=LiveRunHub())
    stream = runs_events_routes.build_run_events_stream(
        bridge=bridge,
        run_id="run-1",
        project_id="proj-1",
        heartbeat_interval_seconds=0.2,
    )
    try:
        frame = next(stream)
    finally:
        stream.close()
    event_type, data_obj = _parse_sse_frame(frame)
    testbase.assert_equal(event_type, "state_changed")
    testbase.assert_equal(data_obj["run_id"], "run-1")
    testbase.assert_equal(data_obj["event_type"], "state_changed")
    return


def test_stream_delivers_published_state_change():
    """
    **Feature: 6-live-run-view PR p19j**
    **Property: A run-state change published on the hub relay
    reaches a subscribed SSE stream as a state_changed frame.**
    """
    bridge = LiveRunBusBridge(hub=LiveRunHub())
    stream = runs_events_routes.build_run_events_stream(
        bridge=bridge,
        run_id="run-2",
        project_id="proj-2",
        heartbeat_interval_seconds=0.2,
    )
    try:
        _initial = next(stream)
        bridge.hub().publish(
            run_id="run-2",
            project_id="proj-2",
            kind="state_changed",
            payload={"to_state": "running"},
            recorded_at=datetime.now(timezone.utc),
        )
        frame = next(stream)
    finally:
        stream.close()
    event_type, data_obj = _parse_sse_frame(frame)
    testbase.assert_equal(event_type, "state_changed")
    testbase.assert_equal(data_obj["state"], "running")
    return


def test_stream_delivers_published_progress_event():
    """
    **Feature: 6-live-run-view PR p19j**
    **Property: A progress summary published on the hub relay
    reaches a subscribed SSE stream as a progress frame carrying
    the ProgressSummary block.**
    """
    bridge = LiveRunBusBridge(hub=LiveRunHub())
    stream = runs_events_routes.build_run_events_stream(
        bridge=bridge,
        run_id="run-3",
        project_id="proj-3",
        heartbeat_interval_seconds=0.2,
    )
    try:
        _initial = next(stream)
        bridge.hub().publish(
            run_id="run-3",
            project_id="proj-3",
            kind="progress.summary",
            payload={
                "tests_total": 10,
                "tests_passed": 4,
                "tests_failed": 1,
                "tests_skipped": 0,
                "tests_errored": 0,
            },
            recorded_at=datetime.now(timezone.utc),
        )
        frame = next(stream)
    finally:
        stream.close()
    event_type, data_obj = _parse_sse_frame(frame)
    testbase.assert_equal(event_type, "progress")
    testbase.assert_equal(data_obj["event_type"], "progress")
    testbase.assert_equal(data_obj["progress"]["tests_passed"], 4)
    return


def test_stream_emits_heartbeat_when_idle():
    """
    **Feature: 6-live-run-view PR p19j**
    **Property: An idle stream emits a heartbeat RunEvent frame
    after the heartbeat interval elapses with no event.**
    """
    bridge = LiveRunBusBridge(hub=LiveRunHub())
    stream = runs_events_routes.build_run_events_stream(
        bridge=bridge,
        run_id="run-4",
        project_id="proj-4",
        heartbeat_interval_seconds=0.1,
    )
    try:
        _initial = next(stream)
        frame = next(stream)
    finally:
        stream.close()
    event_type, data_obj = _parse_sse_frame(frame)
    testbase.assert_equal(event_type, "heartbeat")
    testbase.assert_equal(data_obj["event_type"], "heartbeat")
    return


def test_stream_close_unsubscribes_from_relay():
    """
    **Feature: 6-live-run-view PR p19j**
    **Property: Closing the streaming generator (client disconnect)
    unsubscribes from the hub relay -- no leaked subscriptions.**
    """
    hub = LiveRunHub()
    bridge = LiveRunBusBridge(hub=hub)
    relay = hub.get_or_create_relay(run_id="run-5", project_id="proj-5")

    stream = runs_events_routes.build_run_events_stream(
        bridge=bridge,
        run_id="run-5",
        project_id="proj-5",
        heartbeat_interval_seconds=0.2,
    )
    _initial = next(stream)
    subscribers_while_open = len(relay._subscribers)
    stream.close()
    subscribers_after_close = len(relay._subscribers)

    testbase.assert_equal(subscribers_while_open, 1)
    testbase.assert_equal(subscribers_after_close, 0)
    return


# ---------------------------------------------------------------------------
# Bus bridge -- bus events forward onto hub relays
# ---------------------------------------------------------------------------


def test_bus_bridge_forwards_state_change_onto_hub_relay():
    """
    **Feature: 6-live-run-view PR p19j**
    **Property: A run-state-change EntityEvent delivered to the
    LiveRunBusBridge is forwarded onto the owning run's hub relay.**
    """
    from ccai.pychestrate.webservice.jobs.run.state.events import (
        RunStateEventTopics,
    )
    from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent

    hub = LiveRunHub()
    bridge = LiveRunBusBridge(hub=hub)

    bridge._on_bus_event(
        EntityEvent(
            topic=RunStateEventTopics.STATE_CHANGED,
            payload={
                "run_id": "run-6",
                "project_id": "proj-6",
                "to_state": "running",
            },
            source_event_id="evt-1",
        ),
    )

    relay = hub.find_relay(run_id="run-6")
    testbase.assert_true(relay is not None)
    history = relay.history()
    testbase.assert_equal(len(history), 1)
    testbase.assert_equal(history[0].kind, "state_changed")
    return
