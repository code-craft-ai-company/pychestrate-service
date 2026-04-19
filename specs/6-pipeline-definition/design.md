# 6-pipeline-definition — Design

## Architecture

`6-pipeline-definition` owns the pipeline document model, the parser,
the execution DAG walker, and the stage-level decision logic. It does
not own a new dispatcher — every step becomes a `build` / `infra` /
`test` job routed to the respective orchestrator which uses Layer 5.
Pipeline documents are authoritative in the user's source repo; this
feature stores *references* (project, commit, filename, digest) plus
cached derived state (`PipelineRun`, `PipelineStageRun`). Step kinds
beyond the built-ins come through the `PipelineStepKindExtension`
resource. The feature ships in Phase 6 and is consumed by
`9-wc-pipeline-dag` for rendering, by `6-source-integrations` for
trigger + commit-status posting, and by `7-orchestration-metrics` for
cycle-time analytics.

## Data Model

Tables in `0-persistence`:

- `pipeline_run`:
  - `run_id: UUID` PK
  - `project_id: UUID`
  - `commit_sha: str`
  - `ref: str`
  - `filename: str`
  - `pipeline_digest_sha256: str`
  - `state: PipelineRunState` — `{pending, running, completed, failed, cancelled, rejected}`
  - `trigger_cause: TriggerCause`
  - `started_at: datetime | None`
  - `finished_at: datetime | None`
- `pipeline_stage_run`:
  - `stage_run_id: UUID` PK
  - `run_id: UUID`
  - `stage_id: str` — matches document declaration
  - `stage_index: int`
  - `state: StageState` — `{pending, running, skipped, completed, failed, cancelled}`
  - `when_clause_resolved: str`
  - `shard_set_id: UUID | None` — bound if the stage used a matrix.
  - `started_at, finished_at, final_state_reason`
- `pipeline_step_run`:
  - `step_run_id: UUID` PK
  - `stage_run_id: UUID`
  - `step_id: str`
  - `kind_name: str`
  - `job_kind: "build" | "infra" | "test"`
  - `layer5_run_id: UUID | None`
  - `state: StepState`
  - `started_at, finished_at, attempt: int`
- `pipeline_document_cache`:
  - `(project_id, commit_sha, filename)` PK
  - `pipeline_digest_sha256`
  - `canonical_json_blob_key`
  - `cached_at`

Indices: `(project_id, state)`, `(commit_sha, filename)`, `(pipeline_digest_sha256)`.

Value types:

- `PipelineDocument` — typed AST.
- `StageSpec`, `StepSpec`, `MatrixSpec` (shared with `6-matrix-sharding`).

## Interfaces

### Public API

REST under `8-rest-api-v1`:

- `POST /api/v1/projects/{project_id}/pipelines:trigger` body `{commit_sha, ref, filename, document_bytes}` → `PipelineRunRef`.
- `GET /api/v1/projects/{project_id}/pipeline-runs/{run_id}` → `PipelineRunView` (includes full DAG and stage state).
- `POST /api/v1/projects/{project_id}/pipeline-runs/{run_id}:cancel`.
- `GET /api/v1/projects/{project_id}/pipelines/validate` body `{document_bytes}` → `ValidationResult` (for editor linting).

WebComponent: `<px-pipeline-dag pipeline-run-id="...">` consumes the `PipelineRunView` and renders the DAG.

### Internal API

```python
class PipelineService:
    def __init__(
        self,
        repo: PipelineRepository,
        parser: PipelineParser,
        step_kind_registry: StepKindRegistry,
        build_orch: BuildOrchestrator,
        infra_orch: InfraOrchestrator,
        test_orch: TestOrchestrator,
        sharding: MatrixShardingService,
        variable_resolver: VariableResolver,
        rbac: RbacService,
        audit: AuditLog,
        bus: MessageBus,
        clock: Clock,
        config: PipelineConfig
    ) -> None:
        self._repo = repo
        self._parser = parser
        self._step_kind_registry = step_kind_registry
        self._build_orch = build_orch
        self._infra_orch = infra_orch
        self._test_orch = test_orch
        self._sharding = sharding
        self._variable_resolver = variable_resolver
        self._rbac = rbac
        self._audit = audit
        self._bus = bus
        self._clock = clock
        self._config = config
        return

    def load_from_source(
        self,
        project_id: UUID,
        commit_sha: str,
        doc_bytes: bytes,
        doc_filename: str
    ) -> PipelineDocument:
        """
            Parse and validate a pipeline document.

            :returns: Typed PipelineDocument.
            :raises: SemanticError, ConfigurationError
        """
        ...

    def trigger_run(
        self,
        actor_id: UUID,
        project_id: UUID,
        commit_sha: str,
        ref: str,
        document: PipelineDocument,
        trigger_cause: TriggerCause,
        aspects: TriggerAspects | None = None
    ) -> PipelineRunRef:
        """
            Create a PipelineRun and begin executing the first stage.

            :returns: PipelineRunRef.
            :raises: AuthorizationError, SemanticError
        """
        ...

    def advance_run(
        self,
        run_id: UUID
    ) -> None:
        """
            Walk stage decisions and dispatch ready stages.

            :returns: None.
            :raises: SemanticError
        """
        ...

    def apply_child_job_terminal(
        self,
        step_run_id: UUID,
        final_state: RunState
    ) -> None:
        """
            Apply a downstream job's terminal state onto the step and
            cascade stage-level aggregation.

            :returns: None.
            :raises: SemanticError
        """
        ...
```

### Extension Surface

Resource extension declared here:

```python
class PipelineStepKindExtension(ResourceExtension):
    """
        Base class for reusable pipeline step kinds.
    """
    kind_name: str
    input_schema: dict  # JSON Schema

    @classmethod
    def produce_jobs(
        cls,
        project_id: UUID,
        run_id: UUID,
        stage_spec: StageSpec,
        step_spec: StepSpec,
        aspects: ProduceAspects
    ) -> list[JobProduction]:
        """
            Translate a step into one or more Layer 5 jobs grouped by kind.

            :returns: A list of JobProduction (kind + envelope request).
            :raises: SemanticError, ConfigurationError
        """
        ...
```

Reference kinds shipped in-tree under
`source/site/automojo/extensions/pychestrate/pipeline_step/`:

- `BuildStepKind` — `kind_name="build"`; produces a `build` Layer 5 job.
- `TestStepKind` — `kind_name="test"`.
- `InfraStepKind` — `kind_name="infra"`.
- `ScriptStepKind` — `kind_name="script"`; arbitrary script on the client under pod RBAC.
- `ArtifactPromoteStepKind` — `kind_name="artifact-promote"`; invokes `5-artifact-store.promote`.

Built-ins do not require `uses:` syntax; extension kinds do.

### Events Emitted

- `entity.pipeline.defined` — `{project_id, commit_sha, filename, pipeline_digest_sha256}`
- `entity.pipeline.run_started` — `{project_id, run_id, commit_sha, ref}`
- `entity.pipeline.run_completed` — `{run_id, final_state, duration_seconds}`
- `entity.pipeline.stage.started|completed|skipped` — `{run_id, stage_run_id, stage_id, state}`
- `entity.pipeline.step.dispatched` — `{step_run_id, job_kind, layer5_run_id}`
- `entity.pipeline.validation_failed` — `{project_id, commit_sha, filename, error_kind, details}`

### Events Consumed

- `entity.build.run_completed`, `entity.infra.run_completed`, `entity.test.run_completed` — drive step terminal transitions.
- `entity.shard_set.completed` — drive matrix-backed stage transitions.
- `extension.reloaded` — refresh step-kind registry.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/orchestration/pipelines/`:

- `__init__.py`
- `service.py` — `PipelineService`.
- `repository.py` — `PipelineRepository`.
- `parser.py` — YAML/JSON parser + `pipeline.schema.v1.json` validator.
- `canonicalization.py` — canonical JSON of the document.
- `dag.py` — DAG model, cycle detection, topological walker.
- `decisions.py` — stage `when:` clause evaluator.
- `step_kind_protocol.py` — `PipelineStepKindExtension`.
- `step_kind_registry.py` — extension-host accessor.
- `aspects.py` — `TriggerAspects`, `ProduceAspects`.
- `errors.py` — `ParseError`, `ValidationError` (both subclass `SemanticError`).
- `rest/v1_routes.py` — REST endpoints.

In-tree step-kind extensions live under
`source/site/automojo/extensions/pychestrate/pipeline_step/`.

Schema file shipped in-tree at
`source/site/automojo/pychestrate/webservice/orchestration/pipelines/schemas/pipeline.schema.v1.json`.

## Key Flows

### Flow 1 — Parse and validate

1. `load_from_source` called with `doc_bytes`.
2. Parser selects YAML/JSON by suffix; canonical AST built.
3. Schema validation via `jsonschema`; errors aggregated into `ValidationError` with line numbers.
4. `dag.build(...)` computes stage/step graph; cycle detection returns the smallest cycle or `None`.
5. `step_kind_registry` looked up per step; unknown kinds raise `SemanticError`.
6. Canonical JSON digest computed; `pipeline_document_cache` row upserted.

### Flow 2 — Trigger a run

1. `trigger_run` called (from REST or from `6-source-integrations`).
2. RBAC `pipeline.run.trigger`.
3. `PipelineRun` row inserted with `state = pending`.
4. `advance_run(run_id)` runs: identifies first stage(s) with no unmet deps.
5. For each ready stage, each step goes through `produce_jobs(...)` to get a `list[JobProduction]`.
6. Each production's kind routes to the right orchestrator:
   - `build` → `BuildOrchestrator.trigger_run`
   - `infra` → `InfraOrchestrator.trigger_run`
   - `test` → `TestOrchestrator.trigger_run`
7. `step_run.layer5_run_id` recorded.
8. If stage declares `matrix`, `MatrixShardingService.expand` is called and the stage binds to a `ShardSet`.

### Flow 3 — Stage completion cascade

1. Child job terminal events arrive on the bus.
2. `apply_child_job_terminal(step_run_id, final_state)` mirrors onto `pipeline_step_run`.
3. Once every step's step is terminal (and every ShardSet is terminal if bound), the stage completes.
4. `decisions.evaluate_when(next_stages, aggregate)` picks the next stages; skips others with `state = skipped`.
5. On pipeline completion, `entity.pipeline.run_completed` emitted; `6-source-integrations` posts commit status.

## Error Handling

- `SemanticError` for parse, schema, cycle, unknown kind: bubble; REST returns 400.
- `AuthorizationError`: 403.
- `ConfigurationError` for step-kind registry contract breakage: bubble; handler returns 500 and host quarantines.
- `rejected` pipeline runs (parse failed post-trigger) persisted with detailed error to support retries.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- Variable resolution centralized via `2-global-variables`; only resolved-at-dispatch. Document bytes themselves never contain secret values — only `${var}` references.
- Step-kind extensions' `produce_jobs` receives an `aspects` object that carries the scoped `SecretsAccessor`; extensions never read secrets directly from config files.
- Document size capped at `max_document_bytes` (default 1 MiB); parse timeouts at 2 s.
- Uses `yaml.safe_load` exclusively; `!!python/...` tags rejected.

## Observability

Metrics:

- `pychestrate_pipeline_parse_duration_seconds{project}` — histogram
- `pychestrate_pipeline_runs_total{project,final_state}` — counter
- `pychestrate_pipeline_stage_duration_seconds{project,stage_id}` — histogram
- `pychestrate_pipeline_steps_in_flight{project}` — gauge
- `pychestrate_pipeline_validation_failures_total{project,error_kind}` — counter
- `pychestrate_pipeline_rejected_total{project,error_kind}` — counter

Log events: `pychestrate.pipeline.defined`, `pychestrate.pipeline.run_started`, `pychestrate.pipeline.run_completed`, `pychestrate.pipeline.stage_skipped`, `pychestrate.pipeline.validation_failed`, `pychestrate.pipeline.rejected`.

Trace spans: `pychestrate.pipeline.parse`, `pychestrate.pipeline.trigger`, `pychestrate.pipeline.stage`, `pychestrate.pipeline.step`, `pychestrate.pipeline.advance_run`.

## Open Questions

- `when:` clause expression language — subset of CEL vs a closed-form string enum? Timebox: Phase 6 midpoint.
- Conditional fan-in ordering if multiple predecessors have different `when:` outcomes. Timebox: Phase 6 exit.
- Editor-side JSON Schema hosting (`GET /pipeline.schema.v1.json`) cacheability. Timebox: Phase 6 exit.
