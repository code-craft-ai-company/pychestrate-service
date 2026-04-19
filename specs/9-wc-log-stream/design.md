# 9-wc-log-stream — Design

## Architecture

`9-wc-log-stream` is a framework-agnostic Custom Element (Custom Elements v1)
written in TypeScript and bundled to an ES module. It attaches a closed
shadow root, hosts a virtualised row scroller, and consumes Server-Sent Events
or WebSocket frames from `6-live-run-view`'s relay — which in turn reads from
`5-progress-ingest`. The element is stateless across page loads: every attach
opens a fresh connection and replays from `since` if provided. All colors,
spacing, typography, and elevations resolve from `--pyc-log-stream-*` tokens
mapped onto base tokens in `9-ui-design-tokens`. Ships in **Phase 5**. Hosted
inside `9-run-detail-ui`. The bundle is served under
`/ui/components/pyc-log-stream/` as a static ES module so it can be imported by
any page (including embeddable views per `8-embeddable-views`).

## Data Model

No persistent entities. Runtime state inside the element:

- `LogRecord` — `{sequence: number, timestamp: string, level: "DEBUG"|"INFO"|"WARN"|"ERROR"|"FATAL", source: string, message: string, fields: Record<string, string>}`.
- `BufferState` — `{records: LogRecord[], firstSequence: number, lastSequence: number, droppedBefore: number}`.
- `ViewState` — `{followTail: boolean, scrollTop: number, visibleFirst: number, visibleCount: number, searchCursor: number}`.
- `ConnectionState` — `{kind: "sse"|"ws", url: string, attempt: number, backoffMs: number, status: "connecting"|"open"|"reconnecting"|"closed"}`.

Buffer is a ring buffer capped at `buffer-cap` (default 500 000 records).

## Interfaces

### Public API

**Tag name:** `<pyc-log-stream>`

**Observed attributes:**

- `run-id` (string; UUID) — the run to tail.
- `src` (`sse` | `ws`; default `sse`) — transport.
- `since` (string; integer offset or ISO timestamp) — resume marker.
- `follow-tail` (boolean attribute) — start in follow-tail mode when present.
- `buffer-cap` (string; integer) — ring-buffer capacity override.
- `level-filter` (comma-separated list of levels) — render filter.
- `aria-label` (string) — accessibility label override.
- `data-pyc-theme` (inherited from ancestor) — triggers palette swap.

**Properties (JS):**

- `runId: string`
- `records: readonly LogRecord[]` — a frozen snapshot of the ring buffer.
- `followTail: boolean`
- `status: "connecting"|"open"|"reconnecting"|"closed"`
- `search(text: string, caseSensitive?: boolean): SearchResult`
- `clearSearch(): void`
- `jumpToSequence(sequence: number): void`
- `connect(): void`
- `disconnect(): void`

**Events (bubbling, composed):**

- `pyc-log-stream-opened` — `{runId, transport, attempt}`.
- `pyc-log-stream-record` — `{record: LogRecord}` (throttled, fires once per render batch).
- `pyc-log-stream-trimmed` — `{removed, total}`.
- `pyc-log-stream-reconnecting` — `{attempt, nextDelayMs, reason}`.
- `pyc-log-stream-closed` — `{reason, finalSequence}`.
- `pyc-log-stream-search-result` — `{query, matchCount, durationMs}`.
- `pyc-log-stream-follow-changed` — `{followTail}`.

**Slots:**

- `slot="empty"` — placeholder when zero records have arrived.
- `slot="toolbar-left"` / `slot="toolbar-right"` — consumer-supplied controls.
- `slot="footer"` — consumer-supplied footer (e.g., copy link, open artifact).

**CSS custom properties respected:**

- `--pyc-log-stream-bg` → `var(--pyc-color-surface)`
- `--pyc-log-stream-fg` → `var(--pyc-color-on-surface)`
- `--pyc-log-stream-border` → `var(--pyc-color-border-subtle)`
- `--pyc-log-stream-fg-debug`, `--pyc-log-stream-fg-info`, `--pyc-log-stream-fg-warn`, `--pyc-log-stream-fg-error`, `--pyc-log-stream-fg-fatal`
- `--pyc-log-stream-font-family` → `var(--pyc-font-family-mono)`
- `--pyc-log-stream-font-size` → `var(--pyc-font-size-code)`
- `--pyc-log-stream-row-height` → `var(--pyc-space-5)`
- `--pyc-log-stream-gutter-width` → `var(--pyc-space-10)`
- `--pyc-log-stream-focus-ring` → `var(--pyc-focus-ring)`
- `--pyc-log-stream-match-bg` → `var(--pyc-color-accent-subtle)`

**A11y requirements:**

- Root has `role="log"` with `aria-live="polite"` and `aria-relevant="additions"`.
- Focusable scroller uses `tabindex="0"`; keyboard: `End` → follow-tail, `Home` → jump to oldest kept record, `/` → focus search, `n` / `N` → next / prev match, `Esc` → clear search, `PgUp` / `PgDn` → viewport scroll.
- Search input has an associated `<label>` via `aria-labelledby`.
- Visually-hidden live region (`aria-live="polite"`) announces match counts and reconnection state.
- All interactive elements honor `--pyc-log-stream-focus-ring`.

Server REST surfaces consumed (declared by `6-live-run-view` / `5-progress-ingest`):

- `GET /api/v1/runs/{run_id}/logs.stream?since=<offset>&level=<csv>` (SSE).
- `GET /api/v1/runs/{run_id}/logs.ws?since=<offset>&level=<csv>` (WebSocket).

### Internal API

Element implementation in TypeScript. Non-trivial helpers:

```typescript
class LogRingBuffer {
    private _records: LogRecord[] = []
    private _cap: number
    constructor(cap: number) { this._cap = cap }
    append(record: LogRecord): AppendResult { /* ... */ }
    trimToCap(): TrimResult { /* ... */ }
    range(startSeq: number, endSeq: number): LogRecord[] { /* ... */ }
}

class VirtualScroller {
    readonly rowHeightPx: number
    setTotalRows(count: number): void
    onScroll(scrollTop: number): VisibleWindow
    render(window: VisibleWindow): void
}

class LogStreamTransport {
    constructor(opts: TransportOptions)
    connect(): void
    disconnect(): void
    onRecord(cb: (r: LogRecord) => void): void
    onStatus(cb: (s: ConnectionState) => void): void
}
```

### Extension Surface

None declared. Extensions may register their own log viewer tag under
`WebComponentBundleExtension` (declared by the `9-wc-*` bundle registry owned
by `9-ui-design-tokens`'s sibling extension dispatcher); that is a replacement,
not an override of this element.

### Events Emitted

All events above are DOM CustomEvents, not bus events. The element posts a
single periodic beacon to `/api/v1/ui/metrics` aggregating client histograms.

### Events Consumed

From the SSE/WebSocket transport: `open`, `message`, `close`, `error`.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/webinterface/components/pyc-log-stream/`:

- `pyc-log-stream.ts` — the Custom Element class and registration.
- `log-ring-buffer.ts` — ring-buffer implementation.
- `virtual-scroller.ts` — row virtualisation.
- `log-transport.ts` — SSE + WebSocket transport with backoff.
- `ansi-parser.ts` — ANSI escape parsing to styled spans.
- `search.ts` — O(N) substring search with incremental cursor.
- `keybindings.ts` — keyboard map.
- `styles.css` — multi-line CSS file referencing `--pyc-log-stream-*` tokens.
- `index.ts` — module entry re-exporting the element.
- `tests/` — unit + property-based tests.

Bundle emitted to `/ui/components/pyc-log-stream/pyc-log-stream.js` and `styles.css`.

## Key Flows

### Flow 1 — Attach and tail from now

1. Page inserts `<pyc-log-stream run-id="..." follow-tail>`.
2. `connectedCallback` reads attributes and opens SSE to `/api/v1/runs/{id}/logs.stream`.
3. Transport dispatches `record` events; element batches per `requestAnimationFrame`.
4. Ring buffer appends; virtual scroller re-renders visible window.
5. Element emits `pyc-log-stream-record` (throttled) and `pyc-log-stream-opened`.

### Flow 2 — Resume from offset

1. Page sets `since="128421"` and `run-id="..."`.
2. Transport URL becomes `/api/v1/runs/{id}/logs.stream?since=128421`.
3. First record received has `sequence >= 128421`; buffer initializes with that offset.

### Flow 3 — Disconnect + backoff + reconnect

1. SSE `error` fires.
2. Element sets `status="reconnecting"`, emits `pyc-log-stream-reconnecting` with attempt 1, delay 250 ms (+ jitter).
3. After backoff, transport reopens; on success element emits `pyc-log-stream-opened`.
4. On five consecutive failures with non-retryable statuses (401, 403, 404) element closes, sets `data-pyc-log-stream-status="closed"`, stops retrying.

## Error Handling

- Malformed record frame: skipped, counter `pychestrate_ui_log_stream_malformed_total` incremented, debug-log'd on the browser console.
- Non-UUID `run-id`: element sets `status="closed"`, renders an empty state via the `slot="empty"`; no SemanticError thrown into the page (UI-land does not assert on host input).
- Authorization failure (401/403): element closes the stream, emits `pyc-log-stream-closed` with `reason: "forbidden"`; does NOT retry.
- Stream exceeds `buffer-cap`: oldest records trimmed, `pyc-log-stream-trimmed` event and `droppedBefore` value exposed via `records` view.
- Server-side errors are already surfaced via `6-live-run-view`; the element never bypasses REST to reach the object store.

## Security Considerations

- All HTTP is same-origin to `8-rest-api-v1` and respects the page's session cookies + CSRF header.
- `run-id` is validated as a UUID before any network request. Invalid values disable streaming.
- Log text is rendered via `textContent`; ANSI escape parsing yields a list of `{text, className}` spans, never HTML fragments.
- Search query is bound to `textContent`; no regex execution on unsanitized user input unless the caller opts into `regex: true`, in which case the regex is compiled with a 100 ms timeout watchdog.
- `navigator.sendBeacon` is only used for aggregated client metrics; the payload contains counts and run-id, never log content.

## Observability

Client-side counters and histograms aggregated and beaconed to `/api/v1/ui/metrics`:

- `pychestrate_ui_log_stream_render_duration_seconds` — histogram per batch.
- `pychestrate_ui_log_stream_tti_seconds` — histogram per mount.
- `pychestrate_ui_log_stream_reconnect_total{reason}` — counter.
- `pychestrate_ui_log_stream_trim_total` — counter.
- `pychestrate_ui_log_stream_search_duration_seconds` — histogram.
- `pychestrate_ui_log_stream_malformed_total` — counter.

Server-side ingestion of client metrics emits log events `pychestrate.ui.log_stream.opened`, `pychestrate.ui.log_stream.closed`, `pychestrate.ui.log_stream.reconnecting`, `pychestrate.ui.log_stream.trimmed`.

Trace spans (server-side at ingestion): `pychestrate.ui.log_stream.metric_ingest`.

## Open Questions

- Should ANSI 256-color and true-color sequences all be collapsed into the design-token palette, or emitted as inline `color:` (breaking the no-hard-coded-colors rule for fidelity)? Timebox: Phase 5 midpoint.
- WebSocket fallback is mandatory for embeddable views on networks that break SSE — is `6-live-run-view` going to expose a WS endpoint in Phase 5 or later? Timebox: Phase 5 kickoff.
- Server-side search (offset index over stored logs) vs client-side — threshold? Timebox: Phase 6.
