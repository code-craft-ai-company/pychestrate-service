# 4-reservation-scheduler — Requirements

## Introduction

The `4-reservation-scheduler` feature is the queue-and-fairness layer sitting
between `4-checkout-checkin` and `4-resource-pools`. When a caller requests
a reservation and no candidate is immediately available, the scheduler
enqueues the request and decides *when* and *in what order* waiting
reservations are granted as capacity frees up. The ordering decision is
delegated to the `reservation_scheduler` factory protocol — Pychestrate
ships FIFO, priority, fair-share, and deadline-aware implementations in
tree, and external packs add their own. Each scheduler consumes a
`SchedulerAspects` bundle (priority, fair-share key, deadline hint, owner
policy) and returns the next queued reservation that should be granted.
The scheduler is also the "starvation police": it MUST guarantee that
deadline-missed jobs are not starved indefinitely, and it emits the
metrics that make fairness auditable.
This feature sits downstream of `4-checkout-checkin` (which enqueues) and
upstream of it again (the scheduler calls back into
`grant_from_queue`). Pod reservations respect the same scheduler: a pod is
a single lock unit, so the scheduler never tries to partially grant pod
members. Ships in Phase 4.

## Requirements

### Requirement 1: Enqueue and Dispatch Waiting Reservations

**User Story:** As the checkout service, I want to hand off a would-be-waiter
to the scheduler and be called back when it can be granted, so that I do not
block a request thread.

**Acceptance Criteria (EARS):**

1. WHEN `scheduler.enqueue(reservation_id, pool_id, aspects)` is called
   THEN the system SHALL persist a `SchedulerEntry`, emit
   `pychestrate.scheduler.enqueued`, and register the pool-id on the
   wakeup index.
2. WHEN `entity.reservation.released` fires for a reservation against
   `pool_id=P` THEN the scheduler SHALL pick the next entry for `P`
   according to the configured algorithm and call
   `checkout.grant_from_queue(reservation_id)` within 50 ms.
3. IF `grant_from_queue` returns `ReservationConflictError` THEN the
   scheduler SHALL leave the entry in the queue, increment
   `pychestrate_scheduler_grant_retry_total`, and try the next-best
   candidate on the same pool.
4. WHERE the caller cancels a queued reservation via
   `DELETE /api/v1/reservations/{id}` THEN the scheduler SHALL remove the
   entry idempotently and emit `pychestrate.scheduler.cancelled`.

### Requirement 2: Pluggable Ordering Algorithm

**User Story:** As a project owner, I want to choose the scheduler algorithm
per pool (FIFO / priority / fair-share / deadline / custom), so that my
fairness policy matches my workload.

**Acceptance Criteria (EARS):**

1. WHEN a pool declares `scheduler_algorithm="fair_share"` THEN the
   scheduler SHALL load the `FairShareScheduler` implementation via the
   `reservation_scheduler` factory protocol by name, not by hard-coded
   import.
2. IF the pool's declared algorithm is not in the loaded factory registry
   THEN the scheduler SHALL fall back to `FifoScheduler`, log
   `pychestrate.scheduler.algorithm_missing` once per pool, and emit a
   gauge `pychestrate_scheduler_algorithm_fallback=1`.
3. WHERE two implementations share the factory protocol name, the lower
   numeric `PRECEDENCE` SHALL win.
4. WHILE the service is draining (maintenance mode) the scheduler SHALL
   continue to drain its queues (grant on releases) but SHALL NOT accept
   new enqueues; `scheduler.enqueue` SHALL raise
   `SchedulerUnavailableError`.

### Requirement 3: Deadline-Missed Jobs Are Not Starved

**User Story:** As an on-call engineer, I want the scheduler to guarantee
that a queued reservation with a missed deadline is eventually granted,
so that "unfair" policies cannot starve a job forever.

**Acceptance Criteria (EARS):**

1. WHILE a queued entry's `deadline_at < now() - starvation_threshold`
   (default `starvation_threshold = 2 * median_wait_seconds`, min 30s)
   THEN the scheduler SHALL promote that entry to the head of its pool's
   queue on the next dispatch tick and emit
   `pychestrate.scheduler.starvation_promoted` with `waited_seconds`.
2. IF an entry has been promoted AND is still not granted after one
   additional capacity cycle THEN the scheduler SHALL emit
   `pychestrate.scheduler.starvation_blocked` with the blocking rule
   category (`conflict`, `validator`, `pool_empty`) so operators can see
   *why* the starving job can't be granted.
3. WHEN an entry is granted after a promotion THEN the system SHALL
   increment `pychestrate_scheduler_starvation_recovered_total` and log
   `waited_seconds` and `deadline_missed_by_seconds`.

### Requirement 4: Fair-Share Weights Are Stable Under Churn

**User Story:** As a project owner, I want fair-share to converge across
owners regardless of enqueue order, so that a burst from one owner does
not starve quieter owners.

**Acceptance Criteria (EARS):**

1. WHEN `FairShareScheduler.pick()` is called THEN the system SHALL return
   the entry minimizing `(running_seconds_for_owner + queued_wait_seconds)
   / fair_share_weight`, breaking ties by earliest `enqueued_at`.
2. IF two owners share the same fair-share weight THEN over any window of
   `N = 100` grants the count difference between the two owners SHALL not
   exceed `2` provided both owners have continuously-queued entries.
3. WHERE an aspects bundle sets `fair_share_key = "<team>:<ci_pipeline>"`
   THEN the scheduler SHALL key accounting on that composite, not on the
   owner user-id.

## Property-Based Test Requirements

### Property 1: Deadline-Missed Jobs Are Eventually Granted

- **Invariant:** For any scheduler algorithm A and any sequence of
  enqueue / release operations over a bounded horizon, a queued entry
  with a past deadline is granted before a second full queue-cycle has
  elapsed — i.e. no deadline-missed job is indefinitely starved.
- **Generator:** Hypothesis strategy composing an `Algorithm`
  (`sampled_from(["fifo", "priority", "fair_share", "deadline",
  "adversarial_custom"])`), a sequence of enqueue events with random
  deadlines / priorities / owners, and release events sampled from the
  active grants.
- **Assertion:** For every entry `e` with `e.deadline_at <
  e.enqueued_at`, `e.granted_at - e.deadline_at < 2 *
  median_wait_seconds + 30s`, i.e. starvation-recovery fires within
  bound.
- **Sample size:** 1000 generated cases.

### Property 2: Release-Driven Dispatch Latency Bound

- **Invariant:** For any release event followed by a non-empty queue on
  the same pool, some queued entry transitions to `granted` within
  `SCHEDULER_DISPATCH_BUDGET_SECONDS = 0.050` seconds of the release
  event's timestamp (assuming no validator/conflict denies).
- **Generator:**
  `hypothesis.strategies.lists(tuples(enqueue_spec, release_spec),
  min_size=2, max_size=64)` replayed against a stubbed checkout backend
  that accepts all grants.
- **Assertion:** `all(granted_at - release_ts <= 0.050 for every
  release_ts that triggered a grant)`.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Scheduler decision time p99 < 5 ms at a queue
  depth of 1,000 entries per pool (i.e. `pick_next` returns in that
  budget). End-to-end release → grant-from-queue p99 < 50 ms. Enqueue p99
  < 8 ms.
- **NFR-2 (Security):** Enqueue is internal-only. Priority and fair-share
  weights come from `SchedulerAspects` and MUST be normalized: a caller
  cannot specify negative priority, fair-share weight > `10.0`, or a
  deadline more than `max_reservation_ttl_seconds` into the future.
  Input-normalization rejections return `400` to the checkout service and
  never reach the DB.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_scheduler_queue_depth{pool,algorithm}` (gauge),
  `pychestrate_scheduler_wait_duration_seconds{pool,algorithm}`
  (histogram, observed on grant), `pychestrate_scheduler_decision_duration_seconds{pool,algorithm}`
  (histogram), `pychestrate_scheduler_grant_retry_total{pool}` (counter),
  `pychestrate_scheduler_starvation_promoted_total{pool,algorithm}`,
  `pychestrate_scheduler_starvation_recovered_total{pool,algorithm}`,
  `pychestrate_scheduler_algorithm_fallback{pool}` (gauge). Log events
  `pychestrate.scheduler.enqueued`, `.cancelled`, `.algorithm_missing`,
  `.starvation_promoted`, `.starvation_blocked`. Trace span
  `pychestrate.scheduler.dispatch` with attributes `pool`, `algorithm`,
  `queue_depth`, `picked`.
- **NFR-4 (Reliability):** Scheduler state is persisted in
  `core.scheduler_entries`; a service restart re-hydrates the queue and
  no waiter is lost. Dispatch on restart processes any entries whose
  pools have free capacity immediately.

## Out of Scope

- The checkout and release transaction itself (see `4-checkout-checkin`).
- Resource health (see `4-resource-health`) — scheduler consumes health
  only indirectly through the pool's live-member count.
- Lease heartbeats (see `4-lease-heartbeat`) — affect release timing but
  scheduler does not heartbeat.
- Cross-pool global fairness — initial implementation is per-pool; global
  fair-share is future work.

## Dependencies

- **Depends on:** `4-checkout-checkin`, `4-resource-pools`, `0-message-bus`,
  `0-persistence`, `E-factory-protocols`.
- **Depended on by:** `4-checkout-checkin` (callback path),
  `5-job-dispatch`.
- **Extension points exposed:** `factory: reservation_scheduler` —
  implementations: `FifoScheduler`, `PriorityScheduler`,
  `FairShareScheduler`, `DeadlineScheduler`, plus out-of-tree customs.
