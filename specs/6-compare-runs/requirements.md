# 6-compare-runs — Requirements

## Introduction

The `6-compare-runs` feature produces a side-by-side diff between two
(or more) completed runs: per-test outcomes, log excerpts, artifact
trees, and key artifacts through pluggable
`ArtifactDiffViewerExtension` WebComponents. It gives users a one-click
"what changed?" view used during regression triage and release gating.
Ships in **Phase 5** with the other polish features. Sits between
`5-result-ingest-watcher` / `6-artifact-browser` (data sources) and
`9-run-detail-ui` (presentation). Authoritative source of truth for the
compared content is the runs themselves; this feature owns the *diff
projection* — it does not rewrite run data.

## Requirements

### Requirement 1: Compare Two Runs On Test Outcomes

**User Story:** As a release gatekeeper, I want to see which tests
changed state between run A and run B, so that I can decide whether to
cut the release.

**Acceptance Criteria (EARS):**

1. WHEN `compare.build(project_id, base_run_id, candidate_run_id)` is called AND the caller has `run.compare` THEN the system SHALL return a `CompareReport` with `per_test: list[TestDiff]` where each `TestDiff` has `{test_case_identity_sha256, base_outcome, candidate_outcome, status: "unchanged" | "fixed" | "regressed" | "new" | "removed"}`.
2. IF either run is not in a terminal state THEN the system SHALL raise `SemanticError` naming the incomplete run.
3. WHEN both runs are terminal AND share a `catalog_entry_scope` THEN the system SHALL restrict comparison to the intersection of catalog entries scheduled in both runs AND SHALL surface entries present in one run only in `per_test` as `new`/`removed`.
4. WHERE `runtime_env_digest` differs between runs THEN the system SHALL include a top-level `warnings: ["runtime_env_mismatch"]` entry but SHALL still produce the diff.

### Requirement 2: Artifact Diff Through Registered Viewers

**User Story:** As a user comparing a failing run to a passing run, I
want to see the diff of two `flamegraph.svg` artifacts in a viewer
designed for that type, so that I can see which code paths changed.

**Acceptance Criteria (EARS):**

1. WHEN `compare.select_artifact_diff_viewer(entry_a, entry_b)` is called THEN the system SHALL consult registered `ArtifactDiffViewerExtension` in `PRECEDENCE` order AND return the first viewer whose `matches(entry_a, entry_b)` returns True.
2. IF no viewer matches THEN the system SHALL return `GenericTwoPaneDiffViewer` whose WebComponent is `<px-generic-two-pane-diff>`.
3. WHERE an artifact has a registered `ArtifactTypeExtension` classification THEN the diff viewer lookup SHALL prefer viewers that declare support for that classification.

### Requirement 3: Log Excerpt Diff Around Failures

**User Story:** As a user, I want the compare page to surface the
relevant log excerpt around the first difference, so that I do not
have to scroll through megabytes of logs.

**Acceptance Criteria (EARS):**

1. WHEN a `TestDiff.status` is `regressed` OR `fixed` THEN the system SHALL attach `log_excerpt: LogExcerptPair` containing up to `max_log_context_lines` (default 50) lines around the first differing line from each run.
2. IF a log is missing for one side THEN the system SHALL return an `absent` marker for that side rather than omitting the field.
3. WHEN the log is larger than `max_log_bytes` (default 4 MiB) THEN the system SHALL fall back to a streaming window locator and return a signed-URL anchor with the byte offset.

## Property-Based Test Requirements

### Property 1: Symmetric Reverse Of Compare Swaps Fixed/Regressed

- **Invariant:** For any two completed runs A and B, `compare(A, B)` and `compare(B, A)` produce reports where every `TestDiff` status is reversed in the declared reflection table: `unchanged <-> unchanged`, `fixed <-> regressed`, `new <-> removed`.
- **Generator:** `hypothesis.strategies.lists(tuples(sampled_from(Outcome), sampled_from(Outcome)), min_size=0, max_size=200)` as the paired outcomes per test.
- **Assertion:** For every `test_id`, `reflect(compare(A,B)[test_id].status) == compare(B,A)[test_id].status`.
- **Sample size:** 1000 generated cases

### Property 2: Compare Is Deterministic

- **Invariant:** For any two runs, two consecutive `compare.build(A, B)` calls produce byte-identical serialized reports (excluding `computed_at` timestamp).
- **Generator:** `hypothesis.strategies.tuples(uuids(), uuids())` paired with a seeded run state fixture.
- **Assertion:** `serialize(report1).replace(ts1, "*") == serialize(report2).replace(ts2, "*")`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `compare.build` p99 < 2 s for two runs with 5 000 tests each. Log-excerpt window fetch p99 < 300 ms. Diff-viewer lookup p99 < 20 ms. Cached reports served p99 < 80 ms.
- **NFR-2 (Security):** `run.compare` permission required on the project. Cross-project compares explicitly blocked (`runs_in_same_project` check). Reports stored with a TTL (`compare_report_ttl_hours`, default 72) and are not reachable by URL without RBAC re-check.
- **NFR-3 (Observability):** Metrics `pychestrate_test_compare_build_duration_seconds{project}` (histogram), `pychestrate_test_compare_diff_count{project,status}` (counter), `pychestrate_test_compare_viewer_dispatch_total{project,viewer}` (counter), `pychestrate_test_compare_cache_hits_total{project}` (counter). Log events `pychestrate.test.compare.built`, `pychestrate.test.compare.viewer_selected`, `pychestrate.test.compare.denied`. Trace spans `pychestrate.test.compare.build`, `pychestrate.test.compare.log_excerpt`, `pychestrate.test.compare.viewer_select`.
- **NFR-4 (Reliability):** A `compare.build` that encounters a missing log SHALL still produce a full `per_test` diff; logs degrade to `absent` markers. Diff-viewer extension failures SHALL NOT prevent the base report from rendering — the viewer falls back to the generic two-pane.

## Out of Scope

- Artifact rendering for single runs (see `6-artifact-browser`).
- Flake/triage classification (see `6-flake-tracking`, `6-triage-bug-linking`).
- Performance regression detection as a numeric domain (covered by `7-test-metrics`).

## Dependencies

- **Depends on:** `6-test-orchestration`, `6-flake-tracking`, `5-result-ingest-watcher`, `5-artifact-store`, `0-object-store`, `6-artifact-browser`, `1-rbac`, `E-extension-host`.
- **Depended on by:** `6-triage-bug-linking`, `9-run-detail-ui`.
- **Extension points exposed:** `resource: ArtifactDiffViewerExtension` — generic two-pane, image-diff, text-line-diff, flamegraph-diff, PCAP-diff, custom.
