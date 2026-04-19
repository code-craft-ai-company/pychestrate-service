# 5-artifact-store — Design

## Architecture

The artifact store is a service-owned layer that converts
per-run-prefixed files (landed by `5-result-ingest-watcher` into
the backend allocated by `5-shared-results-backend`) into a
content-addressed store with reference counting and lifecycle
tiers. It lives at
`source/site/automojo/pychestrate/webservice/artifacts/`. Owned
physical layout on the object store:

- `cas/<first2>/<full-hash>` — canonical CAS blob.
- `cas-cold/<first2>/<full-hash>` — promoted cold-tier copy.

Per-run files stay under the results prefix owned by
`5-shared-results-backend`; the artifact store only references them
via `(run_id, path)` and the computed content hash. Authoritative
source of truth for artifact bytes is the CAS blob; the per-run
reference is a pointer. This feature lands in **Phase 3** and
grows through Phases 5-6 as more artifact types and renderers
arrive.

## Data Model

Owned rows:

- `artifact_blob` (CAS index):
  - `content_hash: text` (PK, `sha256:<hex>`)
  - `size_bytes: bigint`
  - `tier: ArtifactTier` (`hot` | `cold`)
  - `cas_key: text` (object-store key)
  - `first_seen_at: timestamptz`
  - `last_referenced_at: timestamptz`
  - `reference_count: int`
- `run_artifact_reference`:
  - `reference_id: UUID` (PK, UUIDv7)
  - `run_id: UUID` (FK, indexed)
  - `run_artifact_id: UUID` (FK → `run_artifact.artifact_id`, unique)
  - `content_hash: text` (FK → `artifact_blob.content_hash`)
  - `path: text` (relative to run prefix)
  - `category: text`
  - `registered_at: timestamptz`
  - `oversize: bool`
- `artifact_type_metadata`:
  - `metadata_id: UUID` (PK)
  - `content_hash: text` (FK)
  - `type_name: text`
  - `metadata_jsonb: jsonb`
  - Unique constraint: `(content_hash, type_name)`.
- `artifact_retention_plan`:
  - `plan_id: UUID` (PK)
  - `content_hash: text` (FK)
  - `run_id: UUID`
  - `retention_days: int`
  - `cold_after_days: int`
  - `promote_to_tier: ArtifactTier`
  - `preserved_labels: text[]`
  - `created_at: timestamptz`

Enums:

- `ArtifactTier`: `hot | cold`

Value types:

- `PromotionPlan`:
  - `retention_days: int`
  - `cold_after_days: int`
  - `promote_to_tier: ArtifactTier`
  - `preserved_labels: frozenset[str]`

## Interfaces

### Public API

N/A. Callers are in-process: `5-result-ingest-watcher`,
`2-retention-policies`, `6-artifact-browser`, `6-build-artifacts`.

### Internal API

```python
class ArtifactStore:
    def __init__(
        self,
        object_store: ObjectStore,
        shared_backend: SharedResultsBackend,
        blob_repository: ArtifactBlobRepository,
        reference_repository: RunArtifactReferenceRepository,
        type_metadata_repository: ArtifactTypeMetadataRepository,
        retention_repository: ArtifactRetentionRepository,
        strategy_registry: PromotionStrategyRegistry,
        type_registry: ArtifactTypeRegistry,
        bus: MessageBus,
        config: ArtifactStoreConfig
    ) -> None:
        self._object_store = object_store
        self._shared_backend = shared_backend
        self._blob_repository = blob_repository
        self._reference_repository = reference_repository
        self._type_metadata_repository = type_metadata_repository
        self._retention_repository = retention_repository
        self._strategy_registry = strategy_registry
        self._type_registry = type_registry
        self._bus = bus
        self._config = config
        return

    def register(
        self,
        run_id: UUID,
        source_key: str,
        category: str,
        labels: frozenset[str] | None = None,
        aspects: RegisterAspects | None = None
    ) -> RunArtifactReference:
        """
            Compute content hash, deduplicate or copy into CAS,
            attach a per-run reference, emit
            entity.artifact.ingested.

            :param run_id: Service run id.
            :param source_key: Object-store key under the run
                               prefix.
            :param category: Classifier result.
            :param labels: Optional label set (e.g., artifacts/<label>).
            :param aspects: Behavior parameters (copy mode, retry).

            :returns: RunArtifactReference.
            :raises: UnsupportedOperationError, SemanticError,
                     ArtifactRegisterError
        """
        ...

    def get(
        self,
        artifact_id: UUID,
        aspects: GetAspects | None = None
    ) -> BinaryIO:
        """
            Open a read stream for an artifact's CAS blob,
            authorized by run access.

            :param artifact_id: Reference row id.
            :param aspects: Behavior parameters.

            :returns: Binary read stream.
            :raises: ArtifactNotFoundError,
                     ArtifactAuthorizationError
        """
        ...

    def promote(
        self,
        content_hash: str,
        to_tier: ArtifactTier
    ) -> None:
        """
            Move a CAS blob to the target tier and update
            artifact_blob.tier.

            :param content_hash: sha256-prefixed hash.
            :param to_tier: Target tier.

            :returns: None
            :raises: UnsupportedOperationError, ArtifactNotFoundError
        """
        ...

    def expire(
        self,
        content_hash: str,
        reason: str
    ) -> None:
        """
            Decrement reference count; delete CAS blob when it
            reaches zero.

            :param content_hash: sha256-prefixed hash.
            :param reason: Audited reason string.

            :returns: None
            :raises: ArtifactNotFoundError
        """
        ...

    def iter_references(
        self,
        run_id: UUID
    ) -> Iterator[RunArtifactReference]:
        """
            Yield every artifact reference for a run.

            :param run_id: Service run id.

            :returns: Iterator of references.
            :raises: None
        """
        ...
```

### Extension Surface

Factory protocol declared here:

```python
class PromotionStrategyProtocol(FactoryProtocolBase):
    """
        Contract for promotion_strategy implementations.
    """
    factory_protocol_name: str = "promotion_strategy"

    @classmethod
    def classify(
        cls,
        reference: RunArtifactReference,
        blob: ArtifactBlob,
        run: RunSnapshot,
        type_metadata: dict[str, Any] | None
    ) -> PromotionPlan | None:
        """
            Return a PromotionPlan for this artifact, or None to
            defer to the next strategy.

            :param reference: Per-run artifact reference.
            :param blob: CAS blob row.
            :param run: Owning run snapshot.
            :param type_metadata: Typed metadata if present.

            :returns: PromotionPlan or None.
            :raises: None
        """
        rtnval = None
        return rtnval
```

Resource extension base declared here:

```python
class ArtifactTypeExtension(ResourceExtension):
    """
        Declare a typed artifact type with a metadata schema.
    """
    type_name: str = ""
    metadata_schema: type[BaseModel] = BaseModel
    classifier_hint_regex: str = r".*"

    @classmethod
    def extract_metadata(
        cls,
        content_hash: str,
        reader: BinaryIO
    ) -> BaseModel:
        """
            Parse typed metadata out of the CAS blob.

            :param content_hash: sha256-prefixed hash.
            :param reader: Read stream for the CAS blob.

            :returns: metadata_schema instance.
            :raises: ArtifactMetadataError
        """
        ...
```

Reference implementations shipped in-tree:

- `DefaultPromotionStrategy` at
  `source/site/automojo/factories/pychestrate/promotion_strategy/default.py`,
  `PRECEDENCE = 1000`. 30-day retention, no promotion.
- `SbomPromotionStrategy` at same path, `PRECEDENCE = 500`.
  7-year retention, promote to cold after 30 days; keyed by
  `category == "sbom"`.
- `BuildArtifactPromotionStrategy` at same path, `PRECEDENCE =
  500`. 1-year retention, promote to cold after 90 days; keyed
  by category `build-output`.
- `SbomArtifactType` at
  `source/site/automojo/extensions/pychestrate/artifact_types/sbom.py`
  — `type_name = "sbom"`.
- `ContainerImageArtifactType` at same path — `type_name =
  "container-image"`.
- `FirmwareImageArtifactType` at same path — `type_name =
  "firmware-image"`.

### Events Emitted

On `0-message-bus`:

- `entity.artifact.ingested` — `{run_id, artifact_id,
  content_hash, category, size_bytes, deduplicated, path}`
- `entity.artifact.promoted` — `{content_hash, from_tier,
  to_tier, promoted_at}`
- `entity.artifact.expired` — `{content_hash, reason,
  expired_at, references_remaining}`
- `pychestrate.artifact.typed_metadata_invalid` — `{content_hash,
  type_name, error}`
- `pychestrate.artifact.oversize_skipped` — `{run_id, path,
  size_bytes}`

### Events Consumed

- `entity.run.completed | entity.run.failed |
  entity.run.cancelled` — triggers per-run retention-plan
  materialization for every registered artifact.
- `retention.sweep.tick` (from `2-retention-policies`) —
  drives promotion and expiration sweeps.
- `extension.reloaded` — rebuilds strategy and type registries.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/`:

- `artifacts/__init__.py`
- `artifacts/store.py` — `ArtifactStore` facade.
- `artifacts/cas_layout.py` — CAS key construction,
  `cas/<first2>/<hash>` / `cas-cold/<first2>/<hash>`.
- `artifacts/hashing.py` — streaming sha256 helper.
- `artifacts/repositories.py` — blob, reference, type-metadata,
  retention repos.
- `artifacts/strategy_registry.py`
- `artifacts/type_registry.py`
- `artifacts/protocols.py` — `PromotionStrategyProtocol`,
  `ArtifactTypeExtension`.
- `artifacts/sweeper.py` — background workers for promotion
  and expiration.
- `artifacts/errors.py` — `ArtifactNotFoundError`,
  `ArtifactAuthorizationError`, `ArtifactRegisterError`,
  `ArtifactMetadataError`.
- `artifacts/hooks.py` — startup hook launching the sweepers.

## Key Flows

### Flow 1 — Register Happy Path

1. `5-result-ingest-watcher` walks a tree, calls
   `artifact_store.register(run_id, source_key, category,
   labels)`.
2. `hashing.stream_sha256(source_key)` computes the hash.
3. `blob_repository.upsert(content_hash, size_bytes, cas_key,
   tier='hot')` either creates the row (new) or returns the
   existing one (dup).
4. If new: `object_store.copy_within(source_key, cas_key)` (or
   stream-copy fallback); `reference_count` set to 1.
5. If dup: `reference_count` incremented in the same transaction
   as the per-run reference insert.
6. `type_registry.match(category, classifier_hints)` may yield
   an `ArtifactTypeExtension`; metadata extracted and persisted.
7. `strategy_registry.classify(...)` produces a `PromotionPlan`;
   `artifact_retention_plan` row written.
8. `entity.artifact.ingested` emitted.

### Flow 2 — Promotion Sweep

1. `retention.sweep.tick` fires hourly.
2. Sweeper queries for `artifact_blob` rows where `tier='hot'`
   and `first_seen_at + cold_after_days < now` and every
   retention plan's cold threshold has elapsed.
3. `object_store.copy_within(cas_key, cold_cas_key)`;
   `blob_repository` updates `tier='cold'`, `cas_key=cold_cas_key`.
4. Original hot blob deleted after cold copy verified.
5. `entity.artifact.promoted` emitted.

### Flow 3 — Expiration

1. Sweeper queries for artifact references whose retention plan
   has elapsed.
2. For each, `expire(content_hash, reason="retention")`
   decrements `reference_count` in a transaction.
3. When count reaches zero: `object_store.delete(cas_key)`;
   `artifact_blob` row deleted.
4. `entity.artifact.expired` emitted.

## Error Handling

- `ArtifactNotFoundError`: domain error; callers translate to 404.
- `ArtifactAuthorizationError`: raised when requester lacks run
  access; translate to 403.
- `ArtifactRegisterError`: caught-and-reclassified envelope for
  underlying `ObjectStoreError` during register; retried per
  aspects, then bubbles.
- `UnsupportedOperationError`: driver lacks a capability needed
  for the configured copy mode; bubbles.
- `ArtifactMetadataError`: logged, skipped, the base reference is
  still created (Requirement 3 AC #4).
- `ConfigurationError`: duplicate `type_name` at load; startup
  fails.
- `SemanticError` (malformed hash, unknown run): never caught.

Example multiline error:

```python
err_msg_lines = ["Artifact register failed — copy driver mismatch."]
err_msg_lines.append("RUN_ID: {}".format(run_id))
err_msg_lines.append("SOURCE_KEY: {}".format(source_key))
err_msg_lines.append("SIZE_BYTES: {}".format(size_bytes))
err_msg_lines.append("DRIVER: {}".format(driver_name))
err_msg_lines.append("REASON: stream-copy path exceeds client_copy_max_bytes")

err_msg = os.linesep.join(err_msg_lines)
raise UnsupportedOperationError(err_msg) from None
```

## Security Considerations

- Content hash computed by the service. Client-supplied hashes
  are never trusted.
- Authorization: `get(artifact_id)` authorizes via the
  `run_artifact_reference` row, which carries the owning run
  and thus the owning project; RBAC is `artifacts:read` scoped
  by project in `8-rest-api-v1`.
- CAS blobs are never exposed by raw hash — there is no public
  endpoint that accepts a hash; every read goes through a
  reference id.
- Promotion to cold tier via server-side-copy keeps credentials
  inside driver boundaries.
- Typed metadata parsers run in-process; gated by
  `E-extension-sandbox` `read:artifacts` in Phase 8.
- `1-audit-log` subscribes to `entity.artifact.ingested`,
  `.promoted`, `.expired`.

## Observability

Metrics listed in requirements.md NFR-3. Additional tracing:

- Span `pychestrate.artifact.register` with `project`, `run_id`,
  `category`, `copy_mode`, `deduplicated`, `size_bytes`.
- Span `pychestrate.artifact.promote` with `from_tier`,
  `to_tier`, `content_hash_prefix`.
- Span `pychestrate.artifact.expire`.

Dashboards:

- CAS dedup rate = 1 - (unique blobs / total registrations).
- Storage-by-tier pie (hot vs cold vs per-run references).
- Oversize count and typed-metadata invalid rate.

Alerts:

- CAS consistency drift (nightly sweeper) > 0 → page on-call.
- Oversize rate > 5% of registrations for 1 h → investigate.

## Open Questions

- Should `content_hash` include a namespace (e.g., `sha256:`) or
  stay raw hex? Current draft: include `sha256:` prefix so future
  multi-algo support is mechanical. Timebox: Phase 3 exit.
- Cold-tier on local-fs driver: emulate via a subdirectory, or
  refuse with `UnsupportedOperationError`? Current draft: emulate
  (it's a dev-mode driver only). Timebox: Phase 3 exit.
- Stream-copy fallback allowed on S3? Generally unnecessary (S3
  supports server-side copy), but do we still gate by size to
  avoid a misconfigured driver hogging a worker? Current draft:
  yes, gate at `client_copy_max_bytes` on every driver. Timebox:
  Phase 3 exit.
