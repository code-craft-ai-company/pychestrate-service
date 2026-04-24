# 5-dispatch-receipt — Tasks

## Milestones

- **M1 — Skeleton:** `dispatch_receipt` table + repository,
  `DispatchReceiptService` record/lookup APIs, in-memory timer
  wheel, startup rehydrate.
- **M2 — Core Behavior:** Idempotent replay, late-arrival flag,
  bus event emission, gauge for pending receipts, `expect` timer
  arming integrated with `5-job-dispatch`.
- **M3 — Hardening:** Property tests, perf validation, Postgres-
  backed scheduler migration, duplicate-run rejection, privacy
  scrubbing in log formatters, dashboards + alert.

## Tasks

### M1 — Skeleton

- [x] T1.1 — Create `jobs/dispatch/receipt/` package skeleton per design.md Component Breakdown.
      *(``source/site/automojo/pychestrate/webservice/jobs/dispatch/receipt/``
      with ``schema.py``, ``models.py``, ``repository.py``,
      ``service.py``, ``timer_wheel.py``, ``errors.py``, and
      ``__init__.py``.)*
- [~] T1.2 — Implement `jobs/dispatch/receipt/schema.py` Pydantic models with `additionalProperties: false`.
      *(Ships as ``frozen=True`` dataclasses instead of Pydantic
      to avoid a new runtime dep. No wire-level
      ``additionalProperties:false`` is meaningful here yet —
      receipts arrive through the internal service API, not a
      REST surface. Pydantic upgrade is M3 alongside the
      ``jobs.envelope`` schema swap.)*
- [~] T1.3 — Implement `jobs/dispatch/receipt/repository.py` with `INSERT … ON CONFLICT (client_id, client_local_run_id) DO UPDATE` idempotency; add migration.
      *(The unique constraint on
      ``(client_id, client_local_run_id)`` is enforced at the DB
      level in migration ``018_phase3_dispatch_receipt``. The
      idempotent upsert is implemented at the service layer via
      ``find_by_local_key`` → early return — portable across
      SQLite tests and Postgres. Native
      ``INSERT ON CONFLICT DO UPDATE`` lands in M3.)*
- [x] T1.4 — Implement `jobs/dispatch/receipt/service.py::DispatchReceiptService.record` + `lookup_by_local` + `lookup_by_run`.
      *(``record`` + ``lookup_by_local`` + ``lookup_by_run``
      exposed as module-level functions; ``record`` computes
      ``late_arrival`` inline, enforces single-receipt-per-run +
      envelope-matches-attempt, and is idempotent on the local
      key.)*
- [x] T1.5 — Implement `jobs/dispatch/receipt/timer_wheel.py` hashed timer wheel; `expect` API to arm, `record` to cancel.
      *(``TimerWheel`` with ``expect / cancel / pending_count /
      peek / fire_expired / reset``. Simple dict-backed
      implementation — M3 swaps in a hashed wheel for O(1) tick
      cost once the pending-count moves past a few hundred.)*
- [~] T1.6 — Register `receipt_rehydrate_hook` at web-app startup priority `55` pulling outstanding `transmitted` attempts and rearming timers.
      *(``jobs.dispatch.repository.list_inflight_attempts`` +
      ``TimerWheel.expect`` are the rehydration building
      blocks. The actual hook registration on the app startup
      priority chain lands with the M2 wiring.)*
- [x] T1.7 — Implement `jobs/dispatch/receipt/errors.py` with the error hierarchy.
      *(``DispatchReceiptError`` base +
      ``DuplicateRunReceiptError``,
      ``ReceiptEnvelopeMismatchError``,
      ``ReceiptNotFoundError``.)*

### M2 — Core Behavior

- [ ] T2.1 — Wire `5-job-dispatch.transmit` to call `receipt_service.expect(attempt_id, run_id, project_id, deadline_at)`.
- [ ] T2.2 — Implement late-arrival flag: compute `late_arrival = received_at > deadline_at` in `record`.
- [ ] T2.3 — Publish `pychestrate.dispatch_receipt.recorded`, `...late_arrival`, `...expected_timeout`, `...duplicate_rejected` on `0-message-bus`.
- [ ] T2.4 — Emit `pychestrate_job_dispatch_pending_receipts{project}` gauge from `_pending_count_by_project`.
- [ ] T2.5 — Implement duplicate-run rejection: second *distinct* receipt for the same `run_id` raises `DuplicateRunReceiptError`.
- [ ] T2.6 — Implement envelope-mismatch guard: receipt.envelope_id ≠ attempt.envelope_id raises `SemanticError`.
- [ ] T2.7 — Enforce `client_id` match between the authenticated transport connection and the attempt's target client.

### M3 — Hardening

- [ ] T3.1 — Migrate timer wheel to a Postgres-backed scheduler so pending timers survive restart.
- [ ] T3.2 — Benchmark NFR-1: `record` p99 < 15 ms, `lookup_*` p99 < 5 ms; fail CI on regression.
- [ ] T3.3 — Emit Prometheus metrics and OTel trace span per design.md Observability.
- [ ] T3.4 — Add log-formatter scrubbing for `launch_pid` and hostnames by default.
- [ ] T3.5 — Add alert rule: late-arrival ratio > 5% over 5 min → `7-alerts-budgets`.
- [ ] T3.6 — Document client-agent responsibilities for receipt construction under `usersguide/jobs/dispatch/receipt.rst`.
- [ ] T3.7 — Verify multiline errors use `os.linesep.join([...])`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (bijection) and Property 2 (idempotent replay), 1000 cases each.
- [ ] TT-3 — Integration test: `5-job-dispatch` → `receipt_service.expect` → mock client ACK → `record` → `pychestrate.dispatch_receipt.recorded` observed on the bus; lookup by both keys resolves the same row.
- [ ] TT-4 — Timeout test: arm an expect with 100 ms deadline; assert `expected_timeout` fires exactly once and no receipt row is created unless a late receipt arrives.
- [ ] TT-5 — Restart-durability test (M3): arm N timers, restart the process, assert all N pending timers are re-armed and fire correctly.
- [ ] TT-6 — Extension-point test: N/A — feature declares no extensions. The equivalent required test task is a negative test verifying there is no registrable hook or factory.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
      — N/A for this feature (no extension points); TT-6 is a negative test.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
