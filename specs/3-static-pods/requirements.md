# 3-static-pods — Requirements

## Introduction

Static Pods are pre-wired automation pods that a client agent registers with
Pychestrate when it comes online. Unlike dynamic pods (`3-dynamic-pods`,
Phase 8), which are materialized from a template, static pods already exist
physically — a test bench, a lab rack, a standing developer workstation —
and the client's job is simply to announce the pod's existence and bind it
to a definition (`3-pod-definitions`). This feature lives in Layer 3 and
ships in Phase 2 alongside the rest of the baseline client plane. Per the
architectural ground rules, the client is the *only* contact point — Pychestrate
trusts the client's claim about the pod's members, verifies it against the
pod definition, and records the pod as `ready` only after the client reports
a full healthy topology.

## Requirements

### Requirement 1: Client registers a static pod against an existing definition

**User Story:** As a pod client agent brought online in a lab, I want to
register my pod with the definition version I was deployed against, so that
Pychestrate recognizes my members and can dispatch to me.

**Acceptance Criteria (EARS):**

1. WHEN a client sends `StaticPodRegisterRequest{pod_definition_id, version,
   member_reports}` over the transport THEN the system SHALL look up the
   pinned version of the definition and SHALL reconcile the report against
   it before writing any row.
2. IF any member in `member_reports` is not present in the pinned definition
   THEN the system SHALL reject the registration with `MemberNotInDefinition`.
3. IF a member in the pinned definition is absent from `member_reports`
   THEN the system SHALL reject with `MissingMember` naming the absent
   members.
4. WHEN the report matches the definition THEN the system SHALL insert a
   `pod_registration` row with `state=registered` and SHALL emit
   `entity.pod.registered`.

### Requirement 2: Client deregisters the pod on shutdown or eviction

**User Story:** As a pod client being taken offline for maintenance, I want
to deregister my pod so that Pychestrate stops routing dispatches to it.

**Acceptance Criteria (EARS):**

1. WHEN a client sends `StaticPodDeregisterRequest{pod_id, reason}` THEN the
   system SHALL transition the registration to `state=deregistered`, set
   `deregistered_at`, and emit `entity.pod.deregistered{reason}`.
2. IF the pod is currently holding a run THEN the deregister SHALL succeed
   but SHALL mark all in-flight runs `reconciliation_required=true` per the
   pod-lifecycle draining rules (see `3-pod-lifecycle`).
3. WHILE deregistration is in progress the system SHALL refuse new
   dispatches with `PodNotAvailable`.

### Requirement 3: Liveness changes of the client cascade to the pod

**User Story:** As a UI operator, I want a pod to show as `lost` when its
client goes `lost`, so that the fleet view tells me where the blast radius
is.

**Acceptance Criteria (EARS):**

1. WHEN `entity.client.liveness_changed{to=lost}` is consumed for a client
   that owns a static pod registration THEN the system SHALL transition the
   pod registration to `state=client_lost` and SHALL emit
   `entity.pod.registered_client_lost` for downstream consumers.
2. WHEN the client recovers (`entity.client.liveness_changed{to=alive}`)
   and the client re-sends an unchanged `StaticPodRegisterRequest` (proving
   the topology is intact) THEN the system SHALL transition the pod
   registration back to `state=registered`.
3. WHERE the client recovers but the re-registration report differs from the
   definition the system SHALL keep the pod in `state=client_lost` until the
   discrepancy is reconciled.

## Property-Based Test Requirements

### Property 1: Registration is idempotent under duplicate report delivery

- **Invariant:** For any `StaticPodRegisterRequest` delivered `N` times
  (`N in [1, 5]`) with identical contents, the final DB state equals the
  state produced by one successful delivery, and `entity.pod.registered` is
  emitted exactly once.
- **Generator:** hypothesis strategy producing requests with random but
  definition-conforming member reports, replayed a random number of times.
- **Assertion:** number of `pod_registration` rows for `(client_id, pod_id)`
  equals 1; count of `entity.pod.registered` for that pod equals 1.
- **Sample size:** 1000 generated cases

### Property 2: Reconcile-on-recover preserves run identity

- **Invariant:** For any pod with runs `R = {r1..rk}` in
  `state != terminal` at the moment the client goes `lost`, after
  `liveness_changed{to=alive}` and an unchanged re-registration, each
  `r_i` retains its original `run_id` and its pre-loss state; no run is
  duplicated or dropped.
- **Generator:** hypothesis strategy producing random in-flight run
  counts and random outage durations.
- **Assertion:** pre/post run-id set equality; pre/post run-state equality
  for each `r_i`.
- **Sample size:** 1000 generated cases

### Property 3: Registration report validation is total against the definition

- **Invariant:** For any `(definition, report)` pair, the set of rejection
  reasons produced by the registrar equals the symmetric difference of the
  definition member-name set and the report member-name set (modulo further
  per-member validation).
- **Generator:** hypothesis strategy producing definitions with 1-20 members
  and reports with deliberate member-set perturbations (add, drop, rename).
- **Assertion:** the set of produced rejection codes matches the expected
  symmetric-difference-derived code set.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** registration p99 <= 250 ms for a definition with
  <= 32 members; deregister p99 <= 150 ms; liveness cascade applied within
  500 ms of the client's liveness transition.
- **NFR-2 (Security):** only the client whose `client_id` matches the pod
  definition's `client_binding.pod_name` (resolved via `3-client-registry`)
  may register it; cross-client hijack attempts rejected with
  `PodNotOwnedByClient`; all registrations audit-logged.
- **NFR-3 (Observability):** metrics `pychestrate_pod_registrations_total{
  outcome}`, `pychestrate_pod_state_distribution{state}`,
  `pychestrate_pod_registration_latency_seconds`; log events
  `pychestrate_pod_registered`, `pychestrate_pod_deregistered`,
  `pychestrate_pod_registration_rejected`; trace span
  `static_pod.register`.
- **NFR-4 (Reliability):** registration is transactional; on partial
  failure the partial `pod_registration` row is rolled back; duplicate
  deliveries coalesce via content hash.

## Out of Scope

- Template-driven provisioning (see `3-dynamic-pods`).
- Lifecycle state machine beyond the registered/deregistered/client_lost
  extension points (see `3-pod-lifecycle`).
- Topology UI (see `3-pod-topology-view`).
- Capability advertisement (see `3-client-capability-advertisement`).

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`,
  `3-client-agent-protocol`, `3-client-enrollment`, `3-client-registry`,
  `3-pod-definitions`, `3-pod-lifecycle`.
- **Depended on by:** `3-pod-topology-view`, `3-client-inventory-ui`,
  `5-job-dispatch`.
- **Extension points exposed:** `event: entity.pod.registered|deregistered`
  (and internal cascades `entity.pod.registered_client_lost` /
  `entity.pod.registered_client_recovered`). See implementation-plan.md
  Layer 3.
