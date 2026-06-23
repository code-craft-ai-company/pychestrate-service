# 7-alerts-budgets — Design

## Architecture

`7-alerts-budgets` is a scheduled evaluator service plus a rule store.
Rules are declarative; their evaluation logic is delegated to
`AlertRuleKindExtension` subclasses collected from the extension host.
The evaluator runs on a single logical worker (horizontally scalable by
rule-hash) that ticks once per `alert_eval_tick_seconds`, loads eligible
rules from `0-persistence`, queries `0-timeseries-backend`, calls
`evaluate(series) → FiringResult`, and updates the `alert_live_state`
table. When firing state changes, it emits events on `0-message-bus`
and hands the notification to `2-notification-hub`. The feature lives
in **Phase 9**. Authoritative storage: rule definitions and live-alert
state are owned here.

## Data Model

Tables in `0-persistence`:

- `alert_rule`:
  - `rule_id: UUID` PK
  - `project_id: UUID`
  - `name: str`
  - `description: str`
  - `kind: str` — matches `AlertRuleKindExtension.kind`
  - `enabled: bool`
  - `evaluation_period_seconds: int`
  - `for_duration_seconds: int`
  - `resolve_hysteresis_seconds: int`
  - `notification_route_key: str`
  - `runbook_url: str | None`
  - `rule_config: dict[str, Any]` (JSONB — validated against kind's `config_schema`)
  - `owner_principal_id: UUID`
  - `created_at, updated_at: datetime`
  - `version: int`
- `alert_live_state`:
  - `alert_id: UUID` PK
  - `rule_id: UUID` FK → `alert_rule`
  - `state: Literal["firing","resolved"]`
  - `first_fired_at: datetime`
  - `last_observed_at: datetime`
  - `current_value: float | None`
  - `last_notified_at: datetime | None`
  - `notification_count_last_hour: int`
- `alert_notification_retry_queue`:
  - `queue_id: BIGSERIAL`
  - `alert_id: UUID`
  - `route_key: str`
  - `payload: bytes` (JSONB)
  - `retry_count: int`
  - `next_attempt_at: datetime`

Value types:

- `AlertRuleDefinition` — API-facing shape.
- `FiringResult` — `{state: Literal["firing","resolved","no_change"], current_value: float | None, rationale: str}`.
- `EvaluationContext` — `{project_id, rule, clock, query_adapter, window}`.
- `AlertPayload` — `{rule_id, project_id, name, description, state, current_value, threshold, runbook_url, dashboard_link}`.

## Interfaces

### Public API

REST under `8-rest-api-v1` (prefix `/api/v1/projects/{project_id}/alert-rules`):

- `GET /` — list project rules.
- `POST /` — create rule (`alerts.write`).
- `GET /{rule_id}` / `PUT /{rule_id}` / `DELETE /{rule_id}` — CRUD.
- `POST /{rule_id}/enable` / `POST /{rule_id}/disable`.
- `GET /{rule_id}/live` — current live-alert row for a rule.
- `GET /kinds` — list registered `AlertRuleKindExtension` kinds.
- `GET /api/v1/projects/{project_id}/alerts/live` — all currently firing alerts for a project.

### Internal API

```python
class AlertRuleService:
    def __init__(
        self,
        repo: AlertRuleRepository,
        kind_registry: AlertRuleKindRegistry,
        notification_hub: NotificationHub,
        rbac: RbacService,
        audit: AuditLog,
        bus: MessageBus,
        clock: Clock,
        config: AlertConfig
    ) -> None:
        self._repo = repo
        self._kind_registry = kind_registry
        self._notification_hub = notification_hub
        self._rbac = rbac
        self._audit = audit
        self._bus = bus
        self._clock = clock
        self._config = config
        return

    def create_rule(
        self,
        actor_id: UUID,
        project_id: UUID,
        definition: AlertRuleDefinition
    ) -> StoredAlertRule:
        ...

    def update_rule(
        self,
        actor_id: UUID,
        rule_id: UUID,
        definition: AlertRuleDefinition,
        if_match_etag: str
    ) -> StoredAlertRule:
        ...

    def delete_rule(
        self,
        actor_id: UUID,
        rule_id: UUID,
        if_match_etag: str
    ) -> None:
        ...

    def validate_rule(
        self,
        definition: AlertRuleDefinition
    ) -> None:
        """
            :raises: AlertRuleValidationError
        """
        ...


class AlertEvaluator:
    def __init__(
        self,
        repo: AlertRuleRepository,
        kind_registry: AlertRuleKindRegistry,
        ts_facade: TimeseriesFacade,
        notification_hub: NotificationHub,
        bus: MessageBus,
        clock: Clock,
        config: AlertConfig
    ) -> None:
        self._repo = repo
        self._kind_registry = kind_registry
        self._ts_facade = ts_facade
        self._notification_hub = notification_hub
        self._bus = bus
        self._clock = clock
        self._config = config
        self._task: asyncio.Task | None = None
        return

    def start(
        self
    ) -> None:
        ...

    def stop(
        self
    ) -> None:
        ...

    def tick(
        self
    ) -> None:
        """
            One pass of rule evaluation. Public for testing.

            :returns: None.
        """
        ...

    def evaluate_rule(
        self,
        rule: StoredAlertRule
    ) -> FiringResult:
        """
            Dispatches to the rule kind's evaluate.

            :returns: FiringResult.
            :raises: None (kind-level errors caught and reclassified).
        """
        ...
```

### Extension Surface

```python
class AlertRuleKindExtension(ResourceExtension):
    """
        Base for registering a new alert rule kind.
    """
    kind: str
    config_schema: dict[str, Any]
    requires_metric_names: list[str]
    default_evaluation_period_seconds: int

    @classmethod
    def evaluate(
        cls,
        context: EvaluationContext,
        series: TimeseriesSeries,
        rule_config: dict[str, Any]
    ) -> FiringResult:
        """
            Pure function over a loaded series + rule config.

            :returns: FiringResult.
            :raises: None (return no_change when inputs insufficient).
        """
        ...

    @classmethod
    def build_query(
        cls,
        rule_config: dict[str, Any]
    ) -> QuerySpec:
        """
            :returns: QuerySpec the evaluator executes against 0-timeseries-backend.
        """
        ...
```

Reference implementations shipped in-tree:

- `source/site/ccai/extensions/pychestrate/alert_rule_kind/threshold.py` — `kind="threshold"`.
- `source/site/ccai/extensions/pychestrate/alert_rule_kind/rate_of_change.py` — `kind="rate_of_change"`.
- `source/site/ccai/extensions/pychestrate/alert_rule_kind/absence.py` — `kind="absence"`.

(`7-slo-views` ships its own `kind="slo_burn_rate"` subclass against this surface.)

### Events Emitted

- `entity.alert.fired` — `{rule_id, alert_id, project_id, fired_at, current_value, threshold, runbook_url}`.
- `entity.alert.resolved` — `{rule_id, alert_id, project_id, resolved_at}`.
- `entity.alert.rule_saved` — `{rule_id, project_id, actor_id, action, version}`.
- `entity.alert.rule_deleted` — `{rule_id, project_id, actor_id}`.

### Events Consumed

- `extension.reloaded` — rebuild `kind_registry`.
- `entity.project.deleted` — cascade alert rule deletion.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/alerts/`:

- `__init__.py`
- `service.py` — `AlertRuleService`.
- `evaluator.py` — `AlertEvaluator`, `tick`, `evaluate_rule`.
- `repository.py` — `AlertRuleRepository`.
- `registry.py` — `AlertRuleKindRegistry`.
- `extension_base.py` — `AlertRuleKindExtension`, `EvaluationContext`, `FiringResult`, `QuerySpec`.
- `validation.py` — `validate_rule` (kind resolution, config schema, route validation).
- `notifier.py` — `AlertNotifier` (wraps `NotificationHub.send` + retry queue).
- `retry_worker.py` — drain `alert_notification_retry_queue`.
- `config.py` — `AlertConfig`.
- `errors.py` — `AlertRuleValidationError`, `ChannelUnavailableError`.
- `rest/v1_routes.py` — REST endpoints.

Kind extensions under
`source/site/ccai/extensions/pychestrate/alert_rule_kind/`.

## Key Flows

### Flow 1 — Save a Rule

1. REST request arrives; RBAC `alerts.write` checked.
2. `validate_rule` resolves `kind` against registry; validates `rule_config` against kind's `config_schema`.
3. `notification_route_key` validated against `NotificationHub.has_route(...)`.
4. `repo.insert(...)`; audit + `entity.alert.rule_saved` emitted.

### Flow 2 — Evaluator Tick

1. `AlertEvaluator.tick()` loads enabled rules whose `next_evaluation_at <= now`.
2. For each rule: resolve kind → `QuerySpec` → `ts_facade.query_range(...)`.
3. `kind.evaluate(...)` → `FiringResult`.
4. State machine update vs `alert_live_state`:
   - `no_change` → touch `last_observed_at`, `current_value`.
   - `firing` (from resolved or new) → create/update live row, emit `entity.alert.fired`, hand to notifier.
   - `resolved` (from firing, past hysteresis) → update live row, emit `entity.alert.resolved`, send resolution notification.

### Flow 3 — Notification With Throttling

1. Notifier loads live row; increments `notification_count_last_hour`.
2. If > `notifications_per_rule_max_per_hour`: skip + metric + log.
3. Else: `NotificationHub.send(route, AlertPayload)` with retries. On persistent failure, row appended to `alert_notification_retry_queue`.
4. Retry worker drains the queue with exponential backoff up to `notification_send_retries`.

### Flow 4 — Recovery After Crash

1. On boot, `AlertEvaluator` hydrates `_live_state_cache` from `alert_live_state`.
2. Rules resume at their last scheduled `next_evaluation_at`.
3. Retry worker resumes draining the retry queue.

## Error Handling

- `SemanticError` on explicit bugs (malformed rule ids, etc.): bubble.
- `AlertRuleValidationError`: 400 with multiline message via `os.linesep.join([...])`.
- Kind `evaluate` raising: caught, reclassified as `AlertEvaluationError`, counted in `pychestrate_alert_evaluations_total{outcome="error"}`, rule marked `last_error` — does *not* stop scheduling.
- `ChannelUnavailableError` from `NotificationHub`: caught, retry queue, metric increment.
- `ConfigurationError` for duplicate `kind` or missing classmethods: fatal at service start.

## Security Considerations

- `alerts.read` / `alerts.write` gating; project membership required.
- Cross-project alerts are platform-admin-only via `alerts.admin`.
- `rule_config` JSON Schema validation prevents arbitrary field injection.
- `notification_route_key` validated at save time — cannot target channels the project does not own.
- Rule definition redaction when caller lacks `alerts.rule_definition.read:details` — mask `threshold`, `rule_config` values.
- `runbook_url` must match `runbook_url_allowlist` (default `^https://`).

## Observability

Metrics:

- `pychestrate_alert_evaluations_total{rule,outcome}` — counter
- `pychestrate_alert_evaluation_duration_seconds{rule_kind}` — histogram
- `pychestrate_alert_firing_count` — gauge
- `pychestrate_alert_notifications_suppressed_total{rule}` — counter
- `pychestrate_alert_notification_failed_total{route}` — counter
- `pychestrate_alert_retry_queue_depth` — gauge
- `pychestrate_alert_rules_registered{kind}` — gauge

Log events: `pychestrate.alert.fired`, `pychestrate.alert.resolved`, `pychestrate.alert.notifications_throttled`, `pychestrate.alert.rule_validation_failed`, `pychestrate.alert.evaluation_error`.

Trace spans: `pychestrate.alert.evaluate`, `pychestrate.alert.notify`, `pychestrate.alert.rule_saved`, `pychestrate.alert.tick`, `pychestrate.alert.retry_drain`.

## Open Questions

- Are inhibition rules (alert A silences alert B) in v1, or deferred? Current design: deferred. Timebox: after Phase 9 exit.
- Should we support multi-tenant grouping (group related alerts into a single notification)? Current design: no. Timebox: Phase 9 midpoint.
- Is `notifications_per_rule_max_per_hour` per-rule or per-(rule, route_key)? Current design: per-rule. Timebox: Phase 9 midpoint.
