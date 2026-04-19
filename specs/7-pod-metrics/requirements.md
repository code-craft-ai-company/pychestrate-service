# 7-pod-metrics — Requirements

## Introduction

The `7-pod-metrics` feature declares and emits metrics describing pod
lifecycle behavior: bring-up time, tear-down time, and aggregate
comparisons of dynamic-vs-static pods. It shares the
`MetricDefinitionExtension` surface owned by `7-metrics-ingest`,
subscribes to events from `3-pod-lifecycle`, `3-static-pods`, and
`3-dynamic-pods`, and publishes canonical metric names consumed by
`7-project-dashboards`, `7-alerts-budgets`, and `7-slo-views`. The
feature lands in **Phase 9**. Authoritative pod state lives in Layer 3;
this feature owns the metric names and a pairing layer that matches
state-transition events to compute durations.

## Requirements

### Requirement 1: Core Pod Metric Family Registered

**User Story:** As a platform owner, I want pod bring-up and tear-down
durations emitted automatically, so that I can see whether dynamic pods
are keeping their promise vs static pre-wired pods.

**Acceptance Criteria (EARS):**

1. WHEN the service starts THEN the system SHALL register the following `MetricDefinitionExtension` subclasses:
   - `pychestrate_pod_bringup_seconds{project,pod_kind,template,provisioner}` — histogram, buckets `[1,5,15,60,300,900,3600]`. `pod_kind` ∈ `{static, dynamic}`.
   - `pychestrate_pod_teardown_seconds{project,pod_kind,template,provisioner}` — histogram, buckets `[1,5,15,60,300,900]`.
   - `pychestrate_pod_lifecycle_result_total{project,pod_kind,phase,result}` — counter (`phase` ∈ `{bringup, teardown}`).
   - `pychestrate_pod_active_count{project,pod_kind}` — gauge.
   - `pychestrate_pod_failure_total{project,pod_kind,failure_class}` — counter.
2. WHEN `entity.pod.state_changed` arrives with `state_to == "ready"` AND the pod has a stored `bringup_started_at` THEN the system SHALL emit `pychestrate_pod_bringup_seconds` with `ready_at - bringup_started_at`.
3. WHEN `entity.pod.state_changed` arrives with `state_to == "torn_down"` AND the pod has a stored `teardown_started_at` THEN the system SHALL emit `pychestrate_pod_teardown_seconds`.
4. WHERE the pod is a `dynamic` pod materialized by a `pod_provisioner` factory the system SHALL label `provisioner` with the factory `factory_protocol_name` value AND WHERE the pod is `static` the system SHALL label `provisioner = "n/a"`.

### Requirement 2: Lifecycle Pairing Under Churn

**User Story:** As an on-call engineer, I want pod duration metrics to
stay accurate even when pods churn fast or tear down without
successfully coming up, so that I can debug provisioner failures
without chasing phantom samples.

**Acceptance Criteria (EARS):**

1. WHEN a pod transitions `bringing_up → failed` without passing through `ready` THEN the system SHALL increment `pychestrate_pod_lifecycle_result_total{phase="bringup",result="failure"}` AND emit `pychestrate_pod_failure_total` with the failure-class label AND SHALL NOT emit `pychestrate_pod_bringup_seconds`.
2. IF a pod's `bringup_started_at` or `teardown_started_at` is absent when the terminal state arrives THEN the system SHALL drop the duration sample AND increment `pychestrate_pod_metrics_unpaired_total{phase}`.
3. WHILE the pairing map grows it SHALL be bounded at `pod_pairing_max_entries` (default 20 000) with LRU eviction; evictions increment `pychestrate_pod_metrics_pairing_evicted_total`.
4. WHERE a dynamic pod tears down because of an upstream resource failure (payload `failure_class="resource_failure"`) the system SHALL label `failure_class` accordingly AND NOT collapse it into `provisioner_error`.

### Requirement 3: Dynamic-vs-Static Comparison Support

**User Story:** As a platform owner, I want dashboards able to compare
dynamic vs static pod behavior without custom aggregation logic, so
that tradeoffs are visible with a single PromQL query.

**Acceptance Criteria (EARS):**

1. WHEN emitting any bringup/teardown/failure metric THEN the system SHALL always include `pod_kind` ∈ `{static, dynamic}` as a label, even for metrics where only one value is relevant, so ratio queries are uniformly expressible.
2. WHEN `entity.pod.registered` arrives for a static pod THEN the system SHALL emit `pychestrate_pod_active_count` (gauge delta via per-tick sampler).
3. WHILE active pods exist THE system SHALL sample `pychestrate_pod_active_count` every `pod_active_sample_interval_seconds` (default 60) AND emit per `(project, pod_kind)` tuple.
4. WHEN a pod is deregistered (static) OR torn down (dynamic) THEN the system SHALL update the in-memory active-pod set AND the sampler's next tick SHALL reflect the change.

## Property-Based Test Requirements

### Property 1: Duration Non-Negativity

- **Invariant:** For any `(started_at, ready_at)` pair with `ready_at >= started_at`, the emitted bringup sample is `>= 0`.
- **Generator:** `hypothesis.strategies.tuples(datetimes(), timedeltas(min_value=timedelta(0), max_value=timedelta(hours=2)))`.
- **Assertion:** `sample.value >= 0.0`.
- **Sample size:** 1000 generated cases

### Property 2: Lifecycle Emit Exclusivity

- **Invariant:** For any single pod lifecycle `[bringing_up, (ready|failed), ... , (torn_down|failed)]`, the system emits *at most one* `pychestrate_pod_bringup_seconds` sample AND *at most one* `pychestrate_pod_teardown_seconds` sample.
- **Generator:** `hypothesis.strategies.lists(sampled_from(["bringing_up","ready","running","tearing_down","torn_down","failed"]), min_size=1, max_size=20)`.
- **Assertion:** `bringup_emits <= 1 and teardown_emits <= 1` per pod lifecycle.
- **Sample size:** 1000 generated cases

### Property 3: Active Count Monotonic Between Events

- **Invariant:** For any sequence of `pod.registered` and `pod.deregistered` / `pod.torn_down` events, `pychestrate_pod_active_count` equals the running `registered - deregistered` count at every emission point.
- **Generator:** `hypothesis.strategies.lists(sampled_from([LifeOp.REGISTER, LifeOp.DEREGISTER]), min_size=0, max_size=500).filter(prefix_non_negative)`.
- **Assertion:** `active_count(t) == count(register, <=t) - count(deregister, <=t)`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Per-event emit p99 < 5 ms. Active-count sampler pass p99 < 150 ms for 10 000 pods. Pairing map lookup p99 < 1 ms.
- **NFR-2 (Security):** Metrics read gated by `metrics.read` + project membership. Pod template names sanitized + truncated to 200 bytes. `failure_class` values constrained to a bounded allow-list to prevent cardinality abuse.
- **NFR-3 (Observability):** Self-metrics `pychestrate_pod_metrics_emit_duration_seconds{metric_name}` (histogram), `pychestrate_pod_metrics_unpaired_total{phase}` (counter), `pychestrate_pod_metrics_pairing_evicted_total` (counter). Log events `pychestrate.pod_metrics.unpaired_terminal`, `pychestrate.pod_metrics.pairing_evicted`, `pychestrate.pod_metrics.unknown_failure_class`. Trace spans `pychestrate.pod_metrics.emit`, `pychestrate.pod_metrics.pair`, `pychestrate.pod_metrics.active_sampler_tick`.
- **NFR-4 (Reliability):** Service restart SHALL NOT corrupt pairing state — on boot, the pairing map is rebuilt from Layer 3's current `bringing_up` / `tearing_down` pods rather than persisted. A pod in `bringing_up` at boot whose `bringup_started_at` is unknown SHALL be labeled accordingly and skipped from duration emission.

## Out of Scope

- Pod state-machine authority (owned by `3-pod-lifecycle`).
- Bus subscription mechanics (owned by `7-metrics-ingest`).
- Alert thresholds (owned by `7-alerts-budgets`).
- Provisioner implementations (owned by `3-dynamic-pods`).

## Dependencies

- **Depends on:** `7-metrics-ingest`, `3-pod-lifecycle`, `3-static-pods`, `3-dynamic-pods`, `3-pod-definitions`, `0-message-bus`, `0-timeseries-backend`, `E-extension-host`.
- **Depended on by:** `7-project-dashboards`, `7-alerts-budgets`, `7-slo-views`.
- **Extension points exposed:** shares `resource: MetricDefinitionExtension`.
