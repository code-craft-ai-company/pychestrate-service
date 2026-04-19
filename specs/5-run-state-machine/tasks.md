# 5-run-state-machine — Tasks

## Milestones

- **M1 — Skeleton:** `RunState`/`RunEvent` enums, transition table,
  `run` + `run_state_audit` + `run_event_outbox` tables,
  `RunStateMachine.transition` happy path, outbox publisher.
- **M2 — Core Behavior:** Bus subscriptions for dispatch/receipt/
  progress/result/cancel-ack events, `request_cancel` and
  `reconcile` APIs, stall sweeper, all milestone events
  (`entity.run.*`) emitted with typed payloads.
- **M3 — Hardening:** Property tests, perf validation, outbox-lag
  alert, audit-log wiring, `needs_investigation` workflow, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `jobs/run/state/` package skeleton per design.md Component Breakdown.
- [ ] T1.2 — Implement `jobs/run/state/enums.py` with `RunState`, `RunEvent`, `TerminalOutcome`.
- [ ] T1.3 — Implement `jobs/run/state/transition_table.py` encoding every permitted `(state, event) → next_state` edge.
- [ ] T1.4 — Add Postgres migrations for `run`, `run_state_audit`, `run_event_outbox`.
- [ ] T1.5 — Implement `jobs/run/state/repository.py` with a single transaction covering state update + audit insert + outbox insert.
- [ ] T1.6 — Implement `jobs/run/state/machine.py::RunStateMachine.transition` enforcing table + terminal-guard.
- [ ] T1.7 — Implement `jobs/run/state/outbox_publisher.py` background task draining the outbox onto `0-message-bus`.
- [ ] T1.8 — Implement `jobs/run/state/errors.py` with `IllegalTransitionError`, `TerminalStateError`, `RunNotFoundError`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `jobs/run/state/subscriptions.py` mapping `entity.run.dispatched`, `pychestrate.dispatch_receipt.*`, `entity.progress.received`, `entity.result_tree.landed`, `entity.run.cancel_ack` to events.
- [ ] T2.2 — Implement `request_cancel` → `cancel_requested` and emit `entity.run.cancelled` (request phase).
- [ ] T2.3 — Implement `reconcile` honoring client truth; emit `entity.run.reconciled` with prior + resolved state.
- [ ] T2.4 — Implement `stall_sweeper` periodic task (30 s interval) transitioning stalled running runs into `progress_stalled`.
- [ ] T2.5 — Emit `entity.run.completed`, `entity.run.failed`, `entity.run.cancelled` on terminal transitions in addition to `entity.run.state_changed`.
- [ ] T2.6 — Wire hook to call `5-cancel-reconcile.send_cancel_rpc` after `cancel_requested`.
- [ ] T2.7 — Implement `get` with a short-TTL in-memory cache invalidated by `entity.run.state_changed`.
- [ ] T2.8 — Add `progress_last_observed_at` update on `progress_observed` / `first_progress` transitions.

### M3 — Hardening

- [ ] T3.1 — Emit Prometheus metrics and OTel trace span per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: `transition` p99 < 20 ms; sustain ≥ 500/sec/process.
- [ ] T3.3 — Wire `1-audit-log` subscriber for `entity.run.state_changed`, `entity.run.cancelled`, `entity.run.reconciled`.
- [ ] T3.4 — Add alert: `pychestrate_run_outbox_lag_seconds > 30` for 2 min.
- [ ] T3.5 — Implement `needs_investigation` workflow: operator can call `reconcile` with `source="operator"` to close the ticket.
- [ ] T3.6 — Document state graph under `usersguide/jobs/run/state_machine.rst` with a rendered transition diagram.
- [ ] T3.7 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.8 — Subscriber-error resilience: unit test asserting a throwing subscriber does not roll back state.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement (Requirements 1–3), including all enumerated permitted and rejected transitions.
- [ ] TT-2 — Property-based tests implementing Property 1 (DAG/canonical-predecessor) and Property 2 (idempotent transition), 1000 cases each.
- [ ] TT-3 — Integration test: dispatch → receipt → progress → result landing → terminal, verify every milestone event appears on the bus with correct payload.
- [ ] TT-4 — Cancellation-race test: start cancel, simulate concurrent completion, assert `entity.run.reconciled` is published and terminal state is the client's truth.
- [ ] TT-5 — Outbox crash test: kill the process between state commit and outbox publish; restart and assert the event is eventually published exactly once.
- [ ] TT-6 — Stall detection test: run 10 runs, freeze progress for half, advance wall clock past threshold, sweep, assert only stalled runs transition.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
      — event topics are the extension surface; test-only subscriber included in TT-3.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
