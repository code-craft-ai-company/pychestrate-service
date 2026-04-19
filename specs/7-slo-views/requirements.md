# 7-slo-views — Requirements

## Introduction

The `7-slo-views` feature lets project owners declare Service Level
Objectives over metrics produced by Layer 7, computes burn-rate windows
against the declared error budgets, and surfaces both current status
and burn-rate alerts. It owns the `SLODefinitionExtension` resource
surface (rule families for availability-ratio, latency-quantile, and
threshold-budget SLOs), and it ships a burn-rate
`AlertRuleKindExtension` subclass against `7-alerts-budgets` rather
than evaluating alerts itself. It lands in **Phase 9** alongside
`7-project-dashboards` and `7-alerts-budgets`; the
`slo_burn` dashboard tile from `7-project-dashboards` reads the SLO
status endpoints published here. Authoritative storage for SLO
definitions lives in `0-persistence`; metric values are read from
`0-timeseries-backend`; alert firing is done by `7-alerts-budgets`.

## Requirements

### Requirement 1: Declare and Compute SLOs

**User Story:** As a service owner, I want to declare an SLO like
"99% of builds complete in under 900 s over 30 d", so that Pychestrate
tells me where I stand against that commitment without a spreadsheet.

**Acceptance Criteria (EARS):**

1. WHEN a user with `slo.write` calls `POST /api/v1/projects/{project_id}/slos` with a valid `SLODefinition` THEN the system SHALL persist it, emit `entity.slo.saved`, AND return 201 with the stored document.
2. WHEN `GET /api/v1/projects/{project_id}/slos/{slo_id}/status` is called THEN the system SHALL compute the current `SLOStatus` including `target`, `achieved`, `error_budget_remaining_ratio`, `window_start`, `window_end` AND return within `slo_status_timeout_seconds` (default 1.2) p99.
3. IF a declared SLO's `kind` is not registered by a `SLODefinitionExtension` THEN the system SHALL respond 400 AND include the missing kind in the error message.
4. WHERE `target` is declared as a fraction `[0.0, 1.0]` (e.g., `0.99`) AND `window_seconds` spans at least `slo_window_min_seconds` (default 3600) the system SHALL accept the SLO.

### Requirement 2: Burn-Rate Computation

**User Story:** As an on-call engineer, I want a burn-rate display
showing how fast the error budget is being consumed, so that I can
tell if we will blow through the SLO this week.

**Acceptance Criteria (EARS):**

1. WHEN `GET /api/v1/projects/{project_id}/slos/{slo_id}/burn-rate` is called with `window=<short|long>` THEN the system SHALL compute `burn_rate = observed_error_ratio / (1.0 - target)` over the requested window AND return `{burn_rate, observed_error_ratio, window_seconds}`.
2. WHEN burn rate exceeds `burn_rate_fast_threshold` (default 14.4x, the 2 h multi-burn-rate trigger) THEN the system SHALL emit `entity.slo.burn_rate_high` with `{slo_id, severity="fast", burn_rate}`.
3. WHEN burn rate exceeds `burn_rate_slow_threshold` (default 6x, the 6 h trigger) THEN the system SHALL emit `entity.slo.burn_rate_high` with `severity="slow"` AND when the condition persists for at least `burn_rate_slow_for_seconds` (default 900).
4. WHILE the burn rate is below both thresholds THE system SHALL NOT emit `entity.slo.burn_rate_high` events AND SHALL update `pychestrate_slo_burn_rate{slo_id,window}` gauge each evaluation tick.

### Requirement 3: Burn-Rate Alert Rule Kind Contribution

**User Story:** As an on-call engineer, I want burn-rate alerts to use
the same routing, throttling, and runbook mechanics as my threshold
alerts, so that I have a single notification pane of glass.

**Acceptance Criteria (EARS):**

1. WHEN the extension host scans THEN the system SHALL register an `AlertRuleKindExtension` subclass with `kind="slo_burn_rate"` that targets the declared SLO by `slo_id` AND uses the multi-window burn-rate algorithm.
2. WHEN an `slo_burn_rate` alert rule is created referencing an SLO that does not exist THEN the system SHALL respond 400 with the missing `slo_id`.
3. WHEN the SLO that an alert rule references is deleted THEN the system SHALL cascade-delete the dependent alert rules AND emit `entity.alert.rule_deleted` for each AND emit `entity.slo.deleted`.
4. WHERE an SLO declares `auto_attach_burn_rate_alerts: True` the system SHALL create a default fast + slow burn-rate alert on save AND link them to the SLO's `default_notification_route_key`.

## Property-Based Test Requirements

### Property 1: Burn Rate Monotonic In Error Count

- **Invariant:** For any SLO with `target T` and window `W`, holding `total_count` fixed, `burn_rate` is non-decreasing as `error_count` increases.
- **Generator:** `hypothesis.strategies.tuples(integers(min_value=0, max_value=10**6), integers(min_value=1, max_value=10**6)).filter(lambda t: t[0] <= t[1])` paired with `T in floats(0.9, 0.9999)`.
- **Assertion:** `all(burn_rate(e_i, total) <= burn_rate(e_{i+1}, total) for (e_i, e_{i+1}) in pairwise(ascending_error_counts))`.
- **Sample size:** 1000 generated cases

### Property 2: Error Budget Identity

- **Invariant:** For any SLO with target `T` and observed error ratio `r`, `error_budget_remaining_ratio + (r / (1 - T)) == 1.0` (when `r <= 1 - T`) — i.e., the budget accounting is exact.
- **Generator:** `hypothesis.strategies.tuples(floats(min_value=0.9, max_value=0.9999), floats(min_value=0.0, max_value=0.1))`.
- **Assertion:** `abs(remaining + r/(1-T) - 1.0) < 1e-9` when `r <= 1 - T`.
- **Sample size:** 1000 generated cases

### Property 3: Quiet When Healthy

- **Invariant:** For any sequence of burn-rate samples all strictly below both `fast` and `slow` thresholds, no `entity.slo.burn_rate_high` event is emitted.
- **Generator:** `hypothesis.strategies.lists(floats(min_value=0.0, max_value=5.0), min_size=1, max_size=500)` paired with `fast=14.4, slow=6.0`.
- **Assertion:** `count(entity.slo.burn_rate_high emits) == 0`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** SLO status API p99 < 1.2 s (dominated by `0-timeseries-backend` range query). Burn-rate evaluator tick for 200 SLOs completes p99 < 3 s per tick. Dashboard `slo_burn` tile render p99 < 1.5 s.
- **NFR-2 (Security):** Read gated by `slo.read` + project membership; write by `slo.write`. SLO definitions reveal target metric names — masked when caller lacks `slo.definition.read:details`. Burn-rate alert route validation is delegated to `7-alerts-budgets`.
- **NFR-3 (Observability):** Metrics `pychestrate_slo_target{slo_id}` (gauge), `pychestrate_slo_achieved{slo_id}` (gauge), `pychestrate_slo_error_budget_remaining_ratio{slo_id}` (gauge), `pychestrate_slo_burn_rate{slo_id,window}` (gauge), `pychestrate_slo_burn_rate_high_total{slo_id,severity}` (counter), `pychestrate_slo_status_duration_seconds{slo_id}` (histogram). Log events `pychestrate.slo.saved`, `pychestrate.slo.burn_rate_high`, `pychestrate.slo.definition_validation_failed`. Trace spans `pychestrate.slo.compute_status`, `pychestrate.slo.compute_burn_rate`, `pychestrate.slo.burn_rate_tick`.
- **NFR-4 (Reliability):** Burn-rate evaluator missing a tick SHALL NOT double-fire — the burn-rate comparison uses observed state vs. stored last-state, not tick count. SLO status endpoint SHALL degrade gracefully (partial window) when `0-timeseries-backend` reports partial results.

## Out of Scope

- Alert routing and throttling (owned by `7-alerts-budgets`).
- Metric storage/query (owned by `0-timeseries-backend`).
- Dashboard tile rendering (owned by `7-project-dashboards` + `9-wc-metric-tile`).
- Multi-window multi-burn-rate tuning UI (candidate follow-up feature).

## Dependencies

- **Depends on:** `7-metrics-ingest`, `7-alerts-budgets`, `0-timeseries-backend`, `0-persistence`, `0-message-bus`, `1-rbac`, `2-projects`, `E-extension-host`, `E-resource-extensions`.
- **Depended on by:** `7-project-dashboards` (via `slo_burn` tile kind), `9-project-dashboard-ui`.
- **Extension points exposed:** `resource: SLODefinitionExtension` · `event: entity.slo.saved` · `event: entity.slo.deleted` · `event: entity.slo.burn_rate_high`.
