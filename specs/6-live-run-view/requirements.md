# 6-live-run-view — Requirements

## Introduction

The `6-live-run-view` feature surfaces *streamed* progress for in-flight
runs by fanning out `5-progress-ingest` events to browser clients over
Server-Sent Events (and a fallback long-poll). It is the user's real-time
window on a dispatched job and must mirror the testbase
`ProgressConcentratorServer`/`ForwardingInfo` shapes directly so that a
browser tab renders the same numbers the client agent is reporting.
Ships in **Phase 3** with `6-test-orchestration` and `6-test-catalog`.
The feature owns no execution state — it is a pub/sub fanout that
subscribes to `0-message-bus` for progress events and exposes them to
WebComponents under `9-run-detail-ui`. Authoritative source of truth for
progress is the client agent; this feature is a push-only relay.

## Requirements

### Requirement 1: Live Progress Stream Per Run

**User Story:** As a user who just triggered a run, I want to open its
detail page and see the counts tick up in real time, so that I know the
job is making progress without refreshing.

**Acceptance Criteria (EARS):**

1. WHEN a client opens `GET /api/v1/runs/{run_id}/progress.stream` with `Accept: text/event-stream` THEN the system SHALL respond with an open SSE connection AND SHALL send the last-known `ProgressSnapshot` as the first event within 200 ms.
2. WHEN `5-progress-ingest` emits `progress.updated` on `0-message-bus` for `run_id` THEN the system SHALL forward the delta as an SSE `event: progress` frame to every subscribed client within 250 ms p99.
3. WHILE a client is subscribed AND the underlying run is in a terminal state (`completed`, `failed`, `cancelled`, `completed_no_summary`) the system SHALL send a final `event: terminal` frame with the final snapshot AND close the connection.
4. IF the client reconnects with `Last-Event-ID: <sequence>` THEN the system SHALL replay events with `sequence > Last-Event-ID` from the in-memory ring buffer if available, or send a single `event: resync` frame and the current snapshot if the gap is larger than `max_replay_events` (default 500).
5. WHERE the caller lacks `run.progress.view` on the project THEN the system SHALL return HTTP 403 before upgrading the connection.

### Requirement 2: Long-Poll Fallback

**User Story:** As a user behind a corporate proxy that breaks SSE, I
want a polling endpoint that delivers the same events, so that the run
detail page still works.

**Acceptance Criteria (EARS):**

1. WHEN a client calls `GET /api/v1/runs/{run_id}/progress.longpoll?since=<sequence>&timeout_ms=<n>` THEN the system SHALL either return immediately with all events `sequence > since` OR block up to `timeout_ms` (capped at `max_longpoll_timeout_ms`, default 25 000) until an event arrives.
2. WHEN the ring buffer has been rotated past `since` THEN the system SHALL respond with HTTP 410 and a body `{resync: true, snapshot: ProgressSnapshot}` instructing the client to re-baseline.
3. IF `timeout_ms > max_longpoll_timeout_ms` THEN the system SHALL clamp to the maximum AND include `X-Pychestrate-Effective-Timeout` in the response header.

### Requirement 3: Progress Snapshot Shape Mirrors testbase

**User Story:** As the testbase integration owner, I want the Pychestrate
relay to preserve `ForwardingInfo` shape fields verbatim, so that
downstream renderers can reuse the same schema.

**Acceptance Criteria (EARS):**

1. WHEN a `progress.updated` event is relayed THEN the event body SHALL include `{run_id, sequence, total, completed, passed, failed, skipped, errors, current_test, elapsed_seconds, updated_at}` plus a `forwarding_info_raw: dict` passthrough of the client-supplied frame.
2. WHEN a relay is opened THEN the first `event: snapshot` frame SHALL contain the current aggregated state plus the `sequence` of the last applied event.
3. IF `forwarding_info_raw` contains fields not declared in the canonical snapshot THEN the system SHALL pass them through verbatim without filtering.

### Requirement 4: Backpressure And Fan-Out Bounds

**User Story:** As a service operator, I want the live-run relay bounded
so that a single pathological run cannot consume unbounded memory or CPU.

**Acceptance Criteria (EARS):**

1. WHILE a run has more than `max_subscribers_per_run` (default 256) live subscribers the system SHALL reject new subscriptions with HTTP 429 and a `Retry-After` header.
2. WHEN an SSE client is slower than the publish rate THEN the system SHALL drop the oldest queued frames for that subscriber beyond `max_subscriber_backlog` (default 64) AND SHALL increment `pychestrate_test_live_subscriber_drops_total`.
3. WHEN a run terminates THEN the system SHALL retain its final snapshot in an LRU cache for `terminal_snapshot_ttl_seconds` (default 300) so late openers see the outcome.

## Property-Based Test Requirements

### Property 1: Sequence-Ordered, No-Drop Stream For Timely Subscribers

- **Invariant:** For any run receiving N `progress.updated` events, a subscriber that opened before event 1 and keeps up with the publish rate observes exactly N `event: progress` frames in ascending `sequence` order plus one terminal frame.
- **Generator:** `hypothesis.strategies.integers(min_value=0, max_value=10_000)` for N, paired with a publish rate sampled from `floats(min_value=1.0, max_value=1000.0)` events/sec and a subscriber drain rate ≥ publish rate.
- **Assertion:** Received sequences == `list(range(1, N+1))` and a single terminal frame follows.
- **Sample size:** 1000 generated cases

### Property 2: Replay Is A Subset Of The Ring Buffer

- **Invariant:** For any replay request with `Last-Event-ID = k`, the frames delivered are exactly `{e in ring_buffer : e.sequence > k}` in ascending order, or a `resync` signal if the buffer no longer covers `k`.
- **Generator:** `hypothesis.strategies.tuples(integers(min_value=0, max_value=10_000), integers(min_value=0, max_value=10_000))` as `(buffer_size, events_published)`.
- **Assertion:** Delivered events' `sequence` list equals the intersection of the ring buffer and `(k, +inf)`, sorted ascending; else `resync` is sent and no other events are.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** SSE fan-out latency bus-event → subscriber p99 < 250 ms at 256 subscribers per run and 1 000 runs concurrently. Snapshot first-event latency p99 < 200 ms. Long-poll response latency p99 < 150 ms excluding block time.
- **NFR-2 (Security):** All endpoints behind `run.progress.view` RBAC on the project. SSE tokens scoped by project; `run_id` authorization re-checked on every reconnect. Connection count capped globally by `max_global_live_connections` (default 20 000).
- **NFR-3 (Observability):** Metrics `pychestrate_test_live_subscribers{project}` (gauge), `pychestrate_test_live_fanout_latency_seconds{project}` (histogram), `pychestrate_test_live_frames_sent_total{project,event_type}` (counter), `pychestrate_test_live_subscriber_drops_total{project,reason}` (counter), `pychestrate_test_live_connections_rejected_total{project,reason}` (counter). Log events `pychestrate.test.live.subscriber_opened`, `pychestrate.test.live.subscriber_closed`, `pychestrate.test.live.resync_issued`, `pychestrate.test.live.fanout_overflow`. Trace spans `pychestrate.test.live.fanout`, `pychestrate.test.live.subscribe`.
- **NFR-4 (Reliability):** A bus disconnect SHALL surface as a `event: resync` to every subscriber of affected runs; no silent loss. Service restart SHALL re-hydrate `last snapshot` from `5-progress-ingest`'s durable store before accepting subscriptions.

## Out of Scope

- Final result rendering (see `6-artifact-browser`, `9-run-detail-ui`).
- Multi-run compare (see `6-compare-runs`).
- Log streaming (see `9-wc-log-stream`).
- Per-test case drill-in (owned by `9-run-detail-ui` using testbase stream).

## Dependencies

- **Depends on:** `5-progress-ingest`, `0-message-bus`, `1-rbac`, `6-test-orchestration`, `0-web-app-host` (SSE support).
- **Depended on by:** `9-run-detail-ui`, `9-wc-log-stream`, `9-wc-result-viewer`.
- **Extension points exposed:** None declared by this feature; progress parsing extensibility lives under `factory: progress_parser` in `5-progress-ingest`.
