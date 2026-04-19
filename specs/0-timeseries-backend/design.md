# 0-timeseries-backend — Design

## Architecture

The time-series backend is a `TimeseriesFacade` that dispatches to a single
active `TimeseriesDriver` selected by the extension host at startup from
the `timeseries_driver` factory protocol registry. The facade owns
cross-cutting concerns: metric-definition resolution, cardinality
guardrails, label validation, buffering during driver degradation, and
read/write span emission. The active driver is the authoritative source of
truth for stored samples; the facade maintains only a bounded in-memory
buffer for resilience. The Phase 0 landing stands up the *facade and
native fallback* so downstream features have a non-throwing sink.
Prometheus / Influx / Timescale drivers land in Phase 9 through the
extension host, repeating the Phase 0.5 pattern `0-object-store`
establishes for driver discovery.

## Data Model

Persistent state lives inside each driver's backend; the facade holds:

- `metric_registry: dict[str, MetricDefinition]` — seeded from
  `MetricDefinitionExtension` resources.
- `cardinality_state: dict[str, CardinalityCounter]` — one per metric.
- `active_driver: TimeseriesDriver`
- `write_buffer: Deque[Sample]` — bounded at `buffer_max_samples`
- `driver_health: DriverHealth` — `healthy | degraded | unavailable`

Value types:

- `MetricDefinition`:
  - `name: str`
  - `kind: Literal["counter", "gauge", "histogram"]`
  - `label_names: list[str]`
  - `buckets: list[float] | None` (histograms)
  - `help_text: str`
  - `cardinality_max: int`
- `Sample`:
  - `metric_name: str`
  - `labels: dict[str, str]`
  - `value: float`
  - `observed_at: datetime`
- `RangeQueryResult`:
  - `series: list[Series]`
  - `step_seconds: int`
- `Series`:
  - `labels: dict[str, str]`
  - `points: list[tuple[datetime, float]]`

Native driver persists samples to a Postgres partition table `core.ts_samples`
with hypertable-style monthly partitions; TimescaleDB is optional on top.

## Interfaces

### Public API

HTTP (under `/api/v1/metrics/` — gated by permission
`pychestrate.timeseries.query`):

- `POST /api/v1/metrics/query_range` — body
  `{expr, start, end, step}` → `RangeQueryResult`.
- `POST /api/v1/metrics/query_instant` — body `{expr, at}` →
  `InstantQueryResult`.

No public write endpoint — writes come from in-process
`7-metrics-ingest`.

### Internal API

```python
class TimeseriesFacade:
    def __init__(
        self,
        driver: TimeseriesDriver,
        metric_registry: MetricRegistry,
        config: TimeseriesConfig
    ) -> None:
        self._driver = driver
        self._metric_registry = metric_registry
        self._config = config
        self._buffer: deque = deque(maxlen=config.buffer_max_samples)
        return

    def write_counter(
        self,
        name: str,
        delta: float,
        labels: dict[str, str]
    ) -> None:
        """
            Record a counter delta.

            :param name: Declared metric name.
            :param delta: Non-negative increment.
            :param labels: Label set; names must match declaration.

            :returns: None
            :raises: SemanticError on undeclared name or reserved label.
        """
        ...

    def write_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str]
    ) -> None:
        """
            Record a gauge sample.

            :param name: Declared metric name.
            :param value: Current value.
            :param labels: Label set.

            :returns: None
            :raises: SemanticError
        """
        ...

    def write_histogram(
        self,
        name: str,
        observation: float,
        labels: dict[str, str]
    ) -> None:
        """
            Record a histogram observation.

            :param name: Declared metric name.
            :param observation: Observed value.
            :param labels: Label set.

            :returns: None
            :raises: SemanticError
        """
        ...

    def query_range(
        self,
        expr: str,
        start: datetime,
        end: datetime,
        step_seconds: int
    ) -> RangeQueryResult:
        """
            Evaluate a PromQL-shaped range query.

            :param expr: PromQL expression.
            :param start: Range start.
            :param end: Range end.
            :param step_seconds: Step resolution.

            :returns: RangeQueryResult with one Series per matched label set.
            :raises: UnsupportedQueryError, DriverUnavailableError
        """
        ...

    def query_instant(
        self,
        expr: str,
        at: datetime
    ) -> InstantQueryResult:
        """
            Evaluate a PromQL-shaped instant query.

            :param expr: PromQL expression.
            :param at: Evaluation timestamp.

            :returns: InstantQueryResult.
            :raises: UnsupportedQueryError, DriverUnavailableError
        """
        ...
```

### Extension Surface

Factory protocol declared here:

```python
class TimeseriesDriverProtocol(FactoryProtocolBase):
    """
        Contract for timeseries_driver implementations.

        Every implementing class inherits FactoryExtension, sets
        factory_protocol_name = "timeseries_driver", and assigns an
        integer PRECEDENCE (lower wins).
    """
    factory_protocol_name: str = "timeseries_driver"

    @classmethod
    def open(
        cls,
        config: DriverConfig,
        secrets: SecretsAccessor
    ) -> TimeseriesDriver:
        """
            Instantiate and connect the driver.

            :param config: Driver-specific configuration.
            :param secrets: Read-only accessor for vault secrets.

            :returns: A ready-to-use TimeseriesDriver.
            :raises: ConfigurationError, DriverUnavailableError
        """
        ...

    @classmethod
    def capabilities(cls) -> TimeseriesDriverCapabilities:
        """
            Report driver capabilities.

            :returns: TimeseriesDriverCapabilities (histogram_native,
                      exemplars, pushgateway, promql_native,
                      max_query_range_days).
            :raises: None
        """
        ...
```

`TimeseriesDriver` instance methods required: `write_samples(samples)`,
`query_range(expr, start, end, step)`, `query_instant(expr, at)`,
`flush()`, `health()`, `close()`.

Reference implementations shipped in-tree (under
`source/site/automojo/factories/pychestrate/timeseries/`):

- `NativePgTimeseriesDriver` — `PRECEDENCE = 1000`. Postgres-partitioned
  table; works on every deployment since Postgres is already required by
  `0-persistence`. Always available. Ships in Phase 0.
- `PrometheusRemoteWriteTimeseriesDriver` — `PRECEDENCE = 500`. Ships in
  Phase 9.
- `InfluxDbTimeseriesDriver` — `PRECEDENCE = 500`. Phase 9.
- `TimescaleDbTimeseriesDriver` — `PRECEDENCE = 400`. Phase 9.

Operators / site extensions override by shipping a lower-PRECEDENCE driver
(e.g., `100` for an internal Mimir endpoint).

### Events Emitted

- `timeseries.driver.activated` — `{driver_class: str, capabilities:
  TimeseriesDriverCapabilities}`
- `timeseries.driver.degraded` — `{driver_class: str, reason: str}`
- `timeseries.driver.recovered` — `{driver_class: str, replayed_samples: int}`
- `timeseries.write.dropped` — `{metric: str, reason: str, count: int}`

### Events Consumed

- `maintenance.mode.changed` — pause queries if a project is in
  maintenance (writes continue; historical inspection is blocked).
- `extension.reloaded` — re-resolve active driver and re-import
  `MetricDefinitionExtension` resources.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/`:

- `timeseries/__init__.py`
- `timeseries/config.py` — `TimeseriesConfig`, `DriverConfig`.
- `timeseries/facade.py` — `TimeseriesFacade`.
- `timeseries/metric_registry.py` — `MetricRegistry`,
  `MetricDefinition`.
- `timeseries/cardinality.py` — `CardinalityCounter`, rejection logic.
- `timeseries/buffer.py` — bounded write buffer with oldest-drop policy.
- `timeseries/protocol.py` — `TimeseriesDriverProtocol`.
- `timeseries/driver_base.py` — abstract `TimeseriesDriver` base.
- `timeseries/errors.py` — `UnsupportedQueryError`,
  `DriverUnavailableError`, `CardinalityLimitError`.
- `timeseries/hooks.py` — startup / shutdown hooks.
- `timeseries/promql_translate/` — helpers for non-native drivers to map
  PromQL AST nodes (shared across Influx / Timescale drivers).

Factories under
`source/site/automojo/factories/pychestrate/timeseries/`:

- `native_pg.py` — `NativePgTimeseriesDriver`
- (Phase 9) `prometheus_remote_write.py`, `influxdb.py`, `timescale_db.py`

## Key Flows

### Flow 1 — Write counter

1. Feature calls
   `timeseries.write_counter("pychestrate_runs_completed_total", 1, {"project": "proj-a", "outcome": "pass"})`.
2. Facade looks up `MetricDefinition`; missing → `SemanticError`.
3. Facade validates label names against definition and rejects reserved
   double-underscore names.
4. Facade consults `CardinalityCounter` — new label set beyond cap →
   drop with counter increment + rate-limited log.
5. Sample enqueued into `write_buffer`.
6. Background flush batches and calls `driver.write_samples(batch)`.
7. On driver success, metric
   `pychestrate_timeseries_samples_written_total` increments; on failure
   the driver flips to `degraded` and buffered samples remain.

### Flow 2 — Startup driver resolution

1. Host startup hook priority `35` fires.
2. Hook queries extension host for `timeseries_driver` ordered by
   `PRECEDENCE`.
3. First driver whose `open()` succeeds becomes `active_driver`.
4. Metric definitions are loaded from
   `MetricDefinitionExtension` resources and frozen into the registry.
5. `timeseries.driver.activated` is published.

### Flow 3 — Range query from a dashboard tile

1. Tile REST call → `POST /api/v1/metrics/query_range`.
2. Handler checks RBAC permission `pychestrate.timeseries.query` scoped
   to the project embedded in the label matcher.
3. Handler calls `facade.query_range(expr, start, end, step)`.
4. Facade delegates to driver; non-PromQL-native driver translates AST,
   raising `UnsupportedQueryError` on unsupported functions.
5. Response serialized and returned.

## Error Handling

- `SemanticError` (undeclared metric, reserved label, facade closed):
  bubbles — never caught.
- `CardinalityLimitError` is internal-only; the facade converts it to a
  silent drop + metric + rate-limited log so producers are not impacted.
- `DriverUnavailableError` during writes: buffer the sample, flip health
  to `degraded`, continue. During queries: bubble as 503.
- `UnsupportedQueryError`: bubbles as 400.
- `ConfigurationError` from bad metric definition or bad driver config at
  startup: bubbles to host, process exits code 78.

Multiline error example:

```python
err_msg_lines = ["Undeclared metric write rejected."]
err_msg_lines.append("METRIC NAME: {}".format(name))
err_msg_lines.append("CALLER FRAME: {}".format(caller_frame))
err_msg_lines.append("HINT: register via MetricDefinitionExtension first")

err_msg = os.linesep.join(err_msg_lines)
raise SemanticError(err_msg) from None
```

## Security Considerations

- Driver credentials from `1-secrets-vault`; env fallback gated by
  `PYCHESTRATE_DEV_MODE`.
- Query endpoints require `pychestrate.timeseries.query` permission,
  project-scoped by label matcher extraction.
- Metric names validated against `^[a-z_][a-z0-9_]*$`; label values
  truncated at 1 KiB to prevent accidental PII spillage.
- Reserved labels `__name__`, `__project__`, `__tenant__` are
  service-managed; user writes rejected.
- Native driver's Postgres role has INSERT and SELECT only on
  `core.ts_samples`.

## Observability

Metrics:

- `pychestrate_timeseries_write_duration_seconds{driver,metric}` — histogram
- `pychestrate_timeseries_samples_written_total{driver,metric}` — counter
- `pychestrate_timeseries_samples_dropped_total{driver,metric,reason}` — counter
- `pychestrate_timeseries_query_duration_seconds{driver,query_kind}` — histogram
- `pychestrate_timeseries_cardinality_rejections_total{metric}` — counter
- `pychestrate_timeseries_buffer_depth{driver}` — gauge

Log events:

- `pychestrate.timeseries.driver.activated`
- `pychestrate.timeseries.driver.degraded`
- `pychestrate.timeseries.driver.recovered`
- `pychestrate.timeseries.write.buffered`
- `pychestrate.timeseries.write.dropped`
- `pychestrate.timeseries.cardinality.limit_hit`
- `pychestrate.timeseries.query.failed`

Trace spans:

- `pychestrate.timeseries.write` — attrs `driver`, `metric`, `batch_size`
- `pychestrate.timeseries.query_range` — attrs `driver`, `expr`, `series`
- `pychestrate.timeseries.query_instant`

Dashboards: backend-health tile under `9-admin-ui`; cardinality trend
tile under `7-orchestration-metrics`.

## Open Questions

- Does the native driver need continuous aggregates (materialized 5m /
  1h rollups) in Phase 0, or is raw-only acceptable until Phase 9?
  Timebox: Phase 9 start.
- Query-side PromQL translation — vend the subset of functions we
  guarantee, or rely on each driver to self-report? Timebox: Phase 9
  scoping.
- Should `MetricDefinitionExtension` registration be frozen at startup
  (current plan) or mutable on extension hot-reload? Timebox: Phase 0.5
  exit.
