# 5-result-ingest-watcher — Requirements

## Introduction

The `5-result-ingest-watcher` feature is Pychestrate's passive
observer of the shared results backend. When a pod client finishes
a job, it writes the full testbase result tree — `testrun_summary.json`,
`testrun_results_stream.jsos`, `testrun_results.json`,
`testsummary.html`, plus `artifacts/<label>/`, `static/`,
`diagnostics/`, `taskings/<uuid>/task-summary.json`, and
`tc-by-products/<uuid>/` subdirs — under the per-run prefix allocated
by `5-shared-results-backend`. The watcher sees the tree, parses it
with a `result_tree_parser` (testbase default in-tree; extensions
may add gtest-flat, custom formats, etc.), classifies every artifact
via registered `ArtifactClassifierExtension`s, hands content-addressed
blobs to `5-artifact-store`, and emits `entity.result_tree.landed`
plus per-artifact `entity.artifact.ingested`. Pychestrate never pulls
the result tree — the client pushes it to the backend, and the
watcher reacts. This feature ships in **Phase 3**.

## Requirements

### Requirement 1: Passive Detection of a Completed Result Tree

**User Story:** As a service operator, I want Pychestrate to notice
every result tree the client finishes writing, so that runs appear
completed without the client having to call back to signal
completion.

**Acceptance Criteria (EARS):**

1. WHEN the client writes a sentinel file `.pychestrate_landed`
   under the run's results prefix `<backend_key_prefix>/` THEN
   the watcher SHALL enqueue that prefix for scanning within
   `detection_latency_seconds` (default 5 s) at p99.
2. WHILE an object-store driver advertises a native change-feed
   capability (e.g., S3 EventBridge, Azure Event Grid) the
   watcher SHALL consume that feed in preference to polling.
3. WHERE no native change-feed exists the watcher SHALL poll the
   backend's `list(prefix)` API on an operator-tuned interval
   (default 15 s) AND use `last_modified` watermarks to bound work.
4. IF a sentinel is observed but the tree is incomplete (missing
   `testrun_summary.json` OR missing referenced artifact files)
   THEN the watcher SHALL wait up to `completion_grace_seconds`
   (default 120 s) for the tree to finish; if still incomplete, it
   SHALL mark the run `needs_investigation` and emit
   `pychestrate.ingest.result.incomplete_tree`.

### Requirement 2: Tree Parsing via `result_tree_parser` Factory

**User Story:** As an extension author writing a new runner
integration, I want to register a result-tree parser keyed by a
format tag, so that my runner's layout is understood without
patching the service.

**Acceptance Criteria (EARS):**

1. WHEN a run's envelope declared `results.format_tag` THEN the
   watcher SHALL select the `ResultTreeParserProtocol`
   implementation whose `format_tag()` matches — defaulting to
   `"testbase-v1"` when the envelope omits the tag.
2. WHEN the testbase parser is active THEN the watcher SHALL
   extract `runid`, pipeline `id/instance`, `job.id/name/type`,
   `BuildInfo.branch/build/flavor/release` from
   `testrun_summary.json` AND validate each against the envelope
   — mismatch → run marked `needs_investigation` with reason
   `result_identifier_mismatch`.
3. WHEN the testbase parser processes `taskings/<uuid>/task-summary.json`
   THEN the system SHALL persist a `task_result` row per file with
   `worker`, `instance`, `parent`, `rtype`, `result` identifiers
   preserved.
4. WHERE no parser matches a declared `format_tag` THEN the watcher
   SHALL mark the run `needs_investigation` with reason
   `no_tree_parser` and emit
   `pychestrate.ingest.result.unknown_format`.

### Requirement 3: Per-File Classification via `ArtifactClassifierExtension`

**User Story:** As a downstream artifact browser, I want every file
under `artifacts/<label>/`, `static/`, `diagnostics/`, and
`tc-by-products/<uuid>/` tagged with an artifact category, so that
the UI can render previews appropriately and retention rules can
target categories.

**Acceptance Criteria (EARS):**

1. WHEN the watcher walks a parsed tree THEN the system SHALL
   present each discovered file to every registered
   `ArtifactClassifierExtension.classify(path, mime, magic_bytes,
   size)` AND accept the first non-None classification in
   `PRECEDENCE` order.
2. IF zero classifiers return a classification THEN the system
   SHALL assign category `unclassified` AND emit
   `pychestrate.ingest.result.unclassified` with file path and
   detected mime.
3. WHEN a file is classified THEN the system SHALL register the
   blob with `5-artifact-store` via `store.register(run_id, path,
   category, labels)` — the store performs content-addressing.
4. WHEN every file has been processed THEN the watcher SHALL emit
   exactly one `entity.result_tree.landed` per run including
   `terminal_outcome` derived from `testrun_results.json`
   (`success`, `failure`, `cancelled`, or `error`).

## Property-Based Test Requirements

### Property 1: Artifact Count Preservation

- **Invariant:** For any generated testbase tree containing `F`
  files across `artifacts/`, `static/`, `diagnostics/`,
  `taskings/<uuid>/`, `tc-by-products/<uuid>/` subdirs, the
  watcher persists exactly `F` `run_artifact` rows (plus the four
  top-level summary files) and emits exactly `F + 4`
  `entity.artifact.ingested` events, with no duplicates.
- **Generator:** `hypothesis.strategies.builds(testbase_tree(),
  file_count=integers(0, 500), subdir_distribution=...)` returning
  a temp directory populated with realistic file contents. Write
  to a local-fs object-store driver, drop the sentinel, run the
  watcher.
- **Assertion:** row count equals `F + 4`; emitted event count
  equals `F + 4`; `(run_id, path)` is unique across persisted
  rows.
- **Sample size:** 1000 generated cases

### Property 2: Summary Identifier Equality Across Envelope, Progress, and Result

- **Invariant:** For any run where `5-progress-ingest` persisted
  a final summary *and* the result watcher parses a
  `testrun_summary.json`, the identifier tuples
  `(runid, pipeline_id, pipeline_instance, job_id, job_name,
  job_type, build_branch, build_build, build_flavor, build_release)`
  from envelope, progress summary, and result summary are all
  equal. Mismatch marks the run `needs_investigation`.
- **Generator:** Build an envelope; derive matching progress and
  result summaries; perturb a single identifier in the result
  summary with probability 0.3 and assert the run transitions to
  `needs_investigation` iff perturbation happened.
- **Assertion:** equal tuples when unperturbed; divergence
  detected when perturbed.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Watcher detection latency p99 < 5 s
  from sentinel write to scan start with change-feed drivers; p99
  < 20 s with polling drivers at 15 s interval. Tree ingest
  throughput p99 < 30 s for a 1000-file, 500 MiB tree. Watcher
  backlog depth gauge SHALL stay below 50 trees awaiting scan under
  normal load.
- **NFR-2 (Security):** Watcher reads are authenticated to the
  object store using service credentials from `1-secrets-vault`.
  Parsers run in-process and MUST validate every file path
  against `^<prefix>/[A-Za-z0-9/_.\-]+$` before opening to block
  path traversal. File size cap per artifact: default 5 GiB;
  oversize files skipped + logged, not fatal.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_ingest_result_trees_landed_total{project}` (counter),
  `pychestrate_ingest_result_tree_scan_duration_seconds{project,parser}`
  (histogram),
  `pychestrate_ingest_result_backlog_depth` (gauge),
  `pychestrate_ingest_result_files_processed_total{project,category}`
  (counter),
  `pychestrate_ingest_result_unclassified_files_total{project,mime}`
  (counter),
  `pychestrate_ingest_result_incomplete_trees_total{project}`
  (counter),
  `pychestrate_ingest_result_detection_latency_seconds{driver}`
  (histogram). Log events
  `pychestrate.ingest.result.tree_detected`,
  `pychestrate.ingest.result.scan_completed`,
  `pychestrate.ingest.result.incomplete_tree`,
  `pychestrate.ingest.result.unknown_format`,
  `pychestrate.ingest.result.unclassified`. Trace span
  `pychestrate.ingest.result.scan` with attributes `project`,
  `run_id`, `parser`, `file_count`, `bytes_processed`.
- **NFR-4 (Reliability):** A failed scan SHALL be retried with
  exponential backoff starting at 30 s, capped at 30 min, up to 5
  attempts. After final failure the run is marked
  `needs_investigation` and a human-review record is queued.
  Process restart MUST resume scans in progress without re-processing
  already-ingested artifacts — the `run_artifact` row's
  `(run_id, content_hash)` uniqueness provides idempotency.

## Out of Scope

- Per-run prefix allocation on the shared backend — owned by
  `5-shared-results-backend`.
- Content-addressed blob storage and promotion — owned by
  `5-artifact-store`.
- UI rendering of artifacts — owned by `6-artifact-browser` and
  `6-live-run-view`.
- Live progress ingest — owned by `5-progress-ingest`.
- Retention/purge of result trees — owned by `2-retention-policies`.

## Dependencies

- **Depends on:** `0-object-store`, `0-persistence`, `0-message-bus`,
  `5-shared-results-backend`, `5-artifact-store`, `5-job-envelope`
  (identifier reference), `5-progress-ingest` (identifier
  cross-check), `5-run-state-machine` (transition sink),
  `E-extension-host`, `E-factory-protocols`, `E-resource-extensions`.
- **Depended on by:** `6-live-run-view` (terminal transitions),
  `6-artifact-browser`, `6-compare-runs`, `7-test-metrics`.
- **Extension points exposed:** `factory: result_tree_parser`,
  `resource: ArtifactClassifierExtension` — see
  implementation-plan.md Layer 5 section.
