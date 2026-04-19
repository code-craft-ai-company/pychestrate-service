# 9-wc-log-stream — Requirements

## Introduction

`9-wc-log-stream` is the framework-agnostic Custom Element that live-tails a
run's log stream in the browser. It connects to `5-progress-ingest` (via
`6-live-run-view`'s SSE endpoint or a WebSocket fallback) and appends log
records into a virtualised viewport with line numbering, level-aware coloring,
search, jump-to-offset, and follow-tail. It is themed entirely through CSS
custom properties from `9-ui-design-tokens`. Ships in **Phase 5** as the first
WebComponent that ingests live data. Sits between `6-live-run-view`
(authoritative producer of log events) and `9-run-detail-ui` (primary host).
The element owns view state (scroll position, follow mode, search cursor)
ephemerally; the authoritative log record store is the `5-progress-ingest`
durable log. The element NEVER caches logs across sessions.

## Requirements

### Requirement 1: Connect and Live-Tail a Run's Log Stream

**User Story:** As an engineer watching a run, I want the log viewer to attach
to the run and append new lines as they arrive, so that I can see what is
happening without refreshing.

**Acceptance Criteria (EARS):**

1. WHEN the element receives the `run-id` attribute AND the `src` attribute `sse` or `ws` THEN the system SHALL open a stream to `/api/v1/runs/{run_id}/logs.stream` (SSE) or `/api/v1/runs/{run_id}/logs.ws` (WebSocket) within 250 ms.
2. IF the stream disconnects with a retryable error THEN the element SHALL attempt exponential-backoff reconnection with jitter (250 ms, 500 ms, 1 s, 2 s, 4 s, cap 10 s) AND SHALL emit a `pyc-log-stream-reconnecting` CustomEvent each attempt.
3. WHILE the element is in `follow-tail` mode AND new records arrive THEN the system SHALL auto-scroll the viewport so the newest record is visible.
4. WHEN the user scrolls above the bottom THEN the element SHALL exit `follow-tail` mode AND SHALL display a "jump to tail" affordance.
5. WHERE the `since` attribute is set THEN the stream subscription SHALL include a `?since=<offset>` query parameter AND the server SHALL resume from that offset.

### Requirement 2: Virtualised Rendering for Large Logs

**User Story:** As an engineer scrolling through a 500 MiB log, I want the
viewport to stay smooth, so that scrolling and searching are not blocked.

**Acceptance Criteria (EARS):**

1. WHEN the element mounts THEN it SHALL use a row-virtualised scroller that keeps at most 512 DOM nodes regardless of total record count.
2. IF the record buffer exceeds `buffer-cap` (default 500 000 records) THEN the element SHALL trim the oldest records AND emit `pyc-log-stream-trimmed` with `{removed: int, total: int}`.
3. WHILE the viewport is idle (no user input for 200 ms) THEN the element SHALL pre-render 32 records above and 32 below the visible window.
4. WHEN the user issues a search via the `search(text)` JS property THEN the element SHALL highlight matches AND SHALL report match count via `pyc-log-stream-search-result` within 50 ms for a 500 000-record buffer.

### Requirement 3: Theming via Design Tokens Only

**User Story:** As a themer, I want to re-skin the log viewer by overriding
CSS custom properties, so that I do not have to patch the element's styles.

**Acceptance Criteria (EARS):**

1. WHEN the element renders THEN every declared color, font, radius, and spacing SHALL come from a token under `--pyc-log-stream-*` which resolves to a base token under `--pyc-color-*`, `--pyc-space-*`, etc.
2. IF a consumer overrides `--pyc-log-stream-bg`, `--pyc-log-stream-fg-debug`, `--pyc-log-stream-fg-info`, `--pyc-log-stream-fg-warn`, `--pyc-log-stream-fg-error`, or `--pyc-log-stream-font-family` on a host selector THEN the element SHALL honor the override without JavaScript changes.
3. WHERE the page toggles `data-pyc-theme="dark"` THEN the element SHALL switch palette without reload or reconnection.
4. WHEN the element initializes THEN it SHALL NOT contain any hard-coded color, hex value, or absolute `px` font-size; all values resolve via `var(--pyc-*)`.

### Requirement 4: Accessibility and Keyboard Navigation

**User Story:** As a keyboard user, I want to navigate the log with keys and
screen-reader announcements, so that I can use it without a mouse.

**Acceptance Criteria (EARS):**

1. WHEN the element mounts THEN its root SHALL expose `role="log"` AND `aria-live="polite"` AND a `aria-label="Run log"` unless overridden by the `aria-label` attribute.
2. WHEN the user presses `End` THEN the element SHALL scroll to the tail AND enter follow-tail mode.
3. WHEN the user presses `/` THEN the element SHALL focus the search input.
4. WHEN the user presses `n` / `N` THEN the element SHALL jump to the next / previous search match.
5. IF a match moves the viewport THEN the element SHALL announce `"Match <k> of <n> at line <line>"` through a visually-hidden live region.

## Property-Based Test Requirements

### Property 1: Attribute Changes Produce Idempotent Renders

- **Invariant:** For any sequence of attribute changes on a mounted `<pyc-log-stream>` that returns the attribute set to a previously-seen configuration, the element's DOM inside its shadow root converges to the same structure.
- **Generator:** `hypothesis.strategies.lists(tuples(sampled_from(observed_attrs), text() | integers() | none()), min_size=1, max_size=50)` with a final reset step to a known configuration.
- **Assertion:** `snapshot(shadowRoot)` after the reset equals the reference snapshot, byte-for-byte (ignoring non-deterministic ids).
- **Sample size:** 1000 generated sequences

### Property 2: Virtualised Scroll Preserves Record Ordering

- **Invariant:** For any stream of records received in ascending sequence numbers and any user scroll trajectory, the records rendered in the visible viewport are contiguous and strictly ascending by sequence number.
- **Generator:** Synthetic stream of 1 to 100 000 records with deterministic sequence numbers, random scroll deltas in `[-2048, 2048]` pixels.
- **Assertion:** At every sampled frame, the visible row sequences form `s0 < s1 < ... < sk`.
- **Sample size:** 1000 generated cases

### Property 3: Design Token Resolution Under Override

- **Invariant:** For any override of `--pyc-log-stream-*` tokens set on the host or on `:root`, the element's computed color matches the override's resolved base token.
- **Generator:** Random token values drawn from the default light pack.
- **Assertion:** `getComputedStyle(row).color === expected_resolved_value`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Time-to-interactive of `<pyc-log-stream>` with `run-id` set and default pack p95 < 180 ms on a 2020-class laptop. Append render p95 < 4 ms per batch (up to 256 records). End-to-end log latency (producer publish → viewport row) p95 < 500 ms through the SSE path under 50 records/s.
- **NFR-2 (Security):** Subscribes only to the authenticated REST API; carries session cookies and CSRF token. `run-id` is sanitized as a UUID; non-UUID values disable streaming. Renders log text with full DOM escaping; ANSI escapes are parsed into styled spans, never injected as HTML. Element never calls `eval`, `Function(...)`, or inserts `<script>`.
- **NFR-3 (Observability):** Client metrics posted via `navigator.sendBeacon` to `/api/v1/ui/metrics`: `pychestrate_ui_log_stream_render_duration_seconds` (histogram), `pychestrate_ui_log_stream_reconnect_total{reason}` (counter), `pychestrate_ui_log_stream_trim_total` (counter), `pychestrate_ui_log_stream_search_duration_seconds` (histogram). Log events `pychestrate.ui.log_stream.opened`, `pychestrate.ui.log_stream.closed`, `pychestrate.ui.log_stream.reconnecting`, `pychestrate.ui.log_stream.trimmed`.
- **NFR-4 (Reliability):** The element SHALL continue functioning (scroll, search) when the stream is disconnected; it SHALL display a `data-pyc-log-stream-status="disconnected"` attribute so CSS can surface the state. Tab-backgrounded elements SHALL reduce reconnect cadence to once every 30 s.

## Out of Scope

- Log ingestion or storage (see `5-progress-ingest`).
- Server-side log search across runs (see a future `6-log-index` feature).
- Persistent bookmarks or annotations (future).
- Download of the full log file (see `6-artifact-browser`).

## Dependencies

- **Depends on:** `9-ui-design-tokens`, `6-live-run-view`, `5-progress-ingest`, `8-rest-api-v1`, `1-authentication`, `1-rbac`.
- **Depended on by:** `9-run-detail-ui`.
- **Extension points exposed:** None directly; consumed by `WebComponentBundleExtension` hosting (extensions may ship replacement log renderers by shipping a different tag).
