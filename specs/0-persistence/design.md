# 0-persistence — Design

## Architecture

Persistence sits between `0-web-app-host` and every entity-owning feature. It
registers a priority-20 startup hook with the host; the hook performs
migrations, builds the connection pool, and exposes a typed repository
factory. The implementation is SQLAlchemy Core (not the ORM) — queries are
explicit, mapping is hand-rolled via dataclass + adapter. The repository is
the authoritative read/write path for entities; no feature may open its own
DB connection. Schema is versioned by Alembic, and extension-provided
schemas are composed into the same version graph via per-extension
`version_locations`. Authoritative state: Postgres. The in-process cache
(bounded LRU) is purely an optimization and is invalidated on any save in
the same process; cross-process coherence is delegated to `0-message-bus`
(Phase 0) which broadcasts `entity.<kind>.saved`.

## Data Model

Every entity shares a base shape in its own table:

- `id: UUID` — primary key (v7, time-ordered)
- `version: int` — optimistic concurrency counter, starts at 1
- `created_at: datetime` — set by Postgres `now()` default
- `updated_at: datetime` — set by the repository on every save
- `created_by: UUID | None` — FK to `users.id` once `1-user-management` ships
- `tenant_scope: str | None` — reserved; currently always `NULL`

Domain tables live under schema `core` (owned by Pychestrate). Extension
tables live under schema `ext_<ext_name>`. Indices are declared per-feature
in its own spec; the persistence layer mandates only:

- PRIMARY KEY on `id`
- UNIQUE on `(id, version)` expressed as a check constraint, not an index
- INDEX on `created_at DESC` for time-ordered scans

Alembic metadata tables:

- `alembic_version` — single row, stores core head
- `alembic_version_ext_<ext_name>` — one per loaded extension schema

## Interfaces

### Public API

N/A — internal-only feature.

### Internal API

```python
def load_persistence_config(
    service_config: ServiceConfig
) -> PersistenceConfig:
    """
        Load DB URL, pool sizing, and migration knobs.

        :param service_config: The host service config.

        :returns: An immutable PersistenceConfig.
        :raises: ConfigurationError
    """
    ...


def initialize_persistence(
    app: WebApplication,
    config: PersistenceConfig,
    migration_packs: list[MigrationPack]
) -> PersistenceLayer:
    """
        Run migrations and build the connection pool.

        :param app: The web application (for hook registration).
        :param config: The persistence config.
        :param migration_packs: Core pack plus any extension packs.

        :returns: A PersistenceLayer with pool and repository factory.
        :raises: ConfigurationError, DatabaseUnavailableError
    """
    ...


class Repository:
    def __init__(
        self,
        kind: str,
        table: Table,
        adapter: EntityAdapter,
        pool: ConnectionPool
    ) -> None:
        self._kind = kind
        self._table = table
        self._adapter = adapter
        self._pool = pool
        return

    def load(
        self,
        entity_id: UUID
    ) -> Entity | None:
        """
            Load a single entity by primary key.

            :param entity_id: The entity id.

            :returns: The entity or None if not found.
            :raises: DatabaseAcquireTimeoutError, DatabaseUnavailableError
        """
        ...

    def load_many(
        self,
        entity_ids: list[UUID]
    ) -> list[Entity]:
        """
            Load multiple entities by id in a single query.

            :param entity_ids: List of entity ids.

            :returns: List of entities in input order; missing ids omitted.
            :raises: DatabaseAcquireTimeoutError, DatabaseUnavailableError
        """
        ...

    def save(
        self,
        entity: Entity
    ) -> Entity:
        """
            Persist an entity with optimistic concurrency.

            :param entity: The entity to save.

            :returns: The entity with updated version and updated_at.
            :raises: StaleEntityError, DatabaseAcquireTimeoutError,
                     DatabaseUnavailableError
        """
        ...

    def delete(
        self,
        entity_id: UUID,
        expected_version: int
    ) -> bool:
        """
            Delete an entity if its version matches expected_version.

            :param entity_id: The entity id.
            :param expected_version: The version the caller last observed.

            :returns: True if a row was deleted, False if no match.
            :raises: DatabaseAcquireTimeoutError, DatabaseUnavailableError
        """
        ...


@contextmanager
def unit_of_work(
    pool: ConnectionPool
) -> Iterator[UnitOfWorkHandle]:
    """
        Open a transactional scope. Nested calls use SAVEPOINT.

        :param pool: The connection pool.

        :returns: A handle the caller binds repositories against.
        :raises: SemanticError on invalid nesting misuse.
    """
    ...
```

### Extension Surface

Resource extension:

```python
class EntityMigrationExtension(ResourceExtension):
    """
        Base class for migration packs shipped by extensions.

        Subclasses declare:
          - schema_prefix: class attribute (e.g. "ext_slackintegration")
          - migrations_path: class attribute (filesystem path to the pack)
          - min_service_version: class attribute
    """
    schema_prefix: str
    migrations_path: Path
    min_service_version: str

    @classmethod
    def get_alembic_config(cls) -> AlembicConfig:
        """
            Return the alembic config the host should fold into upgrade head.

            :returns: An AlembicConfig for this pack.
            :raises: ConfigurationError
        """
        ...
```

Reference implementation shipped in-tree:
`automojo/extensions/pychestrate/core/migrations/CoreMigrationExtension` —
registers the core `alembic/` directory as a pack so core migrations are
discovered through the same mechanism extensions use (dogfood).

### Events Emitted

On the in-process lifecycle channel (forwarded to `0-message-bus` once it
lands):

- `entity.<kind>.saved` — `{id: UUID, version: int, kind: str}`
- `entity.<kind>.deleted` — `{id: UUID, kind: str}`

Lifecycle:

- `persistence.migration.started` — `{head: str}`
- `persistence.migration.completed` — `{head: str, applied: list[str], duration_ms: float}`
- `persistence.migration.failed` — `{revision: str, error: str}`
- `persistence.pool.closed` — `{}`

### Events Consumed

None in Phase 0. In Phase 0.5, the extension host re-loads migration packs
on a `extension.reloaded` event.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/`:

- `persistence/__init__.py`
- `persistence/config.py` — `PersistenceConfig` dataclass.
- `persistence/pool.py` — `ConnectionPool`, acquire timeouts, drain.
- `persistence/migrations/runner.py` — orchestrates core + extension packs.
- `persistence/migrations/advisory_lock.py` — Postgres advisory lock helper.
- `persistence/migrations/pack.py` — `MigrationPack` dataclass.
- `persistence/repository.py` — `Repository`, `Entity` base, `EntityAdapter`.
- `persistence/uow.py` — `unit_of_work`, nested savepoint logic.
- `persistence/errors.py` — `StaleEntityError`, `DatabaseAcquireTimeoutError`,
  `DatabaseUnavailableError` (none are caught-and-swallowed).
- `persistence/hooks.py` — startup/shutdown hooks registered on the host.
- `persistence/alembic/` — core migration directory (env.py, script_mako,
  versions/).

Extension reference in `source/site/automojo/extensions/pychestrate/core/migrations/`.

## Key Flows

### Flow 1 — Startup migration

1. Host invokes `persistence_startup_hook` at priority 20.
2. Hook loads `PersistenceConfig` from env.
3. Hook discovers `EntityMigrationExtension` subclasses via the extension
   host (or, in Phase 0 without the host, a hardcoded list containing just
   the core pack).
4. Hook acquires advisory lock `919191`.
5. Hook runs `alembic upgrade head` against each pack in dependency order
   (core first, then extensions). Emits `persistence.migration.started`,
   per-revision metrics, and `persistence.migration.completed`.
6. Hook releases advisory lock.
7. Hook builds `ConnectionPool(min=4, max=32)` and stores it on the app.
8. Host continues to the next startup phase.

### Flow 2 — Entity save with optimistic concurrency

1. Caller loads entity via `repository.load(id)` → observes `version=7`.
2. Caller mutates locally, calls `repository.save(entity)`.
3. Repository issues `UPDATE ... SET version=8, updated_at=now() WHERE
   id=? AND version=7 RETURNING *`.
4. If `rowcount == 0`, repository issues a `SELECT version` to distinguish
   missing vs stale and raises `StaleEntityError` with both versions in the
   message.
5. If `rowcount == 1`, repository emits `entity.<kind>.saved`.

### Flow 3 — Unit of work with nesting

1. `with unit_of_work(pool) as outer:` begins a transaction.
2. Inside, caller calls `with unit_of_work(pool) as inner:` — this issues
   `SAVEPOINT sp_<n>`.
3. If the inner block exits normally, the savepoint is released.
4. If the inner block raises, the savepoint is rolled back; outer continues.
5. If caller calls `inner.commit()`, `SemanticError` is raised (nested UoW
   may not commit independently).

## Error Handling

- `StaleEntityError` is a domain error (caller must retry or abort) — never
  caught by the repository.
- `DatabaseAcquireTimeoutError` and `DatabaseUnavailableError` bubble to the
  request handler, which translates to HTTP 503.
- `SemanticError` (e.g., mis-nested UoW, repository used after pool closed)
  never caught per AGENTS.md.
- `ConfigurationError` raised by migration runner on malformed DSN or
  missing migration file; bubbles to host, which exits with code 78.
- Alembic exceptions during `upgrade head` are caught exactly once and
  reclassified as `ConfigurationError` with a multiline message:

```python
err_msg_lines = ["Migration failed; database not upgraded."]
err_msg_lines.append("FAILED REVISION: {}".format(revision))
err_msg_lines.append("PREVIOUS HEAD: {}".format(previous_head))
err_msg_lines.append("ERROR: {}".format(str(cause)))

err_msg = os.linesep.join(err_msg_lines)
raise ConfigurationError(err_msg) from cause
```

## Security Considerations

- DSN never logged; `PersistenceConfig.__repr__` redacts password.
- Parameterized queries only; a lint rule (`ruff` + custom check) rejects
  `text()` with f-string interpolation.
- Role `pychestrate_service` has `CONNECT, USAGE, SELECT, INSERT, UPDATE,
  DELETE` on schema `core`; extension roles are granted on their own schema.
- DDL happens only via migrations; the service role lacks `CREATE TABLE`.
- Once `1-secrets-vault` lands, DSN is retrieved through the vault client
  at startup; env fallback is gated by `PYCHESTRATE_DEV_MODE`.
- All entity writes are audited by a later `1-audit-log` subscriber on
  `entity.<kind>.saved`.

## Observability

Metrics:

- `pychestrate_persistence_query_duration_seconds{operation,entity_kind}` — histogram
- `pychestrate_persistence_pool_in_use` — gauge
- `pychestrate_persistence_pool_waiters` — gauge
- `pychestrate_persistence_pool_acquire_timeout_total` — counter
- `pychestrate_persistence_migration_duration_seconds{revision}` — histogram
- `pychestrate_persistence_stale_entity_total{entity_kind}` — counter

Log events:

- `pychestrate.persistence.migration.started`
- `pychestrate.persistence.migration.completed`
- `pychestrate.persistence.migration.failed`
- `pychestrate.persistence.pool.acquire_timeout`
- `pychestrate.persistence.pool.closed`
- `pychestrate.persistence.stale_entity`

Trace spans:

- `pychestrate.persistence.query` — attributes `operation`, `entity_kind`,
  `rows`, `duration_ms`
- `pychestrate.persistence.unit_of_work` — attributes `nested`, `rollback`

Dashboards: DB health tile in `9-admin-ui` (Phase 10), migration timeline in
`7-orchestration-metrics`.

## Open Questions

- Do we allow extensions to declare cross-pack FK constraints, or must they
  be name-only references? Timebox: decide before Phase 0.5 (extension host
  ships).
- SQLAlchemy 2.x vs plain `psycopg` — do we commit to SQLAlchemy Core's
  query builder or the psycopg/pgcrypto direct path for hotspots? Timebox:
  decide before Phase 0 exit.
- Pool sizing defaults: 32 is a guess; revisit after Phase 3 live-traffic
  data. Timebox: decide before Phase 4 (Resources & Scheduling).
