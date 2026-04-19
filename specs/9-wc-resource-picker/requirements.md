# 9-wc-resource-picker — Requirements

## Introduction

`9-wc-resource-picker` is the framework-agnostic Custom Element that lets
users pick a set of resources from `4-resource-inventory` constrained by
pool, capability, health, and availability. It queries pool summaries and
availability from `4-resource-pools` / `4-resource-health` via `8-rest-api-v1`,
presents a filterable / selectable list, and emits a selection payload that
callers translate into a checkout request through `4-checkout-checkin`. The
element never mutates reservations directly — it is a picker only. Ships in
**Phase 8** alongside `9-wc-pod-topology`. Sits between Layer 4 REST endpoints
and any page that needs to reserve resources (dispatch dialogs, dynamic-pod
materialization). The authoritative inventory lives in
`4-resource-inventory`; this element paginates and filters the derived
projection.

## Requirements

### Requirement 1: Filter Resources by Pool, Capability, Tag, and Health

**User Story:** As a job dispatcher, I want to narrow the list to resources in
the `rf-lab` pool that have `vector-sig-gen` capability and are healthy, so
that I can pick viable candidates quickly.

**Acceptance Criteria (EARS):**

1. WHEN the element receives `pool-id` AND `capabilities="<csv>"` THEN the system SHALL fetch `/api/v1/pools/{pool_id}/resources?capabilities=<csv>&health=healthy&limit=<n>&cursor=<c>` AND render the first page of results.
2. IF `tags` is set to a comma-separated tag list THEN the server query SHALL include `&tags=<csv>` AND only resources matching all tags SHALL appear.
3. WHEN the user types in the search input AND the string stabilizes for 200 ms THEN the element SHALL re-issue the query with `&search=<string>` AND replace the list without losing the current selection set.
4. WHERE `include-unhealthy` is present THEN the element SHALL drop the `&health=healthy` filter AND SHALL render unhealthy entries with a `--pyc-resource-picker-status-unhealthy-bg` badge.

### Requirement 2: Selection and Capacity Preview

**User Story:** As a user, I want to select N resources and see how that
selection interacts with the pool's concurrency caps, so that I know whether
my dispatch will succeed.

**Acceptance Criteria (EARS):**

1. WHEN the user selects or deselects a resource THEN the element SHALL update an internal `SelectionSet` AND emit `pyc-resource-picker-selection-changed` with `{resourceIds: string[], count: number, estimatedCapacity: CapacityEstimate}`.
2. IF `multiple` is absent THEN selection SHALL be single-value AND clicking a different resource SHALL replace the selection without requiring deselection.
3. WHILE the selection is non-empty THEN the element SHALL render a `slot="summary"` content area populated with a selection count and a deselect-all button.
4. WHERE `min-select` or `max-select` constraints are set THEN the element SHALL disable the confirm affordance until the selection size is in range AND SHALL emit `pyc-resource-picker-selection-invalid` on out-of-range transitions.

### Requirement 3: Live Availability and Stale-Item Guardrails

**User Story:** As a dispatcher, I want the picker to live-update availability
so I do not pick a resource that was just reserved by someone else, so that
my dispatch does not fail at checkout.

**Acceptance Criteria (EARS):**

1. WHEN the element mounts THEN it SHALL subscribe to `/api/v1/pools/{pool_id}/availability.stream` AND update each resource's availability badge within 300 ms of an event.
2. IF a selected resource becomes unavailable THEN the element SHALL mark that entry with `data-pyc-resource-picker-stale="true"` AND emit `pyc-resource-picker-stale` with `{resourceIds: string[]}`.
3. WHEN the user presses the confirm action THEN the element SHALL emit `pyc-resource-picker-confirm` with `{resourceIds, poolId, capabilities, tags, takenAt: ISO8601, selectionFingerprint: string}`; the host page SHALL present this payload to `4-checkout-checkin`.
4. IF the confirm action is attempted WHILE stale resources exist THEN the element SHALL block the event and emit `pyc-resource-picker-confirm-blocked` with `{reason: "stale"}`.

### Requirement 4: Accessibility

**User Story:** As a keyboard user, I want to navigate and select resources
with the keyboard, so that I can use this picker without a mouse.

**Acceptance Criteria (EARS):**

1. WHEN the element mounts THEN the list root SHALL expose `role="listbox"` with `aria-multiselectable` reflecting the `multiple` attribute.
2. WHEN the user presses `ArrowUp`/`ArrowDown` THEN focus SHALL move between list items.
3. WHEN the user presses `Space` or `Enter` THEN the focused item SHALL toggle selection.
4. IF a stale event fires for selected items THEN the element SHALL announce `"<n> selected resources became unavailable"` via a live region.
5. WHERE the picker is used inside a dialog THEN the element SHALL honor `autofocus` on the search input.

## Property-Based Test Requirements

### Property 1: Selection Set Is Monotonic Under Stable Input

- **Invariant:** For any sequence of select/deselect operations on a stable result set, the final `SelectionSet` equals the set computed by applying the same operations in any reordering that preserves the partial order of per-resource operations.
- **Generator:** Random sequences of select/deselect operations drawn from a fixed resource catalog.
- **Assertion:** `finalSet(seq)` equals `finalSet(any_permutation_preserving_per_resource_order(seq))`.
- **Sample size:** 1000 generated cases

### Property 2: Stale Detection Is Sound

- **Invariant:** For any stream of availability events, every resource currently in the `SelectionSet` whose latest event says `available: false` is marked stale.
- **Generator:** Random interleavings of selection and availability events.
- **Assertion:** After each event, `staleIds ⊆ selectionIds` and `staleIds` equals the set of selected resource ids whose latest availability was `false`.
- **Sample size:** 1000 generated cases

### Property 3: Idempotent Re-Render Under Attribute Reset

- **Invariant:** For any sequence of attribute changes terminating in a baseline configuration, the element's shadow-DOM snapshot equals the baseline.
- **Generator:** Random attribute-change sequences.
- **Assertion:** Snapshot equivalence.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** TTI p95 < 220 ms with cached pool summary. Search-debounced re-query p95 < 300 ms end-to-end. Availability event apply p95 < 5 ms. Scrolling through a 2 000-resource pool maintains 60 fps (element virtualises at threshold 500).
- **NFR-2 (Security):** Same-origin REST; session cookies + CSRF. Selection payload contains only ids and a fingerprint (SHA-256 of sorted ids + pool id + timestamp) — never reservation tokens. RBAC enforced server-side on `/api/v1/pools/...`.
- **NFR-3 (Observability):** Client metrics beaconed: `pychestrate_ui_resource_picker_tti_seconds` (histogram), `pychestrate_ui_resource_picker_query_duration_seconds{pool}` (histogram), `pychestrate_ui_resource_picker_selection_size` (summary), `pychestrate_ui_resource_picker_stale_total{pool}` (counter), `pychestrate_ui_resource_picker_confirm_blocked_total{reason}` (counter). Log events `pychestrate.ui.resource_picker.query`, `pychestrate.ui.resource_picker.selection_changed`, `pychestrate.ui.resource_picker.confirm_blocked`.
- **NFR-4 (Reliability):** If the availability stream disconnects the element SHALL fall back to polling every 5 s. If the pool endpoint 404s the element SHALL render `slot="pool-unavailable"`.

## Out of Scope

- Creating reservations (see `4-checkout-checkin`).
- Authoring resources or pools (see `4-resource-inventory` / `4-resource-pools`).
- Conflict-aware scheduling preview (see `4-reservation-scheduler`; a future integration may surface it here).

## Dependencies

- **Depends on:** `9-ui-design-tokens`, `4-resource-inventory`, `4-resource-pools`, `4-resource-health`, `4-checkout-checkin`, `8-rest-api-v1`, `1-authentication`, `1-rbac`.
- **Depended on by:** dispatch dialogs in `9-run-detail-ui`, dynamic-pod materialization UI, `9-admin-ui`.
- **Extension points exposed:** None directly; `ResourceKindExtension` (server-side) influences what the picker surfaces but is not consumed in this element.
