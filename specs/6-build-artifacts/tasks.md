# 6-build-artifacts — Tasks

## Milestones

- **M1 — Skeleton:** Manifest schema + synthesize subscriber + basic REST read endpoint + built-in `ContainerImageArtifactType`.
- **M2 — Core Behavior:** Promote + rollback + channel head + stepped-promotion validator + attestation check + event emission.
- **M3 — Hardening:** `SbomArtifactType`, `FirmwareImageArtifactType`, `PythonPackageArtifactType`, metrics/logs/traces, property tests, perf, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/orchestration/build/artifacts/` package per design.md.
- [ ] T1.2 — Add `0-persistence` migration for `build_artifact_manifest`, `build_artifact_entry_index`, `build_artifact_promotion_ledger`, `channel_head`.
- [ ] T1.3 — Implement `synthesizer.py::synthesize_manifest` reading from `5-result-ingest-watcher`.
- [ ] T1.4 — Implement `ContainerImageArtifactType` at `source/site/automojo/extensions/pychestrate/artifact_type/container_image.py`.
- [ ] T1.5 — Implement `service.py::BuildArtifactsService.synthesize_manifest` and subscriber on `entity.build.run_completed`.
- [ ] T1.6 — Register `GET /api/v1/projects/{id}/build-runs/{run_id}/artifact-manifest`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `promotion.py` stepped-promotion validator and declared-chain data structure.
- [ ] T2.2 — Implement `promote` calling `5-artifact-store.promote` for each entry atomically.
- [ ] T2.3 — Implement `rollback` flipping `channel_head` to prior ledger entry.
- [ ] T2.4 — Implement `channel_head.py` with 5-minute LRU cache.
- [ ] T2.5 — Register REST `POST :promote`, `POST :rollback`, `GET /channel-head`.
- [ ] T2.6 — Implement `attestation.py` validating attestation SHA-256 pairs.
- [ ] T2.7 — Emit `entity.build.artifact.manifest_synthesized`, `entity.build.artifact.promoted`, `entity.build.artifact.promotion_denied`, `entity.build.artifact.rolled_back`.
- [ ] T2.8 — Wire audit log for every promotion and rollback.

### M3 — Hardening

- [ ] T3.1 — Implement `SbomArtifactType`, `FirmwareImageArtifactType`, `PythonPackageArtifactType`.
- [ ] T3.2 — Emit Prometheus metrics and OTel spans per design.md Observability.
- [ ] T3.3 — Benchmark NFR-1: synthesize p99 < 300 ms at 500 entries; promote p99 < 900 ms; channel-head lookup p99 < 40 ms. Fail CI on regression.
- [ ] T3.4 — Sphinx docs for REST, internal API, type authoring, attestation flow.
- [ ] T3.5 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.6 — Synthesis failure retry queue with bounded backoff; idempotent.
- [ ] T3.7 — Verify partial-promotion rollback atomicity via integration test.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (deterministic synthesis) and Property 2 (stepped promotion invariants) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 6 scenario — build produces `container-image` + `sbom` entries; `promote` moves both to `staging`; channel head returns the new head; rollback reverts cleanly.
- [ ] TT-4 — Extension-point test (reuse `5-artifact-store` surface): test-only `FakeArtifactType` (`PRECEDENCE = 1`) registered; manifest entries flagged against it.
- [ ] TT-5 — Attestation-required test: type declares `requires_attestation: True`; promote without attestations returns 400 with `AttestationRequiredError`.
- [ ] TT-6 — Partial-failure test: force a single-entry promotion to fail; assert no other entries flipped channel state.
- [ ] TT-7 — Channel-head cache test: stale-cache does not outlast its TTL; rollbacks invalidate the cache.

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
