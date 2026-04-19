# 9-wc-metric-tile — Requirements

## Introduction

`9-wc-metric-tile` is the dashboard tile primitive — a framework-agnostic
Custom Element that renders a single metric (counter, gauge, histogram
summary, sparkline, heatmap, or custom) queried from `0-timeseries-backend`
via `7-metrics-ingest` REST endpoints. It is the composition unit for
`9-project-dashboard-ui` and is the canonical consumer of
`DashboardTileKindExtension` — extensions ship new tile kinds (e.g.,
SLO-burn-rate tile, matrix heatmap) as custom elements that register with a
tile-kind registry served through the same mechanism used by
`9-wc-pod-topology`'s renderer registry. Ships in **Phase 9** when the
timeseries backend stands up. Sits between Layer 7 ingest and the project
dashboard.

## Requirements

### Requirement 1: Query, Render, and Refresh a Metric

**User Story:** As a user looking at a dashboard, I want each tile to show
the current value of a metric, refreshing without me pressing anything, so
that I can spot changes.

**Acceptance Criteria (EARS):**

1. WHEN the element receives `query` AND `range` THEN the system SHALL call `GET /api/v1/metrics/query?q=<query>&range=<range>` AND render the result within 400 ms.
2. IF `refresh-seconds` is set THEN the element SHALL re-issue the query every N seconds AND emit `pyc-metric-tile-refreshed` with `{at, durationMs}`.
3. WHEN a query errors (4xx/5xx) THEN the element SHALL render an error state via `slot="error"` AND SHALL emit `pyc-metric-tile-error` with `{status, error_code}`.
4. WHILE the tab is backgrounded THEN the element SHALL reduce refresh cadence to `max(refresh-seconds, 60)`.
5. WHERE `kind="sparkline"` THEN the element SHALL render a 64x24 SVG sparkline using `--pyc-metric-tile-sparkline-fg` without hard-coded colors.

### Requirement 2: Pluggable Tile Kinds via DashboardTileKindExtension

**User Story:** As an extension author, I want to ship a new tile kind (e.g.,
"SLO burn rate gauge") as a Custom Element, so that operators can drop it
into dashboards without forking Pychestrate.

**Acceptance Criteria (EARS):**

1. WHEN the element is asked to render `kind="<id>"` AND `<id>` is NOT a built-in kind THEN the element SHALL consult the `DashboardTileKindExtension` registry at `/api/v1/extensions/dashboard_tile_kinds.json` AND dynamically import the extension's bundle.
2. IF the extension's custom element tag does not exist after import THEN the element SHALL fall back to the generic numeric tile AND emit `pyc-metric-tile-extension-error` with `{extensionName, reason}`.
3. WHEN the extension tile renders THEN the parent `<pyc-metric-tile>` SHALL forward `query`, `range`, `refresh-seconds`, and `unit` attributes to it.
4. WHERE the extension declares `supports-drilldown: true` THEN the element SHALL surface a secondary-action affordance that emits `pyc-metric-tile-drilldown` with `{query, range, tileKind, extraContext}`.

### Requirement 3: Theming and Formatting

**User Story:** As a user, I want units, thresholds, and colors to look
correct and consistent with the rest of the dashboard, so that scanning
multiple tiles is quick.

**Acceptance Criteria (EARS):**

1. WHEN `unit` is one of `percent`, `bytes`, `seconds`, `count`, `rate` THEN the element SHALL format the rendered value using SI-aware formatting (e.g., `1.2 MiB`, `3.4 %`, `450 ms`).
2. IF `thresholds` is set as a JSON string THEN the element SHALL pick the token class matching the highest-breached threshold (`--pyc-metric-tile-state-warn-bg`, `--pyc-metric-tile-state-crit-bg`).
3. WHEN the `data-pyc-theme` ancestor attribute flips between light/dark THEN the tile SHALL repaint without reloading data.
4. WHEN `title` and `subtitle` attributes are set THEN the element SHALL render them via `textContent` in the header — no HTML injection.

### Requirement 4: Accessibility

**User Story:** As a keyboard user / screen-reader user, I want every tile to
be reachable and understandable, so that I can consume the dashboard without
a mouse.

**Acceptance Criteria (EARS):**

1. WHEN the element mounts THEN the root SHALL expose `role="region"` with `aria-label="<title> <value> <unit>"` updated on every refresh.
2. WHEN the user focuses the tile and presses `Enter` THEN the element SHALL emit `pyc-metric-tile-activate` (host page routes to the full metric view).
3. IF the tile is in an error state THEN the announcement SHALL include `"<title> — error"`.
4. WHEN the tile refreshes THEN the element SHALL use `aria-live="off"` on the value element by default to avoid flooding screen readers; hosts opt-in to `aria-live="polite"` via the `announce-refresh` attribute.

## Property-Based Test Requirements

### Property 1: Value Formatter Is Unit-Stable

- **Invariant:** For any numeric value and any supported unit, the formatted string contains a number and a unit suffix, and round-tripping the numeric portion back through the formatter with the same unit yields the same string.
- **Generator:** Random floats across ranges `[0, 1e-9]`, `[1e-9, 1]`, `[1, 1e12]`, combined with each supported unit.
- **Assertion:** `format(v, u) == format(format(v, u).numericPart, u)`.
- **Sample size:** 1000 generated cases

### Property 2: Threshold Selection Is Monotonic

- **Invariant:** For any threshold list `[warn, crit]` with `warn < crit` and any value `v`, the state class advances monotonically with `v` crossing thresholds.
- **Generator:** Random thresholds and random `v` in a wide range.
- **Assertion:** If `v1 < v2` and both in nominal range, `stateOf(v1) <= stateOf(v2)` in the ordinal `ok < warn < crit`.
- **Sample size:** 1000 generated cases

### Property 3: Extension Dispatch Idempotency

- **Invariant:** For any sequence of `kind` attribute changes that ends at a known tile kind, the rendered child custom-element tag equals the expected tag for that kind.
- **Generator:** Random sequences of kind changes across built-in and extension kinds with a final reset step.
- **Assertion:** Final child tag matches expected.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** TTI per tile p95 < 200 ms on cache hit; first refresh post-mount p95 < 500 ms. A 20-tile dashboard SHALL maintain 60 fps during simultaneous refresh ticks. Extension bundle load per kind p95 < 150 ms after warm-up.
- **NFR-2 (Security):** Same-origin REST; session cookies + CSRF. Extension bundles served only from registered namespaced paths. `query` is sent as a server-validated query string; the element never interprets query as JS. `title`, `subtitle`, and unit labels rendered via `textContent`.
- **NFR-3 (Observability):** Client metrics beaconed: `pychestrate_ui_metric_tile_tti_seconds{kind}` (histogram), `pychestrate_ui_metric_tile_query_duration_seconds{kind}` (histogram), `pychestrate_ui_metric_tile_refresh_total{kind, outcome}` (counter), `pychestrate_ui_metric_tile_extension_error_total{extension}` (counter). Log events `pychestrate.ui.metric_tile.refreshed`, `pychestrate.ui.metric_tile.error`, `pychestrate.ui.metric_tile.extension_error`.
- **NFR-4 (Reliability):** Queries that fail SHALL stop refreshing after 5 consecutive failures AND SHALL expose a retry affordance. Extension-kind tiles that throw during mount SHALL fall back to the generic numeric tile without breaking neighboring tiles.

## Out of Scope

- Authoring metrics (see `7-metrics-ingest` and `MetricDefinitionExtension`).
- Dashboard composition and layout (see `9-project-dashboard-ui`).
- Alerting decisions (see `7-alerts-budgets`; tiles display thresholds but do not route alerts).

## Dependencies

- **Depends on:** `9-ui-design-tokens`, `7-metrics-ingest`, `0-timeseries-backend`, `8-rest-api-v1`, `1-authentication`, `1-rbac`, `E-extension-host`.
- **Depended on by:** `9-project-dashboard-ui`, `9-admin-ui` (system-health tiles), `9-run-detail-ui` (run-kpi tiles).
- **Extension points exposed:** Consumes `resource: DashboardTileKindExtension`.
