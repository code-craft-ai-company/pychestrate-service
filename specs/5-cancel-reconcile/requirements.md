# 5-cancel-reconcile — Requirements

## Introduction

The `5-cancel-reconcile` feature implements two closely related
responsibilities. First, it sends the RPC that asks a pod client to
cancel a running job — Pychestrate cannot reach into the client's
process tree; it can only *ask* the client via
`3-client-agent-protocol`. Second, on every client reconnect it
reconciles service-side beliefs about each of that client's
in-flight runs against the client's authoritative ledger, because
the client is the only authority on what its process tree is
actually doing. This feature ships in **Phase 3** alongside the
other minimum-viable Layer 5 features and is the producer of
`entity.run.reconciled` that `5-run-state-machine` consumes.

## Requirements

### Requirement 1: Cancel Is a Request, Not a Fiat

**User Story:** As a user cancelling a long-running job, I want
Pychestrate to send a cancel RPC to the pod client and only commit
the cancelled-terminal state after the client confirms the job
stopped, so that my view of the system reflects reality.

**Acceptance Criteria (EARS):**

1. WHEN `cancel_reconciler.send_cancel_rpc(run_id, reason,
   actor)` is called (typically from `5-run-state-machine` after
   `request_cancel`) THEN the system SHALL locate the run's
   current `client_id` + `client_local_run_id` via
   `5-dispatch-receipt`, send a `ClientCancelRequest` over
   `3-client-agent-protocol`, AND record a `cancel_request` row
   with `{request_id, run_id, client_id, sent_at, state:
   "sent"}`.
2. WHEN the client acknowledges with a `ClientCancelAck` THEN the
   system SHALL publish `entity.run.cancel_ack` (consumed by
   `5-run-state-machine`) AND update the `cancel_request` row to
   `state: "acked"`.
3. IF the client does not reply within
   `cancel_ack_timeout_seconds` (default 15 s) THEN the system
   SHALL retry up to `cancel_ack_retries` (default 3) with
   exponential backoff 1 s → 8 s AND, on final failure, emit
   `pychestrate.cancel.rpc_unreachable` — the run state does NOT
   auto-transition to terminal; a subsequent reconciliation will.
4. WHERE the client's next heartbeat reports the run as
   terminated THEN the system SHALL transition the run to
   `cancelled` (if the client says cancelled) or the
   client-reported terminal state (if the run completed before
   cancel landed).

### Requirement 2: Client-Authoritative Reconciliation on Reconnect

**User Story:** As a service that survived a crash and is
re-establishing contact with client agents, I want to inherit the
client's truth for every in-flight run, so that network partitions
and process restarts do not leave runs stuck in the wrong state.

**Acceptance Criteria (EARS):**

1. WHEN a client re-establishes its `3-client-agent-protocol`
   session AND reports its local run ledger (`ClientRunLedger =
   list[ClientRunEntry]`) THEN the system SHALL compare, for
   every entry, the client-reported state against
   `5-run-state-machine.get(run_id).state`.
2. WHEN the client and service agree THEN the system SHALL emit
   exactly one `pychestrate.reconcile.concur` per run (log-level
   metric) and transition nothing.
3. WHEN the client and service disagree THEN the system SHALL
   call `5-run-state-machine.reconcile(run_id,
   client_reported_state, source="client_truth")`, persist a
   `reconcile_decision` row, and emit `entity.run.reconciled`
   with `{prior_state, resolved_state, source}`.
4. IF the client reports a run the service has no knowledge of
   (e.g., orphan from a crashed service) THEN the system SHALL
   create a `needs_investigation` run record pointing at the
   client's `client_local_run_id` AND emit
   `pychestrate.reconcile.orphan_run`.
5. WHERE the service has a run marked `dispatch_unconfirmed` AND
   the client's ledger shows the run never received the envelope
   THEN the system SHALL transition the run to `dispatch_lost`
   and emit `entity.run.failed` with reason
   `"dispatch_lost_confirmed"`.

### Requirement 3: Idempotent Replay of Cancel and Reconcile

**User Story:** As the service under retry storms, I want repeated
cancel requests and reconciliation attempts to be idempotent, so
that I cannot double-transition a run or double-kill a client's
process tree.

**Acceptance Criteria (EARS):**

1. WHEN `send_cancel_rpc(run_id, ...)` is called multiple times
   for the same `run_id` while an earlier request is in
   `sent | acked | completing` THEN the system SHALL return the
   existing `cancel_request_id` and SHALL NOT transmit a second
   RPC.
2. WHEN a `ClientCancelAck` arrives for a run whose cancel has
   already been acked THEN the system SHALL update
   `received_at` but SHALL NOT emit a second
   `entity.run.cancel_ack`.
3. WHEN reconciliation runs twice over the same client ledger THEN
   the second pass SHALL result in zero new
   `reconcile_decision` rows because the first pass already
   aligned state.

## Property-Based Test Requirements

### Property 1: Reconciled State Equals Client-Reported State

- **Invariant:** For any client reconnect that presents a
  `ClientRunLedger` with entries spanning multiple service-side
  states, after reconciliation finishes,
  `state_machine.get(run_id).state ==
  client_reported_state(run_id)` for every entry OR the entry
  was flagged `orphan_run` (no service-side run existed).
- **Generator:** Build a universe of N runs (N ∈ [1, 200]) in
  random service-side states; construct a client ledger by
  assigning each entry a random state drawn from a weighted
  distribution (mostly agreeing, 20% divergent); inject 5% orphan
  entries.
- **Assertion:** after `reconcile_on_reconnect(client_id,
  ledger)`, state equality holds or orphan flag is set.
- **Sample size:** 1000 generated cases

### Property 2: Cancel RPC Is Sent At Most Once Per Cancel Lifecycle

- **Invariant:** For any sequence of K calls to
  `send_cancel_rpc(run_id, ...)` interleaved with retries, the
  total number of `ClientCancelRequest` transmissions equals
  `min(K_initial_requests, cancel_ack_retries + 1)` —
  *not* K-total.
- **Generator:** Build a cancel workflow with random
  retry-trigger signals (ack-timeout; transport error;
  duplicate request from operator).
- **Assertion:** count of transport sends ≤ retry budget per
  cancel lifecycle; a new lifecycle only starts after the prior
  is terminal (`acked_and_confirmed | timed_out | unreachable`).
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `send_cancel_rpc` p99 < 50 ms from
  call to transport hand-off. Reconciliation of a 1000-entry
  client ledger p99 < 400 ms including state-machine writes.
  Retry backoff does not contribute to this latency; only the
  initial transmission is measured.
- **NFR-2 (Security):** Cancel requests require `jobs:cancel`
  RBAC enforced at `8-rest-api-v1`; `1-audit-log` captures every
  cancel attempt. The reconciliation entry point is only callable
  by `3-client-agent-protocol`'s authenticated heartbeat
  handler — never by unauthenticated paths. Reconcile decisions
  include `client_id`, `run_id`, prior/resolved states; all
  audited.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_run_cancel_requests_total{project,result}` (counter),
  `pychestrate_run_cancel_rpc_latency_seconds{project}`
  (histogram),
  `pychestrate_run_cancel_retries_total{project}` (counter),
  `pychestrate_run_cancel_unreachable_total{project}` (counter),
  `pychestrate_run_reconcile_runs_total{outcome}` (counter — outcome
  ∈ `concur | divergent | orphan | dispatch_lost`),
  `pychestrate_run_reconcile_duration_seconds{client_id_bucket}`
  (histogram),
  `pychestrate_run_reconcile_orphans_total{project}` (counter).
  Log events `pychestrate.cancel.rpc_sent`,
  `pychestrate.cancel.ack_received`,
  `pychestrate.cancel.rpc_unreachable`,
  `pychestrate.reconcile.run_divergent`,
  `pychestrate.reconcile.orphan_run`,
  `pychestrate.reconcile.dispatch_lost_confirmed`. Trace spans
  `pychestrate.cancel.send_rpc`,
  `pychestrate.reconcile.on_reconnect`.
- **NFR-4 (Reliability):** A pending cancel request survives
  process restart — `cancel_request` rows in `sent` state are
  picked up and retried by a startup rehydrate. Reconciliation
  is eventually-consistent: a heartbeat that arrives during
  another reconciliation for the same client is serialized via a
  per-client lock; no lost updates.

## Out of Scope

- Actually killing the client's process tree — that's the pod
  client's responsibility once it receives the cancel RPC.
- Run state enumeration — owned by `5-run-state-machine`.
- Heartbeat transport — owned by `3-client-agent-protocol`.
- Buffered replay when the client is offline — owned by
  `5-offline-tolerance` (Phase 5).
- Cancellation due to resource-policy violations — that path
  originates in Layer 4 and flows through this feature as an
  ordinary cancel request.

## Dependencies

- **Depends on:** `3-client-agent-protocol`, `3-client-registry`,
  `0-persistence`, `0-message-bus`, `1-audit-log`,
  `5-dispatch-receipt` (client/local id resolution),
  `5-run-state-machine` (transition consumer),
  `5-job-dispatch` (dispatch-unconfirmed observations),
  `5-offline-tolerance` (deferred reconciliation when the
  client is offline).
- **Depended on by:** `5-run-state-machine` (cancel-ack and
  reconcile producers), `5-offline-tolerance` (reuses
  reconciliation entry point), `8-rest-api-v1` (cancel routes).
- **Extension points exposed:** None — this is a pure
  reconciliation feature.
