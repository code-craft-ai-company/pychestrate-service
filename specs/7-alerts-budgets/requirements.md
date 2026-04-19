# 7-alerts-budgets — Requirements

## Introduction

The `7-alerts-budgets` feature evaluates user-declared alert rules
against the time-series in `0-timeseries-backend`, raises and resolves
alert events, and routes them to `2-notification-hub` for channel
delivery. It owns the `AlertRuleKindExtension` resource surface
(different families of rule logic — threshold, burn-rate, absence,
rate-of-change) and publishes `entity.alert.fired` /
`entity.alert.resolved` events. It lands in **Phase 9** alongside
`7-project-dashboards` and `7-slo-views`; `7-slo-views` in particular
creates `AlertRuleKindExtension` subclasses for burn-rate alerts.
Authoritative storage for alert rule definitions and live alert state
lives here; metric values are read from `0-timeseries-backend`; channel
delivery is delegated to `2-notification-hub`.

## Requirements

### Requirement 1: Declare, Store, and Evaluate Alert Rules

**User Story:** As an on-call engineer, I want to declare threshold
alert rules against metric names, so that I get notified when
`pychestrate_build_duration_seconds` crosses my SLO.

**Acceptance Criteria (EARS):**

1. WHEN a user with `alerts.write` calls `POST /api/v1/projects/{project_id}/alert-rules` with a valid `AlertRuleDefinition` THEN the system SHALL persist it, emit `entity.alert.rule_saved`, AND return 201.
2. WHILE an alert rule is `enabled` the system SHALL evaluate it every `rule.evaluation_period_seconds` (minimum `alert_eval_period_floor_seconds`, default 15) AND emit `entity.alert.fired` when the rule's `AlertRuleKindExtension.evaluate(...)` returns a `FiringResult`.
3. WHEN the rule's `evaluate` returns `RESOLVED` for a rule currently firing THEN the system SHALL emit `entity.alert.resolved` AND mark the stored live-alert state as resolved.
4. IF no alert has fired and no change in firing state occurs THEN the system SHALL NOT emit any alert event (no-op evaluations are silent).

### Requirement 2: Threshold-Based Rule Semantics

**User Story:** As a service owner, I want threshold rules that fire
after a configurable `for` duration, so that transient spikes don't
page me.

**Acceptance Criteria (EARS):**

1. WHEN a `threshold` rule with `threshold: T`, `comparator: >`, and `for_duration_seconds: W` is evaluated AND the observed metric value has been `> T` for at least `W` seconds THEN the system SHALL emit `entity.alert.fired` exactly once for that firing episode.
2. WHILE the metric remains `> T` beyond the initial fire THEN the system SHALL NOT re-emit `entity.alert.fired` for the same episode AND SHALL update the live-alert row's `last_observed_at` and `current_value`.
3. IF the metric drops below `T` for `resolve_hysteresis_seconds` (default 60) THEN the system SHALL transition the alert to `resolved` AND emit `entity.alert.resolved`.
4. WHERE the rule declares `absent_strategy: Literal["fire","resolve","ignore"]` AND the queried series returns zero samples for the evaluation window THEN the system SHALL apply the declared strategy.

### Requirement 3: Routing to Notification Hub With Throttling

**User Story:** As an on-call engineer, I want alert notifications
throttled per rule, so that a flapping metric does not spam my Slack
channel.

**Acceptance Criteria (EARS):**

1. WHEN `entity.alert.fired` is emitted THEN the system SHALL call `NotificationHub.send(route_key, payload)` using `rule.notification_route_key` within `notification_enqueue_timeout_seconds` (default 3.0).
2. IF the same rule fires more than `notifications_per_rule_max_per_hour` (default 12) times in one rolling hour THEN the system SHALL suppress additional notifications AND emit `pychestrate_alert_notifications_suppressed_total{rule}` counter + `pychestrate.alert.notifications_throttled` log.
3. IF `NotificationHub.send` raises `ChannelUnavailableError` THEN the system SHALL catch-and-reclassify, retry the send up to `notification_send_retries` (default 3) with exponential backoff, AND on final failure emit `pychestrate_alert_notification_failed_total{route}` and persist a fallback entry for manual review.
4. WHERE the alert rule has `runbook_url` the system SHALL include it in the notification payload AND attach it to the stored live-alert row for UI display.

## Property-Based Test Requirements

### Property 1: Quiet Below Threshold

- **Invariant:** For any threshold rule with comparator `>` and threshold `TH`, no `entity.alert.fired` event is emitted while every observed value is `< TH` for the evaluation window.
- **Generator:** `hypothesis.strategies.lists(floats(min_value=0.0, max_value=10.0), min_size=1, max_size=500).filter(lambda xs: max(xs) < 10.0 - epsilon)` paired with `TH = 10.0`.
- **Assertion:** `count(entity.alert.fired emits for this rule) == 0`.
- **Sample size:** 1000 generated cases

### Property 2: Single Fire Per Episode

- **Invariant:** For any continuous firing episode (metric `> TH` for at least `W` seconds), exactly one `entity.alert.fired` event is emitted until a resolution.
- **Generator:** Synthetic metric series with controlled above/below transitions.
- **Assertion:** `count(fire_events in episode) == 1`.
- **Sample size:** 1000 generated cases

### Property 3: Fire/Resolve Pairing

- **Invariant:** For any rule lifecycle, `count(fired) == count(resolved) + count(currently_firing)` at any point in time.
- **Generator:** `hypothesis.strategies.lists(sampled_from([0.0, 5.0, 15.0]), min_size=0, max_size=1000)` with `TH = 10.0`.
- **Assertion:** Invariant holds at every evaluation step.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Rule evaluation latency (load + query + evaluate + emit) p99 < 250 ms per rule for rules with evaluation window `<= 10 min`. Evaluator scheduler can handle 2 000 concurrent rules on a single worker with average CPU `< 40%`. Notification fan-out p99 < 500 ms per alert.
- **NFR-2 (Security):** Rule read/write gated by `alerts.read` / `alerts.write` + project membership. `notification_route_key` validated against `2-notification-hub` at save time to prevent configuring an unroutable alert. Rule expressions sanitized — only known metric names may be referenced. RBAC-aware redaction of rule definitions when the caller lacks `alerts.rule_definition.read:details` (e.g., `threshold` values masked).
- **NFR-3 (Observability):** Metrics `pychestrate_alert_evaluations_total{rule,outcome}` (counter), `pychestrate_alert_evaluation_duration_seconds{rule_kind}` (histogram), `pychestrate_alert_firing_count` (gauge), `pychestrate_alert_notifications_suppressed_total{rule}` (counter), `pychestrate_alert_notification_failed_total{route}` (counter). Log events `pychestrate.alert.fired`, `pychestrate.alert.resolved`, `pychestrate.alert.notifications_throttled`, `pychestrate.alert.rule_validation_failed`. Trace spans `pychestrate.alert.evaluate`, `pychestrate.alert.notify`, `pychestrate.alert.rule_saved`.
- **NFR-4 (Reliability):** Evaluator crash recovery SHALL rebuild the live-alert state from `alert_live_state` table at restart; no alerts are lost. `NotificationHub` retries exponentially; the final failure is durable in an `alert_notification_retry_queue` for offline review.

## Out of Scope

- Channel delivery implementations (owned by `2-notification-hub`).
- Burn-rate math for SLOs (owned by `7-slo-views`, which contributes an `AlertRuleKindExtension` subclass).
- Metric storage/query (owned by `0-timeseries-backend`).
- Dashboard tile rendering (owned by `7-project-dashboards`).

## Dependencies

- **Depends on:** `7-metrics-ingest`, `7-project-dashboards` (optional — tiles can reference alerts), `0-timeseries-backend`, `0-persistence`, `0-message-bus`, `2-notification-hub`, `1-rbac`, `E-extension-host`, `E-resource-extensions`.
- **Depended on by:** `7-slo-views` (uses the evaluator to fire burn-rate alerts), `9-project-dashboard-ui` (surfaces live alerts on dashboards).
- **Extension points exposed:** `resource: AlertRuleKindExtension` · `event: entity.alert.fired` · `event: entity.alert.resolved` · `event: entity.alert.rule_saved`.
