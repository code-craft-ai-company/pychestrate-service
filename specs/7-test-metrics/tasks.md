# 7-test-metrics — Tasks

## Milestones

- **M1 — Skeleton:** `TestResultMetric`, `TestCaseDurationMetric`, resolver per-case path, `TestMetricResolver`, first end-to-end emit.
- **M2 — Core Behavior:** MTTR-to-green, flake-rate, coverage line ratio + delta, `CoverageArtifactTypeExtension`, slowest-top-N, coverage regression event.
- **M3 — Hardening:** Caching, clamp/warn handling, DLQ coverage parse failures, perf benchmarks, docs, self-metrics.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/metrics/domains/test/` package per design.md.
- [ ] T1.2 — Implement `TestResultMetric` (counter) and `TestCaseDurationMetric` (histogram) under `source/site/automojo/extensions/pychestrate/metric_definition/test/`.
- [ ] T1.3 — Implement `resolver.py::TestMetricResolver.on_test_case_completed` writing both metrics.
- [ ] T1.4 — Wire subscription `entity.run.test_case_completed` via `SubscriptionSpec`.
- [ ] T1.5 — Verify end-to-end: 10 synthetic case-completed events populate both metrics.

### M2 — Core Behavior

- [ ] T2.1 — Add `0-persistence` migration for `test_coverage_snapshot` and `test_suite_state`.
- [ ] T2.2 — Implement `TestMttrMetric` and `resolver.on_suite_completed` with fail→pass transition detection.
- [ ] T2.3 — Implement `TestFlakeRateMetric` and `resolver.on_flake_classified` consulting `6-flake-tracking`.
- [ ] T2.4 — Implement `CoverageArtifactTypeExtension`, `CoverageParserRegistry`, and `cobertura_v4.py` reference parser.
- [ ] T2.5 — Implement `TestCoverageLineRatioMetric` + `TestCoverageDeltaMetric` + `resolver.on_coverage_artifact`.
- [ ] T2.6 — Emit `entity.test.coverage.regressed` when delta < `-coverage_alert_drop_threshold` (default 0.02).
- [ ] T2.7 — Skip delta emit on `coverage_schema_version` mismatch; log `pychestrate.test_metrics.coverage_schema_mismatch`.
- [ ] T2.8 — Implement `slowest.py::SortedTopN` and `TestCaseSlowestMetric`; hash case names > 200 bytes.
- [ ] T2.9 — Wire subscriptions for `entity.run.suite_completed`, `entity.flake.classified`, `entity.build.artifact_published`.

### M3 — Hardening

- [ ] T3.1 — Implement `flake_rate_cache` with `flake_rate_cache_ttl_seconds` (default 300).
- [ ] T3.2 — Implement `clamp01` and wire coverage ratios through it with `pychestrate.test_metrics.coverage_out_of_range` log on clamp.
- [ ] T3.3 — Route `CoverageParseError` to `7-metrics-ingest` DLQ while preserving other per-run metric emits.
- [ ] T3.4 — Emit self-metrics `pychestrate_test_metrics_emit_duration_seconds`, `pychestrate_test_metrics_cache_hit_ratio`, `pychestrate_test_metrics_coverage_parse_errors_total`.
- [ ] T3.5 — Emit OTel spans per design.md Observability.
- [ ] T3.6 — Benchmark NFR-1: 5 000-case run ingest < 15 s; flake recompute p99 < 80 ms; coverage delta p99 < 120 ms.
- [ ] T3.7 — Sphinx docs for the test metric catalog + `CoverageArtifactTypeExtension` authoring guide.
- [ ] T3.8 — Enforce coverage artifact path validation against the run's artifact root.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (flake rate bounded), Property 2 (MTTR transition-only), Property 3 (coverage clamp) at 1000 cases each.
- [ ] TT-3 — Integration test: replay a real testbase result tree; assert every declared metric family populates.
- [ ] TT-4 — Extension-point test: test-only `CoverageArtifactTypeExtension` subclass with a synthetic schema v99 handles a sample artifact and produces matching samples.
- [ ] TT-5 — MTTR test: synthetic sequence `fail, fail, fail, pass` emits exactly one MTTR sample with value == `pass_at - first_fail_at`.
- [ ] TT-6 — Coverage schema mismatch: previous snapshot v3 + current v4 emits no delta but still emits current line ratio.
- [ ] TT-7 — Slowest-top-N: 10 000 generated durations leave exactly `slowest_top_n` entries emitted with unique `case` labels.

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
