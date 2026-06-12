# 9-wc-metric-tile — Design

## Architecture

`9-wc-metric-tile` is the dashboard tile primitive. It queries a metric and
renders it in one of the built-in kinds (`number`, `sparkline`, `gauge`,
`histogram-summary`) OR dispatches to a `DashboardTileKindExtension` that
contributes a custom element tag. The parent element does query management,
refresh scheduling, and wrapping; the inner child element does the pixels.
Extensions register tile kinds through a JSON feed populated by
`E-extension-host` and serve bundles under namespaced paths. Ships in
**Phase 9** when `0-timeseries-backend` and `7-metrics-ingest` stand up fully.
Composed in `9-project-dashboard-ui`.

## Data Model

No persistent entities. Runtime state:

- `TileQuery` — `{query: string, range: string, step: string | null, unit: Unit, title: string, subtitle: string | null, thresholds: {warn?: number, crit?: number} | null}`.
- `QueryResult` — `{kind: "scalar"|"series"|"heatmap"|"histogram", series: Point[] | null, value: number | null, fetchedAt: string}`.
- `TileKindRecord` — `{kindId: string, extensionName: string | null, componentTag: string, bundleUrl: string | null, supportsDrilldown: boolean}` (built-ins have `extensionName: null`).
- `RefreshScheduler` — `{tickSeconds: number, backgrounded: boolean, consecutiveFailures: number}`.

## Interfaces

### Public API

**Tag name:** `<pyc-metric-tile>`

**Observed attributes:**

- `kind` (string; built-in or extension kind id; default `number`).
- `query` (string) — PromQL/LogQL-like query string recognized by `7-metrics-ingest`.
- `range` (string; e.g., `1h`, `24h`) — query range.
- `step` (string; optional) — query step override.
- `unit` (`percent` | `bytes` | `seconds` | `count` | `rate`; default `count`).
- `title`, `subtitle` (string).
- `refresh-seconds` (string; integer; default `30`).
- `thresholds` (JSON string; e.g., `{"warn": 0.5, "crit": 0.9}`).
- `announce-refresh` (boolean attribute).
- `aria-label` (string).

**Properties (JS):**

- `query: string`
- `range: string`
- `unit: Unit`
- `lastResult: QueryResult | null`
- `lastFetchedAt: Date | null`
- `setThresholds(t: {warn?: number, crit?: number}): void`
- `reload(): Promise<void>`
- `pauseRefresh(): void`
- `resumeRefresh(): void`

**Events (bubbling, composed):**

- `pyc-metric-tile-refreshed` — `{at, durationMs, kindId}`.
- `pyc-metric-tile-error` — `{status, error_code}`.
- `pyc-metric-tile-extension-error` — `{extensionName, reason}`.
- `pyc-metric-tile-activate` — `{query, range, kindId}`.
- `pyc-metric-tile-drilldown` — `{query, range, tileKind, extraContext}`.
- `pyc-metric-tile-state-changed` — `{state: "ok"|"warn"|"crit"|"error"}`.

**Slots:**

- `slot="header-right"` — consumer-supplied controls (e.g., open-query link).
- `slot="footer"` — consumer-supplied footer.
- `slot="error"` — consumer-supplied error content (element falls back to a generic error message if absent).
- `slot="extra"` — passthrough to extension children.

**CSS custom properties respected:**

- `--pyc-metric-tile-bg` → `var(--pyc-color-surface)`
- `--pyc-metric-tile-fg` → `var(--pyc-color-on-surface)`
- `--pyc-metric-tile-border` → `var(--pyc-color-border-subtle)`
- `--pyc-metric-tile-title-fg`, `--pyc-metric-tile-subtitle-fg`
- `--pyc-metric-tile-value-font` → `var(--pyc-font-family-display)`
- `--pyc-metric-tile-value-size` → `var(--pyc-font-size-display)`
- `--pyc-metric-tile-sparkline-fg` → `var(--pyc-color-accent)`
- `--pyc-metric-tile-state-ok-bg`, `--pyc-metric-tile-state-warn-bg`, `--pyc-metric-tile-state-crit-bg`, `--pyc-metric-tile-state-error-bg`
- `--pyc-metric-tile-focus-ring` → `var(--pyc-focus-ring)`

**A11y requirements:**

- Root: `role="region"` with `aria-label="<title> <value> <unit>"` (or override), `aria-busy` during refresh, `aria-live="polite"` when `announce-refresh` is set.
- Tile is focusable (`tabindex="0"`); `Enter` emits `pyc-metric-tile-activate`.
- Error state announced to screen readers.

Server REST surfaces consumed:

- `GET /api/v1/metrics/query?q=<q>&range=<r>&step=<s>` — authoritative metric query.
- `GET /api/v1/extensions/dashboard_tile_kinds.json` — tile-kind registry.

### Internal API

```typescript
class TileTransport {
    query(q: TileQuery): Promise<QueryResult>
}

class TileKindRegistry {
    load(): Promise<TileKindRecord[]>
    resolve(kindId: string): TileKindRecord | null
}

class RefreshScheduler {
    start(fn: () => Promise<void>): void
    stop(): void
    onBackgrounded(backgrounded: boolean): void
}

class ValueFormatter {
    format(value: number, unit: Unit): FormattedValue
}

class ThresholdEvaluator {
    evaluate(value: number, thresholds: Thresholds | null): "ok" | "warn" | "crit"
}
```

### Extension Surface

Consumes `DashboardTileKindExtension` via the registry JSON and dynamic
`import()`. Each record:

```typescript
interface DashboardTileKindRecord {
    kindId: string
    extensionName: string
    componentTag: string        // custom element tag
    bundleUrl: string           // /ext/<ext-name>/bundle/...
    supportsDrilldown: boolean
    forwardedAttributes: string[]
}
```

In-tree built-ins under `source/site/ccai/pychestrate/webservice/webinterface/components/`:

- `<pyc-metric-tile-number>` — scalar number.
- `<pyc-metric-tile-sparkline>` — 64x24 SVG sparkline.
- `<pyc-metric-tile-gauge>` — arc gauge with thresholds.
- `<pyc-metric-tile-histogram>` — histogram summary.

### Events Emitted

DOM CustomEvents. Client metrics beaconed.

### Events Consumed

None.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/webinterface/components/pyc-metric-tile/`:

- `pyc-metric-tile.ts` — parent Custom Element with wrapper + dispatch.
- `transport/tile-transport.ts` — metric query client.
- `tile-kind-registry.ts` — built-in + extension tile resolution.
- `refresh-scheduler.ts` — cadence and backoff.
- `value-formatter.ts` — SI-aware formatting.
- `threshold-evaluator.ts`.
- `styles.css` — multi-line CSS referencing `--pyc-metric-tile-*` tokens.
- `tests/`.

Built-in child elements live in sibling folders:

- `components/pyc-metric-tile-number/`.
- `components/pyc-metric-tile-sparkline/`.
- `components/pyc-metric-tile-gauge/`.
- `components/pyc-metric-tile-histogram/`.

Bundle emitted at `/ui/components/pyc-metric-tile/pyc-metric-tile.js`.

## Key Flows

### Flow 1 — Render a scalar tile

1. Element reads `query`, `range`, `unit`, `kind="number"`.
2. Transport issues `GET /metrics/query`; on success `QueryResult` arrives.
3. `ValueFormatter.format` produces display text; `ThresholdEvaluator` picks a state token.
4. Inner `<pyc-metric-tile-number>` renders the formatted value.
5. Element emits `pyc-metric-tile-refreshed` and schedules the next tick.

### Flow 2 — Render an extension-contributed tile

1. Element reads `kind="slo-burn-rate"` (not built-in).
2. Registry resolves to `{componentTag: "acme-slo-burn-rate", bundleUrl: "/ext/acme-slo/bundle/acme-slo.js"}`.
3. Bundle is dynamically imported (cached across tiles).
4. Inner element is created; forwarded attributes are set.
5. On subsequent `query` result, parent forwards the result via a `data` property.

### Flow 3 — Backoff after failures

1. Query fails 5 times consecutively.
2. Scheduler stops; element renders `slot="error"` with a retry affordance.
3. User clicks retry; scheduler resumes and counters reset.

## Error Handling

- Query 4xx/5xx: emit `pyc-metric-tile-error`; render `slot="error"` content.
- After 5 consecutive failures: stop refresh, expose retry.
- Extension bundle load failure: fall back to built-in numeric tile; emit `pyc-metric-tile-extension-error`.
- Inner extension element throws during mount: swap to built-in fallback, mark extension quarantined for the parent instance.
- Malformed `thresholds` JSON: ignore thresholds, render `ok` state, console-warn.

## Security Considerations

- Same-origin REST; session cookies + CSRF.
- `query` parameter sent server-side; the element does not interpret it. Server validates the query language and RBAC.
- Extension bundle URLs restricted to `/ext/<ext-name>/bundle/...`.
- `title` and `subtitle` rendered via `textContent`; thresholds parsed via `JSON.parse` with a try/catch.
- No localStorage / sessionStorage usage.

## Observability

Client metrics beaconed:

- `pychestrate_ui_metric_tile_tti_seconds{kind}` — histogram.
- `pychestrate_ui_metric_tile_query_duration_seconds{kind}` — histogram.
- `pychestrate_ui_metric_tile_refresh_total{kind, outcome}` — counter.
- `pychestrate_ui_metric_tile_extension_error_total{extension}` — counter.
- `pychestrate_ui_metric_tile_state_total{state}` — counter.

Log events: `pychestrate.ui.metric_tile.refreshed`, `pychestrate.ui.metric_tile.error`, `pychestrate.ui.metric_tile.extension_error`.

Trace spans (server-side at ingestion): `pychestrate.ui.metric_tile.metric_ingest`.

## Open Questions

- Coordinated refresh jitter across a dashboard of 20+ tiles (server-side hint?) to smooth load spikes? Timebox: Phase 9 midpoint.
- Built-in heatmap tile — ship in Phase 9 or defer? Timebox: Phase 9 kickoff.
- Should query cancellation on unmount use `AbortController`? Timebox: Phase 9 exit.
