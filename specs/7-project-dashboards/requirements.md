# 7-project-dashboards — Requirements

## Introduction

The `7-project-dashboards` feature stores per-project dashboard layouts
as declarative JSON documents, renders them as composable tile grids
driven by `9-wc-metric-tile` and `DashboardTileKindExtension`
contributions, and exposes a REST API for CRUD + reflow. It lands in
**Phase 9** alongside `9-wc-metric-tile` and `9-project-dashboard-ui`,
sits between the metric-producing features
(`7-metrics-ingest`/`7-*-metrics`) and the rendering UI
(`9-project-dashboard-ui`), and owns the `DashboardTileKindExtension`
resource surface. Authoritative storage for dashboard layouts is a
Postgres table owned here; the metric values rendered inside tiles
remain authoritative in `0-timeseries-backend`.

## Requirements

### Requirement 1: Dashboard CRUD Per Project

**User Story:** As a project owner, I want to save, edit, and restore
dashboards per project, so that each team sees a view tailored to its
pipelines and pods without editing a global config.

**Acceptance Criteria (EARS):**

1. WHEN an authenticated user with `dashboards.write` calls `POST /api/v1/projects/{project_id}/dashboards` with a valid `DashboardDefinition` THEN the system SHALL persist the document, assign a `dashboard_id: UUID`, emit `entity.dashboard.saved`, AND return 201 with the stored document.
2. WHEN an authenticated user with `dashboards.read` calls `GET /api/v1/projects/{project_id}/dashboards/{dashboard_id}` THEN the system SHALL return the document including `tiles: list[TileInstance]` within `dashboard_get_timeout_seconds` (default 0.6) at p99.
3. IF a `DashboardDefinition` references a `tile_kind` that is not registered THEN the system SHALL respond 400 with a `DashboardValidationError` listing the missing kind.
4. WHERE the project has `dashboards_per_project_max` (default 50) already saved THEN the system SHALL respond 409 on a further create AND NOT silently truncate.

### Requirement 2: Composable Tile Layouts

**User Story:** As a dashboard author, I want to arrange tiles in a
responsive grid with constraints, so that the same dashboard looks
sensible on a phone and on a 4K wall display.

**Acceptance Criteria (EARS):**

1. WHEN a `TileInstance` is saved THEN the system SHALL validate `x, y, w, h` are integers with `1 <= w <= grid_columns_max` (default 12) and `1 <= h <= tile_rows_max` (default 40) AND reject overlapping tiles with `DashboardValidationError` including the overlapping pair coordinates.
2. WHEN a dashboard is rendered at a reduced viewport width `V < grid_columns_max` THEN the system SHALL reflow tiles via a deterministic column-pack algorithm AND preserve tile z-order (earlier tiles in the array render earlier).
3. WHERE a tile declares `min_width_columns: int` THEN the system SHALL NOT reflow it below that width; instead it SHALL occupy a full-width row.
4. WHEN a user with `dashboards.write` POSTs `PATCH /.../dashboards/{id}/tiles` with a replacement `tiles` array THEN the system SHALL validate the full array atomically AND either apply all changes or reject all.

### Requirement 3: DashboardTileKindExtension Registry

**User Story:** As an extension author, I want to ship a new tile kind
(e.g., `pod-topology-summary`) as a resource extension, so that the
new tile appears in the dashboard palette without modifying core.

**Acceptance Criteria (EARS):**

1. WHEN the extension host scans THEN the system SHALL collect every direct subclass of `DashboardTileKindExtension` and register `(kind, webcomponent_tag, default_size, config_schema, default_config)` into the `tile_kind_registry`.
2. IF two `DashboardTileKindExtension` subclasses declare the same `kind` THEN the system SHALL raise `ConfigurationError` naming both subclasses.
3. WHEN `GET /api/v1/projects/{project_id}/dashboards/tile-kinds` is called THEN the system SHALL return every registered tile kind's metadata filtered by the caller's `dashboards.tile_kinds.read` grants.
4. WHERE a tile instance's stored `config` does not validate against the kind's `config_schema` THEN the system SHALL reject save with `DashboardValidationError` listing the failing path.

## Property-Based Test Requirements

### Property 1: Reflow Preserves Z-Order

- **Invariant:** For any dashboard `D` with `tiles = [t_0, t_1, ..., t_n]` and any viewport width `V in [1, grid_columns_max]`, the reflowed output preserves the original array order — i.e., if `t_i` renders above `t_j` in the input, `t_i` also renders above `t_j` in the output.
- **Generator:** `hypothesis.strategies.tuples(dashboards_from_grid(grid_columns_max=12), integers(min_value=1, max_value=24))`.
- **Assertion:** `all(pos_out(t_i) <= pos_out(t_j) for t_i, t_j in pairs(tiles) if i < j)`.
- **Sample size:** 1000 generated cases

### Property 2: No-Overlap After Save

- **Invariant:** For any successfully-saved dashboard, no two tiles' rectangles overlap.
- **Generator:** `hypothesis.strategies.lists(tile_instance_strategy(), min_size=0, max_size=30).filter(all_nonoverlapping)`.
- **Assertion:** `for all (t_a, t_b) in pairs(saved.tiles): not rects_overlap(t_a, t_b)`.
- **Sample size:** 1000 generated cases

### Property 3: Tile-Kind Registration Idempotent Across Rescans

- **Invariant:** For any fixed set of registered `DashboardTileKindExtension` subclasses, two consecutive `rescan` calls leave the `tile_kind_registry` bit-identical.
- **Generator:** `hypothesis.strategies.lists(tile_kind_class_strategy(), min_size=1, max_size=40, unique_by=lambda c: c.kind)`.
- **Assertion:** `serialize(registry_after_first_scan) == serialize(registry_after_second_scan)`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Dashboard read p99 < 600 ms (tiles alone, excluding metric queries which are owned by `0-timeseries-backend`). Dashboard save p99 < 800 ms. Reflow computation for a 30-tile layout p99 < 15 ms. End-to-end dashboard render (including metric tile queries) p99 < 2.5 s on a 12-tile layout.
- **NFR-2 (Security):** Read gated by `dashboards.read` + project membership; write by `dashboards.write`. Tile configs are validated against their kind's schema *before* storage to prevent stored-XSS via config blobs. All string fields HTML-escaped on render by `9-wc-metric-tile` (contract enforced here).
- **NFR-3 (Observability):** Metrics `pychestrate_dashboard_save_total{project,outcome}` (counter), `pychestrate_dashboard_get_duration_seconds{project}` (histogram), `pychestrate_dashboard_reflow_duration_seconds` (histogram), `pychestrate_dashboard_tile_kinds_registered` (gauge), `pychestrate_dashboard_validation_error_total{reason}` (counter). Log events `pychestrate.dashboard.saved`, `pychestrate.dashboard.validation_failed`, `pychestrate.dashboard.tile_kind_registered`. Trace spans `pychestrate.dashboard.save`, `pychestrate.dashboard.reflow`, `pychestrate.dashboard.validate`.
- **NFR-4 (Reliability):** Dashboard save is fully transactional — a partial tile array that fails validation leaves the prior version intact. Concurrent PATCH operations on the same dashboard SHALL use optimistic concurrency via `if_match: <etag>` and return 412 on conflict.

## Out of Scope

- Tile rendering / WebComponent internals (owned by `9-wc-metric-tile` and `DashboardTileKindExtension` implementations).
- Metric query execution (owned by `0-timeseries-backend`).
- Per-user personal dashboards (v1 is per-project only; revisit after Phase 9).
- Alerting logic (owned by `7-alerts-budgets`).

## Dependencies

- **Depends on:** `7-metrics-ingest`, `0-timeseries-backend`, `0-persistence`, `0-message-bus`, `1-rbac`, `2-projects`, `E-extension-host`, `E-resource-extensions`, `9-wc-metric-tile`.
- **Depended on by:** `9-project-dashboard-ui`, `7-alerts-budgets` (reads tile kinds to offer alert-attachment UX), `7-slo-views` (embeds tiles).
- **Extension points exposed:** `resource: DashboardTileKindExtension` · `event: entity.dashboard.saved` · `event: entity.dashboard.deleted`.
