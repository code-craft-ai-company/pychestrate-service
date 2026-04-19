# 5-progress-ingest — Design

## Architecture

Progress ingest is a WebWorks-routed HTTP receiver under
`source/site/automojo/pychestrate/webservice/ingest/progress/`. Two
routes fan into a single `ProgressIngestService` that performs auth,
run/envelope identifier validation, parser selection (via
`E-extension-host`), persistence, aggregate-counter update, and
outbox emission for `entity.progress.received`. The service is
deliberately passive — there is no pull path. It mirrors testbase's
`ProgressConcentratorServer` shape so clients already built on
testbase can point their `ForwardingInfo` at Pychestrate with no
code changes. Authoritative source of truth for the record timeline
is the `run_progress_record` table's `(run_id, seq)` index; the
periodic summary is a *materialized* view the client computes and
posts, stored separately in `run_progress_summary`. This feature
lands in **Phase 3** and is the bus source behind `6-live-run-view`
and the first progress transitions in `5-run-state-machine`.

## Data Model

Owned rows:

- `run_progress_summary`:
  - `summary_id: UUID` (PK, UUIDv7)
  - `run_id: UUID` (FK, indexed)
  - `received_at: timestamptz`
  - `latest_offset: int` (record offset the summary reflects)
  - `runid: str` (testbase-reported)
  - `pipeline_id: str | None`
  - `pipeline_instance: str | None`
  - `job_id: str`
  - `job_name: str`
  - `job_type: str`
  - `build_branch: str | None`
  - `build_build: str | None`
  - `build_flavor: str | None`
  - `build_release: str | None`
  - `counters_pass: int`
  - `counters_fail: int`
  - `counters_error: int`
  - `counters_skipped: int`
  - `raw_summary: jsonb` (parser-normalized snapshot)
- `run_progress_record`:
  - `record_id: UUID` (PK, UUIDv7)
  - `run_id: UUID` (FK, indexed)
  - `seq: bigint`
  - `received_at: timestamptz`
  - `worker: str`
  - `instance: str`
  - `parent: str | None`
  - `rtype: str` (`test`, `task`, `asset`, `phase`, …)
  - `result: str` (`pass`, `fail`, `error`, `skipped`, `running`,
    `start`)
  - `format_tag: str`
  - `raw_record: jsonb`
  - Unique constraint: `(run_id, seq)`.
  - Indices: `(run_id, received_at)`, `(run_id, worker)`.
- `run_progress_counters`:
  - `run_id: UUID` (PK)
  - `pass_count: int`
  - `fail_count: int`
  - `error_count: int`
  - `skipped_count: int`
  - `running_count: int`
  - `last_updated_at: timestamptz`

In-memory state:

- `_stream_locks: dict[UUID, asyncio.Lock]` — per-run ingest lock.
- `_active_stream_count: int` — for gauge.
- `_parser_registry: ProgressParserRegistry` — resolved via
  `E-extension-host`.

Value types:

- `ProgressRecord`:
  - `worker: str`
  - `instance: str`
  - `parent: str | None`
  - `rtype: str`
  - `result: str`
  - `payload: dict[str, Any]` (parser-normalized, schema-validated)
- `ProgressSummary`:
  - `latest_offset: int`
  - `runid: str`
  - `pipeline_id: str | None`
  - `pipeline_instance: str | None`
  - `job_id: str`
  - `job_name: str`
  - `job_type: str`
  - `build_info: BuildInfo`
  - `counters: ProgressCounters`
  - `raw: dict[str, Any]`

## Interfaces

### Public API

Two routes served by `0-web-app-host`:

- `POST /ingest/v1/progress/<run_id>/summary`
  - Request: `Content-Type: application/json`; body matches
    testbase summary schema OR custom format selected by
    `X-Pychestrate-Progress-Format`.
  - Response: `202 Accepted` on success with
    `{summary_id, latest_offset, server_received_at}`; `403` /
    `409` / `415` / `422` / `429` per requirements.
- `POST /ingest/v1/progress/<run_id>/records`
  - Request: `Content-Type: application/jsos`; body newline-delimited
    JSON with 0x1E record separator.
  - Response: `202 Accepted` with `{accepted_count,
    skipped_parse_errors, next_seq}`.

### Internal API

```python
class ProgressIngestService:
    def __init__(
        self,
        summary_repository: ProgressSummaryRepository,
        record_repository: ProgressRecordRepository,
        counter_repository: ProgressCounterRepository,
        parser_registry: ProgressParserRegistry,
        envelope_reader: EnvelopeReader,
        receipt_lookup: DispatchReceiptService,
        bus: MessageBus,
        config: ProgressIngestConfig
    ) -> None:
        self._summary_repository = summary_repository
        self._record_repository = record_repository
        self._counter_repository = counter_repository
        self._parser_registry = parser_registry
        self._envelope_reader = envelope_reader
        self._receipt_lookup = receipt_lookup
        self._bus = bus
        self._config = config
        self._stream_locks: dict[UUID, asyncio.Lock] = {}
        return

    def ingest_summary(
        self,
        run_id: UUID,
        authenticated_client_id: UUID,
        format_tag: str,
        body_bytes: bytes
    ) -> SummaryIngestResult:
        """
            Validate auth + identifiers, parse, persist, emit
            entity.progress.received.

            :param run_id: Service run id.
            :param authenticated_client_id: Client id from the
                                            authenticated request.
            :param format_tag: Format tag from header or default.
            :param body_bytes: Request body.

            :returns: SummaryIngestResult.
            :raises: ProgressAuthError, ProgressIdentifierMismatchError,
                     ProgressParseError, UnsupportedFormatError
        """
        ...

    def ingest_records(
        self,
        run_id: UUID,
        authenticated_client_id: UUID,
        format_tag: str,
        body_bytes: bytes
    ) -> RecordIngestResult:
        """
            Parse JSOS stream, persist, update counters, emit
            entity.progress.received.

            :param run_id: Service run id.
            :param authenticated_client_id: Client id.
            :param format_tag: Format tag.
            :param body_bytes: JSOS body (may span records at
                               chunk boundaries).

            :returns: RecordIngestResult with accepted + skipped
                      counts.
            :raises: ProgressAuthError, UnsupportedFormatError
        """
        ...
```

### Extension Surface

Factory protocol declared here:

```python
class ProgressParserProtocol(FactoryProtocolBase):
    """
        Contract for progress_parser implementations.
    """
    factory_protocol_name: str = "progress_parser"

    @classmethod
    def format_tag(cls) -> str:
        """
            Return the format tag this parser handles.

            :returns: A stable format tag string.
            :raises: None
        """
        ...

    @classmethod
    def parse_summary(
        cls,
        body_bytes: bytes
    ) -> ProgressSummary:
        """
            Parse a summary body into a ProgressSummary.

            :param body_bytes: Raw request body.

            :returns: ProgressSummary.
            :raises: ProgressParseError
        """
        ...

    @classmethod
    def parse_records(
        cls,
        body_bytes: bytes,
        start_seq: int
    ) -> Iterator[tuple[int, ProgressRecord]]:
        """
            Yield (seq, record) pairs by incrementally parsing a
            JSOS body.

            :param body_bytes: Raw request body.
            :param start_seq: Next seq value to assign.

            :returns: Iterator of (seq, ProgressRecord).
            :raises: None — bad records are skipped, counted.
        """
        ...
```

Reference implementations shipped in-tree (under
`source/site/automojo/factories/pychestrate/progress_parser/`):

- `TestBaseProgressParser` — `format_tag = "testbase-v1"`,
  `PRECEDENCE = 1000`. Parses testbase's
  `testrun_summary.json` and `testrun_results_stream.jsos` shapes.

### Events Emitted

On `0-message-bus`:

- `entity.progress.received` — `{run_id, project_id, kind:
  "summary" | "records", latest_offset: int, first: bool,
  received_at}`
- `pychestrate.ingest.progress.parse_skipped` — `{run_id,
  format, error_kind, error_id}`
- `pychestrate.ingest.progress.identifier_mismatch` — `{run_id,
  mismatch_fields}`
- `pychestrate.ingest.progress.auth_rejected` — `{run_id,
  authenticated_client_id, expected_client_id}`
- `pychestrate.ingest.progress.unknown_format` — `{format_tag,
  run_id}`

### Events Consumed

- `extension.reloaded` — rebuilds `_parser_registry`.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/`:

- `ingest/progress/__init__.py`
- `ingest/progress/routes.py` — WebWorks routes for the two endpoints.
- `ingest/progress/service.py` — `ProgressIngestService` facade.
- `ingest/progress/jsos.py` — 0x1E record splitter, chunk-boundary
  aware.
- `ingest/progress/parser_registry.py` — factory protocol
  resolution keyed by `format_tag`.
- `ingest/progress/protocol.py` — `ProgressParserProtocol`.
- `ingest/progress/repositories.py` — `ProgressSummaryRepository`,
  `ProgressRecordRepository`, `ProgressCounterRepository`.
- `ingest/progress/schema.py` — Pydantic models for internal value
  types.
- `ingest/progress/auth.py` — client-id binding check.
- `ingest/progress/errors.py` — `ProgressAuthError`,
  `ProgressIdentifierMismatchError`, `ProgressParseError`,
  `UnsupportedFormatError`.
- `ingest/progress/hooks.py` — startup hook that instantiates the
  service and registers routes.

Factories live under
`source/site/automojo/factories/pychestrate/progress_parser/`.

## Key Flows

### Flow 1 — Summary POST

1. Client POSTs to
   `/ingest/v1/progress/<run_id>/summary`.
2. Auth middleware extracts `authenticated_client_id`.
3. Route handler invokes `ingest_summary`.
4. Service verifies `authenticated_client_id` matches
   `receipt_lookup.lookup_by_run(run_id).client_id` → else
   `ProgressAuthError` → 403.
5. Service selects parser from `_parser_registry` keyed by
   `format_tag`.
6. Parser normalizes the body; service validates every testbase
   identifier against the envelope via `envelope_reader`.
7. On success: row persisted, counters updated,
   `entity.progress.received` published on the outbox.

### Flow 2 — Records POST (JSOS)

1. Client POSTs JSOS body to
   `/ingest/v1/progress/<run_id>/records`.
2. Service acquires `_stream_locks[run_id]`.
3. Service fetches `next_seq` from the record repository.
4. `jsos.split(body_bytes)` yields record byte slices — any
   trailing partial slice (chunk boundary) is buffered for the
   next POST (the lock serializes posts for this run).
5. Parser yields `(seq, ProgressRecord)` pairs; bad records are
   skipped and counted.
6. Bulk INSERT of records; counter repository `UPDATE … WHERE
   run_id = :run_id` applied atomically with record insert via a
   single transaction.
7. `entity.progress.received` published once per batch with
   `kind="records"`.

### Flow 3 — First Progress → Running Transition

1. First successful ingest for a run publishes
   `entity.progress.received` with `first=true`.
2. `5-run-state-machine` subscribes; maps to `first_progress`
   event → transitions `dispatched → running`.

## Error Handling

- `ProgressAuthError`: domain error → 403.
- `ProgressIdentifierMismatchError`: multiline message listing
  mismatching fields → 409.
- `UnsupportedFormatError`: lists every registered `format_tag` →
  415.
- `ProgressParseError`: per-request (not per-record) → 422; the
  per-record path skips and counts instead.
- `SemanticError` (unknown `run_id`, malformed `run_id` UUID):
  never caught → translated to 404 at the route boundary.
- Parser exceptions that are not `ProgressParseError` are caught
  at the parser boundary, reclassified to `ProgressParseError`
  with parser-class + format-tag context, re-raised.

Example multiline error:

```python
err_msg_lines = ["Progress summary identifiers do not match envelope."]
err_msg_lines.append("RUN_ID: {}".format(run_id))
err_msg_lines.append("MISMATCHES:")
for field_name, envelope_value, summary_value in mismatches:
    err_msg_lines.append(
        "    {} : envelope={!r} summary={!r}".format(
            field_name, envelope_value, summary_value
        )
    )

err_msg = os.linesep.join(err_msg_lines)
raise ProgressIdentifierMismatchError(err_msg) from None
```

## Security Considerations

- Endpoints are authenticated via the client-agent bearer token
  resolved by `3-client-agent-protocol`'s auth middleware.
- Auth binding: `authenticated_client_id` must equal the receipt's
  `client_id`; mismatch → 403 + `auth_rejected` event.
- Body size caps enforced before parse to prevent OOM from a
  malicious client.
- Rate limit per `client_id` via a token-bucket middleware.
- Identifier validation is load-bearing — prevents a compromised
  client from posting summaries for a run it does not own (even if
  token is leaked, ids won't match).
- Parser extensions run in-process; `E-extension-sandbox`
  `write:progress` capability gates parser registration in Phase 8.

## Observability

Metrics:

- `pychestrate_ingest_progress_requests_total{endpoint,format,result}`
  — counter
- `pychestrate_ingest_progress_records_total{project,parser}` —
  counter (run_id label avoided for cardinality; aggregated per
  project)
- `pychestrate_ingest_progress_bytes_total{endpoint,format}` —
  counter
- `pychestrate_ingest_progress_latency_seconds{endpoint,format}` —
  histogram
- `pychestrate_ingest_progress_parse_errors_total{project,format}` —
  counter
- `pychestrate_ingest_progress_active_streams` — gauge
- `pychestrate_ingest_progress_lock_wait_seconds` — histogram

Log events:

- `pychestrate.ingest.progress.summary.received`
- `pychestrate.ingest.progress.records.received`
- `pychestrate.ingest.progress.parse_skipped`
- `pychestrate.ingest.progress.identifier_mismatch`
- `pychestrate.ingest.progress.auth_rejected`
- `pychestrate.ingest.progress.unknown_format`

Trace span `pychestrate.ingest.progress.post` with attrs `endpoint`,
`format`, `run_id`, `project`, `record_count`, `bytes`.

Dashboards: records-per-second, parse-error rate, active-streams
gauge on `7-orchestration-metrics`; alert when parse-error ratio
> 2% for 5 minutes.

## Open Questions

- Chunk-boundary buffering across POSTs: do we store partial
  trailing bytes in the DB (survives restart) or only in memory
  (requires client to retry on 202 ack failure)? Current draft:
  in-memory for M1, DB-backed for M3 alongside
  `5-offline-tolerance`. Timebox: Phase 5 start.
- Do we expose a websocket mirror for progress so `9-wc-log-stream`
  can connect directly? Current draft: no — the WC subscribes to
  the bus via the server's SSE gateway. Timebox: Phase 5.
- Back-pressure: when ingest falls behind should we 503 or buffer
  internally? Current draft: 503 + `Retry-After` based on active
  stream count. Timebox: Phase 3 exit.
