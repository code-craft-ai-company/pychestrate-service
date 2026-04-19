# 6-flake-tracking — Requirements

## Introduction

The `6-flake-tracking` feature measures per-test stability across runs
and attaches a classification (`stable`, `intermittent`, `flaky`,
`quarantined`, `broken`) to every catalog entry. It drives quarantine
(exclude from required gates) and per-test retry policy decisions, and
it provides history inputs to `WeightedByHistoryStrategy` in
`6-matrix-sharding`. The feature ships in **Phase 5** alongside
`6-triage-bug-linking` and `6-compare-runs`, and sits between
`6-test-orchestration` (result producer) and `6-pipeline-definition`
(which consults classification to decide whether a test is blocking).
Authoritative source of truth for per-test outcomes is the testbase
result tree + `5-result-ingest-watcher`; this feature is a rollup that
owns classification and per-test history.

## Requirements

### Requirement 1: Per-Test History Keyed By Stable Identity

**User Story:** As a test-quality owner, I want a durable per-test
history so that I can see the pass/fail pattern for a specific test
case across weeks of runs.

**Acceptance Criteria (EARS):**

1. WHEN `5-result-ingest-watcher` emits `entity.run.completed` for a test run THEN the system SHALL read `testrun_results.json`, iterate each test case, and append a `TestOutcome` row keyed by `(project_id, catalog_entry_id, test_case_identity_sha256)` with `{outcome, started_at, duration_ms, run_id, pod_id, runtime_env_digest}`.
2. WHEN the same test case is observed under a different `runtime_env_digest` THEN the system SHALL keep both histories AND compute classification per-env as well as aggregated.
3. IF a test case identity exceeds `max_identity_bytes` (default 512) THEN the system SHALL SHA-256 it and store the hash only, retaining the raw identity in a side table for display.
4. WHILE retention policy `test_outcome_max_age_days` (default 180) is active THEN the system SHALL drop outcome rows older than the window without losing computed classification state.

### Requirement 2: Classification Factory Protocol

**User Story:** As a platform owner with domain-specific flake
heuristics, I want to plug in my classifier, so that Pychestrate uses
our flake policy instead of its default.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers a `FlakeClassifierProtocol` implementation THEN the system SHALL verify `classifier_name`, `window_config`, `classify`, `explain` classmethods AND raise `ConfigurationError` naming missing methods.
2. WHEN classification runs THEN the system SHALL call the highest-precedence classifier's `classify(history: TestHistoryWindow) -> FlakeClassification` and persist the result with a `classifier_name` + `classifier_version` pair.
3. IF two classifiers share `(classifier_name, PRECEDENCE)` THEN the system SHALL raise `ConfigurationError` at load time.
4. WHERE the classifier declares `requires_min_samples: int` AND history has fewer samples THEN the system SHALL return classification `insufficient_data` rather than calling the classifier.

### Requirement 3: Quarantine And Retry

**User Story:** As a pipeline author, I want quarantined tests excluded
from the blocking gate and flaky tests retried automatically, so that
real regressions are not lost in the noise.

**Acceptance Criteria (EARS):**

1. WHEN classification for a test transitions to `quarantined` THEN the system SHALL emit `entity.flake.quarantined` AND `6-pipeline-definition` SHALL exclude it from required-gate evaluation.
2. WHEN classification is `flaky` AND the pipeline declares `retry_flaky: True` THEN `6-test-orchestration` SHALL retry the test up to `max_flaky_retries` (default 2) before finalizing a fail.
3. IF a quarantined test is manually un-quarantined via `flake.clear_quarantine(catalog_entry_id)` THEN the system SHALL emit `entity.flake.quarantine_cleared` AND SHALL require `quarantine.clear` RBAC.
4. WHEN a test transitions into `broken` (zero passes in the last `broken_threshold_runs`, default 5) THEN the system SHALL alert via `2-notification-hub` to the test's owner.

## Property-Based Test Requirements

### Property 1: Same History Yields Same Classification

- **Invariant:** For any `TestHistoryWindow` instance, `classifier.classify(window)` is a pure function of its inputs — two invocations with equal windows produce equal `FlakeClassification` and equal `explain(...)` output.
- **Generator:** `hypothesis.strategies.lists(sampled_from(Outcome), min_size=0, max_size=200)` paired with timestamps drawn from `floats(min_value=0.0, max_value=1.0e9)`.
- **Assertion:** `classify(w) == classify(copy(w))` and `explain(w) == explain(copy(w))`.
- **Sample size:** 1000 generated cases

### Property 2: Monotonic Quarantine (Classification Can Only Relax Via Explicit Action)

- **Invariant:** For any sequence of consecutive classifications reaching `quarantined`, the class SHALL NOT spontaneously revert to `stable`/`intermittent`/`flaky` without an explicit `clear_quarantine` action appearing in the log.
- **Generator:** `hypothesis.strategies.lists(sampled_from([Outcome.PASS, Outcome.FAIL]), min_size=0, max_size=500)` as a post-quarantine outcome stream.
- **Assertion:** For all prefixes of the stream, stored classification remains `quarantined` unless a `flake.clear_quarantine(...)` event is present in the stream.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Ingesting per-test outcomes from a 5 000-test run p99 < 2 s. `classify` per-test p99 < 5 ms. Aggregate classification update after a run completion p99 < 5 s. `flake.get(project, catalog_entry_id)` p99 < 60 ms.
- **NFR-2 (Security):** Reads behind `flake.read`; quarantine mutations behind `flake.write`; un-quarantine behind `quarantine.clear`. Classification never reflects secrets. Ownership resolution through `6-test-catalog`.
- **NFR-3 (Observability):** Metrics `pychestrate_flake_classifications_total{project,class,classifier}` (counter), `pychestrate_flake_classify_duration_seconds{project,classifier}` (histogram), `pychestrate_flake_quarantined_count{project}` (gauge), `pychestrate_flake_retries_total{project,outcome}` (counter). Log events `pychestrate.flake.classified`, `pychestrate.flake.quarantined`, `pychestrate.flake.quarantine_cleared`, `pychestrate.flake.broken_alerted`. Trace spans `pychestrate.flake.ingest`, `pychestrate.flake.classify`, `pychestrate.flake.quarantine_decide`.
- **NFR-4 (Reliability):** An ingest crash partway through a run's test case list SHALL be re-playable idempotently — `(run_id, test_case_identity_sha256)` is the unique key. Classification SHALL NOT block the run completion pathway; it runs on a separate worker that can lag by minutes without losing events.

## Out of Scope

- Result parsing (see `5-result-ingest-watcher`).
- Bug linking (see `6-triage-bug-linking`).
- Cross-run diff (see `6-compare-runs`).
- Runtime re-sharding (see `6-matrix-sharding`).

## Dependencies

- **Depends on:** `6-test-orchestration`, `6-test-catalog`, `5-result-ingest-watcher`, `0-persistence`, `0-message-bus`, `1-rbac`, `2-notification-hub`, `E-extension-host`.
- **Depended on by:** `6-pipeline-definition`, `6-triage-bug-linking`, `7-test-metrics`, `6-matrix-sharding` (`WeightedByHistoryStrategy`).
- **Extension points exposed:** `factory: flake_classifier` — default windowed classifier plus statistical/Bayesian variants.
