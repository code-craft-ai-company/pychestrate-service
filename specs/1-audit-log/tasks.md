# 1-audit-log — Tasks

## Milestones

- **M1 — Skeleton:** `audit_records` table with INSERT-only grants,
  `capture_event` writing a single row with a simple hash chain,
  in-tree `LocalDatabaseAuditSink`, bus subscriber wired to a minimal
  set of kinds (`audit.user.created`, `audit.role.assigned`,
  `audit.secret.accessed`).
- **M2 — Core Behavior:** Full `AuditEventTypeExtension` catalog, per-sink
  outbox, `audit_sink` factory protocol with `JsonFileAuditSink`
  reference, `verify_audit_chain`, REST query and verify endpoints,
  canonical-sink-unhealthy signaling.
- **M3 — Hardening:** Splunk HEC and SIEM syslog skeletons, metrics /
  logs / traces, dead-letter for `audit.unknown`, perf baseline,
  Sphinx docs, out-of-tree sink extension exercised.

## Tasks

### M1 — Skeleton

- [x] T1.1 — Land the `audit_records`, `audit_event_catalog`,
      `audit_sink_registrations`, `audit_sink_outbox` tables with
      `REVOKE UPDATE, DELETE ON audit_records` asserted in the
      migration. *(All four models in `audit/models.py`; Alembic migration
      004_phase1_identity_tables creates them and runs a ``DO $$ ...
      REVOKE UPDATE, DELETE ON TABLE audit_records FROM <app_role>``
      guarded by ``pg_roles`` membership so environments without the
      configured role treat the REVOKE as a no-op.)*
- [x] T1.2 — Declare `AuditEventTypeExtension` resource base and ship
      `UserLifecycleAuditEvents`, `RoleBindingAuditEvents`,
      `SecretAuditEvents` in-tree.
- [x] T1.3 — Declare `AuditSinkProtocol` `FactoryProtocolBase` with
      `protocol_schema_version = 1`.
- [x] T1.4 — Ship `LocalDatabaseAuditSink` at `PRECEDENCE = 1000`
      with `is_canonical = True`.
- [x] T1.5 — Implement `audit_writer.capture_event` with canonical
      JSON serialization and SHA-256 hash chain.
- [x] T1.6 — Wire `bus_subscriber` onto the minimal Phase-1 event set
      and publish `entity.audit.emitted` after each insert.

### M2 — Core Behavior

- [ ] T2.1 — Ship `SessionAuditEvents`, `ProjectAuditEvents`,
      `FlagAuditEvents` reference `AuditEventTypeExtension`s.
- [ ] T2.2 — Implement per-sink `audit_sink_outbox` and
      `sink_dispatcher.dispatch_record` +
      `drain_sink_outbox`.
- [ ] T2.3 — Ship `JsonFileAuditSink` at `PRECEDENCE = 2000`.
- [ ] T2.4 — Implement `chain_verifier.verify_audit_chain` and the
      startup readiness probe that refuses rotation on a broken
      chain.
- [ ] T2.5 — Wire REST controllers `GET /api/v1/audit`,
      `GET /api/v1/audit/{sequence_number}`,
      `POST /api/v1/audit/verify`,
      `GET /api/v1/audit/sinks`,
      `POST /api/v1/audit/sinks/{sink_name}/replay`.
- [ ] T2.6 — Implement canonical-sink health probe and publish
      `entity.audit.sink.unhealthy` / `entity.audit.sink.healthy`.
- [ ] T2.7 — Implement `audit.unknown` fallback kind with a
      dedicated dead-letter route and the
      `pychestrate_audit_unknown_event_total{topic}` counter.

### M3 — Hardening

- [ ] T3.1 — Ship `SplunkHecAuditSink` and `SiemSyslogAuditSink`
      skeletons with TLS + credential load from
      `1-secrets-vault`.
- [ ] T3.2 — Emit every metric in requirements.md NFR-3.
- [ ] T3.3 — Emit every log event in NFR-3 and add trace spans
      `audit.capture`, `audit.chain.verify`, `audit.sink.dispatch`,
      `audit.sink.flush`.
- [ ] T3.4 — Benchmark capture overhead and hold ≤ 2 ms p95 in the
      capture path; verify sink slowness does not add > 5 ms to
      request p99.
- [ ] T3.5 — Generate Sphinx docs for public and internal API, the
      `audit_sink` contract, and the `AuditEventTypeExtension`
      base.
- [ ] T3.6 — Ship an out-of-tree `pychestrate-ext-audit-fixture`
      sample sink at `PRECEDENCE = 500` (non-canonical) to
      exercise the extension path in the integration suite.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS acceptance criterion in
      Requirements 1–4.
- [ ] TT-2 — Hypothesis-based property tests: Property 1 (exactly one
      record per mutation), Property 2 (hash chain integrity),
      Property 3 (non-blocking request path), 1000 cases each.
- [ ] TT-3 — Integration test: drive a Layer 1 mutation mix
      (create users, assign roles, write + read secrets, create
      project, toggle flag) and assert
      `audit_records.sequence_number` is contiguous, every source
      event appears exactly once, and a deliberate tamper fails
      `verify_audit_chain` at the tampered row.
- [ ] TT-4 — Extension-point test: out-of-tree non-canonical sink
      registers, receives the fan-out, and survives injected
      transient failures without affecting the canonical sink.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface has at least one in-tree reference
      implementation (`LocalDatabaseAuditSink`,
      `JsonFileAuditSink`, `UserLifecycleAuditEvents`, ...) and one
      test-only override using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 1 —
      Identity & Projects in specs/implementation-plan.md
