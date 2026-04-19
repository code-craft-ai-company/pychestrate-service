# 5-shared-results-backend — Tasks

## Milestones

- **M1 — Skeleton:** `shared_results_allocation` table, deterministic
  `path_builder`, `allocate`/`resolve` APIs, integration into
  `5-job-envelope`.
- **M2 — Core Behavior:** Timer-wheel driven deadlines,
  `mark_landed` subscription to `entity.result_tree.landed`,
  `release` API, `presign_put` for capable drivers,
  maintenance-mode gating.
- **M3 — Hardening:** Property tests, perf validation, dashboards,
  alert on timeout rate, audit-log subscriber, cross-driver test
  coverage.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `jobs/results/` package skeleton per design.md Component Breakdown.
- [ ] T1.2 — Add Postgres migration for `shared_results_allocation`.
- [ ] T1.3 — Implement `jobs/results/repository.py::AllocationRepository` with upsert-on-conflict-do-nothing idempotency on `run_id`.
- [ ] T1.4 — Implement `jobs/results/path_builder.py` with regex-sanitized components and the prescribed template `<project_slug>/results/<yyyy>/<mm>/<dd>/<job_type>/<run_id>`.
- [ ] T1.5 — Implement `jobs/results/backend.py::SharedResultsBackend.allocate` + `resolve` happy paths.
- [ ] T1.6 — Wire `5-job-envelope.codec.build` to call `shared_backend.allocate(...)` and populate `envelope.results.backend_key_prefix` + `backend_driver`.
- [ ] T1.7 — Implement `jobs/results/errors.py` with `AllocationNotFoundError`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `_timer_wheel` and arm a timer per allocation at `hard_deadline_at`.
- [ ] T2.2 — Subscribe to `entity.result_tree.landed` and call `mark_landed` in the subscription handler.
- [ ] T2.3 — Implement `release` API (called by retention + operator flows).
- [ ] T2.4 — Implement `presign_put` delegating to `ObjectStore.presign_put` with TTL capped at `min(hard_deadline_at + 300 s, max_presign_expires_seconds)`.
- [ ] T2.5 — Subscribe to `maintenance.mode.changed`; update `_maintenance_gate`; reject new `allocate` with `MaintenanceModeError`.
- [ ] T2.6 — Publish `pychestrate.shared_results.allocated / landed / prefix_timed_out / released` on `0-message-bus`.
- [ ] T2.7 — Add startup hook rehydrating pending timers from `shared_results_allocation` rows in `pending`.
- [ ] T2.8 — Emit `entity.run.failed` event path via `5-run-state-machine` subscription on `prefix_timed_out` (timeout with no landing).

### M3 — Hardening

- [ ] T3.1 — Emit Prometheus metrics and OTel trace span per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: `allocate` p99 < 25 ms; `mark_landed`/`release` p99 < 15 ms; 1000 allocations/sec sustained.
- [ ] T3.3 — Add alert: allocation timeout rate > 5% over 1 h → `7-alerts-budgets`.
- [ ] T3.4 — Wire `1-audit-log` subscriber for allocation and release events.
- [ ] T3.5 — Integration test against both `LocalFsObjectStoreDriver` and `S3ObjectStoreDriver` to confirm prefix behavior is driver-agnostic.
- [ ] T3.6 — Document operator guide `usersguide/jobs/results/shared_backend.rst` with prefix conventions and retention contract.
- [ ] T3.7 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.8 — Coordinate with `0-object-store` on `delete_prefix` API landing (consumer in `2-retention-policies`, not here).

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (uniqueness + idempotency) and Property 2 (scope + key regex), 1000 cases each.
- [ ] TT-3 — Integration test: full dispatch with `SharedResultsBackend` wired → client writes tree under returned prefix → `entity.result_tree.landed` → `mark_landed` observed.
- [ ] TT-4 — Idempotency test: call `allocate(run_id)` 100 times concurrently; assert exactly one row persists and every call returns identical prefix.
- [ ] TT-5 — Timeout test: allocate with `hard_deadline_at = now + 2 s`; wait; assert `prefix_timed_out` event and allocation status `timed_out`.
- [ ] TT-6 — Maintenance-mode test: flip project to read-only; assert `allocate` raises `MaintenanceModeError`; assert `resolve` continues to work.
- [ ] TT-7 — Extension-point test: N/A — this feature declares no extension points. TT-7 is a negative test verifying there is no registrable factory or resource under `jobs/results/`.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
      — N/A for this feature; reuses `object_store_driver` from `0-object-store`.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
