# 6-pipeline-definition — Requirements

## Introduction

The `6-pipeline-definition` feature is Pychestrate's pipeline-as-code
surface: YAML/JSON pipeline documents stored in each project's source
repository, parsed into a typed DAG, rendered in the UI, and executed
as sequences of `build`, `infra`, and `test` jobs — all dispatched
through the existing Layer 5 plane. The feature ships in **Phase 6**
with `6-source-integrations`, `6-build-orchestration`, and
`6-build-artifacts`. It sits between `6-source-integrations` (webhook
→ pipeline run trigger) and every job-type orchestrator
(`6-build-orchestration`, `6-infra-orchestration`, `6-test-orchestration`).
Step kinds are extensible via `PipelineStepKindExtension`. Pipeline
documents are always source-controlled and versioned; Pychestrate never
owns the authoritative copy.

## Requirements

### Requirement 1: Typed DAG Parsed From Source-Controlled YAML/JSON

**User Story:** As a pipeline author, I want to declare my pipeline in
a version-controlled YAML file, so that the pipeline evolves with the
code it ships.

**Acceptance Criteria (EARS):**

1. WHEN `pipelines.load_from_source(project_id, commit_sha, doc_bytes, doc_filename)` is called THEN the system SHALL parse the document via `yaml.safe_load` (for `.yaml|.yml`) or `json.loads` (for `.json`), validate against the `pipeline.schema.v1.json`, and return a `PipelineDocument` with a typed DAG.
2. IF the document references a step kind not registered via `PipelineStepKindExtension` THEN the system SHALL raise `SemanticError` listing the missing kind and the declaring file path/line.
3. WHEN the DAG contains a cycle THEN the system SHALL raise `SemanticError` naming the cycle edges.
4. WHERE a stage declares a `matrix` THEN the system SHALL validate every dimension has at least one value AND SHALL delegate expansion to `6-matrix-sharding` at execution time.
5. WHEN parse succeeds THEN the system SHALL compute `pipeline_digest_sha256 = sha256(canonical_json(document))` and persist `(project_id, commit_sha, filename)` → `pipeline_digest_sha256` for audit and replay.

### Requirement 2: Execute A Pipeline Run Through Layer 5

**User Story:** As a project owner, I want a pipeline run to dispatch
each stage's jobs to the correct pod client via Layer 5, so that I do
not operate multiple dispatch paths.

**Acceptance Criteria (EARS):**

1. WHEN `pipelines.trigger_run(project_id, commit_sha, ref, document, trigger_cause)` is called AND RBAC `pipeline.run.trigger` passes THEN the system SHALL create a `PipelineRun` entity with state `pending` AND transition to `running` on dispatch of the first stage.
2. WHEN a stage executes THEN for each declared step the system SHALL route `build|infra|test` kinds to `6-build-orchestration`, `6-infra-orchestration`, `6-test-orchestration` respectively AND use their existing Layer 5 dispatch paths WITHOUT introducing a new dispatch path.
3. IF a stage declares `when: succeeded|failed|always` conditionals THEN the system SHALL honor them against the aggregate outcome of prior stages AND SHALL skip the stage with state `skipped` when the guard is false.
4. WHILE a stage is running THEN the system SHALL emit `entity.pipeline.stage.started|completed` events with stage index, id, and aggregate status.
5. WHERE a matrix expansion produces N shards THEN the system SHALL dispatch via `6-matrix-sharding` AND finalize the stage only when the `ShardSet.state` is terminal.

### Requirement 3: Step Kind Extension Surface

**User Story:** As an extension author, I want to register a reusable
step kind (e.g., `containerize`, `sign-artifact`), so that pipeline
authors can reference it without inline scripts.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers a `PipelineStepKindExtension` subclass THEN the system SHALL verify it declares `kind_name: str`, `input_schema: dict`, `produce_jobs(project_id, run_id, stage_spec, aspects)` classmethod AND raise `ConfigurationError` naming missing members.
2. WHEN a pipeline document uses `- uses: <kind_name>` THEN the system SHALL validate the step's inputs against the kind's JSON schema AND raise `SemanticError` listing schema errors.
3. WHERE multiple extensions register the same `kind_name` THEN the system SHALL use the lowest `PRECEDENCE` AND SHALL raise `ConfigurationError` at load time if two kinds share both `kind_name` and `PRECEDENCE`.
4. WHEN an in-tree step kind (`build`, `test`, `infra`, `script`, `artifact-promote`) is referenced THEN the system SHALL NOT require `uses:` — they are first-class shortcuts.

## Property-Based Test Requirements

### Property 1: Canonical Digest Is Stable Across Equivalent Representations

- **Invariant:** For any pipeline document, two semantically equivalent YAML/JSON serializations (different key order, quoting, comment presence) produce the same `pipeline_digest_sha256`.
- **Generator:** Compose a `hypothesis.strategies.recursive` pipeline-AST strategy; emit two different serializations per AST (reordered keys, flow-vs-block style, quoted vs bare scalars).
- **Assertion:** `sha256(canonical_json(parse(ser1))) == sha256(canonical_json(parse(ser2)))`.
- **Sample size:** 1000 generated cases

### Property 2: Reassembly Order Within A Parallel Stage

- **Invariant:** For any pipeline DAG with M stages and K parallel groups per stage, the aggregate stage outcome report preserves the declared order of parallel groups and the lexicographic order within a group (mirrors `6-matrix-sharding` Property 2 at the pipeline-run granularity).
- **Generator:** A DAG strategy with `integers(1, 5)` stages each with `integers(1, 4)` parallel groups; each group has `integers(1, 10)` members whose completion times are randomized.
- **Assertion:** `aggregate.stages[i].groups[j].members` is ordered lexicographically by member id regardless of completion timestamp.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `load_from_source` parse+validate p99 < 150 ms for documents up to 1 MiB. Pipeline-run triggering (decision + first dispatch) p99 < 800 ms. Stage decision evaluation p99 < 30 ms. DAG renderer payload generation p99 < 250 ms for 500-step pipelines.
- **NFR-2 (Security):** Only `pipeline.run.trigger` principals can trigger; `pipeline.definition.edit` principals can write overrides. Document variables resolved through `2-global-variables` with secret dereferencing; resolved values never stored on the `PipelineRun` — only refs. `uses:` step kinds gated by the capability manifest of their extension via `E-extension-sandbox` when available (Phase 8).
- **NFR-3 (Observability):** Metrics `pychestrate_pipeline_parse_duration_seconds{project}` (histogram), `pychestrate_pipeline_runs_total{project,final_state}` (counter), `pychestrate_pipeline_stage_duration_seconds{project,stage_id}` (histogram), `pychestrate_pipeline_steps_in_flight{project}` (gauge), `pychestrate_pipeline_validation_failures_total{project,error_kind}` (counter). Log events `pychestrate.pipeline.defined`, `pychestrate.pipeline.run_started`, `pychestrate.pipeline.run_completed`, `pychestrate.pipeline.stage_skipped`, `pychestrate.pipeline.validation_failed`. Trace spans `pychestrate.pipeline.parse`, `pychestrate.pipeline.trigger`, `pychestrate.pipeline.stage`, `pychestrate.pipeline.step`.
- **NFR-4 (Reliability):** A pipeline document whose parsing fails at runtime (imported at trigger time) SHALL NOT abort the webhook pipeline — the `PipelineRun` is persisted with state `rejected` and a structured error. A stage crash SHALL NOT affect another concurrent stage of the same run — stages are isolated at the ShardSet/dispatch boundary.

## Out of Scope

- The actual execution of build/infra/test jobs (delegated to the respective orchestrators).
- Matrix fan-out mechanics (see `6-matrix-sharding`).
- Webhook parsing (see `6-source-integrations`).
- DAG-rendering WebComponent (see `9-wc-pipeline-dag`).

## Dependencies

- **Depends on:** `6-source-integrations`, `6-build-orchestration`, `6-infra-orchestration`, `6-test-orchestration`, `6-matrix-sharding`, `5-job-dispatch`, `2-global-variables`, `0-persistence`, `0-message-bus`, `1-rbac`, `1-audit-log`, `E-extension-host`.
- **Depended on by:** `9-wc-pipeline-dag`, `7-orchestration-metrics`, `6-source-integrations` (for status posting).
- **Extension points exposed:** `resource: PipelineStepKindExtension` — `containerize`, `sign-artifact`, `deploy`, `k8s-apply`, custom.
