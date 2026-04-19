# 5-run-state-machine — Design

## Architecture

The state machine is a pure-Python table-driven transition engine
over the `run` row owned by `0-persistence`. It lives at
`source/site/automojo/pychestrate/webservice/jobs/run/state/`. It is
the *only* component that writes `run.state` — every other feature
that needs to change state calls `run_state_machine.transition(...)`
with an event name, never a raw state. This is load-bearing: it
keeps the permissible state graph in one place and makes it
impossible for a new feature to invent a state edge by accident.
Authoritative source of truth is the `run` row plus its append-only
`run_state_audit` log; the outbox pattern guarantees the bus event
is published iff the state row committed. This feature lands in
**Phase 3** and is the bus backbone for `6-live-run-view`,
`7-test-metrics`, retention, and the run-detail UI.

## Data Model

Owned rows:

- `run`:
  - `run_id: UUID` (PK)
  - `project_id: UUID` (FK, indexed)
  - `job_type: str`
  - `state: RunState` (enum)
  - `prior_state: RunState | None`
  - `entered_state_at: timestamptz`
  - `progress_last_observed_at: timestamptz | None`
  - `terminal_outcome: TerminalOutcome | None`
  - `cancel_reason: str | None`
  - `cancel_actor: str | None`
  - Index: `(project_id, state)`, `(state,
    progress_last_observed_at)` for stall sweeping.
- `run_state_audit`:
  - `audit_id: UUID` (PK, UUIDv7)
  - `run_id: UUID` (FK, indexed)
  - `from_state: RunState`
  - `to_state: RunState`
  - `event: RunEvent`
  - `actor: str`
  - `reason: str | None`
  - `transitioned_at: timestamptz`
- `run_event_outbox`:
  - `outbox_id: UUID` (PK)
  - `run_id: UUID`
  - `topic: str`
  - `payload: jsonb`
  - `created_at: timestamptz`
  - `published_at: timestamptz | None`

Enums:

- `RunState`: `pending | dispatching | dispatched |
  dispatch_unconfirmed | dispatch_lost | dispatch_failed | running |
  progress_stalled | cancel_requested | cancelling | cancelled |
  completing | completed | failed | needs_investigation`
- `RunEvent`: `dispatch_started | envelope_signed |
  receipt_recorded | receipt_ack_timeout | receipt_lost |
  dispatch_aborted | first_progress | progress_observed |
  progress_stall_detected | progress_resumed | cancel_requested |
  cancel_ack_received | cancel_completed | completion_observed |
  failure_observed | reconciled_to_terminal | investigation_required`
- `TerminalOutcome`: `success | failure | cancelled |
  dispatch_failed | dispatch_lost`

## Interfaces

### Public API

N/A at the HTTP surface. UI/REST flows go through `8-rest-api-v1`
which calls `request_cancel`.

### Internal API

```python
class RunStateMachine:
    def __init__(
        self,
        repository: RunRepository,
        audit_repository: RunStateAuditRepository,
        outbox: RunEventOutbox,
        transition_table: TransitionTable,
        clock: Clock,
        stall_threshold_seconds: int
    ) -> None:
        self._repository = repository
        self._audit_repository = audit_repository
        self._outbox = outbox
        self._transition_table = transition_table
        self._clock = clock
        self._stall_threshold_seconds = stall_threshold_seconds
        return

    def transition(
        self,
        run_id: UUID,
        event: RunEvent,
        actor: str,
        reason: str | None = None
    ) -> RunStateSnapshot:
        """
            Apply an event to a run; transactional state update +
            audit append + outbox insert.

            :param run_id: Run id.
            :param event: Event to apply.
            :param actor: Authenticated actor identifier.
            :param reason: Optional free-form reason (audited).

            :returns: RunStateSnapshot with prior + new state.
            :raises: IllegalTransitionError, TerminalStateError,
                     SemanticError
        """
        ...

    def request_cancel(
        self,
        run_id: UUID,
        actor: str,
        reason: str
    ) -> RunStateSnapshot:
        """
            Request cancellation — transitions to cancel_requested
            and hands off to 5-cancel-reconcile for RPC delivery.

            :param run_id: Run id.
            :param actor: Authenticated actor.
            :param reason: Human-readable reason.

            :returns: RunStateSnapshot.
            :raises: IllegalTransitionError, TerminalStateError
        """
        ...

    def reconcile(
        self,
        run_id: UUID,
        client_reported_state: RunState,
        source: str
    ) -> RunStateSnapshot:
        """
            Apply a client-reported truth to reconcile divergence.

            :param run_id: Run id.
            :param client_reported_state: The client's authoritative
                                          state.
            :param source: Origin tag, e.g., "client_truth".

            :returns: RunStateSnapshot.
            :raises: SemanticError
        """
        ...

    def get(
        self,
        run_id: UUID
    ) -> RunStateSnapshot:
        """
            Read the current state snapshot.

            :param run_id: Run id.

            :returns: RunStateSnapshot.
            :raises: RunNotFoundError
        """
        ...

    def sweep_stalled(
        self
    ) -> int:
        """
            Transition all running runs whose
            progress_last_observed_at is older than the threshold
            into progress_stalled.

            :returns: Number of runs transitioned.
            :raises: None
        """
        ...
```

### Extension Surface

None at the factory level — this feature declares *event topics*,
which are the primary extension surface for external subscribers.

Declared topics (`event:` surface on
implementation-plan.md Layer 5):

- `entity.run.state_changed` — every transition.
- `entity.run.cancelled` — terminal cancelled AND request phase.
- `entity.run.completed` — terminal success.
- `entity.run.failed` — terminal failure.
- `entity.run.reconciled` — client-truth divergence resolved.
- `entity.run.dispatched` — emitted from `5-job-dispatch` but
  consumed here to drive the `dispatch_started` → `dispatched`
  transition.

### Events Emitted

See topics above. Payload shape (Python dataclass-style):

```python
@dataclass(frozen=True)
class RunStateChanged:
    run_id: UUID
    project_id: UUID
    from_state: RunState
    to_state: RunState
    event: RunEvent
    actor: str
    reason: str | None
    transitioned_at: datetime

@dataclass(frozen=True)
class RunReconciled:
    run_id: UUID
    project_id: UUID
    prior_state: RunState
    resolved_state: RunState
    source: str
    reconciled_at: datetime
```

### Events Consumed

- `entity.run.dispatched` (from `5-job-dispatch`) → `dispatch_started`.
- `pychestrate.dispatch_receipt.recorded` → `receipt_recorded`.
- `pychestrate.dispatch_receipt.expected_timeout` →
  `receipt_ack_timeout`.
- `entity.progress.received` (from `5-progress-ingest`) →
  `first_progress` or `progress_observed`.
- `entity.result_tree.landed` (from `5-result-ingest-watcher`) →
  `completion_observed` or `failure_observed` depending on the
  parsed summary.
- `entity.run.cancel_ack` (from `5-cancel-reconcile`) →
  `cancel_ack_received`.
- `entity.run.reconciled` (from `5-cancel-reconcile`) →
  triggers `reconcile()` call.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/`:

- `jobs/run/state/__init__.py`
- `jobs/run/state/enums.py` — `RunState`, `RunEvent`,
  `TerminalOutcome`.
- `jobs/run/state/transition_table.py` — table-driven edges and
  terminal-state set.
- `jobs/run/state/machine.py` — `RunStateMachine` facade.
- `jobs/run/state/repository.py` — `run`, `run_state_audit`, and
  `run_event_outbox` CRUD.
- `jobs/run/state/outbox_publisher.py` — background task that
  drains the outbox onto `0-message-bus`.
- `jobs/run/state/stall_sweeper.py` — periodic task that flips
  stalled runs.
- `jobs/run/state/errors.py` — `IllegalTransitionError`,
  `TerminalStateError`, `RunNotFoundError`.
- `jobs/run/state/subscriptions.py` — wires bus subscriptions listed
  in "Events Consumed".
- `jobs/run/state/hooks.py` — startup hook to start the outbox
  publisher + stall sweeper.

## Key Flows

### Flow 1 — Dispatch to Running

1. `5-job-dispatch` creates the run in state `pending` via
   `transition(run_id, event=dispatch_started, actor="dispatcher")`.
2. Dispatcher emits `entity.run.dispatched`; subscription calls
   `transition(run_id, event=envelope_signed)` → `dispatching` then
   `transition(run_id, event=receipt_recorded)` → `dispatched`.
3. Client sends first progress record; `5-progress-ingest` emits
   `entity.progress.received`; subscription calls
   `transition(run_id, event=first_progress)` → `running`.

### Flow 2 — Cancel with Client-Side Completion Race

1. User presses cancel; `request_cancel(run_id, actor,
   "user-cancel")` transitions to `cancel_requested`, publishes
   `entity.run.cancelled` (request phase), invokes
   `5-cancel-reconcile.send_cancel_rpc`.
2. Client acks → `cancel_ack_received` → `cancelling`.
3. Meanwhile the result tree lands with
   `terminal_outcome=success`; `entity.result_tree.landed` arrives.
4. Subscription maps to `completion_observed`. Machine detects
   mid-cancel race, calls `reconcile(run_id, completed,
   source="client_truth")`, transitions to `completed`, emits
   `entity.run.reconciled` *and* `entity.run.completed`.

### Flow 3 — Stall Detection

1. `stall_sweeper` fires every 30 s.
2. For every run in `running` with
   `progress_last_observed_at < now - stall_threshold_seconds`,
   `transition(run_id, event=progress_stall_detected)` → `progress_stalled`.
3. Next progress record triggers `transition(run_id,
   event=progress_resumed)` → `running`.

## Error Handling

- `IllegalTransitionError`: multiline message listing current state,
  event, and permitted events; caller responsibility to log and
  investigate — never caught internally.
- `TerminalStateError`: bubbles; caller decides whether to ignore
  (idempotent retry) or log.
- `SemanticError`: raised for unknown event enum, null run_id,
  unknown actor — never caught.
- Subscriber exceptions: caught at the subscription harness, logged,
  metric incremented; state machine not rolled back. This is the
  only place we catch broadly, and only because subscribers are
  third-party code surfaces.

Example multiline error:

```python
err_msg_lines = ["Illegal run state transition."]
err_msg_lines.append("RUN_ID: {}".format(run_id))
err_msg_lines.append("FROM_STATE: {}".format(current_state))
err_msg_lines.append("EVENT: {}".format(event))
err_msg_lines.append("PERMITTED EVENTS FROM THIS STATE:")
for permitted in sorted(permitted_events):
    err_msg_lines.append("    {}".format(permitted))

err_msg = os.linesep.join(err_msg_lines)
raise IllegalTransitionError(err_msg) from None
```

## Security Considerations

- Every `transition` call requires `actor`, which is set by the
  caller from the authenticated context. Unauthenticated system
  flows pass `actor="system:<subsystem>"`.
- `request_cancel` requires `jobs:cancel` RBAC, enforced at
  `8-rest-api-v1` route and audited on `1-audit-log`.
- `run_state_audit` is append-only; there is no API to delete rows.
- No free-form state strings — callers always use `RunEvent` enum
  values, parsed at the API boundary.

## Observability

Metrics:

- `pychestrate_run_state_transitions_total{from,to}` — counter
- `pychestrate_run_state_transition_duration_seconds` — histogram
- `pychestrate_run_state_active{state,project}` — gauge
- `pychestrate_run_terminal_total{outcome,project}` — counter
- `pychestrate_run_event_handler_errors_total{topic}` — counter
- `pychestrate_run_stall_total{project}` — counter
- `pychestrate_run_outbox_lag_seconds` — gauge (oldest unpublished
  outbox row age)

Log events:

- `pychestrate.run.state_changed`
- `pychestrate.run.cancel_requested`
- `pychestrate.run.reconciled`
- `pychestrate.run.stalled`
- `pychestrate.run.illegal_transition`

Trace span `pychestrate.run.transition` with `from`, `to`, `event`,
`run_id`, `project`, `actor`.

Dashboards: state-time-in-state histograms and active-by-state
stacked area on `7-orchestration-metrics`. Alert when outbox lag >
30 s for 2 minutes.

## Open Questions

- Should `needs_investigation` be terminal or re-resolvable? Current
  draft: re-resolvable — an operator can call `reconcile` to move
  it to a terminal state after review. Timebox: Phase 3 exit.
- Do we keep `progress_stall_threshold_seconds` as a service-wide
  config or expose it per project? Phase 5 (`5-offline-tolerance`)
  may need per-project override. Timebox: Phase 5 start.
- Should reconcile ever resurrect a terminal state? Current draft:
  no — once terminal, always terminal. If the client later contradicts
  a terminal, we create a new `needs_investigation` ticket rather
  than mutate the terminal outcome. Timebox: Phase 3 exit.
