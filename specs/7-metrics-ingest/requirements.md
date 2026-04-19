# 7-metrics-ingest — Requirements

## Introduction

The `7-metrics-ingest` feature is the single funnel that turns every
`entity.*` domain event emitted by Layers 3/4/5/6 into metric writes on
`0-timeseries-backend`. It owns the `MetricDefinitionExtension` resource
catalog (shared across the Layer 7 domain-rollup features), the
`metric_exporter` factory protocol (push-to-external-system side-channel),
and the subscription wiring that attaches declared mappings to
`0-message-bus` topics. The feature lands in **Phase 9** alongside
`0-timeseries-backend` completion and sits between the event-producing
layers upstream and the domain-rollup features (`7-build-metrics`,
`7-test-metrics`, `7-orchestration-metrics`, `7-resource-metrics`,
`7-pod-metrics`) downstream, which register their own
`MetricDefinitionExtension` resources against this feature. The
authoritative source of truth for emitted samples is
`0-timeseries-backend`; this feature is a *stateless translator* whose
only persisted state is the set of currently-wired subscriptions.

## Requirements

### Requirement 1: Event-Driven Metric Emission

**User Story:** As a platform operator, I want every significant domain
event to produce the metric samples declared for it, so that dashboards
and alerts are populated without any producer needing to know about the
timeseries backend.

**Acceptance Criteria (EARS):**

1. WHEN `0-message-bus` delivers an `entity.*` event matching a subscription declared by a `MetricDefinitionExtension` THEN the system SHALL translate the event into the declared `Sample` list AND write it through `TimeseriesFacade.write_batch(...)` within 250 ms of bus delivery (p99).
2. IF a declared label resolver raises during translation THEN the system SHALL catch-and-reclassify as `MetricTranslationError`, write the event to a dead-letter topic `entity.metric.translation_failed`, AND continue processing subsequent events without dropping the subscription.
3. WHILE `TimeseriesFacade.driver_health` is `degraded` the system SHALL buffer writes up to `ingest_buffer_max_samples` (default 50 000) AND flush on recovery in first-in-first-out order.
4. WHERE an event carries a `trace_id` attribute the system SHALL propagate it as an `exemplar` on the resulting histogram sample.

### Requirement 2: MetricDefinitionExtension Resource Catalog

**User Story:** As an extension author, I want to declare a new metric
family by shipping a single resource class, so that I do not need to
modify core code to surface a new counter/gauge/histogram.

**Acceptance Criteria (EARS):**

1. WHEN the extension host scans a package THEN the system SHALL collect every direct subclass of `MetricDefinitionExtension` AND register `(name, kind, unit, label_names, help_text, buckets, subscriptions)` into the in-process `metric_registry`.
2. IF two `MetricDefinitionExtension` subclasses share `metric_name` but differ on `kind` or `label_names` THEN the system SHALL raise `ConfigurationError` at load time naming both extensions.
3. IF a metric declaration's `metric_name` does not match `pychestrate_[a-z0-9_]+` THEN the system SHALL raise `ConfigurationError`.
4. WHEN a metric is newly registered THEN the system SHALL emit `entity.metric.definition_registered` with the full definition payload.

### Requirement 3: External Exporter Factory Protocol

**User Story:** As a platform owner who already runs Datadog, I want to
plug in a `metric_exporter` implementation so that Pychestrate ships
copies of every sample to our existing dashboards without losing the
in-tree native timeseries backend.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers a `MetricExporterProtocol` implementation THEN the system SHALL verify the classmethods `exporter_name`, `export`, `flush_interval_seconds` AND raise `ConfigurationError` when any is missing.
2. WHEN a sample is written through the facade THEN the system SHALL fan it out to every registered exporter via `exporter.export(samples)` in precedence order, wrapping each in a bounded `asyncio.wait_for(...)` with `exporter_timeout_seconds` (default 2.0).
3. IF an exporter raises repeatedly (>= `exporter_circuit_open_threshold`, default 5 consecutive failures) THEN the system SHALL open a per-exporter circuit breaker for `exporter_circuit_open_seconds` (default 60) AND emit `pychestrate_metric_exporter_circuit_opened` gauge transition.
4. WHERE an exporter declares `supports_exemplars: True` the system SHALL forward exemplar trace ids AND otherwise strip them before calling `export`.

## Property-Based Test Requirements

### Property 1: Bounded Cardinality Under Bounded Event Universe

- **Invariant:** For any sequence of `N` events whose label sources draw from a universe of `K` distinct label-tuples, the emitted metric label cardinality is `<= K` — the translator never invents new label values.
- **Generator:** `hypothesis.strategies.lists(events(universe_size=K), min_size=0, max_size=2000)` with `K` in `integers(min_value=1, max_value=50)`.
- **Assertion:** `len(set((s.metric_name, frozenset(s.labels.items())) for s in samples)) <= K * number_of_registered_metrics_for_topic`.
- **Sample size:** 1000 generated cases

### Property 2: Subscription Isolation

- **Invariant:** For any two independent subscriptions `S1` and `S2` wired to disjoint topic sets, delivering an event to topic `S1.topic` produces only samples belonging to `S1.metric_name` — there is no cross-contamination between unrelated subscriptions.
- **Generator:** `hypothesis.strategies.tuples(subscription(), subscription(), event_for_topic())` with a post-filter enforcing disjoint topics.
- **Assertion:** For every generated delivery, `{s.metric_name for s in samples} ⊆ {S1.metric_name}`.
- **Sample size:** 1000 generated cases

### Property 3: Translation Failure Does Not Drop Subsequent Events

- **Invariant:** For any interleaved sequence of valid and poison-pill events, every valid event still produces its declared samples.
- **Generator:** `hypothesis.strategies.lists(one_of(valid_event(), poison_event()), min_size=1, max_size=500)`.
- **Assertion:** `count(valid_events_in_sequence) == count(samples_for_valid_events)`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** End-to-end event-to-sample latency p99 < 250 ms at 2 000 events/s steady state on a single ingest worker. Extension registry scan at startup < 750 ms for 500 declared metrics. Exporter fan-out overhead p99 < 10 ms per sample batch per exporter when circuit closed.
- **NFR-2 (Security):** Only the scoped service principal `svc.metrics-ingest` may call `TimeseriesFacade.write_batch`. Exporter configuration lives in `2-global-variables` keyspace `ext.metrics_ingest.<exporter_name>.*`; secrets in `1-secrets-vault`. Label values SHALL be truncated at 200 chars before write to prevent cardinality-blow-up attacks.
- **NFR-3 (Observability):** Metrics `pychestrate_metrics_ingest_events_total{topic,outcome}` (counter), `pychestrate_metrics_ingest_translation_duration_seconds{topic}` (histogram), `pychestrate_metrics_ingest_buffer_depth` (gauge), `pychestrate_metrics_ingest_dropped_total{reason}` (counter), `pychestrate_metric_exporter_circuit_opened{exporter}` (gauge). Log events `pychestrate.metrics.definition_registered`, `pychestrate.metrics.translation_failed`, `pychestrate.metrics.exporter_circuit_opened`, `pychestrate.metrics.exporter_circuit_closed`. Trace spans `pychestrate.metrics.translate`, `pychestrate.metrics.write_batch`, `pychestrate.metrics.exporter_fanout`.
- **NFR-4 (Reliability):** A poison-pill event SHALL NOT stop the subscription; the dead-letter path SHALL retain the event for 48 h for inspection. Buffer overflow SHALL drop oldest samples and increment `pychestrate_metrics_ingest_dropped_total{reason="buffer_overflow"}` rather than backpressuring the bus.

## Out of Scope

- Query-side read API (owned by `0-timeseries-backend`).
- Per-domain metric definitions themselves (owned by `7-build-metrics`, `7-test-metrics`, `7-orchestration-metrics`, `7-resource-metrics`, `7-pod-metrics`).
- Alert threshold evaluation (owned by `7-alerts-budgets`).
- Tile rendering (owned by `7-project-dashboards` + `9-wc-metric-tile`).

## Dependencies

- **Depends on:** `0-timeseries-backend`, `0-message-bus`, `0-persistence` (for dead-letter table), `E-extension-host`, `E-resource-extensions`, `E-factory-protocols`, `1-secrets-vault`, `2-global-variables`.
- **Depended on by:** `7-build-metrics`, `7-test-metrics`, `7-orchestration-metrics`, `7-resource-metrics`, `7-pod-metrics`, `7-project-dashboards`, `7-alerts-budgets`, `7-slo-views`.
- **Extension points exposed:** `factory: metric_exporter` · `resource: MetricDefinitionExtension` · `event: entity.metric.definition_registered` · `event: entity.metric.translation_failed`.
