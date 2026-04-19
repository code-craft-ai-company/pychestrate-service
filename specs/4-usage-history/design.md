# 4-usage-history — Design

## Architecture

Usage history is a passive recorder — it subscribes to `0-message-bus`
and writes immutable rows to `core.resource_timeline_events`. It never
initiates state changes, never mutates existing timeline rows, and is
the authoritative source for per-resource activity history. A separate
rollup worker computes small, fixed-window aggregates into
`core.resource_usage_rollups` for UI and dashboard consumption. An
optional extension surface, `UsageAnalyticsHookExtension`, decorates
each row with annotations before persist — hooks run in PRECEDENCE
order, collisions keep the lower-precedence value, and any crash is
contained to a single hook. Pod events expand to per-member rows plus a
pod-level row linked by `pod_event_group_id`. Idempotence keys on
`(event_id, resource_id)` so at-least-once bus delivery never produces
duplicates. Ships in Phase 4.

## Data Model

Schema `core`:

- `core.resource_timeline_events`
  - `event_row_id: UUID` — PK, v7
  - `event_id: UUID` — FROM bus envelope, for idempotence
  - `resource_id: UUID`
  - `event_type: str` — the bus topic
  - `at_ts: datetime` — event wall-clock
  - `actor: UUID | None`
  - `reservation_id: UUID | None`
  - `pod_id: UUID | None`
  - `pod_event_group_id: UUID | None` — links member rows to the pod row
  - `is_member_expansion: bool`
  - `payload: jsonb` — redacted copy of bus payload
  - `annotations: jsonb` — merged hook output
  - `post_retention: bool` — flag for late-arriving events
  - `ingested_at: datetime`

Indices:

- PK on `event_row_id`.
- UNIQUE on `(event_id, resource_id)` — idempotence.
- INDEX on `(resource_id, at_ts DESC)` — timeline query.
- INDEX on `(event_type, at_ts DESC)` — cross-resource analytics.
- INDEX on `(pod_event_group_id)` — pod expansion lookups.

- `core.resource_usage_rollups`
  - `resource_id: UUID`
  - `window: RollupWindow` — `w24h | w7d | w30d`
  - `granted_count: int`
  - `release_count: int`
  - `forced_release_count: int`
  - `held_seconds: int`
  - `quarantined_seconds: int`
  - `last_good_age_seconds: int | None`
  - `computed_at: datetime`
  - `payload_hash: str` — dedupe equal rollups
  - PK `(resource_id, window)`.

Indices:

- PK.
- INDEX on `(window, computed_at DESC)`.

## Interfaces

### Public API

REST under `/api/v1/resources/{resource_id}`:

- `GET /api/v1/resources/{resource_id}/timeline?since=&until=&
  event_types=&include_pod_member_expansion=` — paged timeline rows.
- `GET /api/v1/resources/{resource_id}/usage-rollups?window=` — return
  the prebuilt rollup for the window.

### Internal API

```python
def append_timeline_event(
    bus_event: BusEvent,
    inventory_snapshot: Resource
) -> list[ResourceTimelineEvent]:
    """
        Transform a bus event into one or more timeline rows,
        decorate via hooks, and persist idempotently.

        :param bus_event: The envelope delivered from 0-message-bus.
        :param inventory_snapshot: The current Resource row for
                                   sensitive-attr redaction.

        :returns: The persisted timeline rows (1 for resource events,
                  1 + n_members for pod events).
    """
    ...


def run_rollup_tick(
    tick_ts: datetime
) -> int:
    """
        Recompute rollups for resources with events in any window.

        :param tick_ts: Wall-clock tick.

        :returns: Number of rollup rows written (not all resources —
                  idempotent skips are counted as 0).
    """
    ...


def query_timeline(
    resource_id: UUID,
    since: datetime,
    until: datetime,
    event_types: list[str] | None,
    include_pod_member_expansion: bool,
    limit: int,
    offset: int
) -> list[ResourceTimelineEvent]:
    """
        Return matching rows sorted by at_ts ascending.

        :param resource_id: Resource id.
        :param since: Window start (inclusive).
        :param until: Window end (exclusive).
        :param event_types: Optional filter.
        :param include_pod_member_expansion: Include per-member rows.
        :param limit: Page size.
        :param offset: Page offset.

        :returns: Timeline rows.
    """
    ...
```

### Extension Surface

Resource extension:

```python
class UsageAnalyticsHookExtension(ResourceExtension):
    """
        Hook invoked once per timeline-event persist to attach
        annotations. Hooks MUST NOT perform side effects outside of
        returning annotations; they MUST complete in < 20 ms p99.

        Subclasses declare:
          - hook_name: str
          - applies_to_event_types: tuple[str, ...] | None
    """
    hook_name: str
    applies_to_event_types: tuple | None

    @classmethod
    def decorate(
        cls,
        event: BusEvent,
        context: UsageHookContext
    ) -> dict:
        """
            Return a flat dict of string annotations to merge.

            :param event: The bus event.
            :param context: Read-only snapshot of resource, reservation,
                            actor.

            :returns: {key: value} of string annotations.
        """
        ...
```

In-tree implementations under
`source/site/automojo/extensions/pychestrate/resources/usage_hooks/`:

- `ProjectAttributionHook` — records `project_id`, `project_name`.
- `OwnerTeamHook` — records `owner_team` from the owner's `1-user-management`
  team membership.
- `ReservationDurationHook` — on release events, computes
  `held_seconds` from prior grant row.
- `QuarantineSpanHook` — on heal events, computes
  `quarantined_seconds` from prior quarantine row.

Test-only `AlwaysCrashHook` under `tests/` for extension-point coverage.

### Events Emitted

- `pychestrate.resource.usage.hook_error` — `{hook_name, event_type, error}`
- `pychestrate.resource.usage.hook_key_collision` — `{hook_a, hook_b,
  key}`
- `pychestrate.resource.usage.forced_release_burst` — `{resource_id,
  window, ratio}`
- `pychestrate.resource.usage.post_retention_event` — `{resource_id,
  event_type, at_ts}`

### Events Consumed

From `0-message-bus`:

- `entity.resource.registered`
- `entity.resource.quarantined`
- `entity.resource.healed`
- `entity.resource.retired`
- `entity.reservation.granted`
- `entity.reservation.released`
- `entity.reservation.forced_released`
- `entity.lease.renewed`
- `entity.lease.expired`
- `extension.reloaded` — rebuild hook registry.

## Component Breakdown

Under `source/site/automojo/pychestrate/webservice/resources/usage_history/`:

- `models.py` — `ResourceTimelineEvent`, `ResourceUsageRollup`,
  `RollupWindow`, `UsageHookContext`.
- `repository.py` — append (idempotent) and query helpers.
- `subscribers.py` — bus subscriptions and event-to-row translation.
- `pod_expansion.py` — single-responsibility helper for pod member
  expansion.
- `hook_pipeline.py` — runs `UsageAnalyticsHookExtension.decorate`,
  merges results with collision logging.
- `rollup_worker.py` — 60s tick.
- `api.py` — `/timeline` and `/usage-rollups` endpoints.

Hooks at
`source/site/automojo/extensions/pychestrate/resources/usage_hooks/`.

## Key Flows

### Flow 1 — Grant event flows into the timeline

1. `entity.reservation.granted` arrives with payload including
   `reservation_id`, `resource_id`, `mode`, `granted_at`, `owner`.
2. `subscribers.on_reservation_granted(event)` loads the
   inventory snapshot (for redaction).
3. Hook pipeline runs each `UsageAnalyticsHookExtension.decorate`:
   - `ReservationDurationHook` skipped (applies only to releases).
   - `ProjectAttributionHook` adds `{project_id, project_name}`.
   - `OwnerTeamHook` adds `{owner_team}`.
4. Annotations merged with lower-PRECEDENCE-wins; `hook_key_collision`
   logged on conflict.
5. Row inserted with UNIQUE `(event_id, resource_id)` — replay is
   swallowed by the constraint.

### Flow 2 — Pod release expands to member rows

1. `entity.reservation.released` arrives with `pod_id` set.
2. `pod_expansion.expand_pod_event(event)` resolves members from
   `3-pod-definitions`, generates one row per member plus a pod-level
   row; all share `pod_event_group_id=<new UUID>`.
3. Hook pipeline runs once per row; hooks see the individual member
   context.

### Flow 3 — Rollup tick

1. Every 60s, `run_rollup_tick(now)` selects resources with any
   timeline activity since `last_rollup_at`.
2. For each resource / window pair, compute the aggregate by a single
   `SELECT ...` over `core.resource_timeline_events`.
3. Hash the aggregate tuple; if `payload_hash` matches existing rollup,
   skip. Otherwise UPSERT.
4. If `forced_release_count / granted_count > threshold`, emit
   `pychestrate.resource.usage.forced_release_burst` (throttled to
   once per hour per resource).

### Flow 4 — Timeline query

1. `GET /api/v1/resources/{resource_id}/timeline?since=&until=` loads
   rows using the `(resource_id, at_ts DESC)` index.
2. `include_pod_member_expansion=false` adds predicate
   `is_member_expansion = FALSE`.
3. Window > 30d requires `resource.usage.deep_history_read`; otherwise
   `403`.

## Error Handling

- Hook exceptions caught at hook boundary and translated to an error
  log + metric increment; the event is still persisted with annotations
  from surviving hooks.
- `SemanticError` (e.g. double subscribe) bubbles per AGENTS.md.
- Idempotence-constraint violation on replay is swallowed silently —
  that is the design.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- Timeline payloads are redacted through each kind's `render_public`
  before persist; no sensitive attribute cleartext lands in jsonb.
- `resource.usage.read` gates windows ≤ 30d;
  `resource.usage.deep_history_read` gates deep scans.
- Hook extensions run with their `E-extension-sandbox` capabilities;
  in-tree hooks require no outbound capabilities.
- Hooks MUST NOT attempt to mutate the event or write anywhere else;
  the `UsageHookContext` is read-only.

## Observability

Metrics:

- `pychestrate_resource_usage_rows_appended_total{event_type,kind}` — counter
- `pychestrate_resource_usage_hook_duration_seconds{hook}` — histogram
- `pychestrate_resource_usage_hook_error_total{hook}` — counter
- `pychestrate_resource_usage_rollup_duration_seconds{window}` — histogram
- `pychestrate_resource_usage_rollup_writes_total{window}` — counter
- `pychestrate_resource_usage_timeline_query_duration_seconds{window_days}` — histogram
- `pychestrate_resource_usage_hook_key_collision_total` — counter

Log events:

- `pychestrate.resource.usage.hook_error`
- `pychestrate.resource.usage.hook_key_collision`
- `pychestrate.resource.usage.forced_release_burst`
- `pychestrate.resource.usage.post_retention_event`

Trace spans:

- `pychestrate.resource.usage.append` — `event_type`, `hook_count`,
  `annotation_count`.
- `pychestrate.resource.usage.rollup_tick` — `resources_scanned`,
  `writes`.

Dashboards: "Resource Usage" panel on `7-resource-metrics` — append rate,
top 20 resources by held_seconds, forced-release-burst list.

## Open Questions

- Do we keep every lease-renew event (potentially high volume) or
  sample them? Current plan: keep all; revisit if append rate exceeds
  10k/sec.
- Should rollups store p95 hold-duration too, or only sums? Current
  plan: sums only in Phase 4; percentiles may come in Phase 9 via
  `7-resource-metrics`.
- Retention of timeline rows: tied into `2-retention-policies` once
  that feature ships; defaults to 180 days. Timebox: Phase 10 when
  `2-retention-policies` lands.
