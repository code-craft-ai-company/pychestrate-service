# 7-pod-metrics — Design

## Architecture

`7-pod-metrics` declares the pod lifecycle metric family and a
`PodMetricResolver` that pairs state transitions to compute durations.
It lives in **Phase 9**, shares `MetricDefinitionExtension` with
`7-metrics-ingest`, and subscribes to events from Layer 3. The feature
owns an LRU-bounded in-memory `pairing_map` keyed by `pod_id` plus a
per-`(project, pod_kind)` active-pod set maintained off the bus events
and sampled periodically.

## Data Model

No persisted schema owned here. In-memory state:

- `pairing_map: collections.OrderedDict[UUID, PodPairingEntry]` bounded
  at `pod_pairing_max_entries` with LRU eviction.
- `active_pods: dict[tuple[UUID, str], set[UUID]]` — `(project_id, pod_kind) → set of pod_ids`.

Value types:

- `PodPairingEntry`:
  - `pod_id: UUID`
  - `project_id: UUID`
  - `pod_kind: Literal["static","dynamic"]`
  - `template: str`
  - `provisioner: str`
  - `bringup_started_at: datetime | None`
  - `teardown_started_at: datetime | None`
- `PodFailureClassification` — closed set:
  `{provisioner_error, image_pull_failure, network_error, resource_failure, timeout, validation_error, unknown}`.

## Interfaces

### Public API

None directly. Query access via `0-timeseries-backend`'s
`POST /api/v1/metrics/query_range`.

### Internal API

```python
class PodMetricResolver:
    def __init__(
        self,
        pod_registry: PodRegistry,
        clock: Clock,
        config: PodMetricsConfig
    ) -> None:
        self._pod_registry = pod_registry
        self._clock = clock
        self._config = config
        self._pairing_map: "collections.OrderedDict[UUID, PodPairingEntry]" = collections.OrderedDict()
        self._active_pods: dict[tuple[UUID, str], set[UUID]] = {}
        return

    def rebuild_pairing_from_registry(
        self
    ) -> None:
        """
            Reconstruct pairing map from Layer 3's current bringing_up /
            tearing_down pods. Called at service boot.

            :returns: None.
        """
        ...

    def on_pod_state_changed(
        self,
        event: PodStateChangedEvent
    ) -> list[Sample]:
        """
            Update pairing map and emit duration/result/failure samples
            as appropriate.

            :returns: Samples.
        """
        ...

    def on_pod_registered(
        self,
        event: PodRegisteredEvent
    ) -> list[Sample]:
        """
            Insert into active_pods.

            :returns: Empty list (active count emitted by sampler).
        """
        ...

    def on_pod_deregistered(
        self,
        event: PodDeregisteredEvent
    ) -> list[Sample]:
        ...


class PodActiveSampler:
    def __init__(
        self,
        resolver: PodMetricResolver,
        facade: TimeseriesFacade,
        clock: Clock,
        config: PodMetricsConfig
    ) -> None:
        self._resolver = resolver
        self._facade = facade
        self._clock = clock
        self._config = config
        self._task: asyncio.Task | None = None
        return

    def start(
        self
    ) -> None:
        ...

    def stop(
        self
    ) -> None:
        ...

    def tick(
        self
    ) -> None:
        """
            Emit pychestrate_pod_active_count for every (project, pod_kind).

            :returns: None.
        """
        ...


def classify_failure(
    raw_failure_class: str
) -> PodFailureClassification:
    """
        Map an arbitrary upstream failure-class string onto the closed set.

        :returns: Allowed classification, or UNKNOWN with a log.
    """
    ...
```

### Extension Surface

Shares `MetricDefinitionExtension` (owned by `7-metrics-ingest`). In-tree
subclasses shipped here:

- `source/site/automojo/extensions/pychestrate/metric_definition/pod/bringup.py` — `PodBringupMetric`.
- `source/site/automojo/extensions/pychestrate/metric_definition/pod/teardown.py` — `PodTeardownMetric`.
- `source/site/automojo/extensions/pychestrate/metric_definition/pod/result.py` — `PodLifecycleResultMetric`.
- `source/site/automojo/extensions/pychestrate/metric_definition/pod/active.py` — `PodActiveCountMetric`.
- `source/site/automojo/extensions/pychestrate/metric_definition/pod/failure.py` — `PodFailureMetric`.

### Events Emitted

- `entity.metric.definition_registered` (via `7-metrics-ingest`).

### Events Consumed

- `entity.pod.state_changed` (from `3-pod-lifecycle`).
- `entity.pod.registered` (from `3-static-pods`) and `entity.pod.materialized` (from `3-dynamic-pods`).
- `entity.pod.deregistered` / `entity.pod.torn_down` (from Layer 3).

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/metrics/domains/pod/`:

- `__init__.py`
- `resolver.py` — `PodMetricResolver`.
- `sampler.py` — `PodActiveSampler`.
- `failure_classes.py` — `PodFailureClassification` allow-list + `classify_failure`.
- `config.py` — `PodMetricsConfig`.
- `value_types.py` — `PodPairingEntry`, event payload dataclasses.

`MetricDefinitionExtension` subclasses under
`source/site/automojo/extensions/pychestrate/metric_definition/pod/`.

## Key Flows

### Flow 1 — Bring-up Pairing

1. `entity.pod.state_changed` with `state_to="bringing_up"` arrives; resolver stores `bringup_started_at`.
2. On `state_to="ready"`, entry is located; `duration = now - bringup_started_at`; `pychestrate_pod_bringup_seconds` emitted.
3. `entity.pod.state_changed` transitioning to terminal `failed` during bringup increments `pychestrate_pod_lifecycle_result_total{phase="bringup",result="failure"}` and `pychestrate_pod_failure_total`.

### Flow 2 — Tear-down Pairing

1. `entity.pod.state_changed` with `state_to="tearing_down"` arrives; resolver stores `teardown_started_at`.
2. On `state_to="torn_down"`, duration emitted; entry removed from pairing map.

### Flow 3 — Active Sampler

1. `PodActiveSampler.tick()` iterates `_active_pods`.
2. Emits `pychestrate_pod_active_count{project,pod_kind}` with `value = len(set)`.
3. Runs every `pod_active_sample_interval_seconds` (default 60).

### Flow 4 — Boot Reconstruction

1. At service boot, `rebuild_pairing_from_registry()` queries Layer 3 for pods currently in `bringing_up` / `tearing_down`.
2. For each, creates a `PodPairingEntry` with `bringup_started_at = pod.state_entered_at` (from Layer 3).
3. If timestamp unknown, entry is created with `None` — duration emit will be skipped; `pychestrate_pod_metrics_unpaired_total{phase}` increments on terminal state.

## Error Handling

- `SemanticError` for malformed state transitions (e.g., `ready` without `bringing_up`): bubble.
- Unknown `failure_class` string: `classify_failure` returns `UNKNOWN` and logs `pychestrate.pod_metrics.unknown_failure_class`.
- Pairing map eviction is non-error: drop sample + increment counter + log.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- `template` label value is sanitized + truncated to 200 bytes (shared sanitizer contract).
- `failure_class` is a closed enum — arbitrary strings from upstream events are mapped to `UNKNOWN`, preventing cardinality attacks.
- Active-pod set tracking uses `pod_id` UUIDs only — no free-form text persisted.
- Sampler runs under `svc.pod-metrics` scoped principal.

## Observability

Self-metrics:

- `pychestrate_pod_metrics_emit_duration_seconds{metric_name}` — histogram
- `pychestrate_pod_metrics_unpaired_total{phase}` — counter
- `pychestrate_pod_metrics_pairing_evicted_total` — counter
- `pychestrate_pod_metrics_active_sampler_tick_duration_seconds` — histogram

Domain metrics:

- `pychestrate_pod_bringup_seconds{project,pod_kind,template,provisioner}`
- `pychestrate_pod_teardown_seconds{project,pod_kind,template,provisioner}`
- `pychestrate_pod_lifecycle_result_total{project,pod_kind,phase,result}`
- `pychestrate_pod_active_count{project,pod_kind}`
- `pychestrate_pod_failure_total{project,pod_kind,failure_class}`

Log events: `pychestrate.pod_metrics.unpaired_terminal`, `pychestrate.pod_metrics.pairing_evicted`, `pychestrate.pod_metrics.unknown_failure_class`.

Trace spans: `pychestrate.pod_metrics.emit`, `pychestrate.pod_metrics.pair`, `pychestrate.pod_metrics.active_sampler_tick`, `pychestrate.pod_metrics.boot_reconstruct`.

## Open Questions

- Do we need per-provisioner percentile metrics separately, or is label-split sufficient? Current design: label-split. Timebox: Phase 9 midpoint.
- Should `pychestrate_pod_active_count` also expose `state_to` counts (`bringing_up`, `tearing_down`)? Candidate for a follow-up. Timebox: Phase 9 exit.
- Is `PodFailureClassification` extensible through a resource extension, or is the closed list final? Current design: closed list + `UNKNOWN` escape. Timebox: Phase 9 exit.
