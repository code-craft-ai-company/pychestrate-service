# 7-project-dashboards — Design

## Architecture

`7-project-dashboards` is the authoritative store for per-project
dashboard layouts: JSON `DashboardDefinition` documents persisted in
`0-persistence`, validated against the `tile_kind_registry` built from
`DashboardTileKindExtension` subclasses, and exposed via REST under
`8-rest-api-v1`. The feature owns the reflow algorithm (pure function)
and publishes `entity.dashboard.saved` / `entity.dashboard.deleted`
events on `0-message-bus`. It lives in **Phase 9** and sits adjacent to
`9-project-dashboard-ui` (consumer) and `9-wc-metric-tile` (render
contract). This feature does not execute metric queries — tiles defer
query execution to `0-timeseries-backend` at render time.

## Data Model

Tables in `0-persistence`:

- `dashboard`:
  - `dashboard_id: UUID` PK
  - `project_id: UUID`
  - `name: str`
  - `description: str`
  - `owner_principal_id: UUID`
  - `grid_columns_max: int` (default 12)
  - `tiles: list[TileInstance]` (JSONB)
  - `created_at: datetime`
  - `updated_at: datetime`
  - `version: int` — optimistic concurrency counter; ETag = `sha256(dashboard_id || version)`.
- `dashboard_audit`:
  - `audit_id: BIGSERIAL`
  - `dashboard_id: UUID`
  - `actor_id: UUID`
  - `action: Literal["created","updated","deleted"]`
  - `diff: bytes` (JSONB diff)
  - `at: datetime`

Value types:

- `DashboardDefinition`:
  - `dashboard_id: UUID | None`
  - `project_id: UUID`
  - `name: str`
  - `description: str`
  - `grid_columns_max: int`
  - `tiles: list[TileInstance]`
- `TileInstance`:
  - `tile_id: UUID`
  - `kind: str`
  - `x: int`, `y: int`, `w: int`, `h: int`
  - `config: dict[str, Any]`
  - `min_width_columns: int | None`
- `TileKindRegistryEntry`:
  - `kind: str`
  - `webcomponent_tag: str`
  - `default_size: tuple[int, int]`
  - `config_schema: dict[str, Any]`  (JSON Schema)
  - `default_config: dict[str, Any]`
  - `source_extension: str`

## Interfaces

### Public API

REST under `8-rest-api-v1` (prefix `/api/v1/projects/{project_id}/dashboards`):

- `GET /` → list dashboards for project.
- `POST /` → create dashboard (`dashboards.write`).
- `GET /{dashboard_id}` → fetch one dashboard.
- `PUT /{dashboard_id}` → replace (optimistic concurrency via `If-Match`).
- `PATCH /{dashboard_id}/tiles` → replace tile array only.
- `DELETE /{dashboard_id}` → delete.
- `GET /tile-kinds` → list registered tile kinds (`dashboards.tile_kinds.read`).
- `POST /{dashboard_id}/reflow` → compute reflowed layout for a given viewport width (server-side helper; returns JSON positions).

### Internal API

```python
class DashboardService:
    def __init__(
        self,
        repo: DashboardRepository,
        tile_kind_registry: TileKindRegistry,
        rbac: RbacService,
        audit: AuditLog,
        bus: MessageBus,
        clock: Clock,
        config: DashboardConfig
    ) -> None:
        self._repo = repo
        self._tile_kind_registry = tile_kind_registry
        self._rbac = rbac
        self._audit = audit
        self._bus = bus
        self._clock = clock
        self._config = config
        return

    def create_dashboard(
        self,
        actor_id: UUID,
        project_id: UUID,
        definition: DashboardDefinition
    ) -> StoredDashboard:
        """
            :raises: AuthorizationError, DashboardValidationError,
                     DashboardQuotaExceededError
        """
        ...

    def update_dashboard(
        self,
        actor_id: UUID,
        dashboard_id: UUID,
        definition: DashboardDefinition,
        if_match_etag: str
    ) -> StoredDashboard:
        """
            :raises: ConcurrencyConflictError, DashboardValidationError,
                     AuthorizationError
        """
        ...

    def replace_tiles(
        self,
        actor_id: UUID,
        dashboard_id: UUID,
        tiles: list[TileInstance],
        if_match_etag: str
    ) -> StoredDashboard:
        ...

    def delete_dashboard(
        self,
        actor_id: UUID,
        dashboard_id: UUID,
        if_match_etag: str
    ) -> None:
        ...

    def validate_definition(
        self,
        definition: DashboardDefinition
    ) -> None:
        """
            Raise DashboardValidationError on any invariant failure
            (unknown kind, overlap, config schema mismatch, bounds).

            :returns: None.
            :raises: DashboardValidationError
        """
        ...


class TileKindRegistry:
    def __init__(
        self,
        extension_host: ExtensionHost
    ) -> None:
        self._extension_host = extension_host
        self._entries: dict[str, TileKindRegistryEntry] = {}
        return

    def build(
        self
    ) -> None:
        ...

    def get(
        self,
        kind: str
    ) -> TileKindRegistryEntry | None:
        ...

    def list_kinds(
        self
    ) -> list[TileKindRegistryEntry]:
        ...


def reflow_tiles(
    tiles: list[TileInstance],
    viewport_columns: int,
    grid_columns_max: int
) -> list[ReflowedTile]:
    """
        Column-pack reflow preserving array z-order.

        :param tiles: Tile array in z-order (earliest first).
        :param viewport_columns: Available columns in the target viewport.
        :param grid_columns_max: Authoring grid width.

        :returns: Reflowed positions; each tile's w is min(tile.w, viewport_columns).
    """
    ...


def rects_overlap(
    a: TileInstance,
    b: TileInstance
) -> bool:
    """
        :returns: True when tile rectangles overlap in the authoring grid.
    """
    ...
```

### Extension Surface

```python
class DashboardTileKindExtension(ResourceExtension):
    """
        Base for registering a new dashboard tile kind.
    """
    kind: str
    webcomponent_tag: str
    default_size: tuple[int, int]
    config_schema: dict[str, Any]
    default_config: dict[str, Any]
    min_width_columns: int | None = None

    @classmethod
    def describe(
        cls
    ) -> TileKindRegistryEntry:
        """
            :returns: Entry for registry insertion.
        """
        ...
```

Reference implementations shipped in-tree:

- `source/site/ccai/extensions/pychestrate/dashboard_tile_kind/metric_line.py` — `kind="metric_line"`, `webcomponent_tag="pychestrate-metric-line-tile"`.
- `source/site/ccai/extensions/pychestrate/dashboard_tile_kind/metric_stat.py` — `kind="metric_stat"`.
- `source/site/ccai/extensions/pychestrate/dashboard_tile_kind/slo_burn.py` — `kind="slo_burn"` (consumed by `7-slo-views`).
- `source/site/ccai/extensions/pychestrate/dashboard_tile_kind/pipeline_health.py` — `kind="pipeline_health"`.

### Events Emitted

- `entity.dashboard.saved` — `{project_id, dashboard_id, actor_id, action, version}`.
- `entity.dashboard.deleted` — `{project_id, dashboard_id, actor_id}`.

### Events Consumed

- `extension.reloaded` — rebuild `tile_kind_registry`.
- `entity.project.deleted` — cascade dashboard deletion.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/dashboards/`:

- `__init__.py`
- `service.py` — `DashboardService`.
- `repository.py` — `DashboardRepository`.
- `registry.py` — `TileKindRegistry`.
- `extension_base.py` — `DashboardTileKindExtension`.
- `validation.py` — `validate_definition`, `rects_overlap`, `validate_tile_config`.
- `reflow.py` — `reflow_tiles`, `ReflowedTile` value type.
- `config.py` — `DashboardConfig`.
- `errors.py` — `DashboardValidationError`, `DashboardQuotaExceededError`, `ConcurrencyConflictError`.
- `rest/v1_routes.py` — REST endpoints.
- `rest/schemas.py` — pydantic-style schemas for request/response.

Tile kind extensions under
`source/site/ccai/extensions/pychestrate/dashboard_tile_kind/`.

## Key Flows

### Flow 1 — Create Dashboard

1. `POST /api/v1/projects/{id}/dashboards` arrives.
2. RBAC `dashboards.write` check.
3. Quota check against `dashboards_per_project_max`.
4. `validate_definition` — each tile's `kind` resolved against registry, `config` validated against kind's JSON Schema, rects checked non-overlapping, bounds checked.
5. `repo.insert(...)` with initial `version=1`.
6. Audit row appended; `entity.dashboard.saved` emitted.
7. 201 returned with stored document + `ETag` header.

### Flow 2 — PATCH Tiles with Concurrency

1. `PATCH /.../tiles` arrives with `If-Match: <etag>` + `tiles`.
2. RBAC + quota checks.
3. Load current dashboard; compare ETag — mismatch → 412.
4. Validate replacement tile array atomically.
5. Persist with `version = version + 1`; emit `entity.dashboard.saved`.

### Flow 3 — Reflow Computation

1. `POST /.../reflow` body `{viewport_columns: int}`.
2. Load dashboard; call `reflow_tiles(tiles, viewport_columns, grid_columns_max)`.
3. Return JSON positions; no persistence side effects.

### Flow 4 — Tile Kind Registry Build

1. At startup, `TileKindRegistry.build()` calls the extension host.
2. Collects every direct subclass of `DashboardTileKindExtension`.
3. Uniqueness check on `kind`; conflict → `ConfigurationError`.
4. Emits `entity.dashboard.tile_kind_registered` (via log — not a bus event) per registered kind.

## Error Handling

- `SemanticError` for schema violations that indicate upstream bugs (non-UUID ids, etc.): bubble.
- `DashboardValidationError`: caught at REST layer → 400 with multiline message built via `os.linesep.join([...])`.
- `ConcurrencyConflictError`: → 412.
- `DashboardQuotaExceededError`: → 409.
- `AuthorizationError`: → 403.
- `ConfigurationError` for duplicate `kind`: fatal at service start.

## Security Considerations

- `dashboards.read` / `dashboards.write` permissions gate endpoints; project membership enforced.
- Tile `config` validated against declared JSON Schema before persistence; free-form strings escaped at tile-render time by `9-wc-metric-tile`.
- Admin override `dashboards.admin` allows cross-project listing but not editing.
- Rate limit `max_dashboard_writes_per_hour_per_actor` (default 300).
- `description` field length capped at 4 KiB; rejected with `DashboardValidationError` otherwise.

## Observability

Metrics:

- `pychestrate_dashboard_save_total{project,outcome}` — counter
- `pychestrate_dashboard_get_duration_seconds{project}` — histogram
- `pychestrate_dashboard_reflow_duration_seconds` — histogram
- `pychestrate_dashboard_tile_kinds_registered` — gauge
- `pychestrate_dashboard_validation_error_total{reason}` — counter
- `pychestrate_dashboard_concurrency_conflict_total{project}` — counter

Log events: `pychestrate.dashboard.saved`, `pychestrate.dashboard.validation_failed`, `pychestrate.dashboard.tile_kind_registered`, `pychestrate.dashboard.concurrency_conflict`.

Trace spans: `pychestrate.dashboard.save`, `pychestrate.dashboard.reflow`, `pychestrate.dashboard.validate`, `pychestrate.dashboard.registry_build`.

## Open Questions

- Should dashboards support templating variables (e.g., `$branch`) server-side or is that a `9-wc-metric-tile` concern? Current design: client-side. Timebox: Phase 9 midpoint.
- Do we offer versioned rollbacks (view history) in v1? Current design: no, audit diff exists but no restore endpoint. Timebox: after Phase 9 exit.
- Does reflow need to be responsive to tile `importance` ranks, or strict z-order only? Current design: strict z-order. Timebox: Phase 9 midpoint.
