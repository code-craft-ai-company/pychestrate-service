# 0-object-store — Tasks

## Milestones

- **M1 — Skeleton:** Facade + `LocalFsObjectStoreDriver` reference
  driver, key validation, project scoping, put/get/stat/list/delete
  wired, hooked onto the web app host.
- **M2 — Core Behavior:** Factory protocol declaration, multipart
  chunked uploads, retry `Aspects`, maintenance-mode gating, bus event
  emission, S3 reference driver (first out-of-factory consumer via the
  extension host).
- **M3 — Hardening:** Perf validation, property tests, integrity
  guarantees, Azure Blob and GCS reference drivers, dashboards,
  presign capping, chaos test for driver failover.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/object_store/` package skeleton per design.md Component Breakdown.
- [ ] T1.2 — Implement `object_store/config.py::ObjectStoreConfig` and `DriverConfig`.
- [ ] T1.3 — Implement `object_store/key_validation.py` enforcing `^[A-Za-z0-9/_.\-]{1,1024}$` and project-slug extraction.
- [ ] T1.4 — Implement `object_store/driver_base.py::ObjectStoreDriver` abstract class with instance methods listed in design.md.
- [ ] T1.5 — Implement `object_store/facade.py::ObjectStore` single-shot put/get/stat/list/delete without multipart; wire ProjectLookup and MaintenanceGate dependencies.
- [ ] T1.6 — Implement `LocalFsObjectStoreDriver` at `source/site/automojo/factories/pychestrate/object_store/local_fs.py` with `PRECEDENCE = 1000`.
- [ ] T1.7 — Register `object_store_startup_hook` on the web app at priority `30`; wire `active_driver` via the extension host (or direct instantiation pre-Phase-0.5).
- [ ] T1.8 — Implement `object_store/errors.py` with the error hierarchy listed in design.md.

### M2 — Core Behavior

- [ ] T2.1 — Implement `object_store/protocol.py::ObjectStoreDriverProtocol` declaring `factory_protocol_name = "object_store_driver"` and required classmethods.
- [ ] T2.2 — Implement multipart path in `object_store/multipart.py`: threshold 16 MiB, chunk 8 MiB, 4-worker parallel uploads.
- [ ] T2.3 — Implement `object_store/aspects.py::PutAspects` and `GetAspects` with retry policy (3 attempts, exponential backoff 250 ms → 5 s).
- [ ] T2.4 — Implement `object_store/integrity.py` streaming SHA-256, set `etag = "sha256:<hex>"` when driver does not provide one.
- [ ] T2.5 — Subscribe to `maintenance.mode.changed` on `0-message-bus`; update `MaintenanceGate`; raise `MaintenanceModeError` on put/delete/copy for affected scopes.
- [ ] T2.6 — Publish `object_store.driver.activated`, `object_store.object.put`, `object_store.object.deleted` events on the bus.
- [ ] T2.7 — Implement `S3ObjectStoreDriver` at `source/site/automojo/factories/pychestrate/object_store/s3.py` with `PRECEDENCE = 500`; source credentials via `SecretsAccessor`.
- [ ] T2.8 — Implement `copy_within` and `presign_get` in facade with capability gating (`UnsupportedOperationError` when driver disables).

### M3 — Hardening

- [ ] T3.1 — Implement `AzureBlobObjectStoreDriver` and `GcsObjectStoreDriver` with `PRECEDENCE = 500`.
- [ ] T3.2 — Emit Prometheus metrics and OTel spans per design.md Observability; verify label cardinality stays bounded by project count × driver count.
- [ ] T3.3 — Benchmark NFR-1: 1 MiB put p99 < 250 ms (local-fs), < 800 ms (S3 intra-region); 1 GiB multipart < 60 s on 1 Gbps. Fail CI on regression.
- [ ] T3.4 — Chaos test: kill the active driver mid-`put`, verify `DriverUnavailableError` surfaces and the health probe flips.
- [ ] T3.5 — Enforce `max_presign_expires_seconds` ceiling (default 3600), reject larger values with `SemanticError`.
- [ ] T3.6 — Wire audit-log subscriber stub for `object_store.object.put` / `deleted` (full impl lands with `1-audit-log`).
- [ ] T3.7 — Document each driver's config schema under `usersguide/object_store/drivers/<name>.rst`.
- [ ] T3.8 — Verify multiline errors use `os.linesep.join([...])`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (put→get identity) and Property 2 (lex-stable pagination) across both `LocalFsObjectStoreDriver` and `S3ObjectStoreDriver` (minio-in-docker in CI), 1000 cases each driver.
- [ ] TT-3 — Integration test: Phase 0.5 exit criterion — a sample `pychestrate-ext-example-objectstore` package ships a driver with `PRECEDENCE = 100`, the host loads it, it becomes active, and a put→get round-trip succeeds through it.
- [ ] TT-4 — Extension-point test: in-tree `LocalFsObjectStoreDriver` (`PRECEDENCE = 1000`) plus a test-only `EphemeralMemoryDriver` (`PRECEDENCE = 1`) registered at test setup; assert the memory driver wins and unseating it re-activates local-fs.
- [ ] TT-5 — Maintenance test: flip `maintenance.mode.changed` to `read_only` for a project; verify `put`/`delete`/`copy_within` raise `MaintenanceModeError`; `get`/`stat`/`list`/`presign_get` continue to succeed.
- [ ] TT-6 — Integrity test: inject a byte-flipping MITM between facade and driver; assert `ObjectIntegrityError` is raised with both checksums in the error message.

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
