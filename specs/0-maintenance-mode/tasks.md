# 0-maintenance-mode — Tasks

## Milestones

- **M1 — Skeleton:** Stub `MaintenanceGate` that always returns `active`,
  interface surface published so Phase 0 siblings (object store,
  persistence) can integrate. No REST, no persistence.
- **M2 — Core Behavior:** Full persistence, REST endpoints, audit
  trail, bus fanout, cache warm-up, precedence logic, middleware
  rejection with `Retry-After`.
- **M3 — Hardening:** Auto-expiry task, degraded-mode behavior, perf
  validation, admin UI integration, property tests, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/ccai/pychestrate/webservice/maintenance/` package skeleton per design.md.
- [ ] T1.2 — Implement `maintenance/mode.py::MaintenanceMode` enum and `mode_precedence`.
- [ ] T1.3 — Implement `maintenance/gate.py::MaintenanceGate` stub that always returns `active`; wire into the web app host so Phase 0 siblings can integrate.
- [ ] T1.4 — Implement `maintenance/errors.py::MaintenanceModeError` with scope / mode / retry_after / ends_at payload.
- [ ] T1.5 — Implement `maintenance/middleware.py::@read_only_safe` decorator and `@requires_writable` helper; route filter consults the gate.
- [ ] T1.6 — Integrate the gate into `0-object-store` put/delete/copy paths (stub always passes).
- [ ] T1.7 — Document the stub integration story in `usersguide/maintenance/integration.rst`.

### M2 — Core Behavior

- [ ] T2.1 — Add Alembic migration creating `core.maintenance_mode` and `core.maintenance_mode_audit` tables with PK + index as listed in design.md.
- [ ] T2.2 — Implement `maintenance/repository.py::MaintenanceRepository` with `load_all`, `upsert`, `clear`; audit row + mode upsert in a single unit of work.
- [ ] T2.3 — Replace the stub `MaintenanceGate` with the real one: cache, bus subscription, TTL re-read, `warm()` at startup.
- [ ] T2.4 — Implement REST endpoints under `/api/v1/admin/maintenance` (GET list, POST set, DELETE clear) gated by `pychestrate.maintenance.manage` / `.read`.
- [ ] T2.5 — Publish `maintenance.mode.changed` on `0-message-bus` on every upsert/clear.
- [ ] T2.6 — Validate `reason` length (10..512) and `ends_at >= now()+60s`; raise `SemanticError` otherwise.
- [ ] T2.7 — Integrate `MaintenanceGate.require_writable` into every write handler in `0-persistence`, `0-object-store`, and stub into the Phase 5 dispatcher.
- [ ] T2.8 — Seed the default `pychestrate.maintenance.manage` / `.read` permissions in `1-rbac` migrations; bind to `service_admin` role.

### M3 — Hardening

- [ ] T3.1 — Implement `maintenance/auto_expire.py` background task (30s period); transition expired scopes and emit `maintenance.mode.auto_expired`.
- [ ] T3.2 — Implement degraded-mode behavior: DB unavailable → serve from cache, log `pychestrate.maintenance.gate.degraded` ≤1/min.
- [ ] T3.3 — Benchmark NFR-1: cache-hit `status` p99 < 1 ms, mode change p99 < 50 ms, bus fan-out median < 50 ms. Fail CI on regression.
- [ ] T3.4 — Wire Prometheus metrics per design.md Observability.
- [ ] T3.5 — Add trace span `pychestrate.maintenance.gate.check` with `scope`, `mode`, `cache_hit` attributes.
- [ ] T3.6 — Integrate with `9-admin-ui`: maintenance-mode tile showing active scopes + scheduled expirations.
- [ ] T3.7 — Audit every multiline error to ensure `os.linesep.join([...])` usage.
- [ ] T3.8 — Document operator runbook under `usersguide/maintenance/runbook.rst` (enter read-only → backfill → clear → verify).

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (mode precedence monotonic + commutative) and Property 2 (read paths never gated), 1000 cases each.
- [ ] TT-3 — Integration test: set `service` to `read_only`, attempt `POST /api/v1/projects/...` → expect 503 with `Retry-After` and maintenance body; `GET` of the same resource returns 200.
- [ ] TT-4 — Extension-point test: N/A — no extension surface. Instead, add a test that adding a new route annotated `@read_only_safe` requires a matching entry in the closed in-tree list (lint check).
- [ ] TT-5 — Audit test: apply 10 maintenance changes with various reasons; assert 10 rows in `core.maintenance_mode_audit` with correct `actor_user_id`, `actor_ip`, `from_mode`, `to_mode`, `reason`.
- [ ] TT-6 — Auto-expiry test: set a scope with `ends_at = now()+90s`, wait 2 minutes, assert the scope transitioned to `active` and exactly one `maintenance.mode.auto_expired` event fired.
- [ ] TT-7 — Degraded test: pause Postgres, call `require_writable`; assert cached result used and `pychestrate.maintenance.gate.degraded` logged once.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
      (N/A — this feature exposes no extension surface by design.)
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
