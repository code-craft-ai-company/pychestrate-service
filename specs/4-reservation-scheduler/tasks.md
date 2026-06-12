# 4-reservation-scheduler — Tasks

## Milestones

- **M1 — Skeleton:** Persistent queue table, dispatch worker skeleton
  subscribed to `entity.reservation.released`, `FifoScheduler` hard-wired,
  enqueue/cancel internal API.
- **M2 — Core Behavior:** `reservation_scheduler` factory protocol and
  four in-tree algorithms, per-pool algorithm selection, starvation
  recovery, drain-mode integration, state rehydration on startup.
- **M3 — Hardening:** Perf targets, metrics/logs/traces, extension tests,
  property tests, fairness dashboard.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/ccai/pychestrate/webservice/resources/scheduler/` per design.md.
- [ ] T1.2 — Alembic migration `0040_scheduler_entries` creating `core.scheduler_entries` with PK, UNIQUE on `reservation_id`, and the three composite indices in design.md.
- [ ] T1.3 — Implement `models.py` with `SchedulerEntry`, `SchedulerEntryState`, `SchedulerAspects`, `SchedulerAccounting`.
- [ ] T1.4 — Implement `repository.py::SchedulerRepository` with `insert`, `cancel_by_reservation`, `next_for_pool`, and the fair-share running-seconds query.
- [ ] T1.5 — Implement `service.py::enqueue` (with aspects normalization) and `service.py::cancel`.
- [ ] T1.6 — Implement `dispatch_worker.py` subscribing to `entity.reservation.released` and the 1s tick; FIFO hard-wired.
- [ ] T1.7 — Implement `rehydrate_on_startup` rebuilding in-memory queues from persisted entries.
- [ ] T1.8 — Emit `pychestrate.scheduler.enqueued` and `.cancelled`.

### M2 — Core Behavior

- [ ] T2.1 — Declare `ReservationSchedulerProtocol` (FactoryProtocolBase) and register it through `E-factory-protocols`.
- [ ] T2.2 — Implement `FifoScheduler` (PRECEDENCE 1000), `PriorityScheduler` (1100), `FairShareScheduler` (1200), `DeadlineScheduler` (1300) under `source/site/ccai/factories/pychestrate/reservation_scheduler/`.
- [ ] T2.3 — Wire per-pool algorithm selection via factory lookup by name; fall back to FIFO on missing algorithm, emit `algorithm_missing` exactly once per pool, set `pychestrate_scheduler_algorithm_fallback{pool}=1`.
- [ ] T2.4 — Add materialized view `core.fair_share_running_seconds_mv` with a 30s refresh; `FairShareScheduler` reads from it.
- [ ] T2.5 — Implement `starvation.py::run_starvation_sweep` with the threshold formula in requirements.md (Requirement 3); set `promoted_at`, head-of-queue promotion, emit `.starvation_promoted`.
- [ ] T2.6 — Implement `.starvation_blocked` emission when a promoted entry does not grant after one dispatch cycle; categorize blocker as `conflict | validator | pool_empty`.
- [ ] T2.7 — Subscribe to `0-maintenance-mode.drain_started` / `.drain_ended`; reject new `enqueue` during drain with `SchedulerUnavailableError`; continue dispatching existing entries.
- [ ] T2.8 — Subscribe to `extension.reloaded` to rebuild factory-protocol bindings.
- [ ] T2.9 — Integrate with `4-checkout-checkin.grant_from_queue`; bound per-release retry count at 3; increment `pychestrate_scheduler_grant_retry_total`.

### M3 — Hardening

- [ ] T3.1 — Add every metric from design.md Observability.
- [ ] T3.2 — Benchmark `pick_next_for_pool` p99 < 5 ms at queue depth 1,000; fail CI on regression (NFR-1).
- [ ] T3.3 — Benchmark release → grant p99 < 50 ms; fail CI on regression.
- [ ] T3.4 — Trace spans `pychestrate.scheduler.dispatch` and `.starvation_sweep`.
- [ ] T3.5 — Audit-log every `starvation_promoted` event with waited_seconds and deadline_missed_by_seconds.
- [ ] T3.6 — Sphinx docs for the factory protocol and each in-tree scheduler.
- [ ] T3.7 — Ship an out-of-tree `pychestrate-ext-scheduler-costaware` demonstrating a custom `CostAwareScheduler`; integration test selects it by name.
- [ ] T3.8 — Add Scheduler Fairness panel to `7-resource-metrics` dashboards.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Hypothesis tests implementing Property 1 (deadline-missed jobs eventually granted across FIFO/priority/fair-share/deadline/adversarial algorithms) and Property 2 (release-driven dispatch latency ≤ 50 ms), 1000 cases each.
- [ ] TT-3 — Integration test: rehydration on restart — enqueue 100 entries across 5 pools, restart the service, assert every entry re-appears in its pool's queue and dispatches as capacity frees.
- [ ] TT-4 — Extension-point test: `AdversarialStarvingScheduler` at PRECEDENCE=100 is active for a pool; assert starvation-recovery still fires and metrics reflect it.
- [ ] TT-5 — Fair-share convergence test: two owners with equal weight, 200 continuous enqueues each; over any 100-grant window the owner-grant-count difference ≤ 2.
- [ ] TT-6 — Drain test: enter maintenance mode; assert new `enqueue` raises `SchedulerUnavailableError` while existing queued entries still grant on release.

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
