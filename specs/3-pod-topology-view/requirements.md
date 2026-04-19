# 3-pod-topology-view — Requirements

## Introduction

The Pod Topology View renders the live graph of a pod's members and links — a
visual representation of what the client last reported, overlaid with
lifecycle state and capability hints. It lives in Layer 3 and ships in
Phase 2 as a minimal read-only REST backing (the `9-wc-pod-topology`
WebComponent in Phase 8 consumes it). The data feed is derived: this feature
composes a single `TopologyGraph` DTO from `3-pod-definitions` (the declared
spec), `3-static-pods`/`3-dynamic-pods` (the live registration report), and
`3-pod-lifecycle` (the current state). Custom member kinds contributed via
`PodMemberKindExtension` may register a `PodMemberRendererExtension` to
supply a WebComponent tag and icon metadata so unfamiliar member kinds
render meaningfully. Per the architectural ground rules, the view never
probes members directly — it only reads already-persisted state from the
sibling features.

## Requirements

### Requirement 1: The topology endpoint returns a consistent composed view

**User Story:** As a UI engineer, I want one endpoint that returns the
definition, live report, lifecycle state, and renderer hints for a pod in
one trip, so that the UI never has to reconcile three separate calls.

**Acceptance Criteria (EARS):**

1. WHEN `GET /api/v1/projects/{project_id}/pods/{pod_id}/topology` is
   called THEN the system SHALL return a `TopologyGraph` containing
   `definition_version`, `members`, `links`, `registration_report_hash`,
   `lifecycle_state`, and a `renderer_hints` map keyed by member kind.
2. IF the pod has no active registration THEN the response SHALL include
   `lifecycle_state` and the declared members only; each member's
   `report_status` SHALL be `unreported`.
3. WHERE a live registration disagrees with the definition (e.g., an
   extra member not in the spec) THEN the system SHALL annotate the
   offending member with `divergence=true` and include a `divergence_reason`.

### Requirement 2: Renderer hints are contributed by extensions

**User Story:** As an extension author shipping a new member kind, I
want to ship a WebComponent tag name and an icon ref alongside my
`PodMemberKindExtension`, so that the UI renders my kind without Pychestrate
code changes.

**Acceptance Criteria (EARS):**

1. WHEN a `PodMemberRendererExtension` declares `member_kind_name` that
   matches a loaded `PodMemberKindExtension` THEN the topology endpoint
   SHALL populate `renderer_hints[member_kind_name] = {tag, icon_ref,
   bundle_url}`.
2. IF no renderer is registered for a kind THEN the system SHALL emit a
   default hint pointing to the built-in `<pcx-generic-member>` component
   and SHALL NOT raise an error.
3. WHEN two renderer extensions are loaded for the same kind THEN the
   lower `PRECEDENCE` value SHALL win and the other SHALL be ignored
   (with a warning-level log event).

### Requirement 3: The view reflects live state within a bounded freshness window

**User Story:** As an operator watching a pod's topology during a
registration flap, I want the graph to show the current state rather than
a stale cached copy, so that I can trust what I see during debugging.

**Acceptance Criteria (EARS):**

1. WHEN `entity.pod.state_changed` fires for a pod THEN any topology read
   issued more than `topology_read_freshness_seconds` later SHALL reflect
   the new state.
2. WHILE the endpoint is cached at the edge the system SHALL set
   `Cache-Control: private, max-age=<freshness>` and SHALL set
   `ETag: <definition_version>:<registration_report_hash>:<lifecycle_state>`.
3. IF the `If-None-Match` header matches the current ETag THEN the
   system SHALL respond HTTP 304 with no body.

## Property-Based Test Requirements

### Property 1: Topology composition is pure relative to its inputs

- **Invariant:** For any `(definition_version, registration_report,
  lifecycle_state, renderer_set)` tuple, repeated calls to
  `compose_topology` produce byte-identical DTOs.
- **Generator:** hypothesis strategy producing random-but-consistent
  tuples across the five inputs (definitions 1-20 members, reports with
  0%-20% divergence, random `PodState`, random renderer map).
- **Assertion:** `canonical_json(compose(t)) == canonical_json(compose(t))`
  for any input tuple `t`.
- **Sample size:** 1000 generated cases

### Property 2: ETag collapses equivalent inputs

- **Invariant:** For any two input tuples `t1, t2` with equal
  `(definition_version, registration_report_hash, lifecycle_state)`,
  `etag(t1) == etag(t2)`. Conversely, any of those three fields
  differing yields a different ETag.
- **Generator:** hypothesis strategy randomly perturbing exactly one of
  the three key fields at a time and measuring ETag equality.
- **Assertion:** perturbation of any key field produces inequality;
  no-perturbation produces equality.
- **Sample size:** 1000 generated cases

### Property 3: Divergence marking is symmetric

- **Invariant:** For any (definition members set `D`, report members set
  `R`), the set of members marked `divergence=true` equals the symmetric
  difference `D Δ R`.
- **Generator:** hypothesis strategy producing `(D, R)` pairs with
  arbitrary overlap and member names.
- **Assertion:** `{m.name for m in topology.members if m.divergence} ==
  symmetric_difference(D, R)`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** topology endpoint p99 <= 75 ms for pods with
  <= 64 members + 128 links on a warm cache; <= 200 ms cold.
- **NFR-2 (Security):** RBAC permission `pod.topology.read`; the
  endpoint filters members whose `tags` include `confidential` unless
  the caller holds `pod.topology.read.confidential`; renderer bundle URLs
  are served through a namespaced static path that does not expose the
  extension package's filesystem layout.
- **NFR-3 (Observability):** metrics
  `pychestrate_pod_topology_reads_total{outcome}`,
  `pychestrate_pod_topology_divergence_total`,
  `pychestrate_pod_topology_latency_seconds`; log events
  `pychestrate_pod_topology_read`,
  `pychestrate_pod_topology_renderer_conflict`; trace span
  `pod_topology.compose`.
- **NFR-4 (Reliability):** the endpoint degrades gracefully: if the
  registration row is unavailable (DB hiccup) the response still
  includes the definition and lifecycle state with a `partial=true`
  flag.

## Out of Scope

- The WebComponent itself (`9-wc-pod-topology`, Phase 8).
- Streaming updates (future feature — Phase 9 live dashboards).
- Write actions on the topology (drain, force_release are in
  `3-pod-lifecycle`).

## Dependencies

- **Depends on:** `3-pod-definitions`, `3-static-pods`,
  `3-dynamic-pods`, `3-pod-lifecycle`, `1-rbac`, `E-extension-host`,
  `E-resource-extensions`.
- **Depended on by:** `9-wc-pod-topology`, `3-client-inventory-ui`,
  `9-run-detail-ui` (sidebar).
- **Extension points exposed:** `resource: PodMemberRendererExtension` —
  UI-side WebComponent tag + icon reference per member kind. See
  implementation-plan.md Layer 3.
