# 3-client-inventory-ui — Tasks

## Milestones

- **M1 — Skeleton:** `:inventory` REST aggregator with filter parsing
  and permission scoping; minimal WebComponent renders a table with
  default columns.
- **M2 — Core Behavior:** Changes feed, cursor-based pagination,
  bus-subscriber change-log wiring, sorted stable pages, rate limits.
- **M3 — Hardening:** Retention sweep, cursor signing, metrics, perf
  target, WebComponent polish + themability.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Migration pack: `client_inventory_change_log` table with
  indices.
- [ ] T1.2 — DTOs `ClientInventoryRow`, `InventoryPage`,
  `InventoryChange`, `CapabilitySummary`.
- [ ] T1.3 — `InventoryRepository` with three-way join
  (`client`, `pod_runtime_state`, `client_capability`).
- [ ] T1.4 — `filters.py` parsing project_id / liveness /
  agent_version_lt / lost_since / capability_has.
- [ ] T1.5 — `service.read_inventory` with caller-scope intersect.
- [ ] T1.6 — REST `GET /clients:inventory`.
- [ ] T1.7 — WebComponent `<pcx-client-inventory>` rendering the
  default 8-column table and emitting `pcx-client-selected` events.

### M2 — Core Behavior

- [ ] T2.1 — Bus subscribers writing `client_inventory_change_log`
  rows for each of the six observed topics.
- [ ] T2.2 — `service.read_changes` with project-scope intersect.
- [ ] T2.3 — REST `GET /clients:inventory/changes`.
- [ ] T2.4 — Cursor encode/decode with HMAC signing; stable sort
  tuple `(updated_at desc, client_id desc)`.
- [ ] T2.5 — Rate limits: 60 rpm `:inventory`, 600 rpm
  `:inventory/changes`.
- [ ] T2.6 — WebComponent polls `:inventory/changes` on
  `auto-refresh` interval; reconciles rows locally.
- [ ] T2.7 — Mutually-exclusive filter detection with precise error
  bodies.

### M3 — Hardening

- [ ] T3.1 — `sweeper.py` deletes rows older than
  `changes_retention_seconds` every minute.
- [ ] T3.2 — Stale-cursor detection + HTTP 410 handling with a
  UI-friendly body.
- [ ] T3.3 — Emit all metrics in design.md Observability.
- [ ] T3.4 — Trace spans `client_inventory.read`,
  `client_inventory.changes`, `client_inventory.sweep`.
- [ ] T3.5 — Perf validation: 10k-client fleet; `:inventory` p99 <=
  120 ms; `:inventory/changes` p99 <= 40 ms.
- [ ] T3.6 — WebComponent theming via `9-ui-design-tokens` CSS
  custom properties; dark/light variants validated.
- [ ] T3.7 — Sphinx docs for REST + the WebComponent's attribute /
  event contract.

## Test Tasks

- [ ] TT-1 — Unit tests for each EARS clause in Requirements 1-3.
- [ ] TT-2 — Hypothesis tests for Property 1 (page stitching),
  Property 2 (permission-scope composition), Property 3 (changes-feed
  monotonicity and replay-safety).
- [ ] TT-3 — Integration test: seed 200 clients across 5 projects;
  caller scoped to 2 projects sees only those; filter
  `agent_version_lt=2.0.0` returns the correct subset; changes feed
  reflects a follow-on capability advertisement.
- [ ] TT-4 — WebComponent test: component renders, responds to
  `auto-refresh`, emits `pcx-client-selected` on row click, handles a
  410 response by clearing its cache and restarting pagination.
- [ ] TT-5 — Stale-cursor test: a forged cursor is rejected; a
  retention-stale cursor returns 410 with the intended body.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] WebComponent passes `9-ui-design-tokens` theme contract checks.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated for REST and WebComponent contracts.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Definition of Done for Phase 2 in
  specs/implementation-plan.md (minimal slice), with Phase 10 noted
  for the CLI subcommand extension.
