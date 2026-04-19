# 4-lease-heartbeat — Design

## Architecture

Lease tracking is a sibling module to `4-checkout-checkin`. The
authoritative source of truth for lease state is `core.leases`, one row
per active `reservation_id` that opted in. When a reservation is granted
and `lease_kind != "none"`, a `core.leases` row is inserted by a
subscriber on `entity.reservation.granted`. Heartbeats are REST calls
against the reservation path that call into the module and update
`expires_at` by asking the configured `lease_renewal_policy` factory for
a decision. The sweeper is a single-writer worker (one per service
process) that finds expired leases using a partial index, calls
`4-checkout-checkin.release(reservation_id, release_reason="lease_lost")`,
and emits `entity.lease.expired`. Pod leases follow the
pod-as-lock-unit rule: one lease row per pod reservation, not per
member. The 2×TTL guarantee is achieved by running the sweeper at
`ttl_seconds/4` cadence and using `FOR UPDATE SKIP LOCKED` for crash
safety. Ships in Phase 4.

## Data Model

Schema `core`:

- `core.leases`
  - `lease_id: UUID` — PK, v7
  - `reservation_id: UUID` — UNIQUE FK → `core.reservations`
  - `pool_id: UUID | None`
  - `policy_name: str` — snapshot
  - `ttl_seconds: int`
  - `expires_at: datetime` — authoritative expiry time
  - `cap_at: datetime | None` — hard cap from capped policies
  - `last_heartbeat_at: datetime | None`
  - `heartbeat_count: int`
  - `state: LeaseState` — `active` | `capped` | `expired` | `closed`
  - `nearing_expiry_notified: bool` — guards single emission
  - `version: int`
  - `created_at`, `updated_at`

Indices:

- PK on `lease_id`.
- UNIQUE on `reservation_id`.
- INDEX `(state, expires_at)` — the sweeper query.
- INDEX `(pool_id)` — metric aggregation.

## Interfaces

### Public API

REST under `/api/v1/reservations/{reservation_id}`:

- `POST /api/v1/reservations/{reservation_id}:heartbeat` — renew.
- `GET /api/v1/reservations/{reservation_id}/lease` — read lease metadata
  (expires_at, policy_name, last_heartbeat_at, nearing_expiry).

No endpoint exposes `lease_id` directly.

### Internal API

```python
def attach_lease(
    reservation_id: UUID,
    pool_id: UUID | None,
    policy_name: str,
    ttl_seconds: int,
    granted_at: datetime,
    cap_at: datetime | None
) -> Lease:
    """
        Create a Lease row for a just-granted reservation.

        :param reservation_id: The reservation id.
        :param pool_id: The pool the reservation drew from.
        :param policy_name: The renewal-policy factory name.
        :param ttl_seconds: Initial TTL.
        :param granted_at: The reservation grant timestamp.
        :param cap_at: Optional hard cap for capped policies.

        :returns: The persisted Lease.
    """
    ...


def heartbeat(
    reservation_id: UUID,
    actor: UUID,
    aspects: LeaseAspects
) -> Lease:
    """
        Extend a lease via the configured renewal policy.

        :param reservation_id: The reservation id.
        :param actor: The caller.
        :param aspects: Caller-supplied behaviour bundle.

        :returns: The Lease after renewal.
        :raises: LeaseNotFoundError, LeaseAlreadyCappedError,
                 LeaseAlreadyExpiredError (410)
    """
    ...


def run_expiry_sweep(
    tick_ts: datetime,
    batch_size: int
) -> int:
    """
        Expire overdue leases by releasing their reservations.

        :param tick_ts: The current wall-clock tick.
        :param batch_size: Max leases per tick.

        :returns: Number of leases expired.
    """
    ...


def run_nearing_expiry_scan(
    tick_ts: datetime
) -> int:
    """
        Emit pychestrate.lease.nearing_expiry once per at-risk lease.

        :param tick_ts: The current wall-clock tick.

        :returns: Number of events emitted this tick.
    """
    ...
```

### Extension Surface

Factory protocol:

```python
class LeaseRenewalPolicyProtocol(FactoryProtocolBase):
    """
        factory_protocol_name = "lease_renewal_policy"
    """

    @classmethod
    def decide(
        cls,
        lease: Lease,
        heartbeat_ts: datetime,
        aspects: LeaseAspects
    ) -> RenewalDecision:
        """
            Decide the new expires_at for a heartbeat event.

            :param lease: The current lease state.
            :param heartbeat_ts: The wall-clock time of the heartbeat.
            :param aspects: Caller-supplied behaviour bundle.

            :returns: RenewalDecision.extended(new_expires_at) |
                      RenewalDecision.capped(final_expires_at) |
                      RenewalDecision.rejected(reason=..).
        """
        ...
```

In-tree implementations at
`source/site/automojo/factories/pychestrate/lease_renewal_policy/`:

- `FixedTtlRenewalPolicy` — `PRECEDENCE = 1000`; heartbeat bumps
  `expires_at = heartbeat_ts + ttl_seconds`.
- `SlidingRenewalPolicy` — `PRECEDENCE = 1100`; heartbeat bumps
  `expires_at = max(expires_at, heartbeat_ts + ttl_seconds)` with a
  minimum heartbeat interval of 5 s (faster bumps are no-ops).
- `CappedTotalHoldRenewalPolicy` — `PRECEDENCE = 1200`; wraps another
  policy but caps total hold at `cap_at`; once reached, emits
  `.cap_reached` and rejects.
- `DeadlineAwareRenewalPolicy` — `PRECEDENCE = 1300`; caps renewal at
  `aspects.deadline_at` when set.

Test-only `NeverRenewPolicy` at `PRECEDENCE = 100` always returns
`rejected` — exercises the extension-point with a deterministic failure.

### Events Emitted

- `entity.lease.renewed` — `{reservation_id, new_expires_at,
  heartbeat_count}`
- `entity.lease.expired` — `{reservation_id, pool_id, pod_id, ttl_seconds,
  expired_at, last_heartbeat_at}`
- `pychestrate.lease.created` — `{reservation_id, policy_name, ttl_seconds}`
- `pychestrate.lease.cap_reached` — `{reservation_id, final_expires_at}`
- `pychestrate.lease.nearing_expiry` — `{reservation_id, pool_id,
  seconds_remaining}`
- `pychestrate.lease.policy_missing` — `{pool_id, policy_requested}`

### Events Consumed

- `entity.reservation.granted` — when `aspects.lease_kind != "none"`,
  calls `attach_lease`.
- `entity.reservation.released` — closes the lease row (`state=closed`)
  regardless of prior state.
- `extension.reloaded` — rebuild policy bindings.

## Component Breakdown

Under `source/site/automojo/pychestrate/webservice/resources/lease/`:

- `models.py` — `Lease`, `LeaseState`, `LeaseAspects`, `RenewalDecision`.
- `repository.py` — CRUD, sweeper query with `FOR UPDATE SKIP LOCKED`.
- `service.py` — `attach_lease`, `heartbeat`, `close_on_release`.
- `sweeper.py` — background worker, tick cadence = `min(ttl)/4`, min 5s.
- `nearing_expiry.py` — separate scan to emit at-risk events.
- `subscribers.py` — `entity.reservation.granted|released` handlers.
- `api.py` — `POST :heartbeat` and `GET /lease` endpoints.
- `errors.py` — `LeaseNotFoundError`, `LeaseAlreadyCappedError`,
  `LeaseAlreadyExpiredError`.

Policies at `source/site/automojo/factories/pychestrate/lease_renewal_policy/`.

## Key Flows

### Flow 1 — Grant creates a lease

1. Reservation grants, fires `entity.reservation.granted`.
2. Subscriber inspects `aspects.lease_kind`; if `none`, no-op.
3. Otherwise resolve the policy by name via factory registry.
4. `attach_lease(...)` inserts `core.leases` and emits
   `pychestrate.lease.created`.

### Flow 2 — Heartbeat renews

1. `POST /api/v1/reservations/{reservation_id}:heartbeat` arrives.
2. Authz: owner OR `reservation.lease.heartbeat_others`.
3. Load lease; if `state=expired` → `410 Gone` with `last_heartbeat_at`.
4. If `state=capped` → `409` with `final_expires_at`.
5. Call `policy.decide(lease, now, aspects)`:
   - `extended(new_expires_at)` → update row, emit `entity.lease.renewed`,
     observe `pychestrate_lease_heartbeat_interval_seconds`.
   - `capped(final_expires_at)` → set state=`capped`, emit
     `pychestrate.lease.cap_reached`.
   - `rejected(reason)` → `409` with the reason.
6. Return `200` with the new `expires_at`.

### Flow 3 — Sweeper expires dead leases

1. Every tick (`min(ttl_seconds)/4`, bounded ≥ 5s) the sweeper runs:
   `SELECT lease_id, reservation_id FROM core.leases WHERE
   state='active' AND expires_at <= now() ORDER BY expires_at LIMIT
   :batch FOR UPDATE SKIP LOCKED`.
2. For each row: call
   `4-checkout-checkin.release(reservation_id, actor=system,
   release_reason="lease_lost")`; update lease `state=expired,
   expired_at=now()`; emit `entity.lease.expired`.
3. The release transitions the reservation to `released`, clears
   `pod_locked_by` for pod leases, and emits
   `entity.reservation.released`.

### Flow 4 — Nearing-expiry alert

1. Every tick, `run_nearing_expiry_scan` selects active leases where
   `expires_at - now() < ttl_seconds * 0.25` AND
   `nearing_expiry_notified = FALSE`.
2. Emit `pychestrate.lease.nearing_expiry`, set
   `nearing_expiry_notified = TRUE` in the same UPDATE.
3. A subsequent successful heartbeat resets the flag to `FALSE` so a
   late-recovering job can retrigger if it later falls behind again.

## Error Handling

- `LeaseNotFoundError` → `404`.
- `LeaseAlreadyCappedError` → `409` with `final_expires_at`.
- `LeaseAlreadyExpiredError` → `410`.
- Policy exceptions caught at the service boundary → log
  `pychestrate.lease.policy_error`; fall back to
  `FixedTtlRenewalPolicy.decide(...)` once; never let the heartbeat
  return 5xx because a policy crashed.
- `SemanticError` (e.g. `attach_lease` for an already-leased
  reservation) bubbles per AGENTS.md.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- Heartbeat authz: owner OR `reservation.lease.heartbeat_others`.
- TTL clamped to `[10, min(max_reservation_ttl_seconds, 3600)]` at
  `attach_lease` time to prevent heartbeat-storm DoS and unbounded
  holds.
- `lease_id` never leaves the service; REST surface keys exclusively on
  `reservation_id`.
- Force-release (from `4-checkout-checkin`) bypasses lease logic and
  closes the lease row in its own subscriber path.

## Observability

Metrics:

- `pychestrate_lease_created_total{pool,policy}` — counter
- `pychestrate_lease_renewed_total{pool,policy}` — counter
- `pychestrate_lease_expired_total{pool,policy}` — counter
- `pychestrate_lease_cap_reached_total{pool,policy}` — counter
- `pychestrate_lease_heartbeat_interval_seconds{pool}` — histogram
- `pychestrate_lease_ttl_seconds{pool,policy}` — histogram on grant
- `pychestrate_lease_active_count{pool,kind}` — gauge
- `pychestrate_lease_policy_fallback_total{pool}` — counter

Log events:

- `pychestrate.lease.created`
- `pychestrate.lease.renewed`
- `pychestrate.lease.expired`
- `pychestrate.lease.cap_reached`
- `pychestrate.lease.nearing_expiry`
- `pychestrate.lease.policy_missing`
- `pychestrate.lease.policy_error`

Trace spans:

- `pychestrate.lease.heartbeat` — `policy`, `decision`, `new_expires_at`.
- `pychestrate.lease.expiry_sweep` — `expired_count`, `batch_size`.

Dashboards: "Leases" panel on `7-resource-metrics` (active leases,
renewal rate, expired-rate, p95 heartbeat interval, nearing-expiry
gauge).

## Open Questions

- Sweeper cadence with mixed-TTL pools: we derive cadence from
  `min(ttl)` but that might over-poll; consider a per-pool ticker in
  Phase 5.
- Should `DeadlineAwareRenewalPolicy` auto-convert deadline-missed
  leases to `capped` rather than reject? Defer to policy owners.
- Pod-level lease TTL when members have differing recommended TTLs —
  pod currently uses the longest; revisit if pods with a critical-path
  member needing aggressive heartbeat appear.
