# 7-metrics-ingest — Design

## Architecture

`7-metrics-ingest` is a stateless translator service that subscribes to
every `entity.*` topic declared by a `MetricDefinitionExtension`,
converts the event into one or more `Sample` records, and writes them
through the `TimeseriesFacade` exposed by `0-timeseries-backend`. The
feature lives in **Phase 9** and owns two extension surfaces: the
`MetricDefinitionExtension` resource catalog (shared with all domain
rollups in Layer 7) and the `metric_exporter` factory protocol for
external push sinks. The ingest worker is a single logical asyncio
service (horizontally scalable by topic-partition on the bus); it
maintains only an in-memory buffer for driver-degraded periods plus
per-exporter circuit state. Authoritative metric definitions are held
by `MetricRegistry` (built once at startup from scanned extensions, then
immutable until admin-triggered re-scan); authoritative samples live in
`0-timeseries-backend`.

## Data Model

Persisted tables in `0-persistence`:

- `metric_definition_snapshot`:
  - `metric_name: str` PK
  - `kind: Literal["counter", "gauge", "histogram"]`
  - `unit: str`
  - `label_names: list[str]` (JSONB)
  - `buckets: list[float] | None` (JSONB)
  - `help_text: str`
  - `subscriptions: list[str]` (JSONB — bus topics)
  - `source_extension: str`
  - `source_version: str`
  - `registered_at: datetime`
  - `retired_at: datetime | None`
- `metric_translation_dead_letter`:
  - `dlq_id: BIGSERIAL`
  - `topic: str`
  - `event_id: UUID`
  - `payload: bytes`
  - `error_class: str`
  - `error_message: str`
  - `at: datetime`
  - Retention: 48 h via `2-retention-policies` policy `metrics_ingest_dlq`.

In-memory state on the worker:

- `metric_registry: dict[str, MetricDefinition]`
- `subscription_table: dict[str, list[SubscriptionBinding]]` — topic → bindings
- `buffer: collections.deque[Sample]` bounded at `ingest_buffer_max_samples`
- `exporter_circuits: dict[str, CircuitState]` — name → `{state, opened_at, failure_count}`

Value types:

- `SubscriptionBinding`:
  - `topic: str`
  - `metric_name: str`
  - `label_resolvers: dict[str, LabelResolver]`
  - `value_resolver: ValueResolver`
  - `emit_condition: EmitCondition | None`
- `Sample` (re-exported from `0-timeseries-backend`).
- `MetricTranslationError` — carries `topic`, `event_id`, `error_class`.
- `CircuitState` — `{state: Literal["closed","open","half_open"], opened_at, failure_count}`.

## Interfaces

### Public API

REST under `8-rest-api-v1` (admin-only, gated by `metrics.admin`):

- `GET /api/v1/metrics/definitions` → list every registered definition with source extension.
- `GET /api/v1/metrics/dead-letter?topic=&limit=&cursor=` → dead-letter inspection.
- `POST /api/v1/metrics/admin/rescan` → request extension-host re-scan.
- `GET /api/v1/metrics/exporters` → exporter status + circuit state.

### Internal API

```python
class MetricIngestWorker:
    def __init__(
        self,
        facade: TimeseriesFacade,
        registry: MetricRegistry,
        exporter_registry: MetricExporterRegistry,
        bus: MessageBus,
        clock: Clock,
        config: MetricsIngestConfig,
        dlq_repository: MetricDeadLetterRepository
    ) -> None:
        self._facade = facade
        self._registry = registry
        self._exporter_registry = exporter_registry
        self._bus = bus
        self._clock = clock
        self._config = config
        self._dlq_repository = dlq_repository
        self._buffer: "collections.deque[Sample]" = collections.deque(
            maxlen=config.ingest_buffer_max_samples
        )
        self._exporter_circuits: dict[str, CircuitState] = {}
        return

    def start(
        self
    ) -> None:
        """
            Wire every registered subscription to the bus and begin consumption.

            :returns: None.
            :raises: ConfigurationError
        """
        ...

    def stop(
        self
    ) -> None:
        """
            Drain buffer, close exporters, unsubscribe.

            :returns: None.
            :raises: None
        """
        ...

    def translate_event(
        self,
        topic: str,
        event: BusEvent
    ) -> list[Sample]:
        """
            Apply every subscription binding for a topic to a single event.

            :param topic: Bus topic the event arrived on.
            :param event: Deserialized event payload.

            :returns: Zero or more Samples ready for write.
            :raises: MetricTranslationError
        """
        ...


class MetricRegistry:
    def __init__(
        self,
        extension_host: ExtensionHost,
        config: MetricsIngestConfig
    ) -> None:
        self._extension_host = extension_host
        self._config = config
        self._metrics: dict[str, MetricDefinition] = {}
        self._subscriptions: dict[str, list[SubscriptionBinding]] = {}
        return

    def build(
        self
    ) -> None:
        """
            Scan for MetricDefinitionExtension subclasses and populate the
            in-memory registry.

            :returns: None.
            :raises: ConfigurationError
        """
        ...

    def definitions(
        self
    ) -> list[MetricDefinition]:
        """
            :returns: Registered definitions, ordered by metric_name.
        """
        ...

    def bindings_for_topic(
        self,
        topic: str
    ) -> list[SubscriptionBinding]:
        """
            :returns: Subscription bindings for a given bus topic.
        """
        ...


class MetricExporterRegistry:
    def __init__(
        self,
        extension_host: ExtensionHost,
        config: MetricsIngestConfig
    ) -> None:
        self._extension_host = extension_host
        self._config = config
        self._exporters: list[MetricExporterProtocol] = []
        return

    def build(
        self
    ) -> None:
        ...

    def fan_out(
        self,
        samples: list[Sample],
        circuits: dict[str, CircuitState]
    ) -> None:
        """
            Push a batch to every exporter whose circuit is closed or half-open.

            :returns: None.
        """
        ...
```

### Extension Surface

Resource extension declared here:

```python
class MetricDefinitionExtension(ResourceExtension):
    """
        Base for declaring a new metric family in the Pychestrate registry.
    """
    metric_name: str
    kind: Literal["counter", "gauge", "histogram"]
    unit: str
    label_names: list[str]
    help_text: str
    buckets: list[float] | None = None
    subscriptions: list[SubscriptionSpec] = []

    @classmethod
    def metric_definition(
        cls
    ) -> MetricDefinition:
        """
            :returns: Fully materialized MetricDefinition for registration.
        """
        ...
```

Factory protocol declared here:

```python
class MetricExporterProtocol(FactoryProtocolBase):
    """
        Contract for metric_exporter implementations.
    """
    factory_protocol_name: str = "metric_exporter"

    @classmethod
    def exporter_name(
        cls
    ) -> str:
        ...

    @classmethod
    def flush_interval_seconds(
        cls
    ) -> float:
        ...

    @classmethod
    def supports_exemplars(
        cls
    ) -> bool:
        ...

    @classmethod
    def export(
        cls,
        samples: list[Sample]
    ) -> None:
        """
            Push samples to the external system.

            :raises: MetricExporterError on transport failure.
        """
        ...
```

Reference implementations:

- `source/site/ccai/extensions/pychestrate/metric_definition/core_catalog.py` — declares every core `pychestrate_*` family shipped in-tree.
- `source/site/ccai/factories/pychestrate/metric_exporter/prometheus_remote_write.py` — `PRECEDENCE = 1000`; pushes to a Prometheus Remote-Write endpoint.
- `source/site/ccai/factories/pychestrate/metric_exporter/otlp.py` — `PRECEDENCE = 1100`; OTLP/HTTP sink.

### Events Emitted

- `entity.metric.definition_registered` — `{metric_name, kind, unit, label_names, source_extension, source_version, registered_at}`.
- `entity.metric.translation_failed` — `{topic, event_id, metric_name, error_class, error_message}`.

### Events Consumed

- Every `entity.*` topic for which a `MetricDefinitionExtension` declares a `SubscriptionSpec` — that is, the bus topics produced by Layers 3–6 (e.g., `entity.run.completed`, `entity.pod.state_changed`, `entity.reservation.created`, `entity.build.completed`, `entity.test.result_ingested`).
- `extension.reloaded` — drives `MetricRegistry.build()` + `MetricExporterRegistry.build()` re-scan.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/metrics/ingest/`:

- `__init__.py`
- `worker.py` — `MetricIngestWorker`.
- `registry.py` — `MetricRegistry`.
- `exporter_registry.py` — `MetricExporterRegistry`.
- `extension_base.py` — `MetricDefinitionExtension`, `SubscriptionSpec`, `LabelResolver`, `ValueResolver`.
- `exporter_protocol.py` — `MetricExporterProtocol`.
- `translation.py` — pure translator from `(event, binding) → list[Sample]`.
- `circuit.py` — per-exporter circuit breaker.
- `dead_letter.py` — DLQ writer.
- `config.py` — `MetricsIngestConfig`.
- `errors.py` — `MetricTranslationError`, `MetricExporterError`.
- `rest/v1_routes.py` — admin REST endpoints.

Factories under `source/site/ccai/factories/pychestrate/metric_exporter/`.
In-tree resource catalog under `source/site/ccai/extensions/pychestrate/metric_definition/`.

## Key Flows

### Flow 1 — Startup Registration

1. Service boots; `MetricRegistry.build()` scans `MetricDefinitionExtension` subclasses via the host.
2. Each collected class materializes a `MetricDefinition`; uniqueness check on `metric_name`; shape validation against regex.
3. `TimeseriesFacade.declare(definition)` is called; facade rejects duplicates with mismatched shape.
4. Each `SubscriptionSpec` is indexed into `subscription_table[topic]`.
5. `entity.metric.definition_registered` emitted per definition; snapshot persisted to `metric_definition_snapshot`.

### Flow 2 — Event Translation

1. `MetricIngestWorker.start()` subscribes to every topic in `subscription_table`.
2. Bus delivers an event; handler looks up bindings, runs label resolvers and value resolver for each binding.
3. Returns `list[Sample]`; each sample's label values truncated to 200 chars.
4. Batch handed to `TimeseriesFacade.write_batch(...)` and `MetricExporterRegistry.fan_out(...)`.
5. Span `pychestrate.metrics.translate` closes with `topic`, `bindings`, `samples_emitted`.

### Flow 3 — Driver Degradation

1. `TimeseriesFacade.driver_health` transitions to `degraded`.
2. Ingest worker flips to buffering: `self._buffer.append(sample)` (bounded; overflow drops oldest).
3. On recovery, worker flushes buffer in FIFO order in batches of `flush_batch_size` (default 1 000).
4. `pychestrate_metrics_ingest_buffer_depth` gauge reflects real-time state.

### Flow 4 — Exporter Circuit Break

1. Exporter `export(...)` raises `MetricExporterError` five times consecutively.
2. Circuit transitions `closed → open`; `opened_at = now`.
3. While `open`, exporter skipped; gauge `pychestrate_metric_exporter_circuit_opened{exporter}` = 1.
4. After `exporter_circuit_open_seconds`, circuit → `half_open`; next batch is a probe.
5. Success closes the circuit; failure reopens for a doubled window (capped at 600 s).

## Error Handling

- `SemanticError` for duplicate metric name with mismatched shape, invalid metric name pattern, invalid label name pattern: bubble.
- `MetricTranslationError`: caught at the worker boundary, written to DLQ, metric incremented, processing continues.
- `MetricExporterError`: fed to the circuit breaker; never bubbles past fan-out.
- `ConfigurationError` for missing classmethods on `MetricExporterProtocol` implementations: caught at host-load time and logged; the offending extension is skipped.
- Multiline errors built via `os.linesep.join([...])` listing `topic`, `event_id`, resolver trace.

## Security Considerations

- Admin REST endpoints gated by `metrics.admin`.
- `GET /api/v1/metrics/dead-letter` returns *metadata only* unless the caller has `metrics.dlq.read:payload`; payload bodies redacted otherwise.
- Exporter credentials live in `1-secrets-vault` under `ext.metrics_ingest.<exporter_name>.credentials`; worker reads through the scoped service principal.
- Label value truncation at 200 chars guards against pathological event payloads inflating backend storage.
- Rescan endpoint rate-limited to 6 calls/hour per admin to prevent registry thrash.

## Observability

Metrics:

- `pychestrate_metrics_ingest_events_total{topic,outcome}` — counter
- `pychestrate_metrics_ingest_translation_duration_seconds{topic}` — histogram
- `pychestrate_metrics_ingest_buffer_depth` — gauge
- `pychestrate_metrics_ingest_dropped_total{reason}` — counter
- `pychestrate_metric_exporter_circuit_opened{exporter}` — gauge
- `pychestrate_metric_exporter_export_duration_seconds{exporter}` — histogram
- `pychestrate_metric_definitions_registered` — gauge (cardinality of registry)

Log events: `pychestrate.metrics.definition_registered`, `pychestrate.metrics.translation_failed`, `pychestrate.metrics.exporter_circuit_opened`, `pychestrate.metrics.exporter_circuit_closed`, `pychestrate.metrics.rescan_completed`.

Trace spans: `pychestrate.metrics.translate`, `pychestrate.metrics.write_batch`, `pychestrate.metrics.exporter_fanout`, `pychestrate.metrics.registry_build`.

## Open Questions

- Do we partition the ingest worker by topic-hash for horizontal scale, or keep a single worker until 5 000 events/s? Timebox: Phase 9 midpoint.
- Should dead-letter retention be configurable per-topic or globally? Timebox: Phase 9 midpoint.
- Is exemplar support a facade concern or per-exporter? Current design pushes it to per-exporter — revisit when OTLP driver matures. Timebox: Phase 9 exit.
