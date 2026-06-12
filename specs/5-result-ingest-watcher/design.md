# 5-result-ingest-watcher — Design

## Architecture

The result watcher is a pair of long-running tasks owned by
`source/site/ccai/pychestrate/webservice/ingest/result/`:

1. A **detector** that observes the shared backend — either via a
   driver-native change feed (S3/EventBridge, Azure Event Grid, GCS
   Pub/Sub) or via polling with `last_modified` watermarks — and
   enqueues scan tasks when it sees the `.pychestrate_landed`
   sentinel under a run prefix.
2. A **scanner** that dequeues, fetches the tree manifest, routes
   through the `ResultTreeParserProtocol` whose `format_tag()`
   matches, walks the file set classifying each through every
   registered `ArtifactClassifierExtension`, hands blobs to
   `5-artifact-store`, and emits terminal events.

Ingest is passive — Pychestrate never asks the client for the tree.
Authoritative source of truth is the object-store tree itself.
Parsed state is a projection stored in `run_result_summary`,
`task_result`, and `run_artifact` tables. This feature lands in
**Phase 3** and bridges raw file landings into the `5-run-state-machine`
terminal events.

## Data Model

Owned rows:

- `run_result_summary`:
  - `run_id: UUID` (PK)
  - `parser_tag: str`
  - `scanned_at: timestamptz`
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
  - `terminal_outcome: TerminalOutcome`
  - `counters_pass: int`
  - `counters_fail: int`
  - `counters_error: int`
  - `counters_skipped: int`
  - `summary_html_key: str` (object-store key of
    `testsummary.html`)
  - `raw_summary: jsonb` (from `testrun_results.json`)
- `task_result`:
  - `task_result_id: UUID` (PK, UUIDv7)
  - `run_id: UUID` (FK, indexed)
  - `tasking_uuid: str`
  - `worker: str`
  - `instance: str`
  - `parent: str | None`
  - `rtype: str`
  - `result: str`
  - `task_summary_key: str` (object-store key)
  - `started_at: timestamptz | None`
  - `completed_at: timestamptz | None`
- `run_artifact`:
  - `artifact_id: UUID` (PK, UUIDv7)
  - `run_id: UUID` (FK, indexed)
  - `path: str` (relative to run prefix)
  - `category: str`
  - `mime: str | None`
  - `size_bytes: int`
  - `content_hash: str` (sha256, via `5-artifact-store`)
  - `label: str | None` (e.g., artifacts/`<label>`)
  - `tasking_uuid: str | None`
  - `classifier_name: str`
  - Unique constraint: `(run_id, path)`,
    `(run_id, content_hash, path)`.
- `result_scan_attempt`:
  - `attempt_id: UUID` (PK, UUIDv7)
  - `run_id: UUID` (FK, indexed)
  - `started_at: timestamptz`
  - `completed_at: timestamptz | None`
  - `status: ScanStatus`
  - `retries: int`
  - `last_error: str | None`

In-memory state:

- `_scan_queue: asyncio.Queue[ScanTask]`
- `_backoff_queue: list[BackoffEntry]`
- `_backlog_gauge_value: int`

## Interfaces

### Public API

N/A. The watcher has no external HTTP surface — it listens to
object-store events and/or polls.

### Internal API

```python
class ResultWatcherDetector:
    def __init__(
        self,
        object_store: ObjectStore,
        shared_backend: SharedResultsBackend,
        scanner: ResultWatcherScanner,
        config: WatcherConfig
    ) -> None:
        self._object_store = object_store
        self._shared_backend = shared_backend
        self._scanner = scanner
        self._config = config
        return

    def start(
        self,
        aspects: WatcherAspects | None = None
    ) -> None:
        """
            Start the detector loop — native change feed or polling.

            :param aspects: Behavior parameters.

            :returns: None
            :raises: ConfigurationError
        """
        ...

    def stop(self) -> None:
        """
            Signal the detector loop to drain and exit.

            :returns: None
            :raises: None
        """
        ...


class ResultWatcherScanner:
    def __init__(
        self,
        object_store: ObjectStore,
        parser_registry: ResultTreeParserRegistry,
        classifier_registry: ArtifactClassifierRegistry,
        artifact_store: ArtifactStore,
        summary_repository: ResultSummaryRepository,
        task_repository: TaskResultRepository,
        artifact_repository: RunArtifactRepository,
        attempt_repository: ScanAttemptRepository,
        bus: MessageBus,
        envelope_reader: EnvelopeReader,
        progress_summary_reader: ProgressSummaryReader,
        config: WatcherConfig
    ) -> None:
        self._object_store = object_store
        self._parser_registry = parser_registry
        self._classifier_registry = classifier_registry
        self._artifact_store = artifact_store
        self._summary_repository = summary_repository
        self._task_repository = task_repository
        self._artifact_repository = artifact_repository
        self._attempt_repository = attempt_repository
        self._bus = bus
        self._envelope_reader = envelope_reader
        self._progress_summary_reader = progress_summary_reader
        self._config = config
        return

    def scan(
        self,
        run_id: UUID,
        prefix: str,
        parser_tag: str
    ) -> ScanOutcome:
        """
            Parse a landed tree, classify every file, persist,
            emit events.

            :param run_id: Service run id.
            :param prefix: Object-store prefix under which the tree
                           lives.
            :param parser_tag: Tree parser format tag.

            :returns: ScanOutcome with counts + terminal outcome.
            :raises: IncompleteTreeError, UnknownFormatError,
                     ScanFailedError
        """
        ...
```

### Extension Surface

Factory protocol declared here:

```python
class ResultTreeParserProtocol(FactoryProtocolBase):
    """
        Contract for result_tree_parser implementations.
    """
    factory_protocol_name: str = "result_tree_parser"

    @classmethod
    def format_tag(cls) -> str:
        ...

    @classmethod
    def parse_tree(
        cls,
        object_store: ObjectStore,
        prefix: str
    ) -> ParsedResultTree:
        """
            Walk the tree at the given prefix and return a
            ParsedResultTree (summary + task_results + file_index).

            :param object_store: Object store facade (read-only here).
            :param prefix: Prefix for this run.

            :returns: ParsedResultTree.
            :raises: IncompleteTreeError, ResultParseError
        """
        ...
```

Resource extension base declared here:

```python
class ArtifactClassifierExtension(ResourceExtension):
    """
        Classify files into artifact categories by path, mime, and
        magic bytes. PRECEDENCE ordered; first non-None wins.
    """

    @classmethod
    def classify(
        cls,
        path: str,
        mime: str | None,
        magic_bytes: bytes,
        size_bytes: int
    ) -> ArtifactClassification | None:
        """
            Return a classification or None to defer to the next
            classifier.

            :param path: Relative path under the run prefix.
            :param mime: Best-effort MIME type.
            :param magic_bytes: First 64 bytes of the file.
            :param size_bytes: Total size.

            :returns: ArtifactClassification or None.
            :raises: None
        """
        rtnval = None
        return rtnval
```

Reference implementations shipped in-tree (paths rooted under
`source/site/ccai/factories/pychestrate/result_tree_parser/`
and `source/site/ccai/extensions/pychestrate/artifact_classifiers/`):

- `TestBaseResultTreeParser` — `format_tag = "testbase-v1"`,
  `PRECEDENCE = 1000`. Parses the full testbase tree:
  `testrun_summary.json`, `testrun_results_stream.jsos`,
  `testrun_results.json`, `testsummary.html`, and all subdirs.
- `TestBaseSummaryClassifier` — categories `summary-json`,
  `summary-html`, `progress-stream`, `final-results`.
- `TestBaseTaskingClassifier` — categories `task-summary`,
  `task-artifact`.
- `TestBaseArtifactLabelClassifier` — categories keyed by the
  `<label>` directory under `artifacts/`.
- `TestBaseDiagnosticClassifier` — category `diagnostic`.
- `TestBaseStaticAssetClassifier` — category `static-asset`.
- `TestBaseTcByProductClassifier` — category `tc-by-product`.

### Events Emitted

On `0-message-bus`:

- `entity.result_tree.landed` — `{run_id, project_id, parser_tag,
  terminal_outcome, file_count, bytes_scanned, scanned_at}`
- `entity.artifact.ingested` — `{run_id, artifact_id, category,
  path, content_hash, size_bytes}`
- `pychestrate.ingest.result.tree_detected` — `{run_id, prefix,
  driver}`
- `pychestrate.ingest.result.scan_completed`
- `pychestrate.ingest.result.incomplete_tree`
- `pychestrate.ingest.result.unknown_format`
- `pychestrate.ingest.result.unclassified` — `{run_id, path, mime}`

### Events Consumed

- `object_store.object.put` — when the backend driver publishes
  writes, used as the polling-free detection path.
- `extension.reloaded` — rebuilds parser + classifier registries.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/`:

- `ingest/result/__init__.py`
- `ingest/result/detector.py` — `ResultWatcherDetector`.
- `ingest/result/scanner.py` — `ResultWatcherScanner`.
- `ingest/result/parser_registry.py`
- `ingest/result/classifier_registry.py`
- `ingest/result/protocols.py` — `ResultTreeParserProtocol`,
  `ArtifactClassifierExtension`.
- `ingest/result/repositories.py` — summary, task, artifact,
  attempt repos.
- `ingest/result/schema.py` — `ParsedResultTree`,
  `ArtifactClassification`, `ScanOutcome` Pydantic models.
- `ingest/result/errors.py` — `IncompleteTreeError`,
  `UnknownFormatError`, `ScanFailedError`.
- `ingest/result/hooks.py` — startup hook that launches detector
  + scanner tasks.

Factories under
`source/site/ccai/factories/pychestrate/result_tree_parser/`,
extensions under
`source/site/ccai/extensions/pychestrate/artifact_classifiers/`.

## Key Flows

### Flow 1 — Sentinel → Scan → Terminal

1. Client finishes the run, writes every file under
   `<prefix>/`, drops `<prefix>/.pychestrate_landed`.
2. Detector (change-feed or poller) sees the sentinel;
   enqueues a `ScanTask(run_id, prefix, parser_tag_from_envelope)`.
3. Scanner dequeues; `attempt_repository.start(run_id)`;
   `parser_registry.resolve(parser_tag).parse_tree(prefix)`
   returns a `ParsedResultTree`.
4. Scanner validates identifiers against envelope and against any
   persisted progress summary; mismatch → `needs_investigation`.
5. Scanner walks `ParsedResultTree.file_index`, calls every
   `classifier_registry.classify(...)` in order, registers blobs
   with `5-artifact-store`, persists `run_artifact` rows.
6. Scanner persists `task_result` rows from
   `taskings/<uuid>/task-summary.json`.
7. Scanner persists `run_result_summary`, emits
   `entity.result_tree.landed` with `terminal_outcome` from
   `testrun_results.json`.
8. `5-run-state-machine` subscribes, maps to `completion_observed`
   or `failure_observed`, transitions terminal.

### Flow 2 — Polling Driver

1. Detector queries `object_store.list(prefix=<shared-root>,
   limit=1000)` every 15 s.
2. Filters entries with key ending in `.pychestrate_landed` and
   `last_modified > watermark`.
3. Advances watermark; enqueues scans.
4. Back-pressure: if `_scan_queue.qsize() > backlog_cap` (default
   200) the detector skips a poll cycle and emits a gauge alert.

### Flow 3 — Incomplete Tree Grace

1. Sentinel observed; scanner starts; parser throws
   `IncompleteTreeError` because `testrun_summary.json` is missing.
2. Scanner backs off for `completion_grace_seconds / 4` and
   retries.
3. After 4 retries (~120 s), scanner emits
   `pychestrate.ingest.result.incomplete_tree` and transitions the
   run to `needs_investigation`.

## Error Handling

- `IncompleteTreeError`: handled internally with grace retries;
  escalates to `needs_investigation` after exhaustion.
- `UnknownFormatError`: escalates immediately; operator must
  install the parser extension.
- `ScanFailedError`: bubbles to `_backoff_queue`; exponential
  backoff 30 s → 30 min across 5 attempts, then
  `needs_investigation`.
- `ResultParseError` (from parser): caught at parser boundary,
  reclassified with `run_id`, `prefix`, `parser_tag` context.
- `SemanticError` (parser returns malformed `ParsedResultTree`):
  never caught — parser bug.

Example multiline error:

```python
err_msg_lines = ["Result tree scan failed — incomplete."]
err_msg_lines.append("RUN_ID: {}".format(run_id))
err_msg_lines.append("PREFIX: {}".format(prefix))
err_msg_lines.append("EXPECTED (missing):")
for path in missing:
    err_msg_lines.append("    {}".format(path))

err_msg = os.linesep.join(err_msg_lines)
raise IncompleteTreeError(err_msg) from None
```

## Security Considerations

- Object-store reads use service credentials scoped to
  `results:read`.
- Every path read by a parser is validated against
  `^<prefix>/[A-Za-z0-9/_.\-]+$` — blocks traversal via symlinked
  NFS mounts.
- Artifact size cap prevents OOM on malicious/misbehaving clients.
- Parsers run in-process; `E-extension-sandbox` `read:artifacts`
  capability gates parser registration in Phase 8.
- No user-controlled eval paths — all JSON parsed with strict
  schema (`additionalProperties: false`).

## Observability

Metrics:

- `pychestrate_ingest_result_trees_landed_total{project}` — counter
- `pychestrate_ingest_result_tree_scan_duration_seconds{project,parser}`
  — histogram
- `pychestrate_ingest_result_backlog_depth` — gauge
- `pychestrate_ingest_result_files_processed_total{project,category}`
  — counter
- `pychestrate_ingest_result_unclassified_files_total{project,mime}`
  — counter
- `pychestrate_ingest_result_incomplete_trees_total{project}` —
  counter
- `pychestrate_ingest_result_detection_latency_seconds{driver}` —
  histogram
- `pychestrate_ingest_result_scan_retries_total{project}` —
  counter

Log events listed in requirements.md NFR-3. Trace span
`pychestrate.ingest.result.scan` with `project`, `run_id`, `parser`,
`file_count`, `bytes_processed`.

Dashboards: backlog + detection-latency tile on
`7-orchestration-metrics`; unclassified-rate alert on
`7-alerts-budgets` (> 10% for 1 h → investigate new file types).

## Open Questions

- Should the sentinel path be a key convention or a separate
  object-store API (e.g., `mark_landed(run_id)`)? Current draft:
  sentinel key — cheap, works across every driver without
  capability gating. Timebox: Phase 3 exit.
- Do we ingest `testrun_results.json` as-is or normalize to the
  `task_result` row set? Current draft: both — raw kept in
  `run_result_summary.raw_summary`, normalized rows in
  `task_result`. Timebox: Phase 3 exit.
- How do we handle a tree that lands *without* a preceding
  envelope (orphan results from a misconfigured client)? Current
  draft: reject with `needs_investigation`. Timebox: Phase 3 exit.
