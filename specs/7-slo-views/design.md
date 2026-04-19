# 7-slo-views — Design

## Architecture

`7-slo-views` is three cooperating pieces: (1) an SLO definition store
backed by `0-persistence`; (2) a `SLOStatusService` that answers
`status` / `burn-rate` API calls by running short-window and long-window
queries against `0-timeseries-backend`; (3) a background
`BurnRateEvaluator` that emits `entity.slo.burn_rate_high` events when
multi-window thresholds trip. Burn-rate alerts route through
`7-alerts-budgets` via an `AlertRuleKindExtension` subclass
(`kind="slo_burn_rate"`) shipped here, so throttling, notification
channels, and runbook URL handling are reused rather than
reimplemented. The feature lives in **Phase 9**. Authoritative SLO
definitions are owned here; live alert routing and retention are owned
by `7-alerts-budgets`.

## Data Model

Tables in `0-persistence`:

- `slo`:
  - `slo_id: UUID` PK
  - `project_id: UUID`
  - `name: str`
  - `description: str`
  - `kind: str` — matches `SLODefinitionExtension.kind`
  - `target: float` — `[0.0, 1.0]`
  - `window_seconds: int`
  - `definition_config: dict[str, Any]` (JSONB; validated against kind's `config_schema`)
  - `default_notification_route_key: str | None`
  - `auto_attach_burn_rate_alerts: bool`
  - `created_at, updated_at: datetime`
  - `version: int`
- `slo_burn_rate_state`:
  - `slo_id: UUID` PK (FK)
  - `last_fast_burn_rate: float`
  - `last_slow_burn_rate: float`
  - `last_fast_over_since: datetime | None`
  - `last_slow_over_since: datetime | None`
  - `last_evaluated_at: datetime`

Value types:

- `SLODefinition` — API-facing shape.
- `SLOStatus` — `{target, achieved, error_budget_remaining_ratio, window_start, window_end, samples}`.
- `BurnRateResult` — `{burn_rate, observed_error_ratio, window_seconds}`.
- `MultiWindowBurnRate` — `{fast: BurnRateResult, slow: BurnRateResult}`.

## Interfaces

### Public API

REST under `8-rest-api-v1` (prefix `/api/v1/projects/{project_id}/slos`):

- `GET /` — list SLOs for project.
- `POST /` — create SLO (`slo.write`).
- `GET /{slo_id}`, `PUT /{slo_id}`, `DELETE /{slo_id}` — CRUD.
- `GET /{slo_id}/status` — current achieved ratio + error budget remaining.
- `GET /{slo_id}/burn-rate?window=short|long` — burn-rate snapshot.
- `GET /{slo_id}/history?granularity=…&from=…&to=…` — historical status series for `slo_burn` tile.
- `GET /kinds` — list registered `SLODefinitionExtension` kinds.

### Internal API

```python
class SLOService:
    def __init__(
        self,
        repo: SLORepository,
        kind_registry: SLODefinitionKindRegistry,
        alert_service: AlertRuleService,
        rbac: RbacService,
        audit: AuditLog,
        bus: MessageBus,
        clock: Clock,
        config: SLOConfig
    ) -> None:
        self._repo = repo
        self._kind_registry = kind_registry
        self._alert_service = alert_service
        self._rbac = rbac
        self._audit = audit
        self._bus = bus
        self._clock = clock
        self._config = config
        return

    def create_slo(
        self,
        actor_id: UUID,
        project_id: UUID,
        definition: SLODefinition
    ) -> StoredSLO:
        ...

    def delete_slo(
        self,
        actor_id: UUID,
        slo_id: UUID,
        if_match_etag: str
    ) -> None:
        """
            Cascade-delete dependent slo_burn_rate alert rules.
        """
        ...

    def validate_definition(
        self,
        definition: SLODefinition
    ) -> None:
        """
            :raises: SLOValidationError
        """
        ...


class SLOStatusService:
    def __init__(
        self,
        repo: SLORepository,
        kind_registry: SLODefinitionKindRegistry,
        ts_facade: TimeseriesFacade,
        clock: Clock,
        config: SLOConfig
    ) -> None:
        self._repo = repo
        self._kind_registry = kind_registry
        self._ts_facade = ts_facade
        self._clock = clock
        self._config = config
        return

    def compute_status(
        self,
        slo: StoredSLO,
        as_of: datetime | None
    ) -> SLOStatus:
        ...

    def compute_burn_rate(
        self,
        slo: StoredSLO,
        window: Literal["short","long"]
    ) -> BurnRateResult:
        ...

    def compute_multi_window_burn_rate(
        self,
        slo: StoredSLO
    ) -> MultiWindowBurnRate:
        ...


class BurnRateEvaluator:
    def __init__(
        self,
        repo: SLORepository,
        status_service: SLOStatusService,
        bus: MessageBus,
        clock: Clock,
        config: SLOConfig
    ) -> None:
        self._repo = repo
        self._status_service = status_service
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
            Compute multi-window burn rates for every SLO; emit
            entity.slo.burn_rate_high when thresholds trip with
            hysteresis applied.

            :returns: None.
        """
        ...


def compute_burn_rate_value(
    error_ratio: float,
    target: float
) -> float:
    """
        :returns: error_ratio / (1.0 - target) — standard burn rate.
        :raises: SemanticError when target >= 1.0.
    """
    ...
```

### Extension Surface

```python
class SLODefinitionExtension(ResourceExtension):
    """
        Base for declaring a new SLO kind (availability, latency, budget).
    """
    kind: str
    config_schema: dict[str, Any]
    requires_metrics: list[str]

    @classmethod
    def build_status_query(
        cls,
        slo: StoredSLO,
        as_of: datetime
    ) -> QuerySpec:
        ...

    @classmethod
    def compute_achieved_ratio(
        cls,
        slo: StoredSLO,
        series: TimeseriesSeries
    ) -> float:
        """
            :returns: Achieved success ratio in [0.0, 1.0].
        """
        ...

    @classmethod
    def compute_error_ratio(
        cls,
        slo: StoredSLO,
        window_seconds: int,
        series: TimeseriesSeries
    ) -> float:
        """
            :returns: Observed error ratio in [0.0, 1.0].
        """
        ...
```

Reference implementations shipped in-tree:

- `source/site/automojo/extensions/pychestrate/slo_definition/availability_ratio.py` — `kind="availability_ratio"`; target = success ratio over a metric pair (`success_total`, `total`).
- `source/site/automojo/extensions/pychestrate/slo_definition/latency_quantile.py` — `kind="latency_quantile"`; target = fraction of samples below a latency threshold.
- `source/site/automojo/extensions/pychestrate/slo_definition/threshold_budget.py` — `kind="threshold_budget"`; target = fraction of time a metric stays below a threshold.

### Events Emitted

- `entity.slo.saved` — `{slo_id, project_id, actor_id, action, version}`.
- `entity.slo.deleted` — `{slo_id, project_id, actor_id}`.
- `entity.slo.burn_rate_high` — `{slo_id, project_id, severity, burn_rate, observed_error_ratio, window_seconds}`.

### Events Consumed

- `extension.reloaded` — rebuild `kind_registry`.
- `entity.project.deleted` — cascade SLO deletion.
- `entity.alert.rule_deleted` — synchronize cascade bookkeeping.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/slo/`:

- `__init__.py`
- `service.py` — `SLOService`.
- `status.py` — `SLOStatusService`, `compute_burn_rate_value`.
- `evaluator.py` — `BurnRateEvaluator`.
- `repository.py` — `SLORepository`.
- `registry.py` — `SLODefinitionKindRegistry`.
- `extension_base.py` — `SLODefinitionExtension`, `QuerySpec` re-export.
- `validation.py` — `validate_definition`.
- `alert_kind.py` — `SLOBurnRateAlertRuleKind` (subclass of `AlertRuleKindExtension`).
- `config.py` — `SLOConfig`.
- `errors.py` — `SLOValidationError`.
- `rest/v1_routes.py` — REST endpoints.

Kind extensions under
`source/site/automojo/extensions/pychestrate/slo_definition/`.

## Key Flows

### Flow 1 — Create SLO with Auto-Attached Burn-Rate Alerts

1. `POST /.../slos` arrives; RBAC `slo.write` check.
2. `validate_definition` resolves kind, checks config schema, validates `target` and `window_seconds` bounds.
3. `repo.insert(...)`; emit `entity.slo.saved`.
4. If `auto_attach_burn_rate_alerts = True`, `alert_service.create_rule(...)` called twice — once for `fast`, once for `slow` — using `kind="slo_burn_rate"` with `rule_config = {slo_id, severity}`.

### Flow 2 — Compute Status

1. `GET /.../{slo_id}/status` arrives.
2. `SLOStatusService.compute_status(slo, as_of=now)` calls `kind.build_status_query(...)` → `QuerySpec`.
3. `ts_facade.query_range(query)` returns series.
4. `kind.compute_achieved_ratio(...)` returns achieved.
5. `error_budget_remaining_ratio = 1.0 - (1.0 - achieved) / (1.0 - target)` clamped to `[0.0, 1.0]`.
6. Response serialized; status gauges emitted (`pychestrate_slo_target`, `pychestrate_slo_achieved`, `pychestrate_slo_error_budget_remaining_ratio`).

### Flow 3 — Burn-Rate Tick

1. `BurnRateEvaluator.tick()` iterates all enabled SLOs.
2. For each SLO: `compute_multi_window_burn_rate(slo)` → `{fast, slow}`.
3. Fast path: if `fast.burn_rate > fast_threshold`, emit `entity.slo.burn_rate_high{severity="fast"}` (no for-duration — this is the emergency window).
4. Slow path: if `slow.burn_rate > slow_threshold` for at least `burn_rate_slow_for_seconds`, emit `entity.slo.burn_rate_high{severity="slow"}`.
5. Store `slo_burn_rate_state` for use as hysteresis reference.
6. Gauges emitted for both windows.

### Flow 4 — Burn-Rate Alert Rule Kind

1. `SLOBurnRateAlertRuleKind.evaluate(...)` reads `slo_burn_rate_state` (cached) or re-queries if stale.
2. Returns `FiringResult` with firing/resolved semantics driven by burn-rate thresholds — `7-alerts-budgets` does the rest (throttling, notification, retry).

## Error Handling

- `SemanticError` for target `>= 1.0` (division-by-zero): bubble.
- `SLOValidationError`: 400 with multiline message via `os.linesep.join([...])`.
- Kind `compute_achieved_ratio` returning out-of-range: clamp + log warn.
- `ts_facade.query_range` partial-result: honored with a `partial: True` flag in the `SLOStatus` response + `pychestrate.slo.partial_result` log.
- Cascade-delete failure when removing dependent alerts: best-effort; any failure logged + `pychestrate.slo.cascade_delete_orphan` emitted so operators can reconcile.

## Security Considerations

- `slo.read` / `slo.write` gating; project membership enforced.
- Definition redaction when caller lacks `slo.definition.read:details` — mask `definition_config` values.
- `default_notification_route_key` validated against `NotificationHub.has_route` at save time.
- Rate limit `max_slo_writes_per_hour_per_actor` (default 60).
- Cross-project SLOs are admin-only (`slo.admin`).

## Observability

Metrics:

- `pychestrate_slo_target{slo_id}` — gauge
- `pychestrate_slo_achieved{slo_id}` — gauge
- `pychestrate_slo_error_budget_remaining_ratio{slo_id}` — gauge
- `pychestrate_slo_burn_rate{slo_id,window}` — gauge
- `pychestrate_slo_burn_rate_high_total{slo_id,severity}` — counter
- `pychestrate_slo_status_duration_seconds{slo_id}` — histogram
- `pychestrate_slo_definitions_registered{kind}` — gauge

Log events: `pychestrate.slo.saved`, `pychestrate.slo.burn_rate_high`, `pychestrate.slo.definition_validation_failed`, `pychestrate.slo.partial_result`, `pychestrate.slo.cascade_delete_orphan`.

Trace spans: `pychestrate.slo.compute_status`, `pychestrate.slo.compute_burn_rate`, `pychestrate.slo.burn_rate_tick`, `pychestrate.slo.validate`.

## Open Questions

- Do we expose per-SLO multi-window tuples or stick with a fixed two-window model? Current design: fixed (short = 2 h, long = 6 h). Timebox: Phase 9 midpoint.
- Should `compute_status` be cached across REST calls? Current design: cache at the `SLOStatusService` with `status_cache_ttl_seconds` (default 30). Timebox: Phase 9 midpoint.
- Should `slo_history` persist long-term aggregates or always read-through to `0-timeseries-backend`? Current design: read-through. Timebox: Phase 9 exit.
