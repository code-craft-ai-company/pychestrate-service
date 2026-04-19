# 6-matrix-sharding — Design

## Architecture

`6-matrix-sharding` is a pure orchestration component. It takes a
`MatrixSpec` (from `6-pipeline-definition` or from a runtime API call)
and a chosen `sharding_strategy`, expands it into an ordered `ShardSet`
of `ShardSpec` rows, and schedules each shard as an ordinary Layer 5
job. It also owns the inverse transform — reassembly — subscribing to
`entity.run.state_changed` for constituent shards and emitting
`entity.shard_set.completed` when all shards have terminated. The
authoritative source of truth for shard lifecycles is Layer 5; this
feature owns the fan-out bookkeeping table plus the per-strategy
ordering rules. Ships in Phase 5.

## Data Model

Tables in `0-persistence`:

- `shard_set`:
  - `shard_set_id: UUID` — PK
  - `project_id: UUID`
  - `parent_kind: str` — `"pipeline_stage" | "test_run" | "build_run"`.
  - `parent_id: UUID`
  - `strategy_name: str`
  - `matrix_spec_canonical_sha256: str`
  - `state: ShardSetState` — `{expanding, in_progress, completed, completed_partial, failed, cancelled, timed_out}`
  - `fail_fast: bool`
  - `allow_partial_success: bool`
  - `min_success_fraction: float`
  - `started_at: datetime`
  - `finished_at: datetime | None`
- `shard_spec`:
  - `shard_id: str` — 16-char hex derived from dims.
  - `shard_set_id: UUID` — FK, part of composite PK.
  - `dimension_values_canonical_json: bytes`
  - `parallel_group: str`
  - `run_id: UUID | None` — bound after dispatch (Layer 5 `run_id`).
  - `state: ShardState`
  - `sequence_in_group: int` — the lexicographic ordinal within its group.
  - PK `(shard_set_id, shard_id)`

Indices: `(shard_set_id, parallel_group, sequence_in_group)`, `(run_id)`.

Value types:

- `MatrixSpec` — `{dimensions: dict[str, list[str]], includes: list[dict], excludes: list[dict]}`.
- `ShardSpec` — `{shard_id, dimension_values, parallel_group, sequence_in_group}`.
- `ShardSet` — wrapper with `shards`, `strategy_name`, `parent`.
- `SummaryAggregate` — `{per_shard: list[ShardOutcome], overall: PassFail, groups: dict[str, list[ShardOutcome]], partial: bool, timed_out: bool}`.

## Interfaces

### Public API

Internal to the service — matrix-shard APIs are called by `6-pipeline-definition`
and `6-test-orchestration`. No public REST. `GET /api/v1/projects/{id}/shard-sets/{set_id}` is exposed for
observability.

### Internal API

```python
class MatrixShardingService:
    def __init__(
        self,
        repo: ShardSetRepository,
        dispatcher: JobDispatcher,
        canceller: CancelReconcileService,
        bus: MessageBus,
        strategy_registry: ShardingStrategyRegistry,
        runtime_history: RuntimeHistoryQuery,
        clock: Clock,
        config: ShardingConfig
    ) -> None:
        self._repo = repo
        self._dispatcher = dispatcher
        self._canceller = canceller
        self._bus = bus
        self._strategy_registry = strategy_registry
        self._runtime_history = runtime_history
        self._clock = clock
        self._config = config
        return

    def expand(
        self,
        project_id: UUID,
        parent_kind: str,
        parent_id: UUID,
        matrix_spec: MatrixSpec,
        strategy_name: str,
        aspects: ExpandAspects | None = None
    ) -> ShardSet:
        """
            Expand a matrix spec into a ShardSet.

            :param project_id: Owning project.
            :param parent_kind: "pipeline_stage" | "test_run" | "build_run".
            :param parent_id: The parent record id.
            :param matrix_spec: The matrix dimensions/includes/excludes.
            :param strategy_name: Registered sharding strategy.
            :param aspects: Behavior parameters (max_parallelism, timeouts).

            :returns: ShardSet with stable shard ids.
            :raises: SemanticError, ConfigurationError
        """
        ...

    def dispatch_shards(
        self,
        shard_set_id: UUID,
        envelope_builder: Callable[[ShardSpec], JobEnvelope]
    ) -> None:
        """
            Dispatch every shard as a Layer 5 job honoring max_parallelism.

            :param shard_set_id: Target shard set.
            :param envelope_builder: Callback that produces an envelope per shard.

            :returns: None.
            :raises: ConfigurationError
        """
        ...

    def apply_shard_state(
        self,
        run_id: UUID,
        new_state: RunState
    ) -> None:
        """
            Mirror a Layer 5 run state onto its bound shard.

            :param run_id: Layer 5 run id bound to a shard.
            :param new_state: New state from the run state machine.

            :returns: None.
            :raises: SemanticError
        """
        ...

    def reassemble(
        self,
        shard_set_id: UUID
    ) -> SummaryAggregate:
        """
            Compute the aggregate outcome of a completed shard set.

            :param shard_set_id: Target shard set.

            :returns: SummaryAggregate ordered by parallel_group then sequence_in_group.
            :raises: SemanticError
        """
        ...
```

### Extension Surface

Factory protocol declared here:

```python
class ShardingStrategyProtocol(FactoryProtocolBase):
    """
        Contract for sharding_strategy implementations.
    """
    factory_protocol_name: str = "sharding_strategy"

    @classmethod
    def strategy_name(cls) -> str:
        """
            :returns: Strategy identifier.
        """
        ...

    @classmethod
    def expand(
        cls,
        matrix_spec: MatrixSpec,
        runtime_history: RuntimeHistoryQuery | None
    ) -> list[ShardSpec]:
        """
            Produce the shard list for the given matrix.

            :returns: Ordered list of ShardSpec.
            :raises: SemanticError
        """
        ...

    @classmethod
    def should_cancel_on_failure(cls) -> bool:
        """
            :returns: Whether a failing shard cancels siblings.
        """
        ...

    @classmethod
    def describe(cls) -> StrategyDescription:
        """
            :returns: Human description and declared flags
                      (requires_runtime_history, allow_partial_success,
                      default_min_success_fraction).
        """
        ...
```

Reference implementations in `source/site/automojo/factories/pychestrate/sharding/`:

- `CartesianShardingStrategy` — `PRECEDENCE = 1000`; full cartesian expansion with includes/excludes.
- `FailFastCartesianStrategy` — `PRECEDENCE = 1000`; cartesian + `should_cancel_on_failure == True`.
- `WeightedByHistoryStrategy` — `PRECEDENCE = 500`; re-orders shards by historical duration DESC to front-load long shards; requires `RuntimeHistoryQuery`.

### Events Emitted

- `entity.shard_set.expanded` — `{shard_set_id, project_id, shard_count, strategy_name}`
- `entity.shard_set.completed` — `{shard_set_id, state, per_shard_summary, started_at, finished_at}`
- `entity.shard.state_changed` — `{shard_set_id, shard_id, run_id, state}`
- `entity.shard_set.fail_fast_triggered` — `{shard_set_id, triggering_shard_id}`

### Events Consumed

- `entity.run.state_changed` from `5-run-state-machine` — mirror onto shard.
- `entity.run.completed`, `entity.run.failed`, `entity.run.cancelled` — drive terminal shard state.
- `extension.reloaded` — refresh strategy registry.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/orchestration/pipelines/sharding/`:

- `__init__.py`
- `service.py` — `MatrixShardingService`.
- `repository.py` — `ShardSetRepository`.
- `expansion.py` — matrix expansion primitives, canonical JSON of matrix.
- `reassembly.py` — group-ordered reassembly.
- `strategy_protocol.py` — factory protocol.
- `strategy_registry.py` — extension-host accessor.
- `aspects.py` — `ExpandAspects` (max_parallelism, timeout).
- `errors.py` — `ShardSetTimedOutError`.
- `rest/v1_routes.py` — observability endpoint.

Factories under `source/site/automojo/factories/pychestrate/sharding/`.

## Key Flows

### Flow 1 — Expand and dispatch

1. Pipeline stage executor calls `MatrixShardingService.expand(...)`.
2. Strategy looked up; for `WeightedByHistoryStrategy`, `RuntimeHistoryQuery` fetched.
3. `expansion.py` canonicalizes `MatrixSpec` and computes shard ids (`sha256(dims)[:16]`).
4. `ShardSet` and `ShardSpec`s persisted in one transaction.
5. `entity.shard_set.expanded` emitted.
6. Caller invokes `dispatch_shards` with an envelope builder; each shard is an ordinary Layer 5 `dispatch` call.
7. `max_parallelism` enforced through an in-memory semaphore plus a rate-limited tickler.

### Flow 2 — Mirror and reassemble

1. Each Layer 5 run state change arrives on the bus.
2. Service resolves `shard_id` from `run_id` via the `shard_spec.run_id` index.
3. Shard state updated; if `state in terminal_set`, decrement in-flight counter.
4. When the in-flight counter reaches zero, `reassemble` runs.
5. `SummaryAggregate` emitted via `entity.shard_set.completed`.
6. If `strategy.should_cancel_on_failure` and a shard failed, `canceller.cancel_bulk(remaining_runs)` fires before reassembly.

### Flow 3 — Deadline sweep

1. A scheduled sweep every 60 s scans for `shard_set` rows older than `shard_set_max_duration_seconds` (default 7200) still non-terminal.
2. Remaining shards marked `unknown`; `ShardSet.state = timed_out`; `entity.shard_set.completed` emitted with `timed_out: True`.

## Error Handling

- `SemanticError` on empty dimensions, unknown `strategy_name`, illegal `parent_kind`: bubble.
- `ConfigurationError` on missing strategy methods or missing runtime history: bubble.
- `ShardSetTimedOutError`: used internally during deadline sweep; surfaced in metrics, not raised to callers.
- Out-of-order state events handled by the same replay logic as `6-test-orchestration`'s mirror.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- `sharding.expand` and `sharding.dispatch` are internal-only calls; no REST entry point for expansion.
- Shards inherit the parent run's RBAC scope; a strategy cannot escalate privileges — it only reorders/filters shards.
- `matrix_spec` values SHALL NOT resolve through `2-global-variables` within this feature — resolution happens upstream in `6-pipeline-definition` so audit stays there.

## Observability

Metrics:

- `pychestrate_pipeline_shardset_expand_duration_seconds{project,strategy}` — histogram
- `pychestrate_pipeline_shard_count{project,strategy}` — histogram
- `pychestrate_pipeline_shardset_state_total{project,strategy,state}` — counter
- `pychestrate_pipeline_reassembly_duration_seconds{project}` — histogram
- `pychestrate_pipeline_shardset_in_flight{project}` — gauge

Log events: `pychestrate.pipeline.shardset.expanded`, `pychestrate.pipeline.shardset.completed`, `pychestrate.pipeline.shardset.fail_fast_triggered`, `pychestrate.pipeline.shardset.timed_out`.

Trace spans: `pychestrate.pipeline.shardset.expand`, `pychestrate.pipeline.shardset.reassemble`, `pychestrate.pipeline.shardset.dispatch`.

## Open Questions

- Should shards be persisted as rows or kept in object storage when `shard_count > 50 000`? Timebox: Phase 5 exit.
- `WeightedByHistoryStrategy` lookback window — 30 days or 7 days? Timebox: Phase 5 midpoint.
- Do we expose `sharding_strategy` overrides at the pipeline stage level or only at the project default? Timebox: Phase 6 with `6-pipeline-definition`.
