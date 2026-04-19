# 7-orchestration-metrics — Tasks

## Milestones

- **M1 — Skeleton:** Lead-time, stage-duration, and result metrics; resolver on run/stage completion; first end-to-end emit.
- **M2 — Core Behavior:** Retry/cancel counters with enum validation; parallel efficiency computation + metric; label sanitization.
- **M3 — Hardening:** DAG guardrails, self-metrics/logs/traces, perf benchmarks, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/metrics/domains/orchestration/` package per design.md.
- [ ] T1.2 — Implement `PipelineLeadTimeMetric`, `PipelineStageDurationMetric`, `PipelineResultMetric` under `source/site/automojo/extensions/pychestrate/metric_definition/orchestration/`.
- [ ] T1.3 — Implement `resolver.py::OrchestrationMetricResolver.on_pipeline_run_completed` + `on_stage_completed`.
- [ ] T1.4 — Wire subscriptions `entity.pipeline.run_completed` and `entity.pipeline.stage_completed`.
- [ ] T1.5 — Verify end-to-end: synthetic run of 3 stages populates all three metrics.

### M2 — Core Behavior

- [ ] T2.1 — Implement `PipelineRetryMetric` counter and `resolver.on_run_retried`; enum validation against `retry_reason` allow-list.
- [ ] T2.2 — Implement `PipelineCancelMetric` counter and `resolver.on_run_cancelled`; enum validation against `cancel_source`.
- [ ] T2.3 — Implement `longest_path.py::compute_critical_path_seconds` with topological sort and cycle detection.
- [ ] T2.4 — Implement `efficiency.py::compute_parallel_efficiency` with clamp-to-`1.0` for inverted inputs.
- [ ] T2.5 — Implement `PipelineParallelEfficiencyMetric` and emit from `on_pipeline_run_completed` when `stage_timeline` is present.
- [ ] T2.6 — Implement `labels.py::sanitize_label_value` per design contract.
- [ ] T2.7 — Wire `entity.run.retried` and `entity.run.cancelled` subscriptions.
- [ ] T2.8 — Drop sample + log `pychestrate.orchestration_metrics.invalid_enum` on enum failures; drop + log `pychestrate.orchestration_metrics.parallel_efficiency_inverted` on inverted DAG.

### M3 — Hardening

- [ ] T3.1 — Enforce `max_stages_per_run` (default 500) — skip efficiency + log `pychestrate.orchestration_metrics.dag_oversized`.
- [ ] T3.2 — Emit self-metrics `pychestrate_orchestration_metrics_emit_duration_seconds`, `pychestrate_orchestration_metrics_invalid_enum_total`, `pychestrate_orchestration_metrics_critical_path_duration_seconds`.
- [ ] T3.3 — Emit OTel spans per design.md Observability.
- [ ] T3.4 — Benchmark NFR-1: per-event emit p99 < 5 ms; 50-stage longest path p99 < 8 ms.
- [ ] T3.5 — Sphinx docs for the orchestration metric catalog.
- [ ] T3.6 — Golden test: build 10 shaped DAGs and verify critical-path answers match hand-calculated values.
- [ ] T3.7 — Handle missing `stage_timeline` by skipping efficiency without blocking lead-time emit.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (efficiency in range), Property 2 (serial lead time ≈ sum of durations), Property 3 (retry counter monotonicity) at 1000 cases each.
- [ ] TT-3 — Integration test: drive `6-pipeline-definition` through a fan-out-then-join pipeline; assert `parallel_efficiency < 1.0` and equal to `critical_path / total`.
- [ ] TT-4 — Extension-point test: test-only `MetricDefinitionExtension` adds `pychestrate_pipeline_custom_total`; registers and emits alongside built-ins.
- [ ] TT-5 — Enum-validation test: retry with `reason="bogus"` drops sample, emits invalid-enum counter, bus processing continues.
- [ ] TT-6 — DAG cycle test: synthetic pipeline with A→B→A raises `SemanticError` at `compute_critical_path_seconds`.
- [ ] TT-7 — Cancel cascade test: parent run cancel emits `source=cascade` child counters for each descendant run.

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
