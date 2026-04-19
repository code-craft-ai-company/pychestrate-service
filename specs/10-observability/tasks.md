# 10-observability — Tasks

## Milestones

- **M1 — Skeleton (Phase 0 land):** `ObservabilityAspects`,
  `TraceContextManager` with W3C traceparent parse/emit, `StructuredLogger`
  emitting JSON with trace / run / project correlation,
  `trace_exporter` factory protocol, default `OtlpGrpcTraceExporter`,
  bounded span-export queue, boot wiring so every request is traced.
- **M2 — Core Behavior:** Deterministic head sampling, tail
  keep-on-error, bus-handler trace adoption, outbound traceparent
  injection, self-metrics with trace exemplars, Jaeger + Honeycomb
  exporter skeletons, runtime exporter swap surface.
- **M3 — Hardening:** Redactor rules + metric, batch-boundary exporter
  reload without span loss, exporter-credential rotation via
  `1-secrets-vault`, Sphinx docs, out-of-tree exporter extension.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Land `trace_exporter_state` + `trace_exporter_events`
      tables via an `EntityMigrationExtension` pack.
- [ ] T1.2 — Implement `ObservabilityAspects` dataclass and
      `build_default_observability_aspects()` (no mutable defaults).
- [ ] T1.3 — Implement `traceparent_codec.parse` and `serialize` per
      W3C Trace Context spec.
- [ ] T1.4 — Implement `trace_context.continue_or_start_trace`,
      `start_child_span`, `close_span`,
      `get_current_trace_context`, and `inject_traceparent` — store
      the context in a `ContextVar`.
- [ ] T1.5 — Implement `structured_logger.emit` — produce one-line
      JSON records with `trace_id`, `span_id`, `run_id`, `project_id`,
      `request_id`, `service_version`, `service_name`, `event`,
      `level`, `timestamp`, `message`, and caller attributes. Absent
      ids appear as `null`, never omitted.
- [ ] T1.6 — Declare `TraceExporterProtocol` `FactoryProtocolBase`
      with `protocol_schema_version = 1`.
- [ ] T1.7 — Ship `OtlpGrpcTraceExporter` at `PRECEDENCE = 1000` as
      the default; resolve client-cert `secret_ref` from
      `1-secrets-vault`.
- [ ] T1.8 — Implement `span_processor.enqueue_span` and batch/flush
      loop with `batch_size=512`, `batch_linger_seconds=5.0`; bounded
      queue with drop accounting.
- [ ] T1.9 — Wire `boot.py` so the Phase 0 startup sequence
      instantiates the trace context, structured logger, span
      processor, and default exporter before any feature runs.
- [ ] T1.10 — Wire request middleware in `0-web-app-host` to call
      `continue_or_start_trace` and close the root span on response
      completion.

### M2 — Core Behavior

- [ ] T2.1 — Implement `sampler.decide_head` with deterministic
      `head_sample_rate=0.01` based on `trace_id` and
      `force_keep_route` glob override.
- [ ] T2.2 — Implement tail keep-on-error: any ERROR status in a
      trace flips `keep_on_error=True` and forces full export of all
      its spans, including already-enqueued pre-error spans.
- [ ] T2.3 — Wire `0-message-bus` subscriber wrapper to adopt
      `event.headers["traceparent"]` and produce handler spans under
      that trace.
- [ ] T2.4 — Wire outbound HTTP clients used across the service to
      call `trace_context.inject_traceparent` before dispatching.
- [ ] T2.5 — Register the `pychestrate_trace_*` metrics via
      `metrics_collector`; attach trace exemplars to the
      `pychestrate_trace_http_request_duration_seconds` histogram.
- [ ] T2.6 — Ship `JaegerThriftTraceExporter` skeleton at
      `PRECEDENCE = 900`.
- [ ] T2.7 — Ship `HoneycombHttpTraceExporter` skeleton at
      `PRECEDENCE = 900`.
- [ ] T2.8 — Implement `span_processor.set_active_exporter` + the
      REST admin endpoints + CLI (`pychestrate observability
      show-exporter|set-exporter`).
- [ ] T2.9 — Implement ERROR-level log auto-mark: an ERROR log while
      a trace is active marks the active span `status=ERROR` and
      attaches the redacted exception info to the span.

### M3 — Hardening

- [ ] T3.1 — Implement `redactor.scrub_attributes` with built-in
      sensitive keys (`secret.value`, `password`, `token`,
      `authorization`, `cookie`, `set-cookie`, `api_key`) and a
      configurable regex list; apply to logs AND to span attributes
      before export.
- [ ] T3.2 — Emit `pychestrate_trace_redactions_total{key}` each
      time the redactor fires.
- [ ] T3.3 — Implement batch-boundary exporter reload: in-flight
      batch finishes on the old exporter, new batches route to the
      new exporter; no span loss.
- [ ] T3.4 — Subscribe to `entity.secret.rotated` for exporter
      credential `secret_ref`s; rebuild the exporter client at the
      next batch boundary; emit `entity.trace.exporter.reloaded`.
- [ ] T3.5 — Add multi-line error messages built via
      `os.linesep.join(...)` per design.md Error Handling.
- [ ] T3.6 — Add a startup self-test that fails closed if no
      `trace_exporter` is registered (including the default OTLP).
- [ ] T3.7 — Generate Sphinx docs for public and internal APIs and
      the `trace_exporter` contract.
- [ ] T3.8 — Ship an out-of-tree
      `pychestrate-ext-trace-exporter-stdout` example exporter at
      `PRECEDENCE = 500` that serializes spans to stdout NDJSON for
      local debugging; the integration suite loads it and exercises
      the swap path.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS acceptance criterion in
      Requirements 1–4 (traceparent continue/start, JSON log fields
      and null-not-omitted rule, sensitive-key redaction, exemplars,
      head sampling + tail keep-on-error, exporter swap).
- [ ] TT-2 — Hypothesis property tests: Property 1 (child span
      durations within parent), Property 2 (log ↔ trace ↔ metric
      correlation is lossless), Property 3 (error-trace keep is
      monotonic and complete — no partial error traces ever reach
      the exporter), 1000 cases each.
- [ ] TT-3 — Integration test: fire 10 000 synthetic requests at 1%
      head sample with seeded error injection on 2% of requests;
      verify the exported span set includes every span of every error
      trace plus ~1% of non-error traces (within statistical
      tolerance), and that `pychestrate_trace_dropped_total{reason}`
      stays zero for the run.
- [ ] TT-4 — Extension-point test: out-of-tree
      `pychestrate-ext-trace-exporter-stdout` at `PRECEDENCE = 500`
      registers, becomes active via `set_active_exporter`, and
      receives the next batch; in-flight batch finishes on the
      previous exporter — assert zero span loss on the boundary.
- [ ] TT-5 — Bus propagation test: an HTTP request publishes an
      event that triggers a handler in another subscriber; assert the
      handler's spans share the request's `trace_id` and that the
      handler's log records carry the same `trace_id`.
- [ ] TT-6 — Redactor test: publish a log record with `password`,
      `secret.value`, a configured regex-matched key, and an unknown
      non-sensitive key; assert only the sensitive values become
      `"<redacted>"`, the unknown key is preserved verbatim,
      `redacted=true` appears on the emitted metric, and span
      attributes for the same keys are also redacted before export.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface has at least one in-tree reference
      implementation (`OtlpGrpcTraceExporter`) and one test-only
      override using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Default head sample rate 1% and tail keep-on-error 100% hold
      in the end-to-end test
- [ ] Feature is live in Phase 0 so every downstream feature can
      rely on the trace context + structured logger from day one
- [ ] Sphinx docs generated for public and internal APIs and the
      `trace_exporter` contract
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators, Aspects-style behavior
      parameters — no `@retry`)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 0 —
      Platform Readiness in specs/implementation-plan.md
