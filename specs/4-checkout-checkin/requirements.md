# 4-checkout-checkin — Requirements

## Introduction

The `4-checkout-checkin` feature is the reserve/release API for Layer 4: it
converts a "pool + aspects" request into a durable reservation that grants
exclusive or shared access to a concrete `resource_id` (or, for pods, the
whole pod as a single lock unit) and releases it again. Every reservation
carries a reason, an owner, an expiry, and a checkout mode
(`exclusive` / `shared`). The feature is the choke-point that
`5-job-dispatch` blocks against while waiting for resources, and it is
where the `CheckoutValidatorExtension` resource surface plugs in — sites can
add organizational rules ("only this role may check out license seats",
"devices tagged `prod` require a change-ticket id", "pod members MUST NOT
be individually checked out") without forking the core service. Reservation
events (`entity.reservation.created|released|forced_released`) feed the
scheduler, the usage-history timeline, and the audit log.
The feature sits between `4-resource-pools` (source of candidates) and
`4-reservation-scheduler` (source of queued waiters), and it consumes
`4-conflict-deconfliction` for per-resource compatibility rules. Pod
checkout is the lock unit: pod members are NOT independently reservable
while their parent pod is held. Ships in Phase 4.

## Requirements

### Requirement 1: Reserve a Resource via a Pool or a Pod

**User Story:** As a job dispatcher, I want to reserve either a single
resource from a pool or a whole pod as one lock unit, so that the job can
safely run without contention.

**Acceptance Criteria (EARS):**

1. WHEN `POST /api/v1/reservations` is called with
   `{target: {pool_id}, mode, reason, owner, expires_at, aspects}` AND a
   candidate is available THEN the system SHALL persist a `Reservation` in
   state `granted`, emit `entity.reservation.created` with
   `entity.reservation.granted` immediately after, and return `201` with
   the reservation including `resource_id`.
2. IF the target is `{pod_id}` THEN the system SHALL reserve the pod as
   the lock unit and SHALL mark every pod-member `resource_id` as
   `pod_locked`, refusing any independent checkout of those members until
   the pod reservation is released.
3. IF no candidate is available AND `aspects.wait_strategy == "queue"`
   THEN the system SHALL enqueue the request via `4-reservation-scheduler`,
   emit `entity.reservation.queued`, and return `202` with a
   `reservation_id` that resolves to `granted` later.
4. WHERE every loaded `CheckoutValidatorExtension` returns `allow` THEN
   the checkout proceeds; otherwise the first `deny(reason)` SHALL short-
   circuit the reservation with `403` and the returned body MUST include
   the validator name and the deny reason.

### Requirement 2: Release Returns the Resource Cleanly

**User Story:** As a job client, I want release to be idempotent and
observable, so that crash-retry at the client side doesn't double-free.

**Acceptance Criteria (EARS):**

1. WHEN `DELETE /api/v1/reservations/{reservation_id}` is called by the
   reservation's owner THEN the system SHALL move the reservation to state
   `released`, emit `entity.reservation.released`, and return `204`.
2. IF the caller is NOT the reservation owner AND lacks permission
   `reservation.force_release` THEN the system SHALL reject with `403`
   and SHALL NOT mutate state.
3. IF `DELETE` is called against an already-`released` reservation THEN
   the system SHALL return `204` without re-emitting
   `entity.reservation.released` (idempotent).
4. WHERE an operator with `reservation.force_release` calls
   `POST /api/v1/reservations/{reservation_id}:force-release` THEN the
   system SHALL move the reservation to `released`, emit
   `entity.reservation.forced_released` with the actor and reason, and
   record the action in `1-audit-log`.

### Requirement 3: Expiry and Leak Prevention

**User Story:** As an operator, I want unreleased reservations to expire
automatically, so that crashed jobs do not leak resources.

**Acceptance Criteria (EARS):**

1. WHILE a reservation's `expires_at <= now()` AND state is `granted`
   THEN the system SHALL transition it to `released`, emit
   `entity.reservation.released` with `release_reason: expired`, and
   increment `pychestrate_reservation_expired_total`.
2. IF a caller PATCHes `{expires_at: <new>}` where `<new> - now()` exceeds
   `max_reservation_ttl_seconds` THEN the system SHALL reject with `400`.
3. WHERE a pod reservation expires THEN the system SHALL also clear the
   `pod_locked` marker on every member atomically in the same
   transaction.
4. WHEN every pod member is released together THEN the system SHALL NOT
   emit per-member `entity.reservation.released` — only one pod-level event
   fires because the pod is the lock unit.

### Requirement 4: No Independent Pod-Member Checkout

**User Story:** As a pod owner, I want checkout of a pod-member kind to be
rejected while the parent pod is reserved, so that members are only
accessed through the pod contract.

**Acceptance Criteria (EARS):**

1. IF a caller requests a reservation against a `resource_id` that is
   currently `pod_locked` THEN the system SHALL reject with `409` and the
   body MUST name the holding `pod_reservation_id`.
2. WHEN a pod is released THEN the system SHALL clear `pod_locked` on
   every member before returning the release response.
3. WHERE a resource kind is declared by a `PodMemberKindExtension` AND the
   resource is NOT currently under any pod reservation THEN independent
   checkout SHALL be permitted (pod membership is a runtime lock, not a
   schema rule).

## Property-Based Test Requirements

### Property 1: No Resource Leaks Across Matched Checkout/Release Streams

- **Invariant:** For any sequence of valid checkouts C and matching
  releases R where |C| = |R| (releases can be for any granted
  reservation, interleaved arbitrarily), the final resource-leak count is
  0 — no resource remains in state `granted` and no pod member remains
  `pod_locked`.
- **Generator:**
  `hypothesis.strategies.lists(sampled_from(["checkout", "release"]),
  min_size=2, max_size=200)` coupled with `integers(min_value=0,
  max_value=resource_count-1)` to pick targets. Runs against a pool of
  size in `[1, 16]` with a mix of exclusive and shared modes.
- **Assertion:** After replaying the sequence and calling release for
  every granted id at the end, `count(state='granted') == 0` and
  `count(pod_locked=True) == 0`.
- **Sample size:** 1000 generated cases.

### Property 2: Concurrent Exclusive Checkouts Serialize

- **Invariant:** For any set of concurrent checkout attempts against the
  same resource in `mode=exclusive`, exactly one succeeds; every other
  attempt either queues (if `wait_strategy=queue`) or returns `409`
  (`wait_strategy=fail_fast`).
- **Generator:**
  `hypothesis.strategies.lists(tuples(sampled_from(["queue",
  "fail_fast"]), text()), min_size=2, max_size=64)` fanned out across N
  worker threads racing on a one-member pool.
- **Assertion:** `sum(1 for r in results if r.state == "granted" and
  r.at_grant_time < first_release) == 1` and no pair of granted times
  overlaps with any other granted window on the same resource.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Reservation checkout p99 < 25 ms end to end
  when a candidate is available (measured to `entity.reservation.granted`
  emission). Release p99 < 15 ms. Expiry sweep SHALL process ≥ 5,000
  reservations per second on a single worker.
- **NFR-2 (Security):** Checkout requires `reservation.create`; release
  requires ownership OR `reservation.force_release`. Reason field is
  required and stored verbatim; it is emitted in audit events and log
  records. Reservations are project-scoped; cross-project checkout is
  rejected with `403`.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_reservation_created_total{pool,kind,mode}`,
  `pychestrate_reservation_released_total{pool,kind,release_reason}`,
  `pychestrate_reservation_forced_released_total{pool,kind}`,
  `pychestrate_reservation_expired_total{pool,kind}`,
  `pychestrate_reservation_queue_depth{pool}` (gauge),
  `pychestrate_reservation_checkout_duration_seconds{pool,mode}`
  (histogram), `pychestrate_reservation_active{pool,mode}` (gauge),
  `pychestrate_reservation_validator_denied_total{validator}`. Log
  events `pychestrate.reservation.created`,
  `pychestrate.reservation.released`,
  `pychestrate.reservation.forced_released`,
  `pychestrate.reservation.expired`,
  `pychestrate.reservation.validator_denied`. Trace span
  `pychestrate.reservation.checkout` with attributes `pool`, `mode`,
  `validator_count`, `wait_strategy`, `outcome`.
- **NFR-4 (Reliability):** The expiry sweeper is crash-safe: a service
  restart mid-sweep does not lose expiries and does not double-release.
  Release operations are idempotent. The `pod_locked` marker is cleared
  in the same DB transaction as the pod reservation state change.

## Out of Scope

- Queue scheduling decisions (see `4-reservation-scheduler`).
- Conflict-rule evaluation beyond "is the resource free?" (see
  `4-conflict-deconfliction`).
- Lease heartbeats and dead-client auto-release (see `4-lease-heartbeat`).
- Resource health evaluation (see `4-resource-health`).

## Dependencies

- **Depends on:** `4-resource-inventory`, `4-resource-pools`,
  `4-conflict-deconfliction` (for per-checkout rule evaluation),
  `4-reservation-scheduler` (for queued path), `0-persistence`,
  `0-message-bus`, `1-rbac`, `1-audit-log`, `3-pod-definitions`.
- **Depended on by:** `4-lease-heartbeat`, `4-usage-history`,
  `5-job-dispatch`.
- **Extension points exposed:** `resource: CheckoutValidatorExtension` —
  site-specific allow/deny rules applied before checkout is granted;
  `event: entity.reservation.created`,
  `entity.reservation.released`, `entity.reservation.forced_released`,
  `entity.reservation.queued`, `entity.reservation.granted`.
