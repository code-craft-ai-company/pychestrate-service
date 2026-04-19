# 4-resource-pools — Requirements

## Introduction

The `4-resource-pools` feature groups inventory resources into
capability-tagged pools that jobs target by *capability*, not by
`resource_id`. A pool is a named set of candidate resources sharing a
required capability profile (e.g. "rack-3-wifi-ap", "ipv6-subnet-lab-east",
"vendor-acme-license-seat"). Pools are the allocation unit consumed by
`4-checkout-checkin` and the scheduler in `4-reservation-scheduler`; which
specific member is handed out to a caller is decided by the pool's
`pool_allocation_strategy` — a `FactoryProtocolBase` subclass that is
Pychestrate's primary extension surface for picking *how* a resource is
chosen (round-robin, least-recently-used, health-weighted, cost-weighted,
sticky-by-tag, custom).
This feature sits between `4-resource-inventory` (it owns no resources, only
views into inventory) and `4-checkout-checkin` (it answers the question
"which candidate?"). Pod members are never independently poolable — pod
checkout is the lock unit — so pool membership for pod-member kinds is
declared at the pod level and resolved during pod reservation. This feature
ships in Phase 4.

## Requirements

### Requirement 1: Define Pools by Capability Tag and Kind

**User Story:** As a lab administrator, I want to define pools that select
resources by required capability tags, so that jobs can target
"any-wifi-ap-in-rack-3" rather than a specific device id.

**Acceptance Criteria (EARS):**

1. WHEN an administrator POSTs `POST /api/v1/resource-pools` with `{name,
   kind, required_tags, allocation_strategy}` THEN the system SHALL persist
   a `ResourcePool` row, resolve initial membership by scanning the
   inventory for matching `(kind, tags ⊇ required_tags, state=available)`,
   and return the pool with current members.
2. IF `allocation_strategy` names a protocol the factory registry does not
   provide THEN the system SHALL reject the request with `400` and list
   every currently-registered strategy name.
3. WHILE a resource's tag set changes via
   `entity.resource.attributes_updated` the system SHALL recompute
   membership for every pool whose `required_tags` intersects the changed
   tags.
4. WHERE `kind` is declared by a `PodMemberKindExtension` (i.e. the
   resource is a pod member) the system SHALL reject pool creation with
   `422` — pod members are only allocatable via their parent pod.

### Requirement 2: Allocation Strategy Picks the Member

**User Story:** As a scheduler, I want to ask a pool for a candidate
without knowing which member I'll get, so that I can delegate "how" to
whichever strategy the pool was configured with.

**Acceptance Criteria (EARS):**

1. WHEN `pool.pick(aspects)` is called AND the pool has at least one
   member in state `available` AND no active reservation THEN the system
   SHALL delegate the selection to the pool's configured
   `pool_allocation_strategy` and return exactly one candidate
   `resource_id`.
2. IF every member is held, quarantined, or retired THEN the system SHALL
   return `None` and emit `pychestrate.resource.pool.pick_exhausted`.
3. WHERE two strategies are registered under the same protocol name with
   different `PRECEDENCE` values THEN the system SHALL invoke the lower
   numeric PRECEDENCE one.
4. IF the configured strategy raises any exception THEN the system SHALL
   log `pychestrate.resource.pool.pick_strategy_failed` and fall back to
   the in-tree `FifoAllocationStrategy` for that single pick only.

### Requirement 3: Pool Membership Stays Consistent with Inventory

**User Story:** As an operator, I want pool membership to reflect inventory
reality without a reconciliation batch, so that I trust what I see on the
UI.

**Acceptance Criteria (EARS):**

1. WHEN `entity.resource.registered` fires for a resource whose `(kind,
   tags)` match a pool's `required_tags` THEN the system SHALL add the
   resource to the pool's membership within 100 ms.
2. WHEN `entity.resource.retired` or `.quarantined` fires THEN the system
   SHALL remove the resource from every pool that contained it within
   100 ms.
3. WHILE an `entity.resource.healed` event is consumed THEN the system
   SHALL re-evaluate membership for every pool matching the resource's
   `(kind, tags)`.
4. WHERE a pool has `auto_refresh: false` THEN the system SHALL NOT
   recompute membership on inventory events; the admin must call
   `POST /api/v1/resource-pools/{pool_id}:refresh` to do so.

## Property-Based Test Requirements

### Property 1: Allocation Covers Only Live Members

- **Invariant:** For any pool P and any sequence of `pool.pick(aspects)`
  calls, every returned `resource_id` is a current member of P and is in
  state `available` at the moment of the pick.
- **Generator:** A Hypothesis strategy that builds a pool with N random
  members, interleaves `quarantine` / `heal` / `retire` operations across
  members, and calls `pick` from M threads. N in `[1, 32]`, M in `[1, 16]`.
- **Assertion:** `all(pick in live_members_at(ts) for pick, ts in picks)`
  and `no pick is ever a quarantined or retired member`.
- **Sample size:** 1000 generated cases.

### Property 2: FIFO Strategy Preserves Fairness

- **Invariant:** For any pool P configured with
  `FifoAllocationStrategy` and any sequence of interleaved
  `pick → release` pairs, the gap between a given member's most-recent and
  least-recent pick never exceeds `len(P.members) + 1` consecutive picks
  over any sliding window of `10 * len(P.members)` picks.
- **Generator:**
  `hypothesis.strategies.lists(sampled_from(["pick", "release"]),
  min_size=20, max_size=500)` driving a synthetic workload over a pool of
  size in `[2, 16]`.
- **Assertion:** The computed max-gap statistic never breaches
  `len(members) + 1` across the window.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** `pool.pick(aspects)` p99 < 3 ms on a pool with
  ≤ 512 members. Pool creation `POST` p99 < 100 ms on a 50k inventory.
  Membership recomputation on an inventory event p99 < 100 ms across all
  affected pools.
- **NFR-2 (Security):** Pool CRUD requires `resource.pool.write`; pool read
  requires `resource.pool.read`; `pool.pick` is internal-only and is not
  exposed over REST. The allocation-strategy name MUST be matched against
  the loaded factory registry before persistence to avoid storing
  references to unknown strategies.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_resource_pool_pick_total{pool,strategy,outcome}`,
  `pychestrate_resource_pool_pick_duration_seconds{pool,strategy}`
  (histogram), `pychestrate_resource_pool_size{pool,state}` (gauge),
  `pychestrate_resource_pool_recompute_duration_seconds{pool}` (histogram),
  `pychestrate_resource_pool_strategy_fallback_total{pool}`. Log events
  `pychestrate.resource.pool.created`,
  `pychestrate.resource.pool.pick_exhausted`,
  `pychestrate.resource.pool.pick_strategy_failed`. Trace span
  `pychestrate.resource.pool.pick` with attributes `pool`, `strategy`,
  `candidates_considered`.
- **NFR-4 (Reliability):** If the `pool_allocation_strategy` factory is
  missing at service start (extension not installed), the pool is
  automatically pinned to `FifoAllocationStrategy` and
  `pychestrate.resource.pool.strategy_missing` is logged once at startup.
  Membership recomputation is idempotent: replaying an inventory event
  stream converges to the correct set.

## Out of Scope

- Reserving/releasing resources (see `4-checkout-checkin`).
- Queueing and priority (see `4-reservation-scheduler`).
- Health-based eligibility computation (see `4-resource-health` feeds
  state changes which we react to).
- Per-allocation *conflict* rules like subnet overlap (see
  `4-conflict-deconfliction`).

## Dependencies

- **Depends on:** `4-resource-inventory`, `0-message-bus`, `0-persistence`,
  `1-rbac`, `2-tagging`, `E-factory-protocols`.
- **Depended on by:** `4-checkout-checkin`, `4-reservation-scheduler`,
  `5-job-dispatch`.
- **Extension points exposed:** `factory: pool_allocation_strategy` — declares
  `pick(aspects, candidates) -> resource_id | None`. In-tree reference:
  `FifoAllocationStrategy`. Ships in-tree alongside
  `LruAllocationStrategy`, `HealthWeightedAllocationStrategy`,
  `StickyTagAllocationStrategy`.
