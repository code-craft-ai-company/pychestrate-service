# 10-backup-dr — Design

## Architecture

`10-backup-dr` lives under
`source/site/ccai/pychestrate/webservice/ops/backup/`. It is a
self-contained subsystem with three substrate drivers (DB, object
store, secrets), a backup scheduler, a restore orchestrator, a drill
runner, a manifest store (the authoritative source of truth for
which backups exist and which are good), and a `backup_storage_backend`
factory whose registered implementations write the actual bytes. Every
entry point takes a caller-supplied `BackupAspects` object per
AGENTS.md — no decorators modify behavior. The feature consumes events
from `0-message-bus` only to observe DB schema migrations (so a
backup taken mid-migration is tagged with its schema version) and
publishes its own `entity.backup.*` events. The ciphertext + wrapped
DEK format for the secrets substrate comes directly from
`1-secrets-vault`; the backup layer never sees plaintext. Phase 1 ships
a minimal scheduler + local filesystem sink + DB substrate so identity
state survives; Phase 10 completes the object-store and secrets
substrates, the drill runner, and the multi-sink set. Manifests live in
the Postgres DB owned by `0-persistence` because they must survive
sink failure; the DB backup includes the manifests so a restore is
self-describing.

## Data Model

`backup_runs` — one row per initiated backup run:

- `backup_run_id: UUID` — PK.
- `kind: BackupKind` — `{FULL, INCREMENTAL}`.
- `started_at: datetime`, `completed_at: Optional[datetime]`.
- `status: BackupRunStatus` — `{IN_PROGRESS, COMPLETED, FAILED, PARTIAL}`.
- `schema_version: str` — the DB schema version at start.
- `service_version: str` — the Pychestrate version at start.
- `trigger: BackupTrigger` — `{SCHEDULED_DAILY, SCHEDULED_HOURLY,
  MANUAL, DRILL}`.
- `last_successful_drill_at: Optional[datetime]` — updated by drills.

`backup_substrate_results` — one row per (run, substrate):

- `backup_run_id: UUID` — FK.
- `substrate: BackupSubstrate` — `{DB, OBJECT_STORE, SECRETS}`.
- `backend_name: str` — registered name of the backend that stored it.
- `manifest_uri: str` — opaque sink-scoped id.
- `bytes: int`, `sha256: str`.
- `started_at: datetime`, `completed_at: Optional[datetime]`.
- `status: SubstrateStatus` — `{IN_PROGRESS, COMPLETED, FAILED}`.
- `failure_reason: Optional[str]`.
- PK is `(backup_run_id, substrate)`.

`backup_secrets_manifests` — secrets-specific bookkeeping:

- `backup_run_id: UUID` — FK.
- `bmk_key_id: str` — id of the BMK that wrapped the archive.
- `bmk_escrow_source: str` — `{HSM, KMS, SHAMIR_SPLIT}`.
- `bmk_fingerprint: str` — SHA-256 of a derived public marker (never
  the BMK itself).
- `wrapped_archive_uri: str`, `wrapped_archive_sha256: str`.

`backup_object_store_deltas` — per-increment delta records:

- `backup_run_id: UUID` — FK.
- `key: str`, `op: DeltaOp` — `{ADD, MODIFY, TOMBSTONE}`.
- `content_sha256: Optional[str]` — NULL for tombstones.
- `bytes: Optional[int]`.
- Composite index on `(backup_run_id, key)`.

`backup_retention_state` — tombstone policy bookkeeping:

- `backup_run_id: UUID` — FK.
- `substrate: BackupSubstrate`.
- `keep_until: datetime`.
- `policy_name: str`.

`restore_runs` — audit of every restore attempt:

- `restore_run_id: UUID` — PK.
- `source_backup_run_id: UUID` — FK into `backup_runs`.
- `target_env: str` — `{production, staging, drill, adhoc}`.
- `target_time: datetime`.
- `started_at: datetime`, `completed_at: Optional[datetime]`.
- `status: RestoreStatus`.
- `verification_results: JSON` — per-check results.
- `initiated_by: UUID`.

Indexes: `backup_runs(started_at DESC)`,
`backup_runs(trigger, status, started_at DESC)`,
`backup_substrate_results(substrate, status, completed_at DESC)` —
supports `latest_good_backup(substrate)`.

## Interfaces

### Public API

REST routes under `/api/v1/ops/backup/`:

- `POST /runs` — trigger a manual backup; body `{kind}`.
- `GET /runs` — list recent runs with status + substrate results.
- `GET /runs/{backup_run_id}` — detail.
- `POST /restore` — initiate restore with `{source_backup_run_id,
  target_env, target_time}`.
- `GET /restore/{restore_run_id}` — progress + verification report.
- `POST /drills` — trigger an ad-hoc drill (admin-only).
- `GET /drills` — drill history + SLO gauge.

CLI (under `8-cli`):

- `pychestrate backup run [--full|--incremental]`
- `pychestrate backup restore --from <run-id> --into <env>
  [--point-in-time <iso>]`
- `pychestrate backup drill run`
- `pychestrate backup list`

### Internal API

Module
`ccai.pychestrate.webservice.ops.backup.backup_service`:

```python
@dataclass(frozen=True)
class BackupAspects:
    """
        Caller-supplied behavior knobs — AGENTS.md "Aspects" pattern.

        :param sync: If True, wait for all substrates to reach terminal state.
        :param timeout_seconds: Per-substrate deadline.
        :param retry_budget: Attempts against transient backend errors.
        :param include_object_store: Include OBJECT_STORE substrate in this run.
        :param include_secrets: Include SECRETS substrate in this run.
        :param target_env: Restore target; one of production|staging|drill|adhoc.
        :param log_verbosity: NORMAL | DEBUG — never emits plaintext secrets.
    """
    sync: bool
    timeout_seconds: float
    retry_budget: int
    include_object_store: bool
    include_secrets: bool
    target_env: str
    log_verbosity: LogVerbosity


def build_default_backup_aspects() -> BackupAspects:
    """
        Construct the default aspects for scheduled backup runs.

        Per AGENTS.md we never use mutable defaults; callers that want
        defaults call this builder explicitly.
    """
    rtnval = BackupAspects(
        sync=True,
        timeout_seconds=3600.0,
        retry_budget=3,
        include_object_store=True,
        include_secrets=True,
        target_env="adhoc",
        log_verbosity=LogVerbosity.NORMAL
    )
    return rtnval


def run_backup(
        *,
        principal: AuthPrincipal,
        kind: BackupKind,
        trigger: BackupTrigger,
        aspects: BackupAspects
    ) -> BackupRunRecord:
    """
        Execute one backup run across the configured substrates.

        :param principal: Auth principal initiating the run (for audit).
        :param kind: FULL or INCREMENTAL.
        :param trigger: Provenance of the run (scheduled/manual/drill).
        :param aspects: Caller-supplied behavior knobs.

        :returns: The populated `BackupRunRecord` after terminal state.
        :raises: ConfigurationError, BackupBackendUnavailableError,
                 SecretsBackupKeyUnavailableError, SemanticError
    """
    ...


def restore_point_in_time(
        *,
        principal: AuthPrincipal,
        source_backup_run_id: UUID,
        target_time: datetime,
        aspects: BackupAspects
    ) -> RestoreRunRecord:
    """
        Restore the service state to `target_time` using the backup chain.

        :raises: BackupChainIncompleteError, BackupRestoreVerificationError,
                 ConfigurationError, SemanticError
    """
    ...


def run_drill(
        *,
        principal: AuthPrincipal,
        aspects: BackupAspects
    ) -> DrillRunRecord:
    """
        Execute one restore drill into an isolated environment.
    """
    ...


def latest_good_backup(
        *,
        substrate: BackupSubstrate
    ) -> Optional[BackupSubstrateResult]:
    """
        Return the most recent substrate result with status COMPLETED.

        :returns: The newest good result, or None if no good backup exists.
    """
    ...
```

Module
`ccai.pychestrate.webservice.ops.backup.substrates.db_substrate`:

```python
def snapshot_full(
        *,
        backup_run_id: UUID,
        backend: BackupStorageBackendProtocol,
        aspects: BackupAspects
    ) -> BackupSubstrateResult:
    ...


def snapshot_incremental(
        *,
        backup_run_id: UUID,
        previous_manifest_uri: str,
        backend: BackupStorageBackendProtocol,
        aspects: BackupAspects
    ) -> BackupSubstrateResult:
    ...
```

Modules `object_store_substrate.py` and `secrets_substrate.py` expose
the same two functions. `secrets_substrate` additionally loads and
verifies the BMK through `kek_escrow.load_backup_master_key()` before
any write.

Module
`ccai.pychestrate.webservice.ops.backup.kek_escrow`:

```python
def load_backup_master_key(
        *,
        source: BmkEscrowSource,
        aspects: BackupAspects
    ) -> BackupMasterKey:
    """
        Materialize the BMK from HSM / KMS / Shamir split.

        :raises: ConfigurationError if the source is unreachable or rejects.
    """
    ...
```

### Extension Surface

Factory protocol `backup_storage_backend` declared in
`ccai.pychestrate.webservice.ops.backup.factories.backup_storage_backend`:

```python
class BackupStorageBackendProtocol(FactoryProtocolBase):
    factory_protocol_name: str = "backup_storage_backend"
    protocol_schema_version: int = 1

    @classmethod
    def backend_name(cls) -> str:
        """Stable registered name, used in manifests."""
        ...

    @classmethod
    def capabilities(cls) -> BackupBackendCapabilities:
        """Declared caps: supports_multipart, supports_server_side_checksum, ..."""
        ...

    @classmethod
    def write_object(
            cls,
            *,
            backup_run_id: UUID,
            substrate: BackupSubstrate,
            key: str,
            stream: io.RawIOBase,
            aspects: BackupAspects
        ) -> BackendWriteResult:
        ...

    @classmethod
    def read_object(
            cls,
            *,
            manifest_uri: str,
            aspects: BackupAspects
        ) -> io.RawIOBase:
        ...

    @classmethod
    def list_objects(
            cls,
            *,
            backup_run_id: UUID,
            aspects: BackupAspects
        ) -> list[BackendObjectDescriptor]:
        ...

    @classmethod
    def delete_run(
            cls,
            *,
            backup_run_id: UUID,
            aspects: BackupAspects
        ) -> None:
        ...
```

Reference implementations:

- `LocalFilesystemBackupBackend` (`PRECEDENCE = 1000`) — dev/test sink
  that writes under a configured root directory.
- `S3BackupBackend` (`PRECEDENCE = 900`) — production skeleton against
  any S3-compatible endpoint using server-side-encryption-with-KMS for
  the bucket (separate from the BMK used for secrets).
- `SmbBackupBackend` (`PRECEDENCE = 900`) — air-gapped mirror target
  using the same SMB driver registered for `0-object-store`.

### Events Emitted

- `entity.backup.started` — `{backup_run_id, kind, trigger, substrates,
  started_at, initiated_by}`
- `entity.backup.completed` — `{backup_run_id, substrate, bytes,
  sha256, backend_name, duration_seconds, completed_at}`
- `entity.backup.failed` — `{backup_run_id, substrate, reason,
  failed_at}`
- `entity.backup.restore_started` — `{restore_run_id,
  source_backup_run_id, target_env, target_time}`
- `entity.backup.restore_verified` — `{restore_run_id, substrate, ok,
  checks, completed_at}`
- `entity.backup.drill_started` — `{drill_run_id, backup_run_id}`
- `entity.backup.drill_completed` — `{drill_run_id, ok, failures}`

### Events Consumed

- `entity.schema.migration.completed` — records the post-migration
  schema version so subsequent backups are tagged correctly.
- `entity.audit.sink.unhealthy` — trips a write-blocked flag so a
  backup run fails closed rather than silently skipping audit emission.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/ops/backup/
    __init__.py
    backup_service.py             # run_backup / restore_point_in_time / run_drill
    backup_aspects.py             # BackupAspects dataclass + default builder
    backup_scheduler.py           # cron-driven trigger for daily / hourly / drill
    restore_orchestrator.py       # point-in-time resolution + chain validation
    drill_runner.py               # isolated env provisioning + teardown
    manifest_store.py             # CRUD over backup_runs + *_results tables
    kek_escrow.py                 # BMK load from HSM / KMS / Shamir split
    verifier.py                   # post-restore verification pass
    substrates/
        db_substrate.py
        object_store_substrate.py
        secrets_substrate.py
    factories/
        backup_storage_backend.py
        local_fs_backend.py
        s3_backend.py
        smb_backend.py
    models.py
    restapi/
        v1/
            backup_controller.py
    events.py
    exceptions.py
```

## Key Flows

**Daily full backup (scheduled):**

1. `backup_scheduler` fires at 02:00 UTC; constructs a
   `BackupAspects(sync=True, include_object_store=True,
   include_secrets=True, target_env="adhoc")`.
2. `backup_service.run_backup(kind=FULL, trigger=SCHEDULED_DAILY)`
   inserts a `backup_runs` row, publishes
   `entity.backup.started`.
3. For each substrate in parallel (subject to per-substrate mutex):
   - DB: `db_substrate.snapshot_full` streams `pg_basebackup` output
     to `backend.write_object(substrate=DB, key=".../base.tar.zst")`,
     records SHA-256.
   - Object store: `object_store_substrate.snapshot_full` enumerates
     keys via `0-object-store` driver, streams each content blob and
     writes a manifest listing key → content_sha256.
   - Secrets: `secrets_substrate.snapshot_full` loads the BMK via
     `kek_escrow.load_backup_master_key`, reads the ciphertext +
     wrapped DEK rows straight from `1-secrets-vault`'s storage,
     assembles them into an archive, wraps the archive under the BMK
     with AES-256-GCM, and writes `secrets.backup.enc`. It records
     `bmk_key_id`, `bmk_fingerprint`, and `bmk_escrow_source` in
     `backup_secrets_manifests`.
4. Each substrate publishes `entity.backup.completed` (or `.failed`)
   on terminal state.
5. After all substrates settle, the service atomically swaps the
   manifest pointer (single UPDATE on `backup_runs.status`), emits
   the aggregate event, and returns the `BackupRunRecord`.

**Point-in-time restore into production:**

1. Operator invokes `restore_point_in_time(source_backup_run_id,
   target_time, aspects(target_env="production"))`; a second operator
   with `system:backup.restore.production` co-confirms via the UI.
2. `restore_orchestrator` computes the required chain: the youngest
   full at or before `target_time`, plus every incremental in between.
3. `restore_orchestrator` validates the chain is complete; missing
   increments raise `BackupChainIncompleteError` listing the gap.
4. DB substrate: restore base + WAL replay to `target_time`.
   Object-store substrate: apply adds/modifies/tombstones in order.
   Secrets substrate: load the BMK from the production escrow source,
   unwrap the archive, write ciphertext rows back into
   `1-secrets-vault`'s storage.
5. `verifier.run_verification` runs the checks in
   requirements.md R3, stores per-check results in
   `restore_runs.verification_results`, and publishes
   `entity.backup.restore_verified`.

**Monthly drill:**

1. `backup_scheduler` fires the drill window; `drill_runner` provisions
   a drill env (scoped DB, scoped object-store prefix, scoped
   ephemeral vault with its own BMK escrow source).
2. `backup_service.run_drill` calls `restore_point_in_time` with
   `target_env="drill"` against the latest good full.
3. On success, `last_successful_drill_at` is stamped on the backup;
   the `pychestrate_backup_drill_success_slo` gauge is set to 1.0. On
   failure the gauge is set to 0.0 and the
   `pychestrate.backup.drill_failed` alert fires.
4. `drill_runner` tears down the drill env after
   `drill_teardown_ttl_seconds`.

## Error Handling

Failure modes:

- `BackupBackendUnavailableError` — HTTP 503, retries exhausted
  against a sink. Caught and reclassified at the substrate boundary
  to add `backend_name` and `attempts` context; never swallowed.
- `SecretsBackupKeyUnavailableError` — HTTP 503, BMK escrow source
  rejected; secrets substrate fails, DB and object-store continue.
- `BackupChainIncompleteError` — HTTP 409 on restore; the response
  body lists the missing `backup_run_id`s.
- `BackupRestoreVerificationError` — HTTP 500 emitted after a restore
  whose verification pass failed; the target env is marked unhealthy.
- `BackupManifestWriteError` — HTTP 500 if the final atomic manifest
  swap fails; the run is marked PARTIAL and the prior chain remains
  canonical.
- `ConfigurationError` — raised at startup if no
  `backup_storage_backend` is registered, if the BMK escrow source is
  missing, or if `latest_good_backup(DB) is None` when the service is
  configured to require one.
- `SemanticError` — malformed aspect values, unknown substrate, or
  illegal target_env transition; NEVER caught.

Multi-line error messages use the AGENTS.md pattern:

```python
err_msg_lines = ["Backup run failed to complete a substrate."]
err_msg_lines.append("BACKUP_RUN_ID: {}".format(backup_run_id))
err_msg_lines.append("SUBSTRATE: {}".format(substrate.name))
err_msg_lines.append("BACKEND: {}".format(backend_name))
err_msg_lines.append("ATTEMPTS: {}".format(attempts))
err_msg_lines.append("LAST_CAUSE: {}".format(last_cause))
err_msg = os.linesep.join(err_msg_lines)
raise BackupBackendUnavailableError(err_msg) from last_cause
```

The secrets substrate never logs plaintext or the BMK; any error
raised from that path carries only `bmk_key_id`, `bmk_fingerprint`,
and `bmk_escrow_source` as context.

## Security Considerations

- The BMK is loaded only in the process performing the secrets backup
  or restore; it is never persisted to local disk, cache, or log. It
  is zeroized on drop via a `BackupMasterKey` wrapper analogous to
  `SecretBytes`.
- Backup artifacts written to sinks are checksummed with SHA-256; the
  checksum is carried in the manifest and re-verified on restore.
- Sink credentials live in `1-secrets-vault` (the `backup_storage_backend`
  implementation resolves them by `secret_ref`); they never appear in
  configuration files.
- RBAC permissions: `system:backup.read`, `system:backup.trigger`,
  `system:backup.restore`, `system:backup.restore.production`,
  `system:backup.drill`.
- Every entry point writes to `1-audit-log` — a failed audit write
  fails the operation closed.
- `E-extension-sandbox` capability required for a
  `backup_storage_backend` extension: `write:backup`, `read:backup`,
  `net:outbound`. Extensions without these capabilities are refused
  at registry-lookup time once the sandbox lands (Phase 8).

## Observability

Metrics (listed in NFR-3):
`pychestrate_backup_runs_total`,
`pychestrate_backup_duration_seconds`,
`pychestrate_backup_bytes_total`,
`pychestrate_backup_in_progress_gauge`,
`pychestrate_backup_restore_runs_total`,
`pychestrate_backup_restore_duration_seconds`,
`pychestrate_backup_drill_success_slo`,
`pychestrate_backup_drill_failures_total`,
`pychestrate_backup_chain_missing_increments_total`,
`pychestrate_backup_bmk_load_failures_total{source}`.

Log events: `backup.run.started`, `backup.run.completed`,
`backup.run.failed`, `backup.restore.started`,
`backup.restore.completed`, `backup.restore.verified`,
`backup.drill.started`, `backup.drill.completed`,
`backup.bmk.loaded`, `backup.bmk.rejected`,
`backup.chain.gap_detected`.

Trace spans: `backup.run`, `backup.substrate.db`,
`backup.substrate.object_store`, `backup.substrate.secrets`,
`backup.restore`, `backup.drill`, `backup.backend.call`,
`backup.verifier.check`.

## Open Questions

- Do we ship a built-in Shamir-split recombination CLI, or assume
  operators use an external tool? Initial decision: ship a minimal
  k-of-n recombiner behind `system:backup.shamir` RBAC; revisit if
  an HSM is universally available.
- Should the object-store substrate deduplicate by content_sha256
  across runs (so only new blobs are written)? Phase 10 target — yes,
  under `S3BackupBackend` when the sink supports server-side copy.
- Do we encrypt the DB backup stream under an additional
  customer-managed key, separate from the sink's own server-side
  encryption? Deferred to Phase 11; customer escalations will drive
  scope.
- Should drill environments reuse actual service binaries from
  `10-release-channels`'s stable channel, or float on the drill's own
  pin? Tentative: pin drills to stable to catch real-world restore
  drift.
