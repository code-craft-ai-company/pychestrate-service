# 6-live-run-view — Tasks

## Milestones

- **M1 — Skeleton:** `LiveRunHub` + `RunRelay` + SSE endpoint for a single run with ring buffer; first snapshot on connect.
- **M2 — Core Behavior:** Long-poll, resume via `Last-Event-ID`, terminal handling, bus subscriptions for progress and state, subscriber/capacity caps.
- **M3 — Hardening:** Property tests, metrics/logs/traces, back-pressure, `resync` on bus disconnect, perf validation, docs.

## Tasks

### M1 — Skeleton

- [x] T1.1 — Create the `source/site/automojo/pychestrate/webservice/orchestration/test/live/` package per design.md Component Breakdown.
- [x] T1.2 — Implement `snapshot.py` with `ProgressSnapshot`, `ProgressEvent`, delta-merge helper.
      *(``empty_snapshot`` + pure ``merge_event``.)*
- [x] T1.3 — Implement `relay.py::RunRelay` with ring buffer, subscriber set, `publish(event)` and `emit_terminal`.
      *(``deque(maxlen=ring_size)`` ring, thread-safe subscriber
      set, sequence assignment per publish, ``emit_terminal``
      idempotent.)*
- [x] T1.4 — Implement `sse_channel.py` framing (`data:`, `event:`, `id:`, heartbeat every 15 s).
      *(``format_sse_frame`` emits id/event/data + blank-line;
      ``sse_heartbeat_frame`` returns the comment frame.
      ``SSE_HEARTBEAT_INTERVAL_SECONDS`` constant exposed.)*
- [~] T1.5 — Implement `hub.py::LiveRunHub.subscribe_sse` happy path wired to route `GET /api/v1/runs/{id}/progress.stream`.
      *(``LiveRunHub.subscribe_callable`` ships for in-process
      subscribers; the SSE-streaming Flask route lands with the
      Phase-3 REST surface.)*
- [~] T1.6 — Wire the bus subscription to `progress.updated`; append to matching relay and broadcast.
      *(Relay infrastructure ready; bus subscriber that reads
      ``entity.progress.received`` and forwards to the hub
      lands with the M2 wiring.)*
- [~] T1.7 — Implement `GET /api/v1/runs/{id}/progress.snapshot` returning the last known snapshot.
      *(``LiveRunHub.snapshot_for(run_id)`` ships; the REST
      surface follows.)*

### M2 — Core Behavior

- [ ] T2.1 — Implement `longpoll.py` with a condition-variable park/notify and `max_longpoll_timeout_ms` clamping.
- [ ] T2.2 — Register `GET /api/v1/runs/{id}/progress.longpoll` returning `PollResult` JSON.
- [ ] T2.3 — Implement `Last-Event-ID` resume: replay from ring buffer or `event: resync` if gap > `max_replay_events`.
- [ ] T2.4 — Subscribe to `entity.run.state_changed`, `entity.run.completed`, `entity.run.failed`, `entity.run.cancelled`; close relays and promote snapshots into `terminal_cache`.
- [ ] T2.5 — Enforce `max_subscribers_per_run` (429 with `Retry-After`) and `max_global_live_connections` (503).
- [ ] T2.6 — Enforce RBAC `run.progress.view` on every endpoint and on every reconnect.
- [ ] T2.7 — Implement `pod.client.disconnected` subscriber that emits `event: resync` to affected runs.

### M3 — Hardening

- [ ] T3.1 — Implement `max_subscriber_backlog` back-pressure: drop oldest queued frames per subscriber and increment `pychestrate_test_live_subscriber_drops_total`.
- [ ] T3.2 — Emit Prometheus metrics and OTel spans per design.md Observability.
- [ ] T3.3 — Benchmark NFR-1: fan-out p99 < 250 ms at 256 subscribers × 1 000 runs; first snapshot p99 < 200 ms. Fail CI on regression.
- [ ] T3.4 — Enforce `max_frame_bytes` truncation for oversized `forwarding_info_raw`; log truncation at WARNING.
- [ ] T3.5 — Sphinx docs for public HTTP endpoints and `LiveRunHub` internal API.
- [ ] T3.6 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.7 — Hydrate `last_snapshot` from `5-progress-ingest` durable store on service startup before accepting subscriptions.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (ordered no-drop) and Property 2 (replay subset) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 3 scenario — trigger a testbase run, open SSE, observe counts climb, receive terminal, reconnect with `Last-Event-ID = 5`, receive only frames 6..N or `resync`.
- [ ] TT-4 — Extension-point test: N/A for this feature (no extension surface); verify that a new `progress_parser` in `5-progress-ingest` still surfaces through the relay unchanged.
- [ ] TT-5 — Capacity test: open 257 subscribers on one run; 257th receives 429 with `Retry-After`.
- [ ] TT-6 — Slow-subscriber test: publish 10 000 events to a subscriber with a 1 Hz drain rate; subscriber is dropped; fast subscribers still receive every frame.
- [ ] TT-7 — Bus-disconnect test: simulate bus outage; every SSE subscriber receives `event: resync` and the ring buffer resets.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
