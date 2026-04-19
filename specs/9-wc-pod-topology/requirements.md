# 9-wc-pod-topology — Requirements

## Introduction

`9-wc-pod-topology` is the framework-agnostic Custom Element that renders the
graph of a Pod: its client, its members, and the links between them. It
consumes `3-pod-topology-view` through `8-rest-api-v1`, and delegates per-member
visual rendering to `PodMemberRendererExtension` contributions — extensions
ship their own custom elements for novel member kinds (e.g., RF instrument,
embedded board, storage array). Ships in **Phase 8** alongside
`9-wc-resource-picker` after dynamic pods land. Sits between
`3-pod-definitions` / `3-pod-lifecycle` and any page that needs pod
visualization (client inventory, run detail, dynamic-pod materialization
UI). Authoritative pod state belongs to `3-pod-lifecycle`; this element is a
render-only projection.

## Requirements

### Requirement 1: Render a Pod's Client, Members, and Links

**User Story:** As an operator, I want to see the structure of a pod at a
glance, so that I can understand which members a job will reach and through
which client.

**Acceptance Criteria (EARS):**

1. WHEN the element receives `pod-id` THEN the system SHALL fetch `/api/v1/pods/{pod_id}/topology.json` AND render the client as a central node with members positioned radially or hierarchically based on the `layout` attribute.
2. IF a member is in `degraded` or `offline` state THEN its node SHALL render with tokens `--pyc-pod-topology-member-degraded-bg` / `--pyc-pod-topology-member-offline-bg` AND the connecting link SHALL render with `--pyc-pod-topology-link-degraded`.
3. WHEN a link is of kind `ssh`, `serial`, `power`, `network`, or `control` THEN the element SHALL render the link with the token family matching the kind (`--pyc-pod-topology-link-<kind>`).
4. WHERE a member declares a capability tag THEN the element SHALL render the tag as a chip below the node's label using `--pyc-pod-topology-chip-bg`.

### Requirement 2: Dispatch to PodMemberRendererExtension For Custom Members

**User Story:** As an extension author, I want to ship a custom renderer for
my "RF Signal Generator" member kind, so that the topology view displays it
with the right icon and inline metrics.

**Acceptance Criteria (EARS):**

1. WHEN rendering a member THEN the element SHALL resolve a renderer by consulting the `PodMemberRendererExtension` registry through `/api/v1/extensions/pod_member_renderers.json` and select the first renderer whose `matches(member)` returns true in `PRECEDENCE` order.
2. IF no extension matches THEN the element SHALL use the in-tree `PxPodMemberGenericRenderer` (`<pyc-pod-member-generic>`).
3. WHERE an extension renderer declares `live-metrics: true` THEN the element SHALL subscribe to `/api/v1/pods/{pod_id}/members/{member_id}/metrics.stream` AND forward records to the renderer via the `metrics` custom attribute.
4. WHEN an extension renderer bundle fails to load THEN the element SHALL fall back to the generic renderer AND emit `pyc-pod-topology-renderer-error` with `{memberId, extensionName, reason}`.

### Requirement 3: Live State and Selection

**User Story:** As an operator, I want member state to update in real time
and want to click a member to open its detail, so that I can act on issues.

**Acceptance Criteria (EARS):**

1. WHEN a member state event arrives via `/api/v1/pods/{pod_id}/state.stream` THEN the element SHALL update the member's badge in place without re-layout.
2. WHEN the user clicks a member THEN the element SHALL emit `pyc-pod-topology-select` with `{memberId, kind, status}` AND highlight links touching that member.
3. IF the user presses `Enter` on a focused member THEN the element SHALL emit `pyc-pod-topology-navigate` with `{memberId, destination: "detail"|"logs"|"reserve"}` so the host page can route.
4. WHILE the live stream is disconnected THEN the element SHALL reflect `data-pyc-pod-topology-stream="disconnected"` so CSS can dim the canvas.

### Requirement 4: Accessibility

**User Story:** As a keyboard user, I want to walk the member list and
understand state changes via screen reader, so that I can use this view
without a mouse.

**Acceptance Criteria (EARS):**

1. WHEN the element mounts THEN the root SHALL expose `role="application"` AND a shadow `role="list"` mirror SHALL enumerate client + members in stable order.
2. WHEN the user presses `Tab` THEN focus SHALL traverse client → members in declared order.
3. WHEN a member transitions to `offline` THEN the element SHALL announce `"Member <name> offline"` through a live region.
4. WHERE `aria-label` is set THEN the element SHALL use it as the root name; otherwise the default SHALL be `"Pod topology for <pod name>"`.

## Property-Based Test Requirements

### Property 1: Layout Is Deterministic Per Pod Definition

- **Invariant:** For any topology JSON, layout coordinates are a deterministic function of the JSON — permuting the order of members in the JSON does NOT change their assigned `(x, y)`.
- **Generator:** Random pod definitions with 1..64 members; randomly shuffled `members` arrays.
- **Assertion:** For each permutation, `layout(json).byMemberId` equals the original.
- **Sample size:** 1000 generated cases

### Property 2: Renderer Dispatch Precedence Is Stable

- **Invariant:** For any set of registered `PodMemberRendererExtension` matchers, dispatch returns the renderer with the numerically-lowest `PRECEDENCE` whose `matches(member)` returns true, regardless of registration order.
- **Generator:** Random sets of 1..16 matchers with distinct `PRECEDENCE`, random registration order.
- **Assertion:** Resolved renderer matches the expected lowest-`PRECEDENCE` match for every sampled member.
- **Sample size:** 1000 generated cases

### Property 3: Live State Updates Are Idempotent

- **Invariant:** For any stream of member state events ending in known terminal states, replaying the stream yields the same final shadow-DOM snapshot.
- **Generator:** Random permutations of state events for a fixed pod.
- **Assertion:** Snapshot after replay equals the reference snapshot.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** TTI with topology cached p95 < 300 ms. Layout for 64 members p95 < 120 ms. Live state update p95 < 6 ms. Renderer bundle load for cached extension p95 < 100 ms.
- **NFR-2 (Security):** Same-origin REST; session cookies + CSRF. Extension renderer bundles served only from the registered extension namespace under `/ext/<ext-name>/bundle/...`; no cross-origin bundle loads. Member names and messages rendered via `textContent`. Navigation events carry only ids; host page enforces RBAC.
- **NFR-3 (Observability):** Client metrics beaconed: `pychestrate_ui_pod_topology_tti_seconds` (histogram), `pychestrate_ui_pod_topology_layout_duration_seconds` (histogram), `pychestrate_ui_pod_topology_state_update_total{status}` (counter), `pychestrate_ui_pod_topology_renderer_error_total{extension}` (counter), `pychestrate_ui_pod_topology_bundle_load_duration_seconds{extension}` (histogram). Log events `pychestrate.ui.pod_topology.opened`, `pychestrate.ui.pod_topology.closed`, `pychestrate.ui.pod_topology.renderer_error`.
- **NFR-4 (Reliability):** Degraded-stream connections SHALL NOT block rendering; state falls back to last-known. Renderer-bundle failure SHALL fall back to generic renderer without breaking neighbors. A renderer that throws during attach SHALL be quarantined for the lifetime of the element instance.

## Out of Scope

- Pod authoring / editing (see `3-pod-definitions`).
- Dynamic pod provisioning trigger UI (see dynamic-pods UI).
- Member detail pages (see `3-client-inventory-ui` and per-kind UIs).
- Cross-pod topology diff (future).

## Dependencies

- **Depends on:** `9-ui-design-tokens`, `3-pod-definitions`, `3-pod-topology-view`, `3-pod-lifecycle`, `8-rest-api-v1`, `E-extension-host`, `WebComponentBundleExtension` dispatcher.
- **Depended on by:** `9-run-detail-ui`, `9-admin-ui`, `3-client-inventory-ui`.
- **Extension points exposed:** Consumes `resource: PodMemberRendererExtension` contributed via `WebComponentBundleExtension`.
