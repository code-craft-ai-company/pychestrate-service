# 9-project-dashboard-ui — Design

## Architecture

`9-project-dashboard-ui` is a composition Custom Element (`<pyc-project-dashboard>`)
that owns the 12-column responsive grid, the edit-mode UX, and the
add-tile / save flows. Each tile cell hosts a `<pyc-metric-tile>`; extension
tiles are rendered by `<pyc-metric-tile>` via its kind dispatch. The UI
fetches layout from `7-project-dashboards`, applies it to the grid, and
serializes the grid back on save. An optional starter template comes from
`ProjectTemplateExtension` for empty projects. Ships in **Phase 9** when the
metric tile and timeseries backend stand up.

## Data Model

No persistent entities. Runtime state:

- `DashboardLayout` — `{projectId: string, revision: number, tiles: TilePlacement[], updatedAt: string}`.
- `TilePlacement` — `{tileId: string, kind: string, col: number, row: number, width: number, height: number, attrs: Record<string, string>, pinnedGlobal: boolean}`.
- `EditState` — `{enabled: boolean, dragging: string | null, cursor: {col, row} | null, dirty: boolean}`.
- `TileKindCatalog` — `{builtins: TileKindRecord[], extensions: TileKindRecord[], fetchedAt: string}`.

## Interfaces

### Public API

**Tag name:** `<pyc-project-dashboard>`

**Observed attributes:**

- `project-id` (string; UUID).
- `edit-mode` (boolean attribute).
- `refresh-multiplier` (string; float; default `1`).
- `aria-label` (string).

**Properties (JS):**

- `projectId: string`
- `layout: DashboardLayout | null`
- `editing: boolean`
- `dirty: boolean`
- `save(): Promise<SaveResult>`
- `addTile(kind: string, attrs: Record<string, string>): TilePlacement`
- `removeTile(tileId: string): void`
- `movePlacement(tileId: string, col: number, row: number): boolean`
- `resizePlacement(tileId: string, width: number, height: number): boolean`

**Events (bubbling, composed):**

- `pyc-project-dashboard-loaded` — `{projectId, tileCount, revision}`.
- `pyc-project-dashboard-edit-mode-changed` — `{enabled}`.
- `pyc-project-dashboard-tile-inserted` — `{tileId, kind}`.
- `pyc-project-dashboard-tile-removed` — `{tileId}`.
- `pyc-project-dashboard-saved` — `{projectId, revision}`.
- `pyc-project-dashboard-broken-tile` — `{tileId, reason}`.
- `pyc-project-dashboard-conflict` — `{localRevision, serverRevision}`.

**Slots:**

- `slot="header"` — consumer-supplied header controls.
- `slot="empty"` — rendered when no tiles exist (before template seeds it).
- `slot="save-error"` — error state on save.
- `slot="broken-tile-fix"` — per-broken-tile fix affordance.

**CSS custom properties respected:**

- `--pyc-project-dashboard-bg` → `var(--pyc-color-app-bg)`
- `--pyc-project-dashboard-grid-gap` → `var(--pyc-space-4)`
- `--pyc-project-dashboard-drag-bg` → `var(--pyc-color-accent-subtle)`
- `--pyc-project-dashboard-placeholder-bg` → `var(--pyc-color-neutral-subtle)`
- `--pyc-project-dashboard-focus-ring` → `var(--pyc-focus-ring)`
- `--pyc-project-dashboard-font-family` → `var(--pyc-font-family-ui)`

**A11y requirements:**

- Grid: `role="grid"`, `aria-colcount=12`, `aria-rowcount` dynamic.
- Each cell: `role="gridcell"`, `aria-rowindex`, `aria-colindex`.
- Tile activation with `Enter` opens edit / drilldown; `Space` toggles drag mode; arrows move while dragging; `Esc` cancels drag.
- Help dialog on `?`, focus-trapped, lists keybindings.
- Live region announces save failures and conflict states.

Server REST surfaces consumed:

- `GET /api/v1/projects/{project_id}/dashboard`.
- `PUT /api/v1/projects/{project_id}/dashboard`.
- `GET /api/v1/extensions/dashboard_tile_kinds.json` (for the add-tile picker).
- `GET /api/v1/project_templates` (for starter-template hints when layout is empty).

### Internal API

```typescript
class GridModel {
    canPlace(tileId: string, col: number, row: number, width: number, height: number): boolean
    move(tileId: string, col: number, row: number): boolean
    resize(tileId: string, width: number, height: number): boolean
    serialize(): TilePlacement[]
    deserialize(placements: TilePlacement[]): void
}

class DashboardTransport {
    fetch(projectId: string): Promise<DashboardLayout>
    save(projectId: string, layout: DashboardLayout): Promise<DashboardLayout>
}

class TileKindCatalogLoader {
    load(): Promise<TileKindCatalog>
}

class AddTileDialog {
    open(catalog: TileKindCatalog, onInsert: (placement: TilePlacement) => void): void
}
```

### Extension Surface

Consumes `DashboardTileKindExtension` indirectly through `<pyc-metric-tile>`.
No additional extension surface declared here.

### Events Emitted

DOM CustomEvents.

### Events Consumed

Events from child `<pyc-metric-tile>` elements (`pyc-metric-tile-error`,
`pyc-metric-tile-extension-error`) are aggregated into `broken-tile`
notifications.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/webinterface/components/pyc-project-dashboard/`:

- `pyc-project-dashboard.ts` — Custom Element.
- `grid-model.ts` — 12-column validity + layout algebra.
- `transport/dashboard-transport.ts` — REST client.
- `tile-kind-catalog.ts` — built-in + extension catalog.
- `add-tile-dialog.ts` — picker dialog.
- `dnd.ts` — pointer + keyboard drag machinery.
- `keybindings.ts`.
- `styles.css` — multi-line CSS referencing `--pyc-project-dashboard-*` tokens.
- `tests/`.

Bundle emitted at `/ui/components/pyc-project-dashboard/pyc-project-dashboard.js`. Server-side route `GET /projects/<id>/dashboard` serves the document shell.

## Key Flows

### Flow 1 — Open a dashboard

1. Element reads `project-id`.
2. Transport fetches layout JSON.
3. `GridModel.deserialize` populates the grid; `<pyc-metric-tile>` elements instantiate in each cell.
4. Element emits `pyc-project-dashboard-loaded`.

### Flow 2 — Edit mode: add, move, save

1. User enables edit mode (requires `project.dashboard.edit`).
2. User opens add-tile dialog; catalog loads; user picks a kind; attrs form validates.
3. New `TilePlacement` inserted into grid; element emits `tile-inserted`.
4. User drags to reorder; `GridModel.move` returns validity per move.
5. User saves; transport PUTs layout; on success, revision updates, `saved` event fires.

### Flow 3 — Conflict on save

1. User saves; server returns 409 with `serverRevision`.
2. Element emits `pyc-project-dashboard-conflict`; renders a merge banner with choices "Keep mine / Load server".
3. User chooses; grid refreshes accordingly.

## Error Handling

- Layout 404 on empty project: seed from template; mark `dirty=true`; no error shown.
- 403: render forbidden state.
- 409 on save: conflict flow above; never silently overwrite.
- Broken tile (metric kind missing, metric definition removed, extension failed): render broken state with fix affordance; do not break neighbors.
- Save 5xx: surface `slot="save-error"`; retain in-memory layout; retry affordance.

## Security Considerations

- Same-origin REST; CSRF.
- Edit + pin-global actions gated by server + client RBAC.
- Layout JSON passes through a schema validator before render; unknown fields are ignored (forward-compat).
- Tile attrs stored as strings; rendering delegated to `<pyc-metric-tile>` which enforces its own rules.
- No `localStorage` usage; dirty state dies with the element unless saved.

## Observability

Client metrics beaconed:

- `pychestrate_ui_project_dashboard_tti_seconds` — histogram.
- `pychestrate_ui_project_dashboard_save_duration_seconds{outcome}` — histogram.
- `pychestrate_ui_project_dashboard_tile_insert_total{kind}` — counter.
- `pychestrate_ui_project_dashboard_broken_tile_total{kind}` — counter.
- `pychestrate_ui_project_dashboard_edit_mode_total{outcome}` — counter.
- `pychestrate_ui_project_dashboard_conflict_total` — counter.

Log events: `pychestrate.ui.project_dashboard.opened`, `pychestrate.ui.project_dashboard.saved`, `pychestrate.ui.project_dashboard.broken_tile`, `pychestrate.ui.project_dashboard.conflict`.

Trace spans (server-side at ingestion): `pychestrate.ui.project_dashboard.metric_ingest`.

## Open Questions

- Should the dashboard support per-user overrides layered on top of the project default? Timebox: Phase 9 exit.
- Row-based auto-flow on viewport resize — keep explicit grid or reflow? Timebox: Phase 9 midpoint.
- Live-pushed layout updates (someone else edits): merge vs prompt? Timebox: Phase 10.
