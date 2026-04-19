# 7-orchestration-metrics — Design

## Architecture

`7-orchestration-metrics` declares the pipeline/run orchestration
metric family and an `OrchestrationMetricResolver` that translates
pipeline/run events into samples. It lives in **Phase 9**, shares
`MetricDefinitionExtension` with `7-metrics-ingest`, and subscribes to
events from `6-pipeline-definition`, `5-run-state-machine`, and
`5-cancel-reconcile`. The feature owns one pure DAG library
(`longest_path.py`) and the `parallel_efficiency` computation. No
persistent state is owned by this feature — pipeline and stage truth
live upstream, and samples live in `0-timeseries-backend`.

## Data Model

No persisted schema owned here. In-memory state on the resolver:

- `enum_allow_lists: dict[str, set[str]]` — seeded at startup:
  - `retry_reason`: `{flake_retry, infra_retry, manual_retry, policy_retry}`
  - `cancel_source`: `{user, pipeline_policy, resource_conflict, pod_offline, cascade}`
  - `pipeline_trigger`: `{scm_push, scm_pr, schedule, manual, upstream, api}`

Value types:

- `StageInterval`:
  - `stage_id: UUID`
  - `stage_name: str`
  - `started_at: datetime`
  - `completed_at: datetime`
  - `depends_on: list[UUID]`
  - `result: Literal["success","failure","cancelled","timeout","skipped"]`
- `PipelineRunTimeline` — `{run_id, submitted_at, started_at, completed_at, trigger, stages: list[StageInterval]}`
- `OrchestrationMetricSamples` — list of `Sample`.

## Interfaces

### Public API

None directly. Query access via `0-timeseries-backend`'s
`POST /api/v1/metrics/query_range`.

### Internal API

```python
class OrchestrationMetricResolver:
    def __init__(
        self,
        clock: Clock,
        config: OrchestrationMetricsConfig
    ) -> None:
        self._clock = clock
        self._config = config
        self._enum_allow_lists: dict[str, set[str]] = config.enum_allow_lists
        return

    def on_pipeline_run_completed(
        self,
        event: PipelineRunCompletedEvent
    ) -> list[Sample]:
        """
            Emit lead_time + result counter + parallel_efficiency samples.

            :returns: Samples.
        """
        ...

    def on_stage_completed(
        self,
        event: StageCompletedEvent
    ) -> list[Sample]:
        """
            Emit stage_duration sample.

            :returns: Samples.
        """
        ...

    def on_run_retried(
        self,
        event: RunRetriedEvent
    ) -> list[Sample]:
        """
            Emit retry counter sample after validating reason enum.

            :returns: Samples (empty if enum invalid).
        """
        ...

    def on_run_cancelled(
        self,
        event: RunCancelledEvent
    ) -> list[Sample]:
        """
            Emit cancel counter sample after validating source enum.

            :returns: Samples (empty if enum invalid).
        """
        ...


def compute_critical_path_seconds(
    stages: list[StageInterval]
) -> float:
    """
        DAG longest-path over stage durations.

        :param stages: All stages in a run, with `depends_on` edges.

        :returns: Critical path length in seconds.
        :raises: SemanticError on cycles.
    """
    ...


def compute_parallel_efficiency(
    critical_path_seconds: float,
    total_stage_seconds: float
) -> float | None:
    """
        :returns: Ratio clamped to [0.0, 1.0], or None when total == 0.
    """
    ...


def sanitize_label_value(
    raw: str,
    max_bytes: int
) -> str:
    """
        Reuse of the build-metrics sanitizer contract.
    """
    ...
```

### Extension Surface

Shares `MetricDefinitionExtension` (owned by `7-metrics-ingest`). In-tree
subclasses shipped here:

- `source/site/automojo/extensions/pychestrate/metric_definition/orchestration/lead_time.py` — `PipelineLeadTimeMetric`.
- `source/site/automojo/extensions/pychestrate/metric_definition/orchestration/stage_duration.py` — `PipelineStageDurationMetric`.
- `source/site/automojo/extensions/pychestrate/metric_definition/orchestration/result.py` — `PipelineResultMetric`.
- `source/site/automojo/extensions/pychestrate/metric_definition/orchestration/retry.py` — `PipelineRetryMetric`.
- `source/site/automojo/extensions/pychestrate/metric_definition/orchestration/cancel.py` — `PipelineCancelMetric`.
- `source/site/automojo/extensions/pychestrate/metric_definition/orchestration/parallel.py` — `PipelineParallelEfficiencyMetric`.

### Events Emitted

- `entity.metric.definition_registered` (via `7-metrics-ingest`).

### Events Consumed

- `entity.pipeline.run_completed` (from `6-pipeline-definition`).
- `entity.pipeline.stage_completed` (from `6-pipeline-definition`).
- `entity.run.retried` (from `5-run-state-machine`).
- `entity.run.cancelled` (from `5-cancel-reconcile`).

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/metrics/domains/orchestration/`:

- `__init__.py`
- `resolver.py` — `OrchestrationMetricResolver`.
- `longest_path.py` — `compute_critical_path_seconds`, `_topological_order`.
- `efficiency.py` — `compute_parallel_efficiency`.
- `labels.py` — `sanitize_label_value` (shared contract with build metrics).
- `config.py` — `OrchestrationMetricsConfig` including enum allow-lists.
- `value_types.py` — `StageInterval`, `PipelineRunTimeline`, event payload dataclasses.

`MetricDefinitionExtension` subclasses under
`source/site/automojo/extensions/pychestrate/metric_definition/orchestration/`.

## Key Flows

### Flow 1 — Lead Time on Run Completion

1. `entity.pipeline.run_completed` arrives with `submitted_at`, `completed_at`, `trigger`, `stage_timeline`.
2. Resolver validates trigger against `pipeline_trigger` allow-list; invalid → drop + log.
3. Emits `pychestrate_pipeline_lead_time_seconds` and `pychestrate_pipeline_result_total`.
4. If `stage_timeline` present: runs `compute_critical_path_seconds` + `compute_parallel_efficiency`, emits gauge.

### Flow 2 — Stage Duration

1. `entity.pipeline.stage_completed` arrives with `stage_id`, `started_at`, `completed_at`, `result`.
2. Resolver emits `pychestrate_pipeline_stage_duration_seconds` with `result` label.

### Flow 3 — Retry / Cancel Attribution

1. `entity.run.retried` or `entity.run.cancelled` arrives with `reason`/`source`.
2. Resolver validates enum; invalid → drop + `pychestrate.orchestration_metrics.invalid_enum` log.
3. Emits the counter.

### Flow 4 — Parallel Efficiency

1. Build DAG from `stage.depends_on`.
2. Topological sort; if cycle detected, `SemanticError` bubbles (should never happen for valid pipelines).
3. Longest path by cumulative `duration_seconds`.
4. `efficiency = critical_path / sum(durations)`; clamp to `1.0` if inverted with a warn log.

## Error Handling

- `SemanticError` on DAG cycles: bubble (indicates upstream bug).
- Invalid enum values caught and reclassified as drop+log; never raise to worker.
- Missing `stage_timeline` is tolerated — only the efficiency gauge is skipped.
- Negative durations are clamped to 0 with a warn log; division-by-zero for efficiency returns `None`.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- `metrics.read` + project membership for read access.
- Pipeline/stage/trigger labels are sanitized + truncated to 200 bytes.
- DAG computation runs in-process with a hard cap `max_stages_per_run` (default 500); events exceeding the cap skip efficiency emission and log `pychestrate.orchestration_metrics.dag_oversized`.

## Observability

Self-metrics:

- `pychestrate_orchestration_metrics_emit_duration_seconds{metric_name}` — histogram
- `pychestrate_orchestration_metrics_invalid_enum_total{label}` — counter
- `pychestrate_orchestration_metrics_critical_path_duration_seconds{project}` — histogram

Domain metrics:

- `pychestrate_pipeline_lead_time_seconds{project,pipeline,trigger}`
- `pychestrate_pipeline_stage_duration_seconds{project,pipeline,stage,result}`
- `pychestrate_pipeline_result_total{project,pipeline,result}`
- `pychestrate_pipeline_retry_total{project,pipeline,stage,reason}`
- `pychestrate_pipeline_cancel_total{project,pipeline,source}`
- `pychestrate_pipeline_parallel_efficiency{project,pipeline}`

Log events: `pychestrate.orchestration_metrics.invalid_enum`, `pychestrate.orchestration_metrics.parallel_efficiency_inverted`, `pychestrate.orchestration_metrics.dag_oversized`.

Trace spans: `pychestrate.orchestration_metrics.emit`, `pychestrate.orchestration_metrics.longest_path`, `pychestrate.orchestration_metrics.efficiency`.

## Open Questions

- Should `parallel_efficiency` be a histogram (to show distribution over time) rather than a gauge? Current design: gauge emitted per run. Timebox: Phase 9 midpoint.
- Is `critical_path_seconds` exposed as its own metric or only as a factor in `parallel_efficiency`? Current design: the latter; may re-expose if dashboards need it. Timebox: Phase 9 midpoint.
- Do we include `skipped` stages in `total_stage_seconds`? Current design: yes with `duration = 0`. Timebox: Phase 9 exit.
