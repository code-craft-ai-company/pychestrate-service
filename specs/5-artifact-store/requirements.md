# 5-artifact-store — Requirements

## Introduction

The `5-artifact-store` feature sits on top of `0-object-store` and
adds two concepts the raw object store does not: **content-addressed
deduplication** and **promotion paths**. Every artifact the result
watcher hands over is hashed (sha256), stored once under
`cas/<hash-prefix>/<full-hash>`, and referenced from the per-run
view. Retention can then promote "interesting" artifacts (SBOMs,
build outputs, firmware images) into longer-horizon tiers while
letting ephemeral artifacts age out — the `promotion_strategy`
factory protocol governs that decision, and the
`ArtifactTypeExtension` resource extension declares the typed
schemas new artifact types carry. This feature ships in **Phase 3**
and is the source of `entity.artifact.ingested`,
`entity.artifact.promoted`, and `entity.artifact.expired` events.

## Requirements

### Requirement 1: Content-Addressed Registration of Artifacts

**User Story:** As a result watcher, I want to hand every file to
the artifact store without worrying about deduplication, so that a
run that produces the same binary output as a prior run does not
double-store the bytes.

**Acceptance Criteria (EARS):**

1. WHEN `artifact_store.register(run_id, source_key, category,
   labels)` is called with a key already present in the shared
   backend THEN the system SHALL compute the blob's sha256, check
   `artifact_blob` by `content_hash`, and either reference the
   existing CAS blob or copy the source into
   `cas/<first2>/<full-hash>` via the object-store's
   server-side-copy capability.
2. WHEN a CAS blob is newly created THEN the system SHALL persist
   an `artifact_blob` row with `(content_hash, size_bytes,
   first_seen_at, reference_count=1)`.
3. WHEN an existing CAS blob is referenced THEN the system SHALL
   increment its `reference_count` atomically in the same
   transaction that creates the per-run artifact row.
4. IF the source blob exceeds `max_artifact_size_bytes` (default
   5 GiB) THEN the system SHALL store a stub row flagged
   `oversize=true`, NOT copy into CAS, AND emit
   `pychestrate.artifact.oversize_skipped`.
5. WHERE the object-store driver does not support server-side copy
   THEN the system SHALL stream-copy through the service — but this
   path is only permitted for artifacts ≤
   `client_copy_max_bytes` (default 256 MiB); larger artifacts on
   such drivers raise `UnsupportedOperationError` at registration.

### Requirement 2: Promotion via `promotion_strategy` Factory

**User Story:** As a retention engineer, I want to configure per-type
promotion rules, so that SBOMs live in cold-tier for 7 years while
temporary log files expire after 30 days.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers a `PromotionStrategyProtocol`
   implementation THEN the system SHALL register it under
   `factory_protocol_name = "promotion_strategy"` with its
   declared `PRECEDENCE`.
2. WHEN a new artifact is registered THEN the system SHALL invoke
   `strategy.classify(artifact_row, blob_row, run_row,
   artifact_type_row)` to obtain a `PromotionPlan`
   (`retention_days`, `cold_after_days`, `promote_to_tier`,
   `preserved_labels`).
3. WHEN the artifact's `cold_after_days` elapses THEN the system
   SHALL call `object_store.copy_within` to move the CAS blob to
   the cold tier and emit `entity.artifact.promoted`.
4. WHEN the artifact's `retention_days` elapses AND no newer run
   references the CAS blob THEN the system SHALL decrement
   `reference_count`; when it reaches zero, issue a delete on the
   CAS blob AND emit `entity.artifact.expired`.
5. WHERE multiple strategies match THEN the system SHALL apply
   the lowest-`PRECEDENCE` non-None result — higher-precedence
   strategies take priority.

### Requirement 3: Typed Artifact Schemas via `ArtifactTypeExtension`

**User Story:** As an extension author for a container-image scanner,
I want to register a typed `container-image` artifact schema, so
that my tooling can rely on a stable set of fields
(`image_digest`, `image_ref`, `platform`) for every container-image
artifact.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers an `ArtifactTypeExtension`
   subclass THEN the system SHALL register its `type_name`, typed
   schema (`pydantic.BaseModel`), classifier-hint regex, and
   `PRECEDENCE`.
2. WHEN an artifact is registered AND its classification matches
   an `ArtifactTypeExtension` THEN the system SHALL parse the
   extracted metadata through the extension's schema AND persist
   it in `artifact_type_metadata`.
3. IF two `ArtifactTypeExtension` subclasses declare the same
   `type_name` THEN the system SHALL raise `ConfigurationError`
   at load time naming both classes.
4. WHERE an artifact's classification produces metadata that
   fails schema validation THEN the system SHALL log the error,
   skip the typed-metadata row, AND still create the base
   `run_artifact_reference` row (typing is optional enrichment, not
   a registration precondition).

## Property-Based Test Requirements

### Property 1: Content-Addressing Deduplicates Identical Bytes

- **Invariant:** For any set of artifacts `{a_1, …, a_k}` such that
  `sha256(a_i) == sha256(a_j)` for some pair, the resulting CAS
  store contains exactly one `artifact_blob` row per distinct
  sha256 AND the sum of `reference_count` equals the total number
  of `register` calls that produced a non-oversize artifact.
- **Generator:** `hypothesis.strategies.lists(bytes(min_size=0,
  max_size=131072))` with many duplicates injected (half the
  population reuses 8 canonical byte strings).
- **Assertion:** deduplication invariants hold; every referenced
  row reads identical bytes back via
  `artifact_store.get(artifact_id)`.
- **Sample size:** 1000 generated cases

### Property 2: Promotion Plan is Deterministic Per-Type

- **Invariant:** For any fixed `(artifact_type, artifact_category,
  size_bytes, labels)` tuple, repeated calls to
  `strategy.classify(...)` on the lowest-`PRECEDENCE` matching
  strategy return the same `PromotionPlan` tuple.
- **Generator:** sample type/category/size/labels from fixed
  pools; invoke 10 times.
- **Assertion:** every call produces identical
  `(retention_days, cold_after_days, promote_to_tier,
  preserved_labels)`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `register` p99 < 60 ms for artifacts
  already present in CAS (no copy); p99 < 300 ms for a 1 MiB new
  blob on a server-side-copy-capable driver; p99 < 3 s for a 256
  MiB stream-copy (allowed only when driver lacks server-side
  copy). Promotion and expiration sweeps SHALL process ≥ 100
  artifacts/sec/worker.
- **NFR-2 (Security):** `content_hash` is computed by the service
  (not trusted from the client). CAS reads are authorized by the
  run-scope of the requester — an operator without access to run
  A cannot `get` artifact A even if they guess its hash because
  the `run_artifact_reference` is the authorization boundary.
  Promotion and expiration emit `1-audit-log` entries.
  Oversize artifacts are not promoted; they remain stubs in the
  run's result prefix until retention purges the prefix wholesale.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_artifact_registered_total{project,category,deduplicated}`
  (counter),
  `pychestrate_artifact_cas_blobs_total{tier}` (gauge),
  `pychestrate_artifact_cas_bytes_total{tier}` (gauge),
  `pychestrate_artifact_register_duration_seconds{copy_mode}`
  (histogram),
  `pychestrate_artifact_promoted_total{to_tier}` (counter),
  `pychestrate_artifact_expired_total{reason}` (counter),
  `pychestrate_artifact_reference_count{content_hash_bucket}`
  (histogram),
  `pychestrate_artifact_oversize_total{project}` (counter).
  Log events `pychestrate.artifact.registered`,
  `pychestrate.artifact.deduplicated`,
  `pychestrate.artifact.promoted`,
  `pychestrate.artifact.expired`,
  `pychestrate.artifact.oversize_skipped`,
  `pychestrate.artifact.typed_metadata_invalid`. Trace span
  `pychestrate.artifact.register` with `project`, `run_id`,
  `category`, `copy_mode`, `deduplicated`.
- **NFR-4 (Reliability):** Reference-count updates are atomic with
  per-run reference row creation in a single transaction — a
  crash during copy cannot produce an orphaned blob with a
  non-zero count. A background consistency sweeper validates
  `SUM(reference_count) == count_of_reference_rows_per_hash`
  nightly and flags drift.

## Out of Scope

- Raw byte transfer — owned by `0-object-store`.
- Per-run prefix allocation — owned by
  `5-shared-results-backend`.
- UI rendering of artifacts — owned by `6-artifact-browser`.
- Classification into categories — owned by
  `5-result-ingest-watcher` (`ArtifactClassifierExtension`).
- Long-horizon cold-tier backup — owned by `10-backup-dr`.

## Dependencies

- **Depends on:** `0-object-store`, `0-persistence`, `0-message-bus`,
  `5-shared-results-backend` (source prefix for blobs),
  `5-result-ingest-watcher` (registration call site),
  `2-retention-policies` (schedules promotion + expiry sweeps),
  `E-extension-host`, `E-factory-protocols`,
  `E-resource-extensions`, `1-audit-log`.
- **Depended on by:** `6-artifact-browser`, `6-build-artifacts`,
  `6-compare-runs`, `10-backup-dr`.
- **Extension points exposed:** `factory: promotion_strategy`,
  `resource: ArtifactTypeExtension` — see implementation-plan.md
  Layer 5 section.
