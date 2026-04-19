# 3-client-capability-advertisement — Requirements

## Introduction

Client Capability Advertisement is the protocol by which a client agent
reports what it can do — toolchains present, pod member kinds it owns,
max concurrency, supported languages, hardware accelerators, etc. — and
how Pychestrate stores and queries that set. It lives in Layer 3 and
ships in Phase 2. Capabilities drive dispatch: `5-job-dispatch` matches
envelopes against a client's capability report. Capability kinds are
contributed via `CapabilityKindExtension` — a different surface from
`ClientAttributeExtension` (client attributes describe what a client *is*,
capabilities describe what it *can do* under dispatch). Per the
architectural ground rules, capabilities are reported by the client and
take the client's word for it: Pychestrate never probes members to verify.

## Requirements

### Requirement 1: Clients report capabilities post-enrollment and on change

**User Story:** As a client agent, I want to advertise my toolchain inventory
and concurrency caps after I enroll, and to push an update when something
changes on disk, so that Pychestrate dispatches only jobs I can satisfy.

**Acceptance Criteria (EARS):**

1. WHEN a client has completed enrollment THEN it SHALL send a
   `CapabilityAdvertisementFrame` as its first post-enrollment message and
   Pychestrate SHALL persist the snapshot to the registry.
2. WHEN a client detects a change in its local capability inventory THEN it
   SHALL send a delta advertisement with `revision_token > previous` and
   Pychestrate SHALL apply the diff atomically.
3. IF an advertisement includes a `CapabilityKind` that is not declared by
   any loaded `CapabilityKindExtension` THEN the system SHALL reject the
   entire advertisement and emit
   `entity.client.capability_rejected{reason=unknown_kind,kind=...}`.
4. WHILE a client has no advertised capability set the dispatcher SHALL
   treat the client as ineligible for any capability-requiring envelope.

### Requirement 2: Capability values are typed and validated against the declared kind

**User Story:** As a dispatcher, I want every capability value to conform
to its kind's schema, so that my match predicates can rely on the shape
of each value without defensive coding.

**Acceptance Criteria (EARS):**

1. WHEN an advertisement carries a capability value THEN the system SHALL
   validate the value against the kind's `value_schema` and SHALL reject
   the advertisement if any value fails.
2. IF a kind declares `sensitive=true` THEN the value SHALL be stored
   encrypted at rest and SHALL NOT be returned on any non-admin read
   endpoint.
3. WHERE a kind declares `max_value_bytes` the system SHALL enforce that
   cap on the serialized value.

### Requirement 3: Capability queries support dispatch-time match

**User Story:** As `5-job-dispatch`, I want to find all clients matching a
capability predicate (e.g., `has(pytest) AND concurrency.free > 0`) in a
single query, so that dispatch decisions are sub-millisecond at the plane
boundary.

**Acceptance Criteria (EARS):**

1. WHEN `find_clients_matching(predicate)` is called THEN the system SHALL
   evaluate the predicate against current `client_capability` rows and
   return `client_id`s in registry order.
2. IF the predicate references a kind with `searchable=false` THEN the
   system SHALL raise `NonSearchableCapability`.
3. WHILE a client is `liveness_state=lost` the system SHALL exclude it
   from match results regardless of its advertised capabilities.

## Property-Based Test Requirements

### Property 1: Delta application equals full-replace with the post-delta set

- **Invariant:** For any initial capability set `C0` and any sequence of
  deltas `d1, d2, ..., dn`, applying deltas sequentially yields the same
  final set as a single full-replace of `C0 ∪ (d1 ∘ d2 ∘ ... ∘ dn)`.
- **Generator:** hypothesis strategy generating initial sets of 1-20
  capabilities plus 1-10 deltas (add / modify / remove).
- **Assertion:** `apply_deltas(C0, deltas) == full_replace(final_set)`
  (set equality across `(kind, value)` tuples).
- **Sample size:** 1000 generated cases

### Property 2: Dispatch eligibility is monotonic under liveness

- **Invariant:** For any client and any capability predicate `P`, the
  result of `find_clients_matching(P)` containing that client implies the
  client is in `liveness_state in {alive, suspect}`. A client in `lost`
  is never in the result regardless of advertised capabilities.
- **Generator:** hypothesis strategy generating random clients + random
  capability sets + random predicates, then toggling liveness.
- **Assertion:** the predicate result set is a subset of
  `{c : c.liveness_state != lost}`.
- **Sample size:** 1000 generated cases

### Property 3: Rejection on any unknown kind leaves state unchanged

- **Invariant:** For any advertisement containing at least one value of
  an unknown kind, the pre-advertisement capability set equals the
  post-advertisement set.
- **Generator:** hypothesis strategy producing advertisements with a
  random mix of known and unknown kinds (at least one unknown guaranteed).
- **Assertion:** DB snapshot before advertisement == DB snapshot after;
  exactly one `entity.client.capability_rejected` emitted.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** capability advertisement apply p99 <= 25 ms
  for up to 200 capabilities; `find_clients_matching` p99 <= 15 ms
  against a fleet of 10,000 clients with 50 avg capabilities each.
- **NFR-2 (Security):** `sensitive=true` values encrypted at rest via
  `1-secrets-vault`; admin-only REST surface for sensitive values;
  capability bodies capped at 1 MiB per advertisement; RBAC permissions
  `client.capability.read|admin`.
- **NFR-3 (Observability):** metrics
  `pychestrate_client_capability_advertisements_total{outcome}`,
  `pychestrate_client_capability_rows`,
  `pychestrate_client_capability_rejected_total{reason}`,
  `pychestrate_client_capability_match_duration_seconds`; log events
  `pychestrate_client_capability_applied`,
  `pychestrate_client_capability_rejected`; trace spans
  `client_capability.apply`, `client_capability.match`.
- **NFR-4 (Reliability):** delta application transactional; on failure
  the client is emitted an `advertisement_rejected` frame and state
  remains at the previous revision.

## Out of Scope

- Attribute storage (see `3-client-registry`).
- Dispatch matching algorithm details (see `5-job-dispatch`).
- Client inventory UI (see `3-client-inventory-ui`).
- Agent version advertisement (handled by heartbeats — see
  `3-client-agent-protocol`).

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`,
  `3-client-agent-protocol`, `3-client-enrollment`,
  `3-client-registry`, `1-secrets-vault` (for sensitive values),
  `E-extension-host`, `E-resource-extensions`.
- **Depended on by:** `5-job-dispatch`, `3-client-inventory-ui`,
  `3-agent-upgrade-channel` (for agent-side capability pinning).
- **Extension points exposed:** `resource: CapabilityKindExtension` —
  declared capability kinds (value schema, search index hints,
  sensitivity flag). See implementation-plan.md Layer 3.
