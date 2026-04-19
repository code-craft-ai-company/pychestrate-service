# 6-live-run-view — Design

## Architecture

`6-live-run-view` is a pub/sub relay between `5-progress-ingest` and
browser clients. It is not an execution component — it owns no
persistent state other than a per-run in-memory ring buffer of recent
events and an LRU cache of terminal snapshots for late openers. The
relay subscribes to `progress.updated` and `entity.run.state_changed`
on `0-message-bus`, fans those events out to subscribed HTTP clients as
Server-Sent Events, and exposes a long-poll fallback for environments
that break SSE. It sits between Layer 5 (progress ingest) and Layer 9
(`9-run-detail-ui`, `9-wc-log-stream`, `9-wc-result-viewer`). The
authoritative source of truth for progress is the client agent and the
`5-progress-ingest` durable store; the relay is a derived, ephemeral
projection. Ships in Phase 3 as part of the first end-to-end slice.

## Data Model

No persistent entities. In-memory per-run state in a `RunRelay`:

- `run_id: UUID`
- `last_snapshot: ProgressSnapshot | None`
- `last_sequence: int`
- `ring_buffer: deque[ProgressEvent]` — capacity `ring_buffer_size` (default 1024).
- `subscribers: dict[SubscriberId, Subscriber]`
- `state: RunRelayState` — `active` | `terminal` | `closed`.

Global state in `LiveRunHub`:

- `relays: dict[UUID, RunRelay]`
- `terminal_cache: LruCache[UUID, ProgressSnapshot]` (size `terminal_cache_size`, default 4096).
- `global_subscriber_count: int`

Value types:

- `ProgressSnapshot` — `{run_id, sequence, total, completed, passed, failed, skipped, errors, current_test, elapsed_seconds, updated_at, forwarding_info_raw}`.
- `ProgressEvent` — `{sequence, kind: "progress" | "terminal", snapshot, delta}`.

## Interfaces

### Public API

HTTP under `8-rest-api-v1`:

- `GET /api/v1/runs/{run_id}/progress.stream` (SSE) — events `snapshot`, `progress`, `terminal`, `resync`, `heartbeat`.
- `GET /api/v1/runs/{run_id}/progress.longpoll?since=<seq>&timeout_ms=<n>` — JSON `{events: [...], resync?: bool, snapshot?: ProgressSnapshot}`.
- `GET /api/v1/runs/{run_id}/progress.snapshot` — JSON `ProgressSnapshot`.

WebComponent contract: `<px-live-run-view run-id="...">` consumes `progress.stream` and renders counts; events `progress-update`, `run-terminal`, `resync-needed` fire on the element.

### Internal API

```python
class LiveRunHub:
    def __init__(
        self,
        bus: MessageBus,
        rbac: RbacService,
        rerun_state: ProgressDurableStore,
        config: LiveRunConfig,
        clock: Clock
    ) -> None:
        self._bus = bus
        self._rbac = rbac
        self._rerun_state = rerun_state
        self._config = config
        self._clock = clock
        self._relays: dict[UUID, RunRelay] = {}
        self._terminal_cache: LruCache[UUID, ProgressSnapshot] = LruCache(
            capacity=config.terminal_cache_size
        )
        self._global_subscriber_count: int = 0
        return

    def subscribe_sse(
        self,
        actor_id: UUID,
        project_id: UUID,
        run_id: UUID,
        last_event_id: int | None
    ) -> SseChannel:
        """
            Attach a new SSE subscriber and return its channel.

            :param actor_id: Authenticated caller.
            :param project_id: Resolved owning project.
            :param run_id: Run to follow.
            :param last_event_id: Sequence to resume from, if any.

            :returns: SseChannel bound to the subscriber.
            :raises: AuthorizationError, SubscriberCapacityError,
                     RunNotFoundError
        """
        ...

    def poll(
        self,
        actor_id: UUID,
        project_id: UUID,
        run_id: UUID,
        since: int,
        timeout_ms: int
    ) -> PollResult:
        """
            Long-poll for events after `since`.

            :param actor_id: Authenticated caller.
            :param project_id: Resolved owning project.
            :param run_id: Run to follow.
            :param since: Last sequence the client has seen.
            :param timeout_ms: Caller timeout, clamped to config max.

            :returns: PollResult with events or resync directive.
            :raises: AuthorizationError, RunNotFoundError
        """
        ...

    def handle_progress_event(
        self,
        event: ProgressUpdatedBusEvent
    ) -> None:
        """
            Bus subscriber for `progress.updated`; fans out to relays.

            :param event: Bus event with `run_id` and forwarding payload.

            :returns: None.
            :raises: None — errors logged and dropped on a per-subscriber basis.
        """
        ...

    def handle_run_state_event(
        self,
        event: RunStateChangedBusEvent
    ) -> None:
        """
            Bus subscriber for `entity.run.state_changed`; closes relays
            on terminal states and promotes final snapshots into
            terminal_cache.

            :param event: Bus event with `run_id` and state.

            :returns: None.
            :raises: None
        """
        ...
```

### Extension Surface

None declared by this feature. Progress format variability is handled
upstream through `factory: progress_parser` in `5-progress-ingest`.

### Events Emitted

- `pychestrate.test.live.subscriber_opened` (log only, not a bus event).
- `pychestrate.test.live.subscriber_closed`
- `pychestrate.test.live.fanout_overflow`

### Events Consumed

- `progress.updated` (from `5-progress-ingest`) — source of the relay.
- `entity.run.state_changed` (from `5-run-state-machine`) — closes relays on terminal states.
- `entity.run.completed` / `entity.run.failed` / `entity.run.cancelled` — finalize `terminal_cache`.
- `pod.client.disconnected` — emits a `resync` for affected runs.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/orchestration/test/live/`:

- `__init__.py`
- `hub.py` — `LiveRunHub`.
- `relay.py` — `RunRelay` with ring buffer and subscriber management.
- `sse_channel.py` — SSE framing, heartbeats, last-event-id resume.
- `longpoll.py` — long-poll queue and timeout clamping.
- `snapshot.py` — `ProgressSnapshot`, `ProgressEvent` types + delta merge.
- `config.py` — `LiveRunConfig` defaults.
- `rest/v1_routes.py` — route registration.
- `errors.py` — `SubscriberCapacityError`, `RunNotFoundError`.

## Key Flows

### Flow 1 — Subscribe and stream

1. Browser requests `GET /api/v1/runs/{id}/progress.stream`.
2. Route calls `LiveRunHub.subscribe_sse(...)`.
3. RBAC check `run.progress.view`.
4. If no `RunRelay` exists, hub loads the last snapshot from the durable store, builds one, and keeps it warm.
5. Subscriber registered; first frame = current snapshot.
6. Hub subscribes to the bus at startup; each `progress.updated` event applies to the relay, appends to the ring buffer, broadcasts to subscribers.
7. On terminal, a final `event: terminal` frame is sent and the connection closes.

### Flow 2 — Long-poll

1. Client issues `GET /api/v1/runs/{id}/progress.longpoll?since=42&timeout_ms=25000`.
2. Hub validates RBAC, resolves relay.
3. If ring buffer has any events with `sequence > 42`, respond immediately.
4. If the ring no longer covers `42`, respond 410 with `{resync: true, snapshot}`.
5. Otherwise, park the request on a condition variable; wake on next append or timeout.
6. Timeout clamped to `max_longpoll_timeout_ms` with `X-Pychestrate-Effective-Timeout` echoed.

### Flow 3 — Resubscribe after bus disconnect

1. Bus client reports `disconnected`.
2. Hub marks every active relay as needing a resync.
3. Every SSE subscriber receives `event: resync` with the latest snapshot; ring buffer is reset.
4. When bus reconnects, subsequent `progress.updated` events resume with fresh sequence numbers beginning `last_sequence + 1`.

## Error Handling

- `AuthorizationError`: 403 before the SSE upgrade (headers only).
- `SubscriberCapacityError`: 429 with `Retry-After`.
- `RunNotFoundError`: 404.
- Bus subscriber errors (JSON parse, unknown event type): caught and reclassified with a multiline log event; the bus client continues.
- `SemanticError` from negative `since` or malformed `last_event_id`: bubble.
- Slow-subscriber drops: counted, logged at DEBUG, never block the publisher.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- SSE requires the same auth as REST; no anonymous access.
- Per-subscriber identity revalidated on any reconnect; a revoked session is dropped within the heartbeat interval (default 15 s).
- Global connection cap `max_global_live_connections` (default 20 000) to protect the event loop.
- No secrets exist in progress payloads; `forwarding_info_raw` is bounded by `max_frame_bytes` (default 32 KiB) with oversize frames truncated and logged.

## Observability

Metrics:

- `pychestrate_test_live_subscribers{project}` — gauge
- `pychestrate_test_live_fanout_latency_seconds{project}` — histogram
- `pychestrate_test_live_frames_sent_total{project,event_type}` — counter
- `pychestrate_test_live_subscriber_drops_total{project,reason}` — counter
- `pychestrate_test_live_connections_rejected_total{project,reason}` — counter
- `pychestrate_test_live_terminal_cache_hits_total{project}` — counter

Log events: `pychestrate.test.live.subscriber_opened`, `pychestrate.test.live.subscriber_closed`, `pychestrate.test.live.resync_issued`, `pychestrate.test.live.fanout_overflow`.

Trace spans: `pychestrate.test.live.fanout`, `pychestrate.test.live.subscribe`, `pychestrate.test.live.longpoll`.

## Open Questions

- SSE heartbeat interval — 15 s vs 30 s. Timebox: Phase 3 midpoint after measuring idle-connection churn.
- Should we expose WebSocket as a second transport or stick with SSE + long-poll? Timebox: Phase 5 (when more WebComponents land).
- Ring buffer size per run — 1024 may be too generous for very large matrices. Timebox: Phase 5 with `6-matrix-sharding`.
