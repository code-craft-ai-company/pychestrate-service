# 4-checkout-checkin — Design

## Architecture

Checkout/checkin is the transactional heart of Layer 4. It owns the
`core.reservations` table (authoritative source of truth for who holds
what), maintains the `pod_locked` flag on member resource rows, and
mediates the reserve/release API. Checkout is a three-phase operation:
(1) pick a candidate via `4-resource-pools`, (2) run every loaded
`CheckoutValidatorExtension` and every relevant `ConflictRuleExtension`,
(3) commit the reservation in a single DB transaction. If no candidate is
available the request is forwarded to `4-reservation-scheduler` which
holds a queue and later calls back through the same `grant_reservation`
internal path. Release is idempotent and atomic. Expiry runs as a
background sweeper using row-level locks. Pod reservations lock every
member in the same transaction, and only a single pod-level event fires
on create/release. Ships in Phase 4.

## Data Model

Schema `core`:

- `core.reservations`
  - `reservation_id: UUID` — PK, v7
  - `project_id: UUID` — FK, NOT NULL
  - `pool_id: UUID | None` — source pool (NULL for pod reservations)
  - `resource_id: UUID | None` — concrete resource (NULL for pod targets)
  - `pod_id: UUID | None` — populated for pod reservations
  - `mode: ReservationMode` — `exclusive` | `shared`
  - `state: ReservationState` — `queued` | `granted` | `released`
  - `owner: UUID` — FK to `users.id`
  - `reason: str` — free text, required
  - `aspects: jsonb` — the `ReservationAspects` object, opaque to core
  - `expires_at: datetime | None`
  - `granted_at: datetime | None`
  - `released_at: datetime | None`
  - `release_reason: str | None` — `explicit` | `expired` | `forced` | `lease_lost`
  - `version: int`
  - `created_at`, `updated_at`

Indices:

- PK on `reservation_id`.
- UNIQUE partial `(resource_id) WHERE state='granted' AND mode='exclusive'`
  — the exclusivity constraint enforced by the DB.
- INDEX `(pool_id, state)`.
- INDEX `(expires_at) WHERE state='granted' AND expires_at IS NOT NULL`
  for the sweeper.
- INDEX `(pod_id) WHERE state='granted'`.

Resources get a derived column maintained by the reservation service:

- `core.resources.pod_locked_by: UUID | None` — set when a pod reservation
  grants, cleared on release; column owned by this feature.

## Interfaces

### Public API

REST under `/api/v1/reservations`:

- `POST /api/v1/reservations` — checkout. Body:
  `{target: {pool_id} | {pod_id}, mode, reason, owner, expires_at,
  aspects, wait_strategy}`.
- `GET /api/v1/reservations/{reservation_id}`.
- `GET /api/v1/reservations?pool_id=&state=&owner=`.
- `PATCH /api/v1/reservations/{reservation_id}` — update `expires_at`
  and `reason` only.
- `DELETE /api/v1/reservations/{reservation_id}` — owner release,
  idempotent.
- `POST /api/v1/reservations/{reservation_id}:force-release` — operator
  override requiring `reservation.force_release`.

### Internal API

```python
def reserve(
    target: ReservationTarget,
    mode: ReservationMode,
    reason: str,
    owner: UUID,
    expires_at: datetime | None,
    aspects: ReservationAspects,
    wait_strategy: WaitStrategy
) -> Reservation:
    """
        Attempt to grant a reservation, queue it, or fail fast.

        :param target: Either {pool_id} or {pod_id}.
        :param mode: Exclusive or shared.
        :param reason: Required human-readable reason.
        :param owner: Authenticated caller id.
        :param expires_at: Optional expiry; None uses pool default.
        :param aspects: Aspects bundle (sticky tag, job hint, lease kind).
        :param wait_strategy: queue | fail_fast.

        :returns: A Reservation in state granted or queued.
        :raises: ReservationDeniedError, ReservationConflictError,
                 PodMemberLockedError, PoolExhaustedError
    """
    ...


def release(
    reservation_id: UUID,
    actor: UUID,
    release_reason: str
) -> Reservation:
    """
        Release a granted reservation. Idempotent.

        :param reservation_id: The reservation id.
        :param actor: The caller.
        :param release_reason: One of explicit, expired, forced, lease_lost.

        :returns: The Reservation after release.
        :raises: ReservationNotOwnedError
    """
    ...


def force_release(
    reservation_id: UUID,
    actor: UUID,
    reason: str
) -> Reservation:
    """
        Force-release a reservation. Requires reservation.force_release.

        :param reservation_id: The reservation id.
        :param actor: The operator performing the force.
        :param reason: Operator-supplied justification, audited.

        :returns: The Reservation after release.
    """
    ...


def grant_from_queue(
    reservation_id: UUID
) -> Reservation:
    """
        Move a queued reservation to granted once capacity frees up.
        Called by 4-reservation-scheduler.

        :param reservation_id: The queued reservation id.

        :returns: The Reservation in state granted.
        :raises: ReservationConflictError
    """
    ...


def run_expiry_sweep(
    batch_size: int
) -> int:
    """
        Release every granted reservation whose expires_at has passed.

        :param batch_size: Max number of reservations per sweep tick.

        :returns: Number of reservations expired in this tick.
    """
    ...
```

### Extension Surface

Resource extension:

```python
class CheckoutValidatorExtension(ResourceExtension):
    """
        Site-specific allow/deny gate run before checkout commits.

        Subclasses declare:
          - validator_name: str
          - applies_to_kinds: tuple[str, ...] — or () for all kinds
    """
    validator_name: str
    applies_to_kinds: tuple

    @classmethod
    def validate_checkout(
        cls,
        request: CheckoutRequest,
        candidate: Resource
    ) -> ValidatorDecision:
        """
            Allow or deny the checkout.

            :param request: The full checkout request (owner, reason,
                            aspects, mode, target).
            :param candidate: The candidate resource chosen by the pool.

            :returns: ValidatorDecision.allow() or .deny(reason=..).
        """
        ...
```

Reference implementations shipped in-tree under
`source/site/ccai/extensions/pychestrate/resources/checkout_validators/`:

- `RequireReasonValidator` — reason must be non-empty, ≥ 8 chars.
- `PodMemberExclusionValidator` — rejects direct checkout of
  `pod_locked_by != NULL` resources (belt-and-suspenders for Requirement 4).
- `ProjectScopeValidator` — candidate must be in the caller's project.

Test-only `AlwaysDenyValidator` shipped under `tests/` for extension-point
coverage.

### Events Emitted

On `0-message-bus`:

- `entity.reservation.created` — `{reservation_id, pool_id, pod_id,
  resource_id, mode, owner, reason, expires_at}`
- `entity.reservation.queued` — `{reservation_id, pool_id, owner, reason}`
- `entity.reservation.granted` — `{reservation_id, resource_id, pod_id,
  mode, granted_at, from_queue: bool}`
- `entity.reservation.released` — `{reservation_id, resource_id, pod_id,
  release_reason, duration_seconds}`
- `entity.reservation.forced_released` — `{reservation_id, actor, reason}`

Note: `created` fires first; `granted` fires immediately after for
synchronous grants, or later (when the scheduler hands the slot back) for
queued ones.

### Events Consumed

- `entity.resource.quarantined` — if a granted reservation's resource is
  quarantined by `4-resource-health`, we emit a warning log but do NOT
  auto-release; operator decides via force_release.
- `entity.lease.expired` — from `4-lease-heartbeat`; the handler calls
  `release(release_reason="lease_lost")`.

## Component Breakdown

Under `source/site/ccai/pychestrate/webservice/resources/checkout/`:

- `models.py` — `Reservation`, `ReservationMode`, `ReservationState`,
  `ReservationAspects`, `ReservationTarget`, `WaitStrategy`.
- `repository.py` — reservation CRUD with the DB-enforced uniqueness
  constraint on exclusive grants.
- `service.py` — orchestrates `reserve`, `release`, `force_release`,
  `grant_from_queue`.
- `validator_pipeline.py` — runs `CheckoutValidatorExtension` subclasses
  in order; short-circuits on first deny.
- `pod_lock.py` — atomic `pod_locked_by` set/clear helpers.
- `expiry_sweeper.py` — background task, uses SELECT ... FOR UPDATE SKIP
  LOCKED for crash safety.
- `subscribers.py` — `entity.lease.expired`,
  `entity.resource.quarantined`.
- `api.py` — Flask-RestX namespace `/api/v1/reservations`.
- `errors.py` — `ReservationDeniedError`, `ReservationConflictError`,
  `ReservationNotOwnedError`, `PodMemberLockedError`, `PoolExhaustedError`.

## Key Flows

### Flow 1 — Checkout against a pool

1. `POST /api/v1/reservations` arrives with `target={pool_id}`.
2. Service calls `pick_from_pool(pool_id, aspects)` → candidate or `None`.
3. If `None`: `wait_strategy=queue` forwards to
   `4-reservation-scheduler.enqueue(...)` which persists `state=queued`,
   emits `entity.reservation.queued`, returns `202`.
4. If candidate: run `CheckoutValidatorExtension` pipeline over every
   in-scope validator. First `deny` → `ReservationDeniedError` → `403`,
   emit `pychestrate.reservation.validator_denied`.
5. Run `4-conflict-deconfliction.evaluate(candidate, request)`. Any rule
   violation → `ReservationConflictError` → `409`.
6. Inside `unit_of_work`: insert reservation `(state='granted')`; the DB
   unique partial index on `(resource_id) WHERE state='granted' AND
   mode='exclusive'` makes a concurrent-exclusive-winner race atomic.
7. Emit `entity.reservation.created`, then `entity.reservation.granted`
   with `from_queue=false`.
8. Return `201`.

### Flow 2 — Pod checkout locks every member

1. `POST /api/v1/reservations` arrives with `target={pod_id}`.
2. Service resolves pod members from `3-pod-definitions`.
3. Validator pipeline runs with the pod as the candidate bundle (not a
   single `Resource`).
4. Inside `unit_of_work`: insert the pod reservation; update every member
   `resources` row to `pod_locked_by=<reservation_id>` in a single UPDATE
   with `WHERE pod_locked_by IS NULL`. If rowcount != expected, raise
   `PodMemberLockedError` → `409`.
5. Emit a single `entity.reservation.granted` carrying `pod_id` and
   `resource_id=None`; do NOT emit per-member events.
6. On release: set `state='released'`, clear `pod_locked_by` on every
   member, emit one `entity.reservation.released`.

### Flow 3 — Expiry sweep

1. `expiry_sweeper` runs every 1s on a single worker per service.
2. `SELECT reservation_id FROM core.reservations WHERE state='granted'
   AND expires_at <= now() ORDER BY expires_at LIMIT :batch_size FOR
   UPDATE SKIP LOCKED`.
3. For each row: call `release(reservation_id, actor=system,
   release_reason="expired")`.
4. Increment `pychestrate_reservation_expired_total`; emit
   `pychestrate.reservation.expired`.

### Flow 4 — Scheduler grants a queued reservation

1. `4-reservation-scheduler` decides the next waiter.
2. Calls `grant_from_queue(reservation_id)`.
3. Service re-runs validator pipeline and conflict rules (freshness is
   important; the resource state may have changed since enqueue).
4. On success, moves `state` from `queued` to `granted`, emits
   `entity.reservation.granted` with `from_queue=true`.

## Error Handling

- `ReservationDeniedError` → `403`, body names the validator and reason.
- `ReservationConflictError` → `409`, body names the conflict rule.
- `ReservationNotOwnedError` → `403`.
- `PodMemberLockedError` → `409`, body names the holding pod reservation.
- `PoolExhaustedError` → `202` when `wait_strategy=queue`, `409` when
  `fail_fast`.
- `SemanticError` (e.g. release called with malformed
  `release_reason`) bubbles per AGENTS.md.
- The DB uniqueness-constraint violation on exclusive grant races is
  caught at the repository boundary and reclassified to
  `ReservationConflictError`:

```python
err_msg_lines = ["Exclusive checkout lost the race."]
err_msg_lines.append("POOL: {}".format(pool_id))
err_msg_lines.append("RESOURCE_ID: {}".format(candidate.resource_id))
err_msg_lines.append("WINNING RESERVATION: {}".format(winning_id))

err_msg = os.linesep.join(err_msg_lines)
raise ReservationConflictError(err_msg) from cause
```

## Security Considerations

- `reservation.create`, `reservation.release`, `reservation.force_release`,
  `reservation.read` permissions from `1-rbac`.
- Project-scope enforced by `ProjectScopeValidator`.
- Reason is required, stored verbatim, and copied into
  `1-audit-log` for every create / release / force-release.
- Force-release is always audited with actor + reason; a force-release
  without reason returns `400`.
- Validators and conflict rules run with their granted
  `E-extension-sandbox` capabilities (Phase 8); checkout itself requires
  no outbound capabilities.

## Observability

Metrics:

- `pychestrate_reservation_created_total{pool,kind,mode}` — counter
- `pychestrate_reservation_released_total{pool,kind,release_reason}` — counter
- `pychestrate_reservation_forced_released_total{pool,kind}` — counter
- `pychestrate_reservation_expired_total{pool,kind}` — counter
- `pychestrate_reservation_queue_depth{pool}` — gauge
- `pychestrate_reservation_checkout_duration_seconds{pool,mode}` — histogram
- `pychestrate_reservation_active{pool,mode}` — gauge
- `pychestrate_reservation_validator_denied_total{validator}` — counter

Log events:

- `pychestrate.reservation.created`
- `pychestrate.reservation.queued`
- `pychestrate.reservation.granted`
- `pychestrate.reservation.released`
- `pychestrate.reservation.forced_released`
- `pychestrate.reservation.expired`
- `pychestrate.reservation.validator_denied`

Trace spans:

- `pychestrate.reservation.checkout` — `pool`, `mode`, `validator_count`,
  `wait_strategy`, `outcome`.
- `pychestrate.reservation.release` — `release_reason`.
- `pychestrate.reservation.expiry_sweep` — `expired_count`.

Dashboards: "Resource Broker" panel on `7-resource-metrics` (grants/min,
queue depth per pool, median wait, expiry rate, force-release rate).

## Open Questions

- Should `mode=shared` grant without exclusivity constraint at the DB
  level (we rely only on conflict rules)? Current plan: yes, shared
  grants skip the unique partial index; revisit if shared semantics
  diversify.
- Should expiry auto-release be delayed by a small grace period so that
  a heartbeat in-flight wins? Current plan: no grace; heartbeats push
  `expires_at` forward. Revisit if we see spurious expiries.
- How do we handle an `entity.resource.retired` event while a granted
  reservation still points to it? Current plan: reject the retire (in
  `4-resource-inventory`) while active reservations exist; timebox
  before Phase 4 exit.
