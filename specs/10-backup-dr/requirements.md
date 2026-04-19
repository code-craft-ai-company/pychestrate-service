# 10-backup-dr — Requirements

## Introduction

`10-backup-dr` is Pychestrate's backup and disaster-recovery layer. It
produces point-in-time backups of the Postgres state owned by
`0-persistence`, the object-store content addressed by `0-object-store`
(artifacts, result trees, shared results roots), and the secrets material
persisted by `1-secrets-vault` — with the secrets portion wrapped under a
master key that is *escrowed outside the backup itself*. It also runs
automated restore drills into an isolated recovery environment and treats
drill success as a first-class SLO. The feature lives in Layer 10 —
Operations; a minimal baseline ships in **Phase 1 — Identity & Projects**
(because losing the newly-stood-up identity/projects state is
unacceptable) and the full feature (multi-sink, restore drills, SLO
metrics) completes in Phase 10. The feature sits between `0-persistence`,
`0-object-store`, `1-secrets-vault`, and `1-audit-log` upstream, and
plugs storage sinks through the `backup_storage_backend` factory
protocol. Caller-driven behavior follows the AGENTS.md "Aspects" pattern
via `BackupAspects`; there are no behavior-modifying decorators
anywhere in the module.

## Requirements

### Requirement 1: Scheduled Full + Incremental Backup of All Three Substrates

**User Story:** As a site operator, I want Pychestrate to take scheduled,
crash-consistent backups of the Postgres DB, the object store, and the
secrets vault to a pluggable backup sink, so that I can restore the
service after any single-region failure within my recovery objectives.

**Acceptance Criteria (EARS):**

1. WHEN the daily backup schedule fires THEN the system SHALL take one
   full DB snapshot (pg_basebackup or logical dump, configured per sink),
   one full object-store manifest + content copy, and one
   encrypted-secrets archive, emit
   `entity.backup.started{run_id, substrates=[db,object_store,secrets]}`
   on `0-message-bus`, and tag the produced artifacts with
   `backup_run_id` and `backup_kind=full`.
2. WHEN the hourly backup schedule fires THEN the system SHALL take a
   DB WAL-archive increment, an object-store delta manifest (added,
   modified, tombstoned keys since the previous backup), and a secrets
   incremental archive covering rotations / new versions since the
   previous backup, and emit
   `entity.backup.started{kind=incremental}`.
3. WHILE a backup run is in progress the system SHALL advertise
   `pychestrate_backup_in_progress_gauge{substrate}` = 1 per substrate
   and SHALL refuse to start a second run for the same substrate.
4. WHEN each substrate finishes THEN the system SHALL publish
   `entity.backup.completed{run_id, substrate, bytes, sha256,
   backend_name, duration_seconds}`; IF any substrate fails THEN the
   system SHALL publish
   `entity.backup.failed{run_id, substrate, reason}`, mark the overall
   run `failed`, and SHALL NOT overwrite the most recent prior good
   run.
5. WHERE the `backup_storage_backend` factory reports a transient
   error THEN the system SHALL retry per `aspects.retry_budget`
   (default 3 attempts with backoff 10s / 60s / 300s) before raising
   `BackupBackendUnavailableError` and failing the run.

### Requirement 2: Secrets Backup Is Encrypted with an Escrowed Master Key

**User Story:** As a security operator, I want the secrets portion of
the backup to be readable only with a key that was *never* shipped
alongside the backup bytes, so that a compromise of a backup sink does
not yield plaintext secrets.

**Acceptance Criteria (EARS):**

1. WHEN the secrets substrate is archived THEN the system SHALL
   serialize each secret as ciphertext + wrapped DEK (the same AES-GCM
   envelope `1-secrets-vault` uses on disk), wrap the archive under a
   dedicated `backup master key` (BMK) via AES-256-GCM, and write the
   resulting `secrets.backup.enc` file to the configured
   `backup_storage_backend`. The BMK SHALL NOT be written to that sink.
2. IF no BMK is loaded at startup from the configured escrow source
   (HSM handle, KMS alias, or Shamir-split recombination file set)
   THEN the system SHALL refuse to run any secrets backup and SHALL
   raise `ConfigurationError` with a message listing candidate escrow
   sources.
3. WHEN a secrets backup completes THEN the system SHALL record in
   the backup manifest (and in `1-audit-log`) the BMK key id, its
   escrow source identifier, and the BMK fingerprint — but never the
   BMK itself or any derived bytes.
4. WHERE the BMK escrow source fails during backup THEN the system
   SHALL fail the secrets substrate of that run with
   `SecretsBackupKeyUnavailableError`, SHALL NOT proceed to write a
   plaintext or unwrapped archive, and SHALL continue the DB and
   object-store substrates of the same run (they are independent).

### Requirement 3: Point-in-Time Recovery with a Documented RPO / RTO

**User Story:** As an incident commander, I want a one-command restore
into a clean environment that reaches service-ready state within a
documented RTO and loses no more than one RPO of data, so that my
runbook is executable and measured.

**Acceptance Criteria (EARS):**

1. WHEN an operator invokes `restore_point_in_time(target_time,
   into_env, aspects)` THEN the system SHALL select the youngest full
   backup preceding `target_time` for each substrate, replay DB WAL
   increments up to `target_time`, apply object-store deltas up to the
   object-store checkpoint closest-not-after `target_time`, and
   restore secrets versions whose `created_at <= target_time`.
2. IF the selected set of backups for any substrate is incomplete
   (missing intermediate increment) THEN the system SHALL raise
   `BackupChainIncompleteError` with the missing `backup_run_id`
   listed and SHALL NOT proceed with a partial restore.
3. WHEN the restore completes THEN the system SHALL run the
   post-restore verification pass (DB schema version equals expected,
   object-store sample keys are byte-equal, secrets decrypt under the
   escrowed BMK) and SHALL publish
   `entity.backup.restore_verified{backup_run_id, substrate, ok,
   checks}`. IF any verification check fails THEN the system SHALL
   publish `entity.backup.restore_verified{ok=false}` and SHALL mark
   the restore target as unhealthy.
4. WHILE a restore is running the system SHALL expose
   `pychestrate_backup_restore_progress{substrate}` (0.0–1.0).
5. WHERE `aspects.target_env == "production"` THEN the system SHALL
   require two-operator confirmation (`1-rbac`
   `system:backup.restore.production`) and SHALL refuse otherwise.

### Requirement 4: Scheduled Restore Drills Into an Isolated Environment

**User Story:** As a reliability operator, I want Pychestrate to run
restore drills on its own backups on a cadence into a clean, isolated
environment and publish drill success/failure as a first-class metric,
so that untested backups do not silently rot.

**Acceptance Criteria (EARS):**

1. WHEN the monthly drill schedule fires THEN the system SHALL select
   the most recent good full backup for each substrate, invoke
   `restore_point_in_time(into_env=DrillEnv)` against a dedicated
   drill target (separate DB, separate object-store prefix, separate
   ephemeral secrets vault with its own BMK), run the verification
   pass, and publish `entity.backup.restore_verified{drill=true,
   ok=?}`.
2. IF the drill's verification pass fails any check THEN the system
   SHALL increment `pychestrate_backup_drill_failures_total{check}`,
   emit `entity.backup.failed{substrate, reason=drill_verification}`,
   and fire the `pychestrate.backup.drill_failed` alert route.
3. WHILE the drill environment is active the system SHALL NOT route
   production traffic to it (it is isolated at the network and
   `1-rbac` layers) and SHALL tear it down within
   `drill_teardown_ttl_seconds` (default 3600) after completion.
4. WHEN the drill completes successfully THEN the system SHALL stamp
   `last_successful_drill_at` on the `backup_runs` row of the chosen
   backup and SHALL update the `pychestrate_backup_drill_success_slo`
   gauge (1.0 == monthly SLO met, 0.0 == missed).

## Property-Based Test Requirements

### Property 1: Backup + Restore Round-Trip Preserves State

- **Invariant:** For any sequence of writes across the three substrates
  (project/variable/secret puts, object-store puts / tombstones, secret
  rotations) followed by a backup run and a restore into a fresh env,
  the restored state equals the pre-backup state: every DB row set is
  equal (modulo monotonic clocks), every object-store key has the same
  bytes and metadata, and every secret's latest non-expired version
  decrypts to the same plaintext under the escrowed BMK.
- **Generator:** hypothesis strategy producing up to 100 interleaved
  write operations across substrates, up to 20 rotations, up to 10
  tombstones, optional WAL-increment boundaries, optional failure
  injection on individual sink writes.
- **Assertion:** after restore, `state_hash(pre_backup)` equals
  `state_hash(post_restore)` where `state_hash` hashes row contents,
  object bytes, and decrypted secret plaintexts in a canonical order.
- **Sample size:** 1000 generated cases.

### Property 2: Partial Failure Never Corrupts the Good Chain

- **Invariant:** For any backup run where one or more substrate writes
  fail (BMK unavailable, backend transient error exhausting retries,
  checksum mismatch), the most recent prior successful backup for that
  substrate remains the canonical restore target — the system never
  points the pointer at a partial or failed run.
- **Generator:** hypothesis strategy producing random run sequences
  with random per-substrate failure injection (pre-write, mid-write,
  post-write before manifest update).
- **Assertion:** after the full sequence, for every substrate,
  `latest_good_backup(substrate)` is the most recent run where *that
  substrate* succeeded, and every failed run's artifacts are tagged
  `status=failed` and garbage-collected per retention policy without
  affecting the good chain.
- **Sample size:** 1000 generated cases.

### Property 3: BMK Never Co-Located with Secrets Ciphertext

- **Invariant:** For any secrets backup produced by any code path
  (scheduled, manual, drill, ad-hoc export), the bytes written to the
  `backup_storage_backend` do not contain the BMK, any BMK-derived
  key, or any plaintext DEK. Only ciphertext, wrapped DEKs, and a
  reference to the BMK key id appear.
- **Generator:** hypothesis strategy producing random secrets of 1B–4KB
  across random ref namespaces, across all three backup paths
  (scheduled, manual, drill).
- **Assertion:** for every generated case, scanning the written bytes
  for the BMK marker, the raw DEK markers, and the plaintext markers
  yields zero matches; `BackupManifest.bmk_reference` is a key id
  string only.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Recovery Objectives):**
  - **RPO = 1 hour** (hourly incremental cadence).
  - **RTO = 4 hours** for a full service restore from the youngest good
    backup into a clean environment of equivalent size.
  - **Full backup frequency:** daily at 02:00 UTC (configurable).
  - **Incremental backup frequency:** hourly on the top of the hour.
  - **Restore drill frequency:** monthly (first Saturday, 03:00 UTC)
    and on-demand; **monthly drill success is an SLO** with a 1-miss
    annual budget.
  - **Backup retention:** 35 daily fulls + 168 hourly increments
    (default; per-sink configurable).
- **NFR-2 (Security):** BMK is *never* written to a `backup_storage_backend`;
  escrow sources are HSM handle, KMS alias, or Shamir-split file set
  (k-of-n, default 3-of-5). Every backup and restore action is emitted
  to `1-audit-log`; failed audit writes fail the operation. `1-rbac`
  permissions gate every entry point: `system:backup.read`,
  `system:backup.trigger`, `system:backup.restore`,
  `system:backup.restore.production`. Backup artifacts written to a
  sink are checksummed (SHA-256) and the checksum is carried in the
  manifest and the emitted event.
- **NFR-3 (Observability):** emit
  `pychestrate_backup_runs_total{substrate,outcome}`,
  `pychestrate_backup_duration_seconds{substrate}` (histogram),
  `pychestrate_backup_bytes_total{substrate,backend}` (counter),
  `pychestrate_backup_in_progress_gauge{substrate}`,
  `pychestrate_backup_restore_runs_total{outcome,target_env}`,
  `pychestrate_backup_restore_duration_seconds{target_env}`,
  `pychestrate_backup_drill_success_slo` (gauge),
  `pychestrate_backup_drill_failures_total{check}`,
  `pychestrate_backup_chain_missing_increments_total{substrate}`. Log
  events: `backup.run.started`, `backup.run.completed`,
  `backup.run.failed`, `backup.restore.started`,
  `backup.restore.completed`, `backup.restore.verified`,
  `backup.drill.started`, `backup.drill.completed`,
  `backup.bmk.loaded`. Trace spans: `backup.run`,
  `backup.substrate.db`, `backup.substrate.object_store`,
  `backup.substrate.secrets`, `backup.restore`, `backup.drill`,
  `backup.backend.call`.
- **NFR-4 (Reliability):** A single failing substrate SHALL NOT abort
  the other two substrates of the same run. A crash mid-backup SHALL
  leave the prior good chain intact (atomic manifest swap at the end).
  The secrets BMK SHALL be loaded at service startup and re-verified
  before each secrets backup; a failing re-verification SHALL fail
  secrets backups closed.

## Out of Scope

- Cold-tier lifecycle of old backups across retention policies —
  consumes `2-retention-policies` factories.
- Multi-region active-active replication — out of scope for this
  layer; solved at the infra level.
- Encrypting the DB backup stream itself under a customer-managed key —
  Phase 11+; tracked by `Open Questions` in design.md.
- Service binary / container image backup — owned by
  `10-release-channels` (the release manifest is the source of truth
  for binaries; this feature backs up *state*).

## Dependencies

- **Depends on:** `0-persistence`, `0-object-store`, `0-message-bus`,
  `1-secrets-vault`, `1-audit-log`, `1-rbac`, `E-extension-host`,
  `E-factory-protocols`.
- **Depended on by:** `2-retention-policies` (consults backup
  retention), incident runbooks for every other layer.
- **Extension points exposed:** `factory: backup_storage_backend` —
  local filesystem (dev), S3/S3-compatible, Azure Blob, GCS, SMB/NFS
  (air-gapped mirror), custom. Reference implementation
  `LocalFilesystemBackupBackend` ships in-tree for dev/test; a stock
  `S3BackupBackend` skeleton ships for production wiring. See
  implementation-plan.md Layer 10 and Phases 1 / 10.
