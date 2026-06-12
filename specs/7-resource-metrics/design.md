# 7-resource-metrics — Design

## Architecture

`7-resource-metrics` combines event-driven emission (for
reservation/conflict/quarantine counters) with a periodic polling
sampler (for utilization gauges). It lives in **Phase 9**, shares
`MetricDefinitionExtension` with `7-metrics-ingest`, and depends on
Layer 4 for authoritative resource state. The feature owns the
`UtilizationSampler` background task and the `ResourceMetricResolver`
translator. No persistent state is owned here — pools, resources, and
reservations are authoritative in Layer 4; samples live in
`0-timeseries-backend`.

## Data Model

No persisted schema. In-memory state:

- `sampler_state: SamplerState` — `{last_tick_at, consecutive_overruns, inflight}`
- `conflict_rule_allow_list: set[str]` — refreshed from
  `4-conflict-deconfliction`'s `ConflictRuleExtension` catalog on service
  start and on `extension.reloaded`.

Value types:

- `PoolUtilizationSnapshot`:
  - `pool_id: UUID`
  - `resource_kind: str`
  - `sizes: dict[ResourceState, int]` with `ResourceState ∈ {available,reserved,quarantined,offline}`
- `ReservationWaitSample` — `{pool_id, resource_kind, priority, wait_seconds}`

## Interfaces

### Public API

None directly. Query access via `0-timeseries-backend`'s
`POST /api/v1/metrics/query_range`.

### Internal API

```python
class ResourceMetricResolver:
    def __init__(
        self,
        inventory: ResourceInventory,
        pools: ResourcePools,
        conflict_rules: ConflictRuleRegistry,
        clock: Clock,
        config: ResourceMetricsConfig
    ) -> None:
        self._inventory = inventory
        self._pools = pools
        self._conflict_rules = conflict_rules
        self._clock = clock
        self._config = config
        return

    def on_reservation_created(
        self,
        event: ReservationCreatedEvent
    ) -> list[Sample]:
        ...

    def on_reservation_forced_released(
        self,
        event: ReservationForcedReleasedEvent
    ) -> list[Sample]:
        ...

    def on_conflict_detected(
        self,
        event: ConflictDetectedEvent
    ) -> list[Sample]:
        ...

    def on_resource_quarantined(
        self,
        event: ResourceQuarantinedEvent
    ) -> list[Sample]:
        ...

    def on_health_probe_completed(
        self,
        event: HealthProbeCompletedEvent
    ) -> list[Sample]:
        ...


class UtilizationSampler:
    def __init__(
        self,
        pools: ResourcePools,
        inventory: ResourceInventory,
        facade: TimeseriesFacade,
        clock: Clock,
        config: ResourceMetricsConfig
    ) -> None:
        self._pools = pools
        self._inventory = inventory
        self._facade = facade
        self._clock = clock
        self._config = config
        self._last_tick_at: datetime | None = None
        self._task: asyncio.Task | None = None
        return

    def start(
        self
    ) -> None:
        """
            Begin a background task that ticks every
            utilization_sample_interval_seconds.

            :returns: None.
        """
        ...

    def stop(
        self
    ) -> None:
        ...

    def tick(
        self
    ) -> None:
        """
            Single sampling pass. Public for testing.

            :returns: None.
            :raises: None (transient errors handled internally).
        """
        ...


def truncate_reason(
    raw: str,
    max_bytes: int
) -> str:
    """
        Truncate + SHA-256 suffix, returning safe label value.

        :returns: Safe label value.
    """
    ...
```

### Extension Surface

Shares `MetricDefinitionExtension` (owned by `7-metrics-ingest`). In-tree
subclasses shipped here:

- `source/site/ccai/extensions/pychestrate/metric_definition/resource/utilization.py` — `ResourcePoolUtilizationMetric`.
- `source/site/ccai/extensions/pychestrate/metric_definition/resource/pool_size.py` — `ResourcePoolSizeMetric`.
- `source/site/ccai/extensions/pychestrate/metric_definition/resource/wait.py` — `ResourceReservationWaitMetric`.
- `source/site/ccai/extensions/pychestrate/metric_definition/resource/conflict.py` — `ResourceConflictMetric`.
- `source/site/ccai/extensions/pychestrate/metric_definition/resource/quarantine.py` — `ResourceQuarantineMetric`.
- `source/site/ccai/extensions/pychestrate/metric_definition/resource/forced_release.py` — `ResourceForcedReleaseMetric`.
- `source/site/ccai/extensions/pychestrate/metric_definition/resource/probe.py` — `ResourceHealthProbeDurationMetric`.

### Events Emitted

- `entity.metric.definition_registered` (via `7-metrics-ingest`).

### Events Consumed

- `entity.reservation.created` (from `4-checkout-checkin`).
- `entity.reservation.released` / `entity.reservation.forced_released` (from `4-checkout-checkin`).
- `entity.conflict.detected` (from `4-conflict-deconfliction`).
- `entity.resource.quarantined` (from `4-resource-health`).
- `entity.resource.health_probe_completed` (from `4-resource-health`).
- `extension.reloaded` — refresh `conflict_rule_allow_list`.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/metrics/domains/resource/`:

- `__init__.py`
- `resolver.py` — `ResourceMetricResolver`.
- `sampler.py` — `UtilizationSampler`.
- `labels.py` — `truncate_reason`, shared sanitizer contract.
- `config.py` — `ResourceMetricsConfig` (sample interval, overrun threshold, retention knobs).
- `value_types.py` — `PoolUtilizationSnapshot`, event payload dataclasses.

`MetricDefinitionExtension` subclasses under
`source/site/ccai/extensions/pychestrate/metric_definition/resource/`.

## Key Flows

### Flow 1 — Sampler Tick

1. Background task wakes every `utilization_sample_interval_seconds`.
2. Calls `pools.list_pools()` to enumerate pools; for each, `inventory.snapshot(pool)` returns `{state: count}`.
3. Emits `pychestrate_resource_pool_size{pool,resource_kind,state}` gauges per `(pool, resource_kind, state)` and `pychestrate_resource_pool_utilization_ratio{pool,resource_kind}` gauge.
4. On `InventoryTransientError`, retries once with 500 ms backoff; on persistent failure, logs and moves on.
5. Overruns > `utilization_sample_overrun_warn_seconds` log `pychestrate.resource_metrics.sampler_overrun`.

### Flow 2 — Reservation Event

1. `entity.reservation.created` arrives with `requested_at`, `granted_at`, `priority`.
2. Resolver emits `pychestrate_resource_reservation_wait_seconds`.

### Flow 3 — Conflict / Quarantine

1. `entity.conflict.detected` arrives with `rule`.
2. Resolver validates `rule` against the current `conflict_rule_allow_list`; if missing, relabels as `unregistered` and logs.
3. Emits `pychestrate_resource_conflict_total`.
4. `entity.resource.quarantined` arrives; `reason` truncated if oversized; `pychestrate_resource_quarantine_total` incremented.

### Flow 4 — Health Probe Duration

1. `entity.resource.health_probe_completed` arrives with `probe`, `probe_duration_seconds`.
2. Resolver observes `pychestrate_resource_health_probe_duration_seconds`.

## Error Handling

- `SemanticError` for malformed event payloads (negative duration, missing pool): bubble.
- `InventoryTransientError`: caught, one retry, then skip tick with `pychestrate.resource_metrics.sampler_overrun` log.
- Unknown `conflict.rule`: relabel + log; do not drop sample.
- Oversized quarantine `reason`: truncate + sidecar log.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- Pool membership may contain sensitive device identifiers; label values always go through `truncate_reason` / sanitizer.
- Raw quarantine reasons persisted only to `1-audit-log` sidecar with `audit.read:sidecar` gating, not to metric labels.
- Sampler runs under `svc.resource-metrics` scoped principal with read-only access to Layer 4 APIs.

## Observability

Self-metrics:

- `pychestrate_resource_metrics_emit_duration_seconds{metric_name}` — histogram
- `pychestrate_resource_metrics_sampler_overrun_total` — counter
- `pychestrate_resource_metrics_unregistered_conflict_rule_total` — counter
- `pychestrate_resource_metrics_sampler_tick_duration_seconds` — histogram
- `pychestrate_resource_metrics_pool_snapshot_error_total{error_class}` — counter

Domain metrics:

- `pychestrate_resource_pool_utilization_ratio{pool,resource_kind}`
- `pychestrate_resource_pool_size{pool,resource_kind,state}`
- `pychestrate_resource_reservation_wait_seconds{pool,resource_kind,priority}`
- `pychestrate_resource_conflict_total{pool,resource_kind,rule}`
- `pychestrate_resource_quarantine_total{resource_kind,reason}`
- `pychestrate_resource_forced_release_total{pool,resource_kind,source}`
- `pychestrate_resource_health_probe_duration_seconds{resource_kind,probe}`

Log events: `pychestrate.resource_metrics.sampler_overrun`, `pychestrate.resource_metrics.unregistered_conflict_rule`, `pychestrate.resource_metrics.quarantine_reason_truncated`.

Trace spans: `pychestrate.resource_metrics.sampler_tick`, `pychestrate.resource_metrics.emit`, `pychestrate.resource_metrics.pool_snapshot`.

## Open Questions

- Should the sampler interval be configurable per-pool? Current design: global. Timebox: Phase 9 midpoint.
- Does `pychestrate_resource_pool_size` need a per-`owner_project` label for chargeback? Current design: no, leaves chargeback to dashboard-level projection. Timebox: Phase 9 exit.
- How do we expose `mean_time_to_quarantine_recovery`? Candidate for a follow-up metric after Phase 9 exit.
