# 9-run-detail-ui — Design

## Architecture

`9-run-detail-ui` is a composition Custom Element (`<pyc-run-detail>`) that
instantiates the three pane elements, owns the header and right-rail preview,
and brokers cross-pane forwarding (selection in `9-wc-result-viewer` drives
log jump and artifact path; artifact clicks drive preview mount). Stream
reconnect banners are aggregated at the page level so users see one coherent
status. Run state transitions flow through a single SSE subscription to
`/api/v1/runs/{id}/state.stream` driven by `5-run-state-machine` via
`6-live-run-view`. Ships in **Phase 5**. Hosted at `GET /runs/<id>`;
composed inside `6-compare-runs` side-by-side frames in Phase 5+.

## Data Model

No persistent entities. Runtime state:

- `RunContext` — `{runId: string, project: {id, name}, pod: {id, name}, client: {id, name}, state: RunState, startedAt: string | null, completedAt: string | null, dispatcher: string, envelopeHash: string, capabilitiesRequired: string[]}`.
- `PaneStreamStatus` — `{pane: "results"|"logs"|"state", status: "connecting"|"open"|"reconnecting"|"closed", reason: string | null}`.
- `PreviewState` — `{active: boolean, artifactPath: string | null, componentTag: string | null, bundleUrl: string | null, contentUrl: string | null}`.
- `Selection` — `{resultNodePath: string | null, suggestedArtifactPath: string | null, suggestedLogSequence: number | null}`.

## Interfaces

### Public API

**Tag name:** `<pyc-run-detail>`

**Observed attributes:**

- `run-id` (string; UUID).
- `default-pane` (`results` | `logs` | `artifacts`; default `results`).
- `aria-label` (string).

**Properties (JS):**

- `runId: string`
- `context: RunContext | null`
- `selection: Selection`
- `preview: PreviewState`
- `cancel(reason: string): Promise<void>`
- `requeueFailing(reason: string): Promise<void>`
- `openCompare(otherRunId: string): void`
- `closePreview(): void`

**Events (bubbling, composed):**

- `pyc-run-detail-ready` — `{runId, state}`.
- `pyc-run-detail-state-changed` — `{from, to}`.
- `pyc-run-detail-action` — `{action, outcome}`.
- `pyc-run-detail-terminal` — `{state, passed, failed, errored, durationMs}`.
- `pyc-run-detail-preview-mounted` — `{artifactPath, componentTag}`.
- `pyc-run-detail-preview-failed` — `{artifactPath, reason}`.

**Slots:**

- `slot="header-right"` — consumer-supplied controls.
- `slot="actions"` — optional custom action group.
- `slot="not-found"` — rendered when run 404s.
- `slot="banner"` — additional banners (e.g., triage hints).

**CSS custom properties respected:**

- `--pyc-run-detail-bg` → `var(--pyc-color-app-bg)`
- `--pyc-run-detail-header-bg` → `var(--pyc-color-surface-elevated)`
- `--pyc-run-detail-header-fg` → `var(--pyc-color-on-surface-elevated)`
- `--pyc-run-detail-banner-reconnect-bg` → `var(--pyc-color-warn-subtle)`
- `--pyc-run-detail-pane-border` → `var(--pyc-color-border-subtle)`
- `--pyc-run-detail-preview-bg` → `var(--pyc-color-surface)`
- `--pyc-run-detail-focus-ring` → `var(--pyc-focus-ring)`
- `--pyc-run-detail-font-family` → `var(--pyc-font-family-ui)`

**A11y requirements:**

- Top-level `role="main"` with `aria-label="Run detail"`.
- Each pane wrapped in `role="region"` with accessible name (`"Results"`, `"Log stream"`, `"Artifacts"`).
- Header uses `role="banner"`.
- Preview panel is a `role="region"` with a focus trap when active; `Esc` closes and returns focus.
- Keyboard: `Ctrl/Cmd+1` / `2` / `3` jumps between panes; `?` opens help; `Shift+C` cancels (when permitted); `Shift+R` requeues failing (when permitted).
- Live region announces state changes and preview errors.

Server REST surfaces consumed:

- `GET /api/v1/runs/{run_id}/context`.
- `GET /api/v1/runs/{run_id}/state.stream` (SSE).
- `POST /api/v1/runs/{run_id}:cancel` — cancel.
- `POST /api/v1/runs/{run_id}:requeue_failing` — requeue failing shards.
- Plus those consumed by the embedded components.

### Internal API

```typescript
class RunContextTransport {
    fetch(runId: string): Promise<RunContext>
    openStateStream(runId: string): StreamHandle
}

class CrossPaneBridge {
    onResultSelected(path: string, suggestedSequence: number | null): void
    onArtifactOpen(path: string): void
    onLogSelect(sequence: number): void
}

class PreviewController {
    mount(entry: EntryRef, rendererChoice: RendererChoice): Promise<void>
    unmount(): void
}

class StreamStatusAggregator {
    update(pane: PaneName, status: ConnectionStatus): void
    current(): PaneStreamStatus
}
```

### Extension Surface

None directly. Consumes `ArtifactRendererExtension` via `6-artifact-browser`.

### Events Emitted

DOM CustomEvents only.

### Events Consumed

From embedded components: `pyc-result-viewer-select`,
`pyc-result-viewer-artifact-open`, `pyc-log-stream-opened` / `-closed` /
`-reconnecting`, `pyc-result-viewer-stream-closed`, `entity.run.state_changed`
via SSE.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/webinterface/components/pyc-run-detail/`:

- `pyc-run-detail.ts` — composition Custom Element.
- `run-header.ts` — header subcomponent.
- `cross-pane-bridge.ts` — selection forwarding.
- `preview-controller.ts` — right-rail preview mount/unmount.
- `stream-status-aggregator.ts`.
- `transport/run-context-transport.ts`.
- `keybindings.ts`.
- `help-dialog.ts`.
- `styles.css` — multi-line CSS referencing `--pyc-run-detail-*` tokens.
- `tests/`.

Bundle at `/ui/components/pyc-run-detail/pyc-run-detail.js`. Server-side route `GET /runs/<id>` serves the document shell.

## Key Flows

### Flow 1 — Open a completed run

1. Element reads `run-id`, fetches context, renders header.
2. Instantiates `<pyc-result-viewer>`, `<pyc-log-stream>`, `<px-artifact-browser>` all keyed to the run.
3. Result viewer resolves terminal data; log stream resumes from offset 0 (read-only); artifact browser lists root.
4. Element emits `pyc-run-detail-ready`.

### Flow 2 — Watch a running run

1. SSE `state.stream` subscribes.
2. Each transition updates header and emits `pyc-run-detail-state-changed`.
3. On `terminal` transition, result viewer switches to terminal doc; log stream switches out of live mode; element emits `pyc-run-detail-terminal`.

### Flow 3 — Triage loop (select node → log jump → artifact preview)

1. User selects a failing test; `pyc-result-viewer-select` fires with `{path, status, kind}`.
2. Bridge computes `suggestedLogSequence` and calls `logEl.jumpToSequence(...)`.
3. Bridge sets artifact-browser `path` to that node's artifact subtree.
4. User clicks an artifact; `6-artifact-browser` returns `RendererChoice`; PreviewController mounts the renderer in the right rail; `pyc-run-detail-preview-mounted` fires.

### Flow 4 — Cancel

1. User presses `Shift+C`; element calls `cancel(reason)`.
2. Typed-confirm dialog appears; on accept, POST `/runs/{id}:cancel` with reason.
3. On response, emit `pyc-run-detail-action` with `{action: "cancel", outcome}`.

## Error Handling

- Context 404: render `slot="not-found"`; offer project-run-list link.
- Context 403: render forbidden state with a helpful message.
- Any pane's stream reconnects: aggregator surfaces a single header banner; individual pane banners are suppressed.
- Preview mount throws: fall back to `<px-artifact-generic-download>`; emit `pyc-run-detail-preview-failed`; preview closes on next action.
- Cancel / requeue 409 (already terminal): render inline explanation; emit action with outcome `stale`.

## Security Considerations

- `run-id` validated as UUID before any network call.
- RBAC is enforced server-side on every endpoint; client hides affordances.
- Signed URLs never rendered as HTML; open-in-new-tab uses `window.open` with `rel="noopener noreferrer"`.
- Reason strings required for mutating actions and audited server-side via `1-audit-log`.
- No local/session storage usage beyond the result-viewer's own expansion state keyed per run.

## Observability

Client metrics beaconed:

- `pychestrate_ui_run_detail_tti_seconds` — histogram.
- `pychestrate_ui_run_detail_pane_mount_duration_seconds{pane}` — histogram.
- `pychestrate_ui_run_detail_action_total{action, outcome}` — counter.
- `pychestrate_ui_run_detail_renderer_error_total{extension}` — counter.
- `pychestrate_ui_run_detail_reconnect_total{reason}` — counter.
- `pychestrate_ui_run_detail_preview_mount_total{outcome}` — counter.

Log events: `pychestrate.ui.run_detail.opened`, `pychestrate.ui.run_detail.action`, `pychestrate.ui.run_detail.terminal`, `pychestrate.ui.run_detail.reconnect`, `pychestrate.ui.run_detail.preview_failed`.

Trace spans (server-side at ingestion): `pychestrate.ui.run_detail.metric_ingest`.

## Open Questions

- Should selection forwarding be bidirectional (log click selects closest result node)? Timebox: Phase 5 midpoint.
- Preview-panel layout on small viewports — bottom sheet vs right rail? Timebox: Phase 5 exit.
- Should the page support query-string deep links into a specific node + artifact pair for sharing? Timebox: Phase 5 kickoff.
