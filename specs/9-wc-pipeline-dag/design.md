# 9-wc-pipeline-dag — Design

## Architecture

`9-wc-pipeline-dag` is a Custom Element that fetches a pipeline graph JSON
projection from `8-rest-api-v1`, computes a deterministic layered layout
(Sugiyama-style with stable tie-breakers), renders nodes and edges into an
SVG inside a closed shadow root, and overlays status updates from
`6-live-run-view`'s pipeline status stream. Layout is performed on the main
thread via a self-contained algorithm (no d3/cytoscape dependency) keyed by
deterministic secondary sort on `nodeId` for reproducibility. The element
owns view state (zoom, pan, selection, focus) but not graph state — the
authoritative graph lives in `6-pipeline-definition`. Ships in **Phase 6**.

## Data Model

No persistent entities. Runtime state:

- `DagNode` — `{nodeId: string, label: string, stepKind: string, status: NodeStatus, shardIndex: number | null, matrixSize: number | null, startedAt: string | null, completedAt: string | null, metadata: Record<string, string>}`.
- `DagEdge` — `{fromId: string, toId: string, kind: "sequence" | "fanout" | "fanin" | "conditional"}`.
- `Graph` — `{nodes: DagNode[], edges: DagEdge[], matrixGroups: MatrixGroup[]}`.
- `LayoutNode` — `{nodeId, rank: number, order: number, x: number, y: number, width: number, height: number}`.
- `Layout` — `{nodes: LayoutNode[], edges: LayoutEdge[], width: number, height: number, rankCount: number}`.
- `ViewState` — `{zoom: number, translate: {x, y}, selectedNodeId: string | null, focusedNodeId: string | null}`.

Status map: `statusByNodeId: Map<string, NodeStatus>`, updated in place.

## Interfaces

### Public API

**Tag name:** `<pyc-pipeline-dag>`

**Observed attributes:**

- `pipeline-run-id` (string; UUID) — the pipeline run to render.
- `direction` (`LR` | `TB`; default `LR`) — layout orientation.
- `expand-matrix` (`all` | `none` | `failing`; default `failing`) — default matrix expansion policy.
- `zoom-min`, `zoom-max` (string; floats; default 0.25 / 4.0).
- `initial-zoom` (`fit` | `1.0`; default `fit`).
- `stream` (`sse` | `ws` | `off`; default `sse`) — live status transport.
- `aria-label` (string) — accessibility label override.

**Properties (JS):**

- `pipelineRunId: string`
- `graph: Graph | null`
- `layout: Layout | null`
- `viewState: ViewState`
- `select(nodeId: string): void`
- `focus(nodeId: string): void`
- `resetViewport(): void`
- `fitSubgraph(nodeId: string): void`
- `toggleMatrix(matrixGroupId: string): void`
- `reload(): void`

**Events (bubbling, composed):**

- `pyc-pipeline-dag-graph-loaded` — `{nodeCount, edgeCount}`.
- `pyc-pipeline-dag-status-update` — `{nodeId, status, prevStatus}` (throttled per batch).
- `pyc-pipeline-dag-select` — `{nodeId, stepKind, status, shardIndex}`.
- `pyc-pipeline-dag-navigate` — `{nodeId, destination: "logs"|"results"|"artifacts"}` (emitted when user clicks a secondary action; host page resolves).
- `pyc-pipeline-dag-terminal` — `{passed, failed, errored, skipped, durationMs}`.
- `pyc-pipeline-dag-error` — `{reason, detail}`.

**Slots:**

- `slot="toolbar"` — consumer-supplied controls (rerun, cancel).
- `slot="legend"` — consumer-supplied legend.
- `slot="graph-unavailable"` — rendered when graph fetch fails.
- `slot="node-extra"` — extension point rendered inside each node's badge area.

**CSS custom properties respected:**

- `--pyc-pipeline-dag-bg` → `var(--pyc-color-surface)`
- `--pyc-pipeline-dag-fg` → `var(--pyc-color-on-surface)`
- `--pyc-pipeline-dag-edge` → `var(--pyc-color-border-strong)`
- `--pyc-pipeline-dag-edge-selected` → `var(--pyc-color-accent)`
- `--pyc-pipeline-dag-node-passed-bg`, `--pyc-pipeline-dag-node-failed-bg`, `--pyc-pipeline-dag-node-errored-bg`, `--pyc-pipeline-dag-node-skipped-bg`, `--pyc-pipeline-dag-node-running-bg`, `--pyc-pipeline-dag-node-pending-bg`
- `--pyc-pipeline-dag-pulse-failed` → 300 ms keyframe amplitude via `var(--pyc-motion-accent)`
- `--pyc-pipeline-dag-spinner-speed` → `var(--pyc-motion-spinner)`
- `--pyc-pipeline-dag-font-family` → `var(--pyc-font-family-ui)`
- `--pyc-pipeline-dag-focus-ring` → `var(--pyc-focus-ring)`

**A11y requirements:**

- Root: `role="application"` with `aria-label="Pipeline DAG"` (overridable) and `aria-describedby` referencing a topologically-ordered hidden `role="list"` shadow element.
- Each node: `role="button"`, `tabindex="0"`, `aria-label="<label> <status>"`, `aria-current="step"` when selected.
- Keyboard: `Tab` traversal in topological order, `ArrowRight`/`ArrowLeft` for downstream/upstream, `Enter` selects, `F` fits subgraph, `R` resets, `M` toggles matrix expansion on focused matrix group, `Esc` clears selection.
- Live region announces status transitions and errors.

Server REST surfaces consumed:

- `GET /api/v1/pipeline_runs/{pipeline_run_id}/graph.json` — static graph definition.
- `GET /api/v1/pipeline_runs/{pipeline_run_id}/status.stream` — SSE of status events.
- `GET /api/v1/pipeline_runs/{pipeline_run_id}/status.ws` — WebSocket fallback.

### Internal API

```typescript
class DagLayout {
    compute(graph: Graph, direction: "LR" | "TB"): Layout { /* deterministic Sugiyama */ }
}

class DagRenderer {
    render(layout: Layout, viewState: ViewState, statusByNodeId: Map<string, NodeStatus>): void
}

class PipelineStatusTransport {
    connect(pipelineRunId: string, mode: StreamMode): Promise<void>
    onEvent(cb: (e: StatusEvent) => void): void
    onClose(cb: (reason: string) => void): void
}

class CycleDetector {
    detect(graph: Graph): string[][]  // returns strongly-connected components with size > 1
}
```

### Extension Surface

None declared on this element. Custom node appearance is deferred to
`DashboardTileKindExtension` (consumed by `9-project-dashboard-ui`) when a
pipeline tile is embedded there.

### Events Emitted

All DOM CustomEvents. Client metrics beaconed to `/api/v1/ui/metrics`.

### Events Consumed

SSE/WebSocket status events from `6-live-run-view`.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/webinterface/components/pyc-pipeline-dag/`:

- `pyc-pipeline-dag.ts` — Custom Element.
- `layout/sugiyama.ts` — deterministic layered layout.
- `layout/cycle-detector.ts` — Tarjan SCC implementation.
- `renderer/svg-renderer.ts` — SVG rendering with zoom/pan.
- `renderer/node-shapes.ts` — per-step-kind node shape functions.
- `transport/status-transport.ts` — SSE + WebSocket with backoff.
- `keybindings.ts`.
- `styles.css` — multi-line CSS referencing `--pyc-pipeline-dag-*` tokens.
- `tests/`.

Bundle emitted at `/ui/components/pyc-pipeline-dag/pyc-pipeline-dag.js`.

## Key Flows

### Flow 1 — Open a running pipeline

1. Element reads `pipeline-run-id`.
2. Transport fetches `graph.json`; layout is computed on the main thread.
3. SVG is rendered; element emits `pyc-pipeline-dag-graph-loaded`.
4. Status stream opens; each event updates the in-place node badge; layout is never recomputed.
5. On terminal status across all nodes, element emits `pyc-pipeline-dag-terminal`.

### Flow 2 — Cycle detected

1. `graph.json` includes a back edge due to an authoring bug.
2. `CycleDetector.detect(graph)` returns the implicated SCC.
3. Element emits `pyc-pipeline-dag-error` with `{reason: "cycle_detected", nodes: [...]}`.
4. Renderer still renders the condensation (collapsing the SCC into a single super-node flagged as `cycle`) so the rest of the graph is navigable.

### Flow 3 — Matrix expansion

1. User focuses a matrix super-node and presses `M`.
2. `toggleMatrix(groupId)` flips the expansion policy locally.
3. Layout is recomputed (only this time; subsequent status updates do not re-layout).
4. Shards lay out in a sub-rank under their parent.

## Error Handling

- `graph.json` fetch 404: emit `pyc-pipeline-dag-error` `{reason: "not_found"}`, render `slot="graph-unavailable"`.
- `graph.json` fetch 401/403: emit `{reason: "forbidden"}`; do not retry.
- `graph.json` retryable 5xx: 3 retries with backoff 250 ms / 1 s / 4 s.
- Status stream disconnect: reflect `data-pyc-pipeline-dag-stream="disconnected"`, attempt reconnection with same backoff ladder as `9-wc-log-stream`.
- Cycles: render condensation, emit error event, do not throw.
- Malformed status event: skip, increment counter.

## Security Considerations

- Same-origin REST.
- Node labels and messages rendered via SVG `<text>` using `textContent`; no `innerHTML`.
- Navigation to logs/results/artifacts is emitted as an event carrying IDs only; host page resolves URLs through RBAC-aware REST endpoints.
- Layout runs in main thread with a 5 s wall-clock watchdog; exceeding the budget emits `pyc-pipeline-dag-error` `{reason: "layout_timeout"}`.
- Matrix expansion limited to `matrix-expansion-cap` nodes (default 5 000) to prevent pathological shards from freezing the UI.

## Observability

Client-side metrics beaconed:

- `pychestrate_ui_pipeline_dag_tti_seconds` — histogram.
- `pychestrate_ui_pipeline_dag_layout_duration_seconds{node_bucket}` — histogram.
- `pychestrate_ui_pipeline_dag_status_update_total{status}` — counter.
- `pychestrate_ui_pipeline_dag_cycle_detected_total` — counter.
- `pychestrate_ui_pipeline_dag_fps` — summary (sampled via `requestAnimationFrame`).
- `pychestrate_ui_pipeline_dag_reconnect_total{reason}` — counter.

Log events: `pychestrate.ui.pipeline_dag.opened`, `pychestrate.ui.pipeline_dag.terminal`, `pychestrate.ui.pipeline_dag.cycle_detected`, `pychestrate.ui.pipeline_dag.error`.

Trace spans (server-side at ingestion): `pychestrate.ui.pipeline_dag.metric_ingest`.

## Open Questions

- Should layout be offloaded to a Web Worker to avoid main-thread stalls on 2 000+ nodes? Timebox: Phase 6 midpoint.
- Edge routing: orthogonal routing with spline smoothing vs straight-line — what matches operator expectations? Timebox: Phase 6 kickoff.
- Matrix super-nodes: surface summary status (aggregated) vs first-failed-shard — configurable via attribute? Timebox: Phase 6 exit.
