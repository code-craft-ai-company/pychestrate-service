# 5-progress-ingest — Tasks

## Milestones

- **M1 — Skeleton:** Two HTTP routes, auth binding,
  `TestBaseProgressParser` in-tree, `run_progress_summary` and
  `run_progress_record` tables, outbox publish of
  `entity.progress.received`.
- **M2 — Core Behavior:** JSOS chunk-boundary aware splitter,
  `progress_parser` factory registry, parser selection via header,
  counters repository, identifier validation against envelope,
  rate-limit middleware.
- **M3 — Hardening:** Property tests, perf validation against
  NFR-1, dashboards, alerts, parse-error budget, docs for runner
  authors.

## Tasks

### M1 — Skeleton

- [x] T1.1 — Create `ingest/progress/` package skeleton per design.md Component Breakdown.
- [~] T1.2 — Register routes `POST /ingest/v1/progress/<run_id>/summary` and `.../records` in `ingest/progress/routes.py`.
      *(M1 ships the service-layer entry points
      (``ingest_summary``, ``ingest_record``); the Flask routes
      land when the v1 ingest namespace is published — same
      deferral as the existing ``8-rest-api-v1`` controllers
      shipped under ``restapi/versions/v1/`` for other features.)*
- [~] T1.3 — Implement `ingest/progress/auth.py` — verify authenticated `client_id` matches the run's `DispatchReceipt.client_id`.
      *(Check is inlined in
      ``service._assert_run_belongs_to_client`` consuming the
      ``DispatchReceipt`` shipped by ``5-dispatch-receipt`` M1.
      Will move to a dedicated ``auth.py`` when the route layer
      lands.)*
- [x] T1.4 — Add Postgres migrations for `run_progress_summary`, `run_progress_record`, `run_progress_counters`.
      *(Migration ``019_phase3_results_ingest`` creates the three
      tables with the unique constraint on
      ``(run_id, record_index)``.)*
- [x] T1.5 — Implement `ingest/progress/repositories.py` — summary, record, counter CRUD.
- [~] T1.6 — Implement `ingest/progress/schema.py` Pydantic value types with `additionalProperties: false`.
      *(Frozen ``dataclass`` shapes instead of Pydantic — same
      decision as ``5-job-envelope`` M1 to avoid the new runtime
      dep. Wire-level strict validation attaches when the route
      layer lands.)*
- [~] T1.7 — Implement `TestBaseProgressParser` at `source/site/ccai/factories/pychestrate/progress_parser/testbase_v1.py` with `PRECEDENCE = 1000`.
      *(Located in-package at
      ``ingest/progress/factories/testbase_v1.py``;
      ``PRECEDENCE=1000`` preserved. Registered via
      ``ingest.progress.register_builtin_extensions`` and called
      from ``phase5_bootstrap``.)*
- [x] T1.8 — Implement `ingest/progress/service.py::ProgressIngestService.ingest_summary` happy path; emit `entity.progress.received` via outbox.
      *(Service exposes ``ingest_summary``, ``ingest_record``,
      ``get_summary``, ``list_records``. Emits
      ``entity.progress.received`` and
      ``entity.progress.summary_landed`` per commit.)*

### M2 — Core Behavior

- [ ] T2.1 — Implement `ingest/progress/jsos.py` 0x1E splitter with chunk-boundary buffering (in-memory for M2).
- [ ] T2.2 — Implement `ingest/progress/parser_registry.py::ProgressParserRegistry` keyed by `format_tag` via `E-extension-host`.
- [ ] T2.3 — Declare `ProgressParserProtocol` factory protocol at `ingest/progress/protocol.py`.
- [ ] T2.4 — Implement `ingest_records` including per-run `_stream_locks`, batch INSERT, counter update in a single transaction.
- [ ] T2.5 — Implement identifier validation: compare summary `runid / pipeline / job / BuildInfo.*` against envelope; 409 on mismatch.
- [ ] T2.6 — Implement rate-limit middleware (token-bucket per `client_id`, 100 burst / 20 sustained).
- [ ] T2.7 — Implement body-size caps: `max_records_bytes_per_request = 4 MiB`, `max_summary_bytes = 256 KiB`; reject with 413.
- [ ] T2.8 — Implement `first` flag: emit `entity.progress.received` with `first=true` only on the run's first successful ingest.

### M3 — Hardening

- [ ] T3.1 — Emit Prometheus metrics and OTel trace span per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: ≥ 5000 records/sec/process, records endpoint p99 < 150 ms at 500-record batches, summary endpoint p99 < 80 ms.
- [ ] T3.3 — Add 503 + `Retry-After` back-pressure path when `_active_stream_count` exceeds configured limit.
- [ ] T3.4 — Add parse-error-ratio alert: > 2% for 5 min → `7-alerts-budgets`.
- [ ] T3.5 — Document runner author guide `usersguide/ingest/progress/testbase_forwarding.rst` with sample `ForwardingInfo` config.
- [ ] T3.6 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.7 — Add gauge `pychestrate_ingest_progress_active_streams` emission from `_stream_locks` lifetime.
- [ ] T3.8 — Negative test harness: every testbase schema field is covered by an identifier-mismatch case.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (JSOS count+order under arbitrary chunking) and Property 2 (summary-envelope identifier equality), 1000 cases each.
- [ ] TT-3 — Integration test: testbase pod client (mock) forwards a summary + 200 records; assert counters, `entity.progress.received` events (first + subsequent), and `5-run-state-machine` transition to `running`.
- [ ] TT-4 — Extension-point test: register a test-only `GTestJsonProgressParser` (`format_tag = "gtest-json-v1"`, `PRECEDENCE = 500`); ingest a gtest-json body with the header; assert parser selected and records persisted.
- [ ] TT-5 — Auth test: ingest with a bearer for a different client; assert 403 + `auth_rejected` event.
- [ ] TT-6 — Identifier-mismatch test: post a summary with `BuildInfo.build` differing from the envelope; assert 409 + `identifier_mismatch` event.

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
