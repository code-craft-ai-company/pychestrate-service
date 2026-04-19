# 7-test-metrics — Requirements

## Introduction

The `7-test-metrics` feature declares and emits the metric family that
describes test-suite behavior: pass/fail trends, mean-time-to-green
(MTTR-to-green), flakiest suites, slowest suites, and coverage deltas.
It shares the `MetricDefinitionExtension` surface owned by
`7-metrics-ingest`, subscribes to events produced by
`5-result-ingest-watcher`, `6-test-orchestration`, and `6-flake-tracking`,
and publishes canonical metric names consumed by `7-project-dashboards`,
`7-alerts-budgets`, and `7-slo-views`. The feature lands in **Phase 9**.
Authoritative source of truth for test outcomes is the testbase result
tree ingested by `5-result-ingest-watcher`; this feature owns only the
metric names and the streaming aggregations that turn events into
samples.

## Requirements

### Requirement 1: Core Test Metric Family Registered

**User Story:** As a test-quality owner, I want pass/fail trends and
coverage deltas exposed as metrics, so that dashboards and alerts can be
built without special-casing our result store.

**Acceptance Criteria (EARS):**

1. WHEN the service starts THEN the system SHALL register the following `MetricDefinitionExtension` subclasses:
   - `pychestrate_test_result_total{project,suite,result}` — counter (`result` ∈ `{pass,fail,error,skip,xfail,xpass}`).
   - `pychestrate_test_case_duration_seconds{project,suite}` — histogram, buckets `[0.001,0.01,0.1,1,5,30,300]`.
   - `pychestrate_test_mttr_to_green_seconds{project,suite}` — histogram, buckets `[60,300,900,3600,14400,86400,604800]`.
   - `pychestrate_test_flake_rate{project,suite}` — gauge in `[0.0, 1.0]`.
   - `pychestrate_test_coverage_line_ratio{project,suite,artifact}` — gauge in `[0.0, 1.0]`.
   - `pychestrate_test_coverage_delta_ratio{project,suite,artifact}` — gauge in `[-1.0, 1.0]`.
2. WHEN `entity.run.test_case_completed` arrives THEN the system SHALL increment `pychestrate_test_result_total` once per case AND observe `pychestrate_test_case_duration_seconds`.
3. WHEN `entity.run.suite_completed` arrives AND the previous completed suite for the same `(project, suite)` was `fail` THEN the system SHALL compute `mttr_to_green = completed_at - first_fail_at` AND emit `pychestrate_test_mttr_to_green_seconds` only when transitioning fail → pass.
4. WHERE a coverage artifact is declared via `CoverageArtifactTypeExtension` the system SHALL extract `covered_lines / total_lines` into `pychestrate_test_coverage_line_ratio` AND compute `coverage_delta_ratio` against the previous run's coverage for the same suite.

### Requirement 2: Flakiest / Slowest Derivation

**User Story:** As an on-call engineer, I want "flakiest suite" and
"slowest case" rollups precomputed so that dashboards don't have to run
expensive queries across weeks of raw samples.

**Acceptance Criteria (EARS):**

1. WHEN `6-flake-tracking` emits `entity.flake.classified` THEN the system SHALL recompute `pychestrate_test_flake_rate` as `flaky_case_count / total_case_count` for the `(project, suite)` over the `flake_rate_window_days` (default 14).
2. WHILE the window is active the system SHALL cache the computed rate under `(project, suite)` with a TTL of `flake_rate_cache_ttl_seconds` (default 300) to avoid recompute on every event.
3. IF `total_case_count == 0` for the window THEN the system SHALL NOT emit the gauge (zero-divisor is semantically meaningless).
4. WHEN the top-N slowest cases per project change (driven by `entity.run.test_case_completed`) THEN the system SHALL emit `pychestrate_test_case_slowest_observed_seconds{project,suite,case}` for the top `slowest_top_n` (default 25) with the `case` label hashed if its raw name exceeds 200 bytes.

### Requirement 3: Coverage Delta Safety

**User Story:** As a release engineer, I want coverage deltas to be
emitted only when comparable, so that dashboards don't show phantom
drops when the underlying coverage artifact shape changes.

**Acceptance Criteria (EARS):**

1. IF the previous run's coverage artifact has a different `coverage_schema_version` than the current one THEN the system SHALL NOT emit `pychestrate_test_coverage_delta_ratio` AND SHALL emit `pychestrate.test_metrics.coverage_schema_mismatch` log event naming both versions.
2. IF coverage artifact parsing fails THEN the system SHALL catch-and-reclassify as `CoverageParseError`, write to DLQ via `7-metrics-ingest`, AND skip both coverage metrics for that run.
3. WHEN coverage ratio is outside `[0.0, 1.0]` after parsing THEN the system SHALL clamp to the nearest bound AND emit `pychestrate.test_metrics.coverage_out_of_range` log with the raw value.
4. WHEN `coverage_delta_ratio > coverage_alert_drop_threshold` (default 0.02 drop) THEN the system SHALL emit `entity.test.coverage.regressed` for downstream `7-alerts-budgets` consumption.

## Property-Based Test Requirements

### Property 1: Flake Rate Bounded

- **Invariant:** For any sequence of `(flaky_count, total_count)` pairs with `0 <= flaky_count <= total_count`, the emitted `pychestrate_test_flake_rate` value is in `[0.0, 1.0]`.
- **Generator:** `hypothesis.strategies.tuples(integers(min_value=0, max_value=10000), integers(min_value=1, max_value=10000)).filter(lambda t: t[0] <= t[1])`.
- **Assertion:** `0.0 <= sample.value <= 1.0`.
- **Sample size:** 1000 generated cases

### Property 2: MTTR Only On Transition

- **Invariant:** For any sequence of suite results, `pychestrate_test_mttr_to_green_seconds` emits *only* on the event where a `pass` immediately follows at least one consecutive `fail` in the same `(project, suite)` timeline.
- **Generator:** `hypothesis.strategies.lists(sampled_from(["pass","fail","error","skip"]), min_size=1, max_size=200)`.
- **Assertion:** `count(emits) == count(transitions in the sequence matching /fail+pass/)`.
- **Sample size:** 1000 generated cases

### Property 3: Coverage Clamp

- **Invariant:** For any raw ratio `r ∈ ℝ`, the emitted coverage ratio is `max(0.0, min(1.0, r))`.
- **Generator:** `hypothesis.strategies.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False)`.
- **Assertion:** `sample.value == clamp01(r)`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Per-test-case ingest p99 < 3 ms (runs with 5 000 test cases ingest in < 15 s). Flake-rate recompute p99 < 80 ms per `(project, suite)`. Coverage delta computation p99 < 120 ms per artifact.
- **NFR-2 (Security):** Metrics read gated by `metrics.read` + project membership. Case-name labels hashed if they exceed 200 bytes. Coverage artifact paths validated against the project's artifact root to prevent path traversal.
- **NFR-3 (Observability):** Self-metrics `pychestrate_test_metrics_emit_duration_seconds{metric_name}` (histogram), `pychestrate_test_metrics_cache_hit_ratio{cache}` (gauge), `pychestrate_test_metrics_coverage_parse_errors_total` (counter). Log events `pychestrate.test_metrics.coverage_schema_mismatch`, `pychestrate.test_metrics.coverage_out_of_range`, `pychestrate.test_metrics.mttr_computed`. Trace spans `pychestrate.test_metrics.ingest_case`, `pychestrate.test_metrics.flake_recompute`, `pychestrate.test_metrics.coverage_delta`.
- **NFR-4 (Reliability):** Coverage artifact parse failure SHALL NOT stop other test metrics from being emitted for the run. Flake-rate cache eviction SHALL be eventual-consistent with a max 5 minute staleness.

## Out of Scope

- Raw flake classification (owned by `6-flake-tracking`).
- Result tree parsing (owned by `5-result-ingest-watcher`).
- Bus subscription mechanics (owned by `7-metrics-ingest`).
- Test catalog metadata (owned by `6-test-catalog`).

## Dependencies

- **Depends on:** `7-metrics-ingest`, `5-result-ingest-watcher`, `6-test-orchestration`, `6-test-catalog`, `6-flake-tracking`, `0-message-bus`, `0-timeseries-backend`, `E-extension-host`.
- **Depended on by:** `7-project-dashboards`, `7-alerts-budgets`, `7-slo-views`.
- **Extension points exposed:** shares `resource: MetricDefinitionExtension`; declares internal `resource: CoverageArtifactTypeExtension`; declares `event: entity.test.coverage.regressed`.
