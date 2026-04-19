# 5-offline-tolerance — Design

## Architecture

This feature ties together three previously-existing subsystems into
one cohesive offline story. It contributes:

1. A **degraded-pod transition service** living at
   `source/site/automojo/pychestrate/webservice/jobs/offline/pod_state.py`
   that watches `3-client-agent-protocol` session-drop events and
   transitions the owning pod through `ready → degraded → offline`
   / back.
2. A **replay extension** to `5-progress-ingest`'s two endpoints —
   the endpoints stay in place; a replay-header gating pathway and a
   per-client replay-seq tracker land under
   `source/site/automojo/pychestrate/webservice/ingest/progress/replay.py`.
3. A **deferred-cancel queue** living at
   `source/site/automojo/pychestrate/webservice/jobs/offline/cancel_queue.py`
   that persists cancel requests while the client is offline and
   drains them after reconciliation completes.

No new endpoints. No new extension points. Authoritative source of
truth for the client's ledger remains the client; this feature just
guarantees ordered delivery across a disconnect. Lands in **Phase 5**
— after the Phase 3 Layer 5 slice is proved under fleet load, so
degraded-vs-offline thresholds can be tuned from real traces.

## Data Model

Owned rows:

- `pod_offline_state`:
  - `pod_id: UUID` (PK)
  - `client_id: UUID`
  - `state: PodOfflineState` (`ready | degraded | offline`)
  - `entered_state_at: timestamptz`
  - `last_seen_at: timestamptz`
- `client_replay_cursor`:
  - `client_id: UUID` (PK)
  - `session_id: UUID` (changes on every reconnect)
  - `last_ack_seq: bigint`
  - `updated_at: timestamptz`
- `deferred_cancel`:
  - `deferred_id: UUID` (PK, UUIDv7)
  - `run_id: UUID` (FK → run.run_id)
  - `client_id: UUID` (FK, indexed)
  - `reason: text`
  - `actor: text`
  - `queued_at: timestamptz`
  - `drained_at: timestamptz | None`
  - `status: DeferredCancelStatus` (`queued | drained |
    superseded | orphan`)

Enums:

- `PodOfflineState`
- `DeferredCancelStatus`

In-memory state:

- `_pod_timers: dict[UUID, PodTimer]` — degrade + offline timers.
- `_replay_locks: dict[UUID, asyncio.Lock]` — per-client replay
  serialization (shared with `5-progress-ingest`'s per-run lock
  at the run-scope level).

## Interfaces

### Public API

Replay is served over the existing `5-progress-ingest` endpoints
with two added headers:

- `X-Pychestrate-Replay: true`
- `X-Pychestrate-Replay-Seq: <monotonic int>`
- `X-Pychestrate-Replay-Complete: true` (on the final replay
  post)

The existing admin surface of `8-rest-api-v1` gains a read-only
deferred-cancel listing for operator visibility:

- `GET /api/v1/admin/deferred-cancels?client_id=<id>` — lists
  queued cancels per client.

### Internal API

```python
class PodOfflineStateService:
    def __init__(
        self,
        pod_repository: PodOfflineStateRepository,
        pod_lifecycle: PodLifecycle,
        bus: MessageBus,
        clock: Clock,
        config: OfflineConfig
    ) -> None:
        self._pod_repository = pod_repository
        self._pod_lifecycle = pod_lifecycle
        self._bus = bus
        self._clock = clock
        self._config = config
        self._pod_timers: dict[UUID, PodTimer] = {}
        return

    def handle_session_dropped(
        self,
        client_id: UUID,
        pod_id: UUID
    ) -> None:
        """
            Arm degrade timer; transition on expiry.

            :param client_id: Client id whose session dropped.
            :param pod_id: Owning pod id.

            :returns: None
            :raises: None
        """
        ...

    def handle_session_restored(
        self,
        client_id: UUID,
        pod_id: UUID
    ) -> None:
        """
            Cancel timers; mark ready after reconciliation
            completes.

            :param client_id: Client id.
            :param pod_id: Pod id.

            :returns: None
            :raises: None
        """
        ...


class ReplayCoordinator:
    def __init__(
        self,
        cursor_repository: ClientReplayCursorRepository,
        record_repository: ProgressRecordRepository,
        summary_repository: ProgressSummaryRepository,
        bus: MessageBus,
        config: OfflineConfig
    ) -> None:
        self._cursor_repository = cursor_repository
        self._record_repository = record_repository
        self._summary_repository = summary_repository
        self._bus = bus
        self._config = config
        return

    def accept_replay(
        self,
        client_id: UUID,
        session_id: UUID,
        replay_seq: int,
        run_id: UUID,
        kind: str,
        body_bytes: bytes,
        replay_complete: bool
    ) -> ReplayAck:
        """
            Apply a replayed batch after verifying seq order.

            :param client_id: Authenticated client id.
            :param session_id: Current session id from reconnect.
            :param replay_seq: Batch seq from header.
            :param run_id: Run id from route.
            :param kind: "records" or "summary".
            :param body_bytes: Request body.
            :param replay_complete: True on final batch.

            :returns: ReplayAck with next_expected_seq.
            :raises: ReplaySeqGapError, ReplayAuthError
        """
        ...


class DeferredCancelQueue:
    def __init__(
        self,
        repository: DeferredCancelRepository,
        cancel_dispatcher: CancelDispatcher,
        client_registry: ClientRegistryFacade,
        state_machine: RunStateMachine,
        bus: MessageBus,
        config: OfflineConfig
    ) -> None:
        self._repository = repository
        self._cancel_dispatcher = cancel_dispatcher
        self._client_registry = client_registry
        self._state_machine = state_machine
        self._bus = bus
        self._config = config
        return

    def queue_if_offline(
        self,
        run_id: UUID,
        client_id: UUID,
        reason: str,
        actor: str
    ) -> DeferredCancelOutcome:
        """
            Persist a deferred cancel if the client's session is
            not active; otherwise return outcome indicating
            caller should transmit directly.

            :param run_id: Run id.
            :param client_id: Client id.
            :param reason: Reason.
            :param actor: Actor id.

            :returns: DeferredCancelOutcome with queued flag.
            :raises: None
        """
        ...

    def drain_on_reconnect(
        self,
        client_id: UUID
    ) -> DrainReport:
        """
            Drain deferred cancels in queued_at order after the
            client reconciles.

            :param client_id: Client id.

            :returns: DrainReport with drained and superseded
                      counts.
            :raises: None
        """
        ...
```

### Extension Surface

None.

### Events Emitted

On `0-message-bus`:

- `entity.pod.state_changed` — from pod transitions (reusing
  `3-pod-lifecycle`'s topic) with the `degraded` / `offline`
  states added to the canonical set.
- `pychestrate.offline.pod_degraded`
- `pychestrate.offline.pod_offline`
- `pychestrate.offline.pod_recovered`
- `pychestrate.offline.replay_started` — `{client_id,
  session_id, started_at}`
- `pychestrate.offline.replay_completed` — `{client_id,
  session_id, total_records, total_summaries}`
- `pychestrate.offline.replay_gap` — `{client_id, session_id,
  expected_seq, received_seq}`
- `pychestrate.offline.deferred_cancel_queued` — `{run_id,
  client_id, reason, queued_at}`
- `pychestrate.offline.deferred_cancel_drained`
- `pychestrate.offline.deferred_cancel_superseded`

### Events Consumed

- `entity.client.session_dropped` (from
  `3-client-agent-protocol`).
- `entity.client.reconnected` (from
  `3-client-agent-protocol`) — used to trigger reconcile
  completion watch.
- `entity.run.reconciled` (from `5-cancel-reconcile`) —
  enqueues `drain_on_reconnect` after reconciliation finishes.
- `entity.run.state_changed` — detects runs that became
  terminal while offline for the supersede check.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/`:

- `jobs/offline/__init__.py`
- `jobs/offline/pod_state.py` — `PodOfflineStateService`.
- `jobs/offline/cancel_queue.py` — `DeferredCancelQueue`.
- `jobs/offline/timers.py` — hashed timer wheel (reuses
  `5-dispatch-receipt`'s Postgres-backed scheduler
  introduced in its M3).
- `jobs/offline/repository.py` — `PodOfflineStateRepository`,
  `ClientReplayCursorRepository`,
  `DeferredCancelRepository`.
- `jobs/offline/errors.py` — `ReplaySeqGapError`,
  `ReplayAuthError`.
- `jobs/offline/hooks.py` — startup rehydrate for pod timers
  and deferred-cancel queue, subscriber wiring.

- `ingest/progress/replay.py` — `ReplayCoordinator`; imported
  and invoked from `ingest/progress/service.py` when the
  replay header is present.

## Key Flows

### Flow 1 — Client Drops and Degraded Pod Surfaces

1. Client's session drops; `3-client-agent-protocol` emits
   `entity.client.session_dropped`.
2. `pod_state_service.handle_session_dropped(client_id,
   pod_id)` arms a degrade timer for
   `degraded_threshold_seconds`.
3. Timer fires → `pod_lifecycle.transition(pod_id,
   event=session_dropped)` → `degraded`, publish
   `pychestrate.offline.pod_degraded`.
4. Second timer (`offline_escalation_seconds`) arms on
   degrade; fires if still disconnected → `offline`.

### Flow 2 — Client Reconnects with Replay + Deferred-Cancel Drain

1. Client reconnects; `entity.client.reconnected` arrives
   with `ClientRunLedger`.
2. `5-cancel-reconcile.reconcile_on_reconnect` runs first
   (owned by its feature).
3. Concurrent with reconcile: client posts replay batches with
   `X-Pychestrate-Replay: true` and monotonic seq.
4. `ReplayCoordinator.accept_replay` checks cursor; gap →
   `409` + `pychestrate.offline.replay_gap`. Happy path →
   delegates to `ProgressIngestService.ingest_records /
   ingest_summary` with upsert-idempotent semantics on
   `(run_id, seq)`.
5. On `X-Pychestrate-Replay-Complete: true`, coordinator
   emits `replay_completed` and clears cursor.
6. After both reconcile and replay complete,
   `deferred_cancel_queue.drain_on_reconnect(client_id)` runs:
   - Each queued row: if run is terminal → mark `superseded`;
     else call `cancel_dispatcher.send_cancel_rpc`.
7. Pod transitions back to `ready` via
   `pod_state_service.handle_session_restored` after drain
   completes.

### Flow 3 — Cancel Issued While Offline

1. Operator clicks cancel; `8-rest-api-v1` calls
   `state_machine.request_cancel`.
2. State machine invokes `cancel_dispatcher.send_cancel_rpc`.
3. Cancel dispatcher consults `deferred_cancel_queue.queue_if_offline`;
   session inactive → row persisted, outcome `queued`.
4. State machine keeps the run in `cancel_requested`; no
   transport attempt.
5. When the client reconnects and drain runs, Flow 2 step 6
   drives the actual transmit.

## Error Handling

- `ReplaySeqGapError`: domain error → 409 with
  `{expected_seq, received_seq}`; emit `replay_gap`.
- `ReplayAuthError`: 403.
- Non-monotonic seq in a batch (within-batch reorder): 400 +
  logged; treated as client bug.
- `SemanticError` (unknown client/session): never caught.
- Startup rehydrate: rows in `queued` state with clients that
  never reconnect land in a maintenance report after
  `orphan_cutoff_seconds` (default 30 d). They are marked
  `orphan` status, never silently purged.

Example multiline error:

```python
err_msg_lines = ["Replay seq gap — batch refused."]
err_msg_lines.append("CLIENT_ID: {}".format(client_id))
err_msg_lines.append("SESSION_ID: {}".format(session_id))
err_msg_lines.append("EXPECTED_SEQ: {}".format(expected))
err_msg_lines.append("RECEIVED_SEQ: {}".format(received))

err_msg = os.linesep.join(err_msg_lines)
raise ReplaySeqGapError(err_msg) from None
```

## Security Considerations

- Replay endpoints inherit `5-progress-ingest`'s bearer-token
  auth and receipt-matching guarantees.
- `session_id` prevents a stale client process from replaying
  against a newer session; a mismatched `session_id` on the
  cursor → `403`.
- Deferred cancels inherit `jobs:cancel` RBAC; the queued row
  records the authenticated `actor` for audit.
- Rate limit on replay matches live ingest (token-bucket
  per `client_id`).
- A replay batch exceeding `max_records_bytes_per_request`
  (same 4 MiB cap as live) rejects `413`.

## Observability

Metrics and log events listed in requirements.md NFR-3.

Trace spans:

- `pychestrate.offline.replay` with `client_id`, `session_id`,
  `run_id`, `replay_seq`, `record_count`.
- `pychestrate.offline.drain_cancels` with `client_id`,
  `drained`, `superseded`.

Dashboards:

- Degraded/offline pod counts on `3-client-inventory-ui`.
- Replay volume + gap-rejection rate on `7-orchestration-metrics`.
- Deferred-cancel queue depth on `7-orchestration-metrics`.

Alerts:

- Degraded-pod ratio > 10% of fleet for 15 min → page.
- Replay gap-rejection rate > 1% for 30 min → investigate.
- Deferred-cancel queue depth > 200 for 1 h → investigate.

## Open Questions

- Should replay be a distinct endpoint (`.../replay/...`) rather
  than header-gated? Current draft: header-gated to avoid
  duplicating ingest logic. Timebox: Phase 5 start.
- Degraded-threshold default of 30 s — should this be pod-type
  scoped? (e.g., hardware pods with known flaky Wi-Fi want 120 s).
  Current draft: per-pod override added to `3-pod-definitions` at
  Phase 5 mid. Timebox: Phase 5 mid.
- Do we expose a client-facing "pending deferred cancels"
  endpoint so the client can pre-fetch and reconcile locally?
  Current draft: no — the cancel RPC on reconnect is the
  authoritative delivery. Timebox: Phase 5 exit.
