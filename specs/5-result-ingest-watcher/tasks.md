# 5-result-ingest-watcher — Tasks

## Milestones

- **M1 — Skeleton:** Polling detector, sentinel scan trigger,
  `TestBaseResultTreeParser`, summary + task + artifact tables,
  classifier registry with default classifier suite,
  `entity.result_tree.landed` emission.
- **M2 — Core Behavior:** Change-feed detector path for drivers
  that advertise it, incomplete-tree grace logic, identifier
  cross-validation (envelope + progress summary), backoff queue,
  artifact store registration, all artifact classifier extensions
  wired.
- **M3 — Hardening:** Property tests, perf validation, dashboards,
  alerts, unclassified-budget docs, restart idempotency.

## Tasks

### M1 — Skeleton

- [x] T1.1 — Create `ingest/result/` package skeleton per design.md Component Breakdown.
- [x] T1.2 — Add Postgres migrations for `run_result_summary`, `task_result`, `run_artifact`, `result_scan_attempt`.
      *(``019_phase3_results_ingest`` creates the four tables +
      ``ingest_scan_outcome_status`` enum.)*
- [x] T1.3 — Implement `ingest/result/repositories.py` for summary/task/artifact/attempt.
      *(``upsert_summary``, ``upsert_task_result``,
      ``upsert_artifact``, ``insert_scan_attempt``,
      ``finalize_scan_attempt``, plus list/find helpers.)*
- [~] T1.4 — Implement `ingest/result/detector.py` polling path (15 s interval) with `last_modified` watermark.
      *(M1 exposes ``scan_once(run_id, tree_path)`` so callers
      drive each scan explicitly. The polling daemon with
      watermark bookkeeping lands in M2 alongside the
      ``5-shared-results-backend`` ``mark_landed`` subscription.)*
- [x] T1.5 — Implement `ingest/result/scanner.py::ResultWatcherScanner.scan` end-to-end happy path.
      *(``scanner.scan_once`` records a ``ResultScanAttempt``
      row, parses the tree, persists summary / task / artifact
      rows idempotently, and emits
      ``entity.result_tree.landed`` plus per-task and
      per-artifact events.)*
- [~] T1.6 — Implement `TestBaseResultTreeParser` at `source/site/ccai/factories/pychestrate/result_tree_parser/testbase_v1.py` with `PRECEDENCE = 1000`; handles all testbase tree files and subdirs.
      *(In-package at
      ``ingest/result/factories/testbase_v1.py``;
      ``PRECEDENCE=1000`` preserved. Reads
      ``testrun_summary.json``,
      ``testrun_results_stream.jsos`` (terminal records, deduped
      on ``instance`` UUID), and walks every regular file as an
      artifact with classification by top-level subdirectory.)*
- [~] T1.7 — Implement default `ArtifactClassifierExtension`s under `source/site/ccai/extensions/pychestrate/artifact_classifiers/` covering summary, progress-stream, taskings, tc-by-products, diagnostics, static, and labelled artifacts.
      *(M1 classifies inline in the testbase parser via the
      ``ARTIFACT_CLASSIFICATION_MAP``. Extracting the classifiers
      into a registry of ``ArtifactClassifierExtension`` packs
      lands when an out-of-tree classifier is needed (M2).)*
- [x] T1.8 — Emit `entity.result_tree.landed` and per-file `entity.artifact.ingested` via the outbox onto `0-message-bus`.
      *(Plus ``entity.task_result.ingested`` per task — same
      session-outbox pattern the run-state-machine uses.)*

### M2 — Core Behavior

- [ ] T2.1 — Implement change-feed detector path: subscribe to `object_store.object.put` on drivers that advertise the capability.
- [ ] T2.2 — Implement `completion_grace_seconds` grace loop for `IncompleteTreeError` with up to 4 retries; escalate to `needs_investigation`.
- [ ] T2.3 — Cross-validate identifiers: envelope vs. `testrun_summary.json` vs. final progress summary. Mismatch → `needs_investigation` + `pychestrate.ingest.result.incomplete_tree`.
- [ ] T2.4 — Implement `_backoff_queue` with 30 s → 30 min exponential backoff, max 5 attempts.
- [ ] T2.5 — Register each discovered blob with `5-artifact-store.register(...)`; uniqueness on `(run_id, content_hash, path)`.
- [ ] T2.6 — Implement `TaskResultRepository` persistence from `taskings/<uuid>/task-summary.json` files.
- [ ] T2.7 — Implement `format_tag` selection: read from envelope `results.format_tag`; default `"testbase-v1"`.
- [ ] T2.8 — Subscribe to `extension.reloaded` and rebuild `_parser_registry` + `_classifier_registry`.

### M3 — Hardening

- [ ] T3.1 — Emit Prometheus metrics and OTel trace span per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: detection p99 < 5 s (change-feed) / < 20 s (polling); 1000-file / 500 MiB tree scanned p99 < 30 s.
- [ ] T3.3 — Add backlog-depth alert: `pychestrate_ingest_result_backlog_depth > 50` for 10 min → page on-call.
- [ ] T3.4 — Add unclassified-rate alert: `> 10%` of files for 1 h.
- [ ] T3.5 — Implement oversize-file skip + log: > 5 GiB artifacts logged and skipped, not fatal.
- [ ] T3.6 — Restart idempotency: assert replaying a scan does not duplicate `run_artifact` rows (unique constraint + upsert).
- [ ] T3.7 — Document runner author guide `usersguide/ingest/result/testbase_tree_layout.rst` reflecting all testbase files/subdirs Pychestrate consumes.
- [ ] T3.8 — Verify multiline errors use `os.linesep.join([...])`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (artifact count preservation) and Property 2 (identifier equality), 1000 cases each.
- [ ] TT-3 — Integration test: client writes a full testbase tree to the local-fs object store, drops sentinel; watcher scans; assert summary + task + artifact rows persisted and `entity.result_tree.landed` emitted with correct `terminal_outcome`.
- [ ] TT-4 — Extension-point test: register a test-only `GTestFlatResultTreeParser` (`format_tag = "gtest-flat-v1"`, `PRECEDENCE = 500`) and a test-only `SBOMArtifactClassifierExtension`; assert both are used during a scan.
- [ ] TT-5 — Incomplete-tree test: write sentinel before `testrun_summary.json`; assert scan retries 4 times then marks `needs_investigation`.
- [ ] TT-6 — Restart test: kill the scanner mid-scan; restart; assert scan resumes with no duplicate artifact rows.
- [ ] TT-7 — Identifier-mismatch test: perturb `BuildInfo.build` in `testrun_summary.json`; assert run transitions to `needs_investigation` with reason `result_identifier_mismatch`.

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
