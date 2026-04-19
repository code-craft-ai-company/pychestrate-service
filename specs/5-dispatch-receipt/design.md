# 5-dispatch-receipt — Design

## Architecture

The receipt subsystem is a small, persistence-backed correlation
store that sits alongside `5-job-dispatch`. Its single responsibility
is to bind a service-issued `run_id` / `envelope_id` pair to a
client-issued `client_local_run_id` and make both directions of that
mapping queryable. It owns one table and a single in-memory timer
wheel for deadline-bound receipts. Authoritative source of truth for
the `client_local_run_id` is the client — Pychestrate never mints or
rewrites it. This feature has no extension points; it is a pure
contract feature that lands in **Phase 3** alongside the rest of the
Layer 5 minimum-viable run surface.

## Data Model

Owned row:

- `dispatch_receipt`:
  - `receipt_id: UUID` (PK, UUIDv7)
  - `attempt_id: UUID` (FK → `dispatch_attempt.attempt_id`, unique)
  - `run_id: UUID` (FK → `run.run_id`, unique)
  - `envelope_id: UUID` (FK → `job_envelope.envelope_id`)
  - `client_id: UUID` (FK → `client.client_id`, indexed)
  - `client_local_run_id: text`
  - `pod_id: UUID`
  - `client_version: text`
  - `launch_pid: int`
  - `accepted_at: timestamptz` (client-reported)
  - `received_at: timestamptz` (service-observed)
  - `late_arrival: bool`
  - Unique constraints: `(run_id)`,
    `(client_id, client_local_run_id)`, `(attempt_id)`.
  - Indices: `(client_id, client_local_run_id)`, `(run_id)`.

In-memory state:

- `_pending_timers: TimerWheel[UUID, PendingReceipt]` — armed by
  `5-job-dispatch` on transmit; fires
  `pychestrate.dispatch_receipt.expected_timeout` when a receipt
  does not arrive.
- `_pending_count_by_project: dict[UUID, int]` — used for the
  gauge.

Value types:

- `DispatchReceipt`:
  - `envelope_id: UUID`
  - `run_id: UUID`
  - `client_local_run_id: str`
  - `accepted_at: datetime`
  - `client_id: UUID`
  - `pod_id: UUID`
  - `client_version: str`
  - `launch_pid: int`
- `PendingReceipt`:
  - `attempt_id: UUID`
  - `run_id: UUID`
  - `project_id: UUID`
  - `armed_at: datetime`
  - `deadline_at: datetime`

## Interfaces

### Public API

N/A — internal. Receipts traverse `3-client-agent-protocol`.

### Internal API

```python
class DispatchReceiptService:
    def __init__(
        self,
        repository: DispatchReceiptRepository,
        timer_wheel: TimerWheel,
        bus: MessageBus,
        config: ReceiptConfig
    ) -> None:
        self._repository = repository
        self._timer_wheel = timer_wheel
        self._bus = bus
        self._config = config
        self._pending_count_by_project: dict[UUID, int] = {}
        return

    def expect(
        self,
        attempt_id: UUID,
        run_id: UUID,
        project_id: UUID,
        deadline_at: datetime
    ) -> None:
        """
            Arm a timer for an expected receipt.

            :param attempt_id: Dispatch attempt id.
            :param run_id: Service-side run id.
            :param project_id: Project for gauge scoping.
            :param deadline_at: Absolute deadline for arrival.

            :returns: None
            :raises: SemanticError
        """
        ...

    def record(
        self,
        attempt_id: UUID,
        receipt: DispatchReceipt
    ) -> DispatchReceiptRow:
        """
            Persist a receipt, idempotent on
            (client_id, client_local_run_id).

            :param attempt_id: Dispatch attempt id.
            :param receipt: Client-supplied receipt.

            :returns: The persisted (or updated) row.
            :raises: SemanticError, DuplicateRunReceiptError
        """
        ...

    def lookup_by_local(
        self,
        client_id: UUID,
        client_local_run_id: str
    ) -> DispatchReceiptRow:
        """
            Fetch a receipt by client-scoped id.

            :param client_id: Client id.
            :param client_local_run_id: Client's local run id.

            :returns: The receipt row.
            :raises: ReceiptNotFoundError
        """
        ...

    def lookup_by_run(
        self,
        run_id: UUID
    ) -> DispatchReceiptRow:
        """
            Fetch a receipt by service run id.

            :param run_id: Service run id.

            :returns: The receipt row.
            :raises: ReceiptNotFoundError
        """
        ...
```

### Extension Surface

None. This feature is pure contract plumbing.

### Events Emitted

On `0-message-bus`:

- `pychestrate.dispatch_receipt.recorded` — `{run_id, attempt_id,
  client_id, client_local_run_id, received_at}`
- `pychestrate.dispatch_receipt.late_arrival` — same payload with
  `late: true`
- `pychestrate.dispatch_receipt.expected_timeout` — `{attempt_id,
  run_id, project_id, armed_at, deadline_at}`
- `pychestrate.dispatch_receipt.duplicate_rejected` — `{attempt_id,
  run_id, client_id, client_local_run_id, reason}`

### Events Consumed

- `entity.run.dispatched` (from `5-job-dispatch`) — paired with an
  `expect` call; used only for gauge scoping/consistency audits.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/`:

- `jobs/dispatch/receipt/__init__.py`
- `jobs/dispatch/receipt/schema.py` — `DispatchReceipt`,
  `DispatchReceiptRow`, `PendingReceipt` Pydantic models.
- `jobs/dispatch/receipt/service.py` — `DispatchReceiptService`
  facade.
- `jobs/dispatch/receipt/repository.py` — SQL-level CRUD with
  unique-conflict idempotency.
- `jobs/dispatch/receipt/timer_wheel.py` — in-memory hashed timer
  wheel for M1; migrated to Postgres-backed scheduler at M3.
- `jobs/dispatch/receipt/errors.py` — `ReceiptNotFoundError`,
  `DuplicateRunReceiptError`.
- `jobs/dispatch/receipt/hooks.py` — startup hook that rehydrates
  pending timers from attempts in `transmitted` state.

## Key Flows

### Flow 1 — Normal Receipt Path

1. `5-job-dispatch` transmits the envelope and calls
   `receipt_service.expect(attempt_id, run_id, project_id,
   deadline_at=now+dispatch_ack_timeout)`.
2. `_pending_count_by_project[project_id] += 1`, timer armed.
3. Client returns a `DispatchReceipt` on the same connection.
4. Transport handler calls `receipt_service.record(attempt_id,
   receipt)`.
5. Repository performs `INSERT … ON CONFLICT (client_id,
   client_local_run_id) DO UPDATE SET received_at = EXCLUDED.received_at`.
6. Timer cancelled; `_pending_count_by_project[project_id] -= 1`.
7. `pychestrate.dispatch_receipt.recorded` emitted.

### Flow 2 — Deadline Expired

1. Timer wheel fires for `attempt_id`; no matching receipt row.
2. `pychestrate.dispatch_receipt.expected_timeout` emitted.
3. `5-job-dispatch` observes the event and transitions the run to
   `dispatch_unconfirmed`; `5-cancel-reconcile` takes over on the
   client's next heartbeat.

### Flow 3 — Late Arrival After Timeout

1. Timer has already fired; client reconnects and replays the
   receipt.
2. `receipt_service.record` persists the row with `late_arrival =
   true`.
3. `pychestrate.dispatch_receipt.late_arrival` emitted.
4. `5-cancel-reconcile` resolves divergence using the client's
   heartbeat-reported truth — the receipt alone does not flip run
   state back.

## Error Handling

- `SemanticError` (envelope mismatch between attempt and receipt;
  `client_id` mismatch with the attempt's target client): never
  caught — the client is misbehaving.
- `DuplicateRunReceiptError`: raised when a *second distinct*
  receipt arrives for the same `run_id` (not an idempotent replay).
  Bubbles to the caller; `5-cancel-reconcile` logs and investigates.
- `ReceiptNotFoundError`: domain error; callers treat it as an
  ordinary miss.
- Database contention on `ON CONFLICT`: caught at the repository
  boundary, reclassified to `ReceiptPersistError` with multiline
  context, and retried (2 attempts).

Example multiline error:

```python
err_msg_lines = ["Dispatch receipt rejected — envelope mismatch."]
err_msg_lines.append("ATTEMPT_ID: {}".format(attempt_id))
err_msg_lines.append("ATTEMPT_ENVELOPE_ID: {}".format(attempt.envelope_id))
err_msg_lines.append("RECEIPT_ENVELOPE_ID: {}".format(receipt.envelope_id))
err_msg_lines.append("CLIENT_ID: {}".format(receipt.client_id))

err_msg = os.linesep.join(err_msg_lines)
raise SemanticError(err_msg) from None
```

## Security Considerations

- A receipt is accepted only on the authenticated connection that
  owns the dispatch — the transport layer passes the authenticated
  `client_id` into `record`, and a mismatch with the attempt's
  target raises `SemanticError`.
- Receipts never flow through unauthenticated inbound webhooks.
- `launch_pid` and `client_version` are stored, not indexed or
  logged by default; privacy-sensitive fields are redacted from
  default logger formatters.
- Row-level access: operators scoped to a project can read only
  that project's receipts — enforced in the query layer via
  `project_id` derived from the `run` FK.

## Observability

Metrics:

- `pychestrate_job_dispatch_pending_receipts{project}` — gauge
- `pychestrate_job_dispatch_receipts_recorded_total{project}` — counter
- `pychestrate_job_dispatch_receipts_late_total{project}` — counter
- `pychestrate_job_dispatch_receipt_record_latency_seconds` — histogram
- `pychestrate_job_dispatch_receipt_timer_fires_total{project}` — counter

Log events:

- `pychestrate.dispatch_receipt.recorded`
- `pychestrate.dispatch_receipt.late_arrival`
- `pychestrate.dispatch_receipt.expected_timeout`
- `pychestrate.dispatch_receipt.duplicate_rejected`

Trace span `pychestrate.dispatch_receipt.record` with attributes
`project`, `client_id`, `run_id`, `attempt_id`.

Dashboards: pending-receipt gauge and late-arrival ratio on
`7-orchestration-metrics`; alert when late-arrival ratio exceeds
5% for 5 minutes.

## Open Questions

- Should we accept a client-issued `run_id` alias instead of a
  separate `client_local_run_id`? Current draft: keep them distinct
  because operator tooling on the client side already uses its own
  local id scheme; blurring them would break that workflow.
  Timebox: Phase 3 exit.
- Persistent timer scheduler at M3 — Postgres `LISTEN/NOTIFY` or a
  dedicated work queue? Decide when `5-offline-tolerance` lands in
  Phase 5, since that feature re-uses the same scheduler.
