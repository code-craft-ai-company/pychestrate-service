# 9-run-detail-ui — Requirements

## Introduction

`9-run-detail-ui` is the run detail page. It composes three major WebComponents
— `9-wc-result-viewer` (testbase result tree), `9-wc-log-stream` (live log
tail), and `6-artifact-browser` (artifact file walk) — into a single page
keyed to a single run. It also surfaces run metadata (pod, client, status,
timing, dispatcher, envelope summary), action affordances (cancel, requeue
failing, open compare, mark triaged), and a contextual right-rail for a
selected result node. Ships in **Phase 5** alongside the first WebComponents
slice. Sits between Layer 5/6 REST surfaces and the Phase-5 WebComponents;
this is the canonical test-ops daily driver. Authoritative state lives in
`5-run-state-machine` and `5-shared-results-backend`; this UI is strictly a
composition.

## Requirements

### Requirement 1: Three-Pane Composition with Run Context Header

**User Story:** As a test engineer, I want to see the result tree, the live
log, and artifacts in one page with a header summarizing the run, so that I
can triage without flipping between tabs.

**Acceptance Criteria (EARS):**

1. WHEN the user navigates to `/runs/<run-id>` THEN the UI SHALL fetch `GET /api/v1/runs/{run_id}/context` AND render a header containing `{runId, project, pod, client, state, startedAt, completedAt, dispatcher, envelopeHash}`.
2. WHEN the page mounts THEN it SHALL instantiate `<pyc-result-viewer run-id="...">`, `<pyc-log-stream run-id="...">`, and `<px-artifact-browser run-id="...">` with shared `run-id` attribute.
3. WHEN the user selects a result node via `pyc-result-viewer-select` THEN the UI SHALL scroll the log stream to the corresponding time window (via `jumpToSequence` on the log element) AND filter the artifact browser path to the node's artifact subtree.
4. WHERE a run's state is `running` THEN the UI SHALL surface a cancel affordance gated by `run.cancel`.
5. WHERE a run's state is `completed` or `failed` THEN the UI SHALL surface Requeue-Failing and Open-Compare affordances gated by their respective permissions.

### Requirement 2: Artifact Renderer Dispatch

**User Story:** As an engineer, I want to preview artifacts inline using the
best renderer (log / image / PCAP / flamegraph / custom) without leaving the
page, so that I can inspect without downloading.

**Acceptance Criteria (EARS):**

1. WHEN the user clicks an artifact in `6-artifact-browser` THEN the UI SHALL receive `pyc-result-viewer-artifact-open` or the browser's own click event AND mount the selected renderer (resolved by `6-artifact-browser` through `ArtifactRendererExtension`) in the right-rail preview panel.
2. IF the renderer fails to load THEN the UI SHALL fall back to `<px-artifact-generic-download>` AND display a non-blocking banner.
3. WHILE a renderer is mounted THEN the UI SHALL honor `Esc` to close the preview AND restore focus to the trigger element.
4. WHERE the user invokes Open-in-New-Tab THEN the UI SHALL request a signed URL via `POST /api/v1/runs/{run_id}/artifacts/sign` AND open it in a new tab with `rel="noopener noreferrer"`.

### Requirement 3: Live State and Reconnection Across All Panes

**User Story:** As an engineer watching a running job, I want all three panes
to keep up with live events and reconnect cleanly after a hiccup, so that I
trust the data on screen.

**Acceptance Criteria (EARS):**

1. WHEN the run's state machine transitions THEN the UI SHALL update the header state badge within 500 ms AND emit `pyc-run-detail-state-changed` with `{from, to}`.
2. IF the log stream or results stream disconnects THEN the UI SHALL surface a single consolidated "reconnecting" banner in the header AND avoid per-pane spam.
3. WHILE any stream is reconnecting THEN the cancel affordance SHALL remain available (cancellation does not depend on streams).
4. WHEN a run reaches terminal state THEN the UI SHALL switch `<pyc-log-stream>` out of live mode, prefer the terminal results document for `<pyc-result-viewer>`, and emit `pyc-run-detail-terminal`.

### Requirement 4: Keyboard Layout and Accessibility

**User Story:** As a keyboard user, I want to move focus between panes and
use pane-specific shortcuts, so that I can triage without a mouse.

**Acceptance Criteria (EARS):**

1. WHEN the page mounts THEN three landmarks SHALL exist: `role="main"` wrapping the composition, plus each pane with `role="region"` and an accessible name.
2. WHEN the user presses `Ctrl/Cmd + 1` / `2` / `3` THEN focus SHALL move to the Result Viewer / Log Stream / Artifact Browser respectively.
3. WHEN the user presses `?` THEN a help dialog SHALL list all keybindings (global + per-pane).
4. IF a state change demands attention (e.g., run failed) THEN the UI SHALL announce it via a live region.

## Property-Based Test Requirements

### Property 1: Selection Forwarding Is Idempotent

- **Invariant:** For any sequence of result-node selections ending in a known node, the log stream's `jumpToSequence` target and the artifact browser's path equal the values computed by a pure function of the final node.
- **Generator:** Random selection sequences across a fixed run fixture.
- **Assertion:** After replay, final forwarded state equals the reference state.
- **Sample size:** 1000 generated cases

### Property 2: Stream Reconnect Banner Is Single-Voiced

- **Invariant:** For any interleaving of per-pane reconnect events, the header banner never shows more than one simultaneously; its content equals the most-severe active reconnect reason.
- **Generator:** Random sequences of pane connect/disconnect events.
- **Assertion:** Banner invariant holds at every step.
- **Sample size:** 1000 generated cases

### Property 3: Header State Matches State Machine

- **Invariant:** For any stream of run-state transitions, the header's rendered state equals the latest non-error transition applied.
- **Generator:** Random sequences of state events + spurious error events.
- **Assertion:** Header == latest valid state.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Page TTI with warm cache p95 < 600 ms including three pane mounts. Run-context fetch p95 < 150 ms. Inter-pane event forwarding p95 < 10 ms. Renderer preview mount p95 < 500 ms for cached extension bundles.
- **NFR-2 (Security):** Same-origin REST; CSRF. Every pane respects RBAC (view, logs, artifacts). Signed-URL flows bounded in TTL by server policy; UI never renders a server-provided URL as HTML. `run-id` validated as UUID.
- **NFR-3 (Observability):** Client metrics beaconed: `pychestrate_ui_run_detail_tti_seconds` (histogram), `pychestrate_ui_run_detail_pane_mount_duration_seconds{pane}` (histogram), `pychestrate_ui_run_detail_action_total{action, outcome}` (counter), `pychestrate_ui_run_detail_renderer_error_total{extension}` (counter), `pychestrate_ui_run_detail_reconnect_total{reason}` (counter). Log events `pychestrate.ui.run_detail.opened`, `pychestrate.ui.run_detail.action`, `pychestrate.ui.run_detail.terminal`, `pychestrate.ui.run_detail.reconnect`.
- **NFR-4 (Reliability):** A failed pane SHALL NOT break neighbors. Missing run (404) SHALL render a clean empty state with a link back to the project's run list.

## Out of Scope

- Cross-run comparison (see `6-compare-runs`).
- Flake classification display (see `6-flake-tracking`).
- Bug linking (see `6-triage-bug-linking`; the UI only deep-links to it).
- Run authoring / dispatch (that is a separate dispatch dialog).

## Dependencies

- **Depends on:** `9-ui-design-tokens`, `9-wc-result-viewer`, `9-wc-log-stream`, `6-artifact-browser`, `5-run-state-machine`, `5-shared-results-backend`, `5-progress-ingest`, `6-live-run-view`, `8-rest-api-v1`, `1-authentication`, `1-rbac`.
- **Depended on by:** test-ops daily triage, link targets from PR comments, `6-compare-runs` side-by-side frames.
- **Extension points exposed:** Consumes `resource: ArtifactRendererExtension` via `6-artifact-browser`.
