# 7-orchestration-metrics — Requirements

## Introduction

The `7-orchestration-metrics` feature declares and emits metrics that
describe pipeline and run orchestration: lead time, per-stage duration,
parallel-execution efficiency, and retry/cancel rate. It shares the
`MetricDefinitionExtension` surface owned by `7-metrics-ingest`,
subscribes to `6-pipeline-definition`, `5-run-state-machine`, and
`5-cancel-reconcile` events, and publishes canonical metric names
consumed by `7-project-dashboards`, `7-alerts-budgets`, and
`7-slo-views`. The feature lands in **Phase 9**. Authoritative state
for pipeline runs lives in `6-pipeline-definition` and
`5-run-state-machine`; this feature owns the metric names and a
streaming aggregation that turns state transitions into samples.

## Requirements

### Requirement 1: Core Orchestration Metric Family Registered

**User Story:** As a release engineer, I want lead-time and per-stage
duration metrics emitted automatically, so that I can see where a
pipeline spends its time without building one-off queries.

**Acceptance Criteria (EARS):**

1. WHEN the service starts THEN the system SHALL register the following `MetricDefinitionExtension` subclasses:
   - `pychestrate_pipeline_lead_time_seconds{project,pipeline,trigger}` — histogram, buckets `[60,300,900,1800,3600,14400,86400]`.
   - `pychestrate_pipeline_stage_duration_seconds{project,pipeline,stage,result}` — histogram, buckets `[1,5,15,60,300,900,3600]`.
   - `pychestrate_pipeline_result_total{project,pipeline,result}` — counter (`result` ∈ `{success,failure,cancelled,timeout}`).
   - `pychestrate_pipeline_retry_total{project,pipeline,stage,reason}` — counter.
   - `pychestrate_pipeline_cancel_total{project,pipeline,source}` — counter.
   - `pychestrate_pipeline_parallel_efficiency{project,pipeline}` — gauge in `[0.0, 1.0]`.
2. WHEN `entity.pipeline.run_completed` arrives THEN the system SHALL emit `pychestrate_pipeline_lead_time_seconds` using `completed_at - submitted_at` AND `pychestrate_pipeline_result_total` with `result` resolved from payload.
3. WHEN `entity.pipeline.stage_completed` arrives THEN the system SHALL emit `pychestrate_pipeline_stage_duration_seconds` with `result` label from the stage outcome.
4. WHERE the pipeline run produced parallel stages the system SHALL compute `parallel_efficiency = critical_path_seconds / total_stage_seconds` (`1.0` when everything is serial, lower as fan-out wastes idle time) AND emit it once per run completion.

### Requirement 2: Retry / Cancel Attribution

**User Story:** As a pipeline author, I want retry and cancel counts
split by reason/source so that I can distinguish user cancellations
from scheduler cancellations and flake retries from infra retries.

**Acceptance Criteria (EARS):**

1. WHEN `entity.run.retried` arrives THEN the system SHALL increment `pychestrate_pipeline_retry_total{reason}` with `reason` ∈ `{flake_retry, infra_retry, manual_retry, policy_retry}`.
2. WHEN `entity.run.cancelled` arrives THEN the system SHALL increment `pychestrate_pipeline_cancel_total{source}` with `source` ∈ `{user, pipeline_policy, resource_conflict, pod_offline, cascade}`.
3. IF `reason` or `source` is absent or outside the allowed enum THEN the system SHALL drop the sample AND log `pychestrate.orchestration_metrics.invalid_enum` naming the topic + offending value.
4. WHILE a run is in `running` state the system SHALL NOT emit `pychestrate_pipeline_lead_time_seconds` (emitted only on run completion).

### Requirement 3: Parallel Efficiency Accuracy

**User Story:** As a platform owner, I want a trustworthy parallel
efficiency number that correctly credits parallelism rather than being
trivially 1.0 for serial pipelines.

**Acceptance Criteria (EARS):**

1. WHEN `entity.pipeline.run_completed` arrives with `stage_timeline: list[StageInterval]` THEN the system SHALL compute `critical_path_seconds` by running a DAG longest-path over the stage timeline AND compute `total_stage_seconds = sum(stage.duration)`.
2. IF `total_stage_seconds == 0` THEN the system SHALL NOT emit the gauge (division by zero).
3. IF `critical_path_seconds > total_stage_seconds` (indicative of bad inputs) THEN the system SHALL clamp the efficiency to `1.0` AND log `pychestrate.orchestration_metrics.parallel_efficiency_inverted` with the offending timeline hash.
4. WHERE the pipeline is purely serial (one stage at a time) the system SHALL emit `parallel_efficiency = 1.0`.

## Property-Based Test Requirements

### Property 1: Parallel Efficiency In Range

- **Invariant:** For any DAG stage timeline with non-negative durations and `total > 0`, the emitted `pychestrate_pipeline_parallel_efficiency` is in `[0.0, 1.0]` (post-clamp).
- **Generator:** `hypothesis.strategies.lists(stage_intervals(), min_size=1, max_size=50)` where `stage_intervals()` draws a random DAG with `duration_seconds ∈ floats(min_value=0.0, max_value=3600.0)`.
- **Assertion:** `0.0 <= sample.value <= 1.0`.
- **Sample size:** 1000 generated cases

### Property 2: Lead-Time Equals Critical Path For Serial Runs

- **Invariant:** For any serial pipeline (stages strictly sequential), `pychestrate_pipeline_lead_time_seconds == sum(stage.duration) + fixed_overhead_bounded`.
- **Generator:** `hypothesis.strategies.lists(floats(min_value=0.1, max_value=600.0), min_size=1, max_size=30)` → serial stage durations.
- **Assertion:** `abs(sample.value - sum(durations)) <= overhead_epsilon_seconds`.
- **Sample size:** 1000 generated cases

### Property 3: Retry Counter Monotonicity

- **Invariant:** For any sequence of `entity.run.retried` events over a fixed `(project, pipeline, stage, reason)`, the emitted counter is monotonically non-decreasing.
- **Generator:** `hypothesis.strategies.lists(sampled_from(["flake_retry","infra_retry","manual_retry","policy_retry"]), min_size=0, max_size=500)`.
- **Assertion:** `all(c_i <= c_{i+1} for c_i, c_{i+1} in pairwise(observed_counter_snapshots))`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Per-event resolve+emit p99 < 5 ms. DAG longest-path computation p99 < 8 ms for a 50-stage pipeline. Metric queries for a 90-day lead-time series return in p99 < 1.0 s (driven by `0-timeseries-backend`).
- **NFR-2 (Security):** Metrics read gated by `metrics.read` + project membership. Pipeline and stage names sanitized to `[A-Za-z0-9._:/-]` + SHA-256-suffix truncation at 200 bytes. Rejection of sample emit when `project_id` unresolvable SHALL NOT leak raw event payloads in log context.
- **NFR-3 (Observability):** Self-metrics `pychestrate_orchestration_metrics_emit_duration_seconds{metric_name}` (histogram), `pychestrate_orchestration_metrics_invalid_enum_total{label}` (counter), `pychestrate_orchestration_metrics_critical_path_duration_seconds{project}` (histogram). Log events `pychestrate.orchestration_metrics.invalid_enum`, `pychestrate.orchestration_metrics.parallel_efficiency_inverted`. Trace spans `pychestrate.orchestration_metrics.emit`, `pychestrate.orchestration_metrics.longest_path`.
- **NFR-4 (Reliability):** Missing `stage_timeline` on a completed run SHALL NOT block lead-time emit; `parallel_efficiency` is simply skipped. Out-of-order stage events are handled by keying DAG assembly on `stage_id`, not arrival order.

## Out of Scope

- Queue-level scheduling fairness metrics (owned by `7-resource-metrics`).
- Bus subscription mechanics (owned by `7-metrics-ingest`).
- Alert thresholds (owned by `7-alerts-budgets`).
- Tile rendering (owned by `7-project-dashboards`).

## Dependencies

- **Depends on:** `7-metrics-ingest`, `6-pipeline-definition`, `5-run-state-machine`, `5-cancel-reconcile`, `0-message-bus`, `0-timeseries-backend`, `E-extension-host`.
- **Depended on by:** `7-project-dashboards`, `7-alerts-budgets`, `7-slo-views`.
- **Extension points exposed:** shares `resource: MetricDefinitionExtension`.
