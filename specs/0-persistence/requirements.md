# 0-persistence — Requirements

## Introduction

The `0-persistence` feature provides Pychestrate's durable store: a Postgres
database, an Alembic-driven migration system, a connection pool, and a typed
entity repository layer. It is the Phase 0 sibling of `0-web-app-host` and
the foundation for every entity-owning feature (`2-projects`,
`2-global-variables`, `3-client-registry`, `3-pod-definitions`, `5-run-state-machine`,
etc.). Extensions ship their own migration packs via the
`EntityMigrationExtension` resource surface so out-of-tree extensions can own
their own schema without forking the core service. This feature depends only
on `0-web-app-host` for lifecycle and ships in Phase 0.

## Requirements

### Requirement 1: Schema Migration on Startup

**User Story:** As a service operator, I want schema migrations applied
automatically before request traffic is served, so that a deploy never runs
against a half-migrated schema.

**Acceptance Criteria (EARS):**

1. WHEN the `0-persistence` startup hook runs THEN the system SHALL compare
   `alembic_version` against the compiled-in head and run all pending
   migrations before the hook returns.
2. IF a migration raises any exception THEN the system SHALL abort startup
   with `ConfigurationError`, log `pychestrate.persistence.migration.failed`
   with the offending revision id, and leave the database untouched by any
   subsequent revisions.
3. WHILE migrations are running the system SHALL acquire a Postgres advisory
   lock on key `919191` so only one service process migrates at a time.
4. WHERE an `EntityMigrationExtension` is loaded the system SHALL include its
   migration pack in the same `alembic upgrade head` run, under the
   extension's declared `schema_prefix`.

### Requirement 2: Entity Repository with Optimistic Concurrency

**User Story:** As a feature author, I want a typed repository that enforces
optimistic locking, so that concurrent writers cannot silently overwrite each
other's changes.

**Acceptance Criteria (EARS):**

1. WHEN `repository.save(entity)` is called with a stale `version` THEN the
   system SHALL raise `StaleEntityError` and SHALL NOT mutate the row.
2. IF `repository.save(entity)` succeeds THEN the system SHALL increment
   `version` by 1, update `updated_at` to `now()`, and emit
   `entity.<kind>.saved` on the lifecycle channel.
3. WHEN `repository.load(kind, entity_id)` is called against a missing row
   THEN the system SHALL return `None` (not raise).
4. WHERE the entity kind has an `ExtensionMigrationSchema` prefix the system
   SHALL route reads and writes to the extension's schema.

### Requirement 3: Connection Pool with Bounded Blocking

**User Story:** As a service operator, I want the DB connection pool to fail
fast under saturation, so that request threads do not stall indefinitely.

**Acceptance Criteria (EARS):**

1. WHEN a request acquires a connection AND the pool is exhausted THEN the
   system SHALL wait at most `db_pool_acquire_timeout_seconds` (default 3)
   before raising `DatabaseAcquireTimeoutError`.
2. IF `DatabaseAcquireTimeoutError` is raised THEN the system SHALL emit
   metric `pychestrate_persistence_pool_acquire_timeout_total` and log
   `pychestrate.persistence.pool.acquire_timeout`.
3. WHILE Postgres is unreachable the system SHALL fail fast with
   `DatabaseUnavailableError` after one retry at 250 ms and NOT retry again;
   upstream features decide retry policy.
4. WHEN the shutdown hook runs the system SHALL drain idle connections,
   close the pool, and emit `pychestrate.persistence.pool.closed`.

### Requirement 4: Transactional Unit of Work

**User Story:** As a feature author, I want an explicit `unit_of_work`
context so my change set is atomic across repositories.

**Acceptance Criteria (EARS):**

1. WHEN `unit_of_work()` exits normally THEN the system SHALL commit all
   repository writes performed inside it.
2. IF any exception escapes the `with` block THEN the system SHALL roll back
   the transaction before the exception propagates.
3. WHERE a unit of work nests inside another unit of work the system SHALL
   use a SAVEPOINT and raise `SemanticError` if the caller attempts to
   commit the inner one independently.

## Property-Based Test Requirements

### Property 1: Save / Load Round-Trip Preserves Entity State

- **Invariant:** For any valid entity instance, writing it via
  `repository.save` and re-reading via `repository.load` yields byte-equal
  field values (excluding server-assigned `updated_at` and incremented
  `version`).
- **Generator:** `hypothesis.strategies.builds(ExampleEntity,
  name=text(min_size=1, max_size=128), payload=dictionaries(text(), integers(),
  max_size=16), tags=sets(text(min_size=1, max_size=24), max_size=8))`.
- **Assertion:** `loaded.to_dict(exclude={"updated_at", "version"}) ==
  saved.to_dict(exclude={"updated_at", "version"})`.
- **Sample size:** 1000 generated cases

### Property 2: Optimistic Concurrency is Strictly Monotonic

- **Invariant:** For any sequence of interleaved `save` calls against the
  same entity id, at most one caller succeeds per `version`, and the final
  `version` equals the number of successful saves + initial version.
- **Generator:** `hypothesis.strategies.lists(tuples(integers(min_value=0,
  max_value=9), just("save")), min_size=2, max_size=50)` driving concurrent
  `save` attempts across N threads.
- **Assertion:** `len([r for r in results if r == "ok"]) ==
  final_version - initial_version` and every failed save raised
  `StaleEntityError`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Repository `load` by primary key p99 < 5 ms at
  pool size 32 on a co-located Postgres 15. Bulk `load_many(ids)` for
  1,000 ids p99 < 80 ms. Migration of an empty-diff head check completes in
  under 150 ms.
- **NFR-2 (Security):** DB credentials MUST be pulled from
  `1-secrets-vault` once it lands; until then, from env var
  `PYCHESTRATE_DB_URL` which MUST never be logged. All queries MUST use
  parameterized SQL; string-concatenated SQL is a CI failure. Role
  `pychestrate_service` has CRUD on owned schemas only; extension schemas
  are granted per-extension roles.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_persistence_query_duration_seconds{operation,entity_kind}`
  (histogram), `pychestrate_persistence_pool_in_use` (gauge),
  `pychestrate_persistence_pool_waiters` (gauge),
  `pychestrate_persistence_pool_acquire_timeout_total` (counter),
  `pychestrate_persistence_migration_duration_seconds{revision}` (histogram),
  `pychestrate_persistence_stale_entity_total{entity_kind}` (counter).
  Log events `pychestrate.persistence.migration.started`,
  `pychestrate.persistence.migration.completed`,
  `pychestrate.persistence.migration.failed`,
  `pychestrate.persistence.pool.acquire_timeout`,
  `pychestrate.persistence.pool.closed`,
  `pychestrate.persistence.stale_entity`. Trace spans
  `pychestrate.persistence.query` and `pychestrate.persistence.unit_of_work`.
- **NFR-4 (Reliability):** Survives Postgres restart: after connectivity
  returns, the pool reconnects transparently for new acquires. Partial-write
  failure modes (commit after network split) surface as
  `DatabaseUnavailableError` and the request 503s — the service never
  half-commits.

## Out of Scope

- Backup and restore (see `10-backup-dr`).
- Audit logging of entity changes (see `1-audit-log`).
- Query-level RBAC enforcement (see `1-rbac`).
- Caching layer in front of the repository — explicitly deferred until
  usage patterns are observed.
- Cross-database distributed transactions.

## Dependencies

- **Depends on:** `0-web-app-host` (startup/shutdown hooks), Postgres 15+,
  `sqlalchemy` (Core only — ORM discouraged), `alembic`.
- **Depended on by:** `2-projects`, `2-global-variables`, `2-tagging`,
  `3-client-registry`, `3-pod-definitions`, `3-pod-lifecycle`,
  `4-resource-inventory`, `4-checkout-checkin`, `5-run-state-machine`,
  `5-artifact-store` (index only), `1-user-management`, `1-rbac`,
  `1-audit-log`, `1-feature-flags`, and every other entity-owning feature.
- **Extension points exposed:** `resource: EntityMigrationExtension` — an
  extension registers a migrations directory and a `schema_prefix`; the host
  runs those migrations during the same `alembic upgrade head` pass.
