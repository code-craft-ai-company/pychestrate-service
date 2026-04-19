# 0-object-store — Design

## Architecture

The object store is a thin `ObjectStore` facade that dispatches to a single
active `ObjectStoreDriver` selected by the extension host at startup from
the `object_store_driver` factory protocol registry. The facade enforces
cross-cutting concerns the drivers must not reimplement: key validation,
project-slug scoping, maintenance-mode gating, multipart chunking,
SHA-256 integrity, retry policy via `Aspects`, metrics, traces, and log
events. Drivers are *transport only*: they accept already-validated keys
and already-chunked payloads. Authoritative source of truth for object
bytes is the backend (SMB share / S3 bucket / etc.); Pychestrate holds no
local cache beyond in-flight multipart state. The Phase 0.5 exit criterion
hinges on this feature acquiring its SMB and S3 drivers *through the
registry*, so the facade must work when there are zero in-tree driver
implementations and a single out-of-tree one.

## Data Model

No persistent entity tables are owned by this feature. In-memory state:

- `active_driver: ObjectStoreDriver` — singleton loaded at startup.
- `driver_capabilities: DriverCapabilities` — precomputed once per driver.
- `multipart_sessions: dict[UUID, MultipartSession]` — short-lived,
  correlated to in-flight large uploads.

Per-call value types:

- `ObjectKey: str` — validated against `^[A-Za-z0-9/_.\-]{1,1024}$`
- `ObjectPutResult`:
  - `key: str`
  - `etag: str`
  - `size_bytes: int`
  - `backend_path: str`
  - `uploaded_at: datetime`
- `ObjectStat`:
  - `key: str`
  - `size_bytes: int`
  - `etag: str`
  - `content_type: str | None`
  - `last_modified: datetime`
- `ObjectListPage`:
  - `entries: list[ObjectStat]`
  - `continuation: str | None`

Project-slug index state lives with `2-projects`; this feature consults it
read-only via an injected `ProjectLookup` callable.

## Interfaces

### Public API

N/A — internal to the service. External access to objects flows through
`5-artifact-store` endpoints that delegate to this layer, or presigned URLs
the driver generates.

### Internal API

```python
class ObjectStore:
    def __init__(
        self,
        driver: ObjectStoreDriver,
        project_lookup: ProjectLookup,
        maintenance_gate: MaintenanceGate,
        config: ObjectStoreConfig
    ) -> None:
        self._driver = driver
        self._project_lookup = project_lookup
        self._maintenance_gate = maintenance_gate
        self._config = config
        return

    def put(
        self,
        key: str,
        source: BinaryIO | Path,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
        aspects: PutAspects | None = None
    ) -> ObjectPutResult:
        """
            Write an object to the backend.

            :param key: Scoped key starting with a valid project slug.
            :param source: File path or binary stream source.
            :param content_type: MIME type hint for the backend.
            :param metadata: Optional backend metadata map.
            :param aspects: Behavior parameters (retry, timeout, logging).

            :returns: ObjectPutResult describing the stored object.
            :raises: SemanticError, MaintenanceModeError,
                     ObjectIntegrityError, ObjectStoreError
        """
        ...

    def get(
        self,
        key: str,
        aspects: GetAspects | None = None
    ) -> BinaryIO:
        """
            Open a read stream for an object.

            :param key: Scoped key.
            :param aspects: Behavior parameters.

            :returns: A readable binary stream; caller must close.
            :raises: ObjectNotFoundError, ObjectStoreError
        """
        ...

    def stat(
        self,
        key: str
    ) -> ObjectStat:
        """
            Fetch object metadata without body transfer.

            :param key: Scoped key.

            :returns: ObjectStat.
            :raises: ObjectNotFoundError, ObjectStoreError
        """
        ...

    def list(
        self,
        prefix: str,
        limit: int,
        continuation: str | None = None
    ) -> ObjectListPage:
        """
            List objects under a prefix in lexicographic order.

            :param prefix: Key prefix including the project slug.
            :param limit: Maximum entries per page.
            :param continuation: Opaque continuation token or None.

            :returns: ObjectListPage.
            :raises: ObjectStoreError
        """
        ...

    def delete(
        self,
        key: str
    ) -> bool:
        """
            Delete a single object.

            :param key: Scoped key.

            :returns: True if deleted, False if not present.
            :raises: MaintenanceModeError, ObjectStoreError
        """
        ...

    def copy_within(
        self,
        source_key: str,
        dest_key: str
    ) -> ObjectPutResult:
        """
            Server-side copy within the same backend.

            :param source_key: Source key.
            :param dest_key: Destination key.

            :returns: ObjectPutResult for the destination.
            :raises: MaintenanceModeError, ObjectNotFoundError,
                     UnsupportedOperationError, ObjectStoreError
        """
        ...

    def presign_get(
        self,
        key: str,
        expires_seconds: int
    ) -> str:
        """
            Build a presigned GET URL for the object.

            :param key: Scoped key.
            :param expires_seconds: URL validity window, capped by config.

            :returns: A URL the caller can hand to a client.
            :raises: UnsupportedOperationError, ObjectStoreError
        """
        ...
```

### Extension Surface

Factory protocol declared here:

```python
class ObjectStoreDriverProtocol(FactoryProtocolBase):
    """
        Contract for object_store_driver implementations.

        Every implementing class inherits FactoryExtension, sets
        factory_protocol_name = "object_store_driver", and assigns an
        integer PRECEDENCE (lower wins).
    """
    factory_protocol_name: str = "object_store_driver"

    @classmethod
    def open(
        cls,
        config: DriverConfig,
        secrets: SecretsAccessor
    ) -> ObjectStoreDriver:
        """
            Instantiate and connect the driver.

            :param config: Driver-specific configuration.
            :param secrets: Read-only accessor for vault secrets.

            :returns: A ready-to-use ObjectStoreDriver.
            :raises: ConfigurationError, DriverUnavailableError
        """
        ...

    @classmethod
    def capabilities(cls) -> DriverCapabilities:
        """
            Report what this driver supports.

            :returns: DriverCapabilities (presign_get, server_side_copy,
                      server_side_checksum, multipart).
            :raises: None
        """
        ...
```

`ObjectStoreDriver` instance methods required on every driver: `put_single`,
`put_multipart_initiate`, `put_multipart_part`, `put_multipart_complete`,
`put_multipart_abort`, `get`, `stat`, `list`, `delete`, `copy_within`,
`presign_get`, `close`.

Reference implementations shipped in-tree (under
`source/site/automojo/factories/pychestrate/object_store/`):

- `LocalFsObjectStoreDriver` — `PRECEDENCE = 1000`. Backed by a filesystem
  path (works for dev, single-node, and NFS/SMB mounts). Always available;
  used as the fallback.
- `S3ObjectStoreDriver` — `PRECEDENCE = 500`. Backed by `boto3`; supports
  presigned GET, server-side copy, server-side SHA-256.
- `AzureBlobObjectStoreDriver` — `PRECEDENCE = 500`.
- `GcsObjectStoreDriver` — `PRECEDENCE = 500`.

Operators (or out-of-tree extensions) override by shipping a driver with a
lower `PRECEDENCE` (e.g., `100` for a site-specific isilon driver).

### Events Emitted

On `0-message-bus`:

- `object_store.driver.activated` — `{driver_class: str, capabilities:
  DriverCapabilities}`
- `object_store.driver.failed` — `{driver_class: str, error: str}`
- `object_store.object.put` — `{key: str, size_bytes: int, project: str,
  etag: str}`
- `object_store.object.deleted` — `{key: str, project: str}`

Consumers: `7-metrics-ingest`, `1-audit-log`, `5-artifact-store`.

### Events Consumed

- `maintenance.mode.changed` (from `0-maintenance-mode`) — updates the
  in-memory `MaintenanceGate` so subsequent put/delete/copy are gated
  without a driver round-trip.
- `extension.reloaded` — re-resolves the active driver through the
  extension host.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/`:

- `object_store/__init__.py`
- `object_store/config.py` — `ObjectStoreConfig`, `DriverConfig` dataclasses.
- `object_store/facade.py` — `ObjectStore` class (the public internal API).
- `object_store/key_validation.py` — `validate_key`, `split_project_slug`.
- `object_store/multipart.py` — chunking, parallel upload, retry orchestration.
- `object_store/integrity.py` — SHA-256 streaming checksum.
- `object_store/aspects.py` — `PutAspects`, `GetAspects` with retry policy.
- `object_store/errors.py` — `ObjectNotFoundError`, `ObjectIntegrityError`,
  `MaintenanceModeError`, `UnsupportedOperationError`,
  `DriverUnavailableError`.
- `object_store/protocol.py` — `ObjectStoreDriverProtocol` factory protocol.
- `object_store/driver_base.py` — abstract `ObjectStoreDriver` base.
- `object_store/hooks.py` — startup/shutdown hooks and driver resolution.

Factories live under
`source/site/automojo/factories/pychestrate/object_store/` — one file per
reference driver as listed above.

## Key Flows

### Flow 1 — Startup driver resolution

1. Host startup hook priority `30` fires.
2. Hook queries `E-extension-host` for `object_store_driver` implementations
   ordered by `PRECEDENCE`.
3. Hook calls `driver_class.open(config, secrets)` on the lowest-PRECEDENCE
   driver; on `DriverUnavailableError` falls through to the next.
4. First successful driver becomes `active_driver`; its `capabilities()`
   result is cached.
5. `object_store.driver.activated` is published.

### Flow 2 — Put with multipart

1. Caller invokes `store.put("proj-a/run-42/artifacts/x.bin", path,
   content_type="application/octet-stream")`.
2. Facade validates key regex + project slug via `project_lookup`.
3. Facade checks `maintenance_gate` for the project scope.
4. If `source` size ≥ `multipart_threshold_bytes` the facade initiates a
   multipart session through the driver, chunks the source, uploads parts
   in parallel with the retry policy from `PutAspects`, then completes.
5. Facade computes SHA-256 on the fly; if driver does not provide etag,
   returns `sha256:<hex>` as etag.
6. Facade emits `object_store.object.put` and records metrics.

### Flow 3 — Maintenance-mode drain

1. `maintenance.mode.changed` arrives on the bus with
   `{scope: "project:proj-a", mode: "read_only"}`.
2. Facade's subscriber updates `MaintenanceGate`.
3. Subsequent `put`/`delete`/`copy_within` for `proj-a` raise
   `MaintenanceModeError` before touching the driver.
4. Read ops (`get`, `stat`, `list`, `presign_get`) continue unaffected.

## Error Handling

- `ObjectNotFoundError`, `ObjectIntegrityError`,
  `MaintenanceModeError`, `UnsupportedOperationError`: domain errors,
  bubble to the caller. Request handlers translate to 404 / 409 /
  503 / 501 respectively.
- `DriverUnavailableError` during startup: the facade records the failure
  and advances to the next candidate driver. During runtime, it bubbles to
  the caller (503) but the active driver also flips its health probe
  status so subsequent calls short-circuit until recovery.
- Driver-native exceptions (e.g., `botocore.ClientError`) are caught ONCE
  at the driver-base boundary, reclassified with multiline context
  (operation, key, driver_class, cause) as `ObjectStoreError`, and
  re-raised. No swallowing.
- `SemanticError` from invalid project slug, invalid key regex, or use
  after `close()`: never caught.
- `ConfigurationError` from malformed driver config: bubbles to host,
  process exits code 78.

Example multiline error:

```python
err_msg_lines = ["Object put integrity check failed."]
err_msg_lines.append("KEY: {}".format(key))
err_msg_lines.append("DRIVER: {}".format(self._driver.__class__.__name__))
err_msg_lines.append("EXPECTED SHA256: {}".format(expected))
err_msg_lines.append("OBSERVED SHA256: {}".format(observed))

err_msg = os.linesep.join(err_msg_lines)
raise ObjectIntegrityError(err_msg) from None
```

## Security Considerations

- Key regex blocks path traversal and null bytes.
- Driver credentials sourced from `1-secrets-vault`; never logged.
  `DriverConfig.__repr__` redacts credential-shaped fields.
- Presigned URLs capped at `max_presign_expires_seconds` (default 3600).
- RBAC gating for put/delete is enforced at `5-artifact-store` /
  `5-shared-results-backend` — this feature authenticates that its caller
  is *in-process* only; it trusts project-slug scoping.
- All put/delete/presign calls are audited by a `1-audit-log` subscriber
  on `object_store.object.put` and `object_store.object.deleted`.

## Observability

Metrics:

- `pychestrate_object_store_put_duration_seconds{driver,project}` — histogram
- `pychestrate_object_store_get_duration_seconds{driver,project}` — histogram
- `pychestrate_object_store_list_duration_seconds{driver,project}` — histogram
- `pychestrate_object_store_bytes_uploaded_total{driver,project}` — counter
- `pychestrate_object_store_bytes_downloaded_total{driver,project}` — counter
- `pychestrate_object_store_errors_total{driver,operation,error_kind}` — counter
- `pychestrate_object_store_multipart_inflight{driver}` — gauge
- `pychestrate_object_store_driver_available{driver}` — gauge (0/1)

Log events:

- `pychestrate.object_store.driver.activated`
- `pychestrate.object_store.driver.failed`
- `pychestrate.object_store.put.completed`
- `pychestrate.object_store.put.failed`
- `pychestrate.object_store.integrity.mismatch`
- `pychestrate.object_store.maintenance.blocked`

Trace spans:

- `pychestrate.object_store.put` — attrs `driver`, `project`, `key`,
  `size_bytes`, `multipart`
- `pychestrate.object_store.get`
- `pychestrate.object_store.list`
- `pychestrate.object_store.presign_get`

Dashboards: driver-health tile under `9-admin-ui`; artifact-transfer
throughput under `7-orchestration-metrics`.

## Open Questions

- Do we require drivers to support server-side SHA-256, or accept
  streaming client-side checksum as an alternative? Timebox: Phase 0 exit
  before landing S3 driver.
- Multipart worker count (default 4) — tune against `5-shared-results-backend`
  workload once measured. Timebox: Phase 3 exit.
- Do we expose `presign_put` as well, or force all writes through the
  service to preserve audit? Timebox: Phase 3 exit — `5-shared-results-backend`
  will drive the decision.
