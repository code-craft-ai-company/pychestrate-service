# 6-build-artifacts — Requirements

## Introduction

The `6-build-artifacts` feature is the promotion-aware view of build
outputs over `5-artifact-store`. It defines a typed artifact manifest
per `BuildRun`, enables moving artifacts through channels
(`dev → staging → release`) via a declared `promotion_strategy`, and
exposes the manifest as the primary hand-off to deploy steps in
`6-pipeline-definition` and `6-infra-orchestration`. The feature ships
in **Phase 6** with the rest of the build slice. It does not own
artifact bytes — `5-artifact-store` does — but it owns the manifest
schema, promotion semantics, and channel-state lookups. Authoritative
source of truth for bytes is the content-addressed artifact store;
this feature is the promotion + typing layer on top.

## Requirements

### Requirement 1: Typed Artifact Manifest Per Build

**User Story:** As a downstream consumer (deploy step, release tool), I
want a strongly typed list of what a build produced so that I can fetch
only what I need.

**Acceptance Criteria (EARS):**

1. WHEN a `BuildRun` reaches terminal state `completed` THEN the system SHALL synthesize a `BuildArtifactManifest` with `entries: list[BuildArtifactEntry]` each containing `{artifact_type: str, name: str, content_hash_sha256: str, size_bytes: int, media_type: str | None, attrs: dict[str, str]}` AND persist it keyed by `run_id`.
2. WHEN `artifact_type` is declared via `ArtifactTypeExtension` (under `5-artifact-store`) THEN the system SHALL validate entries against the declared schema AND SHALL raise `SemanticError` listing schema errors.
3. IF a manifest entry's `content_hash_sha256` does not exist in `5-artifact-store` THEN the system SHALL raise `ManifestIntegrityError` naming the missing hash.
4. WHERE a build produces no artifacts THEN the manifest SHALL still be persisted with `entries == []`; downstream consumers SHALL receive a valid empty manifest.

### Requirement 2: Promotion Channels And Rules

**User Story:** As a release manager, I want to promote a build's
artifacts from `dev` to `staging` to `release`, so that controlled
release windows are enforceable.

**Acceptance Criteria (EARS):**

1. WHEN `artifacts.promote(project_id, run_id, target_channel, reason)` is called AND RBAC `artifact.promote:<target_channel>` passes THEN the system SHALL invoke `5-artifact-store.promote(entry, target_channel)` for every manifest entry AND persist a `PromotionLedger` row.
2. WHEN a promotion crosses a restricted transition (e.g., `dev → release` skipping `staging`) AND the project's `require_stepped_promotion == True` THEN the system SHALL raise `SemanticError` naming the forbidden transition.
3. WHEN a promotion succeeds THEN the system SHALL emit `entity.build.artifact.promoted` on the bus with `{run_id, from_channel, to_channel, entry_names}`.
4. WHERE a manifest includes entries with `artifact_type.requires_attestation == True` THEN the system SHALL require a valid `attestation_sha256` for each such entry AND SHALL raise `SemanticError` otherwise.

### Requirement 3: Channel State Query

**User Story:** As a deploy step author, I want to ask "what is the
current `release`-channel artifact of type `container-image`
name=`api`?", so that my deploy references the latest promoted build.

**Acceptance Criteria (EARS):**

1. WHEN `artifacts.get_channel_head(project_id, artifact_type, name, channel)` is called THEN the system SHALL return the most recently promoted `BuildArtifactEntry` of that `(type, name, channel)` tuple AND an immutable reference the consumer can use against `5-artifact-store`.
2. IF no entry exists THEN the system SHALL return `None` rather than raising — absence is a valid answer for channel queries.
3. WHERE a promotion was demoted (rollback) THEN the system SHALL return the current head after demotion, not the pre-demotion head.

## Property-Based Test Requirements

### Property 1: Manifest Synthesis Is Deterministic

- **Invariant:** For any `BuildRun` with a fixed set of result-tree artifact records and a fixed declared-type set, manifest synthesis produces a deterministic entry list (order, hashes, sizes) across two runs against the same inputs.
- **Generator:** `hypothesis.strategies.lists(tuples(text(min_size=1, max_size=64), binary(max_size=8192)), min_size=0, max_size=100)` — files + contents; `hypothesis.strategies.sampled_from` over type-schemas.
- **Assertion:** `synthesize(run_inputs) == synthesize(run_inputs)` and `set(entry.content_hash_sha256 for entry in manifest) == expected_hashes`.
- **Sample size:** 1000 generated cases

### Property 2: Stepped Promotion Never Skips When Required

- **Invariant:** For any sequence of promotion requests on a project with `require_stepped_promotion == True`, each accepted promotion moves only to the immediate next channel in the declared chain; any skip attempt raises `SemanticError`.
- **Generator:** `hypothesis.strategies.lists(sampled_from(["dev", "staging", "release", "hotfix"]), min_size=1, max_size=10)` as the requested target sequence; initial state `"dev"`.
- **Assertion:** Accepted transitions in the ledger strictly follow the declared step order; every rejected request raised `SemanticError` with the offending transition.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Manifest synthesis p99 < 300 ms for 500-entry builds. Promotion p99 < 900 ms including content-addressed link operations in `5-artifact-store`. Channel head query p99 < 40 ms with an index on `(project_id, artifact_type, name, channel)`.
- **NFR-2 (Security):** `artifact.promote:<channel>` RBAC gates every promotion; each channel can declare independent permission. Attestations (e.g., SLSA, in-toto) required when the artifact type declares `requires_attestation: True`. Rollback audited with reason and actor; never silent.
- **NFR-3 (Observability):** Metrics `pychestrate_build_artifact_manifest_size_bytes{project}` (histogram), `pychestrate_build_artifact_entries_count{project}` (histogram), `pychestrate_build_artifact_promotions_total{project,from,to}` (counter), `pychestrate_build_artifact_promotion_errors_total{project,error_kind}` (counter), `pychestrate_build_artifact_channel_head_lookups_total{project,type,channel}` (counter). Log events `pychestrate.build.artifact.manifest_synthesized`, `pychestrate.build.artifact.promoted`, `pychestrate.build.artifact.promotion_denied`, `pychestrate.build.artifact.rolled_back`. Trace spans `pychestrate.build.artifact.synthesize`, `pychestrate.build.artifact.promote`, `pychestrate.build.artifact.channel_head`.
- **NFR-4 (Reliability):** Manifest synthesis failures SHALL NOT block the `BuildRun` from completing — a retry-on-next-schedule entry is queued and synthesis is idempotent. Promotion is transactional: partial promotions roll back on any entry failure.

## Out of Scope

- Artifact bytes, presigning, or retention (see `5-artifact-store`).
- Channel-specific access policies beyond RBAC permission names.
- Pipeline integration (see `6-pipeline-definition`).

## Dependencies

- **Depends on:** `6-build-orchestration`, `5-artifact-store`, `5-result-ingest-watcher`, `0-persistence`, `0-message-bus`, `1-rbac`, `1-audit-log`.
- **Depended on by:** `6-pipeline-definition` (`artifact-promote` built-in), `6-infra-orchestration` (deploy references channel heads), `7-build-metrics`.
- **Extension points exposed:** Reuses `5-artifact-store` surfaces: `factory: promotion_strategy`, `resource: ArtifactTypeExtension`. No new extension surface declared here.
