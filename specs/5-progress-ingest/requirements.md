# 5-progress-ingest — Requirements

## Introduction

The `5-progress-ingest` feature is Pychestrate's passive HTTP
receiver for live run progress. It matches the shape of
`automojo-testbase`'s `ProgressConcentratorServer`: the pod client's
test runner opens a `ForwardingInfo` channel to a URL Pychestrate
exposes, then periodically POSTs two flavors of payload — per-record
progress (one task started / finished / partial) and periodic run
summaries (the same summary shape later persisted as
`testrun_summary.json`). Ingest is push-only; Pychestrate never
polls the client. Parsing is extensible via the `progress_parser`
factory protocol keyed by a format tag — testbase default ships
in-tree; other runner formats (gtest-json, JUnit-live, custom
registries) land as extensions. This feature ships in **Phase 3**
and emits `entity.progress.received` that `5-run-state-machine`,
`6-live-run-view`, and `7-test-metrics` all subscribe to.

## Requirements

### Requirement 1: HTTP Endpoints Matching testbase ForwardingInfo

**User Story:** As a pod client running testbase, I want a stable
HTTP endpoint accepting my existing ForwardingInfo POSTs, so that
my runner requires zero code changes to report progress to
Pychestrate.

**Acceptance Criteria (EARS):**

1. WHEN a client POSTs to
   `/ingest/v1/progress/<run_id>/summary` with
   `Content-Type: application/json` AND a body matching the testbase
   summary schema THEN the system SHALL persist a
   `run_progress_summary` row AND publish
   `entity.progress.received` with `{run_id, kind: "summary",
   received_at, latest_offset}`.
2. WHEN a client POSTs to
   `/ingest/v1/progress/<run_id>/records` with
   `Content-Type: application/jsos` AND a newline-delimited JSON
   stream with record separator 0x1E THEN the system SHALL
   incrementally parse every record AND persist each as a
   `run_progress_record` row.
3. IF the authenticated client does not match the `client_id`
   bound to the `DispatchReceipt` for `run_id` THEN the system
   SHALL respond `403 Forbidden` AND emit
   `pychestrate.ingest.progress.auth_rejected`.
4. WHERE a summary payload declares `runid`, `pipeline.id`,
   `pipeline.instance`, `job.id`, `job.name`, `job.type`,
   `BuildInfo.branch`, `BuildInfo.build`, `BuildInfo.flavor`,
   `BuildInfo.release` the system SHALL validate each identifier
   matches the dispatched envelope's corresponding field AND reject
   with `409 Conflict` on any mismatch.
5. WHEN the first progress payload arrives for a run THEN the
   system SHALL emit exactly one `entity.progress.received` with
   `first: true` and subsequent payloads SHALL carry `first: false`.

### Requirement 2: JSOS Record Stream Parsing is Incremental and Ordered

**User Story:** As a live-view UI, I want every record the runner
sent to appear in order and exactly once, so that the run timeline
I render does not skip or reorder task outcomes.

**Acceptance Criteria (EARS):**

1. WHEN a `testrun_results_stream.jsos`-formatted body is POSTed
   THEN the system SHALL split on 0x1E, parse each JSON object,
   and preserve arrival order in the persisted record set via a
   monotonic per-run `seq` column.
2. IF a record fails to parse (invalid JSON, missing required
   `worker`/`instance`/`rtype`/`result` keys) THEN the system
   SHALL skip that record, increment
   `pychestrate_ingest_progress_parse_errors_total{run_id,format}`,
   and log `pychestrate.ingest.progress.parse_skipped` — but the
   remaining records in the batch SHALL still persist.
3. WHILE a record stream is being ingested the system SHALL
   hold a per-run ingest lock so two concurrent POSTs for the
   same `run_id` serialize at the record boundary.
4. WHEN the chosen `progress_parser` returns a
   `ProgressRecord` marking a task terminal THEN the system
   SHALL update the run's aggregated per-task counters (pass /
   fail / error / skipped) atomically with the record insert.

### Requirement 3: Parser Selection via `progress_parser` Factory

**User Story:** As an extension author for a custom test runner, I
want to register my own progress parser keyed by a format tag, so
that my runner's payload is understood without patching the service.

**Acceptance Criteria (EARS):**

1. WHEN a POST includes header `X-Pychestrate-Progress-Format`
   THEN the system SHALL select the `ProgressParserProtocol`
   implementation whose `format_tag()` returns that value — lowest
   `PRECEDENCE` wins on ties.
2. IF no parser matches the format tag THEN the system SHALL
   return `415 Unsupported Media Type` with a body listing every
   registered `format_tag` AND emit
   `pychestrate.ingest.progress.unknown_format`.
3. WHERE the header is absent the system SHALL default to the
   testbase parser (format tag `"testbase-v1"`).
4. WHEN a parser raises `ProgressParseError` the system SHALL log,
   increment the parse-error counter, and respond `422 Unprocessable
   Entity` with an error id the client can include in a bug report.

## Property-Based Test Requirements

### Property 1: JSOS Stream Preserves Record Count and Order

- **Invariant:** For any JSOS stream with `M` well-formed records,
  incremental parsing yields exactly `M` `ProgressRecord`
  instances with the same ordering as the input. Chunk boundary
  inside a record does not duplicate, drop, or reorder records.
- **Generator:** `hypothesis.strategies.lists(testbase_record(),
  min_size=0, max_size=1000)` producing well-formed records;
  serialize with 0x1E separator, then slice the resulting bytes
  into `k` random chunks (`k ∈ [1, 64]`) with boundaries at
  arbitrary offsets (including inside records). Feed chunks
  sequentially to the incremental parser.
- **Assertion:** output record list equals the input list; `seq`
  column is strictly increasing; no record appears twice.
- **Sample size:** 1000 generated cases

### Property 2: Summary Identifiers Equal Envelope Identifiers After Ingest

- **Invariant:** For any dispatched envelope `e` and any summary
  payload whose headers match, the persisted `run_progress_summary`
  row's `(runid, pipeline_id, pipeline_instance, job_id, job_name,
  job_type, build_branch, build_build, build_flavor, build_release)`
  tuple equals the tuple derived from the envelope.
- **Generator:** Build valid envelopes with arbitrary identifier
  combinations; derive a matching summary via
  `testbase_summary_from_envelope(e)`; ingest; read back.
- **Assertion:** tuples are equal across all generated envelopes.
  Any perturbation to a single identifier in the summary → ingest
  rejects with `409`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Records endpoint SHALL sustain ≥ 5000
  records/sec/process at p99 end-to-end latency < 150 ms for
  batches ≤ 500 records. Summary endpoint p99 < 80 ms.
  Per-run ingest lock hold time p99 < 40 ms. Memory per active
  stream ≤ 1 MiB (bounded buffer).
- **NFR-2 (Security):** Endpoints require an authenticated
  `3-client-agent-protocol` bearer token bound to a specific
  `client_id`; requests whose bearer does not map to the run's
  receipt are rejected `403`. Bodies capped at
  `max_records_bytes_per_request` (default 4 MiB) and
  `max_summary_bytes` (default 256 KiB). Payloads MUST be
  validated against the parser's schema — no raw dict persistence.
  Rate limit per `client_id`: 100 requests/sec burst, 20
  sustained; over-limit responds `429`.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_ingest_progress_requests_total{endpoint,format,result}`
  (counter),
  `pychestrate_ingest_progress_records_total{run_id,parser}`
  (counter — label-bounded to project),
  `pychestrate_ingest_progress_bytes_total{endpoint,format}`
  (counter),
  `pychestrate_ingest_progress_latency_seconds{endpoint,format}`
  (histogram),
  `pychestrate_ingest_progress_parse_errors_total{run_id,format}`
  (counter), `pychestrate_ingest_progress_active_streams` (gauge).
  Log events `pychestrate.ingest.progress.summary.received`,
  `pychestrate.ingest.progress.records.received`,
  `pychestrate.ingest.progress.parse_skipped`,
  `pychestrate.ingest.progress.identifier_mismatch`. Trace span
  `pychestrate.ingest.progress.post` with `endpoint`, `format`,
  `run_id`.
- **NFR-4 (Reliability):** Parse failures in one record MUST NOT
  drop surrounding records. A parser exception MUST NOT crash the
  worker — `ProgressParseError` bubbles to the request handler and
  returns `422`. Ingest acknowledgement is durable only after
  `entity.progress.received` is written to the outbox (see
  `5-run-state-machine`).

## Out of Scope

- Long-horizon archival of every record (retention is governed by
  `2-retention-policies`).
- Result-tree parsing — owned by `5-result-ingest-watcher`.
- UI rendering of progress — owned by `6-live-run-view` and the
  `9-wc-log-stream` WebComponent.
- Outbound push of progress to other systems — owned by
  `8-webhooks-out`.

## Dependencies

- **Depends on:** `0-web-app-host`, `0-persistence`, `0-message-bus`,
  `3-client-agent-protocol` (auth), `5-dispatch-receipt` (client
  authorization binding), `5-job-envelope` (identifier validation),
  `5-run-state-machine` (transition consumer), `E-extension-host`,
  `E-factory-protocols`.
- **Depended on by:** `5-run-state-machine` (first-progress → running,
  stall detection), `6-live-run-view`, `7-test-metrics`,
  `7-orchestration-metrics`, `9-wc-log-stream`.
- **Extension points exposed:** `factory: progress_parser` — see
  implementation-plan.md Layer 5 section.
