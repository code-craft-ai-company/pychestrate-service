# 6-build-orchestration — Tasks

## Milestones

- **M1 — Skeleton:** `build_run` schema + `MakefileRunnerKind` + `ReproSnapshot` computation + trigger + state mirror via Layer 5.
- **M2 — Core Behavior:** Replay, runner + cache registries, `PoetryBuildRunnerKind`, `DockerBuildRunnerKind`, `FsBuildCacheBackend`, cancel.
- **M3 — Hardening:** `S3BuildCacheBackend`, metrics/logs/traces, property tests, perf, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/orchestration/build/` package per design.md.
- [ ] T1.2 — Add `0-persistence` migration for `build_run`, `build_toolchain_snapshot`, `build_cache_scope`.
- [ ] T1.3 — Implement `repro_snapshot.py::ReproSnapshot.compute(...)` with canonical ordering and SHA-256 over file paths + content hashes + toolchain versions + environment fingerprint.
- [ ] T1.4 — Implement `runner_protocol.py::BuildRunnerKindProtocol`.
- [ ] T1.5 — Implement `MakefileRunnerKind` at `source/site/automojo/factories/pychestrate/build/makefile.py` with `PRECEDENCE = 1000`.
- [ ] T1.6 — Implement `orchestrator.py::BuildOrchestrator.trigger_run` happy path wiring to `5-job-dispatch` with no cache.
- [ ] T1.7 — Register `POST /api/v1/projects/{id}/build-runs` and `GET /api/v1/projects/{id}/build-runs/{run_id}`.
- [ ] T1.8 — Subscribe to `entity.run.state_changed|completed|failed|cancelled` and mirror onto `BuildRun`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `cache_protocol.py::BuildCacheBackendProtocol`.
- [ ] T2.2 — Implement `FsBuildCacheBackend` at `source/site/automojo/factories/pychestrate/build/fs_cache.py` with `PRECEDENCE = 1000`.
- [ ] T2.3 — Implement `cache_registry.py` and cache-scope allocation path in `trigger_run`.
- [ ] T2.4 — Implement `PoetryBuildRunnerKind` and `DockerBuildRunnerKind`.
- [ ] T2.5 — Implement `replay` endpoint `POST /.../build-runs/{id}:replay` with `ReproducibilityError` handling.
- [ ] T2.6 — Implement `cancel_run` and `POST /.../build-runs/{id}:cancel`.
- [ ] T2.7 — Emit `entity.build.run_started`, `entity.build.run_completed`, `entity.build.run_replayed`, `entity.build.reproducibility.mismatch`, `entity.build.cache.allocated`.
- [ ] T2.8 — Implement `runner_registry.py` and `cache_registry.py` accessors; subscribe to `extension.reloaded`.

### M3 — Hardening

- [ ] T3.1 — Implement `S3BuildCacheBackend` at `source/site/automojo/factories/pychestrate/build/s3_cache.py` with `PRECEDENCE = 500`.
- [ ] T3.2 — Emit Prometheus metrics and OTel spans per design.md Observability.
- [ ] T3.3 — Benchmark NFR-1: trigger p99 < 180 ms; state mirror p99 < 25 ms; replay p99 < 350 ms; digest compute p99 < 150 ms at 1 000 inputs / 50 MiB. Fail CI on regression.
- [ ] T3.4 — Enforce `capability_requirements` mismatch handling with multiline error body.
- [ ] T3.5 — Sphinx docs for REST, internal API, runner authoring, cache-backend authoring.
- [ ] T3.6 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.7 — Cache outage degrades to no-cache with WARNING log; build proceeds.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (pure digest) and Property 2 (replay fidelity) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 6 scenario — PR triggers a build via `6-pipeline-definition`; build dispatches to a synthetic pod, artifact manifest is produced, `entity.build.run_completed` carries `artifact_manifest_ref`.
- [ ] TT-4 — Extension-point test: in-tree `MakefileRunnerKind` plus a test-only `FakeBuildRunnerKind` (`PRECEDENCE = 1`); verify the fake wins lookup.
- [ ] TT-5 — Cache-outage test: break the backend; trigger_run succeeds with `cache_scope_key = None` and `pychestrate.build.cache.unavailable` WARNING logged.
- [ ] TT-6 — Replay-mismatch test: mutate one input byte post-store; replay raises `ReproducibilityError` listing the diverging path.
- [ ] TT-7 — Capability-mismatch test: target pod missing `linux/x86_64` for a runner requiring it; trigger rejected with `CapabilityMismatchError`.

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
