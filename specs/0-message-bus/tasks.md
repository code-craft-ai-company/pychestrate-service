# 0-message-bus — Tasks

## Milestones

- **M1 — Skeleton:** In-process bus with publish/subscribe, single worker
  per subscriber, dot-separated exact-match topics (no wildcards), startup
  + shutdown hook wiring.
- **M2 — Core Behavior:** Wildcard patterns (`*` / `#`), overflow
  policies, drain with grace, `request_id` propagation, typed `Event`
  envelope, duplicate-subscriber SemanticError.
- **M3 — Hardening:** Perf validation (NFR-1), metrics + spans, property
  tests, sample extension-hook subscriber, log sampling, subscriber
  isolation chaos test.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/ccai/pychestrate/webservice/messaging/` package skeleton.
- [ ] T1.2 — Implement `messaging/config.py::MessageBusConfig` with fields `topic_buffer_max`, `bus_drain_seconds`, `default_overflow_policy`.
- [ ] T1.3 — Implement `messaging/bus.py::Event` envelope (ULID event_id, UTC microsecond published_at, request_id from ambient ContextVar).
- [ ] T1.4 — Implement `MessageBus.publish` exact-match delivery with zero subscribers (fast path) and per-subscriber queue enqueue.
- [ ] T1.5 — Implement `MessageBus.subscribe` returning `Subscription`; enforce duplicate-`subscriber_name` `SemanticError`.
- [ ] T1.6 — Implement `messaging/worker.py` per-subscriber worker thread loop with catch-once `SubscriberInvocationError`.
- [ ] T1.7 — Implement `messaging/hooks.py` registering startup hook priority `15` and shutdown hook priority `80` on the web app host.
- [ ] T1.8 — Implement `Subscription.unsubscribe` (idempotent, removes from registry and joins worker).

### M2 — Core Behavior

- [ ] T2.1 — Implement `messaging/matcher.py::match_pattern` supporting `*` (single segment) and `#` (multi-segment); pure function for testability.
- [ ] T2.2 — Implement overflow policies `drop_oldest`, `drop_newest`, `block_publisher` with per-topic override.
- [ ] T2.3 — Implement `MessageBus.drain(timeout_seconds)` that closes the bus, joins workers, returns `DrainResult` counts.
- [ ] T2.4 — Emit log events `pychestrate.bus.overflow`, `pychestrate.bus.drain.started`, `pychestrate.bus.drain.completed`, `pychestrate.bus.subscriber.failed`.
- [ ] T2.5 — Wire Prometheus metrics from design.md Observability section.
- [ ] T2.6 — Propagate `request_id` from the web host ContextVar into every published `Event`.
- [ ] T2.7 — Add trace spans `pychestrate.bus.publish` and `pychestrate.bus.deliver` with documented attributes.

### M3 — Hardening

- [ ] T3.1 — Benchmark: zero-subscriber publish p99 < 15 µs, 10-subscriber end-to-end p99 < 250 µs, sustained 50k ev/s on a 4 vCPU runner. Fail CI on regression (NFR-1).
- [ ] T3.2 — Implement log sampling (`pychestrate.bus.published` 1:1000 by default, 1:1 at DEBUG level).
- [ ] T3.3 — Chaos test: one subscriber sleeps 5s per event; assert other subscribers continue and their delivery latency is unaffected.
- [ ] T3.4 — Document topic naming conventions under `usersguide/messaging/` (e.g., `entity.<kind>.<verb>`).
- [ ] T3.5 — Integration hook: wire `0-persistence`'s `entity.<kind>.saved` lifecycle events through the bus once both features are on the same process.
- [ ] T3.6 — Verify multiline error messages use `os.linesep.join([...])`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (per-topic order preservation) and Property 2 (wildcard ↔ regex equivalence), 1000 cases each.
- [ ] TT-3 — Integration test: run persistence + bus together, save an entity, verify an in-test subscriber receives `entity.<kind>.saved` with the right `request_id`.
- [ ] TT-4 — Extension-point test: simulate an `E-extension-hooks` subscriber (`@subscribes_to("entity.project.created")`) registered via `subscribe(subscriber_name="ext-sample.ProjectWatcher.on_created")` and verify delivery, metric labeling, and unsubscribe on extension-unload.
- [ ] TT-5 — Overflow test: publish 20,000 events to a topic with buffer 10,000 and `drop_oldest`; assert exactly 10,000 drops and oldest-first eviction order.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
      (N/A in Phase 0 — a `message_bus_driver` factory is introduced later
      when a network-backed implementation lands)
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
