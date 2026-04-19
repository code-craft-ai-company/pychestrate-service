# 7-test-metrics — Design

## Architecture

`7-test-metrics` declares the test-domain metric family and a
`TestMetricResolver` that translates `entity.run.*` and
`entity.flake.*` events into samples. It lives in **Phase 9**, shares
the `MetricDefinitionExtension` surface with `7-metrics-ingest`, and
depends on `5-result-ingest-watcher` as the authoritative source of
test-case outcomes. The resolver maintains two pieces of bounded
in-memory state: a `suite_state` map for MTTR-to-green transitions and
a `flake_rate_cache` keyed by `(project, suite)`. Longer-lived history
(flake classifications, coverage baselines) is persisted in
`0-persistence` via `6-flake-tracking` and a new
`test_coverage_snapshot` table owned by this feature.

## Data Model

Tables in `0-persistence`:

- `test_coverage_snapshot`:
  - `snapshot_id: BIGSERIAL`
  - `project_id: UUID`
  - `suite_id: UUID`
  - `run_id: UUID`
  - `artifact_id: UUID`
  - `coverage_schema_version: str`
  - `covered_lines: int`
  - `total_lines: int`
  - `recorded_at: datetime`
  - PK `(snapshot_id)`; unique `(project_id, suite_id, run_id, artifact_id)`.
- `test_suite_state`:
  - `project_id: UUID`
  - `suite_id: UUID`
  - `last_result: Literal["pass","fail","error","skip"]`
  - `first_fail_at: datetime | None`
  - `last_completed_at: datetime`
  - PK `(project_id, suite_id)`.

In-memory on the resolver:

- `flake_rate_cache: dict[tuple[UUID, UUID], FlakeRateCacheEntry]`
- `slowest_top_n: dict[tuple[UUID, UUID], SortedTopN]`
- `suite_state_cache: dict[tuple[UUID, UUID], TestSuiteState]` — write-through to `test_suite_state`.

Value types:

- `FlakeRateCacheEntry` — `{rate: float, computed_at: datetime}`
- `CoverageReport` — `{coverage_schema_version, covered_lines, total_lines}`

## Interfaces

### Public API

None directly. Query access via `0-timeseries-backend`'s
`POST /api/v1/metrics/query_range`.

### Internal API

```python
class TestMetricResolver:
    def __init__(
        self,
        repo: TestMetricRepository,
        coverage_parser_registry: CoverageParserRegistry,
        catalog: TestCatalog,
        clock: Clock,
        config: TestMetricsConfig
    ) -> None:
        self._repo = repo
        self._coverage_parser_registry = coverage_parser_registry
        self._catalog = catalog
        self._clock = clock
        self._config = config
        self._flake_rate_cache: dict[tuple[UUID, UUID], FlakeRateCacheEntry] = {}
        self._slowest_top_n: dict[tuple[UUID, UUID], SortedTopN] = {}
        self._suite_state_cache: dict[tuple[UUID, UUID], TestSuiteState] = {}
        return

    def on_test_case_completed(
        self,
        event: TestCaseCompletedEvent
    ) -> list[Sample]:
        """
            Emit result counter + case duration histogram + top-N tracking.

            :returns: Samples.
        """
        ...

    def on_suite_completed(
        self,
        event: SuiteCompletedEvent
    ) -> list[Sample]:
        """
            Update suite state; emit MTTR-to-green on fail→pass transition.

            :returns: Samples (possibly including MTTR).
        """
        ...

    def on_flake_classified(
        self,
        event: FlakeClassifiedEvent
    ) -> list[Sample]:
        """
            Invalidate flake rate cache for the suite; emit recomputed rate.

            :returns: Gauge sample (or empty list if window has zero cases).
        """
        ...

    def on_coverage_artifact(
        self,
        event: ArtifactPublishedEvent
    ) -> list[Sample]:
        """
            Parse coverage, emit line ratio + delta, skip on schema mismatch.

            :returns: Samples (0, 1, or 2).
            :raises: CoverageParseError (caught by the worker DLQ path).
        """
        ...


def clamp01(
    value: float
) -> float:
    """
        Clamp a float to [0.0, 1.0].

        :returns: Clamped value.
    """
    ...
```

### Extension Surface

Shares `MetricDefinitionExtension` (owned by `7-metrics-ingest`). In-tree
subclasses shipped here:

- `source/site/automojo/extensions/pychestrate/metric_definition/test/result.py` — `TestResultMetric`.
- `source/site/automojo/extensions/pychestrate/metric_definition/test/duration.py` — `TestCaseDurationMetric`.
- `source/site/automojo/extensions/pychestrate/metric_definition/test/mttr.py` — `TestMttrMetric`.
- `source/site/automojo/extensions/pychestrate/metric_definition/test/flake_rate.py` — `TestFlakeRateMetric`.
- `source/site/automojo/extensions/pychestrate/metric_definition/test/coverage.py` — `TestCoverageLineRatioMetric` + `TestCoverageDeltaMetric`.
- `source/site/automojo/extensions/pychestrate/metric_definition/test/slowest.py` — `TestCaseSlowestMetric`.

Internal resource extension declared here:

```python
class CoverageArtifactTypeExtension(ResourceExtension):
    """
        Maps an artifact type + schema version to a coverage parser.
    """
    artifact_type: str
    coverage_schema_version: str

    @classmethod
    def parse(
        cls,
        artifact_body: bytes
    ) -> CoverageReport:
        ...
```

Reference implementation:
`source/site/automojo/extensions/pychestrate/coverage_artifact/cobertura_v4.py`.

### Events Emitted

- `entity.metric.definition_registered` (via `7-metrics-ingest`).
- `entity.test.coverage.regressed` — `{project_id, suite_id, run_id, delta_ratio, previous_ratio, current_ratio}`.

### Events Consumed

- `entity.run.test_case_completed` (from `5-result-ingest-watcher`).
- `entity.run.suite_completed` (from `6-test-orchestration`).
- `entity.flake.classified` (from `6-flake-tracking`).
- `entity.build.artifact_published` (from `6-build-artifacts`) filtered to coverage `artifact_type`.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/metrics/domains/test/`:

- `__init__.py`
- `resolver.py` — `TestMetricResolver`.
- `coverage.py` — `CoverageArtifactTypeExtension`, `CoverageParserRegistry`.
- `slowest.py` — `SortedTopN` data structure.
- `repository.py` — `TestMetricRepository` (snapshots + suite state).
- `config.py` — `TestMetricsConfig`.
- `value_types.py` — event payload dataclasses.
- `errors.py` — `CoverageParseError`.

`MetricDefinitionExtension` subclasses under
`source/site/automojo/extensions/pychestrate/metric_definition/test/`.

## Key Flows

### Flow 1 — Per-case Ingest

1. `entity.run.test_case_completed` arrives.
2. `TestMetricResolver.on_test_case_completed` increments `pychestrate_test_result_total` and observes `pychestrate_test_case_duration_seconds`.
3. The case's `duration_ms` is fed to `SortedTopN`; if it enters the top-N, a `pychestrate_test_case_slowest_observed_seconds` sample is emitted.

### Flow 2 — MTTR-to-Green

1. `entity.run.suite_completed` arrives with `result`.
2. Resolver loads `TestSuiteState` from cache (falling back to `test_suite_state` table).
3. On `fail → pass` transition, `mttr = completed_at - first_fail_at` is computed and emitted as `pychestrate_test_mttr_to_green_seconds`.
4. `suite_state.first_fail_at` is set to `None` after emit; on any new `fail`, it is set to the current `completed_at`.

### Flow 3 — Coverage Delta

1. `entity.build.artifact_published` arrives with `artifact_type` registered via `CoverageArtifactTypeExtension`.
2. Parser extension reads the artifact, returns `CoverageReport`.
3. Resolver fetches previous snapshot for the same `(project_id, suite_id)`; if `coverage_schema_version` differs, delta is skipped and log event emitted.
4. Line ratio emitted (clamped `[0.0, 1.0]`); delta emitted if comparable.
5. If delta is below `-coverage_alert_drop_threshold`, `entity.test.coverage.regressed` fires.

### Flow 4 — Flake-Rate Recompute

1. `entity.flake.classified` arrives.
2. Cache invalidated for `(project, suite)`.
3. Resolver queries `6-flake-tracking` for current flaky-case count over `flake_rate_window_days`.
4. Gauge `pychestrate_test_flake_rate` emitted unless `total == 0`.

## Error Handling

- `SemanticError` for malformed event payloads: bubble.
- `CoverageParseError`: caught at the resolver boundary; DLQ via `7-metrics-ingest`; other metrics for the run still emit.
- `CoverageArtifactTypeExtension.parse` raising is caught and reclassified as `CoverageParseError`.
- Clamp-with-warn on out-of-range ratios rather than raising.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- Case names that exceed 200 bytes are SHA-256-hashed with an 8-char prefix truncation to keep labels debuggable but bounded.
- Coverage artifact paths validated against the run's artifact root before opening (prevents path traversal).
- `metrics.read` + project membership gate REST queries; raw snapshot reads require `metrics.coverage.read`.

## Observability

Self-metrics:

- `pychestrate_test_metrics_emit_duration_seconds{metric_name}` — histogram
- `pychestrate_test_metrics_cache_hit_ratio{cache}` — gauge
- `pychestrate_test_metrics_coverage_parse_errors_total` — counter
- `pychestrate_test_metrics_slowest_top_n_size{project,suite}` — gauge

Domain metrics (written to `0-timeseries-backend`):

- `pychestrate_test_result_total{project,suite,result}`
- `pychestrate_test_case_duration_seconds{project,suite}`
- `pychestrate_test_mttr_to_green_seconds{project,suite}`
- `pychestrate_test_flake_rate{project,suite}`
- `pychestrate_test_coverage_line_ratio{project,suite,artifact}`
- `pychestrate_test_coverage_delta_ratio{project,suite,artifact}`
- `pychestrate_test_case_slowest_observed_seconds{project,suite,case}`

Log events: `pychestrate.test_metrics.coverage_schema_mismatch`, `pychestrate.test_metrics.coverage_out_of_range`, `pychestrate.test_metrics.mttr_computed`.

Trace spans: `pychestrate.test_metrics.ingest_case`, `pychestrate.test_metrics.flake_recompute`, `pychestrate.test_metrics.coverage_delta`, `pychestrate.test_metrics.top_n_update`.

## Open Questions

- Is `coverage_delta_ratio` emitted only when the compared run shares a `pipeline_id`, or across the entire suite timeline? Current design: suite timeline. Timebox: Phase 9 midpoint.
- Do we expose `slowest_top_n` as per-project or per-suite? Current design: per `(project, suite)`. Timebox: Phase 9 midpoint.
- Should `flake_rate_window_days` be per-project-configurable? Current design: global. Timebox: Phase 9 exit.
