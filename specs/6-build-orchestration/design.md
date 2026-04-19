# 6-build-orchestration — Design

## Architecture

`6-build-orchestration` is the build-domain orchestrator mirroring
`6-test-orchestration`. It owns `BuildRun` persistence, the reproducibility
snapshot, runner selection, and cache-scope allocation. Dispatch runs
through the existing Layer 5 plane — no new dispatcher. Replay is a
first-class verb: it re-dispatches a prior run with the stored input
digest. Ships in Phase 6 alongside `6-pipeline-definition`,
`6-source-integrations`, and `6-build-artifacts`. Authoritative source
of truth for run lifecycles is `5-run-state-machine`; this feature owns
the build-specific mirror plus reproducibility and cache-scope tables.

## Data Model

Tables in `0-persistence`:

- `build_run`:
  - `run_id: UUID` PK
  - `project_id: UUID`
  - `runner_kind: str`
  - `target_pod_id: UUID`
  - `state: BuildRunState`
  - `trigger_cause: TriggerCause`
  - `inputs_canonical_json: bytes`
  - `reproducibility_snapshot: ReproSnapshot` — JSON column with typed fields
  - `input_digest_sha256: bytes(32)` — denormalized for index scans
  - `replay_of: UUID | None`
  - `client_local_run_id: str | None`
  - `result_root_key: str | None`
  - `artifact_manifest_ref: str | None`
  - `cache_scope_key: str | None`
  - `started_at, finished_at`
- `build_toolchain_snapshot`:
  - `(run_id, toolchain_name) PK`
  - `version: str`
  - `digest: str | None`
- `build_cache_scope`:
  - `(project_id, runner_kind, input_digest_sha256) PK`
  - `backend_name: str`
  - `scope_key: str`
  - `allocated_at: datetime`
  - `bytes_written: int`
  - `hits: int`
  - `misses: int`

Indices: `(project_id, state)`, `(replay_of)`, `(input_digest_sha256)` on `build_run`.

Value types:

- `ReproSnapshot` — `{input_digest_sha256, toolchain_versions, environment_fingerprint, variable_refs_digest, snapshot_version}`.
- `BuildEnvelope` — Layer 5 envelope with `cache_scope` attached.
- `BuildRunView`.

## Interfaces

### Public API

REST under `8-rest-api-v1`:

- `POST /api/v1/projects/{project_id}/build-runs` — trigger.
- `GET /api/v1/projects/{project_id}/build-runs/{run_id}`.
- `POST /api/v1/projects/{project_id}/build-runs/{run_id}:cancel`.
- `POST /api/v1/projects/{project_id}/build-runs/{run_id}:replay` — replay.

### Internal API

```python
class BuildOrchestrator:
    def __init__(
        self,
        runs_repo: BuildRunRepository,
        dispatcher: JobDispatcher,
        envelope_builder: JobEnvelopeBuilder,
        shared_results: SharedResultsBackend,
        runner_registry: BuildRunnerRegistry,
        cache_backend_registry: BuildCacheBackendRegistry,
        variable_resolver: VariableResolver,
        rbac: RbacService,
        audit: AuditLog,
        bus: MessageBus,
        clock: Clock,
        config: BuildConfig
    ) -> None:
        self._runs_repo = runs_repo
        self._dispatcher = dispatcher
        self._envelope_builder = envelope_builder
        self._shared_results = shared_results
        self._runner_registry = runner_registry
        self._cache_backend_registry = cache_backend_registry
        self._variable_resolver = variable_resolver
        self._rbac = rbac
        self._audit = audit
        self._bus = bus
        self._clock = clock
        self._config = config
        return

    def trigger_run(
        self,
        actor_id: UUID,
        project_id: UUID,
        runner_kind: str,
        target_pod_id: UUID,
        inputs: BuildInputs,
        trigger_cause: TriggerCause,
        aspects: TriggerAspects | None = None
    ) -> BuildRunView:
        """
            Create a BuildRun, compute ReproSnapshot, dispatch via Layer 5.

            :returns: BuildRunView.
            :raises: AuthorizationError, CapabilityMismatchError, SemanticError
        """
        ...

    def cancel_run(
        self,
        actor_id: UUID,
        run_id: UUID,
        reason: str
    ) -> BuildRunView:
        """
            Request cancellation via 5-cancel-reconcile.

            :returns: Updated view.
            :raises: AuthorizationError, SemanticError
        """
        ...

    def replay(
        self,
        actor_id: UUID,
        run_id: UUID,
        aspects: ReplayAspects | None = None
    ) -> BuildRunView:
        """
            Dispatch a new run with the stored ReproSnapshot.

            :returns: New BuildRunView.
            :raises: AuthorizationError, ConfigurationError,
                     ReproducibilityError
        """
        ...

    def apply_layer5_state_event(
        self,
        run_id: UUID,
        event: RunStateEvent
    ) -> None:
        """
            Mirror a Layer 5 state transition onto the BuildRun.

            :returns: None.
            :raises: SemanticError
        """
        ...
```

### Extension Surface

Factory protocols declared here:

```python
class BuildRunnerKindProtocol(FactoryProtocolBase):
    factory_protocol_name: str = "build_runner_kind"

    @classmethod
    def kind_name(cls) -> str: ...

    @classmethod
    def build_job_envelope(
        cls,
        run_id: UUID,
        project_id: UUID,
        target_pod_id: UUID,
        inputs: BuildInputs,
        repro: ReproSnapshot,
        cache_scope: BuildCacheScope | None,
        result_root_key: str
    ) -> BuildEnvelope: ...

    @classmethod
    def validate_inputs(cls, inputs: BuildInputs) -> None: ...

    @classmethod
    def parse_progress_format_tag(cls) -> str: ...

    @classmethod
    def parse_result_format_tag(cls) -> str: ...

    @classmethod
    def capability_requirements(cls, inputs: BuildInputs) -> list[str]: ...

    @classmethod
    def describe_toolchains(cls, inputs: BuildInputs) -> dict[str, str]: ...


class BuildCacheBackendProtocol(FactoryProtocolBase):
    factory_protocol_name: str = "build_cache_backend"

    @classmethod
    def backend_name(cls) -> str: ...

    @classmethod
    def open(cls, config: CacheConfig, secrets: SecretsAccessor) -> BuildCacheBackend: ...

    @classmethod
    def allocate_scope(
        cls,
        backend: BuildCacheBackend,
        project_id: UUID,
        runner_kind: str,
        input_digest_sha256: bytes
    ) -> BuildCacheScope: ...

    @classmethod
    def capabilities(cls) -> CacheCapabilities: ...
```

Reference implementations under
`source/site/automojo/factories/pychestrate/build/`:

- `MakefileRunnerKind` — `PRECEDENCE = 1000`; executes a `make` invocation with `automojo-testbase`-compatible progress stream.
- `PoetryBuildRunnerKind` — `PRECEDENCE = 1000`; Python poetry builds.
- `DockerBuildRunnerKind` — `PRECEDENCE = 1000`; `docker build`.
- `FsBuildCacheBackend` — `PRECEDENCE = 1000`; local FS-backed cache (good for small sites).
- `S3BuildCacheBackend` — `PRECEDENCE = 500`; bucket-backed.

### Events Emitted

- `entity.build.run_started` — `{run_id, project_id, runner_kind, target_pod_id}`
- `entity.build.run_completed` — `{run_id, final_state, artifact_manifest_ref, started_at, finished_at}`
- `entity.build.run_replayed` — `{original_run_id, new_run_id, input_digest_sha256}`
- `entity.build.reproducibility.mismatch` — `{run_id, diverging_paths}`
- `entity.build.cache.allocated` — `{project_id, runner_kind, input_digest_sha256, backend_name}`

### Events Consumed

- `entity.run.state_changed|completed|failed|cancelled` — mirror onto BuildRun.
- `extension.reloaded` — refresh runner/backend registries.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/orchestration/build/`:

- `__init__.py`
- `orchestrator.py` — `BuildOrchestrator`.
- `repository.py` — `BuildRunRepository`.
- `repro_snapshot.py` — `ReproSnapshot.compute(...)`, canonical ordering, SHA-256.
- `runner_protocol.py` — `BuildRunnerKindProtocol`.
- `runner_registry.py`.
- `cache_protocol.py` — `BuildCacheBackendProtocol`.
- `cache_registry.py`.
- `state_mirror.py`.
- `aspects.py` — `TriggerAspects`, `ReplayAspects`.
- `errors.py` — `ReproducibilityError`, `CapabilityMismatchError`.
- `rest/v1_routes.py`.

Factories under `source/site/automojo/factories/pychestrate/build/`.

## Key Flows

### Flow 1 — Trigger a build

1. REST `POST /build-runs` → `BuildOrchestrator.trigger_run(...)`.
2. RBAC `build.run.trigger`.
3. Runner resolved; inputs validated; `describe_toolchains` captures versions.
4. `ReproSnapshot.compute(...)` → `input_digest_sha256` and embedded metadata.
5. Cache backend `allocate_scope(...)` — failure degrades to no-cache.
6. `BuildRun` row persisted; `result_root_key` allocated via `5-shared-results-backend`.
7. Envelope built via `BuildRunnerKindProtocol.build_job_envelope(...)`.
8. `JobDispatcher.dispatch(envelope)`; `client_local_run_id` stored.
9. `entity.build.run_started` emitted.

### Flow 2 — Replay

1. REST `POST /build-runs/{id}:replay` → `BuildOrchestrator.replay(...)`.
2. RBAC `build.run.replay`.
3. Original `BuildRun` row loaded; `ReproSnapshot` re-validated against current inputs.
4. Mismatch → `ReproducibilityError` with list of diverging paths.
5. New run dispatched with `replay_of = original_run_id`; same `input_digest_sha256`.
6. `entity.build.run_replayed` emitted.

### Flow 3 — Terminal mirroring

1. Layer 5 emits `entity.run.state_changed` / `completed` / `failed` / `cancelled`.
2. `state_mirror.apply(run_id, event)` updates `BuildRun`.
3. On terminal: `artifact_manifest_ref` resolved from `6-build-artifacts` → `entity.build.run_completed` emitted.

## Error Handling

- `SemanticError`: unknown runner, bad inputs → bubble (400).
- `AuthorizationError`: 403.
- `CapabilityMismatchError`: 409, multiline body listing required vs advertised.
- `ReproducibilityError`: 412 with list of diverging paths.
- `ConfigurationError`: 500; host quarantines the offending runner/backend.
- Cache backend native exceptions caught once, reclassified, and degraded to no-cache with WARNING.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- Toolchain versions and environment fingerprints never contain secret values — they are OS/arch/version strings only.
- Cache scope keys include `project_id`; a project cannot read another's cache.
- Inputs that reference secret variables dereferenced *on the client* via the runner, not by Pychestrate, so `inputs_canonical_json` never contains secret values.
- All triggers, replays, cancels audited via `1-audit-log`.

## Observability

Metrics:

- `pychestrate_build_runs_total{project,runner_kind,final_state}` — counter
- `pychestrate_build_run_duration_seconds{project,runner_kind}` — histogram
- `pychestrate_build_cache_hits_total{project,backend}` — counter
- `pychestrate_build_cache_misses_total{project,backend}` — counter
- `pychestrate_build_replays_total{project,outcome}` — counter
- `pychestrate_build_reproducibility_errors_total{project}` — counter
- `pychestrate_build_runs_in_flight{project,runner_kind}` — gauge

Log events: `pychestrate.build.run.triggered`, `pychestrate.build.run.completed`, `pychestrate.build.run.replayed`, `pychestrate.build.reproducibility.mismatch`, `pychestrate.build.cache.unavailable`.

Trace spans: `pychestrate.build.trigger`, `pychestrate.build.replay`, `pychestrate.build.compute_digest`, `pychestrate.build.state_mirror_update`.

## Open Questions

- Should environment fingerprint include kernel version and hostname? Timebox: Phase 6 midpoint.
- Per-runner cache-scope salting for security isolation vs cross-runner sharing. Timebox: Phase 6 exit.
- Replay semantics when the target pod is gone — dispatch to a capability-equivalent pod or fail? Timebox: Phase 6 exit.
