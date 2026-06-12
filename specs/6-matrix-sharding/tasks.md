# 6-matrix-sharding — Tasks

## Milestones

- **M1 — Skeleton:** `ShardSet`/`ShardSpec` schema + `CartesianShardingStrategy` + `MatrixShardingService.expand` + dispatch via Layer 5 for a fixed `max_parallelism`.
- **M2 — Core Behavior:** Mirror Layer 5 state onto shards, reassembly with parallel-group ordering, fail-fast cancellation, deadline sweep, `WeightedByHistoryStrategy`.
- **M3 — Hardening:** Property tests, metrics/logs/traces, partial-success semantics, includes/excludes support, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create the `source/site/ccai/pychestrate/webservice/orchestration/pipelines/sharding/` package per design.md Component Breakdown.
- [ ] T1.2 — Add `0-persistence` migration for `shard_set` and `shard_spec` with indices listed in design.md.
- [ ] T1.3 — Implement `expansion.py` with canonical JSON for `MatrixSpec` and `shard_id = sha256(canonical_dims)[:16]`.
- [ ] T1.4 — Implement `strategy_protocol.py::ShardingStrategyProtocol`.
- [ ] T1.5 — Implement `CartesianShardingStrategy` under `source/site/ccai/factories/pychestrate/sharding/cartesian.py` with `PRECEDENCE = 1000`.
- [ ] T1.6 — Implement `service.py::MatrixShardingService.expand` producing persisted rows + emitting `entity.shard_set.expanded`.
- [ ] T1.7 — Implement `dispatch_shards` honoring `max_parallelism` via a semaphore.
- [ ] T1.8 — Register `GET /api/v1/projects/{id}/shard-sets/{set_id}` observability endpoint.

### M2 — Core Behavior

- [ ] T2.1 — Subscribe to `entity.run.state_changed`, `entity.run.completed`, `entity.run.failed`, `entity.run.cancelled`; update bound shards.
- [ ] T2.2 — Implement `reassembly.py` with group-ordered aggregation (lex order of dimension tuples).
- [ ] T2.3 — Implement `FailFastCartesianStrategy` and plumb `should_cancel_on_failure`; call `5-cancel-reconcile.cancel_bulk(...)` on trigger.
- [ ] T2.4 — Implement deadline sweep (60 s scheduled job) marking `timed_out` shard sets.
- [ ] T2.5 — Implement `WeightedByHistoryStrategy` at `source/site/ccai/factories/pychestrate/sharding/weighted_by_history.py` using `RuntimeHistoryQuery`.
- [ ] T2.6 — Implement includes/excludes support in `CartesianShardingStrategy`.
- [ ] T2.7 — Emit `entity.shard_set.completed`, `entity.shard.state_changed`, `entity.shard_set.fail_fast_triggered`.
- [ ] T2.8 — Implement `strategy_registry.py` accessor over the extension host; subscribe to `extension.reloaded`.

### M3 — Hardening

- [ ] T3.1 — Emit Prometheus metrics and OTel spans per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: `expand` p99 < 50 ms at 1 000 shards; reassembly p99 < 500 ms at 10 000 shards; dispatch throughput >= 500 shards/sec. Fail CI on regression.
- [ ] T3.3 — Enforce `allow_partial_success` / `min_success_fraction` semantics in reassembly.
- [ ] T3.4 — Sphinx docs for the internal API and strategy protocol.
- [ ] T3.5 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.6 — Validate that matrix-spec secret refs are not resolved here (delegated to `6-pipeline-definition`).

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (cardinality) and Property 2 (order-preserving reassembly) at 1000 cases each.
- [ ] TT-3 — Integration test: define a 3×2×4 matrix, expand with `FailFastCartesianStrategy`, dispatch against a synthetic client, force one shard to fail, assert remaining shards are cancelled and `entity.shard_set.completed` carries `partial: True`.
- [ ] TT-4 — Extension-point test: in-tree `CartesianShardingStrategy` (`PRECEDENCE = 1000`) plus a test-only `ReverseStrategy` (`PRECEDENCE = 1`); verify the reverse strategy wins and reorders shards in the ShardSet.
- [ ] TT-5 — Deadline test: a 5-shard set with one stuck shard; after `shard_set_max_duration_seconds`, sweep marks `unknown` and emits `timed_out`.
- [ ] TT-6 — Determinism test: expand the same spec 100 times; assert identical shard-id order every time.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
