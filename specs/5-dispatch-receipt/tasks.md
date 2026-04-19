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

- [ ] T1.1 — Create `jobs/dispatch/receipt/` package skeleton per design.md Component Breakdown.
- [ ] T1.2 — Implement `jobs/dispatch/receipt/schema.py` Pydantic models with `additionalProperties: false`.
- [ ] T1.3 — Implement `jobs/dispatch/receipt/repository.py` with `INSERT … ON CONFLICT (client_id, client_local_run_id) DO UPDATE` idempotency; add migration.
- [ ] T1.4 — Implement `jobs/dispatch/receipt/service.py::DispatchReceiptService.record` + `lookup_by_local` + `lookup_by_run`.
- [ ] T1.5 — Implement `jobs/dispatch/receipt/timer_wheel.py` hashed timer wheel; `expect` API to arm, `record` to cancel.
- [ ] T1.6 — Register `receipt_rehydrate_hook` at web-app startup priority `55` pulling outstanding `transmitted` attempts and rearming timers.
- [ ] T1.7 — Implement `jobs/dispatch/receipt/errors.py` with the error hierarchy.

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
