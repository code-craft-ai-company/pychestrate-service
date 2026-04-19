# 0-system-health — Requirements

## Introduction

The `0-system-health` feature provides Pychestrate's internal liveness and
readiness probe aggregation, plus a registry of domain health probes
contributed via the `SystemHealthProbeExtension` resource surface. It
ships in **Phase 0** and takes ownership of `/__health/live`,
`/__health/ready`, and `/__health/detailed` from the temporary probes
stubbed in `0-web-app-host`. Each Layer 0 sibling (`0-persistence`,
`0-message-bus`, `0-object-store`, `0-timeseries-backend`) registers a
probe; extensions ship their own probes for external dependencies (e.g.,
a notification-channel driver's upstream SMTP, a bug-tracker driver's
Jira endpoint). Sits between `0-web-app-host` (hosts the endpoints) and
`10-observability` (exports probe results as metrics).

## Requirements

### Requirement 1: Aggregated Liveness and Readiness Endpoints

**User Story:** As a deploy pipeline, I want cheap liveness and readiness
probes at stable paths, so that Kubernetes / systemd can route traffic
only when the service is actually ready.

**Acceptance Criteria (EARS):**

1. WHEN `GET /__health/live` is requested THEN the system SHALL return
   `200 OK` with body `{"status": "live"}` within 50 ms p99 as long as the
   process is running, regardless of downstream dependency state.
2. WHEN `GET /__health/ready` is requested THEN the system SHALL return
   `200 OK` only if every registered `readiness` probe reports `ok`;
   otherwise `503 Service Unavailable` with a body listing failing probes.
3. IF the service is in `startup` phase (startup hooks not yet complete)
   THEN `/__health/ready` SHALL return `503` with body
   `{"status": "starting"}`.
4. WHERE the service is in `draining` phase the system SHALL return
   `503 Service Unavailable` on `/__health/ready` with body
   `{"status": "draining"}` while `/__health/live` continues returning
   `200 OK`.

### Requirement 2: Detailed Status Endpoint

**User Story:** As an operator debugging a degraded service, I want a
per-probe status endpoint with structured details, so that I can triage
without reading logs.

**Acceptance Criteria (EARS):**

1. WHEN `GET /__health/detailed` is requested THEN the system SHALL
   return `200 OK` with a body of shape
   `{"overall": "ok"|"degraded"|"failing", "probes": [{"name", "kind",
   "status", "last_ok_at", "last_error", "duration_ms"}, ...]}`.
2. IF the caller lacks permission `pychestrate.system_health.detailed`
   THEN the system SHALL return `401` or `403` per `1-authentication` /
   `1-rbac` and SHALL NOT leak probe details.
3. WHERE a probe has never run the system SHALL list it with
   `status: "unknown"` rather than omitting it.

### Requirement 3: Probe Extension Registration

**User Story:** As a feature author or extension, I want to register a
domain-specific probe declaratively, so that failures visibly affect
readiness without bespoke endpoint wiring.

**Acceptance Criteria (EARS):**

1. WHEN a `SystemHealthProbeExtension` subclass is loaded THEN the system
   SHALL register it with its declared `name`, `kind` (`liveness` |
   `readiness` | `informational`), `interval_seconds`, and
   `timeout_seconds`.
2. IF two probes share the same `name` THEN the system SHALL raise
   `SemanticError` at registration time (never caught).
3. WHEN a probe's `timeout_seconds` elapses without completion THEN the
   system SHALL record the run as `failed` with
   `last_error: "probe timeout"` and SHALL NOT let the timeout block the
   scheduler.
4. WHERE a probe raises any exception the system SHALL capture the
   exception class + message into `last_error`, mark `failed`, increment
   `pychestrate_system_health_probe_failures_total{probe}`, and continue
   scheduling.

### Requirement 4: Scheduler Isolation From Request Traffic

**User Story:** As a service operator, I want probe execution to run on
its own scheduler, so that heavy request traffic cannot delay readiness
evaluation.

**Acceptance Criteria (EARS):**

1. WHILE the process is serving requests the system SHALL run probe
   evaluations on a dedicated thread pool sized at
   `probe_worker_count` (default 4) not shared with request workers.
2. WHEN a probe's `interval_seconds` has elapsed since its last run THEN
   the system SHALL schedule a new run within 200 ms.
3. IF the scheduler backlog for a probe grows beyond 1 THEN the system
   SHALL drop duplicate runs AND log `pychestrate.system_health.scheduler.backlog`.
4. WHEN the shutdown hook runs the system SHALL stop the scheduler and
   wait up to 5 s for in-flight probes to finish.

## Property-Based Test Requirements

### Property 1: Aggregate Readiness is the Logical AND of Readiness Probes

- **Invariant:** For any set of registered `readiness` probes with known
  individual statuses, `/__health/ready` returns `200` iff every probe's
  latest status is `ok`.
- **Generator:** `hypothesis.strategies.lists(tuples(text(min_size=1,
  max_size=32, alphabet=ascii_letters), sampled_from(["ok", "fail",
  "unknown"])), min_size=1, max_size=40, unique_by=lambda x: x[0])`.
- **Assertion:** `ready_status == 200 if all(s == "ok" for _, s in
  probes) else 503`.
- **Sample size:** 1000 generated cases

### Property 2: Scheduler Never Runs Stale Probes Concurrently

- **Invariant:** For any probe at any time, there is never more than one
  concurrent execution of that probe, regardless of interval and run
  duration.
- **Generator:** `hypothesis.strategies.lists(tuples(floats(min_value=0.05,
  max_value=2.0), floats(min_value=0.0, max_value=1.5)), min_size=1,
  max_size=10)` (per probe: `interval_seconds`, `simulated_run_duration`)
  plus a randomized observation window.
- **Assertion:** A shared `in_flight` counter never exceeds 1 per probe
  across the observation window.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `/__health/live` p99 < 5 ms; `/__health/ready`
  p99 < 20 ms (served from cached probe results); `/__health/detailed`
  p99 < 100 ms. Probe scheduler overhead < 0.5% CPU with 20 probes on a
  4 vCPU host.
- **NFR-2 (Security):** `/__health/live` is unauthenticated (must always
  answer so orchestrators can route). `/__health/ready` is
  unauthenticated but returns no implementation details.
  `/__health/detailed` requires permission
  `pychestrate.system_health.detailed`. Probe `last_error` messages are
  truncated at 512 chars to prevent leaking secrets from upstream driver
  errors.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_system_health_probe_duration_seconds{probe,kind}`
  (histogram), `pychestrate_system_health_probe_failures_total{probe}`
  (counter), `pychestrate_system_health_probe_up{probe,kind}` (gauge
  0/1), `pychestrate_system_health_overall_status` (gauge: 0=failing,
  1=degraded, 2=ok), `pychestrate_system_health_scheduler_backlog{probe}`
  (gauge). Log events `pychestrate.system_health.probe.failed`,
  `pychestrate.system_health.probe.recovered`,
  `pychestrate.system_health.overall.changed`,
  `pychestrate.system_health.scheduler.backlog`. Trace span
  `pychestrate.system_health.probe.run` with `probe` attribute.
- **NFR-4 (Reliability):** Probe evaluation failures MUST NEVER crash
  the process. `/__health/live` MUST remain responsive even if every
  probe fails. Probe execution is isolated per thread — one probe's
  thread crash MUST NOT affect others.

## Out of Scope

- External health aggregation across Pychestrate instances (a reverse
  proxy / load balancer handles cluster view).
- PagerDuty-style alert routing based on health (see `7-alerts-budgets`).
- Per-tenant health scoping — all probes are service-scoped in Phase 0;
  project-scoped probes revisited with `0-maintenance-mode`.

## Dependencies

- **Depends on:** `0-web-app-host` (hosts the endpoints), `0-message-bus`
  (for emitting `system_health.overall.changed`), `E-resource-extensions`
  (Phase 0.5 — for loading probe extensions; Phase 0 ships with
  in-tree probes only).
- **Depended on by:** `10-observability`, `9-admin-ui` (renders
  detailed view), any feature with an external dependency worth
  monitoring.
- **Extension points exposed:** `resource: SystemHealthProbeExtension`
  — custom probes the aggregated endpoint consumes. Event emitted:
  `system_health.overall.changed`.
