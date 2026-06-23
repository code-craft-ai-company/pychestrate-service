# 7-metrics-ingest — Tasks

## Milestones

- **M1 — Skeleton:** `MetricDefinitionExtension` base, `MetricRegistry` startup scan, single subscription → `TimeseriesFacade.write_batch(...)`, core catalog stub, admin list endpoint.
- **M2 — Core Behavior:** Full translator (label resolvers, value resolvers, emit conditions), dead-letter path, `MetricExporterProtocol` + Prometheus Remote-Write impl, circuit breaker, rescan endpoint.
- **M3 — Hardening:** Buffering under driver degradation, OTLP exporter, exemplar propagation, metrics/logs/traces, perf benchmarks, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/ccai/pychestrate/webservice/metrics/ingest/` package skeleton per design.md Component Breakdown.
- [ ] T1.2 — Implement `extension_base.py::MetricDefinitionExtension` with `SubscriptionSpec`, `LabelResolver`, `ValueResolver` value types.
- [ ] T1.3 — Implement `registry.py::MetricRegistry.build()` scanning `MetricDefinitionExtension` subclasses via `E-extension-host` and populating `_metrics` + `_subscriptions`.
- [ ] T1.4 — Add `0-persistence` migration for `metric_definition_snapshot` and `metric_translation_dead_letter`.
- [ ] T1.5 — Implement `worker.py::MetricIngestWorker.start()` subscribing to a single bootstrap topic (`entity.run.completed`) and writing to `TimeseriesFacade`.
- [ ] T1.6 — Ship core in-tree catalog stub `source/site/ccai/extensions/pychestrate/metric_definition/core_catalog.py` with `pychestrate_metric_definitions_registered` and `pychestrate_metrics_ingest_events_total`.
- [ ] T1.7 — Register `GET /api/v1/metrics/definitions` admin endpoint under `8-rest-api-v1`.
- [ ] T1.8 — Emit `entity.metric.definition_registered` on each successful registration.

### M2 — Core Behavior

- [ ] T2.1 — Implement full `translation.py` applying every binding for a topic, returning `list[Sample]`; 200-char label truncation.
- [ ] T2.2 — Implement dead-letter writer `dead_letter.py`; wire `MetricTranslationError` path in the worker to append + emit `entity.metric.translation_failed`.
- [ ] T2.3 — Implement `exporter_protocol.py::MetricExporterProtocol` and `exporter_registry.py::MetricExporterRegistry.build()`.
- [ ] T2.4 — Implement reference exporter `source/site/ccai/factories/pychestrate/metric_exporter/prometheus_remote_write.py` (`PRECEDENCE = 1000`).
- [ ] T2.5 — Implement `circuit.py` per-exporter circuit breaker with `exporter_circuit_open_threshold`, `exporter_circuit_open_seconds`.
- [ ] T2.6 — Wire fan-out: `TimeseriesFacade.write_batch(...)` + `MetricExporterRegistry.fan_out(...)` after every translation batch.
- [ ] T2.7 — Add uniqueness + shape validation in `MetricRegistry.build()` — raise `ConfigurationError` on conflicting `metric_name`.
- [ ] T2.8 — Register `POST /api/v1/metrics/admin/rescan` and `GET /api/v1/metrics/dead-letter` + `GET /api/v1/metrics/exporters` endpoints.
- [ ] T2.9 — Subscribe to every `entity.*` topic declared by the collected `SubscriptionSpec` list.

### M3 — Hardening

- [ ] T3.1 — Implement bounded `collections.deque` buffer in the worker; flush on driver-health recovery; emit `pychestrate_metrics_ingest_buffer_depth`.
- [ ] T3.2 — Implement OTLP exporter `source/site/ccai/factories/pychestrate/metric_exporter/otlp.py` (`PRECEDENCE = 1100`) with `supports_exemplars = True`.
- [ ] T3.3 — Implement exemplar propagation when events carry `trace_id`.
- [ ] T3.4 — Emit all Prometheus metrics and OTel spans listed in design.md Observability.
- [ ] T3.5 — Benchmark NFR-1: 2 000 events/s sustained with p99 < 250 ms end-to-end; 500-metric registry scan < 750 ms. Fail CI on regression.
- [ ] T3.6 — Rate-limit `POST /admin/rescan` to 6/hour/actor.
- [ ] T3.7 — Sphinx docs for `MetricDefinitionExtension` authoring and `MetricExporterProtocol` authoring.
- [ ] T3.8 — Hook `2-retention-policies` to sweep `metric_translation_dead_letter` older than 48 h.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (bounded cardinality), Property 2 (subscription isolation), Property 3 (poison tolerance) at 1000 cases each.
- [ ] TT-3 — Integration test: emit 10 000 mixed `entity.*` events across 20 topics; verify every declared metric appears in `TimeseriesFacade` and exporter receives an identical copy.
- [ ] TT-4 — Extension-point test: test-only `RecordingExporter` (`PRECEDENCE = 1`) intercepts samples; asserts precedence ordering; circuit breaker opens after forced failures.
- [ ] TT-5 — Extension-point test: test-only `MetricDefinitionExtension` subclass with a new `pychestrate_testonly_*` metric is auto-registered and emits on its declared topic.
- [ ] TT-6 — Buffer-overflow test: force `driver_health=unavailable` and push 200 000 samples; verify bounded loss and gauge transitions.
- [ ] TT-7 — DLQ test: send malformed event to a bound topic; assert DLQ row written, dead-letter event emitted, subsequent valid event still processed.

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
