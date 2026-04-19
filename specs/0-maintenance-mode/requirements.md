# 0-maintenance-mode — Requirements

## Introduction

The `0-maintenance-mode` feature provides a runtime read-only / drain
switch scoped to the whole service, a single project, or (future) a
specific pod. It is consumed by every write-bearing feature
(`0-object-store`, `0-persistence`, `5-job-dispatch`,
`5-run-state-machine`, `4-checkout-checkin`, etc.) to reject mutations
cleanly while allowing reads. Per the implementation plan it lands in
**Phase 10** alongside admin UI, but its interface and event contract are
defined here so every Phase 0 sibling can integrate against a stub
implementation from day one. Sits between `0-persistence` (source of
truth for maintenance state), `0-message-bus` (change broadcast), and
every feature that honors the gate.

## Requirements

### Requirement 1: Scoped Maintenance State

**User Story:** As a service operator, I want to put a single project or
the whole service into read-only mode, so that I can perform maintenance
(backfills, schema changes, infra cutovers) without accepting writes that
will fail downstream.

**Acceptance Criteria (EARS):**

1. WHEN an admin POSTs to `/api/v1/admin/maintenance` with body
   `{scope: "service" | "project:<slug>", mode: "active" | "read_only" |
   "draining", reason: str, ends_at: datetime | None}` AND the caller
   holds permission `pychestrate.maintenance.manage` THEN the system
   SHALL persist the change AND publish `maintenance.mode.changed` on
   `0-message-bus`.
2. IF two scopes overlap (service + project) THEN the more restrictive
   mode SHALL apply: `draining` > `read_only` > `active`.
3. WHERE `ends_at` is in the past the system SHALL treat the scope as
   `active` regardless of the stored mode value AND emit
   `maintenance.mode.auto_expired` exactly once.
4. WHEN a feature queries `maintenance_gate.status(scope)` THEN the
   system SHALL return the current effective mode within 1 ms (cache
   hit) without hitting the database.

### Requirement 2: Write Rejection With Retry Hints

**User Story:** As a REST API client, I want a machine-readable rejection
when my write is blocked by maintenance, so that I can back off and retry
rather than interpret a generic 503.

**Acceptance Criteria (EARS):**

1. WHEN a write request targets a scope currently in `read_only` mode
   THEN the system SHALL respond with HTTP `503 Service Unavailable`,
   header `Retry-After: <seconds>`, body
   `{"error": "maintenance_mode", "scope": "...", "mode": "read_only",
   "reason": "...", "ends_at": "..."}`.
2. IF a write request targets a scope in `draining` mode THEN the system
   SHALL respond with HTTP `503` AND include header `X-Draining: true`.
3. WHILE a scope is in `read_only` mode the system SHALL continue to
   serve reads that do not require a transaction (GET / HEAD /
   `query_range` / `query_instant`).
4. WHERE a scope is in `draining` mode the system SHALL serve only
   `/__health/live`, `/__health/ready`, and `/api/v1/admin/maintenance`.

### Requirement 3: Event-Driven Gate Fanout

**User Story:** As a feature (object store, job dispatcher, entity
repository), I want a fast in-process gate that updates via bus events,
so that I do not re-hit the DB on every write.

**Acceptance Criteria (EARS):**

1. WHEN `maintenance.mode.changed` is published THEN the system SHALL
   deliver the event to every subscribed feature within 50 ms median on
   the in-process bus.
2. IF a feature subscriber crashes THEN the system SHALL catch and log
   via `0-message-bus`'s subscriber isolation AND SHALL NOT leave the
   gate in an inconsistent state — the gate re-reads from the DB on the
   next status query after a failed subscriber notification.
3. WHEN the process starts THEN the system SHALL warm the
   `MaintenanceGate` cache from DB before the first non-admin request
   is served.

### Requirement 4: Audit Trail

**User Story:** As an auditor, I want every maintenance-mode change
recorded with actor, scope, reason, and timestamp, so that incident
reviews can reconstruct operational decisions.

**Acceptance Criteria (EARS):**

1. WHEN a maintenance change is applied THEN the system SHALL write a
   row to the `core.maintenance_mode_audit` table with
   `actor_user_id`, `actor_ip`, `scope`, `from_mode`, `to_mode`,
   `reason`, `ends_at`, `changed_at`.
2. IF `reason` is absent or shorter than 10 characters THEN the system
   SHALL raise `SemanticError` (never caught) and reject the change.
3. WHERE an audit insert fails THEN the system SHALL abort the mode
   change transaction — no mode change is applied without a recorded
   audit row.

## Property-Based Test Requirements

### Property 1: Mode Precedence is Monotonic and Commutative

- **Invariant:** For any pair of (service-scope-mode, project-scope-mode)
  the effective mode on a project-targeted request is
  `max(service_mode, project_mode)` under the ordering
  `active < read_only < draining`, regardless of the order in which the
  two scopes were most recently updated.
- **Generator:** `hypothesis.strategies.lists(tuples(sampled_from(["service",
  "project:proj-x"]), sampled_from(["active", "read_only", "draining"])),
  min_size=1, max_size=50)` applied as a sequence, then a randomly
  permuted replay.
- **Assertion:** `gate.status(project="proj-x") ==
  max(service_final, project_final)` under the defined ordering.
- **Sample size:** 1000 generated cases

### Property 2: Read Paths are Never Gated

- **Invariant:** For any maintenance configuration, any request whose
  route is annotated `@read_only_safe` returns the same status code as
  it would when no maintenance is active.
- **Generator:** `hypothesis.strategies.lists(sampled_from(["active",
  "read_only", "draining"]), min_size=1, max_size=20)` applied to the
  service scope, paired with
  `sampled_from(_read_only_safe_route_table)`.
- **Assertion:** The read-path handler's response status is identical
  across the maintenance mode axis (the only difference permitted is a
  `X-Draining: true` header during drain).
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `maintenance_gate.status(scope)` cache-hit
  p99 < 1 ms. Mode change p99 < 50 ms (DB insert + bus publish). Bus
  fan-out to all in-process subscribers < 50 ms median.
- **NFR-2 (Security):** Writes to `/api/v1/admin/maintenance` require
  permission `pychestrate.maintenance.manage`, which is bound to the
  `service_admin` role only in the default `1-rbac` seed. Every write
  is audited per Requirement 4. `reason` is truncated at 512 chars;
  null bytes rejected. `ends_at` accepted only when >= `now() + 60s`
  (prevents accidental instant auto-expiry).
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_maintenance_mode_current{scope,mode}` (gauge 0/1),
  `pychestrate_maintenance_mode_changes_total{scope,to_mode}` (counter),
  `pychestrate_maintenance_mode_rejections_total{scope,route}` (counter),
  `pychestrate_maintenance_gate_lookup_duration_seconds{cache_hit}`
  (histogram). Log events `pychestrate.maintenance.mode.changed`,
  `pychestrate.maintenance.mode.auto_expired`,
  `pychestrate.maintenance.gate.rejected`. Trace span
  `pychestrate.maintenance.gate.check` with `scope` and `mode`
  attributes.
- **NFR-4 (Reliability):** Bus delivery failures MUST NOT leave the gate
  stale forever — the gate ages out cached entries after
  `cache_ttl_seconds` (default 30) and re-reads from DB. A DB outage
  MUST fail safe: the gate returns the last-known mode and logs
  `pychestrate.maintenance.gate.degraded`; writes do not silently
  bypass maintenance.

## Out of Scope

- Per-pod maintenance mode (candidate for a later phase with Layer 3
  pods).
- Automated maintenance scheduling (cron-driven) — operators invoke the
  REST endpoint manually or via `8-cli`.
- Tenant-scoped maintenance — single-tenancy assumption holds in Phase
  10.

## Dependencies

- **Depends on:** `0-persistence` (stores mode + audit), `0-message-bus`
  (broadcast), `1-authentication` + `1-rbac` (admin-only mutation),
  `1-audit-log` (sinks the audit row to the append-only log once
  available; Phase 10 onwards).
- **Depended on by:** `0-object-store`, `0-timeseries-backend`,
  `3-client-agent-protocol` (rejects new dispatches during drain),
  `4-checkout-checkin` (rejects new reservations), `5-job-dispatch`,
  `5-run-state-machine`, `6-pipeline-definition` (rejects pipeline
  start), and every endpoint that mutates state.
- **Extension points exposed:** None in Phase 0. The `@read_only_safe`
  route-annotation table is a *closed* list maintained in-tree — an
  extension wanting to add a safe read route must pass a review. This
  is deliberate: read-safety classification is security-relevant.
