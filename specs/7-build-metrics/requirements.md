# 7-build-metrics — Requirements

## Introduction

The `7-build-metrics` feature declares and emits the metric family that
describes build-job behavior: duration, queue time, success rate, cache
hit rate, and artifact size. It is a set of `MetricDefinitionExtension`
registrations plus a small transformation layer that enriches
`6-build-orchestration` and `6-build-artifacts` events with
project/pipeline/branch labels before handing them to `7-metrics-ingest`
for the actual write. The feature lands in **Phase 9**, sits between
`6-build-orchestration` / `6-build-artifacts` (event producers) and
`7-project-dashboards` / `7-alerts-budgets` / `7-slo-views` (consumers
of the metric names), and shares the `MetricDefinitionExtension` surface
owned by `7-metrics-ingest`. Authoritative source of truth for build
outcomes is `6-build-orchestration`; this feature owns only the metric
names and the label-resolution logic that turns a build event into a
sample.

## Requirements

### Requirement 1: Core Build Metric Family Registered

**User Story:** As a build-platform owner, I want a canonical set of
build metrics emitted automatically, so that duration, queue time, and
success rate are comparable across every project using the service.

**Acceptance Criteria (EARS):**

1. WHEN the service starts THEN the system SHALL register the following `MetricDefinitionExtension` subclasses:
   - `pychestrate_build_duration_seconds{project,pipeline,branch,result}` — histogram, buckets `[1,5,15,30,60,120,300,600,1800,3600]`.
   - `pychestrate_build_queue_seconds{project,pipeline,branch}` — histogram, buckets `[0.1,1,5,15,60,300,900]`.
   - `pychestrate_build_result_total{project,pipeline,branch,result}` — counter (`result` ∈ `{success,failure,cancelled,timeout}`).
   - `pychestrate_build_cache_hit_ratio{project,pipeline,cache_scope}` — gauge in `[0.0, 1.0]`.
   - `pychestrate_build_artifact_bytes{project,pipeline,artifact_type}` — histogram, buckets `[1KiB,64KiB,1MiB,16MiB,256MiB,4GiB]`.
2. WHEN `entity.build.queued` arrives THEN the system SHALL stamp an in-memory `queue_started_at` keyed by `build_id` so `queue_seconds` can be computed on the matching `entity.build.started`.
3. WHEN `entity.build.completed` arrives THEN the system SHALL emit `pychestrate_build_duration_seconds` AND `pychestrate_build_result_total` with `result` resolved from the event payload.
4. WHERE the build event carries a `cache_report: {hits, misses}` attribute the system SHALL emit `pychestrate_build_cache_hit_ratio = hits / (hits + misses)` clamped to `[0.0, 1.0]` AND emit nothing when `hits + misses == 0`.

### Requirement 2: Stable Label Cardinality

**User Story:** As an on-call engineer, I want build metric label
cardinality to stay bounded, so that the timeseries backend is not
overwhelmed when a branch-per-commit workflow fans out.

**Acceptance Criteria (EARS):**

1. IF a resolved label value exceeds 200 bytes THEN the system SHALL truncate it to 200 bytes and append a deterministic 8-char SHA-256 suffix to keep the mapping reversible.
2. WHEN per-metric cardinality reaches `cardinality_max_per_metric` (default 100 000) THEN the system SHALL drop additional samples, increment `pychestrate_metrics_ingest_dropped_total{reason="cardinality_exceeded"}`, AND emit a once-per-hour `pychestrate.build_metrics.cardinality_exceeded` log event.
3. WHERE the originating project has `branch_label_policy = "collapse_by_pattern"` the system SHALL collapse `refs/pull/<N>/head` to the literal `pull-request` before using it as a label value.
4. IF `project_id` cannot be resolved from the event THEN the system SHALL NOT emit the sample AND SHALL increment `pychestrate_metrics_ingest_dropped_total{reason="missing_project"}`.

### Requirement 3: Artifact Size Reporting

**User Story:** As a platform cost owner, I want per-build artifact
sizes surfaced as metrics, so that runaway artifact growth can be
alerted on before it affects retention budgets.

**Acceptance Criteria (EARS):**

1. WHEN `entity.build.artifact_published` arrives THEN the system SHALL emit `pychestrate_build_artifact_bytes` for every artifact whose `artifact_type` is declared in the project's artifact-type allow-list, observing `bytes_total`.
2. IF `bytes_total == 0` THEN the system SHALL NOT emit a sample (histogram zero is semantically meaningless here).
3. WHILE an in-tree reference `ArtifactClassifierExtension` maps unknown mime types to `artifact_type = "other"` the system SHALL still emit the sample with that classification.
4. WHEN an artifact exceeds `artifact_alert_size_bytes` (default 4 GiB) THEN the system SHALL emit `entity.build.artifact.oversized` for downstream consumption by `7-alerts-budgets`.

## Property-Based Test Requirements

### Property 1: Duration Non-Negativity

- **Invariant:** For any sequence of `(started_at, completed_at)` pairs with `completed_at >= started_at`, the emitted `pychestrate_build_duration_seconds` value is `>= 0` AND never exceeds `completed_at - started_at`.
- **Generator:** `hypothesis.strategies.tuples(datetimes(), timedeltas(min_value=timedelta(0), max_value=timedelta(hours=24)))` producing `(started, started + delta)`.
- **Assertion:** `sample.value >= 0 and sample.value <= (completed_at - started_at).total_seconds() + epsilon`.
- **Sample size:** 1000 generated cases

### Property 2: Cache Hit Ratio In Range

- **Invariant:** For any `(hits, misses)` with `hits >= 0 and misses >= 0 and hits + misses > 0`, the emitted `pychestrate_build_cache_hit_ratio` is in `[0.0, 1.0]`.
- **Generator:** `hypothesis.strategies.tuples(integers(min_value=0, max_value=10**9), integers(min_value=0, max_value=10**9)).filter(lambda t: t[0]+t[1]>0)`.
- **Assertion:** `0.0 <= sample.value <= 1.0`.
- **Sample size:** 1000 generated cases

### Property 3: Queue Time Ordering

- **Invariant:** For any `(queued_at, started_at)` pair with `started_at >= queued_at`, `pychestrate_build_queue_seconds = (started_at - queued_at).total_seconds() >= 0`.
- **Generator:** `hypothesis.strategies.tuples(datetimes(), timedeltas(min_value=timedelta(0), max_value=timedelta(hours=4)))`.
- **Assertion:** `sample.value >= 0.0`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Label resolution + emit p99 < 5 ms per build event. Project-scoped metric query for a 30-day window returns in p99 < 800 ms (driven by `0-timeseries-backend` — this feature only writes).
- **NFR-2 (Security):** Metrics read path gated by `metrics.read` plus project membership. Label values SHALL be sanitized to `[A-Za-z0-9._:/-]` plus truncation; values failing sanitization SHALL be hashed to preserve uniqueness without leaking arbitrary payload.
- **NFR-3 (Observability):** Self-metrics `pychestrate_build_metrics_emit_duration_seconds{metric_name}` (histogram), `pychestrate_build_metrics_dropped_total{reason}` (counter). Log events `pychestrate.build_metrics.cardinality_exceeded`, `pychestrate.build_metrics.project_unresolved`. Trace spans `pychestrate.build_metrics.resolve_labels`, `pychestrate.build_metrics.emit`.
- **NFR-4 (Reliability):** Queue-time tracking tolerates missing `entity.build.queued` by skipping `queue_seconds` rather than failing duration emission. In-memory queue-state table bounded at `queue_state_max_entries` (default 50 000) with LRU eviction.

## Out of Scope

- Sample storage (owned by `0-timeseries-backend`).
- Bus subscription mechanics (owned by `7-metrics-ingest`).
- Cost metrics covering object-store bytes (owned by `7-resource-metrics`).
- Alert thresholds (owned by `7-alerts-budgets`).

## Dependencies

- **Depends on:** `7-metrics-ingest`, `6-build-orchestration`, `6-build-artifacts`, `6-pipeline-definition`, `0-message-bus`, `0-timeseries-backend`, `E-extension-host`.
- **Depended on by:** `7-project-dashboards`, `7-alerts-budgets`, `7-slo-views`.
- **Extension points exposed:** shares `resource: MetricDefinitionExtension` (owned by `7-metrics-ingest`); contributes in-tree subclasses; declares `event: entity.build.artifact.oversized`.
