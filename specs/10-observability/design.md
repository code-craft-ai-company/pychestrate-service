# 10-observability — Design

## Architecture

`10-observability` lives under
`source/site/ccai/pychestrate/webservice/ops/observability/`. It is
wired into the Phase 0 boot sequence so every subsequent feature emits
through it. Internally it owns (1) a `TraceContextManager` — the
singleton that holds the current trace via a `contextvars.ContextVar`,
adopts/constructs `traceparent`, and produces child spans; (2) a
`StructuredLogger` — the JSON-emitting logger every feature uses; (3)
a `MetricsCollector` shim that attaches trace exemplars when sampling
is on; (4) a `SpanProcessor` that collects finished spans, applies the
tail keep-on-error rule, batches, and hands batches to a registered
`trace_exporter`; (5) the factory protocol for `trace_exporter` and the
default `OtlpGrpcTraceExporter`. Authoritative state: the trace context
for a given thread/task lives in a `ContextVar`; the export queue lives
in a bounded `queue.Queue` owned by the `SpanProcessor`; exporter
credentials and the currently-active exporter configuration are
resolved at startup (or on `on_service_ready` hook for
extension-registered exporters) from `1-secrets-vault`. The feature
does *not* own a timeseries sink — that is `0-timeseries-backend`; the
`MetricsCollector` shim registers the pychestrate_trace_* metrics with
whatever collector that feature exposes.

## Data Model

State is predominantly in-memory. A small persistent surface exists
for operator visibility:

`trace_exporter_state` — which exporter is currently active:

- `active_exporter_name: str` — PK (single row).
- `configured_at: datetime`.
- `configured_by: UUID`.
- `configuration_sha256: str` — fingerprint of the config blob for
  change tracking.

`trace_exporter_events` — append-only exporter change log:

- `event_id: UUID`, `kind: TraceExporterEventKind`
  (`{LOADED, FAILED, RELOADED}`), `exporter_name: str`,
  `reason: Optional[str]`, `occurred_at: datetime`.

In-memory structures:

- `TraceContext`:
  - `trace_id: str` — 32 hex chars.
  - `span_id: str` — 16 hex chars.
  - `parent_span_id: Optional[str]`.
  - `trace_flags: int` — the W3C flags byte.
  - `baggage: dict[str, str]`.
  - `sampled: bool`.
  - `keep_on_error: bool` — set True on any child error.
- `Span`:
  - `span_id: str`, `parent_span_id: Optional[str]`, `trace_id: str`,
    `name: str`, `start_time_unix_nano: int`,
    `end_time_unix_nano: int`, `status: SpanStatus`,
    `attributes: dict[str, Any]`, `events: list[SpanEvent]`,
    `status_description: Optional[str]`.
- `ExportBatch`:
  - `batch_id: UUID`, `spans: list[Span]`, `built_at: datetime`,
    `exporter_name: str`.

## Interfaces

### Public API

Minimal REST surface (admin-only, used by ops and the admin UI):

- `GET /api/v1/ops/observability/exporter` — return
  `{active_exporter_name, configuration_sha256, configured_at}`.
- `POST /api/v1/ops/observability/exporter` — swap the active
  exporter name (the named exporter must already be registered via
  the factory).
- `GET /api/v1/ops/observability/self` — diagnostic dump:
  queue depth, dropped total, last export failure.

CLI:

- `pychestrate observability show-exporter`
- `pychestrate observability set-exporter <name>`

### Internal API

Module
`ccai.pychestrate.webservice.ops.observability.trace_context`:

```python
@dataclass(frozen=True)
class ObservabilityAspects:
    """
        Caller-supplied behavior knobs — AGENTS.md "Aspects" pattern.

        :param head_sample_rate: Probability a root span is head-sampled.
        :param force_keep_on_error: When True, any error in the trace forces keep.
        :param batch_size: Span export batch size (>= 1).
        :param batch_linger_seconds: Seconds to wait before flushing a partial batch.
        :param debug_self_tracing: Emit observability's own instrumentation spans.
        :param log_verbosity: NORMAL | DEBUG — never emits secrets.
    """
    head_sample_rate: float
    force_keep_on_error: bool
    batch_size: int
    batch_linger_seconds: float
    debug_self_tracing: bool
    log_verbosity: LogVerbosity


def build_default_observability_aspects() -> ObservabilityAspects:
    """
        Construct the default aspects for routine observability.

        Per AGENTS.md we never use mutable defaults; callers call this
        builder explicitly.
    """
    rtnval = ObservabilityAspects(
        head_sample_rate=0.01,
        force_keep_on_error=True,
        batch_size=512,
        batch_linger_seconds=5.0,
        debug_self_tracing=False,
        log_verbosity=LogVerbosity.NORMAL
    )
    return rtnval


def continue_or_start_trace(
        *,
        incoming_traceparent: Optional[str],
        incoming_tracestate: Optional[str],
        route: str
    ) -> TraceContext:
    """
        Parse an incoming `traceparent` and adopt it, or start a fresh trace.

        :raises: SemanticError on malformed headers that passed a validator check.
    """
    ...


def start_child_span(
        *,
        parent: TraceContext,
        name: str,
        attributes: dict[str, Any]
    ) -> Span:
    """
        Produce a new child span inside the given parent context.
    """
    ...


def close_span(
        *,
        span: Span,
        status: SpanStatus,
        status_description: Optional[str]
    ) -> None:
    """
        Close a span, record its duration, and enqueue it for export.
    """
    rtnval = None
    return rtnval


def get_current_trace_context() -> Optional[TraceContext]:
    """
        Return the active `TraceContext` for the current execution, or None.
    """
    ...


def inject_traceparent(
        *,
        headers: dict[str, str]
    ) -> dict[str, str]:
    """
        Add `traceparent` and `tracestate` headers reflecting the current context.
    """
    ...
```

Module
`ccai.pychestrate.webservice.ops.observability.structured_logger`:

```python
def emit(
        *,
        logger: str,
        level: LogLevel,
        event: str,
        message: str,
        attributes: dict[str, Any]
    ) -> None:
    """
        Emit one JSON log record with trace / run / project correlation.

        Note: callers pass a fully-populated `attributes` dict; the
        logger never mutates caller state and never uses a mutable
        default.
    """
    rtnval = None
    return rtnval


def redact_attributes(
        *,
        attributes: dict[str, Any]
    ) -> dict[str, Any]:
    """
        Apply the sensitive-key redactor to a copy of `attributes`.
    """
    ...
```

Module
`ccai.pychestrate.webservice.ops.observability.span_processor`:

```python
def enqueue_span(
        *,
        span: Span,
        aspects: ObservabilityAspects
    ) -> None:
    """
        Enqueue a closed span for batched export; drops oldest on
        queue overflow with the drop counter bumped.
    """
    rtnval = None
    return rtnval


def flush(
        *,
        aspects: ObservabilityAspects
    ) -> FlushResult:
    """
        Force a flush of the current batch; returns per-exporter results.
    """
    ...


def set_active_exporter(
        *,
        exporter_name: str,
        aspects: ObservabilityAspects
    ) -> None:
    """
        Swap the active exporter at the next batch boundary without restart.

        :raises: ConfigurationError if `exporter_name` is not registered.
    """
    rtnval = None
    return rtnval
```

### Extension Surface

Factory protocol `trace_exporter` declared in
`ccai.pychestrate.webservice.ops.observability.factories.trace_exporter`:

```python
class TraceExporterProtocol(FactoryProtocolBase):
    factory_protocol_name: str = "trace_exporter"
    protocol_schema_version: int = 1

    @classmethod
    def exporter_name(cls) -> str:
        """Stable registered name — used in `trace_exporter_state`."""
        ...

    @classmethod
    def capabilities(cls) -> TraceExporterCapabilities:
        """Declared caps: supports_mtls, supports_compression, max_batch_bytes, ..."""
        ...

    @classmethod
    def export_batch(
            cls,
            *,
            batch: ExportBatch,
            aspects: ObservabilityAspects
        ) -> ExportResult:
        """
            Ship a batch of spans; must be synchronous from the exporter's view.
        """
        ...

    @classmethod
    def shutdown(
            cls,
            *,
            aspects: ObservabilityAspects
        ) -> None:
        """Flush and release network/file resources."""
        ...
```

Reference implementations:

- `OtlpGrpcTraceExporter` (`PRECEDENCE = 1000`, default) — W3C-native
  OTLP over gRPC; mTLS when a client cert is configured by
  `secret_ref = system:observability.otlp_client_cert`.
- `JaegerThriftTraceExporter` (`PRECEDENCE = 900`) — skeleton for
  Jaeger v1 protocol.
- `HoneycombHttpTraceExporter` (`PRECEDENCE = 900`) — skeleton against
  the Honeycomb Events API.

### Events Emitted

- `entity.trace.exported` — `{batch_id, exporter_name, span_count,
  duration_seconds, exported_at}`
- `entity.trace.export_failed` — `{batch_id, exporter_name, reason,
  failed_at}`
- `entity.trace.exporter.loaded` —
  `{exporter_name, configuration_sha256, loaded_at}`
- `entity.trace.sampling.kept_on_error` —
  `{trace_id, root_span_name, spans, at}`

### Events Consumed

- `entity.audit.sink.unhealthy` — observed and logged; does *not*
  affect span export (audit and observability are independent).
- `entity.secret.rotated` where `secret_ref` matches the exporter
  credential patterns — the span processor rebuilds the exporter
  client at the next batch boundary.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/ops/observability/
    __init__.py
    boot.py                         # Phase 0 boot wiring
    trace_context.py                # TraceContext, start/close span, traceparent
    traceparent_codec.py            # W3C parse / serialize
    structured_logger.py            # JSON emitter + redactor
    redactor.py                     # sensitive-key redactor rules
    metrics_collector.py            # metric definition + exemplar plumbing
    span_processor.py               # batching, queue, drop accounting
    sampler.py                      # deterministic head sample + keep-on-error
    exporter_registry.py            # resolves via E-extension-host
    factories/
        trace_exporter.py           # FactoryProtocolBase declaration
        otlp_grpc_exporter.py       # OtlpGrpcTraceExporter
        jaeger_thrift_exporter.py   # JaegerThriftTraceExporter (skeleton)
        honeycomb_http_exporter.py  # HoneycombHttpTraceExporter (skeleton)
    models.py
    restapi/
        v1/
            exporter_controller.py
            self_controller.py
    events.py
    exceptions.py
```

## Key Flows

**Request enters, trace continues from upstream:**

1. `0-web-app-host` middleware calls
   `trace_context.continue_or_start_trace(incoming_traceparent=...,
   route=...)` at the start of every request.
2. If the `traceparent` parses cleanly, the request adopts the parent
   `trace_id` and a new `span_id`; otherwise a fresh trace starts.
   `sampler.decide(trace_id, route)` sets `sampled = True|False`
   deterministically; if the route matches `force_keep_route`,
   `sampled` is forced True.
3. The request handler runs under that context; every log call from
   `structured_logger.emit` reads the context from the `ContextVar`
   and stamps `trace_id` / `span_id` on the JSON record.
4. Any feature calling an outbound HTTP client uses
   `trace_context.inject_traceparent` to propagate.
5. When the handler finishes, `trace_context.close_span` stamps
   duration, status, and calls
   `span_processor.enqueue_span`. If the span's status is ERROR,
   `sampler` flips the trace's `keep_on_error=True`.

**Span export (batched):**

1. `span_processor` accumulates spans into an `ExportBatch` until
   `batch_size` is reached or `batch_linger_seconds` elapses.
2. `exporter_registry.resolve_current` returns the registered
   `trace_exporter` (via `E-extension-host`).
3. The processor calls `exporter.export_batch(batch, aspects)` and
   publishes `entity.trace.exported` on success or
   `entity.trace.export_failed` on failure.
4. On failure, the batch is re-queued up to the configured retry
   budget; if the queue is full, the oldest spans are dropped with
   the drop counter bumped and `trace.sample.dropped` logged.

**Bus message handler adopts trace:**

1. `0-message-bus` subscriber wrapper reads
   `event.headers["traceparent"]`, if present.
2. It calls `trace_context.continue_or_start_trace(incoming_traceparent=...,
   route="bus:{topic}")` before invoking the handler.
3. Handler logs and metrics are correlated to the publishing request's
   trace automatically.

**Swap exporter at runtime:**

1. Admin calls `POST /api/v1/ops/observability/exporter` with
   `{exporter_name}`.
2. `span_processor.set_active_exporter(exporter_name, aspects)`
   validates registration, updates `trace_exporter_state`, emits
   `entity.trace.exporter.loaded`, and flips the pointer at the next
   batch boundary — in-flight batches finish on the previous
   exporter, new batches route to the new exporter.

## Error Handling

Failure modes:

- `TraceExporterUnavailableError` — HTTP 503 on the admin endpoint;
  the named exporter is not registered. Request handling continues
  (no blocking).
- `MalformedTraceparentError` — logged at DEBUG with the invalid
  header value elided to length; a fresh trace starts. Requests
  never fail because of a bad upstream traceparent.
- `SpanQueueOverflow` — not an exception; increments
  `pychestrate_trace_dropped_total{reason=queue_overflow}` and logs
  once per minute with the drop count.
- `ExporterExportError` — caught and reclassified with
  `exporter_name` and `batch_id` context; re-queued per retry
  budget; counted in
  `pychestrate_trace_export_failures_total`.
- `ConfigurationError` — raised at startup when no
  `trace_exporter` is registered (including the default OTLP) —
  observability is load-bearing; the service refuses to start.
- `SemanticError` — illegal aspect values (negative sample rate,
  zero batch size); NEVER caught.

Multi-line error messages use the AGENTS.md pattern:

```python
err_msg_lines = ["Trace exporter rejected a batch after retries."]
err_msg_lines.append("EXPORTER: {}".format(exporter_name))
err_msg_lines.append("BATCH_ID: {}".format(batch_id))
err_msg_lines.append("SPAN_COUNT: {}".format(span_count))
err_msg_lines.append("ATTEMPTS: {}".format(attempts))
err_msg_lines.append("LAST_CAUSE: {}".format(last_cause))
err_msg = os.linesep.join(err_msg_lines)
raise ExporterExportError(err_msg) from last_cause
```

The structured logger never emits plaintext secrets; the redactor
scans both well-known keys (`secret.value`, `password`, `token`,
`authorization`, `cookie`, `set-cookie`, `api_key`) and any key
matching the configured regex list. Redacted records include
`redacted=true` in the metric label so redaction rate is observable.

## Security Considerations

- Exporter credentials (gRPC client cert, Honeycomb API key, Jaeger
  token) resolve by `secret_ref` through `1-secrets-vault`. Reading
  env vars directly for credentials is disallowed and checked in
  startup self-test.
- `trace_exporter` extensions declare `net:outbound` and
  `read:secrets` capabilities. Once `E-extension-sandbox` lands
  (Phase 8) the host refuses to load exporters without those caps.
- Span attributes are redacted before export — the same redactor that
  applies to logs applies to span attribute values.
- `1-audit-log` records each `set_active_exporter` change with actor
  and `configuration_sha256`.
- RBAC: `system:observability.read`,
  `system:observability.set_exporter`.
- Rate limiting on admin mutate endpoints (default 10 rpm) to prevent
  a compromised operator from flapping exporters.

## Observability

The feature is its own first consumer — every metric name below is
emitted by this feature for this feature:

Metrics:

- `pychestrate_trace_spans_emitted_total{span_name,status}`
- `pychestrate_trace_exported_total{exporter}`
- `pychestrate_trace_export_failures_total{exporter,reason}`
- `pychestrate_trace_dropped_total{reason}`
- `pychestrate_trace_export_queue_depth{exporter}` (gauge)
- `pychestrate_trace_http_request_duration_seconds{route,method,status}` (histogram)
- `pychestrate_trace_logs_total{level,logger,redacted}`
- `pychestrate_trace_sample_decisions_total{decision,reason}`
- `pychestrate_trace_redactions_total{key}`

Log events: `trace.exporter.loaded`, `trace.exporter.failed`,
`trace.exporter.reloaded`, `trace.sample.kept_on_error`,
`trace.redacted`, `trace.context.invalid_traceparent`,
`trace.queue.overflow`.

Trace spans (emitted by this feature for itself, gated by
`ObservabilityAspects.debug_self_tracing`):
`observability.export.batch`, `observability.log.emit`,
`observability.exporter.swap`.

## Open Questions

- Do we expose an OTLP-over-HTTP exporter alongside gRPC as in-tree
  default? Tentative: yes in Phase 0.5 once enough early-adopter
  sites are using HTTP ingress only.
- Do we ship a log-over-OTLP exporter or keep logs strictly stdout
  JSON? Initial: stdout JSON only; log aggregation stacks already
  solve this; revisit after Phase 10 operator feedback.
- Should the exemplar plumbing be on by default or opt-in? Initial:
  on by default because cardinality is bounded by metric labels.
- Do we need a configurable "keep-one-in-N head-dropped traces"
  knob for cost-sensitive operators? Deferred to Phase 10.1.
