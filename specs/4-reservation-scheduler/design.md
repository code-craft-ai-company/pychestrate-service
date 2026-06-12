# 4-reservation-scheduler — Design

## Architecture

The scheduler is a single-writer dispatch worker per service process plus a
persistent `core.scheduler_entries` table. The table is the authoritative
source of truth for queued reservations; the in-process queue structures
(per-pool min-heaps / priority queues / fair-share trees) are
reconstituted from it on startup. The dispatch worker reacts to
`entity.reservation.released` events on `0-message-bus` and to a
periodic 1-second tick that runs starvation-recovery checks. The "pick the
next entry" decision is delegated to a `reservation_scheduler` factory
protocol implementation; the scheduler module owns only the queue
mechanics and the starvation guarantees. The decision is expressed as:
"given these waiting entries and this aspect bundle, which one should be
granted next?" Concrete behaviors are configured per pool and stored on
the pool row. Ships in Phase 4.

## Data Model

Schema `core`:

- `core.scheduler_entries`
  - `entry_id: UUID` — PK, v7
  - `reservation_id: UUID` — FK to `core.reservations` (1:1)
  - `pool_id: UUID`
  - `algorithm: str` — snapshot of pool's algorithm at enqueue time
  - `priority: int` — 0..100, 0 highest (reversed-heap convention)
  - `fair_share_key: str | None`
  - `fair_share_weight: float` — default 1.0, clamped to (0, 10]
  - `deadline_at: datetime | None`
  - `enqueued_at: datetime`
  - `promoted_at: datetime | None` — starvation-recovery timestamp
  - `state: SchedulerEntryState` — `queued` | `granted` | `cancelled`
  - `version: int`

Indices:

- PK on `entry_id`.
- UNIQUE on `reservation_id`.
- INDEX `(pool_id, state, priority, enqueued_at)` — covers priority/FIFO.
- INDEX `(pool_id, state, deadline_at NULLS LAST)` — covers deadline.
- INDEX `(fair_share_key, state)` — fair-share accounting.

Accounting view `core.fair_share_running_seconds_mv` (materialized, refreshed
every 30s) aggregates `SUM(granted_duration_seconds)` grouped by
`fair_share_key` over a 1-hour rolling window; the fair-share algorithm
reads from it.

## Interfaces

### Public API

N/A — internal-only. Queue visibility is surfaced via
`GET /api/v1/reservations?state=queued` which reads through
`4-checkout-checkin`.

### Internal API

```python
def enqueue(
    reservation_id: UUID,
    pool_id: UUID,
    algorithm: str,
    aspects: SchedulerAspects
) -> SchedulerEntry:
    """
        Persist a waiting reservation in the scheduler.

        :param reservation_id: The reservation to queue.
        :param pool_id: The pool the reservation is waiting on.
        :param algorithm: Pool's configured algorithm at enqueue time.
        :param aspects: Priority / fair-share / deadline bundle.

        :returns: The persisted SchedulerEntry.
        :raises: SchedulerUnavailableError (during drain),
                 SchedulerAspectsInvalidError
    """
    ...


def cancel(
    reservation_id: UUID,
    actor: UUID
) -> None:
    """
        Remove an entry from the queue; idempotent.

        :param reservation_id: The reservation id to cancel.
        :param actor: The caller performing the cancel.
    """
    ...


def pick_next_for_pool(
    pool_id: UUID
) -> SchedulerEntry | None:
    """
        Ask the pool's configured scheduler for the next grant candidate.

        :param pool_id: The pool to dispatch against.

        :returns: The chosen SchedulerEntry, or None if the queue is empty.
    """
    ...


def on_reservation_released(
    pool_id: UUID
) -> None:
    """
        Bus subscriber: try to grant the next queued entry on pool.

        :param pool_id: The pool whose capacity just freed.
    """
    ...


def run_starvation_sweep(
    tick_ts: datetime
) -> int:
    """
        Promote deadline-missed entries to their pool head.

        :param tick_ts: The current wall-clock tick.

        :returns: Number of entries promoted in this tick.
    """
    ...


def rehydrate_on_startup() -> None:
    """
        Rebuild in-memory queue structures from persisted entries.
    """
    ...
```

### Extension Surface

Factory protocol:

```python
class ReservationSchedulerProtocol(FactoryProtocolBase):
    """
        factory_protocol_name = "reservation_scheduler"
    """

    @classmethod
    def pick(
        cls,
        pool_id: UUID,
        candidates: list[SchedulerEntry],
        accounting: SchedulerAccounting
    ) -> SchedulerEntry | None:
        """
            Return the next entry to grant; None means "not now".

            :param pool_id: The pool being dispatched.
            :param candidates: Currently queued entries for the pool.
            :param accounting: Fair-share / running-time snapshot.

            :returns: The chosen entry, or None.
        """
        ...
```

In-tree implementations under
`source/site/ccai/factories/pychestrate/reservation_scheduler/`:

- `FifoScheduler` — `PRECEDENCE = 1000`; earliest `enqueued_at`.
- `PriorityScheduler` — `PRECEDENCE = 1100`; `priority` ASC, tie-break on
  `enqueued_at`.
- `FairShareScheduler` — `PRECEDENCE = 1200`; minimizes
  `(running_seconds + queued_wait) / weight`.
- `DeadlineScheduler` — `PRECEDENCE = 1300`; `deadline_at` ASC with
  starvation floor.

Test-only `AdversarialStarvingScheduler` at `PRECEDENCE = 100` that
deliberately starves high-priority entries — used to prove that starvation
recovery fires regardless of algorithm.

### Events Emitted

- `pychestrate.scheduler.enqueued` — `{entry_id, reservation_id, pool_id,
  algorithm}`
- `pychestrate.scheduler.cancelled` — `{entry_id, reservation_id, actor}`
- `pychestrate.scheduler.starvation_promoted` — `{entry_id, pool_id,
  waited_seconds, deadline_missed_by_seconds}`
- `pychestrate.scheduler.starvation_blocked` — `{entry_id, pool_id,
  reason: conflict | validator | pool_empty}`
- `pychestrate.scheduler.algorithm_missing` — `{pool_id, algorithm_requested}`

### Events Consumed

- `entity.reservation.released` — triggers dispatch on the pool.
- `entity.reservation.granted` with `from_queue=true` — closes accounting.
- `0-maintenance-mode.drain_started` / `.drain_ended` — enqueue gate.
- `extension.reloaded` — rebuild factory-protocol bindings.

## Component Breakdown

Under `source/site/ccai/pychestrate/webservice/resources/scheduler/`:

- `models.py` — `SchedulerEntry`, `SchedulerEntryState`,
  `SchedulerAspects`, `SchedulerAccounting`.
- `repository.py` — CRUD on `core.scheduler_entries`, fair-share
  running-seconds query.
- `dispatch_worker.py` — single-writer loop subscribing to the bus and
  running the 1s tick.
- `starvation.py` — starvation detection and promotion.
- `service.py` — orchestrates `enqueue`, `cancel`, `pick_next_for_pool`.
- `subscribers.py` — bus subscriptions.
- `errors.py` — `SchedulerUnavailableError`, `SchedulerAspectsInvalidError`.

Factory impls at
`source/site/ccai/factories/pychestrate/reservation_scheduler/`.

## Key Flows

### Flow 1 — Enqueue on pool exhausted

1. `4-checkout-checkin` cannot find a candidate; calls
   `scheduler.enqueue(reservation_id, pool_id, algorithm, aspects)`.
2. Service normalizes aspects: clamp `priority` to `[0, 100]`,
   `fair_share_weight` to `(0, 10]`, `deadline_at` to at most
   `max_reservation_ttl_seconds` into the future; any violation →
   `SchedulerAspectsInvalidError`.
3. Service inserts `core.scheduler_entries` row (state=`queued`) and the
   in-memory queue for `pool_id`.
4. Emit `pychestrate.scheduler.enqueued`; increment gauge
   `pychestrate_scheduler_queue_depth`.

### Flow 2 — Dispatch on release

1. `entity.reservation.released` fires with `pool_id=P`.
2. `on_reservation_released(P)` runs on the dispatch worker.
3. Service calls `pick_next_for_pool(P)` which resolves the pool's
   algorithm, loads candidates from the in-memory queue, and invokes
   `Scheduler.pick(...)`.
4. On a candidate: call `checkout.grant_from_queue(reservation_id)`.
5. On `ReservationConflictError`: leave the entry queued, increment
   `pychestrate_scheduler_grant_retry_total`, try the next-best
   candidate. Bounded at 3 retries per release event.
6. On success: emit `.granted` (from `4-checkout-checkin`), observe
   `pychestrate_scheduler_wait_duration_seconds`.

### Flow 3 — Starvation recovery

1. 1s tick runs `run_starvation_sweep(now)`.
2. For each pool, entries whose `deadline_at < now() -
   starvation_threshold` and `promoted_at IS NULL` are set
   `promoted_at=now()` and moved to the head of the per-pool in-memory
   queue.
3. Emit `pychestrate.scheduler.starvation_promoted` with
   `waited_seconds` and `deadline_missed_by_seconds`.
4. If a promoted entry remains queued after one full dispatch cycle
   (next pool release), emit `.starvation_blocked` with the blocking
   reason so operators can see *why* a starving entry cannot be
   granted (likely a stuck holder — see `4-lease-heartbeat`).

### Flow 4 — Algorithm fallback

1. Service startup hydrates `factory_registry.get_override_types_by_order(
   "reservation_scheduler")`.
2. Per-pool cache maps pool's declared algorithm name to the
   PRECEDENCE-winning implementation.
3. If the declared name is not present, fall back to `FifoScheduler`,
   log `pychestrate.scheduler.algorithm_missing` once per pool, and
   set `pychestrate_scheduler_algorithm_fallback{pool}=1`.

## Error Handling

- `SchedulerUnavailableError` → returned to checkout as `503` when the
  service is draining.
- `SchedulerAspectsInvalidError` → `400` from checkout with the
  offending field listed.
- Factory protocol exceptions caught at the dispatch boundary: log
  `pychestrate.scheduler.dispatch_failed` and fall back to `FifoScheduler`
  for that single pick only.
- `SemanticError` (e.g. dispatch worker started twice) bubbles per
  AGENTS.md.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- All scheduler APIs are internal. Queue visibility comes through the
  checkout REST layer which already enforces `reservation.read`.
- Aspect normalization protects against DoS via absurd priority or
  deadline values.
- Starvation-recovery activity is recorded in `1-audit-log` (one entry
  per `starvation_promoted` event) so sites can prove fairness SLAs.
- Extensions implementing `reservation_scheduler` run with their
  `E-extension-sandbox` capabilities; the scheduler itself needs no
  outbound capabilities.

## Observability

Metrics:

- `pychestrate_scheduler_queue_depth{pool,algorithm}` — gauge
- `pychestrate_scheduler_wait_duration_seconds{pool,algorithm}` — histogram
- `pychestrate_scheduler_decision_duration_seconds{pool,algorithm}` — histogram
- `pychestrate_scheduler_grant_retry_total{pool}` — counter
- `pychestrate_scheduler_starvation_promoted_total{pool,algorithm}` — counter
- `pychestrate_scheduler_starvation_recovered_total{pool,algorithm}` — counter
- `pychestrate_scheduler_algorithm_fallback{pool}` — gauge

Log events:

- `pychestrate.scheduler.enqueued`
- `pychestrate.scheduler.cancelled`
- `pychestrate.scheduler.algorithm_missing`
- `pychestrate.scheduler.starvation_promoted`
- `pychestrate.scheduler.starvation_blocked`
- `pychestrate.scheduler.dispatch_failed`

Trace spans:

- `pychestrate.scheduler.dispatch` — `pool`, `algorithm`, `queue_depth`,
  `picked`.
- `pychestrate.scheduler.starvation_sweep` — `promoted_count`.

Dashboards: "Scheduler Fairness" panel on `7-resource-metrics` — queue
depth, median wait, starvation-promote rate, algorithm mix.

## Open Questions

- Global fair-share across pools — defer to Phase 5 once per-pool
  fair-share has real workload data.
- Should promotion-once-and-done be enough, or should entries be
  continuously re-prioritized while starving? Current plan:
  `promoted_at` is set once; successive sweeps no-op. Revisit before
  Phase 4 exit.
- Persistence of the in-memory queue snapshot — is the materialized view
  fresh enough for fair-share? If not, fall back to an on-demand
  aggregation query. Timebox: during M3 benchmarking.
