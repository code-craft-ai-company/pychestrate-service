# 1-secrets-vault — Tasks

## Milestones

- **M1 — Skeleton:** `SecretBytes` wrapper, `SecretsAspects` dataclass,
  KEK loader, local AES-GCM backend, basic `put_secret` / `read_secret`
  with ACL enforcement, audit integration.
- **M2 — Core Behavior:** Rotation with grace window, outbox for
  async writes, `secrets_backend` factory protocol + router,
  `HashicorpVaultSecretsBackend` and `AwsSecretsManagerBackend`
  skeletons, REST surface.
- **M3 — Hardening:** Metrics/logs/traces, rate limiting, audit
  fail-closed, property-based leak tests, Sphinx docs, out-of-tree
  backend extension exercised.

## Tasks

### M1 — Skeleton

- [x] T1.1 — Implement `SecretBytes` with zeroize-on-drop and
      `__repr__ = "<redacted>"`.
- [x] T1.2 — Implement `SecretsAspects` dataclass + `build_default_aspects`
      helper (no mutable defaults anywhere).
- [~] T1.3 — Implement `kek_loader.load_kek_at_startup` with file,
      env, and KMS shim sources; bail with `ConfigurationError` on
      failure. *(File + env sources implemented; KMS shim deferred until
      the KMS protocol lands.)*
- [x] T1.4 — Land the `secrets`, `secret_versions`, `secret_acls`,
      `secret_outbox` tables via an `EntityMigrationExtension` pack.
      *(Models in `secrets/models.py`; Alembic migration
      004_phase1_identity_tables creates ``phase1_secrets``,
      ``phase1_secret_versions`` (with ``ciphertext_bytes`` column),
      ``secret_acls``, and ``secret_outbox``. ``phase1_`` prefix is the
      parallel-run naming; Phase 10 cut-over renames to the spec names.)*
- [x] T1.5 — Declare `SecretsBackendProtocol` `FactoryProtocolBase`
      with `protocol_schema_version = 1`.
- [x] T1.6 — Ship `LocalEncryptedSecretsBackend` at `PRECEDENCE = 1000`
      claiming `namespace_pattern = "*"` and implementing AES-GCM +
      DEK wrap. *(Fresh 256-bit DEK and 96-bit nonce per encrypt;
      DEK wrapped under the active KEK via NIST AES Key Wrap (RFC 3394);
      AEAD associated-data is the ``secret_ref`` so ciphertext cannot be
      substituted across secrets.)*
- [x] T1.7 — Implement `secrets_service.put_secret` and
      `read_secret` with ACL enforcement and audit emission inside
      the same transaction as the write.
      *(ACL: system:secrets.admin for write, system:secrets.read or
      owner-match for read. Audit emission via ``audit_writer.capture_event``
      inside the same session so commit atomically publishes the secret
      row and the audit row.)*

### M2 — Core Behavior

- [ ] T2.1 — Implement `secrets_router.resolve_backend` with glob
      pattern matching and precedence tie-break.
- [ ] T2.2 — Implement `rotate_secret` with grace window and the
      `rotation.sweeper` background task that flips superseded
      versions to expired.
- [ ] T2.3 — Implement `force_expire_secret` bypassing the grace
      window and emitting `entity.secret.force_expired`.
- [ ] T2.4 — Implement `outbox.enqueue_write` and
      `outbox.flush_pending` with exponential backoff that honors
      `SecretsAspects.retry_budget`.
- [ ] T2.5 — Ship `HashicorpVaultSecretsBackend` skeleton as an
      in-tree guidance implementation.
- [ ] T2.6 — Ship `AwsSecretsManagerBackend` skeleton.
- [ ] T2.7 — Wire REST controllers for create, read (metadata),
      rotate, delete, list.
- [ ] T2.8 — Implement ACL mutation endpoints and emit
      `entity.secret.acl.changed`.

### M3 — Hardening

- [ ] T3.1 — Emit every metric in requirements.md NFR-3 and add the
      `secrets.backend.call` trace span per backend call.
- [ ] T3.2 — Implement rate limiting on `read_secret` per principal
      (100 rps default, configurable).
- [ ] T3.3 — Wire `entity.audit.sink.unhealthy` consumer that trips
      the write-blocked flag; writes fail with
      `AuditUnavailableError`.
- [ ] T3.4 — Add the multi-line error messages built via
      `os.linesep.join(...)` listed in design.md Error Handling.
- [ ] T3.5 — Benchmark local `read_secret` against a warm cache and
      hold < 10 ms p95.
- [ ] T3.6 — Generate Sphinx docs for public and internal API and
      the `secrets_backend` contract.
- [ ] T3.7 — Ship an out-of-tree `pychestrate-ext-secrets-fixture`
      at `PRECEDENCE = 500` claiming `project:testfixture:*`; the
      integration suite exercises the delegated path end-to-end.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS acceptance criterion in
      Requirements 1–4.
- [ ] TT-2 — Hypothesis-based property tests: Property 1 (reads
      produce exactly one audit record), Property 2 (rotation grace
      preserves readers), Property 3 (plaintext never leaks to
      logs), 1000 cases each. Property 3's marker-alphabet scan
      asserts zero log hits and that `secret.value` is always
      `"<redacted>"`.
- [ ] TT-3 — Integration test: configure two backends with
      different `namespace_pattern`s, write to each, rotate, force
      expire; confirm audit records appear exactly once per action
      and `1-authentication` password pepper reads succeed through
      the local backend.
- [ ] TT-4 — Extension-point test: out-of-tree backend claims
      `project:testfixture:*` at `PRECEDENCE = 500`; writes/reads
      route to it while the default backend continues to serve
      unrelated refs.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface has at least one in-tree reference
      implementation (`LocalEncryptedSecretsBackend`) and one
      test-only override using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators, Aspects-style
      behavior parameters — no `@retry`)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 1 —
      Identity & Projects in specs/implementation-plan.md
