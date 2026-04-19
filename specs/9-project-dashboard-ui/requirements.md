# 9-project-dashboard-ui — Requirements

## Introduction

`9-project-dashboard-ui` is the per-project composed dashboard. It fetches a
project's dashboard layout from `7-project-dashboards`, renders a grid of
`9-wc-metric-tile` instances (including extension-contributed
`DashboardTileKindExtension` tiles), and provides layout editing (add tile,
remove, resize, reorder, pin). Ships in **Phase 9**. Sits between
`7-project-dashboards` (layout + data contract) and `9-wc-metric-tile`
(rendering unit). Hosted at `GET /projects/<project-id>/dashboard`. The
authoritative dashboard layout lives in `7-project-dashboards`; this UI is
the editor and renderer. Consumes `DashboardTileKindExtension` through the
tile registry already surfaced by `9-wc-metric-tile`.

## Requirements

### Requirement 1: Load, Render, and Refresh a Project Dashboard

**User Story:** As a project member, I want the project dashboard to load
fast and keep its tiles fresh, so that I can see project health at a glance.

**Acceptance Criteria (EARS):**

1. WHEN a user opens `/projects/<project-id>/dashboard` THEN the UI SHALL call `GET /api/v1/projects/{project_id}/dashboard` AND render the layout within 500 ms on a warm cache.
2. IF the project has no dashboard configured THEN the UI SHALL render a starter template seeded from `ProjectTemplateExtension` (falling back to a built-in default) AND SHALL mark the layout as unsaved.
3. WHEN each tile mounts THEN the UI SHALL forward `query`, `range`, `unit`, `title`, `subtitle`, `refresh-seconds`, `thresholds`, and `kind` to its `<pyc-metric-tile>` child.
4. WHILE the tab is backgrounded THEN the UI SHALL reduce global refresh cadence by 2x AND resume at focus.

### Requirement 2: Edit-Mode Grid (Add/Remove/Resize/Reorder/Pin)

**User Story:** As a project admin, I want to rearrange tiles and save the
layout, so that each project displays what its team cares about.

**Acceptance Criteria (EARS):**

1. WHEN the user enables edit mode AND has `project.dashboard.edit` THEN the UI SHALL expose drag handles on each tile AND the tile grid SHALL honor pointer + keyboard drag.
2. WHEN the user drops or key-moves a tile THEN the UI SHALL snap to a 12-column grid AND the layout SHALL remain valid (non-overlapping, within viewport columns).
3. WHEN the user clicks save THEN the UI SHALL call `PUT /api/v1/projects/{project_id}/dashboard` with the layout delta AND emit `pyc-project-dashboard-saved` with `{projectId, revision}`.
4. IF the user has `project.dashboard.pin_global` THEN a tile may be marked `pinnedGlobal: true` so other projects using the shared template receive the tile by default.
5. WHERE a tile references a missing metric definition (after a `MetricDefinitionExtension` was removed) THEN the UI SHALL render a broken-tile state with a slot-able fix affordance.

### Requirement 3: Extension-Contributed Tile Kinds

**User Story:** As an extension author, I want to register a new tile kind
and have it show up in the "add tile" picker, so that operators can place my
tile into their dashboards.

**Acceptance Criteria (EARS):**

1. WHEN the user opens the add-tile picker THEN the UI SHALL query `GET /api/v1/extensions/dashboard_tile_kinds.json` AND list built-in + extension kinds with icons and labels.
2. IF an extension kind declares required attributes beyond the tile defaults THEN the picker SHALL expose those attributes as a form AND validate before insert.
3. WHEN an extension tile fails to load THEN the broken-tile state SHALL display the extension's name AND a retry affordance.
4. WHERE the caller lacks `project.dashboard.use_extension_kinds` THEN the add-tile picker SHALL list only built-in kinds.

### Requirement 4: Accessibility and Keyboard Editing

**User Story:** As a keyboard user, I want to navigate and edit the
dashboard grid without a mouse, so that I can compose dashboards
accessibly.

**Acceptance Criteria (EARS):**

1. WHEN the UI mounts THEN the grid SHALL expose `role="grid"` AND each tile SHALL expose `role="gridcell"` with `aria-rowindex` and `aria-colindex`.
2. WHEN the user presses `Tab` into a tile and activates drag mode with `Space` THEN arrow keys SHALL move the tile in grid cells AND `Space` again SHALL drop it.
3. WHEN the user presses `?` THEN a help dialog SHALL list keybindings.
4. IF a save fails THEN the announcement SHALL land in a visually-hidden live region with the server's safe message.

## Property-Based Test Requirements

### Property 1: Layout Serialization Round-Trips

- **Invariant:** For any valid 12-column grid layout, `deserialize(serialize(L)) == L`.
- **Generator:** Random grid layouts with 1..40 non-overlapping tiles.
- **Assertion:** Equality after round-trip.
- **Sample size:** 1000 generated cases

### Property 2: Drag/Drop Preserves Grid Validity

- **Invariant:** For any sequence of drag operations applied to a valid layout with legal moves, the resulting layout remains non-overlapping and within column bounds.
- **Generator:** Random sequences of drag moves (possibly including rejected moves).
- **Assertion:** After each accepted move, the layout is valid.
- **Sample size:** 1000 generated cases

### Property 3: Tile-Kind Registry Dispatch Is Stable

- **Invariant:** For any registry state, resolving a tile `kind` yields a deterministic `{componentTag, bundleUrl}` regardless of tile render order.
- **Generator:** Random registry states with extension kinds added / removed.
- **Assertion:** Resolution equals the reference resolution for every tile.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Dashboard TTI with warm cache p95 < 500 ms. 20-tile dashboard sustains 60 fps during refresh ticks. Add-tile flow insert-to-visible p95 < 120 ms. Save p95 < 600 ms.
- **NFR-2 (Security):** Same-origin REST, CSRF. RBAC gates edit and pin-global actions. Tile queries pass through `7-metrics-ingest` which enforces project scoping server-side. No tile content renders HTML from metric payloads.
- **NFR-3 (Observability):** Client metrics beaconed: `pychestrate_ui_project_dashboard_tti_seconds` (histogram), `pychestrate_ui_project_dashboard_save_duration_seconds` (histogram), `pychestrate_ui_project_dashboard_tile_insert_total{kind}` (counter), `pychestrate_ui_project_dashboard_broken_tile_total{kind}` (counter), `pychestrate_ui_project_dashboard_edit_mode_total{outcome}` (counter). Log events `pychestrate.ui.project_dashboard.opened`, `pychestrate.ui.project_dashboard.saved`, `pychestrate.ui.project_dashboard.broken_tile`.
- **NFR-4 (Reliability):** Concurrent save conflicts (409) SHALL surface a merge banner and preserve the user's in-progress edits; no silent overwrite. Broken tiles SHALL NOT break neighboring tiles.

## Out of Scope

- Authoring metrics (see `7-metrics-ingest`).
- Tile rendering internals (see `9-wc-metric-tile`).
- Cross-project dashboards (future).

## Dependencies

- **Depends on:** `9-ui-design-tokens`, `9-wc-metric-tile`, `7-project-dashboards`, `7-metrics-ingest`, `2-project-templates`, `2-projects`, `1-rbac`, `8-rest-api-v1`, `E-extension-host`.
- **Depended on by:** project members, operators.
- **Extension points exposed:** Consumes `resource: DashboardTileKindExtension` (via `9-wc-metric-tile`).
