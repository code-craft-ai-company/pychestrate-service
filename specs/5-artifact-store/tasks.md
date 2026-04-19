# 5-artifact-store — Tasks

## Milestones

- **M1 — Skeleton:** Tables, `ArtifactStore.register` + `get`
  happy paths with server-side copy, `DefaultPromotionStrategy`,
  events.
- **M2 — Core Behavior:** `promotion_strategy` factory registry,
  `ArtifactTypeExtension` resource registry, typed metadata
  extraction, SBOM/container-image/firmware-image types,
  promotion + expiration sweepers, oversize skip path.
- **M3 — Hardening:** Property tests, perf benchmarks,
  consistency sweeper, dashboards, alerts, stream-copy fallback
  with size gate.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `artifacts/` package skeleton per design.md Component Breakdown.
- [ ] T1.2 — Add Postgres migrations for `artifact_blob`, `run_artifact_reference`, `artifact_type_metadata`, `artifact_retention_plan`.
- [ ] T1.3 — Implement `artifacts/repositories.py` CRUD with atomic reference-count updates.
- [ ] T1.4 — Implement `artifacts/hashing.py` streaming sha256 over `ObjectStore.get`.
- [ ] T1.5 — Implement `artifacts/cas_layout.py` CAS key construction for hot and cold tiers.
- [ ] T1.6 — Implement `artifacts/store.py::ArtifactStore.register` server-side-copy happy path; `get` authorized by reference.
- [ ] T1.7 — Implement `DefaultPromotionStrategy` at `source/site/automojo/factories/pychestrate/promotion_strategy/default.py` with `PRECEDENCE = 1000`.
- [ ] T1.8 — Emit `entity.artifact.ingested` on successful register.

### M2 — Core Behavior

- [ ] T2.1 — Declare `PromotionStrategyProtocol` factory and `ArtifactTypeExtension` resource at `artifacts/protocols.py`.
- [ ] T2.2 — Implement `artifacts/strategy_registry.py` and `artifacts/type_registry.py` via `E-extension-host`.
- [ ] T2.3 — Implement `SbomPromotionStrategy`, `BuildArtifactPromotionStrategy` at same factory path with `PRECEDENCE = 500`.
- [ ] T2.4 — Implement `SbomArtifactType`, `ContainerImageArtifactType`, `FirmwareImageArtifactType` under `source/site/automojo/extensions/pychestrate/artifact_types/`.
- [ ] T2.5 — Implement `artifacts/sweeper.py` promotion + expiration workers driven by `retention.sweep.tick`.
- [ ] T2.6 — Implement oversize skip path: record stub with `oversize=true`, no CAS copy, emit `pychestrate.artifact.oversize_skipped`.
- [ ] T2.7 — Implement stream-copy fallback with `client_copy_max_bytes` gate (256 MiB default); refuse larger files on non-server-side-copy drivers.
- [ ] T2.8 — Emit `entity.artifact.promoted` and `entity.artifact.expired`.

### M3 — Hardening

- [ ] T3.1 — Emit Prometheus metrics and OTel spans per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: dedup-hit register p99 < 60 ms; 1 MiB new p99 < 300 ms (server-side); 256 MiB stream-copy p99 < 3 s.
- [ ] T3.3 — Implement nightly consistency sweeper validating `SUM(reference_count) == COUNT(references)` per hash; flag drift.
- [ ] T3.4 — Wire `1-audit-log` subscriber for `entity.artifact.ingested`, `.promoted`, `.expired`.
- [ ] T3.5 — Add alert: oversize rate > 5% over 1 h → `7-alerts-budgets`.
- [ ] T3.6 — Document extension authoring `usersguide/artifacts/extension_guide.rst` — promotion strategies and typed artifact schemas.
- [ ] T3.7 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.8 — Add RBAC test: cross-project `get` denied with `ArtifactAuthorizationError`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (CAS dedup invariants) and Property 2 (deterministic promotion plan), 1000 cases each.
- [ ] TT-3 — Integration test: watcher delivers a 50-file tree with 20 duplicates to the store; assert 30 CAS blobs, 50 reference rows, `entity.artifact.ingested` × 50, dedup rate 40%.
- [ ] TT-4 — Extension-point test: in-tree `DefaultPromotionStrategy` + test-only `PriorityPromotionStrategy` (`PRECEDENCE = 10`); assert priority wins when both match.
- [ ] TT-5 — Typed-metadata test: register an SBOM artifact; assert `artifact_type_metadata` row parsed; register a malformed SBOM; assert base reference still created and `pychestrate.artifact.typed_metadata_invalid` emitted.
- [ ] TT-6 — Expiration test: register an artifact with 1-day retention; advance time 2 days; run expiry sweep; assert CAS blob deleted when `reference_count` reaches 0; other references keep it alive.
- [ ] TT-7 — Oversize test: register a 6 GiB artifact; assert stub created, no CAS copy, `oversize_skipped` event.

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
