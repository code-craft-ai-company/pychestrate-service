"""
.. module:: test_p20t_build_provision_progress_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for generalized build / provision progress frames.

.. moduleauthor:: Code Craft AI LLC

Covers PR p20t -- generalized progress frames for build + provision
live streaming:

* POST /runs/{id}/progress accepts a ``frame_kind=build`` frame.
* POST /runs/{id}/progress accepts a ``frame_kind=provision`` frame.
* POST /runs/{id}/progress accepts a ``frame_kind=test`` frame
  (backward compat) and a body with no ``frame_kind`` at all.
* A build frame missing ``frame`` / ``frames`` is rejected 400.
* An unknown ``frame_kind`` is rejected 400.
* The SSE events route forwards a build progress frame as a
  ``progress`` RunEvent.
* The snapshot of a late-joining subscriber includes the latest
  build / provision progress frame.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.orchestration.test.live.bus_bridge import (
    LiveRunBusBridge,
)
from ccai.pychestrate.webservice.orchestration.test.live.hub import (
    LiveRunHub,
)
from ccai.pychestrate.webservice.orchestration.test.live.snapshot import (
    ProgressEvent,
    empty_snapshot,
    merge_event,
)
from ccai.pychestrate.webservice.runs.restapi.v1 import (
    runs_events_routes,
    runs_routes,
)


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(
        self,
        *,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        body: Any = None,
        db_session: Optional[Any] = None,
        mtls_client_cn: Optional[str] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self._body: Any = body
        self.db_session: Optional[Any] = db_session
        if mtls_client_cn is not None:
            self.mtls_client_cn: str = mtls_client_cn
        return

    def json(self) -> Any:
        return self._body


class _FakeRun:
    def __init__(self, *, run_id: str = "run-1") -> None:
        self.run_id: str = run_id
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_find_run(*, exists: bool) -> Any:
    patch = create_module_patch(runs_routes.run_repo, "find_run")
    mock = patch.activate()
    if exists is True:
        mock.configure(side_effect=lambda **kwargs: _FakeRun())
    else:
        mock.configure(side_effect=lambda **kwargs: None)
    return patch


def _parse_sse_frame(frame: bytes) -> Any:
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
# POST /runs/{id}/progress -- frame_kind acceptance
# ---------------------------------------------------------------------------


def test_progress_accepts_build_frame():
    """
    **Feature: 6-live-run-view PR p20t**
    **Property: POST /runs/{id}/progress accepts a frame_kind=build
    ProgressFrame, routes the frame to progress_service.ingest_frame,
    and returns 202 with frames_accepted=1.**
    """
    captured: Dict[str, Any] = {}

    def fake_ingest_frame(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return object()

    run_patch = _patch_find_run(exists=True)
    svc_patch = create_module_patch(runs_routes.progress_service, "ingest_frame")
    svc_mock = svc_patch.activate()
    svc_mock.configure(side_effect=fake_ingest_frame)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/progress",
            path_params={"run_id": "run-1"},
            body={
                "frame_kind": "build",
                "frame": {
                    "client_id": "client-7",
                    "frame_index": 0,
                    "phase": "building",
                    "status": "running",
                    "percent_complete": 40.0,
                    "payload": {"log_excerpt": "compiling module foo"},
                },
            },
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_post_progress(request)
    finally:
        svc_patch.deactivate()
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 202)
    body = _decode_body(response)
    testbase.assert_equal(body["frame_kind"], "build")
    testbase.assert_equal(body["frames_accepted"], 1)
    testbase.assert_equal(captured["frame_kind"], "build")
    testbase.assert_equal(captured["frame_index"], 0)
    testbase.assert_equal(captured["authenticated_client_id"], "client-7")
    return


def test_progress_accepts_provision_frame():
    """
    **Feature: 6-live-run-view PR p20t**
    **Property: POST /runs/{id}/progress accepts a
    frame_kind=provision ProgressFrame carrying a frames array and
    returns 202 with the accepted count.**
    """
    calls = []

    def fake_ingest_frame(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return object()

    run_patch = _patch_find_run(exists=True)
    svc_patch = create_module_patch(runs_routes.progress_service, "ingest_frame")
    svc_mock = svc_patch.activate()
    svc_mock.configure(side_effect=fake_ingest_frame)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/progress",
            path_params={"run_id": "run-1"},
            body={
                "frame_kind": "provision",
                "frames": [
                    {
                        "client_id": "client-9",
                        "frame_index": 0,
                        "phase": "plan",
                        "status": "succeeded",
                    },
                    {
                        "client_id": "client-9",
                        "frame_index": 1,
                        "phase": "apply",
                        "status": "running",
                    },
                ],
            },
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_post_progress(request)
    finally:
        svc_patch.deactivate()
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 202)
    body = _decode_body(response)
    testbase.assert_equal(body["frame_kind"], "provision")
    testbase.assert_equal(body["frames_accepted"], 2)
    testbase.assert_equal(len(calls), 2)
    return


def test_progress_test_frame_backward_compatible():
    """
    **Feature: 6-live-run-view PR p20t**
    **Property: A ProgressFrame with no frame_kind defaults to the
    test path -- the legacy summary body still flows to
    ingest_summary and returns 202 (backward compat).**
    """
    captured: Dict[str, Any] = {}

    def fake_ingest_summary(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return object()

    run_patch = _patch_find_run(exists=True)
    svc_patch = create_module_patch(runs_routes.progress_service, "ingest_summary")
    svc_mock = svc_patch.activate()
    svc_mock.configure(side_effect=fake_ingest_summary)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/progress",
            path_params={"run_id": "run-1"},
            body={"summary": {
                "run_id": "run-1",
                "client_id": "client-7",
                "format_tag": "testbase",
                "tests_passed": 1,
                "tests_failed": 0,
                "tests_skipped": 0,
                "tests_errored": 0,
                "recorded_at": "2026-05-20T12:00:00+00:00",
            }},
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_post_progress(request)
    finally:
        svc_patch.deactivate()
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 202)
    body = _decode_body(response)
    testbase.assert_equal(body["frame_kind"], "test")
    testbase.assert_equal(body["summaries_accepted"], 1)
    testbase.assert_equal(captured["authenticated_client_id"], "client-7")
    return


def test_progress_build_frame_missing_frame_is_rejected():
    """
    **Feature: 6-live-run-view PR p20t**
    **Property: A frame_kind=build ProgressFrame with neither
    'frame' nor 'frames' is rejected with 400.**
    """
    patch = _patch_find_run(exists=True)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/progress",
            path_params={"run_id": "run-1"},
            body={"frame_kind": "build"},
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_post_progress(request)
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    return


def test_progress_unknown_frame_kind_is_rejected():
    """
    **Feature: 6-live-run-view PR p20t**
    **Property: A ProgressFrame with an unrecognized frame_kind is
    rejected with 400.**
    """
    patch = _patch_find_run(exists=True)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/progress",
            path_params={"run_id": "run-1"},
            body={"frame_kind": "deploy", "frame": {}},
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_post_progress(request)
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["frame_kind"], "deploy")
    return


# ---------------------------------------------------------------------------
# SSE forwarding -- a build frame becomes a `progress` RunEvent
# ---------------------------------------------------------------------------


def test_stream_delivers_published_build_progress_frame():
    """
    **Feature: 6-live-run-view PR p20t**
    **Property: A build progress frame published on the hub relay
    reaches a subscribed SSE stream as a `progress` RunEvent
    carrying the generalized build progress block.**
    """
    bridge = LiveRunBusBridge(hub=LiveRunHub())
    stream = runs_events_routes.build_run_events_stream(
        bridge=bridge,
        run_id="run-b1",
        project_id="proj-b1",
        heartbeat_interval_seconds=0.2,
    )
    try:
        _initial = next(stream)
        bridge.hub().publish(
            run_id="run-b1",
            project_id="proj-b1",
            kind="progress.frame",
            payload={
                "run_id": "run-b1",
                "frame_kind": "build",
                "frame_index": 2,
                "phase": "packaging",
                "status": "running",
                "percent_complete": 75.0,
                "payload": {"log_excerpt": "writing artifact"},
            },
            recorded_at=datetime.now(timezone.utc),
        )
        frame = next(stream)
    finally:
        stream.close()
    event_type, data_obj = _parse_sse_frame(frame)
    testbase.assert_equal(event_type, "progress")
    testbase.assert_equal(data_obj["event_type"], "progress")
    progress = data_obj["progress"]
    testbase.assert_equal(progress["frame_kind"], "build")
    testbase.assert_equal(progress["phase"], "packaging")
    testbase.assert_equal(progress["percent_complete"], 75.0)
    return


def test_snapshot_includes_latest_build_progress_frame():
    """
    **Feature: 6-live-run-view PR p20t**
    **Property: A build progress frame merged into a run's snapshot
    is retained as latest_progress_frame so a late-joining SSE
    subscriber's initial frame shows the latest build progress.**
    """
    snapshot = empty_snapshot(run_id="run-b2", project_id="proj-b2")
    event = ProgressEvent(
        run_id="run-b2",
        project_id="proj-b2",
        kind="progress.frame",
        payload={
            "frame_kind": "provision",
            "frame_index": 0,
            "phase": "apply",
            "status": "running",
            "percent_complete": 50.0,
        },
        recorded_at=datetime.now(timezone.utc),
        sequence=1,
    )
    merged = merge_event(snapshot=snapshot, event=event)
    testbase.assert_true(merged.latest_progress_frame is not None)
    testbase.assert_equal(merged.latest_progress_frame["phase"], "apply")
    testbase.assert_equal(merged.percent_complete, 50.0)
    return


def test_stream_initial_frame_carries_latest_build_progress():
    """
    **Feature: 6-live-run-view PR p20t**
    **Property: When a build progress frame has already landed, a
    newly-attached SSE subscriber's initial synthetic frame is a
    `progress` RunEvent carrying the latest build progress.**
    """
    hub = LiveRunHub()
    bridge = LiveRunBusBridge(hub=hub)
    hub.publish(
        run_id="run-b3",
        project_id="proj-b3",
        kind="progress.frame",
        payload={
            "run_id": "run-b3",
            "frame_kind": "build",
            "frame_index": 0,
            "phase": "cloning",
            "status": "running",
        },
        recorded_at=datetime.now(timezone.utc),
    )
    stream = runs_events_routes.build_run_events_stream(
        bridge=bridge,
        run_id="run-b3",
        project_id="proj-b3",
        heartbeat_interval_seconds=0.2,
    )
    try:
        frame = next(stream)
    finally:
        stream.close()
    event_type, data_obj = _parse_sse_frame(frame)
    testbase.assert_equal(event_type, "progress")
    testbase.assert_equal(data_obj["progress"]["frame_kind"], "build")
    testbase.assert_equal(data_obj["progress"]["phase"], "cloning")
    return
