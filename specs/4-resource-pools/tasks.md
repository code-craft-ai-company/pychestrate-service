# 4-resource-pools — Tasks

## Milestones

- **M1 — Skeleton:** Package scaffold, pool table + members view,
  `POST /api/v1/resource-pools` with `FifoAllocationStrategy` hard-wired,
  baseline membership materialization.
- **M2 — Core Behavior:** `pool_allocation_strategy` factory protocol and
  four in-tree strategies, inventory-event-driven recompute, `pool.pick`
  with sandbox-safe strategy dispatch, pod-member-kind guard.
- **M3 — Hardening:** Perf targets, metrics/logs/traces, fallback
  observability, admin UI, out-of-tree strategy pack, property tests.

## Tasks

### M1 — Skeleton

- [x] T1.1 — Scaffold `source/site/automojo/pychestrate/webservice/resources/pools/` per design.md.
- [x] T1.2 — Alembic migration `0020_resource_pools` creating `core.resource_pools` and `core.resource_pool_members` with the indices listed in design.md.
      *(Migration 022 creates both tables.)*
- [x] T1.3 — Implement `models.py::ResourcePool` + `PoolCandidate`, plus `allocation_aspects.py::AllocationAspects` dataclass (sticky_tag, job_hint, preferred_member).
      *(``AllocationAspects`` lives on
      ``resources/pools/service.py`` with the public surface re-
      exported from ``__init__.py``. M1 honors
      ``preferred_member``; ``sticky_tag`` and ``job_hint`` land
      with the M2 strategy-registry path.)*
- [x] T1.4 — Implement `repository.py` pool CRUD and membership materialization.
      *(insert_pool / find_pool_by_id / find_pool_by_name /
      list_pools / delete_pool / find_member / list_members /
      insert_member / delete_member.)*
- [x] T1.5 — Hard-wire `FifoAllocationStrategy` in the service; plumb the aspects argument end to end.
      *(``pick_candidate`` sorts by ``added_at`` after filtering
      to ``ResourceState.AVAILABLE`` members; aspects flow
      through the public surface.)*
- [~] T1.6 — Add `api.py` with `POST`, `GET`, `DELETE` for `/api/v1/resource-pools`; wire `1-rbac` perms.
      *(Service-layer ``create_pool`` / ``get_pool`` /
      ``list_pools`` / ``add_member`` / ``remove_member`` ship;
      Flask-RestX routes land with the broader Phase-4 REST
      surface.)*
- [x] T1.7 — Emit `pychestrate.resource.pool.created` and `.deleted`.
      *(Plus ``.member_added`` and ``.member_removed`` for
      symmetry on member churn.)*

### M2 — Core Behavior

- [ ] T2.1 — Declare `PoolAllocationStrategyProtocol` (FactoryProtocolBase) and register it through `E-factory-protocols`.
- [ ] T2.2 — Implement in-tree strategies: `FifoAllocationStrategy`, `LruAllocationStrategy`, `HealthWeightedAllocationStrategy`, `StickyTagAllocationStrategy`, each with a distinct `PRECEDENCE` value from design.md.
- [ ] T2.3 — Service uses `get_override_types_by_order("pool_allocation_strategy")` to pick strategy by name; unknown name raises `PoolStrategyUnknownError`.
- [ ] T2.4 — Implement `pick_from_pool` with exception-safe delegation and FIFO fallback on strategy crash; increment `pychestrate_resource_pool_strategy_fallback_total`.
- [ ] T2.5 — Reject pool creation when `kind` is declared by a `PodMemberKindExtension`; raise `PoolKindRejectedError` with the pod-checkout-is-lock-unit explanation.
- [ ] T2.6 — Subscribe on `0-message-bus` to `entity.resource.registered|quarantined|healed|retired|attributes_updated` and recompute affected pools on a bounded executor (max 8).
- [ ] T2.7 — Implement `POST /api/v1/resource-pools/{pool_id}:refresh` and the `auto_refresh=false` branch that skips event-driven recompute.
- [ ] T2.8 — Implement `PATCH /api/v1/resource-pools/{pool_id}` with version-checked optimistic concurrency.
- [ ] T2.9 — Emit `pychestrate.resource.pool.refreshed` with added/removed diff arrays.

### M3 — Hardening

- [ ] T3.1 — Add all metrics from design.md Observability.
- [ ] T3.2 — Benchmark `pool.pick` p99 < 3 ms on a 512-member pool; fail CI on regression (NFR-1).
- [ ] T3.3 — Benchmark event-driven recompute p99 < 100 ms across affected pools; fail CI on regression.
- [ ] T3.4 — Emit trace spans `pychestrate.resource.pool.pick` and `.recompute`.
- [ ] T3.5 — Ship an out-of-tree sample `pychestrate-ext-pool-strategies` that adds a `CostWeightedAllocationStrategy`; integration test loads it and the service picks from it.
- [ ] T3.6 — Add Pool Health tile to `9-admin-ui` (size + picks/min per pool).
- [ ] T3.7 — Log `pychestrate.resource.pool.strategy_missing` exactly once at startup if a pool's persisted strategy name is not in the registry; pin that pool to FIFO.
- [ ] T3.8 — Sphinx docs for the factory protocol and each in-tree strategy.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Hypothesis tests implementing Property 1 (picks cover only live members under concurrency) and Property 2 (FIFO fairness gap bound), 1000 cases each.
- [ ] TT-3 — Integration test: create pool → inventory churn (register, retire, quarantine, heal) → assert materialized membership converges and `refreshed` events match the diffs.
- [ ] TT-4 — Extension-point test: `DeterministicTestAllocationStrategy` (test-only) at PRECEDENCE=100 overrides FIFO and its picks are deterministic end to end.
- [ ] TT-5 — Strategy-crash test: a strategy that raises on `pick` causes a single log + metric increment and FIFO fallback returns a valid candidate; no 5xx to the caller.

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
