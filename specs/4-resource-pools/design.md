# 4-resource-pools — Design

## Architecture

Resource pools sit one layer above `4-resource-inventory` and one layer
below `4-checkout-checkin`. A pool is metadata (name, kind, required tag
set, allocation-strategy protocol name, auto_refresh flag) plus a
materialized membership view of `core.resources`. Pool membership is a
derived projection from inventory; the authoritative source of truth for
membership is still `core.resources`, and pool membership is recomputed in
reaction to `entity.resource.*` events. The `pool.pick(aspects)` code path
delegates to the `pool_allocation_strategy` factory, which is Layer E's
Factory Protocol machinery: the lower numeric `PRECEDENCE` wins, and the
caller passes an `Aspects` object carrying behaviour parameters — we do
not use behaviour-modifying decorators per AGENTS.md.
This feature ships in Phase 4.

## Data Model

Schema `core`:

- `core.resource_pools`
  - `pool_id: UUID` — PK, v7
  - `name: str` — unique per project scope (nullable global pool)
  - `project_id: UUID | None` — FK to `core.projects`; `NULL` means global
  - `kind: str` — resource kind
  - `required_tags: jsonb` — list of tags all members MUST carry
  - `allocation_strategy: str` — factory protocol name
  - `auto_refresh: bool` — default `true`
  - `version: int`
  - `created_at`, `updated_at`, `created_by`

- `core.resource_pool_members` (materialized view of membership)
  - `pool_id: UUID`
  - `resource_id: UUID`
  - `added_at: datetime`
  - PK `(pool_id, resource_id)`

Indices:

- UNIQUE `(project_id, name)` where `project_id` can be `NULL` (partial
  unique with COALESCE).
- INDEX on `(kind)` for event-driven recomputation.

`core.resource_pool_members` is rebuilt on registration / quarantine /
heal / retire / attribute-update events; no tombstone rows kept.

## Interfaces

### Public API

REST under `/api/v1/resource-pools`:

- `POST /api/v1/resource-pools` — create.
- `GET /api/v1/resource-pools/{pool_id}` — fetch with members.
- `GET /api/v1/resource-pools?kind=&project_id=` — list.
- `PATCH /api/v1/resource-pools/{pool_id}` — update metadata.
- `POST /api/v1/resource-pools/{pool_id}:refresh` — force recompute.
- `DELETE /api/v1/resource-pools/{pool_id}` — remove.

### Internal API

```python
def create_pool(
    name: str,
    kind: str,
    required_tags: list[str],
    allocation_strategy: str,
    project_id: UUID | None,
    auto_refresh: bool,
    actor: UserRef
) -> ResourcePool:
    """
        Persist a new resource pool and resolve initial membership.

        :param name: Pool name, unique per project scope.
        :param kind: Resource kind the pool is bound to.
        :param required_tags: Tags every member must carry.
        :param allocation_strategy: Factory protocol name to pick with.
        :param project_id: Owning project, or None for global.
        :param auto_refresh: Recompute on inventory events when True.
        :param actor: The authenticated caller.

        :returns: The persisted ResourcePool with members populated.
        :raises: PoolStrategyUnknownError, PoolKindRejectedError,
                 ResourceKindUnknownError
    """
    ...


def pick_from_pool(
    pool_id: UUID,
    aspects: AllocationAspects
) -> UUID | None:
    """
        Ask the pool's configured strategy for a candidate resource id.

        :param pool_id: The pool id.
        :param aspects: Behaviour parameters passed to the strategy.

        :returns: A candidate resource id, or None when exhausted.
        :raises: PoolNotFoundError
    """
    ...


def recompute_membership(
    pool_id: UUID
) -> list[UUID]:
    """
        Rebuild pool membership from current inventory state.

        :param pool_id: The pool id.

        :returns: The new member list.
    """
    ...


def on_inventory_event(
    event_name: str,
    payload: dict
) -> None:
    """
        Message-bus subscriber: recompute affected pools.

        :param event_name: The fully-qualified event topic.
        :param payload: Event payload.
    """
    ...
```

### Extension Surface

Factory protocol:

```python
class PoolAllocationStrategyProtocol(FactoryProtocolBase):
    """
        Factory protocol for picking a member out of a pool.

        factory_protocol_name = "pool_allocation_strategy"
    """

    @classmethod
    def pick(
        cls,
        aspects: AllocationAspects,
        candidates: list[PoolCandidate]
    ) -> UUID | None:
        """
            Choose a candidate resource id from the live member list.

            :param aspects: Behaviour bundle (tags, job hint, sticky id).
            :param candidates: Live, pickable candidates.

            :returns: The chosen resource id, or None to decline.
        """
        ...
```

In-tree implementations shipped under
`source/site/automojo/factories/pychestrate/pool_allocation/`:

- `FifoAllocationStrategy` — round-robin, `PRECEDENCE = 1000`.
- `LruAllocationStrategy` — oldest-last-used, `PRECEDENCE = 1100`.
- `HealthWeightedAllocationStrategy` — favors probes-passing, `1200`.
- `StickyTagAllocationStrategy` — prefers members matching a caller-
  supplied sticky tag for locality, `1300`.

Test-only override `DeterministicTestAllocationStrategy` at `PRECEDENCE =
100` for extension-point coverage.

### Events Emitted

- `pychestrate.resource.pool.created` — `{pool_id, name, kind, strategy}`
- `pychestrate.resource.pool.refreshed` — `{pool_id, added: [UUID], removed: [UUID]}`
- `pychestrate.resource.pool.deleted` — `{pool_id}`
- `pychestrate.resource.pool.pick_exhausted` — `{pool_id}`
- `pychestrate.resource.pool.pick_strategy_failed` — `{pool_id, strategy, error}`

### Events Consumed

From `0-message-bus` (emitted by `4-resource-inventory`):

- `entity.resource.registered`
- `entity.resource.quarantined`
- `entity.resource.healed`
- `entity.resource.retired`
- `entity.resource.attributes_updated`

## Component Breakdown

All under `source/site/automojo/pychestrate/webservice/resources/pools/`:

- `models.py` — `ResourcePool` dataclass, `PoolCandidate` dataclass.
- `repository.py` — pool CRUD, membership view rebuild.
- `service.py` — orchestrates create, pick, recompute.
- `allocation_aspects.py` — `AllocationAspects` dataclass per AGENTS.md
  Aspects pattern (carries sticky tag, job hint, preferred member).
- `subscribers.py` — `0-message-bus` subscriptions for inventory events.
- `api.py` — Flask-RestX namespace `/api/v1/resource-pools`.
- `errors.py` — `PoolNotFoundError`, `PoolStrategyUnknownError`,
  `PoolKindRejectedError`.

Strategy implementations live under
`source/site/automojo/factories/pychestrate/pool_allocation/`.

## Key Flows

### Flow 1 — Create a pool and materialize members

1. `POST /api/v1/resource-pools` arrives with `{name, kind, required_tags,
   allocation_strategy, project_id, auto_refresh}`.
2. Service resolves `allocation_strategy` against the factory registry; on
   miss, raises `PoolStrategyUnknownError` → `400`.
3. Service checks `kind` is not a `PodMemberKindExtension`; on hit, raises
   `PoolKindRejectedError` → `422`.
4. Inside `unit_of_work`, insert `core.resource_pools`.
5. `recompute_membership(pool_id)` scans
   `core.resources WHERE kind=? AND state='available' AND tags @> required_tags`
   and bulk-inserts into `core.resource_pool_members`.
6. Emit `pychestrate.resource.pool.created`.
7. Return `201`.

### Flow 2 — `pool.pick(aspects)` during dispatch

1. `4-checkout-checkin` calls `pick_from_pool(pool_id, aspects)`.
2. Service loads live membership with a joined query filtering out any
   resource currently reserved (subscribe to `4-checkout-checkin`'s
   reservation table) or not `available`.
3. Strategy lookup: `get_override_types_by_order("pool_allocation_strategy")`
   returns a PRECEDENCE-sorted list; the lowest numeric wins.
4. Call `strategy.pick(aspects, candidates)`.
5. On exception: log `pick_strategy_failed`, call
   `FifoAllocationStrategy.pick` as fallback, increment
   `pychestrate_resource_pool_strategy_fallback_total`.
6. Return the chosen id or `None`.

### Flow 3 — Inventory event rebalances affected pools

1. `entity.resource.attributes_updated` fires on bus.
2. `subscribers.on_inventory_event` looks up every pool whose
   `kind == payload.kind` and whose `required_tags` intersects the
   updated tags.
3. For each such pool with `auto_refresh=true`, `recompute_membership` is
   scheduled on a bounded executor (max 8 concurrent pools).
4. Diff is emitted as `pychestrate.resource.pool.refreshed`.

## Error Handling

- `PoolStrategyUnknownError` → `400`, lists registered strategies.
- `PoolKindRejectedError` → `422`, names the kind and explains pod-member
  constraint.
- `PoolNotFoundError` → `404`.
- `SemanticError` (e.g. `pick_from_pool` called before service start)
  bubbles per AGENTS.md.
- Any exception from a `pool_allocation_strategy` implementation is caught
  *once* at the service boundary, reclassified as a log event + metric +
  fallback pick — not re-raised — because a strategy crash must not fail
  a dispatch.
- Multiline errors built via `os.linesep.join([...])`.

## Security Considerations

- REST permissions via `1-rbac`: `resource.pool.read`,
  `resource.pool.write`, `resource.pool.refresh`.
- `pool.pick` is not exposed externally.
- `1-audit-log` hooks on create / update / delete / refresh.
- Strategy name is validated at persistence time; we never serialize an
  unknown protocol reference to the DB.
- Strategy execution runs with whatever `E-extension-sandbox` capabilities
  are granted (Phase 8); Layer 4 does not need `net:outbound` itself.

## Observability

Metrics:

- `pychestrate_resource_pool_pick_total{pool,strategy,outcome}` — counter
- `pychestrate_resource_pool_pick_duration_seconds{pool,strategy}` — histogram
- `pychestrate_resource_pool_size{pool,state}` — gauge
- `pychestrate_resource_pool_recompute_duration_seconds{pool}` — histogram
- `pychestrate_resource_pool_strategy_fallback_total{pool}` — counter

Log events:

- `pychestrate.resource.pool.created`
- `pychestrate.resource.pool.refreshed`
- `pychestrate.resource.pool.deleted`
- `pychestrate.resource.pool.pick_exhausted`
- `pychestrate.resource.pool.pick_strategy_failed`
- `pychestrate.resource.pool.strategy_missing`

Trace spans:

- `pychestrate.resource.pool.pick` — attributes `pool`, `strategy`,
  `candidates_considered`, `chosen`.
- `pychestrate.resource.pool.recompute` — attributes `pool`,
  `added_count`, `removed_count`.

Dashboards: Pool health tile on `9-admin-ui` (size + picks/min); per-pool
pick-outcome ratio on `7-resource-metrics`.

## Open Questions

- Should a pool support a *dynamic* `required_tags` expression (e.g.
  `"rack=3 AND os='linux'"`) or only a simple ⊇ match? Current model is
  simple superset; defer boolean expressions to Phase 5.
- Should the `pick` operation return an ordered shortlist of candidates to
  let `4-checkout-checkin` retry on conflict, rather than just one id?
  Defer until `4-conflict-deconfliction` wants it.
- Do we eagerly materialize `core.resource_pool_members`, or recompute on
  every `pick`? Current plan is eager; revisit if inventory events exceed
  100/s.
