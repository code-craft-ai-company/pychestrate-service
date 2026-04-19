# 4-usage-history — Requirements

## Introduction

The `4-usage-history` feature records a per-resource timeline of lifecycle
and reservation activity — every reservation granted, every release, every
quarantine, every heal, every lease renewal — so that operators can answer
"who had this device last week?" without log grep, and so that capacity
and flake analytics downstream have a first-class durable source. It is a
write-heavy, read-bounded append-only log plus a set of aggregation
helpers for 24h / 7d / 30d windows. Extensions plug in via
`UsageAnalyticsHookExtension`: on every recorded event, each hook gets a
chance to attach derived fields (e.g. cost accounting, SLA-aware labels,
team-level attribution) before the timeline row is persisted. Hooks are
side-effect-discouraged — they decorate the record, they do not branch
the control flow.
This feature subscribes to `0-message-bus` events from every other Layer
4 feature; it does not initiate any Layer 4 state change. It ships in
Phase 4 and is the data source for `7-resource-metrics` (rollups) and
`6-flake-tracking` (host-level flakiness signals).

## Requirements

### Requirement 1: Append-Only Timeline Row per Lifecycle Event

**User Story:** As an operator, I want every resource lifecycle event —
registration, reservation, release, quarantine, heal, retire — recorded
as a single timeline row, so that I have a single query that shows what
happened to any resource.

**Acceptance Criteria (EARS):**

1. WHEN any of `entity.resource.registered`, `entity.resource.quarantined`,
   `entity.resource.healed`, `entity.resource.retired`,
   `entity.reservation.granted`, `entity.reservation.released`,
   `entity.reservation.forced_released`, `entity.lease.renewed`,
   `entity.lease.expired` is observed THEN the system SHALL append one
   `ResourceTimelineEvent` row with `resource_id`, `event_type`,
   `at_ts`, actor, reservation_id (when applicable), pod_id (when
   applicable), and a copy of the originating payload.
2. IF a pod-level event arrives THEN the system SHALL expand it into one
   row per pod member (for analytics fidelity) PLUS one pod-level row
   linked via `pod_event_group_id`; query filters can include or
   exclude member-level expansion.
3. WHERE an event arrives AFTER the resource has been retired for more
   than `retention_cutoff_days` (default 90) THEN the system SHALL
   still append the row but flag it `post_retention=true`; downstream
   dashboards filter it out by default.

### Requirement 2: Analytics Hooks Decorate but Do Not Change Control Flow

**User Story:** As an extension author, I want to attach fields like
"ci_team" or "cost_center" to every timeline row, so that my analytics
layer has them without modifying core code.

**Acceptance Criteria (EARS):**

1. WHEN a timeline row is about to be appended THEN the system SHALL
   invoke every loaded `UsageAnalyticsHookExtension.decorate(event,
   context)` in PRECEDENCE order and merge returned
   `annotations: dict[str, str]` into the row's `annotations` jsonb
   field.
2. IF a hook raises any exception THEN the system SHALL log
   `pychestrate.resource.usage.hook_error` with the hook name and the
   exception, record `pychestrate_resource_usage_hook_error_total`,
   and SHALL continue to invoke remaining hooks — one bad hook does
   not drop the row.
3. WHERE two hooks annotate the same key THEN the system SHALL keep
   the *lower PRECEDENCE* hook's value (same wins-rule as factory
   protocols) and SHALL emit
   `pychestrate.resource.usage.hook_key_collision` exactly once per
   hook-pair per service run.

### Requirement 3: Bounded-Window Aggregates for Capacity Planning

**User Story:** As a capacity planner, I want a precomputed 24h / 7d /
30d roll-up per resource, so that my dashboard loads quickly instead of
scanning the raw timeline.

**Acceptance Criteria (EARS):**

1. WHEN the rollup worker ticks (every 60s) THEN the system SHALL
   recompute `ResourceUsageRollup(resource_id, window, granted_count,
   release_count, forced_release_count, held_seconds,
   quarantined_seconds, last_good_age_seconds)` for each active
   resource and each window.
2. IF a resource's rollup has not changed (no events in the window)
   THEN the system SHALL skip the write — the rollup worker is
   idempotent and must not re-write identical rows.
3. WHERE a rollup's `forced_release_count / granted_count >
   forced_release_alert_ratio` (default 0.1) THEN the system SHALL
   emit `pychestrate.resource.usage.forced_release_burst` once per
   hour per resource; `7-alerts-budgets` may subscribe.

### Requirement 4: Timeline Query API

**User Story:** As a UI author, I want to fetch a resource's timeline
filtered by time range and event type, so that the run-detail page can
show "device X activity in the last 24h".

**Acceptance Criteria (EARS):**

1. WHEN `GET /api/v1/resources/{resource_id}/timeline?since=&until=&
   event_types=&include_pod_member_expansion=` is called THEN the
   system SHALL return matching rows sorted by `at_ts` ascending with
   p99 < 80 ms for windows ≤ 7d.
2. IF the caller requests a window > 30d AND is not
   `resource.usage.deep_history_read` permitted THEN the system SHALL
   reject with `403`; capacity-planning views require that permission.
3. WHERE the caller passes `include_pod_member_expansion=false` THEN
   the system SHALL return only pod-level rows for pod events (not
   per-member expansions).

## Property-Based Test Requirements

### Property 1: Every Published Event Yields Exactly One Timeline Row

- **Invariant:** For any sequence of bus events drawn from the set in
  Requirement 1, after the subscriber has drained, `|timeline_rows| =
  |events| + pod_member_expansions`, i.e. one row per event plus the
  deterministic per-member expansion defined in Requirement 1.2.
- **Generator:**
  `hypothesis.strategies.lists(event_spec, min_size=1, max_size=200)`
  with random pod memberships and occasional hook-crash injections.
- **Assertion:** Row count matches the formula; no duplicates; every
  `pod_event_group_id` links exactly the expected member rows to one
  pod-level row.
- **Sample size:** 1000 generated cases.

### Property 2: Rollup Idempotence and Commutativity

- **Invariant:** For any bag of events within a rollup window, the
  computed `ResourceUsageRollup` is independent of arrival order (the
  same multiset of events yields the same rollup values), and running
  the rollup worker twice in a row produces no additional DB writes.
- **Generator:**
  `hypothesis.strategies.lists(event_spec, min_size=0, max_size=500)`
  replayed against the rollup logic in two random orders.
- **Assertion:** `rollup(order_A) == rollup(order_B)` across every
  numeric field; repeated invocation yields zero rollup-write count.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Timeline append throughput ≥ 5,000
  rows/sec/service. `GET .../timeline` p99 < 80 ms for 7d windows.
  Rollup tick for 50k resources completes in ≤ 30 s (worker cadence is
  60 s so there's headroom).
- **NFR-2 (Security):** `resource.usage.read` gates `GET .../timeline`
  for windows ≤ 30d. `resource.usage.deep_history_read` gates windows
  > 30d. Hooks run under their `E-extension-sandbox` capabilities
  (Phase 8); no capabilities required for in-tree hooks. Sensitive
  attrs carried in payloads MUST be redacted before timeline persist
  (reuse `ResourceKindExtension.render_public` rendering).
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_resource_usage_rows_appended_total{event_type,kind}`,
  `pychestrate_resource_usage_hook_duration_seconds{hook}`
  (histogram),
  `pychestrate_resource_usage_hook_error_total{hook}`,
  `pychestrate_resource_usage_rollup_duration_seconds{window}`
  (histogram),
  `pychestrate_resource_usage_rollup_writes_total{window}`,
  `pychestrate_resource_usage_timeline_query_duration_seconds{window_days}`
  (histogram). Log events
  `pychestrate.resource.usage.hook_error`,
  `.hook_key_collision`, `.forced_release_burst`,
  `.post_retention_event`. Trace spans
  `pychestrate.resource.usage.append`,
  `pychestrate.resource.usage.rollup_tick`.
- **NFR-4 (Reliability):** The subscriber is at-least-once on the bus;
  timeline append is idempotent per `(event_id, resource_id)` so a
  replayed event does not duplicate rows. Rollup worker is
  restart-safe: state lives in `core.resource_usage_rollups` keyed by
  `(resource_id, window)` with a deterministic compute function.

## Out of Scope

- Aggregation beyond 30d rolling windows — long-term capacity
  forecasting is owned by `7-resource-metrics`.
- Per-test flakiness attribution — see `6-flake-tracking`.
- Cross-project / cross-pool rollups — this feature is per-resource.
- Acting on the events (no side effects beyond timeline + rollup).

## Dependencies

- **Depends on:** `0-message-bus`, `0-persistence`,
  `4-resource-inventory` (for kind-aware sensitive-field rendering),
  `4-checkout-checkin`, `4-lease-heartbeat`, `4-resource-health`,
  `E-resource-extensions`, `1-rbac`.
- **Depended on by:** `7-resource-metrics`, `6-flake-tracking`,
  `9-admin-ui` (resource detail timeline).
- **Extension points exposed:** `resource: UsageAnalyticsHookExtension` —
  `decorate(event, context) -> {key: str}`. In-tree:
  `ProjectAttributionHook`, `OwnerTeamHook`,
  `ReservationDurationHook`, `QuarantineSpanHook`.
