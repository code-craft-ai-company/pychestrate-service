# 4-lease-heartbeat — Requirements

## Introduction

The `4-lease-heartbeat` feature layers lease-with-renewal semantics on top
of `4-checkout-checkin`: every granted reservation carries a lease that
expires unless the holder keeps it alive with periodic heartbeats. When a
holder's pod client crashes or partitions, heartbeats stop, the lease
expires, and the reservation is released automatically — preventing
dead-job resource leaks. Heartbeat cadence, grace periods, and renewal
policy are behavior parameters bundled into a `LeaseAspects` object; the
way renewal decisions are made (sliding vs fixed TTL, exponential-backoff
extension, capped-total-hold) is delegated to the
`lease_renewal_policy` factory protocol — Pychestrate ships sliding,
fixed-ttl, capped, and deadline-aware policies in tree and extensions
add their own. Dead-job auto-release is the key guarantee: a lease whose
heartbeats have stopped MUST be released within 2× the lease duration so
that the pool never leaks capacity indefinitely.
Pod leases behave as a single lock unit: a pod heartbeat releases the
entire pod at once on expiry, matching `4-checkout-checkin`'s pod-as-lock
rule. Ships in Phase 4.

## Requirements

### Requirement 1: Grant-Time Lease Attachment

**User Story:** As a job client, I want every reservation I take to carry
a lease with a clear TTL and renewal contract, so that my job knows how
often to heartbeat.

**Acceptance Criteria (EARS):**

1. WHEN `entity.reservation.granted` fires AND the originating request's
   `aspects.lease_kind != "none"` THEN the system SHALL create a
   `Lease` row with `lease_id`, `reservation_id`, `ttl_seconds`,
   `expires_at = granted_at + ttl_seconds`, and `policy_name` recorded
   from the pool or aspects override.
2. IF the lease policy is not in the loaded factory registry THEN the
   system SHALL fall back to `FixedTtlRenewalPolicy` with
   `ttl_seconds = 300` and log
   `pychestrate.lease.policy_missing` exactly once.
3. WHERE the aspects bundle sets `lease_kind="none"` THEN the reservation
   SHALL remain classic (no lease, no heartbeat) and this feature SHALL
   NOT create a `Lease` row.
4. WHERE the reservation target is a pod THEN the system SHALL create a
   single pod-scoped lease, not one per member, preserving the
   pod-as-lock-unit invariant.

### Requirement 2: Heartbeat-Based Renewal

**User Story:** As a job client, I want to keep my reservation alive by
calling a simple heartbeat endpoint, so that long-running jobs don't
need to pre-negotiate a huge TTL.

**Acceptance Criteria (EARS):**

1. WHEN `POST /api/v1/reservations/{reservation_id}:heartbeat` is called
   by the reservation's owner THEN the system SHALL delegate to the
   configured `lease_renewal_policy`, receive a new `expires_at`, and
   persist it.
2. IF the caller is not the reservation owner AND lacks
   `reservation.lease.heartbeat_others` permission THEN the system
   SHALL reject with `403`.
3. IF the heartbeat arrives AFTER `expires_at` AND the lease was already
   released as `lease_lost` THEN the system SHALL return `410 Gone`
   with a body naming the release time — the holder MUST re-request.
4. WHERE the renewal policy returns
   `RenewalDecision.capped(final_expires_at)` THEN the system SHALL
   record the final expiry, emit `pychestrate.lease.cap_reached`, and
   reject subsequent heartbeats against that lease with `409` and a
   body naming `final_expires_at`.

### Requirement 3: Dead-Holder Auto-Release Within 2× Lease Duration

**User Story:** As an operator, I want dead holders to free resources
without human intervention, so that my pool never leaks capacity.

**Acceptance Criteria (EARS):**

1. WHILE a lease's `expires_at < now()` AND the reservation state is
   `granted` THEN the system SHALL release the reservation with
   `release_reason="lease_lost"`, emit `entity.lease.expired` and
   `entity.reservation.released`, and close the lease row.
2. WHEN a lease expires THEN the end-to-end time from last successful
   heartbeat (or grant, if no heartbeat arrived) to
   `entity.reservation.released` SHALL NOT exceed `2 * ttl_seconds`
   under normal conditions (sweeper running, no DB outage).
3. WHERE a pod lease expires THEN the system SHALL release the
   pod-level reservation — which in turn clears `pod_locked_by` on
   every member in the same transaction — and emit one pod-level
   `entity.lease.expired` event, not per-member.

### Requirement 4: Observable Liveness

**User Story:** As an on-call engineer, I want to see per-pool "holders
at risk" so I can act on stuck jobs before they expire.

**Acceptance Criteria (EARS):**

1. WHEN a lease's time-to-expiry drops below `ttl_seconds * 0.25` AND
   the sweeper runs THEN the system SHALL emit
   `pychestrate.lease.nearing_expiry` exactly once per lease with
   `reservation_id`, `pool_id`, `seconds_remaining`.
2. WHEN a lease is renewed THEN the system SHALL emit
   `entity.lease.renewed` and observe the interval since the prior
   heartbeat on `pychestrate_lease_heartbeat_interval_seconds`.
3. WHILE the sweeper is running the system SHALL maintain the gauge
   `pychestrate_lease_active_count{pool,kind}` to reflect active
   leases, updated each tick.

## Property-Based Test Requirements

### Property 1: Expiring Heartbeats Release Within 2× Lease Duration

- **Invariant:** For any lease with initial TTL `T` whose heartbeats
  stop at time `t0`, the reservation transitions to `released` with
  `release_reason="lease_lost"` by `t0 + 2*T` under a running sweeper.
- **Generator:** Hypothesis strategy producing `T in [30, 600]` seconds
  simulated, a heartbeat sequence that stops at a random `t0`, and a
  renewal policy chosen from the in-tree set. The sweeper's tick
  interval is fixed at `T/4`.
- **Assertion:** For every such trace, `released_at <= t0 + 2*T` and
  `release_reason == "lease_lost"`.
- **Sample size:** 1000 generated cases.

### Property 2: Valid Heartbeats Preserve the Lease

- **Invariant:** For any sequence of heartbeats arriving strictly before
  `expires_at`, the lease is never released with `lease_lost` — its
  state remains `granted` until an explicit release or the policy's cap
  triggers.
- **Generator:** Hypothesis strategy emitting heartbeat arrivals
  uniformly inside each current `[granted_at, expires_at]` window,
  across 1..100 heartbeats per trace.
- **Assertion:** After replaying the trace, `release_reason` is either
  `None`, `explicit`, or `capped` — never `lease_lost`.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Heartbeat endpoint p99 < 10 ms end to end.
  Sweeper processes ≥ 5,000 leases/sec/worker. Scanning the lease table
  to pick expiring leases uses a partial index and returns in under
  50 ms for 100k active leases.
- **NFR-2 (Security):** Heartbeat requires ownership OR
  `reservation.lease.heartbeat_others`. Minimum TTL is 10 s to prevent
  heartbeat-storm DoS; maximum TTL is
  `min(max_reservation_ttl_seconds, 3600)`. The `lease_id` is not
  exposed externally — all API surface keys on `reservation_id`.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_lease_created_total{pool,policy}`,
  `pychestrate_lease_renewed_total{pool,policy}`,
  `pychestrate_lease_expired_total{pool,policy}`,
  `pychestrate_lease_cap_reached_total{pool,policy}`,
  `pychestrate_lease_heartbeat_interval_seconds{pool}` (histogram),
  `pychestrate_lease_ttl_seconds{pool,policy}` (histogram on grant),
  `pychestrate_lease_active_count{pool,kind}` (gauge). Log events
  `pychestrate.lease.created`, `.renewed`, `.expired`, `.cap_reached`,
  `.nearing_expiry`, `.policy_missing`. Trace span
  `pychestrate.lease.heartbeat` with attributes `policy`, `decision`,
  `new_expires_at`.
- **NFR-4 (Reliability):** The sweeper is crash-safe (uses `FOR UPDATE
  SKIP LOCKED`). A DB outage pauses sweeping; on recovery the sweeper
  catches up and still meets the 2×TTL bound provided the outage is
  shorter than one full TTL window. If the outage exceeds TTL, all
  overdue leases are processed in the next tick and alerts fire.

## Out of Scope

- The reservation lifecycle itself (see `4-checkout-checkin`).
- Detecting a dead pod client at the transport layer (see
  `3-client-agent-protocol` heartbeat — Layer 4 heartbeats are about
  resource leases, not client liveness; they are complementary signals).
- Health probes on the resource (see `4-resource-health`) — a healthy
  resource with a dead holder still expires here.
- Usage analytics on lease durations (see `4-usage-history`).

## Dependencies

- **Depends on:** `4-checkout-checkin`, `4-resource-pools`,
  `0-persistence`, `0-message-bus`, `E-factory-protocols`, `1-rbac`.
- **Depended on by:** `4-checkout-checkin` (subscribes to
  `entity.lease.expired` to release), `4-usage-history`, `5-job-dispatch`
  (jobs whose client dies get their reservations released).
- **Extension points exposed:** `factory: lease_renewal_policy` —
  `SlidingRenewalPolicy`, `FixedTtlRenewalPolicy`,
  `CappedTotalHoldRenewalPolicy`, `DeadlineAwareRenewalPolicy` in-tree.
