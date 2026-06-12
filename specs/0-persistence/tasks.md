# 0-persistence — Tasks

## Milestones

- **M1 — Skeleton:** Alembic wired, core `alembic_version` table present,
  connection pool stands up, repository returns None for unknown ids.
- **M2 — Core Behavior:** Optimistic-concurrency `save`/`load`/`delete`,
  unit of work with savepoints, entity lifecycle events, extension
  migration pack composition.
- **M3 — Hardening:** Perf targets validated, chaos tests (Postgres
  restart), metrics and traces wired, DSN secret handoff to
  `1-secrets-vault`, sample extension migration pack integrated.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Add `source/site/ccai/pychestrate/webservice/persistence/` package skeleton per design.md Component Breakdown.
- [ ] T1.2 — Implement `persistence/config.py::PersistenceConfig` with DSN redaction in `__repr__`.
- [ ] T1.3 — Initialize Alembic under `persistence/alembic/` with an empty `versions/` directory and an `env.py` that accepts a `MigrationPack`.
- [ ] T1.4 — Implement `persistence/migrations/runner.py` supporting a single core pack (extension composition deferred to T2.5).
- [ ] T1.5 — Implement advisory-lock helper (key `919191`) and wrap the upgrade call.
- [ ] T1.6 — Implement `persistence/pool.py::ConnectionPool` with `min=4, max=32`, `acquire_timeout=3s`, fast-fail on unreachable DB.
- [ ] T1.7 — Register `persistence_startup_hook` on the web app with priority `20` and a matching shutdown hook that drains the pool.
- [ ] T1.8 — Implement `persistence/repository.py::Repository.load` and `load_many` returning `None` / omitting missing ids.

### M2 — Core Behavior

- [ ] T2.1 — Implement `Repository.save` with `UPDATE ... WHERE id=? AND version=? RETURNING *`, `StaleEntityError` on `rowcount==0`, version increment, `updated_at=now()`.
- [ ] T2.2 — Implement `Repository.delete(entity_id, expected_version)` returning bool.
- [ ] T2.3 — Implement `persistence/uow.py::unit_of_work` context manager with `SAVEPOINT` for nesting; raise `SemanticError` if inner `commit()` is called.
- [ ] T2.4 — Emit `entity.<kind>.saved` / `entity.<kind>.deleted` on the lifecycle channel (forwarded to `0-message-bus` once available).
- [ ] T2.5 — Implement `EntityMigrationExtension` resource surface and fold discovered packs into `alembic upgrade head` (depends on `E-resource-extensions` from Phase 0.5; stub until then).
- [ ] T2.6 — Ship `CoreMigrationExtension` as the in-tree reference under `source/site/ccai/extensions/pychestrate/core/migrations/`.
- [ ] T2.7 — Write first two real core migrations: `0001_pychestrate_base` (schema `core`, extensions for uuid-ossp + pgcrypto) and `0002_service_bookkeeping` (service_info table).
- [ ] T2.8 — Wire per-query span `pychestrate.persistence.query` and unit-of-work span `pychestrate.persistence.unit_of_work`.

### M3 — Hardening

- [ ] T3.1 — Add Prometheus metrics from design.md Observability, with query-level timing histograms.
- [ ] T3.2 — Benchmark `load` p99 < 5 ms, `load_many(1000)` p99 < 80 ms against a co-located Postgres 15; fail CI on regression (NFR-1).
- [ ] T3.3 — Add CI lint: reject `sqlalchemy.text()` with f-string interpolation.
- [ ] T3.4 — Replace `PYCHESTRATE_DB_URL` env lookup with `1-secrets-vault` client call once that feature ships; keep env fallback only in dev mode.
- [ ] T3.5 — Chaos test: kill Postgres mid-request, assert `DatabaseUnavailableError` surfaces and subsequent requests recover once Postgres returns.
- [ ] T3.6 — Document the repository + unit-of-work patterns under `usersguide/persistence/` (sphinx).
- [ ] T3.7 — Verify all multiline error messages use `os.linesep.join([...])`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (round-trip) and Property 2 (monotonic concurrency), 1000 cases each, using a real Postgres in CI.
- [ ] TT-3 — Integration test: startup runs migrations, service serves traffic, SIGTERM drains the pool, next boot is idempotent (`alembic_version` head unchanged).
- [ ] TT-4 — Extension-point test: a sample `ext_sample_migration` pack installs via `EntityMigrationExtension`, creates a table under `ext_sample`, and core + extension migrations both reach head; a test-only override using a lower numeric PRECEDENCE on `CoreMigrationExtension` is accepted.
- [ ] TT-5 — Concurrency stress test: 64 threads save-loop the same entity; assert `final_version == successes + 1` and every failure is `StaleEntityError`.

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
