# 5-job-dispatch — Requirements

## Introduction

The `5-job-dispatch` feature is the scheduler-to-client bridge for
Layer 5. It accepts a `JobSubmission` from `6-test-orchestration`,
`6-build-orchestration`, or `6-infra-orchestration`; selects a pod
whose client advertises the required capabilities (via
`3-client-capability-advertisement`); asks `5-job-envelope` to build
and sign the dispatch payload; and pushes the envelope over
`3-client-agent-protocol` to exactly one client. Pychestrate never
spawns the job process — the client owns that. This feature ships in
**Phase 3** and exposes the `dispatch_strategy` factory protocol so
different fairness and locality policies can be swapped per project
(FIFO default in-tree; out-of-tree extensions can register
priority-weighted, deadline-aware, or sticky-pod strategies without
forking the service).

## Requirements

### Requirement 1: Capability-Matched Pod Selection

**User Story:** As a pipeline author, I want my test job routed to a
pod that actually advertises the capabilities the job declares, so
that dispatch does not land on a pod that cannot run the job.

**Acceptance Criteria (EARS):**

1. WHEN `dispatcher.dispatch(submission)` is called AND
   `submission.required_capabilities` is a non-empty set THEN the
   system SHALL filter the candidate pod set to pods whose most
   recent `ClientCapabilityReport` contains every required
   capability with matching version predicate.
2. IF zero pods satisfy the capability filter THEN the system SHALL
   raise `NoEligiblePodError` naming every unmet capability in a
   multiline message AND record a `dispatch_queued` entry only if
   `submission.queue_if_unavailable` is true — otherwise fail fast.
3. WHILE a pod is in `3-pod-lifecycle` state `draining` or
   `maintenance` the system SHALL exclude it from the candidate set.
4. WHERE `submission.preferred_pod_id` is set AND the preferred pod
   satisfies the capability filter the system SHALL route to that
   pod unless it is over its concurrency cap; otherwise apply the
   active `dispatch_strategy`.

### Requirement 2: Strategy-Driven Selection via `dispatch_strategy`

**User Story:** As a service operator, I want to configure per-project
dispatch policy (fair-share, priority, deadline, sticky), so that my
fleet utilization matches my organization's contention policy.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers a `DispatchStrategyProtocol`
   implementation THEN the system SHALL register it under
   `factory_protocol_name = "dispatch_strategy"` with its declared
   `PRECEDENCE`.
2. WHEN `dispatcher.dispatch(submission)` resolves a strategy for a
   project THEN the system SHALL call
   `strategy.select(candidate_pods, submission, pod_load_snapshot)`
   and route to the returned `pod_id`.
3. IF a strategy returns `None` THEN the system SHALL treat the
   submission as un-dispatchable at this moment AND, when
   `queue_if_unavailable` is true, enqueue it in the in-memory
   backoff queue with exponential backoff starting at 1 s capped at
   60 s.
4. WHERE two strategies share `factory_protocol_name` with equal
   `PRECEDENCE` THEN the system SHALL raise `ConfigurationError` at
   load time naming both classes.

### Requirement 3: Signed-Envelope Handoff Over the Client Protocol

**User Story:** As a pod client author, I want every dispatch
delivered as a single signed envelope over the agent protocol, so
that my client does not have to make secondary calls to materialize
context before launching the job.

**Acceptance Criteria (EARS):**

1. WHEN a pod is selected THEN the system SHALL call
   `5-job-envelope.codec.build(dispatch_request)`, sign, persist,
   and transmit the `SignedJobEnvelope` over
   `3-client-agent-protocol.send_envelope(client_id, signed_envelope,
   timeout)`.
2. IF the client transport returns a retryable failure THEN the
   system SHALL retry via a `DispatchAspects`-provided policy
   (default: 3 attempts, exponential 500 ms → 5 s, jittered).
3. WHEN the client acknowledges receipt with a `DispatchReceipt` the
   system SHALL persist the receipt via `5-dispatch-receipt`, publish
   `entity.run.dispatched`, and transition the run's state to
   `dispatched` in `5-run-state-machine`.
4. IF acknowledgement does not arrive within `dispatch_ack_timeout`
   (default 10 s) THEN the system SHALL treat the dispatch as
   unconfirmed, mark the run `dispatch_unconfirmed`, and let
   `5-cancel-reconcile` resolve truth on the client's next heartbeat.

## Property-Based Test Requirements

### Property 1: Dispatch Never Exceeds Pod Concurrency Cap

- **Invariant:** For any sequence of K submissions arriving in any
  order against a fleet of N pods each with per-pod
  `concurrency_cap`, the total number of simultaneously in-flight
  dispatches to any given pod never exceeds that pod's cap.
- **Generator:** `hypothesis.strategies.lists(submissions())` with
  `K ∈ [1, 200]`, pod count `N ∈ [1, 10]`, cap `C ∈ [1, 8]`;
  each submission picks capabilities from a fixed universe of 6 so
  multiple pods match.
- **Assertion:** at every step, `inflight_count(pod_id) <=
  cap(pod_id)`. Stateful property test over the dispatcher
  including dispatch, acknowledge, and complete transitions.
- **Sample size:** 1000 generated cases (min 50 steps each)

### Property 2: Strategy Selection is Deterministic Given Same Snapshot

- **Invariant:** For any fixed `candidate_pods`, fixed
  `submission`, fixed `pod_load_snapshot`, and fixed strategy
  configuration, repeated calls to `strategy.select(...)` return
  the same `pod_id` (or both return `None`).
- **Generator:** Build candidate pod sets of size 1–16, random
  submissions with capability sets drawn from the universe, random
  load snapshots. Run each tuple through `select` 10 times.
- **Assertion:** every run of the same tuple produces the same
  result.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `dispatcher.dispatch` p99 < 75 ms from
  accept to envelope-transmitted, measured across the in-tree FIFO
  strategy with 1000 pods in the fleet and ≤ 16 required capabilities
  per submission. Queue drain under steady state SHALL sustain ≥ 200
  dispatches per second per service process.
- **NFR-2 (Security):** Dispatch requests MUST be authenticated as
  originating from an in-process orchestrator module;
  externally-driven dispatch flows through `8-rest-api-v1` after
  passing the `jobs:dispatch` RBAC permission. Envelopes MUST carry
  a one-shot `envelope_id`; replayed envelopes are rejected by the
  repository's unique constraint. All dispatch decisions are logged
  to `1-audit-log` including `project_id`, `job_id`, `pod_id`, and
  the strategy name that chose the pod.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_job_dispatch_requested_total{project,job_type}`,
  `pychestrate_job_dispatch_succeeded_total{project,job_type,strategy}`,
  `pychestrate_job_dispatch_failed_total{project,reason}`,
  `pychestrate_job_dispatch_latency_seconds{project,strategy}`
  (histogram),
  `pychestrate_job_dispatch_queue_depth{project}` (gauge),
  `pychestrate_job_dispatch_inflight{pod_id}` (gauge). Log events
  `pychestrate.job_dispatch.accepted`,
  `pychestrate.job_dispatch.routed`,
  `pychestrate.job_dispatch.ack_timeout`,
  `pychestrate.job_dispatch.failed`. Trace span
  `pychestrate.job_dispatch.dispatch` with attributes `project`,
  `job_type`, `pod_id`, `strategy`.
- **NFR-4 (Reliability):** A dispatch SHALL NOT be considered
  durable until the `job_envelope` row is persisted AND the
  `DispatchReceipt` row is persisted; either failure leaves the run
  in `pending` state and is retried on the next scheduler tick.
  Process crash between envelope transmit and receipt persist MUST
  be resolved by `5-cancel-reconcile` on the client's next
  heartbeat.

## Out of Scope

- Envelope schema, signing, verification — owned by
  `5-job-envelope`.
- Client-issued local run id assignment — owned by
  `5-dispatch-receipt`.
- Run lifecycle transitions past `dispatched` — owned by
  `5-run-state-machine`.
- Resource reservations for pod members — owned by Layer 4.
- Long-term queue persistence (beyond in-memory backoff queue) — a
  future concern when persistent fair-share scheduling lands.

## Dependencies

- **Depends on:** `3-client-agent-protocol`, `3-client-registry`,
  `3-client-capability-advertisement`, `3-pod-lifecycle`,
  `5-job-envelope`, `5-dispatch-receipt` (for persist order),
  `E-extension-host`, `E-factory-protocols`, `0-message-bus`,
  `0-persistence`, `1-audit-log`.
- **Depended on by:** `6-test-orchestration`, `6-build-orchestration`,
  `6-infra-orchestration`, `6-matrix-sharding` (fan-out dispatch),
  `4-reservation-scheduler` (integration path for
  resource-gated dispatch).
- **Extension points exposed:** `factory: dispatch_strategy` — see
  implementation-plan.md Layer 5 section.
