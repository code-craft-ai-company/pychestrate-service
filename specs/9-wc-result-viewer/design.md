# 9-wc-result-viewer — Design

## Architecture

`9-wc-result-viewer` is a Custom Element that renders the testbase result tree
for a single run. It is dual-source: a summary fetch for instant structure
and counters, plus an incremental JSOS stream (or a single terminal
`testrun_results.json` for completed runs). The element owns a node-keyed
lookup map plus a flattened outline projected for virtualisation. It resolves
visual styling exclusively through CSS custom properties defined under
`--pyc-result-viewer-*`, mapped to base `9-ui-design-tokens`. Ships in
**Phase 5**. Hosted in `9-run-detail-ui` and embedded inside `6-compare-runs`.
The authoritative result store is `5-result-ingest-watcher`; the REST API is
the render boundary.

## Data Model

No persistent entities. Runtime state:

- `ResultNode` — `{path: string, kind: "suite"|"test"|"subtest"|"step", name: string, status: NodeStatus, startedAt: string | null, completedAt: string | null, durationMs: number | null, message: string | null, childrenPaths: string[], artifactRefs: ArtifactRef[]}`.
- `NodeStatus` — one of `pending`, `running`, `passed`, `failed`, `errored`, `skipped`, `xfailed`, `xpassed`, `cancelled`.
- `ArtifactRef` — `{label: string, relPath: string, contentType: string | null}`.
- `SummarySnapshot` — `{total, completed, passed, failed, errored, skipped, startedAt, completedAt, state}`.
- `OutlineRow` — `{path: string, indent: number, visible: boolean}`.

Lookup:

- `nodesByPath: Map<string, ResultNode>` — O(1) upsert.
- `outline: OutlineRow[]` — projected on demand from the tree for virtualisation.
- `expansionState: Map<string, boolean>` — persisted in `sessionStorage` keyed by `pyc:rv:<run-id>`.

## Interfaces

### Public API

**Tag name:** `<pyc-result-viewer>`

**Observed attributes:**

- `run-id` (string; UUID) — the run to render.
- `filter` (comma-separated statuses) — default `""` (no filter).
- `expand-failures` (boolean) — auto-expand failed/errored branches; default on.
- `virtualize-threshold` (string; integer) — default `5000`.
- `stream-mode` (`auto` | `stream-only` | `terminal-only`) — default `auto`.
- `aria-label` (string) — accessibility label override.

**Properties (JS):**

- `runId: string`
- `summary: SummarySnapshot | null`
- `nodeCount: number`
- `visibleNodeCount: number`
- `getNode(path: string): ResultNode | null`
- `setFilter(filters: string[]): void`
- `expand(path: string): void`
- `collapse(path: string): void`
- `expandAllFailing(): void`
- `reload(): void`

**Events (bubbling, composed):**

- `pyc-result-viewer-summary` — `{summary: SummarySnapshot}`.
- `pyc-result-viewer-node-appended` — `{path, kind, status}` (throttled per batch).
- `pyc-result-viewer-select` — `{path, status, kind}`.
- `pyc-result-viewer-filter-changed` — `{visibleCount, totalCount, filters}`.
- `pyc-result-viewer-artifact-open` — `{path, label, relPath, contentType}`.
- `pyc-result-viewer-stream-closed` — `{reason, recordCount}`.
- `pyc-result-viewer-run-missing` — `{runId}`.

**Slots:**

- `slot="summary-right"` — consumer-supplied controls next to summary (e.g., rerun button).
- `slot="empty"` — rendered when zero nodes have been appended.
- `slot="stream-error"` — rendered when the JSOS stream can't open.
- `slot="node-badge-extra"` — extension slot for per-node badges.

**CSS custom properties respected:**

- `--pyc-result-viewer-bg` → `var(--pyc-color-surface)`
- `--pyc-result-viewer-fg` → `var(--pyc-color-on-surface)`
- `--pyc-result-viewer-row-hover` → `var(--pyc-color-hover)`
- `--pyc-result-viewer-row-selected` → `var(--pyc-color-selected)`
- `--pyc-result-viewer-badge-passed-bg`, `--pyc-result-viewer-badge-failed-bg`, `--pyc-result-viewer-badge-errored-bg`, `--pyc-result-viewer-badge-skipped-bg`, `--pyc-result-viewer-badge-running-bg`, `--pyc-result-viewer-badge-pending-bg`
- `--pyc-result-viewer-progress-fg` → `var(--pyc-color-accent)`
- `--pyc-result-viewer-indent-guide` → `var(--pyc-color-border-subtle)`
- `--pyc-result-viewer-font-family` → `var(--pyc-font-family-ui)`
- `--pyc-result-viewer-focus-ring` → `var(--pyc-focus-ring)`

**A11y requirements:**

- Root: `role="tree"`, `aria-label="Run results"` (or override), `aria-busy` reflecting stream state.
- Each node: `role="treeitem"`, `aria-level=<depth>`, `aria-expanded` where applicable, `aria-selected` for the focused node.
- Keyboard: `ArrowDown`/`Up` to move focus, `ArrowRight`/`Left` to expand/collapse, `Home`/`End` to jump to first/last visible, `Enter` to select, `*` to expand the whole subtree, `/` to focus the filter field, `Esc` to clear selection.
- Live region announces failing transitions and filter-count changes.
- Focus ring honors `--pyc-result-viewer-focus-ring`.

Server REST surfaces consumed:

- `GET /api/v1/runs/{run_id}/testrun_summary.json`.
- `GET /api/v1/runs/{run_id}/testrun_results_stream.jsos` (server sends newline-delimited JSON over `Transfer-Encoding: chunked` or `text/event-stream`).
- `GET /api/v1/runs/{run_id}/testrun_results.json` (terminal only).

### Internal API

```typescript
class ResultTree {
    private _byPath: Map<string, ResultNode> = new Map()
    private _rootPaths: string[] = []
    upsert(record: JsosRecord): UpsertResult { /* ... */ }
    children(path: string): ResultNode[] { /* ... */ }
    projectOutline(filter: FilterSet, expansion: Map<string, boolean>): OutlineRow[] { /* ... */ }
}

class JsosParser {
    feed(chunk: Uint8Array): JsosRecord[] { /* splits on \n, parses each line */ }
    malformedCount: number
}

class ResultTransport {
    connect(runId: string, mode: StreamMode): Promise<void>
    onSummary(cb: (s: SummarySnapshot) => void): void
    onRecord(cb: (r: JsosRecord) => void): void
    onClose(cb: (reason: string) => void): void
}
```

### Extension Surface

None declared. Nodes do not open arbitrary renderers; artifact open is
delegated to the host via `pyc-result-viewer-artifact-open`, which
`9-run-detail-ui` forwards into `6-artifact-browser`'s renderer chain.

### Events Emitted

All events above are DOM CustomEvents. Client metrics beaconed to
`/api/v1/ui/metrics`.

### Events Consumed

Transport-level events from fetch + JSOS stream; nothing from the message bus.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/webinterface/components/pyc-result-viewer/`:

- `pyc-result-viewer.ts` — Custom Element.
- `result-tree.ts` — in-memory tree + outline projection.
- `jsos-parser.ts` — JSOS chunked parser.
- `result-transport.ts` — summary + stream orchestration.
- `virtual-outline.ts` — row virtualisation when above threshold.
- `keybindings.ts` — keyboard map.
- `styles.css` — multi-line CSS referencing `--pyc-result-viewer-*` tokens.
- `tests/`.

Bundle emitted at `/ui/components/pyc-result-viewer/pyc-result-viewer.js`.

## Key Flows

### Flow 1 — Open a completed run

1. Element reads `run-id`.
2. Transport fetches `testrun_summary.json`; element renders counters and progress bar.
3. Run state is `terminal`; transport fetches `testrun_results.json` once.
4. Records are upserted into the tree in batches within `requestAnimationFrame`.
5. `expand-failures` is true; all failed branches auto-expand.

### Flow 2 — Open a running run

1. Transport fetches summary (state `running`, partial counters).
2. Transport opens the JSOS stream; JSOS parser feeds records.
3. Element appends / updates nodes in place; outline is invalidated lazily.
4. On terminal status, stream closes cleanly; element emits `pyc-result-viewer-stream-closed`.

### Flow 3 — Triager filters to failed + errored

1. User sets `filter="failed,errored"` (or clicks filter UI which sets the attribute).
2. Outline projection recomputes visibility; invisible rows have `display: none`.
3. Element emits `pyc-result-viewer-filter-changed`.
4. Expansion state persists across navigation via `sessionStorage`.

## Error Handling

- Malformed JSOS line: skipped, counter incremented, debug-logged. The stream continues.
- Stream HTTP 401/403: close cleanly, render `slot="stream-error"` with a "forbidden" variant.
- 404 on summary or results: emit `pyc-result-viewer-run-missing`; render empty state.
- Invalid `run-id` (non-UUID): element treats it as closed; `status="closed"` attribute reflected.
- Attribute validation errors (`filter` with unknown statuses) cause the element to ignore unknown entries and log a warning.

## Security Considerations

- All requests same-origin against `8-rest-api-v1`.
- Rendering uses `textContent` only; messages that contain ANSI codes are stripped (plain text) — the color is driven by status badge tokens.
- Artifact links are emitted as events with relative paths; the host page decides whether to sign URLs through `6-artifact-browser`.
- `sessionStorage` key includes `run-id`; cross-run leakage is not possible.
- Stream payloads rejected at content-length > 256 MiB (configurable) with a graceful fallback to the terminal document when available.

## Observability

Client-side counters and histograms beaconed:

- `pychestrate_ui_result_viewer_tti_seconds` — histogram.
- `pychestrate_ui_result_viewer_append_duration_seconds{batch_size_bucket}` — histogram.
- `pychestrate_ui_result_viewer_stream_duration_seconds` — histogram.
- `pychestrate_ui_result_viewer_malformed_total` — counter.
- `pychestrate_ui_result_viewer_filter_total{filter}` — counter.
- `pychestrate_ui_result_viewer_run_missing_total` — counter.

Log events: `pychestrate.ui.result_viewer.opened`, `pychestrate.ui.result_viewer.closed`, `pychestrate.ui.result_viewer.malformed`, `pychestrate.ui.result_viewer.run_missing`.

Trace spans (server-side at ingestion): `pychestrate.ui.result_viewer.metric_ingest`.

## Open Questions

- When a suite contains 100 000+ leaves should the element fetch sub-tree summaries lazily? Timebox: Phase 5 exit.
- Should xfail/xpass be rendered with a distinct badge or grouped with pass/fail? Timebox: Phase 5 midpoint.
- Multi-select + bulk actions (rerun all failing) — ship in Phase 5 or push to Phase 6? Timebox: Phase 5 kickoff.
