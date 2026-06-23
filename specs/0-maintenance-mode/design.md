# 0-maintenance-mode — Design

## Architecture

Maintenance mode is two things: (1) a `MaintenanceGate` — an in-process
cache + bus-subscriber consulted by every write-bearing feature — and (2)
an admin REST surface backed by the persistence layer. The gate is
authoritative for the *effective* mode in-process; the DB
(`core.maintenance_mode`) is authoritative for the *persistent* mode. On
startup the gate warms from DB; at runtime it updates via the
`maintenance.mode.changed` bus topic. A TTL re-read guards against bus
delivery gaps. Scope precedence (`service` dominates `project`,
`draining` dominates `read_only`) is computed in `MaintenanceGate.status`,
so callers pass the most specific scope they know about and get the
effective answer. Per implementation-plan.md this feature lands in
**Phase 10**; Phases 0–9 ship a stub `MaintenanceGate` that always
returns `active` so the integration surface exists from day one.

## Data Model

Persistent tables (schema `core`):

```
core.maintenance_mode(
    scope            text PRIMARY KEY,    -- "service" | "project:<slug>"
    mode             text NOT NULL,       -- "active" | "read_only" | "draining"
    reason           text NOT NULL,
    ends_at          timestamptz NULL,
    changed_at       timestamptz NOT NULL DEFAULT now(),
    changed_by       uuid NOT NULL REFERENCES users(id),
    version          int NOT NULL DEFAULT 1
)

core.maintenance_mode_audit(
    audit_id         uuid PRIMARY KEY,
    scope            text NOT NULL,
    from_mode        text NOT NULL,
    to_mode          text NOT NULL,
    reason           text NOT NULL,
    ends_at          timestamptz NULL,
    actor_user_id    uuid NOT NULL,
    actor_ip         inet NOT NULL,
    changed_at       timestamptz NOT NULL DEFAULT now()
)
CREATE INDEX ON core.maintenance_mode_audit (scope, changed_at DESC)
```

In-memory:

- `gate_cache: dict[str, CachedMode]` keyed by scope.
- `CachedMode`:
  - `mode: MaintenanceMode`
  - `ends_at: datetime | None`
  - `reason: str`
  - `loaded_at: datetime`
  - `ttl_seconds: float`

## Interfaces

### Public API

REST:

- `GET /api/v1/admin/maintenance` — auth-gated by
  `pychestrate.maintenance.read`. Returns the list of non-`active`
  scopes.
- `POST /api/v1/admin/maintenance` — auth-gated by
  `pychestrate.maintenance.manage`. Body `{scope, mode, reason,
  ends_at}`.
- `DELETE /api/v1/admin/maintenance/<scope>` — auth-gated by
  `pychestrate.maintenance.manage`. Clears the scope back to `active`.

### Internal API

```python
class MaintenanceMode(enum.Enum):
    active = "active"
    read_only = "read_only"
    draining = "draining"


def mode_precedence(
    modes: list[MaintenanceMode]
) -> MaintenanceMode:
    """
        Combine a list of scope modes into the effective mode.

        :param modes: One or more scope modes.

        :returns: The most restrictive mode under the ordering
                  active < read_only < draining.
        :raises: SemanticError on empty list.
    """
    ...


class MaintenanceGate:
    def __init__(
        self,
        repo: MaintenanceRepository,
        bus: MessageBus,
        config: MaintenanceConfig
    ) -> None:
        self._repo = repo
        self._bus = bus
        self._config = config
        self._cache: dict[str, CachedMode] = {}
        return

    def warm(self) -> None:
        """
            Populate cache from the DB at startup.

            :returns: None
            :raises: DatabaseUnavailableError
        """
        ...

    def status(
        self,
        project_slug: str | None = None
    ) -> EffectiveMode:
        """
            Compute the effective mode for an optional project scope.

            :param project_slug: Optional project scope key.

            :returns: EffectiveMode with the combined mode and source
                      scopes.
            :raises: None
        """
        ...

    def require_writable(
        self,
        project_slug: str | None = None
    ) -> None:
        """
            Guard for write paths.

            :param project_slug: Optional project scope.

            :returns: None
            :raises: MaintenanceModeError when effective mode is not
                     active.
        """
        ...


class MaintenanceRepository:
    def __init__(
        self,
        pool: ConnectionPool
    ) -> None:
        self._pool = pool
        return

    def load_all(self) -> list[MaintenanceRecord]:
        """
            Read every scope currently set.

            :returns: A list of MaintenanceRecord.
            :raises: DatabaseUnavailableError
        """
        ...

    def upsert(
        self,
        record: MaintenanceRecord,
        actor: Actor
    ) -> MaintenanceRecord:
        """
            Persist a mode change and write the audit row atomically.

            :param record: The new record (scope + mode + reason +
                           ends_at).
            :param actor: The authenticated admin performing the change.

            :returns: The persisted record.
            :raises: SemanticError on invalid reason / ends_at;
                     StaleEntityError on concurrent update.
        """
        ...

    def clear(
        self,
        scope: str,
        actor: Actor
    ) -> None:
        """
            Remove a scope (equivalent to setting mode=active).

            :param scope: The scope key.
            :param actor: The authenticated admin.

            :returns: None
            :raises: StaleEntityError
        """
        ...
```

Every feature that owns a write path obtains the shared
`MaintenanceGate` via dependency injection during its startup hook and
calls `gate.require_writable(project)` at the top of its write handlers.

### Extension Surface

None. The `@read_only_safe` annotation table is a closed, in-tree list
because classifying a route as read-safe is a security-relevant
decision.

### Events Emitted

On `0-message-bus`:

- `maintenance.mode.changed` — `{scope: str, from_mode: str, to_mode:
  str, reason: str, ends_at: datetime | None, changed_by: UUID,
  changed_at: datetime}`
- `maintenance.mode.auto_expired` — `{scope: str, expired_mode: str,
  expired_at: datetime}`

### Events Consumed

- `maintenance.mode.changed` — the gate itself subscribes to its own
  topic for out-of-process sync (no-op in single-process Phase 10 but
  preserves the contract).

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/`:

- `maintenance/__init__.py`
- `maintenance/mode.py` — `MaintenanceMode` enum, `mode_precedence`.
- `maintenance/config.py` — `MaintenanceConfig` (cache_ttl_seconds,
  default_retry_after).
- `maintenance/gate.py` — `MaintenanceGate`.
- `maintenance/repository.py` — `MaintenanceRepository`,
  `MaintenanceRecord`.
- `maintenance/middleware.py` — `@read_only_safe` decorator and request
  filter that consults the gate.
- `maintenance/errors.py` — `MaintenanceModeError` with scope + mode +
  retry_after + ends_at payload.
- `maintenance/endpoints.py` — REST handlers under
  `/api/v1/admin/maintenance`.
- `maintenance/audit.py` — audit-row builder, hooks into `1-audit-log`
  subscriber.
- `maintenance/auto_expire.py` — background task that transitions
  expired scopes and emits `auto_expired`.
- `maintenance/hooks.py` — startup/shutdown hooks.

Alembic migrations under `persistence/alembic/versions/`.

## Key Flows

### Flow 1 — Admin sets project to read_only

1. Admin POST `/api/v1/admin/maintenance` with `{scope: "project:proj-a",
   mode: "read_only", reason: "backfill", ends_at: "2026-04-19T23:00Z"}`.
2. Handler checks permission `pychestrate.maintenance.manage`.
3. Handler validates `reason` length >= 10 and `ends_at` >= `now() + 60s`.
4. Handler calls `repo.upsert(...)` in a unit of work — the audit row
   and the mode row commit together.
5. Handler publishes `maintenance.mode.changed` on the bus.
6. Gate subscriber (own process) updates cache.
7. `0-object-store`, `0-persistence`, `5-job-dispatch`, etc. receive
   the event and flip their per-project gate cache.

### Flow 2 — Write request during maintenance

1. Request hits a write handler annotated `@requires_writable`.
2. Handler calls `maintenance_gate.require_writable(project_slug=...)`.
3. Gate returns cache hit in < 1 ms; if mode != `active`, raises
   `MaintenanceModeError(scope, mode, reason, ends_at)`.
4. Middleware translates to 503 with `Retry-After` header and
   structured body.
5. Metric `pychestrate_maintenance_mode_rejections_total{scope,route}`
   increments.

### Flow 3 — Auto-expiry

1. Background task wakes every 30 s.
2. Scans `core.maintenance_mode` for rows where `ends_at < now()` and
   `mode != 'active'`.
3. Upserts them to `mode='active'`, writes audit rows, publishes
   `maintenance.mode.auto_expired`, updates gate cache.

## Error Handling

- `MaintenanceModeError` is a domain error — bubbles to the write
  handler's middleware which translates to 503.
- `SemanticError` (reason too short, ends_at too soon, unknown scope
  syntax): bubbles; admin REST handler translates to 400.
- `DatabaseUnavailableError` in the gate during `require_writable`:
  fail-safe — the gate returns the last-known cached value and emits
  `pychestrate.maintenance.gate.degraded` once per minute. Writes are
  NOT silently permitted if the last-known value was non-active.
- `ConfigurationError` at startup (bad TTL, missing table): bubbles to
  host, exit 78.

Multiline error example:

```python
err_msg_lines = ["Write rejected: target scope is in maintenance mode."]
err_msg_lines.append("SCOPE: {}".format(scope))
err_msg_lines.append("MODE: {}".format(mode.value))
err_msg_lines.append("REASON: {}".format(reason))
err_msg_lines.append("ENDS AT: {}".format(ends_at))

err_msg = os.linesep.join(err_msg_lines)
raise MaintenanceModeError(err_msg) from None
```

## Security Considerations

- REST endpoints require `pychestrate.maintenance.manage` permission
  (mutation) or `pychestrate.maintenance.read` (read).
- Every mutation is audited with actor user id + IP; audit insert is
  part of the same transaction as the mode upsert.
- `reason` length enforced (10..512 chars, printable ASCII +
  whitespace) to prevent injection into log/dashboard renderers.
- `ends_at` floor (`>= now() + 60s`) avoids admins accidentally setting
  `ends_at` in the past and immediately auto-expiring.
- No explicit rate limit — admin scope is small; standard request
  rate-limit applies.
- `MaintenanceRepository.upsert` is idempotent on `(scope, to_mode)` to
  make admin tooling safe to retry.

## Observability

Metrics:

- `pychestrate_maintenance_mode_current{scope,mode}` — gauge (0|1 per
  cell, one 1-cell per scope)
- `pychestrate_maintenance_mode_changes_total{scope,to_mode}` — counter
- `pychestrate_maintenance_mode_rejections_total{scope,route}` — counter
- `pychestrate_maintenance_gate_lookup_duration_seconds{cache_hit}` —
  histogram
- `pychestrate_maintenance_auto_expirations_total{scope}` — counter

Log events:

- `pychestrate.maintenance.mode.changed`
- `pychestrate.maintenance.mode.auto_expired`
- `pychestrate.maintenance.gate.rejected`
- `pychestrate.maintenance.gate.degraded`

Trace spans:

- `pychestrate.maintenance.gate.check` — attrs `scope`, `mode`,
  `cache_hit`

Dashboards: maintenance-mode tile under `9-admin-ui` showing active
scopes + scheduled expirations; rejection-rate panel under
`7-orchestration-metrics`.

## Open Questions

- Should we model pod-scoped maintenance (`pod:<pod-id>`) in Phase 10
  or defer? Timebox: Phase 10 scoping.
- Should read-only mode also block *entity soft-deletes* (which are
  writes) or allow them because they are "cleanup"? Timebox: Phase 10
  exit — requires product call.
- Do we persist a *schedule* of future transitions (e.g., "enter
  read_only at 2026-04-20 02:00, exit at 04:00") or require an admin to
  apply and clear? Timebox: Phase 10 exit.
