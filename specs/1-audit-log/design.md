# 1-audit-log — Design

## Architecture

`1-audit-log` lives under
`source/site/automojo/pychestrate/webservice/audit/`. It is a
consumer-only service in steady state: a bus subscriber maps every
registered `entity.*` topic into an `AuditRecord`, writes it to the
canonical local table (INSERT-only), computes the hash chain, and fans
out to every registered `audit_sink` through a per-sink durable outbox.
The canonical sink is the `audit_records` table in `0-persistence`; all
other sinks are fan-out downstreams and are not authoritative. A failed
canonical-sink write trips `entity.audit.sink.unhealthy` so producing
features (`1-secrets-vault`, `1-rbac`) can fail closed. The feature
declares the `audit_sink` factory protocol and the
`AuditEventTypeExtension` resource base; the catalog of audit kinds is
assembled at service start. This feature ships in
**Phase 1 — Identity & Projects**.

## Data Model

`audit_records` — canonical INSERT-only table:

- `sequence_number: int` — monotonic, server-assigned, PK.
- `record_id: UUID` — stable external id.
- `kind: str` — registered event kind (e.g.,
  `audit.user.created`).
- `source_topic: str` — originating bus topic (e.g.,
  `entity.user.created`).
- `source_event_id: UUID` — id of the source event; `UNIQUE` to
  de-dup on bus retries.
- `actor_user_id: Optional[UUID]`,
  `actor_service_identity: Optional[str]`.
- `target_ref: Optional[str]` — canonical ref of the affected
  entity (e.g., `user:<id>`, `secret:<ref>`, `project:<id>`).
- `payload_json: JSONB` — structured payload validated against the
  registered schema.
- `payload_hash: bytes` — SHA-256 of canonical-JSON serialization.
- `previous_hash: bytes` — `audit_records(sequence_number -
  1).record_hash`.
- `record_hash: bytes` — SHA-256(`previous_hash` || `payload_hash`).
- `written_at: datetime` — server time on insert.

Unique constraints: `UNIQUE(source_event_id)`, `UNIQUE(record_id)`.
Indexes: `INDEX(kind, written_at)`,
`INDEX(actor_user_id, written_at)`,
`INDEX(target_ref, written_at)`.

Database-role policy: the application role has `SELECT, INSERT` only
on `audit_records`. `UPDATE` and `DELETE` are revoked and the
migration asserts this at deploy time.

`audit_sink_registrations` — live view of registered sinks:

- `sink_name: str` — PK.
- `precedence: int`, `is_canonical: bool`, `capabilities: JSONB`.

`audit_sink_outbox` — per-sink outbox:

- `outbox_id: UUID`, `sink_name: str`,
  `sequence_number: int`, `status: OutboxStatus`,
  `enqueued_at: datetime`, `next_attempt_at: datetime`,
  `retry_count: int`.

`audit_event_catalog` — registered kinds:

- `kind: str` — PK.
- `source_name: Optional[str]`, `payload_schema: JSON Schema`,
  `is_reserved: bool`.

## Interfaces

### Public API

REST routes:

- `GET /api/v1/audit` — query with filters `actor_user_id`,
  `kind`, `from_ts`, `to_ts`, `target_ref`, `limit`,
  `page_token`.
- `GET /api/v1/audit/{sequence_number}` — fetch single record by
  sequence.
- `POST /api/v1/audit/verify` — body
  `{from_sequence, to_sequence}`; returns
  `ChainVerificationResult`.
- `GET /api/v1/audit/sinks` — list registered sinks with health.
- `POST /api/v1/audit/sinks/{sink_name}/replay` — re-drain that
  sink's outbox on demand.

There is **no** audit mutation endpoint — UPDATE/DELETE on
`audit_records` are not exposed at any layer.

### Internal API

Module `automojo.pychestrate.webservice.audit.audit_writer`:

```python
def capture_event(
        *,
        source_event_id: UUID,
        source_topic: str,
        kind: str,
        actor_user_id: Optional[UUID],
        actor_service_identity: Optional[str],
        target_ref: Optional[str],
        payload: dict
    ) -> AuditRecord:
    """
        Persist one audit record and stage fan-out to all sinks.

        :param source_event_id: De-dup key across bus retries.
        :param source_topic: Originating bus topic.
        :param kind: Registered audit kind.
        :param actor_user_id: Acting principal, if any.
        :param actor_service_identity: Acting service identity, if any.
        :param target_ref: Canonical ref of affected entity.
        :param payload: Structured, schema-validated payload.

        :returns: The persisted `AuditRecord`.
        :raises: SemanticError on unknown kind/schema mismatch.
    """
    ...
```

Module `automojo.pychestrate.webservice.audit.chain_verifier`:

```python
def verify_audit_chain(
        *,
        from_sequence: int,
        to_sequence: int
    ) -> ChainVerificationResult:
    """
        Recompute the hash chain for a sequence span.

        :returns: `ChainVerificationResult(ok=True, ...)` or `ok=False, first_break=...`.
    """
    ...
```

Module `automojo.pychestrate.webservice.audit.sink_dispatcher`:

```python
def dispatch_record(*, sequence_number: int) -> None:
    """
        Fan the record out to every registered sink via per-sink outbox.
    """
    rtnval = None
    return rtnval


def drain_sink_outbox(*, sink_name: str) -> int:
    """
        Drain a specific sink's outbox; returns count drained.
    """
    ...
```

### Extension Surface

Factory protocol `audit_sink` declared in
`automojo.pychestrate.webservice.audit.factories.audit_sink`:

```python
class AuditSinkProtocol(FactoryProtocolBase):
    factory_protocol_name: str = "audit_sink"
    protocol_schema_version: int = 1

    @classmethod
    def sink_name(cls) -> str:
        ...

    @classmethod
    def is_canonical(cls) -> bool:
        """Return True only for the single canonical durable sink."""
        ...

    @classmethod
    def write_records(cls, *, records: tuple[AuditRecord, ...]) -> SinkWriteResult:
        """Write one or more records; must be idempotent on sequence_number."""
        ...

    @classmethod
    def health_check(cls) -> SinkHealth:
        ...
```

Reference implementations (in-tree):
`LocalDatabaseAuditSink` (`PRECEDENCE = 1000`,
`is_canonical = True`),
`JsonFileAuditSink` (`PRECEDENCE = 2000`, `is_canonical = False`).
Skeletons for guidance: `SplunkHecAuditSink`, `SiemSyslogAuditSink`.

Resource base `AuditEventTypeExtension` declared in
`automojo.pychestrate.webservice.audit.extensions.event_type`:

```python
class AuditEventTypeExtension(ResourceExtension):
    kind: str
    source_topic: str
    payload_schema: dict     # JSON Schema for validation
    description: str
```

Reference implementations: `UserLifecycleAuditEvents`,
`SessionAuditEvents`, `RoleBindingAuditEvents`,
`SecretAuditEvents`, `ProjectAuditEvents`, `FlagAuditEvents`.

### Events Emitted

- `entity.audit.emitted` — `{sequence_number, kind, source_topic, record_hash, written_at}`
- `entity.audit.sink.unhealthy` — `{sink_name, reason, at}`
- `entity.audit.sink.healthy` — `{sink_name, at}`
- `entity.audit.chain.broken` — `{first_break_sequence, detected_at}`
- `entity.audit.catalog.reloaded` — `{kinds_count, at}`

### Events Consumed

- Every registered `entity.*` topic declared by an
  `AuditEventTypeExtension`. In Phase 1 this is at minimum:
  `entity.user.*`, `entity.group.*`, `entity.group.membership.changed`,
  `entity.session.*`, `entity.role.*`, `entity.secret.*`,
  `entity.project.*`, `entity.flag.*`.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/audit/
    __init__.py
    audit_writer.py                # capture_event, payload validation
    chain_verifier.py              # verify_audit_chain
    sink_dispatcher.py             # dispatch_record, drain_sink_outbox
    outbox.py                      # per-sink outbox implementation
    bus_subscriber.py              # registers subscriptions per kind
    models.py                      # AuditRecord, SinkRegistration, ...
    factories/
        audit_sink.py
        local_db_sink.py           # LocalDatabaseAuditSink (canonical)
        json_file_sink.py          # JsonFileAuditSink
        splunk_hec_sink.py         # SplunkHecAuditSink (skeleton)
        siem_syslog_sink.py        # SiemSyslogAuditSink (skeleton)
    extensions/
        event_type.py
        user_events.py
        session_events.py
        role_events.py
        secret_events.py
        project_events.py
        flag_events.py
    restapi/
        v1/
            audit_controller.py
    events.py
    exceptions.py
```

## Key Flows

**Capture Flow (happy path):**

1. `bus_subscriber` receives `entity.user.created` from
   `0-message-bus`.
2. Subscriber resolves the kind `audit.user.created` from the
   catalog and validates the payload against its JSON Schema.
3. `audit_writer.capture_event` inserts the row with
   `payload_hash = sha256(canonical_json(payload))` and
   `record_hash = sha256(previous_hash || payload_hash)` in a
   single transaction with the outbox entries for every registered
   sink.
4. `sink_dispatcher` picks up outbox entries and calls each sink's
   `write_records` concurrently per sink; on success, removes the
   outbox entry.
5. `entity.audit.emitted` is published.

**Canonical Sink Outage:**

1. `LocalDatabaseAuditSink` health check fails.
2. `sink_dispatcher` flips the canonical-health flag and publishes
   `entity.audit.sink.unhealthy`.
3. `1-secrets-vault` and other fail-closed subscribers stop
   accepting writes with `AuditUnavailableError`.
4. On recovery, `sink_dispatcher` publishes
   `entity.audit.sink.healthy` and producing features re-open.

**Chain Verification:**

1. Operator posts `POST /api/v1/audit/verify` with a span.
2. `chain_verifier.verify_audit_chain` iterates the rows and
   recomputes `record_hash`. On mismatch it emits
   `entity.audit.chain.broken` and returns the first offending
   sequence.

## Error Handling

- `SemanticError` — unknown event kind or payload schema
  mismatch; NEVER caught internally. Propagates to the bus
  subscriber which moves the envelope to a dead-letter table for
  triage.
- `AuditSinkTransientError` — caught and classified; re-enqueued in
  the sink's outbox with incremented `retry_count` and exponential
  `next_attempt_at`.
- `AuditSinkPermanentError` — record stays in the outbox pending
  operator action; metric + log + admin-UI alert.
- `ChainVerificationError` — raised when a sequence gap or hash
  mismatch is detected at startup; the readiness probe stays
  `not_ready` until `system:audit.admin` acknowledges via the
  `/api/v1/audit/verify` endpoint.

Multi-line error messages follow AGENTS.md:

```python
err_msg_lines = ["Audit chain broken."]
err_msg_lines.append("FIRST_BREAK_SEQUENCE: {}".format(first_break))
err_msg_lines.append("EXPECTED_HASH: {}".format(expected_hex))
err_msg_lines.append("OBSERVED_HASH: {}".format(observed_hex))
err_msg = os.linesep.join(err_msg_lines)
raise ChainVerificationError(err_msg) from None
```

## Security Considerations

- `system:audit.admin` gates replay and re-verify; `system:audit.read`
  gates query. Project-scoped audit filtering applies
  `project:<id>:audit.read` before returning rows tagged with that
  project.
- Database privileges on `audit_records`: application role is
  `SELECT, INSERT` only. Migrations assert the grants at deploy.
- Payload values SHALL be scrubbed by the producing feature before
  publication — in particular, `1-secrets-vault` publishes
  `secret_ref` and version id but never plaintext.
- Sinks that forward data off-host (Splunk HEC, syslog) must be
  reachable over a TLS-authenticated channel; endpoint credentials
  live in `1-secrets-vault` under `system:audit.sink.<name>`.
- The `audit.unknown` fallback exists so rogue events do not
  silently bypass capture; operators are alerted via
  `pychestrate_audit_unknown_event_total`.

## Observability

Metrics:

- `pychestrate_audit_records_written_total{kind,sink}`
- `pychestrate_audit_outbox_depth{sink}` (gauge)
- `pychestrate_audit_sink_failures_total{sink,reason}`
- `pychestrate_audit_sink_healthy{sink}` (gauge 0/1)
- `pychestrate_audit_unknown_event_total{topic}`
- `pychestrate_audit_chain_verify_duration_seconds` (histogram)
- `pychestrate_audit_chain_breaks_total`

Log events: `audit.emitted`, `audit.sink.failed`,
`audit.sink.healthy`, `audit.sink.unhealthy`,
`audit.chain.verified`, `audit.chain.broken`,
`audit.catalog.reloaded`.

Trace spans: `audit.capture`, `audit.chain.verify`,
`audit.sink.dispatch`, `audit.sink.flush`.

## Open Questions

- Do we include a Merkle-tree export for third-party attestation,
  or is a linear hash chain sufficient for Phase 1? Proposed:
  linear chain now, Merkle export in Phase 10 if compliance asks.
- Do we need per-project audit partitioning (by `target_ref`
  project prefix) for multi-tenancy preparation? Defer until a
  multi-tenant feature request lands.
- Dead-letter table sizing and operator workflow for `audit.unknown`
  triage — close before Phase 1 ship.
