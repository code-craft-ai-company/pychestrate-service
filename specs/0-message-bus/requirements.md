# 0-message-bus — Requirements

## Introduction

The `0-message-bus` feature provides Pychestrate's internal asynchronous
publish/subscribe backbone for entity events, lifecycle signals, and any
extension-hook-driven reactive behavior. It is an in-process bus by default
(no external broker dependency) with a clean seam for later swap to a
network-backed implementation. The feature ships in **Phase 0** and is the
backbone for `E-extension-hooks` (Phase 0.5) — every topic published on the
bus is a subscription surface for extensions. It sits between
`0-persistence` (which emits `entity.<kind>.saved`) and downstream consumers
like `1-audit-log`, `2-notification-hub`, and `7-metrics-ingest`.

## Requirements

### Requirement 1: Topic-Scoped Publish and Subscribe

**User Story:** As a feature author, I want to publish events on a topic and
receive events on a topic subscription, so that features can decouple
producers from consumers.

**Acceptance Criteria (EARS):**

1. WHEN `bus.publish(topic, payload)` is called THEN the system SHALL
   deliver the payload to every active subscriber whose subscription pattern
   matches `topic`.
2. IF a subscription pattern contains `*` (single segment wildcard) OR `#`
   (multi-segment wildcard) THEN the system SHALL match topics using
   AMQP-style segment rules (`.` as segment separator).
3. WHEN a publish happens AND no subscription matches THEN the system SHALL
   increment `pychestrate_bus_published_total{topic,status="unmatched"}`
   and drop the payload silently (unmatched is not an error).
4. WHERE a subscriber raises an exception the system SHALL catch it,
   reclassify it as `SubscriberInvocationError` with subscriber name and
   topic context, log `pychestrate.bus.subscriber.failed`, and continue
   delivering to remaining subscribers.

### Requirement 2: Ordered Delivery Per Topic With Bounded Buffer

**User Story:** As a consumer of `entity.run.state_changed`, I want events
on the same topic delivered in publish order, so that my state machine does
not process transitions out of sequence.

**Acceptance Criteria (EARS):**

1. WHEN two events `e1` and `e2` are published on the same topic and `e1`
   precedes `e2` on the publisher's wall clock THEN the system SHALL invoke
   every subscriber of that topic for `e1` before `e2`.
2. IF a topic's pending buffer exceeds `topic_buffer_max` (default 10,000)
   THEN the system SHALL apply the topic's configured `overflow_policy`
   (`drop_oldest` | `drop_newest` | `block_publisher`, default `drop_oldest`)
   and increment `pychestrate_bus_overflow_total{topic,policy}`.
3. WHILE a subscriber is slow the system SHALL deliver events to that
   subscriber from its own per-subscriber queue without blocking other
   subscribers of the same topic.
4. WHEN the shutdown hook runs the system SHALL stop accepting new publishes
   and drain all pending events with a grace of `bus_drain_seconds`
   (default 10).

### Requirement 3: Subscriber Registration Lifecycle

**User Story:** As an extension author, I want to register a subscriber
declaratively during `on_load`, so that I do not duplicate wiring code and
the host can unwire me on unload.

**Acceptance Criteria (EARS):**

1. WHEN `bus.subscribe(pattern, handler, subscriber_name)` is called THEN
   the system SHALL return a `Subscription` handle whose `.unsubscribe()`
   atomically removes the subscriber.
2. IF `subscriber_name` is already in use THEN the system SHALL raise
   `SemanticError` (never caught).
3. WHERE `E-extension-hooks` registers handlers via `@subscribes_to(topic)`
   the system SHALL resolve `subscriber_name` as `<ext-name>.<class>.<method>`
   and surface it in all metrics and logs.
4. WHEN an extension is unloaded the system SHALL unsubscribe all of its
   handlers and refuse further deliveries to them.

### Requirement 4: Typed Payload Envelope

**User Story:** As a subscriber, I want every event to carry a typed
envelope with `topic`, `event_id`, `published_at`, `request_id`, and
`payload`, so that cross-cutting concerns (correlation, dedupe, tracing)
are uniform.

**Acceptance Criteria (EARS):**

1. WHEN a publish happens THEN the system SHALL wrap the payload in an
   `Event` with `event_id` (ULID), `topic`, `published_at`, `request_id`
   (from the ambient web request context or `None`), `payload`, and
   `headers: dict[str, str]`.
2. IF a handler is invoked THEN the system SHALL pass the full `Event`
   object (not just the payload) as the sole positional argument.
3. WHERE `request_id` is present on the ambient context at publish time the
   system SHALL propagate it through to every subscriber invocation.

## Property-Based Test Requirements

### Property 1: Per-Topic Order is Preserved Under Interleaved Multi-Topic Publishes

- **Invariant:** For any interleaving of publishes across multiple topics
  with a single subscriber per topic, each topic's subscriber observes its
  events in publish order.
- **Generator:** `hypothesis.strategies.lists(tuples(sampled_from(["a",
  "b", "c", "d"]), integers(min_value=0, max_value=1_000_000)), min_size=1,
  max_size=2000)` where the first element is the topic and the second is a
  monotonically-assigned sequence number per topic.
- **Assertion:** For each topic, the subscriber's received sequence equals
  the sequence of publishes filtered to that topic (strict equality, no
  reorder, no loss under default policy).
- **Sample size:** 1000 generated cases

### Property 2: Wildcard Match is Equivalent to Segment Regex

- **Invariant:** For any topic string and any pattern string, the bus's
  match result equals the pre-computed regex: `*` becomes `[^.]+` and `#`
  becomes `.*`, anchored.
- **Generator:** `hypothesis.strategies.builds(lambda segs, has_hash: (".".
  join(segs), ".".join(segs[:random_split]) + (".#" if has_hash else
  ".*")), lists(text(alphabet=ascii_lowercase, min_size=1, max_size=6),
  min_size=1, max_size=6), booleans())`.
- **Assertion:** `bus._matches(pattern, topic) == bool(regex.fullmatch(topic))`
  for every pair.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** In-process publish of a small payload
  (< 1 KB) with zero subscribers: p99 < 15 microseconds. With 10 active
  subscribers: p99 end-to-end < 250 microseconds. Sustained throughput
  50k events/sec on a 4 vCPU host before applying overflow policy.
- **NFR-2 (Security):** Topics and payloads are process-internal; no
  external exposure in Phase 0. When the network-backed implementation
  lands later, every publish and subscribe MUST carry an authenticated
  principal. Headers MUST NOT include raw secrets — subscribers requiring
  secrets pull from `1-secrets-vault`.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_bus_published_total{topic,status}` (counter),
  `pychestrate_bus_delivery_duration_seconds{topic,subscriber}` (histogram),
  `pychestrate_bus_subscriber_failures_total{topic,subscriber}` (counter),
  `pychestrate_bus_buffer_depth{topic}` (gauge),
  `pychestrate_bus_overflow_total{topic,policy}` (counter).
  Log events `pychestrate.bus.published`, `pychestrate.bus.subscriber.failed`,
  `pychestrate.bus.overflow`, `pychestrate.bus.drain.started`,
  `pychestrate.bus.drain.completed`. Trace span `pychestrate.bus.publish`
  with `topic` and `subscriber_count`; child span
  `pychestrate.bus.deliver` per subscriber invocation.
- **NFR-4 (Reliability):** A slow or crashing subscriber MUST NOT stall
  other subscribers, publishers, or request threads. The bus MUST remain
  available throughout a Postgres outage — it holds no DB state in Phase 0.

## Out of Scope

- Cross-process delivery (single-process only in Phase 0 — multi-process
  requires a backend like NATS/Redis and is deferred).
- At-least-once delivery with durable storage (requires a backend).
- Consumer-groups / competing consumers semantics.
- Admin UI for topic inspection (see `9-admin-ui` Phase 10).
- Authz on topics (deferred to `E-extension-sandbox` Phase 8).

## Dependencies

- **Depends on:** `0-web-app-host` (startup/shutdown hooks, request context
  for `request_id` propagation).
- **Depended on by:** `0-persistence` (forwards `entity.<kind>.saved`),
  `0-system-health`, `0-maintenance-mode`, `1-audit-log`, `2-notification-hub`,
  `3-pod-lifecycle`, `4-checkout-checkin`, `5-run-state-machine`,
  `7-metrics-ingest`, and every feature that publishes or subscribes to
  events.
- **Extension points exposed:** `event: *` — every topic published on the
  bus is a subscription surface for `E-extension-hooks`. The bus itself
  does not declare a factory protocol in Phase 0; a `message_bus_driver`
  factory is a candidate for a future network-backed phase and will be
  defined there.
