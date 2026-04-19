# 3-client-agent-protocol — Design

## Architecture

The Client Agent Protocol implementation lives under
`source/site/automojo/pychestrate/webservice/clients/transport/` and is the
lowest-level Layer 3 module: every other Layer 3 feature consumes the session
objects and bus events it produces. The transport is pluggable through the
`client_transport` factory protocol — the in-tree default is a WebSocket-over-
mTLS transport (`websocket_mtls`) that multiplexes all five message families
on a single long-lived session per client. Each active session is owned by an
asyncio task group inside the WebWorks WSGI worker that accepted the upgrade;
per-session state is held in memory, authoritative run/client state is
persisted through `0-persistence`. All inbound frames are routed first to a
validator, then to a per-kind handler, then to `0-message-bus`; **no handler
is permitted to call back into a pod member**. Authoritative state on
reconnect is the client's `ReconcileFrame` payload — the server replaces any
disagreeing `RunRow` fields with client-reported values.

## Data Model

Tables (Postgres, owned by this feature; cross-referenced by
`3-client-registry`).

```
client_session
    session_id:          UUID           primary key
    client_id:           UUID           foreign key -> client(id), nullable until enrolled
    transport_name:      str            index, name from factory registry
    remote_addr:         str
    cert_serial:         str            index
    opened_at:           datetime       not null
    closed_at:           datetime       nullable
    close_code:          int            nullable
    enrollment_nonce:    bytes          unique per (client_id, opened_at)
    last_frame_at:       datetime       not null

client_frame_audit
    frame_id:            UUID           primary key
    session_id:          UUID           foreign key -> client_session(session_id)
    kind:                FrameKind      enum
    direction:           Direction      enum (inbound|outbound)
    size_bytes:          int
    received_at:         datetime
    accepted:            bool
    reject_reason:       str            nullable
    (session_id, received_at) index

client_run_reconcile_log
    reconcile_id:        UUID           primary key
    session_id:          UUID           foreign key -> client_session
    client_run_id:       str            not null
    server_state_before: RunState
    client_state_after:  RunState
    applied_at:          datetime
```

Enumerations (in `clients/transport/enums.py`):

```
class FrameKind(str, Enum):
    CLIENT_ENROLL_REQUEST = "enroll_request"
    CLIENT_ENROLL_ACCEPT = "enroll_accept"
    CLIENT_ENROLL_REJECT = "enroll_reject"
    HEARTBEAT = "heartbeat"
    DISPATCH = "dispatch"
    DISPATCH_ACK = "dispatch_ack"
    PROGRESS = "progress"
    RESULT_MANIFEST = "result_manifest"
    RECONCILE = "reconcile"
    PROTOCOL_ERROR = "protocol_error"


class LivenessState(str, Enum):
    ALIVE = "alive"
    SUSPECT = "suspect"
    LOST = "lost"
```

## Interfaces

### Public API

`/api/v1/clients/transport/ws` — WebSocket upgrade endpoint, mTLS required.
Handshake carries `Sec-WebSocket-Protocol: pychestrate.client.v1`.

Diagnostic REST (admin only, Layer 1 RBAC gated):

- `GET /api/v1/clients/{client_id}/sessions` — list recent sessions.
- `GET /api/v1/clients/{client_id}/sessions/{session_id}/frames` — last 500 frames with
  audit metadata (payloads redacted).

### Internal API

```python
class ClientTransportSession:
    """
        Owns the lifecycle of a single client transport session.
    """

    def __init__(
        self,
        *,
        session_id: UUID,
        remote_addr: str,
        cert_serial: str,
        transport_name: str,
        bus: MessageBus,
        repo: ClientSessionRepository,
        clock: Clock,
    ) -> None:
        ...

    async def run(self) -> None:
        ...

    async def send_frame(self, *, frame: OutboundFrame) -> None:
        ...


def register_client_transport_factory(
    *,
    factory_registry: FactoryRegistry,
) -> None:
    ...


async def handle_inbound_frame(
    *,
    session: ClientTransportSession,
    frame: InboundFrame,
) -> FrameDisposition:
    ...
```

Every function signature adheres to AGENTS.md: snake_case, type hints on every
parameter, explicit return annotations, no mutable defaults, named parameter passing
required.

### Extension Surface

Factory protocol:

```python
class ClientTransportProtocol(FactoryProtocolBase):
    factory_protocol_name = "client_transport"
    protocol_schema_version = 1

    @classmethod
    def create_server_binding(
        cls,
        *,
        listen_addr: str,
        tls_context: TlsContext,
        session_sink: SessionSink,
    ) -> ServerBinding:
        ...

    @classmethod
    def encode_frame(cls, *, frame: OutboundFrame) -> bytes:
        ...

    @classmethod
    def decode_frame(cls, *, raw: bytes) -> InboundFrame:
        ...
```

Reference implementation shipped in-tree: `WebSocketMtlsClientTransport`
(`PRECEDENCE=100`), at
`source/site/automojo/pychestrate/factories/client_transport/websocket_mtls.py`.
Test-only override: `InMemoryLoopbackTransport` at `PRECEDENCE=50` used by the
property-based test suite to exercise the state machine without real sockets.

### Events Emitted

```
entity.client.session_opened       { session_id, remote_addr, transport_name }
entity.client.enrolled             { client_id, session_id }
entity.client.resumed              { client_id, session_id }
entity.client.heartbeat            { client_id, client_reported_clock, rtt_seconds }
entity.client.liveness_changed     { client_id, from, to }
entity.client.frame_rejected       { session_id, kind, reason }
entity.client.session_closed       { session_id, close_code }
entity.run.adopted                 { client_run_id, client_id }
entity.run.reconciled              { client_run_id, from_state, to_state }
```

### Events Consumed

- `entity.client.revoked` (from `3-client-enrollment`) — force-closes any live session
  whose `client_id` is revoked.
- `entity.job.dispatch_requested` (from `5-job-dispatch`) — triggers a `DispatchFrame`
  write to the target session.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/clients/transport/
    __init__.py
    enums.py                    -- FrameKind, LivenessState, Direction
    frames.py                   -- @dataclass InboundFrame / OutboundFrame variants
    session.py                  -- ClientTransportSession
    state_machine.py            -- per-session state transitions
    dispatcher.py               -- inbound frame -> handler routing
    handlers/
        enroll.py
        heartbeat.py
        dispatch_ack.py
        progress.py
        result_manifest.py
        reconcile.py
    repository.py               -- ClientSessionRepository (SQL)
    validator.py                -- frame schema validation
    metrics.py                  -- pychestrate_client_* Prometheus instruments

source/site/automojo/pychestrate/factories/client_transport/
    websocket_mtls.py           -- reference implementation, PRECEDENCE=100
    loopback.py                 -- test helper (tests import only)
```

## Key Flows

**Fresh enrollment.** Client opens TCP+mTLS, upgrades to WebSocket with subprotocol
`pychestrate.client.v1`. Server accepts, creates `ClientTransportSession` in
`state=awaiting_enroll`. Client sends `ClientEnrollRequest`. Server validates
token via `3-client-enrollment`, creates `client` row, writes `client_session`
row, emits `entity.client.enrolled`, transitions session to `state=ready`.

**Steady-state dispatch.** `5-job-dispatch` emits `entity.job.dispatch_requested`
carrying a target `client_id` and an envelope. The session for that client
awaits the event, writes a `DispatchFrame`, and holds the dispatch in a local
`pending_ack` map until `DispatchAck` arrives. On ack the run row is written
in state `accepted_by_client` and `entity.run.accepted` is published.

**Reconnect after outage.** Client reconnects; new session begins in
`state=awaiting_enroll`. Client presents the same mTLS cert; server detects
existing `client_id` by cert serial and emits `entity.client.resumed`. Client
sends `ReconcileFrame` with its local run table. For each divergence the server
applies client state and logs a `client_run_reconcile_log` row.

## Error Handling

- `ProtocolError` (custom exception subclass of `SemanticError` — never caught; caller
  must let it bubble). Raised when a frame violates the session state machine.
  The session closing handler catches `ProtocolError` at the *session boundary only*
  to translate it into a close frame; the exception is then re-raised for telemetry.
- `FrameValidationError` — raised by `validator.py`; caught at the frame dispatcher
  boundary, re-classified to `ClientTransportFrameRejected` with the offending field
  names appended, and emitted as `entity.client.frame_rejected`.
- `ConfigurationError` — raised at startup if the configured `client_transport`
  factory name is not registered or the TLS material in the secrets vault is
  missing. Service refuses to start.
- Multi-line error messages use `os.linesep.join([...])`:

```python
err_msg_lines = ["Client frame rejected."]
err_msg_lines.append("SESSION:   {}".format(session_id))
err_msg_lines.append("KIND:      {}".format(frame.kind))
err_msg_lines.append("REASON:    {}".format(reason))
err_msg_lines.append("INVALID_FIELDS:")
for field_name in invalid_fields:
    err_msg_lines.append("    - {}".format(field_name))

err_msg = os.linesep.join(err_msg_lines)
raise FrameValidationError(err_msg) from None
```

## Security Considerations

- All connections mTLS; server requires a client certificate signed by the Pychestrate
  internal CA managed by `1-secrets-vault`.
- Session identity = `cert_serial`. A cert cannot be moved between clients without
  triggering an enrollment check.
- RBAC permission `client.transport.admin` gates the diagnostic REST endpoints.
- Input validation on every frame via declarative schema; any unknown field is
  rejected (no "ignore extras" mode).
- Audit-log entry (`1-audit-log`) written for `enroll_accept`, `enroll_reject`,
  `revoked_close`, and `reconcile_apply`.
- Rate limit per client: max 10 enrollment attempts/min, max 20 frames/sec sustained
  on non-progress kinds (progress has its own higher limit of 5000/sec).

## Observability

Metrics:

- `pychestrate_client_frames_total{kind,result}` — counter.
- `pychestrate_client_sessions_open` — gauge.
- `pychestrate_client_heartbeat_rtt_seconds` — histogram (buckets:
  `[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]`).
- `pychestrate_client_frame_bytes` — histogram.
- `pychestrate_client_reconcile_runs_total` — counter.
- `pychestrate_client_liveness_transitions_total{from,to}` — counter.

Log events (structured):

- `pychestrate_client_enroll`, `pychestrate_client_session_closed`,
  `pychestrate_client_frame_rejected`, `pychestrate_client_reconcile_apply`.

Trace spans: `client_transport.session` (session-scoped),
`client_transport.frame.<kind>` (per-frame child span).

## Open Questions

- Should the transport multiplex dispatch + progress on a single session or open a
  separate progress-only stream for bandwidth isolation? Decide before M2 of Phase 2.
- Exact serialization (CBOR vs msgpack vs length-prefixed JSON). Default pick: CBOR
  for binary artifact manifests, JSON for enroll/heartbeat. Confirm before M1 ends.
