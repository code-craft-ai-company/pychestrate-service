# 0-timeseries-backend — Tasks

## Milestones

- **M1 — Skeleton:** Facade + `NativePgTimeseriesDriver`, metric
  registry seeded from a hardcoded in-tree metric list, counter and
  gauge writes, buffer, startup/shutdown hooks. No query API yet.
- **M2 — Core Behavior:** Factory protocol declaration, histograms,
  cardinality guardrails, PromQL-shaped range + instant queries on the
  native driver, REST endpoints, `MetricDefinitionExtension` wiring
  once Phase 0.5 lands.
- **M3 — Hardening:** Phase 9 drivers (Prometheus remote_write, Influx,
  Timescale), degradation + buffered replay, property tests, docs,
  perf validation.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/timeseries/` package skeleton per design.md.
- [ ] T1.2 — Implement `timeseries/config.py::TimeseriesConfig` and `DriverConfig`.
- [ ] T1.3 — Implement `timeseries/metric_registry.py::MetricRegistry`, `MetricDefinition` (counter, gauge, histogram kinds).
- [ ] T1.4 — Implement `timeseries/driver_base.py::TimeseriesDriver` abstract class.
- [ ] T1.5 — Implement `timeseries/facade.py::TimeseriesFacade.write_counter` and `write_gauge` with definition lookup + basic label validation.
- [ ] T1.6 — Implement `NativePgTimeseriesDriver` at `source/site/automojo/factories/pychestrate/timeseries/native_pg.py` (`PRECEDENCE = 1000`) writing to partitioned `core.ts_samples`.
- [ ] T1.7 — Add core migrations for `core.ts_samples` (monthly partitioned by `observed_at`) via `0-persistence`.
- [ ] T1.8 — Register `timeseries_startup_hook` at priority `35` and `timeseries_shutdown_hook` on the web app.

### M2 — Core Behavior

- [ ] T2.1 — Implement `timeseries/protocol.py::TimeseriesDriverProtocol` declaring `factory_protocol_name = "timeseries_driver"` and required classmethods.
- [ ] T2.2 — Implement `write_histogram` routing between driver-native histograms and client-side bucketed counters per capability.
- [ ] T2.3 — Implement `timeseries/cardinality.py::CardinalityCounter` with per-metric cap, drop-with-counter, rate-limited log (once/min/metric).
- [ ] T2.4 — Implement `timeseries/buffer.py` bounded write buffer with background flush thread.
- [ ] T2.5 — Implement `query_range` and `query_instant` on `NativePgTimeseriesDriver` supporting the PromQL subset `{=,!=,=~,!~}`, `rate()`, `sum by()`, `histogram_quantile()`.
- [ ] T2.6 — Expose REST endpoints `POST /api/v1/metrics/query_range` and `POST /api/v1/metrics/query_instant` gated by `pychestrate.timeseries.query` permission.
- [ ] T2.7 — Wire `MetricDefinitionExtension` discovery once `E-resource-extensions` ships (Phase 0.5); until then seed from an in-tree list.
- [ ] T2.8 — Publish `timeseries.driver.activated`, `timeseries.driver.degraded`, `timeseries.driver.recovered`, `timeseries.write.dropped` events on the bus.

### M3 — Hardening

- [ ] T3.1 — Implement `PrometheusRemoteWriteTimeseriesDriver` with `PRECEDENCE = 500` (lands in Phase 9).
- [ ] T3.2 — Implement `InfluxDbTimeseriesDriver` and `TimescaleDbTimeseriesDriver` (`PRECEDENCE = 500` and `400`, Phase 9).
- [ ] T3.3 — Implement driver degradation: on `write_samples` failure, flip health to `degraded`, queue into buffer, retry on a backoff schedule, replay on recovery.
- [ ] T3.4 — Benchmark: native driver 100k samples/sec at cardinality ≤ 5k; range query p99 < 400 ms for 1h/15s/100 series; write API p99 < 50 µs. Fail CI on regression (NFR-1).
- [ ] T3.5 — Add Prometheus metrics and OTel spans per design.md Observability; audit label cardinality.
- [ ] T3.6 — Document each driver's config under `usersguide/timeseries/drivers/<name>.rst`.
- [ ] T3.7 — Verify multiline error messages use `os.linesep.join([...])`.
- [ ] T3.8 — Chaos test: kill native driver Postgres connection mid-write; assert buffered samples, recovery, zero loss up to buffer depth.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (counter monotonicity end-to-end) and Property 2 (histogram quantile ordering), 1000 cases each.
- [ ] TT-3 — Integration test: Phase 9 exit criterion — a dashboard tile issues a `query_range` that returns an expected time series over the native driver, and a second run with a test-only extension-registered driver returns the same shape.
- [ ] TT-4 — Extension-point test: in-tree `NativePgTimeseriesDriver` (`PRECEDENCE = 1000`) plus a test-only `MemoryTimeseriesDriver` (`PRECEDENCE = 10`) registered at test setup; assert memory driver wins, writes and queries route there, and removal falls back to native.
- [ ] TT-5 — Cardinality test: write 20_000 unique label sets to a metric capped at 10_000; assert only the first 10_000 are admitted and `pychestrate_timeseries_cardinality_rejections_total` equals 10_000.
- [ ] TT-6 — Degradation test: drop the driver, write 1_000 samples (< buffer), restore the driver, assert all 1_000 samples arrive in order.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
