# E-extension-hooks — Requirements

## Introduction

E-extension-hooks is the reactive, bus-subscriber extension surface
parallel to `E-factory-protocols`' override surface. Where factories
are called-by-consumer, hooks are fired-by-event: an extension class
declares one or more `@subscribes_to("entity.job.completed")`-style
subscriptions, and the host wires them to `0-message-bus` at load time.
This feature ships in Phase 1 alongside `E-extension-config`, after
`0-message-bus` exists.

## Requirements

### Requirement 1: Subscription declaration metadata

**User Story:** As an extension author, I want a single decorator to
mark a classmethod as a bus subscriber, so that the host automatically
wires my method without me touching the bus directly.

**Acceptance Criteria (EARS):**

1. WHEN a classmethod is decorated with `@subscribes_to(topic="entity.job.completed",
   aspects=...)` THEN the system SHALL attach subscription metadata to
   the method (topic, aspects) without modifying its behavior.
2. IF a classmethod is decorated with `@subscribes_to` but its
   enclosing class is not a `FactoryExtension` or `ResourceExtension`
   THEN the system SHALL ignore the decorator and emit
   `pychestrate_extension_hook_orphan` warning.
3. WHERE a topic pattern contains wildcards (`entity.job.*`) THEN the
   system SHALL subscribe using the bus's pattern semantics.

### Requirement 2: Automatic wiring at load time

**User Story:** As a service operator, I want bus subscriptions wired
at extension load time and torn down at unload, so that subscription
state always reflects the loaded extension set.

**Acceptance Criteria (EARS):**

1. WHEN `E-extension-lifecycle` runs `on_load` for an extension THEN
   the system SHALL walk the class for `@subscribes_to` markers and
   register each as a bus subscription.
2. WHEN `on_unload` runs THEN the system SHALL remove every
   subscription registered for that class.
3. WHILE a subscription is registered the system SHALL dispatch bus
   events through the capability-gated delivery path (see
   `E-extension-sandbox` once active).

### Requirement 3: Delivery semantics and timeouts

**User Story:** As a platform maintainer, I want each subscription
delivery bounded by a per-handler timeout and retried per aspect
configuration, so that a misbehaving subscriber cannot stall the bus
dispatch loop.

**Acceptance Criteria (EARS):**

1. WHEN an event is delivered to a subscriber THEN the system SHALL
   invoke the method with the event payload as a named parameter
   `event=<Payload>` and enforce the aspect's `timeout_seconds`
   (default 5.0).
2. IF delivery times out THEN the system SHALL abandon the handler,
   emit `extension.call_failed` with reason `hook_timeout`, and record
   a failure against the subscriber.
3. WHERE the aspect declares `retry_max > 0` THEN the system SHALL
   retry per the aspect configuration, and on exhaustion SHALL emit
   `extension.call_failed` with reason `hook_retry_exhausted`.

### Requirement 4: Isolation across subscribers

**User Story:** As a service operator, I want one slow or broken
subscriber not to block delivery to other subscribers of the same
topic, so that extensions remain loosely coupled.

**Acceptance Criteria (EARS):**

1. WHEN multiple subscribers exist for a topic THEN the system SHALL
   dispatch them concurrently (each on its own executor task).
2. IF one subscriber raises THEN the system SHALL continue delivering
   to the remaining subscribers without propagating the exception.
3. WHILE a subscriber accumulates consecutive failures exceeding the
   aspect's `max_consecutive_failures` THEN the system SHALL mark it
   `quarantined` via `E-extension-lifecycle`.

## Property-Based Test Requirements

### Property 1: Load/unload subscription balance

- **Invariant:** For any extension loaded and then unloaded, the bus's
  subscription table contains zero subscriptions attributable to that
  extension after unload.
- **Generator:** extension classes declaring `N in range(0, 10)`
  subscriptions; permuted load/unload sequences.
- **Assertion:** After each `unload`, `bus.count_subscriptions(
  owner=ext_cls)` equals zero.
- **Sample size:** 1000 generated cases.

### Property 2: Subscriber isolation

- **Invariant:** For any set of K subscribers to a topic where one is
  programmed to raise, every other subscriber still receives the
  event.
- **Generator:** K subscribers with a random-index subscriber that
  always raises.
- **Assertion:** `received_count == K - 1` regardless of the index.
- **Sample size:** 1000 generated cases.

### Property 3: Timeout containment

- **Invariant:** For any subscriber with a handler duration exceeding
  its aspect timeout, the bus dispatch loop's per-event wall clock is
  bounded by `max(per-subscriber timeouts) + bookkeeping_slack`.
- **Generator:** per-subscriber (duration, timeout) pairs.
- **Assertion:** Total per-event dispatch time stays within the
  computed bound.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Subscriber dispatch adds < 3 ms overhead
  per event on top of bus delivery; 10k events/sec sustained with
  100 subscribers.
- **NFR-2 (Security):** Each delivery passes through the capability
  authorization hook (`E-extension-sandbox`, Phase 8); before Phase 8
  it is a no-op but the hook exists.
- **NFR-3 (Observability):** Metrics
  `pychestrate_extension_hook_delivered_total{topic,ext,result}`,
  `pychestrate_extension_hook_duration_seconds{topic,ext}`,
  `pychestrate_extension_hook_timeouts_total{topic,ext}`; log events
  `pychestrate_extension_hook_delivered`,
  `pychestrate_extension_hook_delivery_failed`; trace span
  `pychestrate_extension.hook.dispatch`.
- **NFR-4 (Reliability):** Failing subscribers are quarantined rather
  than allowed to amplify into event storms; quarantine is recorded
  on `E-extension-lifecycle`'s health table.

## Out of Scope

- Synchronous call-by-consumer surface (`E-factory-protocols`).
- Bus implementation (owned by `0-message-bus`).
- Capability enforcement (`E-extension-sandbox`).

## Dependencies

- **Depends on:** `E-extension-host`, `E-extension-lifecycle`,
  `E-extension-manifest`, `0-message-bus`.
- **Depended on by:** every feature that publishes bus events with an
  `event:` extension surface (per implementation-plan.md: 2-projects,
  3-static-pods, 3-pod-lifecycle, 4-checkout-checkin, 5-run-state-machine,
  etc.).
- **Extension points exposed:** the `@subscribes_to` decorator-as-metadata
  marker — decorator is allowed here because it *only* attaches
  subscription metadata (registering a function with a mapping system),
  not behavior modification (AGENTS.md-approved use).
