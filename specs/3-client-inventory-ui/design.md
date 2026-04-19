# 3-client-inventory-ui — Design

## Architecture

The Client Inventory UI backing service lives at
`source/site/automojo/pychestrate/webservice/clients/inventory/`. It is
composed of:

- A REST aggregator that joins `client`, `pod_runtime_state`, and
  `client_capability` tables plus capability kind metadata into the
  `ClientInventoryRow` DTO.
- A changes feed that consumes `entity.client.*` and
  `entity.pod.state_changed` events from `0-message-bus`, buffers them
  in a short-retention ring (implemented over
  `client_inventory_change_log` table + in-memory index), and serves
  `since`-parameterized reads.
- A WebComponent bundle under
  `source/site/automojo/pychestrate/webui/components/pcx-client-inventory/`
  — a framework-agnostic custom element that calls these two endpoints
  and renders the table, themed via `9-ui-design-tokens` CSS custom
  properties.

Authoritative data still lives in sibling features; this feature owns
only the composed DTOs and the change-log table.

## Data Model

One new table for the changes feed:

```
client_inventory_change_log
    change_id:       bigserial  primary key
    client_id:       UUID
    project_id:      UUID
    change_kind:     str        -- heartbeat | liveness | capabilities | pod_state | enroll | revoke
    payload_summary: jsonb
    logged_at:       datetime   not null
    (logged_at) index
    (client_id, logged_at) index
```

Retention enforced by a sweep every minute that deletes rows older than
`changes_retention_seconds` (default 600).

DTOs (`clients/inventory/dtos.py`):

```
@dataclass(frozen=True)
class CapabilitySummary:
    kind: str
    count: int


@dataclass(frozen=True)
class ClientInventoryRow:
    client_id: UUID
    project_id: UUID
    pod_name: str
    liveness_state: LivenessState
    last_seen: Optional[datetime]
    last_agent_version: Optional[str]
    transport_name: Optional[str]
    current_pod_state: Optional[PodState]
    capability_summary: Sequence[CapabilitySummary]
    updated_at: datetime


@dataclass(frozen=True)
class InventoryPage:
    rows: Sequence[ClientInventoryRow]
    next_cursor: Optional[str]
    as_of: datetime


@dataclass(frozen=True)
class InventoryChange:
    client_id: UUID
    change_kind: str
    payload_summary: Mapping[str, Any]
    logged_at: datetime
```

## Interfaces

### Public API

REST (RBAC `client.inventory.read`):

- `GET /api/v1/clients:inventory?project_id=&liveness=&agent_version_lt=&
  lost_since=&capability_has=&sort=&cursor=&page_size=` — returns
  `InventoryPage`.
- `GET /api/v1/clients:inventory/changes?since=<iso8601>&project_id=` —
  returns `{changes: [InventoryChange], as_of}`.

WebComponent:

- `<pcx-client-inventory project-id="" auto-refresh="15"></pcx-client-inventory>`
  - attributes: `project-id`, `filter`, `auto-refresh` (seconds),
    `theme-variant`.
  - events: `pcx-client-selected` (detail: `client_id`),
    `pcx-inventory-error`.
  - served from `source/site/automojo/pychestrate/webui/components/
    pcx-client-inventory/`.

### Internal API

```python
def read_inventory(
    *,
    filters: InventoryFilter,
    cursor: Optional[str],
    page_size: int,
    caller_permissions: AbstractSet[str],
    caller_project_scope: AbstractSet[UUID],
) -> InventoryPage:
    ...


def read_changes(
    *,
    since: datetime,
    project_scope: AbstractSet[UUID],
) -> Sequence[InventoryChange]:
    ...


def log_inventory_change(
    *,
    client_id: UUID,
    project_id: UUID,
    change_kind: str,
    payload_summary: Mapping[str, Any],
) -> None:
    ...
```

### Extension Surface

Phase 2: none. Phase 10 adds:

```python
class FleetListSubcommand(CLISubcommandExtension):
    subcommand_name: ClassVar[str] = "fleet"
    ...
```

### Events Emitted

None directly. The feature writes `client_inventory_change_log` rows.

### Events Consumed

All of the following, translated to change-log rows:

- `entity.client.enrolled` (kind: `enroll`).
- `entity.client.heartbeat` (kind: `heartbeat`).
- `entity.client.liveness_changed` (kind: `liveness`).
- `entity.client.capabilities_applied` (kind: `capabilities`).
- `entity.client.revoked` (kind: `revoke`).
- `entity.pod.state_changed` (kind: `pod_state`) — mapped through the
  owning client.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/clients/inventory/
    __init__.py
    dtos.py
    service.py                 -- read_inventory, read_changes, log_inventory_change
    repository.py              -- InventoryRepository, ChangeLogRepository
    filters.py                 -- InventoryFilter parsing + validation
    cursor.py                  -- opaque cursor encode/decode (signed tuple)
    subscribers.py             -- change-log bus subscribers
    sweeper.py                 -- retention sweep task
    rest.py
    metrics.py

source/site/automojo/pychestrate/webui/components/pcx-client-inventory/
    index.js                   -- custom element registration
    pcx-client-inventory.js
    pcx-client-inventory.css
    tests/                     -- component unit tests (web-test-runner)
```

## Key Flows

**Paged read.** UI calls `:inventory` with filters. Service parses
filters, applies caller permission scope, queries the three-way join
with SQL, encodes a cursor for the last row (stable sort by
`(updated_at desc, client_id desc)`), returns `InventoryPage`.

**Incremental refresh.** UI holds the `as_of` from the last page and
polls `:inventory/changes?since=<as_of>` every `auto-refresh` seconds.
Service queries `client_inventory_change_log WHERE logged_at > since`,
filters by permission scope, returns the list + new `as_of`.

**Bus subscription.** On every
`entity.client.heartbeat|liveness_changed|capabilities_applied|
revoked|enrolled` and `entity.pod.state_changed`, subscribers call
`log_inventory_change` with a compact summary. The summary does not
include capability values — only counts and kinds.

**Cursor staleness.** If a cursor is decoded with a timestamp older
than retention, the service returns 410 Gone instructing the UI to
restart pagination.

## Error Handling

- `InvalidFilterCombination` — mutually-exclusive filters (e.g.,
  `liveness=lost` + `agent_version_lt` without `include_lost=true`)
  rejected at REST boundary with HTTP 400.
- `StaleCursor` — cursor's timestamp older than retention or
  signature mismatch; HTTP 410.
- `ChangesWindowTooOld` — `since` older than retention; HTTP 410.
- `PermissionNarrowed` — caller holds `client.inventory.read` but the
  requested `project_id` is not in their scope; HTTP 403.
- `SemanticError` — never caught.
- Multiline error messages per AGENTS.md.

## Security Considerations

- RBAC: `client.inventory.read` (per-project scopes honored),
  `client.inventory.admin` (unlocks the sensitive-capability drill
  in future phases).
- Cursor tokens carry a SHA-HMAC signature to prevent forged cursors
  from bypassing permission scope.
- Changes feed does not leak capability values — only kinds and
  counts.
- All REST responses set `Cache-Control: no-store` (UI owns caching
  via the changes feed).
- Rate limit 60 requests/minute per caller on `:inventory`; 600/minute
  on `:inventory/changes`.

## Observability

Metrics:

- `pychestrate_client_inventory_reads_total{outcome}` — counter.
- `pychestrate_client_inventory_rows_returned` — histogram.
- `pychestrate_client_inventory_changes_reads_total{outcome}` —
  counter.
- `pychestrate_client_inventory_stale_cursors_total` — counter.
- `pychestrate_client_inventory_changelog_rows` — gauge.

Log events: `pychestrate_client_inventory_read`,
`pychestrate_client_inventory_changes_stale_cursor`,
`pychestrate_client_inventory_changelog_sweep`.

Trace spans: `client_inventory.read`,
`client_inventory.changes`, `client_inventory.sweep`.

## Open Questions

- Should the changes feed be backed by Postgres LISTEN/NOTIFY in
  addition to the log table to reduce UI poll pressure? Defer to
  Phase 9 (dashboards introduce more streaming patterns).
- Do we expose a saved-query concept (named filter bookmarks) at this
  phase? Lean no; revisit with `9-admin-ui`.
