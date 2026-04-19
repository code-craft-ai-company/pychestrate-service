# 9-wc-resource-picker — Design

## Architecture

`9-wc-resource-picker` is a Custom Element that queries Layer 4 REST endpoints
to present a filterable, selectable list of resources. It is a pure picker:
it emits a structured selection payload and never mutates reservations. The
element owns filter state, selection set, and availability state; the
authoritative inventory and availability live on the server. Ships in
**Phase 8**. Typically embedded inside a dialog on `9-run-detail-ui` or on
the dynamic-pod materialization page. Consumes availability SSE from
`4-resource-health`.

## Data Model

No persistent entities. Runtime state:

- `ResourceSummary` — `{resourceId: string, name: string, kind: string, poolId: string, capabilities: string[], tags: string[], health: "healthy"|"degraded"|"quarantined"|"unknown", available: boolean, reservedBy: string | null, lastHealthAt: string | null}`.
- `FilterState` — `{poolId: string, capabilities: string[], tags: string[], search: string, includeUnhealthy: boolean, page: {limit: number, cursor: string | null}}`.
- `SelectionSet` — `{ids: Set<string>, order: string[], fingerprint: string}`.
- `AvailabilityEvent` — `{resourceId, available, reservedBy, at}`.
- `CapacityEstimate` — `{selectedCount, concurrencyCap: number, remaining: number}`.

## Interfaces

### Public API

**Tag name:** `<pyc-resource-picker>`

**Observed attributes:**

- `pool-id` (string; UUID) — the pool to list from.
- `capabilities` (comma-separated list) — capability filter.
- `tags` (comma-separated list) — tag filter.
- `include-unhealthy` (boolean attribute) — include non-healthy resources.
- `multiple` (boolean attribute) — multi-select mode.
- `min-select`, `max-select` (string; integer) — selection size constraints.
- `autofocus-search` (boolean attribute) — focus search on mount.
- `aria-label` (string) — accessibility label override.

**Properties (JS):**

- `poolId: string`
- `capabilities: string[]`
- `tags: string[]`
- `selection: readonly string[]`
- `setSelection(ids: string[]): void`
- `confirm(): SelectionPayload | null`
- `reload(): void`

**Events (bubbling, composed):**

- `pyc-resource-picker-loaded` — `{poolId, totalCount}`.
- `pyc-resource-picker-selection-changed` — `{resourceIds, count, estimatedCapacity}`.
- `pyc-resource-picker-selection-invalid` — `{reason: "below-min"|"above-max"}`.
- `pyc-resource-picker-stale` — `{resourceIds}`.
- `pyc-resource-picker-confirm` — `{resourceIds, poolId, capabilities, tags, takenAt, selectionFingerprint}`.
- `pyc-resource-picker-confirm-blocked` — `{reason}`.
- `pyc-resource-picker-stream-closed` — `{reason}`.

**Slots:**

- `slot="header"` — consumer-supplied header.
- `slot="summary"` — rendered when selection is non-empty.
- `slot="pool-unavailable"` — rendered on pool 404.
- `slot="confirm-action"` — consumer-supplied confirm button; clicking it triggers the confirm flow.

**CSS custom properties respected:**

- `--pyc-resource-picker-bg` → `var(--pyc-color-surface)`
- `--pyc-resource-picker-fg` → `var(--pyc-color-on-surface)`
- `--pyc-resource-picker-row-hover` → `var(--pyc-color-hover)`
- `--pyc-resource-picker-row-selected` → `var(--pyc-color-selected)`
- `--pyc-resource-picker-status-healthy-bg`, `--pyc-resource-picker-status-degraded-bg`, `--pyc-resource-picker-status-unhealthy-bg`, `--pyc-resource-picker-status-reserved-bg`
- `--pyc-resource-picker-chip-bg` → `var(--pyc-color-neutral-subtle)`
- `--pyc-resource-picker-search-bg` → `var(--pyc-color-input-bg)`
- `--pyc-resource-picker-focus-ring` → `var(--pyc-focus-ring)`
- `--pyc-resource-picker-font-family` → `var(--pyc-font-family-ui)`

**A11y requirements:**

- List root: `role="listbox"`, `aria-multiselectable` reflecting `multiple`.
- Each item: `role="option"`, `aria-selected`, `aria-disabled` when unavailable and not overridable.
- Search input associated with a `<label>` via `aria-labelledby`.
- Keyboard: `ArrowUp`/`ArrowDown` move focus, `Space`/`Enter` toggle selection, `Home`/`End` jump, `Esc` clears current search, `/` focuses search, `Ctrl/Cmd+A` selects all visible (in multi mode), `Ctrl/Cmd+D` clears selection.
- Live region announces stale events and selection-count changes.

Server REST surfaces consumed:

- `GET /api/v1/pools/{pool_id}/summary.json`.
- `GET /api/v1/pools/{pool_id}/resources?capabilities=&tags=&search=&health=&include_unhealthy=&limit=&cursor=`.
- `GET /api/v1/pools/{pool_id}/availability.stream` (SSE).

### Internal API

```typescript
class ResourcePickerTransport {
    fetchSummary(poolId: string): Promise<PoolSummary>
    fetchResources(filter: FilterState): Promise<ResourcePage>
    openAvailabilityStream(poolId: string): StreamHandle
}

class SelectionModel {
    toggle(id: string): SelectionChange
    replace(ids: string[]): SelectionChange
    clear(): SelectionChange
    fingerprint(): string
}

class AvailabilityTracker {
    apply(event: AvailabilityEvent): void
    isStale(id: string): boolean
    staleIdsIn(ids: Set<string>): string[]
}
```

### Extension Surface

None declared in this element.

### Events Emitted

DOM CustomEvents only.

### Events Consumed

Transport-level availability events from `4-resource-health`.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/webinterface/components/pyc-resource-picker/`:

- `pyc-resource-picker.ts` — Custom Element.
- `transport/resource-transport.ts` — REST + SSE.
- `selection-model.ts`.
- `availability-tracker.ts`.
- `virtual-list.ts` — row virtualisation at threshold.
- `keybindings.ts`.
- `styles.css` — multi-line CSS referencing `--pyc-resource-picker-*` tokens.
- `tests/`.

Bundle emitted at `/ui/components/pyc-resource-picker/pyc-resource-picker.js`.

## Key Flows

### Flow 1 — Initial query and selection

1. Element reads `pool-id`, `capabilities`, `tags`.
2. Transport fetches summary and first resource page in parallel.
3. Renderer paints list with availability badges.
4. User selects items; `SelectionModel.toggle` updates the set; element emits `pyc-resource-picker-selection-changed` including a `fingerprint`.

### Flow 2 — Live availability and stale detection

1. SSE stream delivers `AvailabilityEvent`s.
2. `AvailabilityTracker.apply` updates per-resource availability.
3. Any currently selected resource whose latest availability is `false` gets `data-pyc-resource-picker-stale="true"`.
4. Element emits `pyc-resource-picker-stale` with the affected ids.

### Flow 3 — Confirm

1. User presses the confirm action (slotted button that dispatches `pyc-resource-picker-confirm-request` on the host).
2. Element computes `SelectionPayload` and validates min/max/stale.
3. If valid, element emits `pyc-resource-picker-confirm`.
4. If stale, element emits `pyc-resource-picker-confirm-blocked` with `reason: "stale"`.
5. Host page calls `/api/v1/reservations` via `4-checkout-checkin` carrying the payload.

## Error Handling

- Summary or resources 404: emit `pyc-resource-picker-stream-closed` with `reason: "not_found"`, render `slot="pool-unavailable"`.
- 401/403: render forbidden state; no retry.
- SSE disconnect: fall back to polling `/api/v1/pools/{pool_id}/availability?since=<offset>` every 5 s until reconnected.
- Search query rejected by server (422): retain previous list, expose a non-blocking inline warning with the server's message.

## Security Considerations

- Selection payload contains ids and a fingerprint only; no reservation tokens.
- `pool-id` validated as UUID; `capabilities` / `tags` sanitized as comma-separated slug-safe strings before query construction.
- `search` input capped at 128 characters and URL-encoded before dispatch.
- Selection size capped at a hard ceiling `selection-hard-cap` (default 1 000) regardless of `max-select` to prevent DoS.
- Element never caches the full resource set across page unloads.

## Observability

Client metrics beaconed:

- `pychestrate_ui_resource_picker_tti_seconds` — histogram.
- `pychestrate_ui_resource_picker_query_duration_seconds{pool}` — histogram.
- `pychestrate_ui_resource_picker_selection_size` — summary.
- `pychestrate_ui_resource_picker_stale_total{pool}` — counter.
- `pychestrate_ui_resource_picker_confirm_blocked_total{reason}` — counter.

Log events: `pychestrate.ui.resource_picker.query`, `pychestrate.ui.resource_picker.selection_changed`, `pychestrate.ui.resource_picker.stale`, `pychestrate.ui.resource_picker.confirm`, `pychestrate.ui.resource_picker.confirm_blocked`.

Trace spans (server-side at ingestion): `pychestrate.ui.resource_picker.metric_ingest`.

## Open Questions

- Should the picker show in-flight reservation timers (countdowns) fetched from `4-lease-heartbeat`? Timebox: Phase 8 exit.
- Conflict-aware preview: when the user selects resources that share conflict rules, should the picker surface the conflict before confirm? Timebox: Phase 8 midpoint.
- Server-side ranking of candidates vs pure client filtering — does the server rank by fit? Timebox: Phase 8 kickoff.
