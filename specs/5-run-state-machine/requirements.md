# 5-run-state-machine — Requirements

## Introduction

The `5-run-state-machine` feature defines the authoritative service-side
lifecycle for a job *run* — the unit of execution a pod client owns on
Pychestrate's behalf. Every significant Layer 5 operation
(dispatch, receipt arrival, progress ingest, result tree landing,
cancel RPC, reconciliation) is a transition in this machine. Because
Pychestrate never spawns processes, transitions are driven by
*observations* — envelope issuance, receipts, heartbeats, forwarded
summaries, watcher events — rather than by reaching out to a client.
This feature ships in **Phase 3** and publishes the
`entity.run.state_changed`, `entity.run.cancelled`,
`entity.run.completed`, `entity.run.failed`, and
`entity.run.reconciled` events every downstream feature subscribes to.

## Requirements

### Requirement 1: Canonical State Set and Transition DAG

**User Story:** As a service developer, I want one authoritative
enumeration of run states and transitions, so that no two features
disagree on what a run's lifecycle looks like.

**Acceptance Criteria (EARS):**

1. WHEN `run_state_machine.list_states()` is called THEN the system
   SHALL return the canonical state set `{pending, dispatching,
   dispatched, dispatch_unconfirmed, dispatch_lost, dispatch_failed,
   running, progress_stalled, cancel_requested, cancelling,
   cancelled, completing, completed, failed, needs_investigation}`.
2. WHEN `run_state_machine.transition(run_id, event)` is called with
   a permitted `event` for the current state THEN the system SHALL
   atomically update the run row, append a `run_state_audit` entry,
   and publish `entity.run.state_changed` with the previous and new
   state.
3. IF the event is not permitted from the current state THEN the
   system SHALL raise `IllegalTransitionError` naming the current
   state, event, and permitted events in a multiline message; no
   state change or event MUST occur.
4. WHERE the target state is terminal (`completed`, `failed`,
   `cancelled`, `dispatch_failed`, `dispatch_lost`) THEN the system
   SHALL reject any further transition attempts for that run with
   `TerminalStateError`.

### Requirement 2: Event Emission Per Lifecycle Phase

**User Story:** As a downstream feature (metrics, notifications,
UI, retention), I want distinct bus events per lifecycle milestone,
so that my subscriber can react to each milestone without
string-comparing state names.

**Acceptance Criteria (EARS):**

1. WHEN a run transitions from non-terminal to terminal state THEN
   the system SHALL publish exactly one of
   `entity.run.completed | entity.run.failed | entity.run.cancelled`
   matching the terminal state, *in addition to*
   `entity.run.state_changed`.
2. WHEN a run is resolved after `5-cancel-reconcile` determines the
   client's authoritative truth THEN the system SHALL publish
   `entity.run.reconciled` with `{run_id, prior_state, resolved_state,
   source: "client_truth"}`.
3. IF a subscriber raises while handling a state-change event THEN
   the system SHALL log, increment
   `pychestrate_run_event_handler_errors_total{topic}`, and continue
   — the state machine MUST NOT roll back because a subscriber
   failed.
4. WHERE a run remains in `running` without a progress update for
   longer than `progress_stall_threshold_seconds` (default 300) the
   system SHALL transition to `progress_stalled` and back to
   `running` when the next progress record arrives.

### Requirement 3: Cancellation Is a Pychestrate-Initiated RPC, Not a Local Decision

**User Story:** As a user clicking "Cancel" on a run, I want
Pychestrate to send a cancel RPC to the client and wait for the
client to report the authoritative outcome, so that Pychestrate's
state never diverges from reality.

**Acceptance Criteria (EARS):**

1. WHEN `run_state_machine.request_cancel(run_id, reason, actor)` is
   called THEN the system SHALL transition to `cancel_requested`,
   publish `entity.run.cancelled` with `{reason, actor,
   requested_at}` — a *request* event, not a *confirmed* event —
   AND call `5-cancel-reconcile.send_cancel_rpc(run_id)`.
2. WHEN the client acknowledges the cancel RPC THEN the system SHALL
   transition to `cancelling`.
3. WHEN the client reports the run as stopped via a forwarded
   summary or result-tree landing THEN the system SHALL transition
   to `cancelled` and emit `entity.run.state_changed` with the
   terminal state.
4. IF the client reports the run as `completed` or `failed` while
   the service-side state is `cancel_requested` or `cancelling` THEN
   the system SHALL honor the client's truth (the run finished
   before the cancel landed), transition to the client-reported
   terminal state, and emit `entity.run.reconciled` recording the
   divergence.

## Property-Based Test Requirements

### Property 1: Transition Graph is a DAG and Has No Skipped States

- **Invariant:** For any legal sequence of events applied to a fresh
  run, the resulting state trajectory is acyclic *when projected
  onto non-terminal states* (a run may re-enter `running` only via
  `progress_stalled → running`, which is explicitly modeled — every
  other non-terminal edge is forward-only) AND no transition reaches
  a terminal state without going through `running` or
  `dispatch_failed` or `dispatch_lost` (the three canonical paths
  from `pending` to a terminal).
- **Generator:** `hypothesis.strategies.lists(run_events(),
  min_size=1, max_size=200)` where `run_events()` draws from the
  full event alphabet. Apply each sequence to a fresh state
  machine; reject inputs that raise `IllegalTransitionError` —
  inside the accepted prefix, check the property.
- **Assertion:** every accepted prefix's trajectory satisfies the
  DAG condition (no non-modeled cycles) and every terminal-state
  trajectory includes at least one of the canonical predecessors.
- **Sample size:** 1000 generated cases

### Property 2: Idempotent Transition Re-Application

- **Invariant:** For any state `s` and any event `e` legal from `s`,
  applying `e` once followed by applying `e` a second time from
  *the new state* produces the same state as applying `e` once
  (i.e., `transition` is idempotent against duplicate-delivery of
  events from a retrying transport), except for transitions that
  are explicitly many-shot (`progress_stalled ↔ running`).
- **Generator:** Generate `(s, e)` pairs by sampling from the state
  table; drive the machine to `s` first, then apply `e` twice.
- **Assertion:** second application either no-ops (returning the
  same state) or raises `TerminalStateError` — it never transitions
  to an unrelated state. For the many-shot pair, the second
  application is expected to be valid.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `transition` p99 < 20 ms (Postgres UPDATE
  + audit INSERT + bus publish); sustained throughput ≥ 500
  transitions/sec/process. State lookups (`get(run_id)`) p99 < 5 ms
  served from a short-TTL in-memory cache with
  `entity.run.state_changed` invalidation.
- **NFR-2 (Security):** All state-change APIs require an authenticated
  actor identifier; cancel requests require the `jobs:cancel` RBAC
  permission gated at `8-rest-api-v1`. State transitions are audited
  to `1-audit-log` with `actor`, `run_id`, `from_state`, `to_state`,
  and `reason` (when present). The state table never accepts a
  free-form `state` value — callers always pass an event enum.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_run_state_transitions_total{from,to}` (counter),
  `pychestrate_run_state_transition_duration_seconds` (histogram),
  `pychestrate_run_state_active{state,project}` (gauge),
  `pychestrate_run_terminal_total{outcome,project}` (counter),
  `pychestrate_run_event_handler_errors_total{topic}` (counter),
  `pychestrate_run_stall_total{project}` (counter). Log events
  `pychestrate.run.state_changed`, `pychestrate.run.cancel_requested`,
  `pychestrate.run.reconciled`, `pychestrate.run.stalled`. Trace
  span `pychestrate.run.transition` with `from`, `to`, `event`,
  `actor`.
- **NFR-4 (Reliability):** A `transition` call is atomic — state
  update, audit insert, and outbox insert for the bus event commit
  in one Postgres transaction; the bus publisher reads from the
  outbox so a process crash between UPDATE and publish cannot lose
  the event.

## Out of Scope

- Actually sending the cancel RPC — owned by `5-cancel-reconcile`.
- Parsing forwarded summaries or result trees to produce
  completion/failure events — owned by `5-progress-ingest` and
  `5-result-ingest-watcher`.
- Retention of `run_state_audit` rows beyond a run's retention
  window — owned by `2-retention-policies`.
- UI rendering of state — owned by `9-run-detail-ui`.

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`, `5-job-dispatch`
  (transition source), `5-dispatch-receipt` (ack → `dispatched`),
  `5-progress-ingest` (first-progress → `running`; stall detection),
  `5-result-ingest-watcher` (terminal landings), `5-cancel-reconcile`
  (divergence resolution), `1-audit-log`.
- **Depended on by:** every Layer-5-and-above feature that observes
  run state — `6-live-run-view`, `6-flake-tracking`,
  `6-compare-runs`, `7-test-metrics`, `9-run-detail-ui`.
- **Extension points exposed:** `event:
  entity.run.state_changed|cancelled|completed|failed|reconciled` —
  see implementation-plan.md Layer 5 section.
