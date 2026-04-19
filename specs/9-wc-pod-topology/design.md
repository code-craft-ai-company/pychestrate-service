# 9-wc-pod-topology — Design

## Architecture

`9-wc-pod-topology` is a Custom Element that renders a pod's client + members
+ links graph. Layout is a hybrid radial/hierarchical computation keyed
deterministically on the sorted `member_id` sequence; the client node is the
center (radial) or root (hierarchical). Each member's visual representation is
delegated to a `PodMemberRendererExtension` — the element looks up a custom
tag name and lazy-loads the bundle from the extension's namespaced static
path, instantiates the renderer as a child custom element, and forwards member
data. Ships in **Phase 8**. Hosted in `9-run-detail-ui`, `9-admin-ui`, and
`3-client-inventory-ui`. Authoritative pod state lives in `3-pod-lifecycle`;
this element is a derived projection.

## Data Model

No persistent entities. Runtime state:

- `PodTopology` — `{podId: string, podName: string, clientId: string, clientName: string, members: PodMember[], links: PodLink[]}`.
- `PodMember` — `{memberId: string, kind: string, name: string, status: MemberStatus, capabilities: string[], metadata: Record<string, string>}`.
- `PodLink` — `{fromId: string, toId: string, kind: "ssh"|"serial"|"power"|"network"|"control"|"other", healthy: boolean}`.
- `RendererRecord` — `{extensionName: string, componentTag: string, bundleUrl: string, precedence: number, matchFn: MatchSpec, liveMetrics: boolean}`.
- `LayoutNode` — `{nodeId, x, y, width, height}`.
- `Layout` — `{nodes: LayoutNode[], edges: LayoutEdge[], width, height}`.

## Interfaces

### Public API

**Tag name:** `<pyc-pod-topology>`

**Observed attributes:**

- `pod-id` (string; UUID) — the pod to render.
- `layout` (`radial` | `hierarchical`; default `radial`).
- `stream` (`sse` | `ws` | `off`; default `sse`).
- `metrics` (`on` | `off`; default `on`) — gate live metrics subscription to renderers that opt in.
- `aria-label` (string) — accessibility label override.

**Properties (JS):**

- `podId: string`
- `topology: PodTopology | null`
- `layout: Layout | null`
- `getMember(memberId: string): PodMember | null`
- `highlightLinks(memberId: string): void`
- `reload(): void`

**Events (bubbling, composed):**

- `pyc-pod-topology-loaded` — `{podId, memberCount, linkCount}`.
- `pyc-pod-topology-select` — `{memberId, kind, status}`.
- `pyc-pod-topology-navigate` — `{memberId, destination}`.
- `pyc-pod-topology-state-update` — `{memberId, prevStatus, status}` (throttled per batch).
- `pyc-pod-topology-renderer-error` — `{memberId, extensionName, reason}`.
- `pyc-pod-topology-stream-closed` — `{reason}`.

**Slots:**

- `slot="toolbar"` — consumer-supplied controls.
- `slot="legend"`.
- `slot="pod-unavailable"` — rendered when the topology endpoint fails.

**CSS custom properties respected:**

- `--pyc-pod-topology-bg` → `var(--pyc-color-surface)`
- `--pyc-pod-topology-fg` → `var(--pyc-color-on-surface)`
- `--pyc-pod-topology-client-bg` → `var(--pyc-color-surface-elevated)`
- `--pyc-pod-topology-member-online-bg`, `--pyc-pod-topology-member-degraded-bg`, `--pyc-pod-topology-member-offline-bg`, `--pyc-pod-topology-member-reserved-bg`
- `--pyc-pod-topology-link-ssh`, `--pyc-pod-topology-link-serial`, `--pyc-pod-topology-link-power`, `--pyc-pod-topology-link-network`, `--pyc-pod-topology-link-control`, `--pyc-pod-topology-link-degraded`
- `--pyc-pod-topology-chip-bg` → `var(--pyc-color-neutral-subtle)`
- `--pyc-pod-topology-chip-fg` → `var(--pyc-color-on-neutral-subtle)`
- `--pyc-pod-topology-focus-ring` → `var(--pyc-focus-ring)`
- `--pyc-pod-topology-font-family` → `var(--pyc-font-family-ui)`

**A11y requirements:**

- Root: `role="application"` with accessible name.
- Shadow `role="list"` mirror enumerates client + members in declared order for screen readers.
- Each member node: `role="button"`, `tabindex="0"`, `aria-label="<kind> <name> — <status>"`, `aria-current="step"` when selected.
- Keyboard: `Tab` traverses, `ArrowLeft`/`ArrowRight` moves focus around the client's members in the layout's stable order, `Enter` selects, `Space` toggles capability-chip expansion, `Esc` clears selection.
- Live region announces state transitions.

Server REST surfaces consumed:

- `GET /api/v1/pods/{pod_id}/topology.json`.
- `GET /api/v1/pods/{pod_id}/state.stream` (SSE).
- `GET /api/v1/extensions/pod_member_renderers.json` — registry projection for renderer dispatch.
- `GET /api/v1/pods/{pod_id}/members/{member_id}/metrics.stream` — for renderers opting into live metrics.

### Internal API

```typescript
class PodTopologyTransport {
    fetchTopology(podId: string): Promise<PodTopology>
    openStateStream(podId: string, mode: StreamMode): StreamHandle
}

class PodMemberRendererRegistry {
    load(): Promise<RendererRecord[]>
    resolve(member: PodMember): RendererRecord
}

class PodLayout {
    compute(topology: PodTopology, kind: "radial" | "hierarchical"): Layout
}

class MemberMountController {
    mount(member: PodMember, renderer: RendererRecord, mountPoint: HTMLElement): Promise<void>
    unmount(memberId: string): void
}
```

### Extension Surface

Server-side `PodMemberRendererExtension` (declared by `3-pod-topology-view`)
is consumed here through a registry JSON feed. Each record provides:

```typescript
interface PodMemberRendererRecord {
    extensionName: string
    componentTag: string       // custom element tag
    bundleUrl: string          // served under /ext/<ext-name>/bundle/...
    precedence: number
    match: MatcherSpec         // e.g., { memberKind: "rf-siggen" } or { capability: "rf.vector" }
    liveMetrics: boolean
}
```

In-tree reference renderers served alongside `9-ui-design-tokens`'s static
dispatcher under `source/site/automojo/pychestrate/webservice/webinterface/components/`:

- `<pyc-pod-member-generic>` — default fallback.
- `<pyc-pod-member-linux-host>` — Linux host, inline load badge.
- `<pyc-pod-member-serial-console>` — serial-port member.

### Events Emitted

DOM CustomEvents only.

### Events Consumed

Transport-level events from fetch + SSE/WebSocket streams.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/webinterface/components/pyc-pod-topology/`:

- `pyc-pod-topology.ts` — Custom Element.
- `layout/radial.ts` — deterministic radial layout.
- `layout/hierarchical.ts` — deterministic hierarchical layout.
- `transport/topology-transport.ts` — fetch + stream.
- `renderer/registry.ts` — `PodMemberRendererRegistry` with bundle loader.
- `renderer/generic.ts` — `<pyc-pod-member-generic>` fallback.
- `renderer/mount.ts` — `MemberMountController`.
- `keybindings.ts`.
- `styles.css` — multi-line CSS referencing `--pyc-pod-topology-*` tokens.
- `tests/`.

In-tree reference member renderers under
`source/site/automojo/pychestrate/webservice/webinterface/components/pyc-pod-member-linux-host/` etc.

Bundle emitted at `/ui/components/pyc-pod-topology/pyc-pod-topology.js`.

## Key Flows

### Flow 1 — Open a pod topology

1. Element reads `pod-id`.
2. Transport fetches `topology.json` and the renderer registry in parallel.
3. Layout is computed deterministically.
4. For each member, registry resolves the best renderer; bundle is dynamically imported from the extension namespace.
5. Member mount point swaps in the renderer custom element instance with attributes `member-id`, `member-kind`, `member-name`, `status`, `metadata`.
6. Element emits `pyc-pod-topology-loaded`.

### Flow 2 — Member state update

1. SSE event `{memberId, status}` arrives.
2. Element updates `statusByMemberId` in place; forwards the `status` attribute to the mounted renderer.
3. No re-layout; link colors update via status-driven token.
4. Element emits `pyc-pod-topology-state-update`.

### Flow 3 — Renderer bundle failure

1. `import('/ext/acme-rf/bundle/pyc-member-rf-siggen.js')` rejects.
2. `MemberMountController.mount` catches and mounts `<pyc-pod-member-generic>` instead.
3. Element emits `pyc-pod-topology-renderer-error`.
4. Subsequent matches for the failing extension within this element instance short-circuit to generic (quarantine for the instance lifetime).

## Error Handling

- `topology.json` 404: emit `pyc-pod-topology-stream-closed` with `reason: "not_found"`, render `slot="pod-unavailable"`.
- 401/403: render forbidden state; no retry.
- Renderer registry fetch failure: use only in-tree renderers.
- SSE disconnect: reflect `data-pyc-pod-topology-stream="disconnected"`; reconnect with backoff.
- Malformed state event: skip, increment counter.
- A renderer that throws during `connectedCallback`: caught, element swaps to generic, extension quarantined within the instance.

## Security Considerations

- Same-origin REST.
- Extension bundles only loaded from `/ext/<ext-name>/bundle/...` paths registered by `E-extension-host`; no arbitrary URL accepted.
- Member metadata rendered via `textContent`; `slot`-based extensions are Custom Elements (no raw HTML injection from server payloads).
- Navigation events carry only ids; host page enforces RBAC before routing.
- `pod-id` validated as UUID.

## Observability

Client metrics beaconed:

- `pychestrate_ui_pod_topology_tti_seconds` — histogram.
- `pychestrate_ui_pod_topology_layout_duration_seconds` — histogram.
- `pychestrate_ui_pod_topology_state_update_total{status}` — counter.
- `pychestrate_ui_pod_topology_renderer_error_total{extension}` — counter.
- `pychestrate_ui_pod_topology_bundle_load_duration_seconds{extension}` — histogram.

Log events: `pychestrate.ui.pod_topology.opened`, `pychestrate.ui.pod_topology.closed`, `pychestrate.ui.pod_topology.renderer_error`.

Trace spans (server-side at ingestion): `pychestrate.ui.pod_topology.metric_ingest`, `pychestrate.ui.pod_topology.renderer_bundle_serve` (served by the extension bundle dispatcher).

## Open Questions

- Should live metrics streams be multiplexed over a single WebSocket per pod rather than one per member? Timebox: Phase 8 midpoint.
- Renderer capability negotiation (e.g., renderer requires WebGL) vs graceful degradation? Timebox: Phase 8 exit.
- Hierarchical layout edge-routing: orthogonal vs straight? Timebox: Phase 8 kickoff.
