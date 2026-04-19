# 6-build-artifacts — Design

## Architecture

`6-build-artifacts` is the typed, promotion-aware view of build outputs
layered over `5-artifact-store`. It synthesizes a `BuildArtifactManifest`
for every completed `BuildRun`, validates entries against
`ArtifactTypeExtension` schemas registered under Layer 5, and mediates
channel promotions via the Layer 5 `promotion_strategy`. It owns
`build_artifact_manifest` and `build_artifact_promotion_ledger` tables
plus `channel_head_cache`; it does not own artifact bytes. Ships in
Phase 6 alongside `6-build-orchestration`.

## Data Model

Tables in `0-persistence`:

- `build_artifact_manifest`:
  - `manifest_id: UUID` PK
  - `project_id: UUID`
  - `run_id: UUID` — unique
  - `entries_blob_key: str` — list[BuildArtifactEntry] serialized under `0-object-store`
  - `entries_count: int`
  - `total_size_bytes: int`
  - `synthesized_at: datetime`
  - `synthesis_error: str | None`
- `build_artifact_entry_index`:
  - `(manifest_id, artifact_type, name) PK`
  - `content_hash_sha256: bytes(32)`
  - `size_bytes: int`
  - `media_type: str | None`
  - `attrs_json: bytes`
- `build_artifact_promotion_ledger`:
  - `ledger_id: BIGSERIAL`
  - `project_id, run_id, artifact_type, name`
  - `from_channel: str | None`
  - `to_channel: str`
  - `actor_id: UUID`
  - `reason: str`
  - `promoted_at: datetime`
  - `rolled_back_at: datetime | None`
- `channel_head`:
  - `(project_id, artifact_type, name, channel) PK`
  - `ledger_id: BIGSERIAL`
  - `content_hash_sha256: bytes(32)`
  - `run_id: UUID`
  - `set_at: datetime`

Indices: `(project_id, artifact_type, channel)` on `channel_head`; `(project_id, run_id)` on `build_artifact_manifest`.

Value types:

- `BuildArtifactEntry` — matches requirements.
- `PromotionRequest`, `PromotionResult`.
- `ChannelHead` — immutable reference returned from queries.

## Interfaces

### Public API

REST under `8-rest-api-v1`:

- `GET /api/v1/projects/{project_id}/build-runs/{run_id}/artifact-manifest` → `BuildArtifactManifestView`.
- `POST /api/v1/projects/{project_id}/build-runs/{run_id}/artifacts:promote` body `{to_channel, reason, attestations?}` → `PromotionResult`.
- `POST /api/v1/projects/{project_id}/build-artifacts:rollback` body `{artifact_type, name, channel, reason}` → `PromotionResult`.
- `GET /api/v1/projects/{project_id}/build-artifacts/channel-head?artifact_type=&name=&channel=` → `ChannelHead | null`.

### Internal API

```python
class BuildArtifactsService:
    def __init__(
        self,
        repo: BuildArtifactsRepository,
        artifact_store: ArtifactStore,
        type_registry: ArtifactTypeRegistry,
        promotion_strategy_registry: PromotionStrategyRegistry,
        rbac: RbacService,
        audit: AuditLog,
        bus: MessageBus,
        clock: Clock,
        config: BuildArtifactsConfig
    ) -> None:
        self._repo = repo
        self._artifact_store = artifact_store
        self._type_registry = type_registry
        self._promotion_strategy_registry = promotion_strategy_registry
        self._rbac = rbac
        self._audit = audit
        self._bus = bus
        self._clock = clock
        self._config = config
        return

    def synthesize_manifest(
        self,
        run_id: UUID
    ) -> BuildArtifactManifest:
        """
            Produce a manifest for a completed BuildRun.

            :returns: BuildArtifactManifest.
            :raises: ManifestIntegrityError, SemanticError
        """
        ...

    def promote(
        self,
        actor_id: UUID,
        project_id: UUID,
        run_id: UUID,
        to_channel: str,
        reason: str,
        attestations: dict[str, bytes] | None = None,
        aspects: PromoteAspects | None = None
    ) -> PromotionResult:
        """
            Promote every manifest entry to target_channel.

            :returns: PromotionResult (per-entry outcomes).
            :raises: AuthorizationError, SemanticError, AttestationRequiredError
        """
        ...

    def rollback(
        self,
        actor_id: UUID,
        project_id: UUID,
        artifact_type: str,
        name: str,
        channel: str,
        reason: str
    ) -> PromotionResult:
        """
            Revert the channel head to the previous entry.

            :returns: PromotionResult.
            :raises: AuthorizationError, SemanticError, NoPreviousHeadError
        """
        ...

    def get_channel_head(
        self,
        project_id: UUID,
        artifact_type: str,
        name: str,
        channel: str
    ) -> ChannelHead | None:
        """
            :returns: Current ChannelHead or None.
            :raises: AuthorizationError
        """
        ...
```

### Extension Surface

None declared here. Reuses:

- `factory: promotion_strategy` from `5-artifact-store`.
- `resource: ArtifactTypeExtension` from `5-artifact-store`.

Built-in declared artifact types shipped under
`source/site/automojo/extensions/pychestrate/artifact_type/`:

- `ContainerImageArtifactType` — validates OCI digest + tag.
- `SbomArtifactType` — validates CycloneDX or SPDX JSON.
- `FirmwareImageArtifactType` — validates image metadata.
- `PythonPackageArtifactType` — validates wheel / sdist metadata.

### Events Emitted

- `entity.build.artifact.manifest_synthesized` — `{run_id, manifest_id, entries_count, total_size_bytes}`
- `entity.build.artifact.promoted` — `{run_id, from_channel, to_channel, entry_names}`
- `entity.build.artifact.promotion_denied` — `{run_id, to_channel, reason}`
- `entity.build.artifact.rolled_back` — `{project_id, artifact_type, name, channel, actor_id}`

### Events Consumed

- `entity.build.run_completed` — triggers `synthesize_manifest`.
- `extension.reloaded` — refresh type and strategy registries.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/orchestration/build/artifacts/`:

- `__init__.py`
- `service.py` — `BuildArtifactsService`.
- `repository.py` — `BuildArtifactsRepository`.
- `synthesizer.py` — builds manifests from result-tree entries in `5-result-ingest-watcher`.
- `promotion.py` — stepped-promotion validator + integration with Layer 5 promotion.
- `channel_head.py` — current-head lookup + caching.
- `attestation.py` — attestation hash validation.
- `aspects.py` — `PromoteAspects`.
- `errors.py` — `ManifestIntegrityError`, `AttestationRequiredError`, `NoPreviousHeadError`.
- `rest/v1_routes.py`.

Built-in artifact type extensions under
`source/site/automojo/extensions/pychestrate/artifact_type/`.

## Key Flows

### Flow 1 — Synthesize manifest

1. Subscriber fires on `entity.build.run_completed`.
2. `synthesizer.build(run_id)` lists ingested artifacts via `5-result-ingest-watcher`.
3. Entries matched to registered `ArtifactTypeExtension`s; unclassified entries default to type `"opaque"`.
4. Schema validation per type; failures aggregated into a single `SemanticError`.
5. Manifest persisted; `entries_blob_key` written to `0-object-store` for the full entries list; index rows populated.
6. `entity.build.artifact.manifest_synthesized` emitted.

### Flow 2 — Promote to next channel

1. REST → `promote(...)`.
2. RBAC `artifact.promote:<to_channel>` checked.
3. Stepped-promotion validator: if `require_stepped_promotion` and the proposed transition is not adjacent in declared chain, `SemanticError`.
4. Attestations verified per-entry as required.
5. Each entry passed to `5-artifact-store.promote(entry, to_channel)`; failures rollback any partial moves atomically.
6. `channel_head` updated; ledger appended.
7. `entity.build.artifact.promoted` emitted.

### Flow 3 — Channel head query

1. REST → `get_channel_head(...)`.
2. Cache checked first (5-min TTL); on miss read `channel_head` row.
3. Response built with an immutable reference usable against `5-artifact-store`.

## Error Handling

- `SemanticError` for forbidden transitions, schema errors, missing attestations: bubble.
- `ManifestIntegrityError` when a content hash is not present in `5-artifact-store`: bubble.
- `AuthorizationError`: 403.
- `NoPreviousHeadError`: 409.
- Synthesis crashes queued for retry with bounded backoff; not raised to the BuildRun subscriber.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- Channel-specific RBAC; a principal may have `artifact.promote:staging` but not `artifact.promote:release`.
- Attestations verified by hash only; verification of the attestation payload itself delegated to the artifact type's logic.
- Rollback auditable and reversible: the ledger keeps every transition.
- Promotion actions written to `1-audit-log` with actor, reason, affected entries.

## Observability

Metrics:

- `pychestrate_build_artifact_manifest_size_bytes{project}` — histogram
- `pychestrate_build_artifact_entries_count{project}` — histogram
- `pychestrate_build_artifact_promotions_total{project,from,to}` — counter
- `pychestrate_build_artifact_promotion_errors_total{project,error_kind}` — counter
- `pychestrate_build_artifact_channel_head_lookups_total{project,type,channel}` — counter

Log events: `pychestrate.build.artifact.manifest_synthesized`, `pychestrate.build.artifact.promoted`, `pychestrate.build.artifact.promotion_denied`, `pychestrate.build.artifact.rolled_back`.

Trace spans: `pychestrate.build.artifact.synthesize`, `pychestrate.build.artifact.promote`, `pychestrate.build.artifact.channel_head`, `pychestrate.build.artifact.rollback`.

## Open Questions

- Signed-attestation format pluggability (cosign, in-toto) — per-type default or via a new factory? Timebox: Phase 6 midpoint.
- Multi-channel fanout (promote to both `staging-eu` and `staging-us` atomically) — Phase 6 or defer. Timebox: Phase 6 exit.
- Channel chain configuration — global per-project or per-artifact-type? Timebox: Phase 6 exit.
