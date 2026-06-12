# 6-compare-runs — Tasks

## Milestones

- **M1 — Skeleton:** `compare_report` schema + `diff_engine` for per-test outcomes + REST build/fetch endpoints + `PxGenericTwoPaneDiffViewer`.
- **M2 — Core Behavior:** Log-excerpt pair, diff viewer registry + in-tree viewers, caching, event emission, paginated fetch.
- **M3 — Hardening:** Property tests, metrics/logs/traces, perf benchmarks, TTL/cleanup, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/ccai/pychestrate/webservice/orchestration/test/compare/` package per design.md.
- [ ] T1.2 — Add `0-persistence` migration for `compare_report` with unique `(base_run_id, candidate_run_id)`.
- [ ] T1.3 — Implement `diff_engine.py` per-test diff algebra producing `list[TestDiff]`.
- [ ] T1.4 — Implement `service.py::CompareRunsService.build` persisting the row and running the diff inline for M1.
- [ ] T1.5 — Register REST `POST /api/v1/projects/{id}/compare` and `GET /api/v1/projects/{id}/compare/{report_id}`.
- [ ] T1.6 — Implement `PxGenericTwoPaneDiffViewer` under `source/site/ccai/extensions/pychestrate/artifact_diff_viewer/generic_two_pane.py`.
- [ ] T1.7 — Implement `viewer_protocol.py::ArtifactDiffViewerExtension` base.

### M2 — Core Behavior

- [ ] T2.1 — Move build work to a worker so request returns `CompareReportRef` immediately.
- [ ] T2.2 — Serialize `list[TestDiff]` to `0-object-store` under `per_test_blob_key`; stream back on fetch.
- [ ] T2.3 — Implement `log_excerpt.py` producing up to `max_log_context_lines` around first-diff; byte-offset + signed-URL fallback when log > `max_log_bytes`.
- [ ] T2.4 — Implement `viewer_registry.py` accessor; subscribe to `extension.reloaded`.
- [ ] T2.5 — Ship in-tree viewers: `PxTextLineDiffViewer`, `PxImageDiffViewer`, `PxFlamegraphDiffViewer`, `PxPcapDiffViewer`.
- [ ] T2.6 — Implement `select_artifact_diff_viewer` and route `GET /.../compare/{id}/artifacts/{path}:diff-viewer`.
- [ ] T2.7 — Emit `entity.compare.built`, `entity.compare.baseline_updated`, `entity.compare.viewer_selected`.
- [ ] T2.8 — Warnings for `runtime_env_mismatch` surfaced in report top-level.

### M3 — Hardening

- [ ] T3.1 — Emit Prometheus metrics and OTel spans per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: 5 000-test compare p99 < 2 s; log-excerpt p99 < 300 ms; viewer lookup p99 < 20 ms; cache hit p99 < 80 ms. Fail CI on regression.
- [ ] T3.3 — Implement expiration sweep for `compare_report` older than `compare_report_ttl_hours` (default 72); purge blob + row.
- [ ] T3.4 — Cross-project block: attempting to compare runs from different projects returns 403 with audit entry.
- [ ] T3.5 — Sphinx docs for REST endpoints, `CompareRunsService` internal API, and viewer authoring guide.
- [ ] T3.6 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.7 — Fallback to generic viewer when an extension's `matches()` raises.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (symmetric reverse) and Property 2 (determinism) at 1000 cases each.
- [ ] TT-3 — Integration test: run A (5 pass, 2 fail) vs run B (6 pass, 1 fail); `per_test` reports one `fixed`, one `regressed`, five `unchanged`; UI viewer dispatch returns the PxTextLineDiffViewer for log artifacts.
- [ ] TT-4 — Extension-point test: test-only `FakeDiffViewer` (`PRECEDENCE = 1`) wins for a mocked classifier tag.
- [ ] TT-5 — Missing-log test: run B missing the log for a regressed test; response includes `LogExcerptPair.candidate == "absent"`.
- [ ] TT-6 — Cache-hit test: two consecutive builds of the same run pair return the same `report_id` and the second build returns within the cache-hit SLO.
- [ ] TT-7 — Cross-project test: runs in different projects rejected with 403.

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
