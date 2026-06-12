# 6-pipeline-definition — Tasks

## Milestones

- **M1 — Skeleton:** Document schema + parser + DAG model + trigger + built-in step kinds (`build`, `test`, `script`) + minimal REST trigger endpoint.
- **M2 — Core Behavior:** Stage decisions (`when:`), matrix integration via `6-matrix-sharding`, step-kind extension protocol, cancel, event emission.
- **M3 — Hardening:** `infra` + `artifact-promote` built-ins, observability, property tests, perf benchmarks, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/ccai/pychestrate/webservice/orchestration/pipelines/` package per design.md.
- [ ] T1.2 — Ship `pipeline.schema.v1.json` under `schemas/` covering stages, steps, matrix, when, uses.
- [ ] T1.3 — Implement `parser.py` with safe YAML/JSON parsing and `jsonschema` validation; aggregate line-numbered errors.
- [ ] T1.4 — Implement `dag.py` with cycle detection (Tarjan) and topological walk.
- [ ] T1.5 — Implement `canonicalization.py` producing canonical JSON and SHA-256 digest.
- [ ] T1.6 — Add `0-persistence` migration for `pipeline_run`, `pipeline_stage_run`, `pipeline_step_run`, `pipeline_document_cache`.
- [ ] T1.7 — Implement built-in step kinds `BuildStepKind`, `TestStepKind`, `ScriptStepKind` under `source/site/ccai/extensions/pychestrate/pipeline_step/`.
- [ ] T1.8 — Implement `service.py::PipelineService.load_from_source` and `trigger_run` happy path; register `POST /api/v1/projects/{id}/pipelines:trigger`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `decisions.py` `when:` evaluator supporting `succeeded`, `failed`, `always`, plus variable refs.
- [ ] T2.2 — Wire matrix handling via `MatrixShardingService.expand` from stage executor.
- [ ] T2.3 — Implement `step_kind_protocol.py::PipelineStepKindExtension` and `step_kind_registry.py`; subscribe to `extension.reloaded`.
- [ ] T2.4 — Implement `apply_child_job_terminal` subscriber on `entity.build.run_completed`, `entity.infra.run_completed`, `entity.test.run_completed`, `entity.shard_set.completed`.
- [ ] T2.5 — Implement `POST /api/v1/projects/{id}/pipeline-runs/{run_id}:cancel` propagating through Layer 5 cancel.
- [ ] T2.6 — Register `GET /api/v1/projects/{id}/pipeline-runs/{run_id}` returning a full `PipelineRunView`.
- [ ] T2.7 — Register `GET /api/v1/projects/{id}/pipelines/validate` for editor linting.
- [ ] T2.8 — Emit `entity.pipeline.defined`, `entity.pipeline.run_started`, `entity.pipeline.run_completed`, `entity.pipeline.stage.*`, `entity.pipeline.step.dispatched`, `entity.pipeline.validation_failed`.

### M3 — Hardening

- [ ] T3.1 — Implement `InfraStepKind` and `ArtifactPromoteStepKind` built-ins.
- [ ] T3.2 — Emit Prometheus metrics and OTel spans per design.md Observability.
- [ ] T3.3 — Benchmark NFR-1: parse p99 < 150 ms at 1 MiB; trigger p99 < 800 ms; DAG renderer payload p99 < 250 ms at 500 steps. Fail CI on regression.
- [ ] T3.4 — Enforce `max_document_bytes` (default 1 MiB) with multiline error listing filename and size.
- [ ] T3.5 — Enforce parse timeout 2 s; raise `SemanticError` naming the timeout.
- [ ] T3.6 — Sphinx docs for REST, `PipelineService` internal API, and step-kind authoring guide.
- [ ] T3.7 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.8 — Subscribe to `extension.reloaded` and hot-refresh step-kind registry.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (digest stable across serializations) and Property 2 (stage parallel-group order preservation) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 6 scenario — PR opens → webhook triggers a pipeline with stages `build → test_matrix(os × python) → deploy` → all stages dispatch on the correct orchestrators → commit status posts back.
- [ ] TT-4 — Extension-point test: ship a test-only `ContainerizeStepKind` (`PRECEDENCE = 1`); verify `uses: containerize` resolves to it and produces a single build job.
- [ ] TT-5 — Validation test: a document with a cycle, an unknown kind, a missing matrix dimension — each produces `ValidationError` with the offending location.
- [ ] TT-6 — Cancel test: cancelling a running pipeline propagates through Layer 5 cancel to every in-flight step.
- [ ] TT-7 — Rejected test: a document that parses but fails schema at trigger time produces a `PipelineRun` with `state=rejected` and a structured error.

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
