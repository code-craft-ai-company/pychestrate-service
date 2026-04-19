# 5-cancel-reconcile — Design

## Architecture

This feature owns two surfaces that cooperate:

1. A **cancel dispatcher** that receives `run_id` + reason from
   `5-run-state-machine.request_cancel`, resolves the live
   `client_id` + `client_local_run_id` via `5-dispatch-receipt`,
   transmits a `ClientCancelRequest` over
   `3-client-agent-protocol`, records the request, and retries
   ack-timeouts with bounded exponential backoff.
2. A **reconciler** invoked by `3-client-agent-protocol` on every
   successful heartbeat reconnect. It takes the client-reported
   `ClientRunLedger`, diffs each entry against the state machine,
   and calls `5-run-state-machine.reconcile` for divergent rows —
   always in the direction of client truth.

Authoritative source of truth for run-process state is the client.
Service belief is a cached projection that gets aligned on every
reconnect. This feature lands in **Phase 3** and is the producer of
`entity.run.cancel_ack` + `entity.run.reconciled` that the state
machine consumes, plus the downstream-visible
`entity.run.cancelled | completed | failed` events (emitted by the
state machine on the terminal transition this feature triggers).
Lives at `source/site/automojo/pychestrate/webservice/jobs/cancel/`
and `.../jobs/reconcile/`.

## Data Model

Owned rows:

- `cancel_request`:
  - `request_id: UUID` (PK, UUIDv7)
  - `run_id: UUID` (FK, unique-while-non-terminal)
  - `client_id: UUID`
  - `client_local_run_id: text`
  - `reason: text`
  - `actor: text`
  - `state: CancelRequestState` (`sent | acked |
    acked_and_confirmed | timed_out | unreachable`)
  - `sent_at: timestamptz`
  - `acked_at: timestamptz | None`
  - `confirmed_at: timestamptz | None`
  - `retries: int`
  - `last_error: text | None`
  - Partial unique index: `run_id` where `state IN ('sent',
    'acked')`.
- `reconcile_decision`:
  - `decision_id: UUID` (PK, UUIDv7)
  - `client_id: UUID` (FK, indexed)
  - `run_id: UUID` (FK, indexed, nullable for orphans)
  - `client_local_run_id: text`
  - `prior_state: RunState | None`
  - `resolved_state: RunState`
  - `outcome: ReconcileOutcome` (`concur | divergent | orphan |
    dispatch_lost_confirmed`)
  - `reconciled_at: timestamptz`

Enums:

- `CancelRequestState`
- `ReconcileOutcome`

Value types:

- `ClientCancelRequest`:
  - `request_id: UUID`
  - `client_local_run_id: str`
  - `reason: str`
  - `deadline_at: datetime`
- `ClientCancelAck`:
  - `request_id: UUID`
  - `client_local_run_id: str`
  - `acked_at: datetime`
  - `client_state_at_ack: str`
- `ClientRunLedger`:
  - `client_id: UUID`
  - `reported_at: datetime`
  - `entries: list[ClientRunEntry]`
- `ClientRunEntry`:
  - `envelope_id: UUID | None`
  - `client_local_run_id: str`
  - `client_reported_state: str`
  - `started_at: datetime | None`
  - `finished_at: datetime | None`
  - `terminal_outcome: str | None`

## Interfaces

### Public API

N/A. Cancel routes live in `8-rest-api-v1`; reconcile is invoked
by the `3-client-agent-protocol` handler.

### Internal API

```python
class CancelDispatcher:
    def __init__(
        self,
        repository: CancelRequestRepository,
        receipt_service: DispatchReceiptService,
        client_transport: ClientTransport,
        run_state_machine: RunStateMachine,
        bus: MessageBus,
        config: CancelConfig
    ) -> None:
        self._repository = repository
        self._receipt_service = receipt_service
        self._client_transport = client_transport
        self._run_state_machine = run_state_machine
        self._bus = bus
        self._config = config
        return

    def send_cancel_rpc(
        self,
        run_id: UUID,
        reason: str,
        actor: str,
        aspects: CancelAspects | None = None
    ) -> CancelRequestRow:
        """
            Transmit a ClientCancelRequest, idempotent while a
            prior request is still live.

            :param run_id: Service run id.
            :param reason: Human-readable reason.
            :param actor: Authenticated actor id.
            :param aspects: Behavior parameters (retry, timeout).

            :returns: The persisted request row.
            :raises: SemanticError, CancelTransportError
        """
        ...

    def handle_ack(
        self,
        ack: ClientCancelAck
    ) -> None:
        """
            Apply an ack to the pending request, emit
            entity.run.cancel_ack.

            :param ack: Client ack.

            :returns: None
            :raises: SemanticError
        """
        ...

    def rehydrate(
        self
    ) -> int:
        """
            Restart pending cancel retries from the cancel_request
            table on process startup.

            :returns: Number of requests rehydrated.
            :raises: None
        """
        ...


class RunReconciler:
    def __init__(
        self,
        state_machine: RunStateMachine,
        receipt_service: DispatchReceiptService,
        decision_repository: ReconcileDecisionRepository,
        bus: MessageBus,
        config: ReconcileConfig
    ) -> None:
        self._state_machine = state_machine
        self._receipt_service = receipt_service
        self._decision_repository = decision_repository
        self._bus = bus
        self._config = config
        self._client_locks: dict[UUID, asyncio.Lock] = {}
        return

    def reconcile_on_reconnect(
        self,
        client_id: UUID,
        ledger: ClientRunLedger
    ) -> ReconcileReport:
        """
            Diff the client's ledger against the state machine
            and align service belief to client truth.

            :param client_id: Authenticated client id.
            :param ledger: Client-reported ledger.

            :returns: ReconcileReport summarizing outcomes.
            :raises: SemanticError
        """
        ...
```

### Extension Surface

None. This feature's behavior is not pluggable — its correctness
hinges on strict invariants described in requirements.

### Events Emitted

On `0-message-bus`:

- `entity.run.cancel_ack` — `{run_id, client_id, acked_at,
  client_state_at_ack}`
- `entity.run.reconciled` — `{run_id, client_id, prior_state,
  resolved_state, outcome, source: "client_truth"}`
- `pychestrate.cancel.rpc_sent`
- `pychestrate.cancel.rpc_unreachable`
- `pychestrate.reconcile.run_divergent`
- `pychestrate.reconcile.orphan_run`
- `pychestrate.reconcile.dispatch_lost_confirmed`

### Events Consumed

- `entity.run.state_changed` — used to garbage-collect terminal
  `cancel_request` rows (sets `state='acked_and_confirmed'` once
  the run is terminal with outcome `cancelled`).
- `entity.client.reconnected` (from `3-client-agent-protocol`)
  — carries the `ClientRunLedger` and triggers reconciliation.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/`:

- `jobs/cancel/__init__.py`
- `jobs/cancel/dispatcher.py` — `CancelDispatcher`.
- `jobs/cancel/repository.py` — `CancelRequestRepository`.
- `jobs/cancel/backoff.py` — retry/backoff policy.
- `jobs/cancel/errors.py` — `CancelTransportError`.
- `jobs/cancel/hooks.py` — startup rehydrate.

- `jobs/reconcile/__init__.py`
- `jobs/reconcile/reconciler.py` — `RunReconciler`.
- `jobs/reconcile/diff.py` — ledger-vs-service state diff.
- `jobs/reconcile/repository.py` — `ReconcileDecisionRepository`.
- `jobs/reconcile/schema.py` — `ClientRunLedger`,
  `ClientRunEntry`, `ReconcileReport`.
- `jobs/reconcile/hooks.py` — subscriber wiring.

## Key Flows

### Flow 1 — User-Triggered Cancel Happy Path

1. User hits the cancel button; `8-rest-api-v1` enforces
   `jobs:cancel` RBAC and calls
   `state_machine.request_cancel(run_id, actor, reason)`.
2. State machine transitions to `cancel_requested`, emits
   `entity.run.cancelled` (request phase), and calls
   `cancel_dispatcher.send_cancel_rpc`.
3. Dispatcher looks up the live `client_id + client_local_run_id`
   via `receipt_service.lookup_by_run`.
4. Dispatcher inserts the `cancel_request` row and calls
   `client_transport.send_cancel(client_id,
   ClientCancelRequest(...), timeout=cancel_ack_timeout)`.
5. Client processes the cancel, replies with `ClientCancelAck`;
   dispatcher calls `handle_ack`, emits
   `entity.run.cancel_ack`.
6. State machine transitions to `cancelling`.
7. Client's next progress or result indicates stopped →
   transition to `cancelled`.

### Flow 2 — Reconnect Reconciliation

1. Client reconnects over `3-client-agent-protocol`; handler
   receives the ledger.
2. Handler invokes `reconciler.reconcile_on_reconnect(client_id,
   ledger)`.
3. Reconciler acquires `_client_locks[client_id]`.
4. For each `ClientRunEntry`:
   - If `run_id` unknown (no `DispatchReceipt`) →
     `needs_investigation` run created, decision row `orphan`.
   - Else if `client_reported_state == service_state` →
     decision row `concur`.
   - Else `state_machine.reconcile(run_id,
     client_reported_state, source="client_truth")`; decision
     row `divergent`.
   - If service says `dispatch_unconfirmed` and client ledger
     does not include the run → decision row
     `dispatch_lost_confirmed`; state machine transitions to
     `dispatch_lost`.
5. `ReconcileReport` returned with counts.

### Flow 3 — Cancel Ack Timeout

1. Transport send succeeds; ack does not arrive within
   `cancel_ack_timeout`.
2. Backoff scheduler retries up to `cancel_ack_retries`.
3. On final failure: `cancel_request.state = 'unreachable'`;
   emit `pychestrate.cancel.rpc_unreachable`.
4. Run state remains `cancel_requested`; reconciliation on the
   client's eventual reconnect will resolve truth.

## Error Handling

- `SemanticError` (missing receipt, unknown run, client_id
  mismatch): never caught.
- `CancelTransportError`: caught at transport adapter boundary,
  reclassified with `client_id`, `run_id`, `request_id`,
  retried under the backoff schedule.
- Reconciliation of an entry that fails state-machine transition
  (e.g., illegal): caught, logged, `reconcile_decision` marked
  with outcome `"illegal_transition"`, processing continues for
  the rest of the ledger — a poisoned entry MUST NOT derail the
  reconnect.
- `IllegalTransitionError` from state machine during reconcile:
  caught locally (this is the explicit exception-to-outcome
  translation; it lets a partial ledger still align the rest).

Example multiline error:

```python
err_msg_lines = ["Cancel RPC unreachable after retries."]
err_msg_lines.append("RUN_ID: {}".format(run_id))
err_msg_lines.append("CLIENT_ID: {}".format(client_id))
err_msg_lines.append("REQUEST_ID: {}".format(request_id))
err_msg_lines.append("RETRIES: {}".format(retries))
err_msg_lines.append("LAST_TRANSPORT_ERROR: {}".format(last_error))

err_msg = os.linesep.join(err_msg_lines)
raise CancelTransportError(err_msg) from None
```

## Security Considerations

- Cancel routes enforce `jobs:cancel` RBAC upstream.
- Reconciliation is only reachable from the authenticated
  `3-client-agent-protocol` handler; the ledger's `client_id`
  must match the authenticated channel — mismatch raises
  `SemanticError`.
- Every cancel attempt and reconcile decision is audited via
  `1-audit-log` subscribers on the corresponding events.
- Orphan runs are created as `needs_investigation` rather than
  silently dropped — a compromised client cannot "disappear" a
  real run by omitting it from the ledger.

## Observability

Metrics and log events listed in requirements.md NFR-3.

Trace spans:

- `pychestrate.cancel.send_rpc` with `run_id`, `client_id`,
  `project`, `retries_used`.
- `pychestrate.reconcile.on_reconnect` with `client_id`,
  `ledger_size`, `divergent_count`, `orphan_count`.

Dashboards: cancel-ack-latency histogram, unreachable-cancel
gauge, reconcile-divergence rate on `7-orchestration-metrics`;
alert on divergence rate > 10% of reconciled runs for 1 h
(indicates systemic drift worth investigating).

## Open Questions

- Ledger size cap: some clients may manage 10k+ in-flight runs
  across a reboot. Do we paginate reconciliation? Current draft:
  yes, page at 500 entries per call; additional pages on
  subsequent heartbeats until the ledger is empty. Timebox:
  Phase 3 exit.
- Do we record cancel request history in `1-audit-log` with
  payload bodies, or only metadata? Current draft: metadata +
  `reason`; payload (which is tiny) is audited as a redacted
  summary. Timebox: Phase 3 exit.
- `dispatch_lost_confirmed` route — should this feature
  automatically re-dispatch, or leave that to orchestration?
  Current draft: leave to orchestration; we only confirm the
  loss. Timebox: Phase 3 exit.
