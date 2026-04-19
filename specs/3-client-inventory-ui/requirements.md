# 3-client-inventory-ui — Requirements

## Introduction

The Client Inventory UI is the operator-facing fleet view of registered
pod clients: one row per client, filterable by project / liveness /
version / capability, with drill-down into `3-client-registry`,
`3-client-capability-advertisement`, and `3-pod-topology-view`. It lives
in Layer 3 and ships in Phase 2 as a *minimal* fleet view; later phases
add richer dashboards. This feature is a thin composition over the
existing REST surfaces plus a new aggregated `clients:inventory`
endpoint used by the Inventory WebComponent. It introduces no new
factory protocols; it does register a `CLISubcommandExtension` via
`8-cli` for scriptable fleet ops (appears in Phase 10 alongside the
CLI), but in Phase 2 the UI is WebComponent-only. Per the architectural
ground rules, all data shown is already server-known — no member probing
— and updates are bounded by the freshness window of heartbeats.

## Requirements

### Requirement 1: The inventory endpoint returns a paged, filtered view in one trip

**User Story:** As an operator triaging a failed pipeline, I want one
endpoint that returns matching clients with enough fields to decide
which to open next, so that the UI does not chatter to the backend.

**Acceptance Criteria (EARS):**

1. WHEN `GET /api/v1/clients:inventory` is called with filter
   parameters THEN the system SHALL return a paginated list of
   `ClientInventoryRow` including `client_id`, `project_id`,
   `pod_name`, `liveness_state`, `last_seen`, `last_agent_version`,
   `transport_name`, `current_pod_state`, and `capability_summary`
   (count per declared searchable kind).
2. IF `project_id` filter is present THEN the response SHALL include
   only clients in that project.
3. WHERE the caller lacks `client.registry.read` globally the
   system SHALL restrict the result to projects on which the caller
   holds that permission.
4. WHEN `sort` and `cursor` parameters are given the system SHALL
   return a stable-ordered page with a `next_cursor` token.

### Requirement 2: Filter predicates support the common triage queries

**User Story:** As an operator, I want to filter by "agent version
older than X" or "lost for more than Y minutes" in the URL, so that
triage dashboards are bookmarkable.

**Acceptance Criteria (EARS):**

1. WHEN `agent_version_lt=<str>` is specified THEN the system SHALL
   include only clients whose `last_agent_version` parses into a
   semver less than the given value.
2. WHEN `lost_since=<duration>` is specified THEN the system SHALL
   include only clients with `liveness_state=lost` and
   `last_seen < now - duration`.
3. WHEN `capability_has=<kind>` is specified THEN the system SHALL
   include only clients with at least one capability row of that
   kind.
4. IF two mutually-exclusive filters are supplied THEN the system
   SHALL respond HTTP 400 with a precise error naming the conflict.

### Requirement 3: Fleet refresh is bounded and progressive

**User Story:** As a dashboard leaving a browser tab open, I want
updates to be incremental rather than full refetches, so that the UI
stays responsive on a 10k-client fleet.

**Acceptance Criteria (EARS):**

1. WHEN the UI calls `GET /api/v1/clients:inventory/changes?since=<ts>`
   THEN the system SHALL return only rows whose
   `updated_at > since` along with a fresh `as_of` timestamp.
2. WHILE the subscriber reads the changes stream via the existing
   `0-message-bus` WebSocket shim the system SHALL emit events for
   `entity.client.*` topics relevant to any visible row.
3. IF `since` is older than `changes_retention_seconds` THEN the
   system SHALL respond HTTP 410 Gone with a message instructing
   the client to refetch the page.

## Property-Based Test Requirements

### Property 1: Page stitching equals a full query

- **Invariant:** For any filter `F` and any page size `n`, the
  concatenation of successive pages using the returned `next_cursor`
  equals the result of the same filter with no pagination, in the
  same order.
- **Generator:** hypothesis strategy generating fleets of 1-2000
  clients, filter predicates randomly chosen, page sizes drawn from
  `integers(1, 500)`.
- **Assertion:** `flatten(paginated(F, n)) == full(F)` as ordered
  lists.
- **Sample size:** 1000 generated cases

### Property 2: Permission scoping is closed under composition

- **Invariant:** For any caller with permission scope `S` and any
  filter `F`, the result set equals
  `filter(full_result(F), lambda r: r.project_id in S)`.
- **Generator:** hypothesis strategy producing random scopes and
  random filters over fleets with clients across 1-10 projects.
- **Assertion:** no `project_id` appears in the result whose row is
  not in `S`; every row in the unscoped result that passes both the
  filter and is in `S` appears in the scoped result.
- **Sample size:** 1000 generated cases

### Property 3: Changes feed is monotonic and replay-safe

- **Invariant:** For any two `changes?since=T1`/`changes?since=T2`
  calls with `T1 <= T2`, the rows returned by the `T2` call are a
  subset of the rows returned by the `T1` call (for overlapping
  windows); replaying the same `since=T1` request twice yields the
  same rows in the same order.
- **Generator:** hypothesis strategy producing random update
  sequences and random `since` window pairs.
- **Assertion:** subset + replay invariants hold.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `:inventory` p99 <= 120 ms for a 10k-client
  fleet with 3 filters; `:inventory/changes` p99 <= 40 ms for a 10k
  fleet with a 60s window.
- **NFR-2 (Security):** RBAC permission `client.inventory.read`;
  per-project filtering honored even when global read is held; no
  capability values in the non-admin response beyond the kind-count
  summary; audit log on admin-view of sensitive capability details
  from a drill-down.
- **NFR-3 (Observability):** metrics
  `pychestrate_client_inventory_reads_total{outcome}`,
  `pychestrate_client_inventory_rows_returned` (histogram),
  `pychestrate_client_inventory_changes_reads_total`,
  `pychestrate_client_inventory_stale_cursors_total`; log events
  `pychestrate_client_inventory_read`,
  `pychestrate_client_inventory_changes_stale_cursor`; trace spans
  `client_inventory.read`, `client_inventory.changes`.
- **NFR-4 (Reliability):** changes stream retention at least 10
  minutes; graceful degradation on timeseries-backend outages (the
  non-time-series fields remain available).

## Out of Scope

- Rich UI widgets for per-client deep inspection — those live in
  `9-admin-ui` and domain-specific widgets.
- Write actions on clients (revoke, drain, pin) — they live in
  sibling features; the UI merely links to their endpoints.
- Real-time streaming updates beyond the changes feed — future phases.
- Pod member inventory — owned by `3-pod-topology-view`.

## Dependencies

- **Depends on:** `3-client-registry`,
  `3-client-capability-advertisement`, `3-pod-lifecycle`,
  `3-pod-topology-view` (for drill-down links),
  `0-message-bus`, `1-rbac`, `9-ui-design-tokens`.
- **Depended on by:** `9-admin-ui`, `8-cli` (fleet listing
  subcommand, Phase 10).
- **Extension points exposed:** none new in Phase 2. In Phase 10 the
  feature registers a `CLISubcommandExtension` for `pycx fleet ls`.
