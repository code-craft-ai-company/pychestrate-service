# 9-wc-result-viewer — Requirements

## Introduction

`9-wc-result-viewer` is the framework-agnostic Custom Element that renders a
run's testbase result tree. It consumes the testbase contract
(`testrun_summary.json`, `testrun_results_stream.jsos`,
`testrun_results.json`) through `8-rest-api-v1` endpoints and streams JSOS
(JSON Object Stream — one JSON object per line) frames incrementally, building
an expandable tree of suites, tests, sub-tests, and steps with status badges,
duration, and per-node artifacts/links. Fully themed via CSS custom properties
from `9-ui-design-tokens`. Ships in **Phase 5** alongside `9-wc-log-stream` and
`9-run-detail-ui`. Authoritative source of truth for results is
`5-result-ingest-watcher` + `5-shared-results-backend`; this element renders
the derived projection exposed by the REST API and NEVER persists the tree.

## Requirements

### Requirement 1: Load Testbase Summary and Stream Results Incrementally

**User Story:** As an engineer opening a run, I want the result tree to appear
immediately with summary counts and then fill in detail as result events
stream in, so that I can start scanning before the run finishes.

**Acceptance Criteria (EARS):**

1. WHEN the element receives `run-id` THEN the system SHALL fetch `/api/v1/runs/{run_id}/testrun_summary.json` within 250 ms AND render the top-level counters immediately.
2. WHEN the summary resolves THEN the element SHALL open `/api/v1/runs/{run_id}/testrun_results_stream.jsos` (SSE with `text/event-stream` or newline-delimited JSON over chunked transfer) AND append each JSOS record into the tree.
3. IF the run is terminal AND `testrun_results.json` is available THEN the element SHALL prefer the complete document over the stream and SHALL NOT open the stream.
4. WHILE the stream is open AND a new record arrives THEN the element SHALL insert or update the corresponding node in `O(log N)` time relative to tree size and SHALL NOT recompute the full tree.
5. WHERE a record carries `artifact_refs` THEN the element SHALL surface each artifact as a link that triggers the `6-artifact-browser` mounting flow in the host page via a `pyc-result-viewer-artifact-open` event.

### Requirement 2: Expandable Tree with Status Badges and Filters

**User Story:** As a triager, I want to filter the tree by status
(failed/error/skipped) and expand only the failing branches, so that I can
focus on regressions without scrolling.

**Acceptance Criteria (EARS):**

1. WHEN a node is `failed` or `errored` THEN its status badge SHALL use `--pyc-result-viewer-badge-failed-bg` (or errored) tokens AND the node SHALL be auto-expanded by default.
2. IF `filter="failed,errored"` is set THEN nodes matching no status in the filter SHALL be hidden (CSS `display: none`) AND the element SHALL emit `pyc-result-viewer-filter-changed` with `{visibleCount, totalCount}`.
3. WHEN the user toggles expansion on a node THEN the element SHALL persist the expansion state keyed by node path in `sessionStorage` scoped to the `run-id`.
4. WHERE the summary reports a total, the element SHALL render a progress bar filled by `completed/total` based on `--pyc-result-viewer-progress-fg` token.

### Requirement 3: JSOS Streaming at Scale

**User Story:** As an engineer watching a 50 000-test run, I want the viewer to
stay smooth and never lock up, so that I can navigate while new records
arrive.

**Acceptance Criteria (EARS):**

1. WHEN records are appended THEN the element SHALL amortize DOM work by batching within a `requestAnimationFrame` tick, with a maximum batch size of 512 records.
2. IF the tree contains more than `virtualize-threshold` (default 5 000) visible nodes THEN the element SHALL switch to row virtualisation of the flattened outline.
3. WHILE the stream is paused (user hovers on a node for > 500 ms) THEN the element SHALL NOT re-scroll the viewport on append.
4. WHEN a malformed JSOS line is received THEN the element SHALL skip it, increment `pychestrate_ui_result_viewer_malformed_total`, AND continue streaming.

### Requirement 4: Keyboard Navigation and Accessibility

**User Story:** As a keyboard user, I want to navigate the tree with arrow
keys and have status announced by a screen reader, so that I can triage
without a mouse.

**Acceptance Criteria (EARS):**

1. WHEN the element mounts THEN its root SHALL expose `role="tree"` AND each node SHALL expose `role="treeitem"` with `aria-level`, `aria-expanded`, and `aria-selected`.
2. WHEN the user presses `ArrowDown` / `ArrowUp` THEN focus SHALL move to the next / previous visible node.
3. WHEN the user presses `ArrowRight` on a collapsed branch THEN the branch SHALL expand; pressing `ArrowLeft` on an expanded branch SHALL collapse it.
4. WHEN the user presses `Enter` on a selected node THEN the element SHALL emit `pyc-result-viewer-select` with `{path, status, nodeKind}`.
5. IF a node transitions from running to failed THEN the element SHALL announce `"Test <name> failed"` through a visually-hidden `aria-live="polite"` region.

## Property-Based Test Requirements

### Property 1: JSOS Stream Renders M Nodes in O(M) Time

- **Invariant:** For any JSOS stream of M records with unique paths and no duplicates, the cumulative DOM work performed is linear in M; specifically, total render time fits `c0 + c1 * M` with `c1 < 0.2 ms` on the benchmark machine.
- **Generator:** `hypothesis.strategies.lists(result_record_strategy(), min_size=1, max_size=100000)` with unique paths.
- **Assertion:** Measured `total_duration - c0` divided by `M` is below the threshold; regression bound is asserted.
- **Sample size:** 1000 generated cases

### Property 2: Idempotent Re-Render On Attribute Reset

- **Invariant:** For any sequence of attribute changes that ends by resetting attributes to a known baseline, the shadow DOM structure converges to the baseline snapshot.
- **Generator:** `hypothesis.strategies.lists(attribute_change_tuple, min_size=1, max_size=40)` with a final reset step.
- **Assertion:** Serialized shadow-DOM snapshot after reset equals the baseline snapshot.
- **Sample size:** 1000 generated cases

### Property 3: JSOS Parser Is Robust Under Arbitrary Byte Splits

- **Invariant:** For any JSOS payload, the parser produces the same sequence of records regardless of how the byte stream is chunked.
- **Generator:** Random chunk boundaries across a synthesized JSOS payload (1 B to 64 KiB chunks).
- **Assertion:** The record list equals the record list obtained from the whole-payload parse.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** TTI with summary resolved p95 < 250 ms. Append render p95 < 6 ms per batch. Full tree render for 50 000 records p95 < 3 s after stream close. Expansion toggle p95 < 16 ms.
- **NFR-2 (Security):** Same-origin REST; session cookies + CSRF. Node names, messages, and artifact refs are rendered via `textContent`, never as HTML. Artifact URLs are emitted as events with a path only; the host page resolves them through `6-artifact-browser` behind RBAC.
- **NFR-3 (Observability):** Client metrics (beaconed): `pychestrate_ui_result_viewer_tti_seconds` (histogram), `pychestrate_ui_result_viewer_append_duration_seconds` (histogram), `pychestrate_ui_result_viewer_stream_duration_seconds` (histogram), `pychestrate_ui_result_viewer_malformed_total` (counter), `pychestrate_ui_result_viewer_filter_total{filter}` (counter). Log events `pychestrate.ui.result_viewer.opened`, `pychestrate.ui.result_viewer.closed`, `pychestrate.ui.result_viewer.malformed`.
- **NFR-4 (Reliability):** If the stream endpoint is unreachable the element SHALL render the summary only and SHALL surface a "stream unavailable" banner via a slot. If the tree endpoint 404s (run purged) the element SHALL emit `pyc-result-viewer-run-missing` and render an empty state.

## Out of Scope

- Authoring or writing results (handled by pod clients and `5-result-ingest-watcher`).
- Cross-run comparison (see `6-compare-runs`).
- Flake classification display (see `6-flake-tracking`; that feature composes this element).
- Per-test log display (that is `9-wc-log-stream` embedded beside this element).

## Dependencies

- **Depends on:** `9-ui-design-tokens`, `5-result-ingest-watcher`, `5-shared-results-backend`, `8-rest-api-v1`, `1-authentication`, `1-rbac`.
- **Depended on by:** `9-run-detail-ui`, `6-compare-runs`, `6-flake-tracking`.
- **Extension points exposed:** None directly; per-node renderer customization is handled by `ArtifactRendererExtension` in `6-artifact-browser`.
