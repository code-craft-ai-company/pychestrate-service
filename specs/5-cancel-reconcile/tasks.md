# 5-cancel-reconcile — Tasks

## Milestones

- **M1 — Skeleton:** `cancel_request` table, `CancelDispatcher`
  with single-shot transmit, state-machine integration for
  `request_cancel` → transmit, basic reconcile pass over a
  heartbeat ledger.
- **M2 — Core Behavior:** Retry + backoff for cancel acks,
  rehydrate-on-startup, reconciliation with `concur /
  divergent / orphan / dispatch_lost_confirmed` outcomes,
  per-client reconcile lock, paginated ledgers.
- **M3 — Hardening:** Property tests, perf validation,
  dashboards, alert on divergence-rate drift, audit-log
  subscribers, chaos tests for cancel storms.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `jobs/cancel/` and `jobs/reconcile/` package skeletons per design.md Component Breakdown.
- [ ] T1.2 — Add Postgres migrations for `cancel_request` and `reconcile_decision`.
- [ ] T1.3 — Implement `jobs/cancel/repository.py::CancelRequestRepository` with the partial unique index on `run_id`.
- [ ] T1.4 — Implement `jobs/cancel/dispatcher.py::CancelDispatcher.send_cancel_rpc` happy path (single transmit, record attempt).
- [ ] T1.5 — Implement `jobs/cancel/dispatcher.py::CancelDispatcher.handle_ack`; emit `entity.run.cancel_ack`.
- [ ] T1.6 — Implement `jobs/reconcile/reconciler.py::RunReconciler.reconcile_on_reconnect` basic concur + divergent paths.
- [ ] T1.7 — Subscribe to `entity.client.reconnected`; invoke reconciler.
- [ ] T1.8 — Implement `jobs/cancel/errors.py::CancelTransportError`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `jobs/cancel/backoff.py` with 1 s → 8 s exponential jittered backoff, `cancel_ack_retries` = 3.
- [ ] T2.2 — Implement `rehydrate` scanning `cancel_request` rows in `sent` state on startup; resume retries.
- [ ] T2.3 — Implement idempotent-replay in `send_cancel_rpc`: if a live request exists for `run_id`, return the existing row without transmit.
- [ ] T2.4 — Implement orphan-run detection: unknown `run_id` in ledger → create `needs_investigation` run + decision row.
- [ ] T2.5 — Implement `dispatch_lost_confirmed` path: service says `dispatch_unconfirmed`, ledger omits run → transition `dispatch_lost` + emit `entity.run.failed` reason `"dispatch_lost_confirmed"`.
- [ ] T2.6 — Implement per-client reconcile lock (`_client_locks[client_id]`).
- [ ] T2.7 — Implement paginated ledger reconciliation (500 entries per call).
- [ ] T2.8 — Garbage-collect terminal `cancel_request` rows in response to `entity.run.state_changed` → terminal transitions.

### M3 — Hardening

- [ ] T3.1 — Emit Prometheus metrics and OTel spans per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: `send_cancel_rpc` p99 < 50 ms; 1000-entry reconcile p99 < 400 ms.
- [ ] T3.3 — Wire `1-audit-log` subscriber for every cancel event and reconcile decision.
- [ ] T3.4 — Add alert: reconcile divergence rate > 10% for 1 h → `7-alerts-budgets`.
- [ ] T3.5 — Chaos test: cancel storm (100 concurrent cancels for the same run); assert only one `ClientCancelRequest` transmitted.
- [ ] T3.6 — Document cancel contract under `usersguide/jobs/cancel/contract.rst` including the "Pychestrate requests, client decides" invariant.
- [ ] T3.7 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.8 — Poisoned-entry test: inject a ledger entry that triggers `IllegalTransitionError`; assert the rest of the ledger still reconciles.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (reconciled state equals client truth) and Property 2 (cancel transmit bounded by retry budget), 1000 cases each.
- [ ] TT-3 — Integration test: user cancel → state machine `request_cancel` → cancel RPC → mock client ack → state transitions through `cancelling` → `cancelled`; assert `entity.run.cancel_ack` and terminal `entity.run.cancelled`.
- [ ] TT-4 — Reconnect-divergence test: service sees `running`, client reports `completed`; reconcile emits `entity.run.reconciled` and terminal state follows client.
- [ ] TT-5 — Orphan-run test: client ledger includes a run Pychestrate has no receipt for; assert orphan run created with `needs_investigation`.
- [ ] TT-6 — Restart-durability test: initiate cancel, kill service before ack; restart; assert retry resumes with `retries` incremented correctly.
- [ ] TT-7 — Extension-point test: N/A — negative test confirming this feature declares no registrable factory or resource.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
      — N/A for this feature.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
