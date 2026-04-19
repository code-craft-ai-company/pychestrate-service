# 10-backup-dr — Tasks

## Milestones

- **M1 — Skeleton (Phase 1 baseline):** Manifest schema, `BackupAspects`,
  `backup_storage_backend` factory protocol, `LocalFilesystemBackupBackend`,
  DB substrate full + incremental, scheduler wiring, CLI + REST trigger,
  audit integration. Enough to recover identity/projects state.
- **M2 — Core Behavior (Phase 10):** Object-store substrate, secrets
  substrate with BMK escrow (HSM / KMS / Shamir), restore orchestrator
  with chain validation, post-restore verifier, `S3BackupBackend`,
  `SmbBackupBackend`.
- **M3 — Hardening (Phase 10):** Monthly drill runner with isolated env,
  drill SLO gauge + alert route, metrics / logs / traces, multi-sink
  retention, production two-operator confirmation, Sphinx docs,
  out-of-tree sink extension.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Land `backup_runs`, `backup_substrate_results`,
      `backup_secrets_manifests`, `backup_object_store_deltas`,
      `backup_retention_state`, `restore_runs` tables via an
      `EntityMigrationExtension` pack.
- [ ] T1.2 — Implement `BackupAspects` dataclass and
      `build_default_backup_aspects()` (no mutable defaults).
- [ ] T1.3 — Declare `BackupStorageBackendProtocol` `FactoryProtocolBase`
      with `protocol_schema_version = 1`.
- [ ] T1.4 — Ship `LocalFilesystemBackupBackend` at `PRECEDENCE = 1000`
      writing under a configured root.
- [ ] T1.5 — Implement `db_substrate.snapshot_full` via `pg_basebackup`
      and `snapshot_incremental` via WAL archive; stream to backend.
- [ ] T1.6 — Implement `manifest_store` CRUD for the six tables with the
      atomic `backup_runs.status` swap at the end of a run.
- [ ] T1.7 — Wire `backup_scheduler` with the daily + hourly cron
      triggers; firing invokes `backup_service.run_backup`.
- [ ] T1.8 — Implement `backup_service.run_backup` for DB-only runs;
      publish `entity.backup.started|completed|failed`.
- [ ] T1.9 — Wire REST controller (`/api/v1/ops/backup/runs` POST/GET)
      and the `pychestrate backup run|list` CLI commands.
- [ ] T1.10 — Emit every backup action to `1-audit-log`; fail closed on
      audit sink unavailability.

### M2 — Core Behavior

- [ ] T2.1 — Implement `object_store_substrate.snapshot_full` and
      `snapshot_incremental` with manifest + delta tracking
      (ADD / MODIFY / TOMBSTONE).
- [ ] T2.2 — Implement `kek_escrow.load_backup_master_key` with the
      three sources (HSM handle, KMS alias, Shamir split file set)
      behind a `BmkEscrowSource` enum; `BackupMasterKey` wrapper
      zeroizes on drop.
- [ ] T2.3 — Implement `secrets_substrate.snapshot_full` /
      `snapshot_incremental` — reads ciphertext + wrapped DEK rows
      directly from `1-secrets-vault` storage, wraps the assembled
      archive under the BMK with AES-256-GCM, writes
      `secrets.backup.enc`. Records `bmk_key_id`,
      `bmk_fingerprint`, and `bmk_escrow_source` in
      `backup_secrets_manifests`.
- [ ] T2.4 — Implement `restore_orchestrator` with point-in-time chain
      computation and `BackupChainIncompleteError` on gaps.
- [ ] T2.5 — Implement `verifier.run_verification` covering DB schema
      version match, object-store sample byte-equality, and secrets
      decrypt-under-BMK smoke tests; persist per-check results.
- [ ] T2.6 — Implement `backup_service.restore_point_in_time` with the
      production `system:backup.restore.production` two-operator
      confirmation.
- [ ] T2.7 — Ship `S3BackupBackend` at `PRECEDENCE = 900` with
      multipart upload and SHA-256 verification.
- [ ] T2.8 — Ship `SmbBackupBackend` at `PRECEDENCE = 900` reusing the
      `0-object-store` SMB driver.
- [ ] T2.9 — Wire REST restore controller (`/api/v1/ops/backup/restore`)
      and the `pychestrate backup restore` CLI.

### M3 — Hardening

- [ ] T3.1 — Implement `drill_runner`: isolated env provisioning,
      restore invocation, teardown after `drill_teardown_ttl_seconds`.
- [ ] T3.2 — Implement `backup_service.run_drill` and the monthly cron
      in `backup_scheduler`; stamp `last_successful_drill_at`.
- [ ] T3.3 — Emit `pychestrate_backup_drill_success_slo` gauge and
      wire the `pychestrate.backup.drill_failed` alert route via
      `7-alerts-budgets`.
- [ ] T3.4 — Emit every metric in requirements.md NFR-3 and add the
      trace spans (`backup.run`, `backup.substrate.*`, `backup.restore`,
      `backup.drill`, `backup.backend.call`).
- [ ] T3.5 — Implement retention sweeper consuming
      `backup_retention_state`; enforce 35 daily fulls + 168 hourly
      increments by default, never deleting a run that is the
      latest-good for its substrate.
- [ ] T3.6 — Add multi-line error messages built via
      `os.linesep.join(...)` per design.md Error Handling.
- [ ] T3.7 — Generate Sphinx docs for public + internal APIs and the
      `backup_storage_backend` contract.
- [ ] T3.8 — Ship an out-of-tree
      `pychestrate-ext-backup-sink-airgap` example package with its
      own backend at `PRECEDENCE = 500`; the integration suite
      exercises the delegated path end-to-end.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS acceptance criterion in
      Requirements 1–4 (schedules, BMK escrow, point-in-time restore,
      drill success + failure paths).
- [ ] TT-2 — Hypothesis property tests: Property 1 (backup + restore
      round-trip preserves state), Property 2 (partial failure never
      corrupts the good chain), Property 3 (BMK never co-located with
      secrets ciphertext), 1000 cases each. Property 3 scans every
      written byte stream for the BMK and plaintext markers and asserts
      zero hits; `BackupManifest.bmk_reference` must be a key id only.
- [ ] TT-3 — Integration test: configure two sinks
      (`LocalFilesystemBackupBackend`, `S3BackupBackend`), run a full +
      two incrementals, restore to point-in-time into a drill env,
      verify decrypted secrets equal pre-backup values; trigger a
      missing-increment gap and confirm `BackupChainIncompleteError`
      with the exact missing run id.
- [ ] TT-4 — Extension-point test: out-of-tree
      `pychestrate-ext-backup-sink-airgap` registers at
      `PRECEDENCE = 500` claiming production substrates; runs route to
      it; in-tree defaults continue to serve drill env; confirm metrics
      label `backend` reflects the override.
- [ ] TT-5 — Drill SLO test: simulate a month of successful drills and
      a month with one failure; assert the gauge flips to 0.0 on
      failure, the alert fires, and recovers on the next success.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface has at least one in-tree reference
      implementation (`LocalFilesystemBackupBackend`, `S3BackupBackend`)
      and one test-only override using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3,
      including `pychestrate_backup_drill_success_slo`
- [ ] RPO = 1 hour and RTO = 4 hours validated in the Phase 10 drill
      and documented in the runbook
- [ ] Monthly drill SLO configured with a 1-miss annual budget and
      wired to `pychestrate.backup.drill_failed`
- [ ] Sphinx docs generated for public and internal APIs and the
      `backup_storage_backend` contract
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators, Aspects-style behavior
      parameters — no `@retry`)
- [ ] No TODO / FIXME left in shipped code
- [ ] Phase 1 (baseline) and Phase 10 (full) Definition of Done entries
      in specs/implementation-plan.md both list this feature
