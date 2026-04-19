# 0-object-store — Requirements

## Introduction

The `0-object-store` feature is Pychestrate's abstraction over the shared
artifact/result backend used by pod clients to push test results, build
artifacts, and other large blobs. It must support multiple backends — SMB,
NFS, S3, Azure Blob, GCS, and site-specific drivers — through the
`object_store_driver` factory protocol. The feature ships in **Phase 0**
and is the storage foundation for `5-shared-results-backend`,
`5-artifact-store`, `5-result-ingest-watcher`, and `6-build-artifacts`. Per
the implementation plan's Phase 0.5 exit criterion, this feature is the
first production consumer of the extension host: its SMB/S3 drivers are
loaded through `E-factory-protocols` rather than hard-wired, proving the
registry on a live dependency.

## Requirements

### Requirement 1: Driver-Agnostic Put/Get/List/Delete API

**User Story:** As a feature author, I want a single uniform object-store
API, so that my code does not change when the deployment backend changes
from local SMB to cloud S3.

**Acceptance Criteria (EARS):**

1. WHEN a caller invokes `store.put(key, source, content_type, metadata)`
   THEN the system SHALL write the object via the active driver and return
   an `ObjectPutResult` with `etag`, `size_bytes`, and `backend_path`.
2. IF the active driver is changed via configuration reload THEN the system
   SHALL invalidate any cached handles and route subsequent calls through
   the new driver without requiring a process restart.
3. WHEN `store.get(key)` is called against a non-existent key THEN the
   system SHALL raise `ObjectNotFoundError` — not return an empty body.
4. WHERE the driver supports server-side checksums THEN the system SHALL
   validate the checksum on `put` completion AND raise
   `ObjectIntegrityError` on mismatch.
5. WHEN `store.list(prefix, limit, continuation)` is called THEN the system
   SHALL return a page of at most `limit` entries in lexicographic key
   order plus an opaque `continuation` token.

### Requirement 2: Factory Protocol Contract Enforcement

**User Story:** As an extension author writing a new object-store driver, I
want a strict, typed protocol to implement, so that my driver drops into
Pychestrate without bespoke wiring.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers an implementation of
   `ObjectStoreDriverProtocol` THEN the system SHALL verify every required
   classmethod (`open`, `put`, `get`, `stat`, `list`, `delete`,
   `copy_within`, `presign_get`, `capabilities`, `close`) is present AND
   raise `ConfigurationError` naming the missing method otherwise.
2. IF two driver implementations share the same `factory_protocol_name`
   with the same `PRECEDENCE` value THEN the system SHALL raise
   `ConfigurationError` at load time naming both classes.
3. WHERE a call selects the driver by `_by_order` the system SHALL return
   the implementation with the lowest numeric `PRECEDENCE` (last-match
   wins for equal precedence is an error per AC #2, so the rule is
   unambiguous here).
4. WHERE a driver declares capability `presign_get: True` the system SHALL
   expose `store.presign_get(key, expires_seconds)`; where the capability
   is `False` the system SHALL raise `UnsupportedOperationError`.

### Requirement 3: Per-Project Scoped Paths

**User Story:** As a service operator, I want every stored object's
physical path namespaced by project, so that retention policies and access
isolation can be enforced at the backend level.

**Acceptance Criteria (EARS):**

1. WHEN a `put` is issued with a key of the form `<project_slug>/<…>` AND
   `project_slug` does not match an existing project THEN the system SHALL
   raise `SemanticError` (never caught).
2. WHEN a key is accepted THEN the system SHALL write at physical path
   `<bucket_prefix>/<project_slug>/<remainder>`.
3. WHILE a project is in read-only maintenance mode (see
   `0-maintenance-mode`) the system SHALL reject `put`, `delete`, and
   `copy_within` with `MaintenanceModeError` and SHALL continue to serve
   `get`, `stat`, `list`, and `presign_get`.

### Requirement 4: Integrity, Retry, and Chunked Uploads

**User Story:** As a pod client pushing large result trees, I want
resilient chunked uploads with content integrity, so that transient
network failures do not lose artifact bytes.

**Acceptance Criteria (EARS):**

1. WHEN `put` is invoked with an object larger than
   `multipart_threshold_bytes` (default 16 MiB) THEN the system SHALL split
   the upload into chunks of `multipart_chunk_bytes` (default 8 MiB) and
   transmit them in parallel with a bounded worker count (default 4).
2. IF a chunk upload fails with a retryable error THEN the system SHALL
   retry using an `Aspects`-provided policy (default: 3 attempts,
   exponential backoff starting at 250 ms, capped at 5 s).
3. WHERE the source is a file the system SHALL compute SHA-256 while
   uploading AND include it in the returned `etag` as
   `sha256:<hex>` when the driver does not provide its own etag.

## Property-Based Test Requirements

### Property 1: Put Then Get Yields Identical Bytes Across Any Driver

- **Invariant:** For any byte sequence `b` and any key `k`, `store.put(k, b)`
  followed by `store.get(k)` returns bytes equal to `b` and `size_bytes`
  equal to `len(b)`, for every in-tree driver (local-fs, s3-compat).
- **Generator:** `hypothesis.strategies.binary(min_size=0, max_size=8_388_608)`
  (up to 8 MiB to exercise multipart boundary) paired with
  `text(alphabet=ascii_letters + digits + "/-_.", min_size=1, max_size=255)`
  prefixed with a fixed project slug `"proj-test"`.
- **Assertion:** `store.get(k).read() == b` and
  `store.stat(k).size_bytes == len(b)`.
- **Sample size:** 1000 generated cases (per driver)

### Property 2: Lexicographic List Pagination is Stable and Complete

- **Invariant:** For any set of keys under a prefix, paginating with page
  size `n` reconstructs exactly the original set in sorted order with no
  duplicates.
- **Generator:** `hypothesis.strategies.sets(text(alphabet=ascii_letters +
  digits + "/-_.", min_size=1, max_size=64), min_size=0, max_size=500)`
  with each key prefixed `proj-test/listtest/`.
- **Assertion:** `sorted(all_keys) == flatten(list_pages(prefix, page_size))`
  and no key appears twice.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Single-object `put` of 1 MiB p99 < 250 ms on the
  local-fs reference driver; S3 reference driver (intra-region) p99 <
  800 ms. `stat` p99 < 30 ms across all drivers. Multipart of 1 GiB
  completes under 60 s on an S3 driver with 4 parallel workers on a
  1 Gbps link.
- **NFR-2 (Security):** Driver credentials MUST be pulled from
  `1-secrets-vault` (env var fallback gated by `PYCHESTRATE_DEV_MODE`).
  Presigned URLs MUST default to `expires_seconds <= 3600` with an
  operator-configurable ceiling. Keys MUST be validated against
  `^[A-Za-z0-9/_.\-]{1,1024}$` before being passed to the driver to prevent
  path traversal.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_object_store_put_duration_seconds{driver,project}`
  (histogram), `pychestrate_object_store_get_duration_seconds{driver,project}`
  (histogram), `pychestrate_object_store_list_duration_seconds{driver,project}`
  (histogram), `pychestrate_object_store_bytes_uploaded_total{driver,project}`
  (counter), `pychestrate_object_store_bytes_downloaded_total{driver,project}`
  (counter), `pychestrate_object_store_errors_total{driver,operation,error_kind}`
  (counter). Log events `pychestrate.object_store.put.completed`,
  `pychestrate.object_store.put.failed`, `pychestrate.object_store.integrity.mismatch`,
  `pychestrate.object_store.maintenance.blocked`. Trace spans
  `pychestrate.object_store.put`, `pychestrate.object_store.get`,
  `pychestrate.object_store.list` with `driver` and `project` attributes.
- **NFR-4 (Reliability):** 99.9% monthly availability of the local-fs
  driver tier; cloud driver availability bounded by the upstream
  provider's SLA. A dead driver MUST NOT block process startup — startup
  continues with the driver marked `unavailable` and returns 503 for
  operations until the driver's health probe reports recovery.

## Out of Scope

- Content-addressed storage and promotion paths (see `5-artifact-store`).
- File-path-to-artifact-category classification (see
  `ArtifactClassifierExtension` under `5-result-ingest-watcher`).
- CDN fronting / edge caching.
- Client-side encryption (driver-side encryption is delegated to the
  driver's capability matrix).

## Dependencies

- **Depends on:** `0-web-app-host` (hooks), `E-extension-host` (Phase 0.5
  — required to load drivers; in Phase 0 a hardcoded `LocalFsDriver` is
  acceptable), `1-secrets-vault` once available (env fallback until then),
  `0-maintenance-mode` (read-only gating for put/delete/copy).
- **Depended on by:** `5-shared-results-backend`, `5-artifact-store`,
  `5-result-ingest-watcher`, `6-build-artifacts`, `10-backup-dr`.
- **Extension points exposed:** `factory: object_store_driver` — concrete
  drivers for SMB, NFS, S3, Azure Blob, GCS, and custom backends.
