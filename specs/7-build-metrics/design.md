# 7-build-metrics — Design

## Architecture

`7-build-metrics` is a package of `MetricDefinitionExtension` subclasses
plus a `BuildMetricResolver` that converts `6-build-orchestration` and
`6-build-artifacts` events into samples. It does not open its own bus
subscription — instead, each `MetricDefinitionExtension` declares the
topic(s) it cares about, and `7-metrics-ingest` wires the subscription.
The feature lives in **Phase 9**. Authoritative build state lives in
`6-build-orchestration`; this feature is a pure translation layer plus
one bounded in-memory queue-state map used to compute queue duration
(`entity.build.queued` → `entity.build.started`).

## Data Model

No persisted schema — all state either lives in
`0-timeseries-backend` (emitted samples) or
`6-build-orchestration` (authoritative build rows).

In-memory state on the build-metrics helper module:

- `queue_state: dict[UUID, QueueEntry]` bounded at `queue_state_max_entries`
  with LRU eviction.

Value types:

- `QueueEntry`:
  - `build_id: UUID`
  - `queued_at: datetime`
  - `project_id: UUID`
  - `pipeline_id: UUID`
  - `branch: str`
- `BuildMetricSamples` — return type from the resolver; list of `Sample`.

## Interfaces

### Public API

None directly. Query access comes through
`0-timeseries-backend`'s `POST /api/v1/metrics/query_range` using the
metric names declared here. Documentation for those metric names is
published with `E-extension-docs`.

### Internal API

```python
class BuildMetricResolver:
    def __init__(
        self,
        project_service: ProjectService,
        pipeline_service: PipelineService,
        artifact_classifier_registry: ArtifactClassifierRegistry,
        clock: Clock,
        config: BuildMetricsConfig
    ) -> None:
        self._project_service = project_service
        self._pipeline_service = pipeline_service
        self._artifact_classifier_registry = artifact_classifier_registry
        self._clock = clock
        self._config = config
        self._queue_state: "collections.OrderedDict[UUID, QueueEntry]" = collections.OrderedDict()
        return

    def on_build_queued(
        self,
        event: BuildQueuedEvent
    ) -> list[Sample]:
        """
            Stash queue start time; emit zero samples.

            :returns: Empty list.
        """
        ...

    def on_build_started(
        self,
        event: BuildStartedEvent
    ) -> list[Sample]:
        """
            Compute queue_seconds against stored queue entry if present.

            :returns: Samples for `pychestrate_build_queue_seconds`
                      (possibly empty when queued event was missed).
        """
        ...

    def on_build_completed(
        self,
        event: BuildCompletedEvent
    ) -> list[Sample]:
        """
            Emit duration, result counter, and cache-hit-ratio samples.

            :returns: Samples with resolved labels.
        """
        ...

    def on_artifact_published(
        self,
        event: ArtifactPublishedEvent
    ) -> list[Sample]:
        """
            Emit artifact_bytes per artifact; raise oversized event if needed.

            :returns: Samples for `pychestrate_build_artifact_bytes`.
        """
        ...


def resolve_branch_label(
    project_policy: str,
    branch: str
) -> str:
    """
        Apply per-project branch label policy.

        :param project_policy: `raw` | `collapse_by_pattern`.
        :param branch: Raw branch identifier from the event.

        :returns: Sanitized branch label value.
    """
    ...


def sanitize_label_value(
    raw: str,
    max_bytes: int
) -> str:
    """
        Truncate to max_bytes and append deterministic sha256 suffix
        if truncation occurred.

        :returns: Safe label value.
    """
    ...
```

### Extension Surface

Shares `MetricDefinitionExtension` (owned by `7-metrics-ingest`). In-tree
subclasses shipped here:

- `source/site/ccai/extensions/pychestrate/metric_definition/build/duration.py` — `BuildDurationMetric`.
- `source/site/ccai/extensions/pychestrate/metric_definition/build/queue.py` — `BuildQueueMetric`.
- `source/site/ccai/extensions/pychestrate/metric_definition/build/result.py` — `BuildResultMetric`.
- `source/site/ccai/extensions/pychestrate/metric_definition/build/cache.py` — `BuildCacheHitRatioMetric`.
- `source/site/ccai/extensions/pychestrate/metric_definition/build/artifact.py` — `BuildArtifactBytesMetric`.

Each subclass references `BuildMetricResolver` methods via its
`SubscriptionSpec.value_resolver` and
`SubscriptionSpec.label_resolvers`.

### Events Emitted

- `entity.metric.definition_registered` (via `7-metrics-ingest`) — once per declared build metric at startup.
- `entity.build.artifact.oversized` — `{project_id, build_id, artifact_id, bytes_total, artifact_type}`.

### Events Consumed

- `entity.build.queued` (from `6-build-orchestration`).
- `entity.build.started` (from `6-build-orchestration`).
- `entity.build.completed` (from `6-build-orchestration`).
- `entity.build.artifact_published` (from `6-build-artifacts`).

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/metrics/domains/build/`:

- `__init__.py`
- `resolver.py` — `BuildMetricResolver`.
- `labels.py` — `resolve_branch_label`, `sanitize_label_value`.
- `config.py` — `BuildMetricsConfig`.
- `value_types.py` — `QueueEntry`, `BuildCompletedEvent`, etc.

`MetricDefinitionExtension` subclasses under
`source/site/ccai/extensions/pychestrate/metric_definition/build/`.

## Key Flows

### Flow 1 — Queue → Start Duration Pairing

1. `entity.build.queued` delivered to resolver; `queue_state[build_id] = QueueEntry(...)`.
2. When `entity.build.started` arrives, resolver pops the entry and emits `pychestrate_build_queue_seconds` with value `(started_at - queued_at).total_seconds()`.
3. If the LRU evicted the entry before `started` arrived, no queue_seconds sample emits; `pychestrate_build_metrics_dropped_total{reason="queue_state_evicted"}` increments.

### Flow 2 — Build Completion

1. `entity.build.completed` arrives with `{build_id, started_at, completed_at, result, cache_report}`.
2. Resolver computes `duration = completed_at - started_at`, clamps at 0.
3. Emits `pychestrate_build_duration_seconds{project,pipeline,branch,result}` and `pychestrate_build_result_total{…,result}`.
4. If `cache_report` present and `hits + misses > 0`, emits `pychestrate_build_cache_hit_ratio`.

### Flow 3 — Artifact Size

1. `entity.build.artifact_published` arrives with `[Artifact]` list.
2. For each artifact, the classifier registry resolves `artifact_type` (defaulting to `other`).
3. Emits `pychestrate_build_artifact_bytes{project,pipeline,artifact_type}`.
4. If any artifact exceeds `artifact_alert_size_bytes`, emits `entity.build.artifact.oversized`.

## Error Handling

- `SemanticError` for invalid event payloads (missing `build_id`, non-monotonic timestamps): bubble.
- `ProjectNotFoundError` caught and reclassified as a drop with `reason="missing_project"` (see Requirement 2.4).
- Artifact classifier raising is caught at the classifier-registry boundary; artifact_type falls back to `other`.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- Label sanitization: values outside `[A-Za-z0-9._:/-]` are replaced with `_` before truncation; truncation appends a deterministic 8-char SHA-256 suffix to preserve uniqueness.
- `queue_state` is in-memory only; no user input is persisted there beyond the bounded map.
- `entity.build.artifact.oversized` carries a project-scoped payload; downstream alert routing is governed by project RBAC.

## Observability

Metrics (self-metrics of this feature):

- `pychestrate_build_metrics_emit_duration_seconds{metric_name}` — histogram
- `pychestrate_build_metrics_dropped_total{reason}` — counter
- `pychestrate_build_metrics_queue_state_size` — gauge

Domain metrics declared by this feature (written to `0-timeseries-backend`):

- `pychestrate_build_duration_seconds{project,pipeline,branch,result}`
- `pychestrate_build_queue_seconds{project,pipeline,branch}`
- `pychestrate_build_result_total{project,pipeline,branch,result}`
- `pychestrate_build_cache_hit_ratio{project,pipeline,cache_scope}`
- `pychestrate_build_artifact_bytes{project,pipeline,artifact_type}`

Log events: `pychestrate.build_metrics.cardinality_exceeded`, `pychestrate.build_metrics.project_unresolved`, `pychestrate.build_metrics.oversized_artifact`.

Trace spans: `pychestrate.build_metrics.resolve_labels`, `pychestrate.build_metrics.emit`, `pychestrate.build_metrics.artifact_classify`.

## Open Questions

- Do we export a "cache scope" taxonomy at the metric level or leave it free-form? Current design: free-form, bounded by sanitization. Revisit after Phase 9 live traffic. Timebox: Phase 9 midpoint.
- Should queue-state survive service restart? Current design says no (in-memory only). Timebox: Phase 9 exit.
- Does `pychestrate_build_artifact_bytes` as a histogram scale better than a gauge snapshot keyed by `artifact_id`? Timebox: Phase 9 midpoint.
