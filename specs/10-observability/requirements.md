# 10-observability — Requirements

## Introduction

`10-observability` is Pychestrate's self-monitoring surface: distributed
traces, structured logs, and exported metrics describing Pychestrate's
own behavior (not the jobs or runs it orchestrates — those have their
own metric paths in Layer 7). It establishes a single context object
that flows through every request and every internal work unit, ensures
that every log record and every metric sample can be correlated back to
the trace that produced it via `trace_id`, and exports traces out of
the process through a pluggable `trace_exporter` factory (OTLP by
default; Jaeger, Honeycomb, and custom sinks available as overrides).
The feature lands in **Phase 0 — Platform Readiness** (foundational):
without it the rest of the stack cannot produce correlated
observability from day one, which forces retro-fit later and leaves
gaps in every downstream feature's NFR-3. It lives under Layer 10 —
Operations in the catalog, but is wired at the web-app-host boot path so
every feature emits through it. Behavior is controlled through an
`ObservabilityAspects` object per AGENTS.md — no decorators modify
behavior. Structured logs are JSON and carry `trace_id`, `span_id`,
`run_id`, `project_id`, `request_id`, and `service_version` on every
record.

## Requirements

### Requirement 1: W3C Traceparent Propagation and Trace Context

**User Story:** As a site reliability engineer, I want every request
entering Pychestrate to either continue an upstream trace or start a
new one, and every internal work unit to run inside that trace, so
that a single distributed trace covers a request from edge to exit.

**Acceptance Criteria (EARS):**

1. WHEN an HTTP request arrives at a Pychestrate endpoint THEN the
   system SHALL inspect the `traceparent` header per W3C Trace
   Context; IF present and valid THEN the system SHALL continue that
   trace by adopting its `trace_id` and creating a new child span;
   IF absent or malformed THEN the system SHALL start a fresh trace
   with a newly-generated `trace_id` and the request span as root.
2. WHEN Pychestrate initiates an outbound HTTP call (for example,
   notifying `2-notification-hub` sinks, fetching from a remote object
   store, or talking to an enrolled client) THEN the system SHALL
   inject `traceparent` and `tracestate` headers reflecting the
   current span.
3. WHEN a message is published on `0-message-bus` THEN the system
   SHALL attach the current `trace_id` and `span_id` to the event
   headers, and subscribers SHALL adopt that trace for spans covering
   their handler.
4. WHILE a unit of work executes inside a span the system SHALL
   expose `get_current_trace_context()` returning
   `(trace_id, span_id, baggage)` so feature code can stamp log
   records and metric exemplars without explicit parameter plumbing.
5. WHERE a span is closed THEN the system SHALL record
   `start_time_unix_nano`, `end_time_unix_nano`, `status`,
   `attributes`, and enqueue it for export through the configured
   `trace_exporter`.

### Requirement 2: Structured JSON Logging Correlated by Trace Id + Run Id + Project Id

**User Story:** As an on-call engineer, I want every log line to be
parseable JSON and carry the identifiers I need to stitch logs, runs,
and traces together, so that a single `trace_id` or `run_id` query
yields every record relevant to an incident.

**Acceptance Criteria (EARS):**

1. WHEN any feature calls the shared logger THEN the system SHALL
   emit one JSON record per line with at minimum these fields:
   `timestamp` (RFC 3339 with microsecond precision),
   `level`, `logger`, `message`, `service_version`, `service_name`,
   `trace_id`, `span_id`, `run_id`, `project_id`, `request_id`,
   `event`, and any caller-supplied key/value attributes. Absent
   ids SHALL appear as `null`, never be omitted.
2. IF a log call occurs outside any active trace context THEN the
   system SHALL still emit the record with `trace_id = null` and
   `span_id = null` (no silent drops, no fabricated ids).
3. WHEN a log record carries a `secret.value` key or a key matching
   a configured sensitive-key pattern THEN the system SHALL replace
   the value with the literal string `"<redacted>"` before writing
   the record.
4. WHILE the process runs the system SHALL expose a
   `pychestrate_trace_logs_total{level,logger,redacted}` counter
   reflecting emitted records (not sampled).
5. WHERE a log record's level is `ERROR` or higher AND a trace is
   active THEN the system SHALL mark the active span as
   `status=ERROR` and attach the error's exception type and
   redacted message as span attributes.

### Requirement 3: Self-Monitoring Metrics With Trace Exemplars

**User Story:** As an SRE, I want Pychestrate to export metrics about
its own HTTP request latency, bus delivery, object-store calls, and
task queues, with exemplars pointing to real traces, so that I can
click from a latency spike to the trace that caused it.

**Acceptance Criteria (EARS):**

1. WHEN an HTTP request completes THEN the system SHALL observe
   `pychestrate_trace_http_request_duration_seconds{route,method,status}`
   (histogram) and attach a trace exemplar carrying the completing
   span's `trace_id`.
2. WHEN an internal work unit emits a span THEN the system SHALL
   increment
   `pychestrate_trace_spans_emitted_total{span_name,status}` and, if
   the span is exported, `pychestrate_trace_exported_total{exporter}`;
   IF the export fails THEN the system SHALL increment
   `pychestrate_trace_export_failures_total{exporter,reason}` and
   SHALL NOT drop the span silently — it SHALL remain in the local
   export queue until the queue depth exceeds the configured limit,
   after which the oldest dropped span increments
   `pychestrate_trace_dropped_total{reason=queue_overflow}`.
3. WHILE the configured `trace_exporter` is the default OTLP export
   THEN the system SHALL use the gRPC OTLP protocol with mTLS when a
   client cert is configured in `1-secrets-vault`, and SHALL send in
   configurable batch sizes (default 512 spans, 5-second linger).
4. WHEN a `trace_exporter` extension is registered via the factory
   THEN the system SHALL route exports through that exporter on the
   next batch boundary without restarting the process.

### Requirement 4: Sampling With Full Sampling on Errors

**User Story:** As an operator paying for an external tracing SaaS,
I want most traces sampled at 1% but every error path captured in
full, so that I keep cost bounded without losing root-cause data.

**Acceptance Criteria (EARS):**

1. WHEN a root span starts THEN the system SHALL apply the configured
   `head_sample_rate` (default 0.01 = 1%) deterministically from the
   `trace_id` so sampling is consistent across services.
2. IF at any point during the trace a span records
   `status = ERROR` OR attaches an exception THEN the system SHALL
   upgrade the entire trace to "keep" regardless of the initial head
   sampling decision (tail-based keep-on-error).
3. WHILE a trace is marked "keep" the system SHALL ensure all spans
   in the trace are exported, including those recorded before the
   upgrade.
4. WHERE the operator configures `force_keep_route = <route_glob>`
   THEN every request matching that glob SHALL be sampled at 100%
   irrespective of the head rate.

## Property-Based Test Requirements

### Property 1: Child Span Durations Do Not Exceed Parent

- **Invariant:** For any trace emitted by Pychestrate, the sum of any
  child span's duration is less than or equal to its parent span's
  duration, and each child span is fully contained (start and end
  times) within its parent span's time window.
- **Generator:** hypothesis strategy producing random trees of up to
  200 nested work units with random durations, random (but legal)
  start-time offsets from parents, and random error injection.
- **Assertion:** for every generated trace, every child span
  `(start, end)` satisfies `parent.start <= child.start <= child.end
  <= parent.end`, and `sum(child.duration) <= parent.duration`.
- **Sample size:** 1000 generated cases.

### Property 2: Log ↔ Trace ↔ Metric Correlation Is Lossless

- **Invariant:** For any log record emitted while a trace is active,
  the record's `trace_id` equals the active trace's id, and for every
  metric sample observed during the same span, the sample's exemplar
  (when present) carries the same `trace_id` and a `span_id` that is
  an ancestor of or equal to the active span.
- **Generator:** hypothesis strategy producing random trees of work
  units that interleave log emissions and metric observations at
  random depths.
- **Assertion:** for every (log record, concurrent metric sample)
  pair, the `trace_id` values match exactly; orphan logs (no active
  trace) have `trace_id = null` and no metric sample in the same
  window carries a contradicting exemplar.
- **Sample size:** 1000 generated cases.

### Property 3: Error Trace Keep Is Monotonic and Complete

- **Invariant:** For any trace where at least one span transitions to
  `status = ERROR`, the complete span set of the trace is exported
  regardless of the head sampling decision — no partial trace ever
  reaches the exporter when any span is in error.
- **Generator:** hypothesis strategy producing random traces with
  varying head sample decisions and random error injection at random
  depths.
- **Assertion:** for every generated trace, either the exported span
  set is empty (no error, not head-sampled) or it contains exactly
  every span recorded during the trace; a trace with any error never
  produces a partial export.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):**
  - **Head sample rate default:** 1% (deterministic by `trace_id`).
  - **Full sampling on error:** 100% (tail keep-on-error).
  - **Span export batch size default:** 512 spans.
  - **Span export linger default:** 5 seconds.
  - **Per-request instrumentation overhead:** p99 <= 1.5 ms on the
    request path.
  - **Log emission overhead:** p99 <= 200 μs per record for a JSON
    record up to 4 KB.
- **NFR-2 (Security):** The exporter never sends log records on the
  span export channel; span `attributes` values are scanned against
  the sensitive-key redactor before export. Exporter credentials live
  in `1-secrets-vault` — the configured `trace_exporter` resolves
  them by `secret_ref`, never reads environment variables directly.
  Every `trace_exporter` load is audited. No PII / secrets are
  permitted in span `name` or `attributes` — an assertion runs in
  the debug build that panics if a redactable key slips through.
- **NFR-3 (Observability — self):**
  `pychestrate_trace_spans_emitted_total{span_name,status}`,
  `pychestrate_trace_exported_total{exporter}`,
  `pychestrate_trace_export_failures_total{exporter,reason}`,
  `pychestrate_trace_dropped_total{reason}`,
  `pychestrate_trace_export_queue_depth{exporter}` (gauge),
  `pychestrate_trace_http_request_duration_seconds{route,method,status}` (histogram),
  `pychestrate_trace_logs_total{level,logger,redacted}`,
  `pychestrate_trace_sample_decisions_total{decision,reason}`.
  Log events: `trace.exporter.loaded`, `trace.exporter.failed`,
  `trace.sample.kept_on_error`, `trace.redacted`,
  `trace.context.invalid_traceparent`.
  Trace spans: `observability.export.batch`,
  `observability.log.emit` (instrumentation self-span, disabled by
  default, enabled via `ObservabilityAspects.debug_self_tracing`).
- **NFR-4 (Reliability):** A failing `trace_exporter` SHALL NOT block
  request handling or bus delivery; exports are async via a bounded
  queue. When the queue is full the oldest spans are dropped with the
  counter above; the service never exhausts memory due to export
  backlog. Exporter reload on factory change SHALL NOT lose already-
  enqueued spans.

## Out of Scope

- Orchestration-domain metrics (runs, tests, builds, resources) —
  owned by Layer 7 features.
- Log retention / archival — owned by downstream log aggregation
  stacks (this feature emits; another system retains).
- User-facing log-stream WebComponent — `9-wc-log-stream`.
- Timeseries backend for service metrics — `0-timeseries-backend`
  (this feature emits; that feature stores).

## Dependencies

- **Depends on:** `0-web-app-host`, `0-message-bus`,
  `0-persistence`, `1-secrets-vault` (exporter credentials),
  `1-audit-log`, `E-extension-host`, `E-factory-protocols`.
- **Depended on by:** every other feature (every feature's NFR-3 is
  fulfilled through this one). In particular `10-backup-dr` and
  `10-release-channels` consume the trace context and structured
  logger declared here.
- **Extension points exposed:** `factory: trace_exporter` — OTLP
  (default in-tree), Jaeger (in-tree skeleton), Honeycomb (in-tree
  skeleton), custom. Reference implementation `OtlpGrpcTraceExporter`
  ships at `PRECEDENCE = 1000`. See implementation-plan.md Layer 10
  and Phase 0.
