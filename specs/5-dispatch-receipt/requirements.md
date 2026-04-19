# 5-dispatch-receipt — Requirements

## Introduction

The `5-dispatch-receipt` feature formalizes the narrow but critical
handshake between Pychestrate and a pod client: when a client accepts
a `SignedJobEnvelope`, it coins a **local run id** (unique to that
client's process) and returns it in a `DispatchReceipt`. That local
id is the *client's* authoritative identifier for the run and is
what Pychestrate uses to reconcile state on reconnect (see
`5-cancel-reconcile`). Without this receipt there is no way to
distinguish two envelopes the service believes it dispatched from
one the client actually accepted. This feature ships in **Phase 3**,
and it has no extension points — it is pure contract plumbing
shared by `5-job-dispatch`, `5-run-state-machine`,
`5-progress-ingest`, and `5-cancel-reconcile`.

## Requirements

### Requirement 1: Receipt Schema and Persistence

**User Story:** As a reconciliation subsystem, I want every dispatch
acknowledged by a typed, persisted receipt, so that I can map
service-side `run_id` to the client's local run id without guesswork
on reconnect.

**Acceptance Criteria (EARS):**

1. WHEN a pod client acknowledges a dispatch THEN the client SHALL
   transmit a `DispatchReceipt` with fields `envelope_id` (UUID,
   echoes the service's id), `run_id` (UUID, echoes the service's
   id), `client_local_run_id` (string, client-scoped unique key),
   `accepted_at` (RFC3339), `client_id` (UUID), `pod_id` (UUID),
   `client_version` (semver string), and `launch_pid` (int,
   client's own process pid that owns the job tree).
2. WHEN `receipt_service.record(attempt_id, receipt)` is called THEN
   the system SHALL persist a `dispatch_receipt` row whose
   `(client_id, client_local_run_id)` is unique.
3. IF a receipt arrives whose `envelope_id` does not match the
   attempt's stored envelope id THEN the system SHALL raise
   `SemanticError` — a client cannot acknowledge an envelope it was
   not asked to run.
4. WHERE a client retransmits the same receipt (identical
   `client_local_run_id` and `envelope_id`) THEN the system SHALL
   treat it as idempotent — the second call updates `received_at`
   but does not create a second row.

### Requirement 2: Service-Issued Correlation Contract

**User Story:** As an operator debugging a missing run, I want a
bidirectional mapping between service `run_id` and
`client_local_run_id`, so that I can grep the client's local logs
using the id I see in the Pychestrate UI.

**Acceptance Criteria (EARS):**

1. WHEN a receipt is persisted THEN the system SHALL index the row
   on both `(run_id)` and `(client_id, client_local_run_id)`.
2. WHEN `receipt_service.lookup_by_local(client_id,
   client_local_run_id)` is called THEN the system SHALL return the
   matching `DispatchReceipt` AND its corresponding service
   `run_id`.
3. WHEN `receipt_service.lookup_by_run(run_id)` is called THEN the
   system SHALL return the single persisted receipt for that run
   OR raise `ReceiptNotFoundError`.
4. WHERE a run is redispatched (second envelope for the same
   `run_id` — forbidden in the current model) THEN the system SHALL
   reject the new receipt with `DuplicateRunReceiptError`.

### Requirement 3: Receipt Arrival SLA and Failure Signaling

**User Story:** As the dispatcher, I want a clear signal when a
receipt fails to arrive in time, so that I can mark the run as
`dispatch_unconfirmed` and defer to `5-cancel-reconcile`.

**Acceptance Criteria (EARS):**

1. WHEN `5-job-dispatch` registers an expected receipt for
   `attempt_id` with `deadline_at = now + dispatch_ack_timeout` THEN
   the system SHALL arm a timer that emits
   `pychestrate.dispatch_receipt.expected_timeout` with
   `{attempt_id, run_id}` on the bus when the deadline passes
   without a receipt.
2. IF a receipt arrives after `deadline_at` THEN the system SHALL
   still persist the receipt, emit
   `pychestrate.dispatch_receipt.late_arrival`, and let
   `5-cancel-reconcile` resolve which truth wins.
3. WHILE a receipt is pending (not yet persisted) the system SHALL
   count it in the `pychestrate_job_dispatch_pending_receipts` gauge
   per project.

## Property-Based Test Requirements

### Property 1: Client-Local Id Mapping is a Bijection

- **Invariant:** For any set of distinct `client_local_run_id`
  values on a single `client_id`, the mapping
  `(client_id, client_local_run_id) → run_id` is a bijection —
  no two distinct client-local ids map to the same service run, and
  no two runs share a `(client_id, client_local_run_id)` pair.
- **Generator:** `hypothesis.strategies.lists(tuples(client_id,
  client_local_run_id), min_size=0, max_size=500, unique=True)`,
  choosing `client_id` from a pool of 16. Drive the receipt
  service with the generated sequence (each paired with a fresh
  `run_id`/`envelope_id`).
- **Assertion:** after all receipts are recorded,
  `lookup_by_local(client_id, client_local_run_id)` and
  `lookup_by_run(run_id)` are mutual inverses for every recorded
  pair.
- **Sample size:** 1000 generated cases

### Property 2: Idempotent Replay Preserves Count and Updates Timestamp

- **Invariant:** For any `DispatchReceipt r` and any k ≥ 1 repeated
  calls to `record(attempt_id, r)`, the stored row count for that
  `(client_id, client_local_run_id)` is exactly 1 after every call;
  `received_at` is non-decreasing across calls.
- **Generator:** Build a receipt, then replay it k times where
  `k ∈ [1, 50]` with monotonically increasing wall clocks between
  calls.
- **Assertion:** row count stays 1; stored `received_at` equals the
  latest call's timestamp.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `receipt_service.record` p99 < 15 ms
  (Postgres INSERT … ON CONFLICT).
  `receipt_service.lookup_by_local` p99 < 5 ms.
  `receipt_service.lookup_by_run` p99 < 5 ms. Receipt timer arming
  costs O(log n) with n inflight attempts.
- **NFR-2 (Security):** Receipts are accepted only on the
  authenticated `3-client-agent-protocol` connection that owns the
  dispatch. Receipts from a different `client_id` than the one the
  envelope was addressed to are rejected with `SemanticError`.
  `DispatchReceipt.__repr__` does not emit `launch_pid` or client
  machine hostnames to logs by default (privacy of client runtime
  topology).
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_job_dispatch_pending_receipts{project}` (gauge),
  `pychestrate_job_dispatch_receipts_recorded_total{project}`
  (counter),
  `pychestrate_job_dispatch_receipts_late_total{project}` (counter),
  `pychestrate_job_dispatch_receipt_record_latency_seconds` (histogram).
  Log events `pychestrate.dispatch_receipt.recorded`,
  `pychestrate.dispatch_receipt.late_arrival`,
  `pychestrate.dispatch_receipt.expected_timeout`,
  `pychestrate.dispatch_receipt.duplicate_rejected`. Trace span
  `pychestrate.dispatch_receipt.record`.
- **NFR-4 (Reliability):** Timer arming uses a single backing store
  (in-memory wheel at M1, migrated to a Postgres-backed scheduler at
  M3) so a process restart does not drop pending-receipt timers for
  attempts still awaiting receipts.

## Out of Scope

- Choosing or computing the `client_local_run_id` — that is a
  client-agent concern (typically `<client-process-id>-<counter>`).
- State machine transitions — owned by `5-run-state-machine`.
- Reconciling divergent truth on reconnect — owned by
  `5-cancel-reconcile`.
- Archive retention of receipts beyond a single run's lifetime —
  retention rules live in `2-retention-policies`.

## Dependencies

- **Depends on:** `5-job-dispatch` (arms the timer,
  supplies `attempt_id`), `3-client-agent-protocol` (transport),
  `3-client-registry` (`client_id` validation), `0-persistence`,
  `0-message-bus`.
- **Depended on by:** `5-run-state-machine`, `5-progress-ingest`,
  `5-cancel-reconcile`, `5-offline-tolerance`.
- **Extension points exposed:** None — pure contract feature.
