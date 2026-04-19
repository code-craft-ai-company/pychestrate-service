# 7-resource-metrics — Requirements

## Introduction

The `7-resource-metrics` feature declares and emits metrics describing
the resource-management plane: per-pool utilization, reservation wait
time, conflict rate, and quarantine counts. It shares the
`MetricDefinitionExtension` surface owned by `7-metrics-ingest`,
subscribes to events from `4-resource-inventory`, `4-resource-pools`,
`4-checkout-checkin`, `4-reservation-scheduler`,
`4-conflict-deconfliction`, and `4-resource-health`, and publishes
canonical metric names consumed by `7-project-dashboards`,
`7-alerts-budgets`, and `7-slo-views`. The feature lands in
**Phase 9**. Authoritative resource state lives in Layer 4; this
feature owns the metric names and a periodic utilization sampler.

## Requirements

### Requirement 1: Core Resource Metric Family Registered

**User Story:** As a resource-pool owner, I want utilization, wait
time, and conflict metrics emitted automatically, so that capacity
planning does not require ad-hoc queries against the inventory
database.

**Acceptance Criteria (EARS):**

1. WHEN the service starts THEN the system SHALL register the following `MetricDefinitionExtension` subclasses:
   - `pychestrate_resource_pool_utilization_ratio{pool,resource_kind}` — gauge in `[0.0, 1.0]`.
   - `pychestrate_resource_pool_size{pool,resource_kind,state}` — gauge (`state` ∈ `{available,reserved,quarantined,offline}`).
   - `pychestrate_resource_reservation_wait_seconds{pool,resource_kind,priority}` — histogram, buckets `[0.1,1,5,30,120,600,3600]`.
   - `pychestrate_resource_conflict_total{pool,resource_kind,rule}` — counter.
   - `pychestrate_resource_quarantine_total{resource_kind,reason}` — counter.
   - `pychestrate_resource_health_probe_duration_seconds{resource_kind,probe}` — histogram, buckets `[0.05,0.25,1,5,30,120]`.
2. WHEN `entity.reservation.created` arrives THEN the system SHALL emit `pychestrate_resource_reservation_wait_seconds` using `granted_at - requested_at`.
3. WHEN `entity.conflict.detected` arrives THEN the system SHALL increment `pychestrate_resource_conflict_total` with the triggering rule label.
4. WHEN `entity.resource.quarantined` arrives THEN the system SHALL increment `pychestrate_resource_quarantine_total` with `reason` from the event.

### Requirement 2: Periodic Utilization Sampling

**User Story:** As an on-call engineer, I want pool utilization gauges
updated on a consistent cadence even when no reservation events are
flowing, so that dashboards do not flatline when pools are idle.

**Acceptance Criteria (EARS):**

1. WHILE the service is running THE system SHALL sample every registered resource pool at `utilization_sample_interval_seconds` (default 30) AND emit `pychestrate_resource_pool_utilization_ratio` and `pychestrate_resource_pool_size` gauges for every `(pool, resource_kind, state)` tuple.
2. IF the sampler overruns its interval by more than `utilization_sample_overrun_warn_seconds` (default 10) THEN the system SHALL log `pychestrate.resource_metrics.sampler_overrun` with the overrun duration AND skip to the next scheduled tick.
3. IF a pool has zero resources THEN the system SHALL emit `utilization_ratio = 0.0` rather than skipping (absence is ambiguous on dashboards).
4. WHEN the sampler cannot read pool state due to an `InventoryTransientError` THEN the system SHALL retry once with a 500 ms backoff THEN log and skip that tick.

### Requirement 3: Conflict / Quarantine Attribution

**User Story:** As a platform owner, I want conflicts and quarantines
split by rule/reason so that I can tell deconfliction rule churn from
underlying hardware flakiness.

**Acceptance Criteria (EARS):**

1. IF the conflict rule name is not present in a declared `ConflictRuleExtension` from `4-conflict-deconfliction` THEN the system SHALL emit the counter with `rule = "unregistered"` AND log `pychestrate.resource_metrics.unregistered_conflict_rule`.
2. IF the quarantine reason exceeds 120 bytes THEN the system SHALL truncate + SHA-256 suffix, AND store the raw reason in a sidecar log for on-call diagnosis.
3. WHEN `entity.reservation.forced_released` arrives THEN the system SHALL increment `pychestrate_resource_forced_release_total{pool,resource_kind,source}` with `source` in `{user_override,scheduler_preempt,health_fail}`.
4. WHERE an `entity.resource.health_probe_completed` event carries `probe_duration_seconds` the system SHALL observe `pychestrate_resource_health_probe_duration_seconds`.

## Property-Based Test Requirements

### Property 1: Utilization Ratio In Range

- **Invariant:** For any pool with `size_total >= 0` and `size_reserved <= size_total`, the emitted `pychestrate_resource_pool_utilization_ratio` is in `[0.0, 1.0]`.
- **Generator:** `hypothesis.strategies.tuples(integers(min_value=0, max_value=10000), integers(min_value=0, max_value=10000)).filter(lambda t: t[0] <= t[1])`.
- **Assertion:** `0.0 <= sample.value <= 1.0`.
- **Sample size:** 1000 generated cases

### Property 2: Wait Time Non-Negativity

- **Invariant:** For any `(requested_at, granted_at)` pair with `granted_at >= requested_at`, `pychestrate_resource_reservation_wait_seconds >= 0`.
- **Generator:** `hypothesis.strategies.tuples(datetimes(), timedeltas(min_value=timedelta(0), max_value=timedelta(hours=6)))`.
- **Assertion:** `sample.value >= 0.0`.
- **Sample size:** 1000 generated cases

### Property 3: Sampler Tick Count Bounded

- **Invariant:** For any wall-clock window `W` and sample interval `I`, the sampler emits `<= ceil(W / I) + 1` ticks per `(pool, resource_kind, state)` (allowing for one overlap at boundaries).
- **Generator:** `hypothesis.strategies.tuples(floats(min_value=1.0, max_value=3600.0), floats(min_value=1.0, max_value=60.0))`.
- **Assertion:** `observed_emit_count <= math.ceil(W / I) + 1`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Per-event emit p99 < 5 ms. Full-pool sampler pass over 10 000 resources p99 < 400 ms. Metric query for a 30-day utilization series p99 < 900 ms (driven by `0-timeseries-backend`).
- **NFR-2 (Security):** Metrics read gated by `metrics.read` plus project OR platform-admin membership (pools are not always project-scoped). Raw quarantine reasons stored only in log sidecar under `audit.sidecar.quarantine`, accessible via `audit.read:sidecar`.
- **NFR-3 (Observability):** Self-metrics `pychestrate_resource_metrics_emit_duration_seconds{metric_name}` (histogram), `pychestrate_resource_metrics_sampler_overrun_total` (counter), `pychestrate_resource_metrics_unregistered_conflict_rule_total` (counter). Log events `pychestrate.resource_metrics.sampler_overrun`, `pychestrate.resource_metrics.unregistered_conflict_rule`, `pychestrate.resource_metrics.quarantine_reason_truncated`. Trace spans `pychestrate.resource_metrics.sampler_tick`, `pychestrate.resource_metrics.emit`.
- **NFR-4 (Reliability):** Sampler SHALL catch-and-reclassify `InventoryTransientError`, retry once, then skip the tick without crashing the worker. Missed sampler ticks SHALL NOT back-fill on recovery — metric series will show a gap that matches reality.

## Out of Scope

- Resource health probe implementations (owned by `4-resource-health`).
- Bus subscription mechanics (owned by `7-metrics-ingest`).
- Alert thresholds (owned by `7-alerts-budgets`).
- Per-project access rollups (owned by `7-project-dashboards`).

## Dependencies

- **Depends on:** `7-metrics-ingest`, `4-resource-inventory`, `4-resource-pools`, `4-checkout-checkin`, `4-reservation-scheduler`, `4-conflict-deconfliction`, `4-resource-health`, `0-message-bus`, `0-timeseries-backend`, `E-extension-host`.
- **Depended on by:** `7-project-dashboards`, `7-alerts-budgets`, `7-slo-views`.
- **Extension points exposed:** shares `resource: MetricDefinitionExtension`.
