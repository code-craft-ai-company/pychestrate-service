# 6-build-orchestration — Requirements

## Introduction

The `6-build-orchestration` feature dispatches build jobs onto pod client
agents via Layer 5 and tracks `BuildRun` entities with per-build
reproducibility metadata (input-digest, toolchain versions, environment
fingerprint). It is the build-domain peer of `6-test-orchestration` and
`6-infra-orchestration`. Ships in **Phase 6** with `6-pipeline-definition`,
`6-source-integrations`, and `6-build-artifacts`. It sits between the
pipeline layer (or a direct REST trigger) and Layer 5. A replay action
on an existing `BuildRun` dispatches a fresh run with the stored input
digest, enabling "build exactly the same thing again." Authoritative
source of truth for run lifecycles remains `5-run-state-machine`; this
feature owns the build-specific mirror and reproducibility tables.

## Requirements

### Requirement 1: Dispatch Build Jobs Through Layer 5

**User Story:** As a pipeline author, I want a `build` step to dispatch
to a selected pod client without a new dispatch pipeline, so that build
and test jobs share scheduling and RBAC paths.

**Acceptance Criteria (EARS):**

1. WHEN `build_orchestrator.trigger_run(project_id, actor_id, runner_kind, target_pod_id, inputs, trigger_cause)` is called AND RBAC `build.run.trigger` passes THEN the system SHALL persist a `BuildRun` with `state = pending`, a fresh `run_id`, and a captured `reproducibility_snapshot`; it SHALL dispatch via `5-job-dispatch` (no new dispatcher).
2. WHEN Layer 5 reports a terminal state THEN the system SHALL mirror it onto the `BuildRun` exactly as `6-test-orchestration` does, through the shared state-mirror pattern.
3. IF the runner kind is unknown THEN the system SHALL raise `SemanticError`.
4. WHERE the target pod lacks the advertised build capabilities declared by the runner's `capability_requirements` THEN the system SHALL raise `CapabilityMismatchError` before dispatch.
5. WHEN the run transitions to terminal THEN the system SHALL emit `entity.build.run_completed` with final state and `artifact_manifest_ref: str` (key under `5-artifact-store`).

### Requirement 2: Reproducibility Snapshot And Replay

**User Story:** As a release engineer, I want every build to record a
reproducibility snapshot and be replayable, so that I can re-run a
past build with identical inputs.

**Acceptance Criteria (EARS):**

1. WHEN a `BuildRun` is created THEN the system SHALL compute `reproducibility_snapshot = ReproSnapshot(input_digest_sha256, toolchain_versions, environment_fingerprint, variable_refs_digest)` AND persist it in the build_run row.
2. WHEN `build_orchestrator.replay(run_id)` is called THEN the system SHALL dispatch a new run with the same `reproducibility_snapshot.input_digest_sha256` AND SHALL mark the new run's `replay_of: UUID = <run_id>`.
3. IF any field referenced in the snapshot can no longer be resolved (e.g., a toolchain version was removed) THEN the system SHALL raise `ConfigurationError` listing the missing references.
4. WHERE an input file has a content hash mismatch vs the stored `input_digest_sha256` at replay time THEN the system SHALL raise `ReproducibilityError` with the list of diverging paths.

### Requirement 3: Build Runner Kind Factory Protocol

**User Story:** As an extension author, I want to register a new build
runner (e.g., for a yocto image pipeline) so that Pychestrate can
dispatch my builds without changes in-tree.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers a `BuildRunnerKindProtocol` implementation THEN the system SHALL verify `kind_name`, `build_job_envelope`, `validate_inputs`, `parse_progress_format_tag`, `parse_result_format_tag`, `capability_requirements`, `describe_toolchains` classmethods AND raise `ConfigurationError` naming missing members.
2. IF two implementations share `kind_name` and `PRECEDENCE` THEN the system SHALL raise `ConfigurationError` at load time.
3. WHEN `trigger_run` references `runner_kind` not registered THEN the system SHALL raise `SemanticError`.
4. WHERE `build_cache_backend` is configured THEN the system SHALL expose a scoped cache accessor to the runner via `BuildEnvelope.cache_scope` so that content-addressed intermediate artifacts speed up repeated builds.

### Requirement 4: Build Cache Backend Factory Protocol

**User Story:** As a build-infra owner, I want to plug in a site
build-cache (S3-compat bucket, sccache-style server) so that repeated
builds run faster.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers a `BuildCacheBackendProtocol` implementation THEN the system SHALL verify `backend_name`, `open`, `allocate_scope`, `capabilities` classmethods AND raise `ConfigurationError` naming missing members.
2. WHEN a build is dispatched THEN the system SHALL allocate a cache scope `(project_id, runner_kind, input_digest_sha256)` and include it in `BuildEnvelope.cache_scope`.
3. IF the backend is unavailable THEN the system SHALL degrade to `no_cache` mode with a WARNING log; builds SHALL NOT fail.

## Property-Based Test Requirements

### Property 1: Reproducibility Snapshot Is A Pure Function Of Inputs

- **Invariant:** For any fixed `(input_files, toolchain_versions, environment_fingerprint, variable_refs)`, `ReproSnapshot.compute(...)` yields the same `input_digest_sha256` and the same serialized snapshot string across invocations and machines.
- **Generator:** Compose `hypothesis.strategies.dictionaries` for toolchain versions and `hypothesis.strategies.lists(tuples(text(min_size=1, max_size=64), binary(max_size=1024)))` for input files; permute input order to assert order-independence.
- **Assertion:** `compute(inputs) == compute(inputs.shuffled())` and `compute(inputs).snapshot_json == compute(inputs).snapshot_json`.
- **Sample size:** 1000 generated cases

### Property 2: Replay Preserves Digest And Divergence Is Detected

- **Invariant:** For any build `B` with stored digest `d`, replay dispatched with the identical input set produces a run whose recomputed digest equals `d`; any single-byte change to any input file flips the digest and triggers `ReproducibilityError` at replay time.
- **Generator:** `hypothesis.strategies.lists(tuples(text(), binary(max_size=2048)), min_size=1, max_size=30)` for initial inputs plus `hypothesis.strategies.integers(min_value=0, max_value=N-1)` selecting a file to mutate.
- **Assertion:** `compute(original) == compute(original)` and `compute(mutated) != compute(original)` and replay of `B` with mutated inputs raises `ReproducibilityError`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `trigger_run` p99 < 180 ms; state-mirror update p99 < 25 ms; `replay(run_id)` p99 < 350 ms. Reproducibility digest compute p99 < 150 ms at 1 000 inputs / 50 MiB total.
- **NFR-2 (Security):** `build.run.trigger` gates trigger; `build.run.replay` gates replay. Toolchain/environment fingerprints never contain secret values — only names, versions, OS/arch, image digests. Cache scope writes audited by `1-audit-log`.
- **NFR-3 (Observability):** Metrics `pychestrate_build_runs_total{project,runner_kind,final_state}` (counter), `pychestrate_build_run_duration_seconds{project,runner_kind}` (histogram), `pychestrate_build_cache_hits_total{project,backend}` (counter), `pychestrate_build_cache_misses_total{project,backend}` (counter), `pychestrate_build_replays_total{project,outcome}` (counter), `pychestrate_build_reproducibility_errors_total{project}` (counter). Log events `pychestrate.build.run.triggered`, `pychestrate.build.run.completed`, `pychestrate.build.run.replayed`, `pychestrate.build.reproducibility.mismatch`. Trace spans `pychestrate.build.trigger`, `pychestrate.build.replay`, `pychestrate.build.compute_digest`.
- **NFR-4 (Reliability):** Cache backend outage SHALL degrade to no-cache without failing builds. State-mirror events arriving out of order SHALL be buffered and reapplied correctly, identical to the test-run pattern.

## Out of Scope

- Typed build outputs and promotion (see `6-build-artifacts`).
- Pipeline-level composition (see `6-pipeline-definition`).
- Webhook routing (see `6-source-integrations`).

## Dependencies

- **Depends on:** `5-job-envelope`, `5-job-dispatch`, `5-dispatch-receipt`, `5-run-state-machine`, `5-shared-results-backend`, `5-artifact-store`, `3-client-registry`, `3-client-capability-advertisement`, `0-persistence`, `0-message-bus`, `1-rbac`, `1-audit-log`, `2-projects`, `E-extension-host`.
- **Depended on by:** `6-pipeline-definition`, `6-build-artifacts`, `7-build-metrics`.
- **Extension points exposed:** `factory: build_runner_kind`; `factory: build_cache_backend`.
