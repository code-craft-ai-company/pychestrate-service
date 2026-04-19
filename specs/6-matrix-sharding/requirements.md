# 6-matrix-sharding — Requirements

## Introduction

The `6-matrix-sharding` feature turns a single pipeline stage or test
invocation described with a matrix spec (e.g., `os × python × region`)
into a deterministic fan-out of many sibling jobs and then reassembles
their results into a single parent outcome. The feature ships in
**Phase 5** with the test-orchestration polish (`6-artifact-browser`,
`6-flake-tracking`, `6-triage-bug-linking`, `6-compare-runs`) and
sits between `6-pipeline-definition` (which carries matrix specs in
stages) and `6-test-orchestration` / `6-build-orchestration` (which
actually trigger the sharded jobs via Layer 5). This feature owns the
`ShardSet` entity, the factory protocol `sharding_strategy`, and the
reassembly algebra. It introduces no new dispatch plumbing — each
shard becomes an ordinary Layer 5 job.

## Requirements

### Requirement 1: Deterministic Fan-Out From A Matrix Spec

**User Story:** As a pipeline author, I want my `matrix` block to expand
into a predictable number of shards with stable identifiers, so that
reruns and comparisons are possible.

**Acceptance Criteria (EARS):**

1. WHEN `sharding.expand(matrix_spec, strategy_name, aspects)` is called THEN the system SHALL return a `ShardSet` with `shards: list[ShardSpec]` where `len(shards) == prod(len(values_i) for values_i in matrix_spec.dimensions)` unless the strategy declares `includes` / `excludes` adjustments that the system SHALL apply in declared order.
2. WHEN expansion runs THEN each `ShardSpec.shard_id: str` SHALL be `sha256(canonical_json(dimension_values))[:16]` AND SHALL collide across expansions only if the dimension tuple is identical.
3. IF the matrix spec declares a dimension with zero values THEN the system SHALL raise `SemanticError` naming the empty dimension.
4. WHERE the strategy supports `max_parallelism: int` THEN the system SHALL clamp the concurrent in-flight shard count to that value before handing off to `5-job-dispatch`.
5. WHEN the same `(matrix_spec_canonical, strategy_name)` is expanded twice THEN the returned `ShardSet.shard_ids` SHALL be identical AND in the same order.

### Requirement 2: Reassembly Preserves Shard Group Order

**User Story:** As a consumer of sharded results, I want the aggregated
outcome to reflect each shard's state without losing per-shard order
inside a parallel group.

**Acceptance Criteria (EARS):**

1. WHEN all shards in a `ShardSet` reach terminal states THEN the system SHALL emit `entity.shard_set.completed` with a `SummaryAggregate` containing per-shard states, overall pass/fail, started_at/finished_at bounds, and a reassembled ordered list keyed by the original dimension tuple.
2. IF any shard is `failed` or `cancelled` AND the strategy's `fail_fast` is true THEN the system SHALL cancel the remaining shards via `5-cancel-reconcile` AND SHALL still emit `entity.shard_set.completed` with a `partial: True` flag.
3. WHEN shards run concurrently within a declared parallel group THEN the reassembled per-group order SHALL match the lexicographic order of the dimension tuples of that group (no permutation by completion time).
4. WHERE `strategy.allow_partial_success` is true THEN the overall `ShardSet.state` SHALL be `completed_partial` if at least one shard is `completed` AND fewer than `strategy.min_success_fraction` of shards succeeded.

### Requirement 3: Sharding Strategy Factory Protocol

**User Story:** As an extension author, I want to ship a custom
sharding strategy (e.g., weighted by historical runtime), so that
matrix fan-out can adopt smarter policies per site.

**Acceptance Criteria (EARS):**

1. WHEN the extension host loads a `ShardingStrategyProtocol` implementation THEN the system SHALL verify `strategy_name`, `expand`, `should_cancel_on_failure`, `describe` classmethods AND raise `ConfigurationError` naming any missing method.
2. IF two strategies share `strategy_name` and `PRECEDENCE` THEN the system SHALL raise `ConfigurationError` at load time naming both classes.
3. WHEN `sharding.expand(...)` is called with an unknown `strategy_name` THEN the system SHALL raise `SemanticError` before any DB write.
4. WHERE a strategy declares `requires_runtime_history: True` THEN the system SHALL pass a `RuntimeHistoryQuery` accessor into `expand(...)` AND SHALL raise `ConfigurationError` if history is unavailable for the project.

## Property-Based Test Requirements

### Property 1: Cardinality Equals The Product Of Dimension Sizes (Without Includes/Excludes)

- **Invariant:** For any matrix spec with dimensions `D1 × D2 × ... × Dn` and no `includes`/`excludes`, `expand(spec, "cartesian")` produces exactly `∏|Di|` shards with distinct `shard_id`s.
- **Generator:** `hypothesis.strategies.lists(lists(text(min_size=1, max_size=20), min_size=1, max_size=5, unique=True), min_size=1, max_size=4)`.
- **Assertion:** `len(shards) == prod(len(d) for d in dims)` and `len({s.shard_id for s in shards}) == len(shards)`.
- **Sample size:** 1000 generated cases

### Property 2: Reassembly Is Order-Preserving Within A Parallel Group

- **Invariant:** For any DAG with M stages and K parallel groups per stage, `reassemble(shard_set)` emits each group's shards in the lexicographic order of their dimension tuples, regardless of completion order.
- **Generator:** A DAG strategy producing `hypothesis.strategies.integers(min_value=1, max_value=5)` stages each with `integers(min_value=1, max_value=5)` parallel groups and `integers(min_value=1, max_value=20)` shards per group; completion times sampled uniformly.
- **Assertion:** For every group G, `[s.dims for s in aggregate.groups[G]] == sorted([s.dims for s in aggregate.groups[G]])`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `expand(...)` p99 < 50 ms for matrices up to 1 000 shards. Reassembly of a 10 000-shard `ShardSet` p99 < 500 ms. Parallel shard dispatch throughput >= 500 shards/sec into `5-job-dispatch`.
- **NFR-2 (Security):** Every shard inherits the parent run's RBAC scope and `envelope_field` extensions. A strategy SHALL NOT be able to inject dimension values derived from unscoped inputs; dimension values originate from the matrix spec only.
- **NFR-3 (Observability):** Metrics `pychestrate_pipeline_shardset_expand_duration_seconds{project,strategy}` (histogram), `pychestrate_pipeline_shard_count{project,strategy}` (histogram), `pychestrate_pipeline_shardset_state{project,strategy,state}` (counter), `pychestrate_pipeline_reassembly_duration_seconds{project}` (histogram). Log events `pychestrate.pipeline.shardset.expanded`, `pychestrate.pipeline.shardset.completed`, `pychestrate.pipeline.shardset.fail_fast_triggered`. Trace spans `pychestrate.pipeline.shardset.expand`, `pychestrate.pipeline.shardset.reassemble`.
- **NFR-4 (Reliability):** A crashed shard SHALL NOT block reassembly — a hard deadline per `ShardSet` (default 2 h, configurable) closes out missing shards as `unknown` and the aggregate emits with a `timed_out: True` flag.

## Out of Scope

- The pipeline DSL itself (see `6-pipeline-definition`).
- Artifact aggregation across shards (handled by `6-build-artifacts` and `5-artifact-store`).
- Flake-aware resharding (see `6-flake-tracking`).

## Dependencies

- **Depends on:** `6-test-orchestration`, `6-pipeline-definition`, `5-job-dispatch`, `5-cancel-reconcile`, `0-persistence`, `0-message-bus`, `E-extension-host`.
- **Depended on by:** `6-pipeline-definition`, `7-test-metrics`, `9-wc-pipeline-dag`.
- **Extension points exposed:** `factory: sharding_strategy` — cartesian, fail-fast cartesian, weighted-by-history, round-robin, custom.
