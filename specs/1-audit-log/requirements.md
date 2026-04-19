# 1-audit-log — Requirements

## Introduction

`1-audit-log` is the append-only record of every configuration, secret,
and dispatch action Pychestrate takes. It is the forensic and compliance
backbone of the service: every other Layer 1+ feature emits entity
events, and the audit log turns those events into durable, ordered,
tamper-evident rows that operators and auditors can query. It ships in
**Phase 1 — Identity & Projects** and sits below every producing feature
on the consumption graph. The feature declares the `audit_sink` factory
protocol so operators can route records to local storage, a SIEM
forwarder, or a Splunk HEC destination, and declares the
`AuditEventTypeExtension` resource base so extension packs can register
new event kinds with structured payload schemas.

## Requirements

### Requirement 1: Capture Every Mutation

**User Story:** As an auditor, I want every mutating action in
Pychestrate to produce an audit row, so that I can reconstruct who did
what and when without gaps.

**Acceptance Criteria (EARS):**

1. WHEN any feature publishes an `entity.*` event to `0-message-bus`
   that is registered as an auditable event kind THEN the system SHALL
   capture exactly one `AuditRecord` row with a monotonic sequence
   number, event kind, actor, target, and structured payload.
2. IF the sink for an audit event is unavailable THEN the system
   SHALL hold the record in a durable local outbox and SHALL NOT
   acknowledge the source operation as complete — write-producing
   features fail closed (coordinated via `entity.audit.sink.unhealthy`
   back to those features).
3. WHEN the sink becomes available again THEN the system SHALL drain
   the outbox in strict sequence order and publish
   `entity.audit.sink.healthy`.
4. WHERE an incoming event kind is not in the registered catalog
   THEN the system SHALL still capture it under the reserved kind
   `audit.unknown` with the original payload preserved for later
   classification, and SHALL emit
   `pychestrate_audit_unknown_event_total{topic}`.

### Requirement 2: Append-Only Tamper Evidence

**User Story:** As a compliance officer, I want the audit log to be
provably append-only, so that evidence cannot be silently altered.

**Acceptance Criteria (EARS):**

1. WHEN a new record is appended THEN the system SHALL compute
   `record_hash = SHA-256(previous_hash || canonical_payload)` and
   store it, producing a hash chain.
2. IF any attempt is made to UPDATE or DELETE an existing audit row
   through the REST API THEN the system SHALL reject the request
   with HTTP 403 and SHALL NOT expose any controller path that
   performs such operations.
3. WHILE an operator runs `verify_audit_chain(from_sequence,
   to_sequence)` the system SHALL recompute the hash chain for the
   given range and return a `ChainVerificationResult` that reports
   either `ok` with the covered span or `broken` with the first
   offending sequence number.
4. WHEN rows are exported through a `audit_sink` the system SHALL
   include `sequence_number` and `record_hash` so downstream systems
   can independently verify continuity.

### Requirement 3: Pluggable Sinks

**User Story:** As an operator, I want to forward audit records to my
SIEM or Splunk HEC endpoint in addition to the local store, so that
audit data reaches the team that already monitors it.

**Acceptance Criteria (EARS):**

1. WHEN an `audit_sink` extension is registered THEN the system
   SHALL fan out every new record to that sink in declaration
   order (sorted by `PRECEDENCE`), preserving the sequence number.
2. IF any single sink's write fails THEN the system SHALL retry
   that sink independently with exponential backoff (0.5s, 2s, 8s,
   32s — capped at 60s), preserve the outbox position for that
   sink, and SHALL NOT block healthy sinks.
3. WHERE the local file/DB sink is configured as
   `is_canonical = True` the system SHALL block write-producing
   features via `entity.audit.sink.unhealthy` if *that* specific
   sink is down, irrespective of other sinks' health.
4. WHEN an extension declares a new `AuditEventTypeExtension` the
   system SHALL include the event kind in the registered catalog
   with its declared payload schema, reject mismatched payloads
   with `ConfigurationError`, and publish
   `entity.audit.catalog.reloaded`.

### Requirement 4: Query and Retention

**User Story:** As an operator, I want to query audit history by
actor, target, time range, and event kind, so that I can respond to
incidents and access reviews quickly.

**Acceptance Criteria (EARS):**

1. WHEN a caller invokes
   `GET /api/v1/audit?actor_user_id=&kind=&from_ts=&to_ts=&target_ref=`
   THEN the system SHALL return matching records paginated by
   sequence number with a maximum page size of 1000.
2. IF a request omits every filter THEN the system SHALL require a
   `from_ts` parameter, returning HTTP 400 otherwise.
3. WHILE retention policy `audit.retention_days` is set the system
   SHALL archive records older than the window to the configured
   archival sink and retain the hash chain metadata locally so
   `verify_audit_chain` still works on archived spans.

## Property-Based Test Requirements

### Property 1: Every Mutation → Exactly One Record

- **Invariant:** For any sequence of mutating actions (user
  create/update/deactivate, role assign/revoke, secret
  read/write/rotate, project update, session open/close), the
  number of committed `AuditRecord` rows equals the number of
  mutations that were accepted by their owning features, with no
  duplicates and no omissions.
- **Generator:** Strategy producing interleavings of 1–100 mutating
  actions across Layer 1 features, with random failure injection
  on the sink to exercise the outbox + recovery path.
- **Assertion:** After the interleaving completes and the outbox
  drains, the row count matches the accepted-mutation count and
  each mutation is represented by exactly one record identified by
  its source `entity.*.id`.
- **Sample size:** 1000 generated cases.

### Property 2: Hash Chain Integrity

- **Invariant:** For any prefix of appended records,
  `verify_audit_chain(1, current_sequence)` returns `ok`. For any
  deliberate mutation of a past row, `verify_audit_chain` returns
  `broken` with the mutated row's sequence number or an earlier
  sequence.
- **Generator:** Strategy producing 1–5000 appends followed by an
  optional single tamper operation (flip a byte in an existing
  row's payload hash field).
- **Assertion:** With no tamper, verify returns `ok`; with tamper,
  verify returns `broken` at ≤ the tampered sequence.
- **Sample size:** 1000 generated cases.

### Property 3: Non-Blocking Request Path

- **Invariant:** For any audit emission performed as a background
  task (non-canonical sinks), the p99 latency of the triggering
  request is not degraded by sink slowness. Specifically, injected
  sink latency of up to 5 seconds on a non-canonical sink SHALL NOT
  delay the caller by more than 5 ms beyond the no-sink baseline.
- **Generator:** Strategy producing request latencies with and
  without injected sink delay across a representative mix of
  Layer 1 endpoints.
- **Assertion:** Per-endpoint p99 with injected delay ≤ p99 baseline
  + 5 ms.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Capture-path overhead on producing
  features SHALL be ≤ 2 ms p95. **Audit write SHALL never block the
  request path** beyond the transactional hop into the outbox — the
  sink-fanout writes happen out-of-band.
- **NFR-2 (Security):** Every audit row SHALL carry the acting
  principal (user id or service identity) and the target entity
  ref. Audit-log admin (replay, re-verify) requires
  `system:audit.admin`; read requires `system:audit.read`. The
  audit table SHALL have no UPDATE or DELETE privileges granted to
  any application role — only INSERT and SELECT.
- **NFR-3 (Observability):** The feature SHALL emit
  `pychestrate_audit_records_written_total{kind,sink}`,
  `pychestrate_audit_outbox_depth{sink}` (gauge),
  `pychestrate_audit_sink_failures_total{sink,reason}`,
  `pychestrate_audit_unknown_event_total{topic}`,
  `pychestrate_audit_chain_verify_duration_seconds`, and
  structured log events `audit.emitted`, `audit.sink.failed`,
  `audit.sink.healthy`, `audit.sink.unhealthy`,
  `audit.chain.verified`, `audit.catalog.reloaded`.
- **NFR-4 (Reliability):** On process restart, the outbox SHALL
  resume from its last confirmed sequence per sink. A corrupted
  hash chain SHALL surface on startup via a readiness probe that
  keeps the service out of rotation until an operator acknowledges
  the break.

## Out of Scope

- Source of the audit payload — every mutating feature already
  publishes entity events; this feature only consumes.
- UI for viewing audit records — lives in `9-admin-ui` (Phase 10).
- Cross-tenant isolation — Pychestrate is a single-tenant service
  in Phase 1.
- Long-term cold storage of archived records — owned by
  `2-retention-policies` / `10-backup-dr`.

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`, `1-rbac`,
  `E-extension-host`, `E-factory-protocols`,
  `E-resource-extensions`.
- **Depended on by:** every Layer 1+ feature transitively; direct
  coordination with `1-secrets-vault` (fail-closed on unhealthy
  canonical sink).
- **Extension points exposed:** `factory: audit_sink` (local,
  SIEM forwarder, Splunk HEC); `resource: AuditEventTypeExtension`.
  Reference implementations: `LocalDatabaseAuditSink`,
  `JsonFileAuditSink`. See implementation-plan.md Layer 1.
