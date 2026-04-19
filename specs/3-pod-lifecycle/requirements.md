# 3-pod-lifecycle — Requirements

## Introduction

Pod Lifecycle is the authoritative state machine for an Automation Pod. Every
pod — static or dynamic — moves through the states `defined -> provisioning ->
ready -> in_use -> draining -> released`, with side branches to
`client_lost` and `failed`. This feature lives in Layer 3 and lands in
Phase 2 (static side). It publishes the single bus topic
`entity.pod.state_changed` that downstream features (`5-job-dispatch`,
`3-client-inventory-ui`, `3-pod-topology-view`) subscribe to. Per the
architectural ground rules, the pod's state is derived from signals the
*client* reports — Pychestrate never probes pod members directly; state
transitions happen in response to client frames (`registered`,
`deregister_requested`, `liveness_changed`) and run-plane events
(`run.accepted`, `run.completed`).

## Requirements

### Requirement 1: A pod enters `ready` only when its client has registered it and reported all members healthy

**User Story:** As a dispatcher, I want to dispatch only to pods in `ready`,
so that I never send a job to a pod whose members are not actually online.

**Acceptance Criteria (EARS):**

1. WHEN `entity.pod.registered` is received for a pod in `state=provisioning`
   or `state=defined` THEN the system SHALL transition the pod to
   `state=ready` and emit `entity.pod.state_changed{to=ready}`.
2. IF any member in the registration report is marked unhealthy by the
   client THEN the system SHALL transition to `state=failed` and SHALL NOT
   enter `ready`.
3. WHILE the pod is in `state=ready` the system SHALL accept dispatch
   requests; IF no dispatch arrives within `idle_grace_seconds` the pod
   SHALL remain in `ready`.

### Requirement 2: Run lifecycle drives the `in_use` ↔ `ready` oscillation

**User Story:** As a run observer, I want the pod to flip to `in_use` the
moment the client accepts a dispatch and back to `ready` the moment the
run terminates, so that concurrency controls reflect reality.

**Acceptance Criteria (EARS):**

1. WHEN `entity.run.accepted{pod_id=...}` is received for a `ready` pod
   THEN the system SHALL transition to `state=in_use` with
   `in_use_since = event.timestamp`.
2. WHEN `entity.run.completed|failed|cancelled{pod_id=...}` is received
   AND no other non-terminal runs remain for the pod THEN the system
   SHALL transition back to `state=ready`.
3. WHERE the pod's concurrency attribute allows multiple simultaneous
   runs the pod SHALL remain `in_use` as long as at least one run is
   active and SHALL NOT reject additional runs while under the
   concurrency cap.

### Requirement 3: Draining blocks new dispatches and waits for in-flight runs

**User Story:** As an operator about to take a pod offline, I want to
drain it cleanly so that in-flight runs can finish and no new runs start.

**Acceptance Criteria (EARS):**

1. WHEN an admin calls `POST /api/v1/pods/{pod_id}:drain` THEN the system
   SHALL transition the pod from any pre-terminal state to
   `state=draining` and emit `entity.pod.state_changed{to=draining}`.
2. WHILE the pod is in `state=draining` the system SHALL reject any new
   dispatch targeting the pod with `PodDraining`.
3. WHEN all non-terminal runs against the pod reach a terminal state AND
   the pod is in `state=draining` THEN the system SHALL transition to
   `state=released` and emit `entity.pod.state_changed{to=released}`.
4. IF the client is `lost` at the moment drain starts THEN the system
   SHALL transition to `state=draining` and wait for reconciliation
   before releasing.

### Requirement 4: Client loss cascades into `client_lost` without data destruction

**User Story:** As a run operator, I do not want a temporary client
outage to destroy run state — I want the pod marked `client_lost` so the
dispatcher stops targeting it but runs continue as the client last
reported them.

**Acceptance Criteria (EARS):**

1. WHEN `entity.client.liveness_changed{to=lost}` is received for a pod
   in `{ready, in_use}` THEN the system SHALL transition to
   `state=client_lost` and SHALL NOT modify any run state.
2. WHEN the client recovers with an intact registration THEN the pod
   SHALL return to the state it held before the loss (`ready` or
   `in_use` depending on whether runs are still non-terminal).
3. IF the recovered registration disagrees with the pre-loss definition
   THEN the pod SHALL transition to `state=failed` for operator review.

## Property-Based Test Requirements

### Property 1: State transitions respect the declared graph

- **Invariant:** For any sequence of input events applied to a fresh
  pod, every recorded transition is present in the declared transition
  table; no "impossible" edge (e.g., `released -> in_use`) ever occurs.
- **Generator:** hypothesis strategy producing random event sequences
  drawn from the full event alphabet (`registered`, `deregistered`,
  `run.accepted`, `run.completed`, `run.failed`, `run.cancelled`,
  `liveness_changed{alive,suspect,lost}`, `drain_requested`).
- **Assertion:** every observed `(from, to)` pair exists in
  `TRANSITIONS`; the terminal state `released` is followed by no
  further transitions.
- **Sample size:** 1000 generated cases

### Property 2: Invalid transitions leave state untouched

- **Invariant:** For any event that is not valid from the current
  state, the state machine rejects the event with
  `InvalidPodTransition` and no side effects (DB state, emitted events,
  audit entries) are produced.
- **Generator:** hypothesis strategy producing `(current_state,
  event_kind)` pairs randomly, including many invalid pairs.
- **Assertion:** for rejected pairs, DB snapshot before == DB snapshot
  after; exactly one `InvalidPodTransition` raised; no
  `entity.pod.state_changed` emitted.
- **Sample size:** 1000 generated cases

### Property 3: Runs-remaining invariant during drain

- **Invariant:** For any pod in `state=draining`, the transition to
  `released` occurs if and only if `runs_remaining(pod_id) == 0`.
- **Generator:** hypothesis strategy producing pods with 0-10 active
  runs and random run-termination orderings.
- **Assertion:** at every observable intermediate state,
  `state == released` implies `runs_remaining == 0`; the moment the
  last run terminates, the very next observable state is `released`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** state transition p99 <= 25 ms from event
  ingest to `entity.pod.state_changed` publish; drain decision on
  run-termination arrival p99 <= 50 ms.
- **NFR-2 (Security):** only the owning client (via transport
  session) may submit registration-based transitions; REST transitions
  (drain, force_release) are RBAC-gated with permissions
  `pod.lifecycle.drain`, `pod.lifecycle.admin`; every admin transition
  is audit-logged.
- **NFR-3 (Observability):** metrics
  `pychestrate_pod_state_transitions_total{from,to}`,
  `pychestrate_pod_state_gauge{state}`,
  `pychestrate_pod_drain_duration_seconds`,
  `pychestrate_pod_lifecycle_invalid_transition_total{from,event}`; log
  event `pychestrate_pod_state_changed`; trace span
  `pod_lifecycle.transition`.
- **NFR-4 (Reliability):** transition persistence is
  `SERIALIZABLE`-isolation tx against the pod row; on concurrent
  transition attempt the loser retries once against the refreshed
  state; on a second collision a `pychestrate_pod_lifecycle_race`
  log event fires.

## Out of Scope

- Pod definition CRUD (see `3-pod-definitions`).
- Static pod registration wire mechanics (see `3-static-pods`).
- Dynamic pod provisioning (see `3-dynamic-pods`).
- Per-run state machine (see `5-run-state-machine`).
- Topology rendering (see `3-pod-topology-view`).

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`, `1-audit-log`,
  `1-rbac`, `3-pod-definitions`, `3-static-pods`, `3-client-registry`.
- **Depended on by:** `3-dynamic-pods`, `3-pod-topology-view`,
  `5-job-dispatch`, `5-run-state-machine`, `3-client-inventory-ui`.
- **Extension points exposed:** `event: entity.pod.state_changed`.
  See implementation-plan.md Layer 3.
