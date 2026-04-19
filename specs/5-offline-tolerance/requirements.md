# 5-offline-tolerance — Requirements

## Introduction

The `5-offline-tolerance` feature hardens Layer 5 against pod-client
disconnects. When a client's `3-client-agent-protocol` session
drops, Pychestrate cannot send cancels, cannot confirm progress,
and cannot discover whether the client's process tree is still
running the job. This feature introduces a **degraded pod state**
(so operators see reality), an inbound **buffered replay**
mechanism (so progress records and receipts the client accumulated
during the outage are re-ingested in order), and an outbound
**deferred cancel queue** (so cancels issued while the client is
offline are delivered once the session returns). It ships in
**Phase 5** per the implementation plan — it is deliberately after
the minimum-viable Phase 3 Layer 5 slice, because its behavior is
only observable under real fleet load.

## Requirements

### Requirement 1: Degraded Pod State on Client Disconnect

**User Story:** As an operator watching the fleet view, I want a
pod whose client has disconnected to show as `degraded` (not
`ready` or `offline`), so that I can distinguish transient network
hiccups from actual pod failures.

**Acceptance Criteria (EARS):**

1. WHEN `3-client-agent-protocol` observes a session drop for a
   client whose pod is `ready` THEN the system SHALL transition
   the pod to `degraded` after `degraded_threshold_seconds`
   (default 30 s) without reconnect AND emit
   `entity.pod.state_changed` with `to_state="degraded"`.
2. WHILE a pod is `degraded` the system SHALL NOT route new
   dispatches to it (`5-job-dispatch` eligibility filter honors
   the state).
3. WHEN the client reconnects THEN the system SHALL wait for
   successful reconciliation via `5-cancel-reconcile` to
   complete, then transition the pod back to `ready` AND emit
   `entity.pod.state_changed`.
4. IF the client remains disconnected longer than
   `offline_escalation_seconds` (default 600 s) THEN the
   system SHALL transition the pod to `offline` AND emit
   `entity.pod.state_changed` with reason
   `"offline_timeout"`.

### Requirement 2: Buffered Replay of Inbound Progress and Receipts

**User Story:** As a run timeline, I want progress records and
dispatch receipts the client accumulated during the outage
replayed in the exact order they were produced, so that my run
view is consistent after the hiccup with no gaps or reorderings.

**Acceptance Criteria (EARS):**

1. WHEN a client reconnects THEN the system SHALL accept an
   inbound replay stream via the existing
   `/ingest/v1/progress/<run_id>/records` and
   `.../summary` endpoints with header
   `X-Pychestrate-Replay: true` AND a strictly monotonic
   `X-Pychestrate-Replay-Seq: <int>` per batch.
2. IF a replay batch has a gap in `X-Pychestrate-Replay-Seq`
   relative to the highest seq seen since the current reconnect
   THEN the system SHALL respond `409 Conflict` with
   `{expected_seq, received_seq}` — the client retries from
   `expected_seq`.
3. WHILE a client is replaying THEN the system SHALL serialize
   replay posts for a single `run_id` via the same per-run lock
   used by live progress (no new lock class).
4. WHERE a replayed progress record has a `seq` value already
   persisted in `run_progress_record(run_id, seq)` THEN the
   system SHALL treat it as a no-op (idempotent UPSERT) — not a
   duplicate-error.
5. WHEN all queued replay batches have been acknowledged THEN
   the client SHALL send `X-Pychestrate-Replay-Complete: true`
   AND the system SHALL emit
   `pychestrate.offline.replay_completed` with `{client_id,
   run_id_set, total_records, total_summaries}`.

### Requirement 3: Outbound Cancel Queue During Offline

**User Story:** As a user who clicked cancel while the pod client
happened to be offline, I want my cancel delivered the moment the
client reconnects, so that I do not have to watch the fleet view
and re-click once connectivity returns.

**Acceptance Criteria (EARS):**

1. WHEN `5-cancel-reconcile.send_cancel_rpc` is called AND the
   client's session is not active THEN the system SHALL persist
   a `deferred_cancel` row with `{run_id, client_id, reason,
   actor, queued_at}` AND respond that the request was queued
   (not transmitted).
2. WHEN the client reconnects AND reconciliation finishes THEN
   the system SHALL drain the `deferred_cancel` rows for that
   `client_id` in `queued_at` order AND invoke
   `cancel_dispatcher.send_cancel_rpc` per row.
3. IF a queued cancel's `run_id` is already in a terminal state
   by the time the client reconnects (e.g., the run completed
   before disconnect) THEN the system SHALL drop the deferred
   cancel AND emit
   `pychestrate.offline.deferred_cancel_superseded`.
4. WHERE a pod is `offline` (past escalation) AND a new cancel
   arrives THEN the system SHALL accept it and defer it; on
   hypothetical reconnect it drains — but the UI SHALL surface
   the pending-cancel count per pod.

## Property-Based Test Requirements

### Property 1: Replay Preserves Per-Run Order and Exact Count

- **Invariant:** For any sequence of `M` progress records
  produced by the client during an outage, replayed in
  arbitrary-size batches with strictly monotonic
  `X-Pychestrate-Replay-Seq`, after replay the persisted
  `run_progress_record` rows for each `run_id` match the
  client's original order byte-for-byte (excluding
  service-assigned `received_at`) and count equals `M`.
- **Generator:** Build M records (M ∈ [0, 5000]) across 1–10
  runs on a single client; slice into k batches (k ∈ [1, 50])
  of varying sizes; randomize the order *of batches* while
  preserving per-record order within each batch; assert seq
  monotonicity at post time.
- **Assertion:** persisted order per `run_id` equals client
  original; total record count equals M; idempotent replay of
  the same batch is a no-op.
- **Sample size:** 1000 generated cases

### Property 2: Deferred Cancel FIFO is Preserved Through Reconnect

- **Invariant:** For any sequence of `K` deferred cancels queued
  for a single `client_id` during offline, after reconnect +
  reconciliation the emitted order of `ClientCancelRequest`
  transmissions matches the `queued_at` order of the
  `deferred_cancel` rows — with superseded cancels dropped.
- **Generator:** Build K cancels (K ∈ [0, 200]) across multiple
  runs; randomly mark some runs terminal before reconnect.
- **Assertion:** emitted order equals queued_at order filtered
  by non-terminal runs at drain time.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Degraded-state transition latency p99
  < 35 s end-to-end (30 s threshold + 5 s detection overhead).
  Replay drain throughput ≥ 5000 records/sec (matches live
  ingest NFR). Deferred-cancel drain p99 < 1 s per queued row
  after reconnect completes.
- **NFR-2 (Security):** Replay posts are authenticated by the
  same bearer-token check as live ingest; `client_id` must
  still match each run's receipt. `X-Pychestrate-Replay-Seq`
  must be a non-negative monotonically-increasing integer —
  non-monotonic sequences respond `400`. Deferred cancels
  inherit `1-audit-log` coverage from `5-cancel-reconcile`,
  adding a `deferred=true` flag on the audited event.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_run_offline_pods_degraded{project}` (gauge),
  `pychestrate_run_offline_pods_offline{project}` (gauge),
  `pychestrate_ingest_replay_records_total{project}` (counter),
  `pychestrate_ingest_replay_summaries_total{project}`
  (counter),
  `pychestrate_ingest_replay_gap_rejections_total{project}`
  (counter),
  `pychestrate_ingest_replay_duration_seconds{project}`
  (histogram),
  `pychestrate_run_deferred_cancels_queued{project}` (gauge),
  `pychestrate_run_deferred_cancels_drained_total{project}`
  (counter),
  `pychestrate_run_deferred_cancels_superseded_total{project}`
  (counter). Log events
  `pychestrate.offline.pod_degraded`,
  `pychestrate.offline.pod_offline`,
  `pychestrate.offline.pod_recovered`,
  `pychestrate.offline.replay_started`,
  `pychestrate.offline.replay_completed`,
  `pychestrate.offline.replay_gap`,
  `pychestrate.offline.deferred_cancel_queued`,
  `pychestrate.offline.deferred_cancel_drained`,
  `pychestrate.offline.deferred_cancel_superseded`. Trace
  spans `pychestrate.offline.replay`,
  `pychestrate.offline.drain_cancels`.
- **NFR-4 (Reliability):** Deferred cancels and replay-seq state
  survive service restart — backed by `0-persistence`. A
  `deferred_cancel` row whose client disappears permanently
  (e.g., decommissioned) SHALL be surfaced via a maintenance
  report for operator cleanup; it is never silently purged.

## Out of Scope

- Agent retry/buffer mechanics on the *client* side — the client
  agent implements its own local store; this feature defines the
  wire contract for replay and cancel queueing only.
- Client enrollment and auth — owned by `3-client-enrollment`.
- Long-term time-series analysis of degraded-pod frequency —
  owned by `7-pod-metrics`.
- Offline-initiated dispatch (running new jobs while offline) —
  explicitly unsupported; offline pods do not accept new
  dispatches until `ready`.

## Dependencies

- **Depends on:** `3-client-agent-protocol`, `3-client-registry`,
  `3-pod-lifecycle`, `5-progress-ingest` (endpoint reuse with
  replay header), `5-cancel-reconcile` (deferred cancel flush),
  `5-dispatch-receipt`, `5-run-state-machine`, `0-persistence`,
  `0-message-bus`, `1-audit-log`.
- **Depended on by:** `3-client-inventory-ui` (pod state badges),
  `6-live-run-view` (gap indication), `7-pod-metrics`,
  `8-rest-api-v1` (exposes deferred-cancel listings).
- **Extension points exposed:** None — reuses
  `progress_parser` via `5-progress-ingest` and the
  `5-cancel-reconcile` pathway. Landing this feature does not
  introduce new extension surfaces.
