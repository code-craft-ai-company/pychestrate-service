# 0-timeseries-backend — Requirements

## Introduction

The `0-timeseries-backend` feature is Pychestrate's read/write abstraction
over whichever time-series store is deployed: Prometheus (via remote_write
+ PromQL), InfluxDB, TimescaleDB, or a native embedded fallback. Ownership
of concrete drivers is delegated to the `timeseries_driver` factory
protocol. The feature is listed in **Phase 0** but intentionally stood up
fully in **Phase 9** (metrics, dashboards, alerts) per the implementation
plan — the Phase 0 landing is the interface + native fallback driver so
every downstream feature has a non-throwing destination for metric writes.
Sits between `7-metrics-ingest` (producer) and `7-project-dashboards` /
`7-alerts-budgets` / `7-slo-views` (consumers).

## Requirements

### Requirement 1: Uniform Write API Across Metric Kinds

**User Story:** As a feature emitting metrics, I want a single write API
for counters, gauges, and histograms, so that my metric code does not
change when the deployment backend changes.

**Acceptance Criteria (EARS):**

1. WHEN `timeseries.write_counter(name, value, labels)` is called THEN the
   system SHALL forward the sample to the active driver with label
   cardinality validated against declared limits.
2. IF a metric name has not been declared via `MetricDefinitionExtension`
   THEN the system SHALL raise `SemanticError` — undeclared names are not
   silently coerced.
3. WHEN `timeseries.write_histogram(name, value, labels)` is called THEN
   the system SHALL route to the driver's histogram-native path when
   capability `histogram_native: True` and to a client-side bucketed
   counter otherwise.
4. WHERE the active driver is in `degraded` health THEN the system SHALL
   buffer up to `buffer_max_samples` (default 50_000) samples in memory
   and flush on recovery; samples beyond the buffer are dropped with
   counter increment.

### Requirement 2: Factory Protocol Contract Enforcement

**User Story:** As an extension author adding a new time-series backend, I
want a typed factory protocol contract, so that my driver drops in without
adapter glue.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers a `TimeseriesDriverProtocol`
   implementation THEN the system SHALL verify presence of classmethods
   `open`, `write_samples`, `query_range`, `query_instant`, `capabilities`,
   `close` AND raise `ConfigurationError` naming any missing method.
2. IF two driver implementations share `factory_protocol_name` with equal
   `PRECEDENCE` THEN the system SHALL raise `ConfigurationError` naming
   both classes at load time.
3. WHERE a caller uses `_by_order` driver selection the system SHALL
   return the implementation with the lowest numeric `PRECEDENCE`.

### Requirement 3: PromQL-Compatible Query API

**User Story:** As a dashboard tile, I want to issue PromQL-shaped range
and instant queries against whichever backend is active, so that tile
definitions are portable.

**Acceptance Criteria (EARS):**

1. WHEN `timeseries.query_range(expr, start, end, step)` is called THEN
   the system SHALL return a `RangeQueryResult` with one series per
   returned label set and `(timestamp, value)` pairs at `step` resolution.
2. IF the active driver does not natively speak PromQL THEN the driver
   SHALL translate the query internally and raise
   `UnsupportedQueryError` for functions it cannot express.
3. WHEN `timeseries.query_instant(expr, at)` is called THEN the system
   SHALL return the samples valid at time `at` within the driver's
   staleness window.

### Requirement 4: Cardinality Guardrails

**User Story:** As a service operator, I want the service to reject
high-cardinality label explosions, so that a misbehaving extension cannot
OOM the metrics pipeline.

**Acceptance Criteria (EARS):**

1. WHEN a metric's observed label-set count exceeds
   `per_metric_cardinality_max` (default 10_000) THEN the system SHALL
   drop subsequent new label sets, increment
   `pychestrate_timeseries_cardinality_rejections_total{metric}`, and log
   `pychestrate.timeseries.cardinality.limit_hit` at most once per minute
   per metric.
2. IF a label name matches `^__.*__$` (reserved double-underscore) THEN
   the system SHALL raise `SemanticError`.
3. WHERE an operator raises the cardinality cap via config reload the
   system SHALL re-admit new label sets immediately without a restart.

## Property-Based Test Requirements

### Property 1: Counter Monotonicity is Preserved End-to-End

- **Invariant:** For any sequence of `write_counter(name, delta, labels)`
  with non-negative deltas, reading the counter back via
  `query_instant(name, now)` yields a value equal to the sum of deltas
  for that label set, modulo driver staleness.
- **Generator:** `hypothesis.strategies.lists(tuples(just("pychestrate_test_counter_total"),
  integers(min_value=0, max_value=10_000), dictionaries(sampled_from(["a",
  "b", "c"]), text(min_size=1, max_size=8), max_size=3)), min_size=1,
  max_size=500)`.
- **Assertion:** `query_instant(metric, now).for_labels(labels) ==
  sum(deltas_for(labels))` after flush.
- **Sample size:** 1000 generated cases

### Property 2: Histogram Quantile Ordering

- **Invariant:** For any histogram and any two quantiles `q1 < q2`,
  `histogram_quantile(q1, buckets) <= histogram_quantile(q2, buckets)`.
- **Generator:** `hypothesis.strategies.lists(floats(min_value=0.0,
  max_value=10_000.0, allow_nan=False, allow_infinity=False), min_size=1,
  max_size=10_000)` observations, plus two quantiles from
  `floats(min_value=0.01, max_value=0.99)`.
- **Assertion:** After writing observations and reading quantiles,
  `p_low <= p_high` for every generated pair with `q_low < q_high`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Write throughput 100k samples/sec on the native
  driver on a 4 vCPU host with label cardinality ≤ 5k. `query_range`
  p99 < 400 ms for a 1h / 15s-step query returning ≤ 100 series. Write
  API p99 latency (excluding driver flush) < 50 microseconds.
- **NFR-2 (Security):** Remote-write credentials for Prometheus /
  InfluxDB / Timescale are pulled from `1-secrets-vault` (env fallback
  gated by `PYCHESTRATE_DEV_MODE`). Query endpoint is auth-gated via
  `1-authentication` and `1-rbac` permission
  `pychestrate.timeseries.query`. Metric names validated against
  `^[a-z_][a-z0-9_]*$`; label values truncated at 1 KiB.
- **NFR-3 (Observability):** Emit
  `pychestrate_timeseries_write_duration_seconds{driver,metric}` (histogram),
  `pychestrate_timeseries_samples_written_total{driver,metric}` (counter),
  `pychestrate_timeseries_samples_dropped_total{driver,metric,reason}`
  (counter, reason in `{buffer_full, cardinality, driver_unavailable}`),
  `pychestrate_timeseries_query_duration_seconds{driver,query_kind}`
  (histogram), `pychestrate_timeseries_cardinality_rejections_total{metric}`
  (counter), `pychestrate_timeseries_buffer_depth{driver}` (gauge).
  Log events `pychestrate.timeseries.driver.activated`,
  `pychestrate.timeseries.write.buffered`,
  `pychestrate.timeseries.write.dropped`,
  `pychestrate.timeseries.cardinality.limit_hit`,
  `pychestrate.timeseries.query.failed`. Trace spans
  `pychestrate.timeseries.write`, `pychestrate.timeseries.query_range`,
  `pychestrate.timeseries.query_instant`.
- **NFR-4 (Reliability):** A driver outage MUST NOT break metric
  emission: writes buffer for up to `buffer_max_samples` then drop with
  counter. On recovery, buffered samples are flushed in original order.
  Query API SHALL respond 503 during outage rather than hang.

## Out of Scope

- Alert evaluation and routing (see `7-alerts-budgets`).
- SLO definition evaluation (see `7-slo-views`).
- Dashboard composition (see `7-project-dashboards`).
- Trace/metric exemplar linkage (candidate for `10-observability` Phase
  10).
- Backfill of historical data from another store.

## Dependencies

- **Depends on:** `0-web-app-host`, `E-extension-host` (Phase 0.5 — for
  driver discovery; Phase 0 ships only the native fallback driver),
  `0-message-bus` (for `maintenance.mode.changed` and extension reload
  events), `1-secrets-vault` (deferred binding).
- **Depended on by:** `7-metrics-ingest`, `7-build-metrics`,
  `7-test-metrics`, `7-orchestration-metrics`, `7-resource-metrics`,
  `7-pod-metrics`, `7-project-dashboards`, `7-alerts-budgets`,
  `7-slo-views`.
- **Extension points exposed:** `factory: timeseries_driver` — concrete
  drivers for Prometheus (remote_write), InfluxDB, TimescaleDB, native
  SQLite-on-Pgsql, and custom backends.
