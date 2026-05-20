"""
.. module:: runs.restapi.v1.runs_events_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native SSE route for GET /api/v1/runs/{run_id}/events.

.. moduleauthor:: Automation Mojo LLC

This module hosts one planned operation from
``specs/openapi/pychestrate.yaml``:

* ``GET /api/v1/runs/{run_id}/events`` (tag: runs)

The endpoint is a long-lived ``text/event-stream`` (Server-Sent
Events) response. The future run-detail UI (PR M) opens an
``EventSource`` against it to stream live run progress.

Each SSE frame's ``data:`` payload is a JSON document conforming to
the OpenAPI ``RunEvent`` schema; the SSE ``event:`` line carries the
event type (``state_changed`` | ``progress`` | ``result_manifest`` |
``heartbeat``).

Threading model
---------------

WebWorks runs on a synchronous WSGI worker pool (gunicorn threads).
A streaming SSE connection holds one worker thread for the lifetime
of the connection -- exactly like the long-poll dispatch transport
(PR p19g). For the alpha "few viewers" target this is acceptable;
production scale-out needs async workers. The generator is bounded
only by the client disconnecting -- when the WSGI server stops
pulling frames the generator's ``finally`` block runs and the hub
subscription is released, so no subscription leaks.

The route reads the process-singleton :class:`LiveRunBusBridge`
constructed at startup by ``phase6_bootstrap.bootstrap_live_run_view``
through the module-level ``ACTIVE_LIVE_RUN_BRIDGE`` seam.

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import logging
import queue
import threading

from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import Response, StreamingResponse

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.jobs.run.state import repository as run_repo
from automojo.pychestrate.webservice.orchestration.test.live.bus_bridge import (
    LiveRunBusBridge,
)
from automojo.pychestrate.webservice.orchestration.test.live.snapshot import (
    ProgressEvent,
    ProgressSnapshot,
)
from automojo.pychestrate.webservice.runs.restapi.v1.runs_routes import (
    RUNS_PATH,
    RUNS_READ_PERMISSION_KEY,
)
from automojo.pychestrate.webservice.security.rbac import rbac_evaluator


#: Seconds between heartbeat frames. Keeps proxies + EventSource
#: clients from treating an idle stream as dead. Mirrors the
#: live-hub ``SSE_HEARTBEAT_INTERVAL_SECONDS`` constant.
SSE_HEARTBEAT_INTERVAL_SECONDS: int = 15

#: How long the streaming generator blocks waiting for the next
#: relay event before it emits a heartbeat instead. Equal to the
#: heartbeat interval so an idle stream heartbeats on schedule.
_EVENT_WAIT_TIMEOUT_SECONDS: float = float(SSE_HEARTBEAT_INTERVAL_SECONDS)

#: Module-level seam: the active :class:`LiveRunBusBridge`. Set by
#: ``phase6_bootstrap.bootstrap_live_run_view`` at startup. When it
#: is ``None`` the route answers 503 -- the documented "live view
#: not configured" behaviour.
ACTIVE_LIVE_RUN_BRIDGE: Optional[LiveRunBusBridge] = None

_LOGGER = logging.getLogger("pychestrate.runs.events.routes")


def set_active_live_run_bridge(*, bridge: Optional[LiveRunBusBridge]) -> None:
    """
        Publish the process-singleton :class:`LiveRunBusBridge` on
        the module seam the SSE route reads.

        :param bridge: The constructed bridge, or ``None`` to clear
                       the seam (tests use ``None`` to assert the
                       503 path).

        :returns: None.
    """
    global ACTIVE_LIVE_RUN_BRIDGE
    ACTIVE_LIVE_RUN_BRIDGE = bridge
    return


# ---------------------------------------------------------------------------
# Problem-flow plumbing
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
    """
        Internal control-flow exception carrying a webworks problem
        response so the top-level handler can convert it to a
        return value at the boundary.
    """

    def __init__(self, response: Response) -> None:
        super().__init__("problem abort")
        self.response: Response = response
        return


def _abort_problem(
        *,
        request: Request,
        status: int,
        detail: str,
        extensions: Optional[Dict[str, Any]] = None
    ) -> None:
    """
        Build a problem response and raise :class:`_ProblemAbort`.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param extensions: Optional namespaced extension members.

        :returns: Never returns.
    """
    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _resolve_db_session(request: Request) -> Optional[Any]:
    """
        Return the request-scoped db session attached by the
        session middleware, or ``None`` when none is bound.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _resolve_auth_principal(request: Request) -> Optional[Any]:
    """
        Return the ``AuthPrincipal`` attached to the request by the
        session middleware, or ``None`` when anonymous.

        :param request: Incoming webworks request.

        :returns: AuthPrincipal or None.
    """
    rtnval = getattr(request, "auth_principal", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort 503.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session.
    """
    db_session = _resolve_db_session(request=request)
    if db_session is None:
        _abort_problem(
            request=request,
            status=503,
            detail="Request-scoped db_session not configured",
        )
    rtnval = db_session
    return rtnval


def _require_runs_read_permission(*, request: Request, db_session: Any) -> None:
    """
        Require the calling principal to hold ``system:runs.read``.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.

        :returns: None.
    """
    principal = _resolve_auth_principal(request=request)
    if principal is None:
        _abort_problem(
            request=request,
            status=401,
            detail="Authentication required.",
        )

    now = datetime.now(timezone.utc)
    decision = rbac_evaluator.check_permission(
        db_session=db_session,
        principal=principal,
        permission_key=RUNS_READ_PERMISSION_KEY,
        now=now,
    )
    if decision.allowed is False:
        _abort_problem(
            request=request,
            status=403,
            detail="Permission denied: {}".format(RUNS_READ_PERMISSION_KEY),
            extensions={"required_permission": RUNS_READ_PERMISSION_KEY},
        )
    return


def _require_active_bridge(request: Request) -> LiveRunBusBridge:
    """
        Resolve the process-singleton :class:`LiveRunBusBridge`, or
        abort 503 when the live-view bootstrap has not run.

        :param request: Incoming webworks request.

        :returns: The active :class:`LiveRunBusBridge`.
    """
    bridge = ACTIVE_LIVE_RUN_BRIDGE
    if bridge is None:
        _abort_problem(
            request=request,
            status=503,
            detail="Live run-view bridge is not configured.",
        )
    rtnval = bridge
    return rtnval


# ---------------------------------------------------------------------------
# RunEvent frame formatting (OpenAPI RunEvent schema shape)
# ---------------------------------------------------------------------------


def _classify_event_type(*, kind: str) -> str:
    """
        Map a relay event ``kind`` onto the OpenAPI ``RunEvent``
        ``event_type`` enum value.

        :param kind: Relay event kind tag.

        :returns: One of ``state_changed`` / ``progress`` /
                  ``result_manifest`` / ``heartbeat``.
    """
    if kind.startswith("progress") is True:
        rtnval = "progress"
        return rtnval
    if kind.startswith("result") is True:
        rtnval = "result_manifest"
        return rtnval
    if kind == "heartbeat":
        rtnval = "heartbeat"
        return rtnval
    rtnval = "state_changed"
    return rtnval


def _progress_block(*, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
        Build the optional ``progress`` block of a ``RunEvent`` from
        a progress-bearing payload, or ``None`` when the payload
        carries no counter fields.

        :param payload: Bus / relay event payload.

        :returns: A ``ProgressSummary``-shaped dict, or None.
    """
    counter_keys = (
        "tests_total",
        "tests_passed",
        "tests_failed",
        "tests_skipped",
        "tests_errored",
        "percent_complete",
    )
    has_counter = False
    for key in counter_keys:
        if key in payload:
            has_counter = True
            break
    if has_counter is False:
        rtnval = None
        return rtnval

    rtnval = {
        "run_id": payload.get("run_id"),
        "client_id": payload.get("client_id"),
        "format_tag": payload.get("format_tag", "testbase"),
        "tests_total": payload.get("tests_total"),
        "tests_passed": int(payload.get("tests_passed", 0)),
        "tests_failed": int(payload.get("tests_failed", 0)),
        "tests_skipped": int(payload.get("tests_skipped", 0)),
        "tests_errored": int(payload.get("tests_errored", 0)),
        "percent_complete": payload.get("percent_complete"),
        "recorded_at": payload.get("received_at", payload.get("recorded_at")),
    }
    return rtnval


def _run_event_body(*, event: ProgressEvent) -> Dict[str, Any]:
    """
        Render a relay :class:`ProgressEvent` as a ``RunEvent``
        JSON object matching ``components/schemas/RunEvent``.

        :param event: Relay event to render.

        :returns: A JSON-serializable ``RunEvent`` dict.
    """
    payload: Dict[str, Any] = dict(event.payload)
    event_type = _classify_event_type(kind=event.kind)

    rtnval: Dict[str, Any] = {
        "run_id": event.run_id,
        "event_type": event_type,
        "sequence": event.sequence,
        "occurred_at": event.recorded_at.isoformat(),
        "state": None,
        "terminal_outcome": None,
        "progress": None,
        "manifest": None,
    }

    state_value = payload.get("to_state", payload.get("state", None))
    if isinstance(state_value, str) and len(state_value) > 0:
        rtnval["state"] = state_value

    terminal_value = payload.get("terminal_outcome", None)
    if isinstance(terminal_value, str) and len(terminal_value) > 0:
        rtnval["terminal_outcome"] = terminal_value

    if event_type == "progress":
        rtnval["progress"] = _progress_block(payload=payload)

    if event_type == "result_manifest":
        manifest = payload.get("manifest", None)
        if isinstance(manifest, dict):
            rtnval["manifest"] = manifest

    return rtnval


def _snapshot_event(*, snapshot: ProgressSnapshot) -> ProgressEvent:
    """
        Build the synthetic initial ``state_changed`` event a
        late-joining subscriber receives so it is immediately
        consistent with the run's current progress.

        :param snapshot: The relay's current :class:`ProgressSnapshot`.

        :returns: A :class:`ProgressEvent` carrying the snapshot.
    """
    payload: Dict[str, Any] = {
        "run_id": snapshot.run_id,
        "project_id": snapshot.project_id,
        "state": snapshot.state,
        "tests_total": snapshot.tests_total,
        "tests_passed": snapshot.tests_passed,
        "tests_failed": snapshot.tests_failed,
        "tests_skipped": snapshot.tests_skipped,
        "tests_errored": snapshot.tests_errored,
        "percent_complete": snapshot.percent_complete,
    }
    rtnval = ProgressEvent(
        run_id=snapshot.run_id,
        project_id=snapshot.project_id,
        kind="state_changed",
        payload=payload,
        recorded_at=snapshot.latest_event_at,
        sequence=snapshot.sequence,
    )
    return rtnval


def format_run_event_frame(*, event: ProgressEvent) -> bytes:
    """
        Render a relay :class:`ProgressEvent` as one SSE wire frame
        (UTF-8 bytes). Format::

            id: <sequence>
            event: <event_type>
            data: <RunEvent json>

        followed by a blank line.

        :param event: Relay event to render.

        :returns: UTF-8 frame bytes.
    """
    body = _run_event_body(event=event)
    rtnval = (
        "id: {}\n"
        "event: {}\n"
        "data: {}\n\n"
    ).format(
        event.sequence,
        body["event_type"],
        json.dumps(body, ensure_ascii=False, sort_keys=True),
    ).encode("utf-8")
    return rtnval


def format_heartbeat_frame(*, run_id: str, sequence: int) -> bytes:
    """
        Render a ``heartbeat`` ``RunEvent`` SSE frame. A heartbeat
        keeps proxies + clients from treating an idle stream as
        dead and lets a client detect a half-open connection.

        :param run_id: Run UUID the stream belongs to.
        :param sequence: Last-seen relay sequence (echoed back so a
                         reconnecting client can resume).

        :returns: UTF-8 heartbeat frame bytes.
    """
    body = {
        "run_id": run_id,
        "event_type": "heartbeat",
        "sequence": sequence,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "state": None,
        "terminal_outcome": None,
        "progress": None,
        "manifest": None,
    }
    rtnval = (
        "event: heartbeat\n"
        "data: {}\n\n"
    ).format(
        json.dumps(body, ensure_ascii=False, sort_keys=True),
    ).encode("utf-8")
    return rtnval


# ---------------------------------------------------------------------------
# Streaming generator
# ---------------------------------------------------------------------------


def build_run_events_stream(
        *,
        bridge: LiveRunBusBridge,
        run_id: str,
        project_id: str,
        heartbeat_interval_seconds: float = _EVENT_WAIT_TIMEOUT_SECONDS
    ) -> Iterator[bytes]:
    """
        Build the SSE frame generator for one ``GET
        /api/v1/runs/{run_id}/events`` connection.

        The generator:

        1. yields an initial ``state_changed`` frame carrying the
           relay's current snapshot so a late-joining client is
           immediately consistent;
        2. subscribes the run's relay through the hub and yields a
           frame for every event the relay broadcasts;
        3. yields a ``heartbeat`` frame whenever
           ``heartbeat_interval_seconds`` elapse with no event;
        4. unsubscribes from the relay in a ``finally`` block when
           the consumer (the WSGI server, on client disconnect)
           stops iterating -- so no hub subscription leaks.

        The generator is testable in isolation: feed events to the
        hub relay for ``run_id`` and assert on the yielded frames.

        :param bridge: The active :class:`LiveRunBusBridge` whose
                       hub holds the per-run relays.
        :param run_id: Run UUID the stream belongs to.
        :param project_id: Owning project UUID (used to construct
                           the relay on first subscribe).
        :param heartbeat_interval_seconds: Idle interval after
                                           which a heartbeat is
                                           emitted.

        :returns: Iterator of SSE frame byte chunks.
    """
    hub = bridge.hub()
    relay = hub.get_or_create_relay(run_id=run_id, project_id=project_id)

    # The relay broadcasts on the publisher's thread; a bounded
    # thread-safe queue decouples the publisher from this WSGI
    # worker so a slow client can never block the bus.
    event_queue: "queue.Queue[ProgressEvent]" = queue.Queue(maxsize=1024)

    def _on_relay_event(event: ProgressEvent) -> None:
        try:
            event_queue.put_nowait(event)
        except queue.Full:
            # A consumer this far behind has effectively dropped the
            # stream; silently discard rather than block the bus.
            return
        return

    unsubscribe = relay.subscribe(callback=_on_relay_event)

    last_sequence = 0
    try:
        snapshot = relay.snapshot()
        initial_event = _snapshot_event(snapshot=snapshot)
        last_sequence = initial_event.sequence
        yield format_run_event_frame(event=initial_event)

        while True:
            try:
                event = event_queue.get(timeout=heartbeat_interval_seconds)
            except queue.Empty:
                yield format_heartbeat_frame(
                    run_id=run_id, sequence=last_sequence,
                )
                continue

            last_sequence = event.sequence
            yield format_run_event_frame(event=event)
    finally:
        unsubscribe()
        _LOGGER.info(
            "pychestrate.runs.events.stream_closed run_id=%s last_sequence=%d",
            run_id,
            last_sequence,
        )
    return


# ---------------------------------------------------------------------------
# GET /api/v1/runs/{run_id}/events
# ---------------------------------------------------------------------------


def handle_run_events(request: Request) -> Response:
    """
        ``GET /api/v1/runs/{run_id}/events`` -- subscribe to a
        run's live events via Server-Sent Events.

        Returns a long-lived ``text/event-stream`` streaming
        response on success, or an RFC 7807 problem response on
        validation / auth failure.

        :param request: Incoming webworks request.

        :returns: :class:`StreamingResponse` (200) or a problem
                  :class:`Response`.
    """
    run_id = request.path_params.get("run_id", "")
    try:
        db_session = _require_session(request=request)
        _require_runs_read_permission(
            request=request, db_session=db_session,
        )
        bridge = _require_active_bridge(request=request)

        run_row = run_repo.find_run(db_session=db_session, run_id=run_id)
        if run_row is None:
            _abort_problem(
                request=request,
                status=404,
                detail="Run not found.",
                extensions={"run_id": run_id},
            )
            run_row = None  # unreachable -- _abort_problem raises.

        project_id = str(run_row.project_id)

        stream = build_run_events_stream(
            bridge=bridge,
            run_id=run_id,
            project_id=project_id,
        )

        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        rtnval: Response = StreamingResponse(
            content=stream,
            status_code=200,
            headers=headers,
            media_type="text/event-stream",
        )

        _LOGGER.info(
            "pychestrate.runs.events.stream_opened run_id=%s project_id=%s",
            run_id,
            project_id,
        )
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_runs_events_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the run live-events SSE route to a webworks
        application.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + RUNS_PATH
    app.attach_route(
        base + "/{run_id}/events", methods=["GET"],
    )(handle_run_events)
    return


__all__ = [
    "SSE_HEARTBEAT_INTERVAL_SECONDS",
    "ACTIVE_LIVE_RUN_BRIDGE",
    "set_active_live_run_bridge",
    "format_run_event_frame",
    "format_heartbeat_frame",
    "build_run_events_stream",
    "handle_run_events",
    "register_runs_events_routes",
]
