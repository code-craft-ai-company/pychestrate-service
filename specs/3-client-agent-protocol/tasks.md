# 3-client-agent-protocol — Tasks

## Milestones

- **M1 — Skeleton:** In-memory loopback transport proves the frame schema, session
  state machine, and bus wiring. No persistence, no mTLS.
- **M2 — Core Behavior:** WebSocket-over-mTLS reference transport in-tree. Session
  persistence, liveness detection, dispatch/ack/result round-trips, reconcile flow.
- **M3 — Hardening:** Rate limits, trace spans, audit hooks, extension-point
  validation, performance targets met, docs generated.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Declare `FrameKind`, `LivenessState`, and `Direction` enums under
  `clients/transport/enums.py`.
- [ ] T1.2 — Define `InboundFrame`/`OutboundFrame` dataclasses for all ten frame
  kinds under `clients/transport/frames.py`.
- [ ] T1.3 — Implement `validator.py` with strict schema validation raising
  `FrameValidationError` on any unknown field or type mismatch.
- [ ] T1.4 — Implement session state machine (`state_machine.py`) with explicit
  transition table and `ProtocolError` on invalid transitions.
- [ ] T1.5 — Declare `ClientTransportProtocol(FactoryProtocolBase)` with classmethods
  `create_server_binding`, `encode_frame`, `decode_frame`.
- [ ] T1.6 — Implement `InMemoryLoopbackTransport` at `PRECEDENCE=50` for tests.
- [ ] T1.7 — Wire five bus topics (`entity.client.session_opened|enrolled|heartbeat|
  frame_rejected|session_closed`) through `0-message-bus`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `WebSocketMtlsClientTransport` at `PRECEDENCE=100` using
  `codecraftai-webworks` WebSocket support.
- [ ] T2.2 — Add `client_session`, `client_frame_audit`, `client_run_reconcile_log`
  tables via `0-persistence` migration pack with namespaced prefix `clients_`.
- [ ] T2.3 — Implement `ClientSessionRepository` with async SQL helpers for
  insert/update/close session and append frame audit row.
- [ ] T2.4 — Implement heartbeat liveness tracker with timer wheel; emit
  `entity.client.liveness_changed` at the 3x and 10x thresholds.
- [ ] T2.5 — Implement dispatch handshake: outbound `DispatchFrame`, `pending_ack`
  map keyed by `dispatch_id`, timeout->reconcile on ack miss.
- [ ] T2.6 — Implement progress and result-manifest handlers with idempotent
  keying on `client_run_id`.
- [ ] T2.7 — Implement `ReconcileFrame` handler that overwrites `RunRow` with
  client-reported state and appends to `client_run_reconcile_log`.
- [ ] T2.8 — Bus consumer that listens for `entity.client.revoked` and force-closes
  sessions.
- [ ] T2.9 — Bus consumer for `entity.job.dispatch_requested` that writes a
  `DispatchFrame` to the target session.
- [ ] T2.10 — Ship a diagnostic REST router at `/api/v1/clients/{client_id}/sessions`
  behind the `client.transport.admin` permission.

### M3 — Hardening

- [ ] T3.1 — Add per-session rate limits: 10 enroll/min, 20 non-progress frames/sec,
  5000 progress/sec. Reject with `ProtocolError{code="rate_limited"}`.
- [ ] T3.2 — Emit all metrics listed in design.md Observability; wire default
  Grafana dashboard JSON to `docs/observability/client_transport.json`.
- [ ] T3.3 — Add OTLP trace spans `client_transport.session` and
  `client_transport.frame.<kind>` honoring `10-observability`.
- [ ] T3.4 — Wire `1-audit-log` writes for `enroll_accept`, `enroll_reject`,
  `revoked_close`, `reconcile_apply`.
- [ ] T3.5 — Perf run: sustain 2000 progress frames/sec/process for 5 min on a
  reference host; record headroom.
- [ ] T3.6 — Sphinx docs for public REST, factory protocol, internal module API.

## Test Tasks

- [ ] TT-1 — Unit tests per EARS clause in requirements.md Requirements 1-4.
- [ ] TT-2 — Hypothesis tests for Property 1 (liveness monotonicity), Property 2
  (dispatch/result idempotence), Property 3 (out-of-order frame rejection without
  partial state).
- [ ] TT-3 — Integration test: a real loopback transport runs a full enroll -> 5x
  heartbeat -> dispatch -> progress -> result -> disconnect -> reconnect -> reconcile
  sequence and asserts exactly one `entity.run.completed`.
- [ ] TT-4 — Extension-point test: a test-only `EchoingClientTransport` at
  `PRECEDENCE=25` overrides the reference transport and the `SuperFactory` lookup
  returns the override.
- [ ] TT-5 — Fuzz test: 50k random byte payloads into `decode_frame` must never
  raise anything other than `FrameValidationError`.
- [ ] TT-6 — mTLS negative test: connecting without a client cert, with a cert
  signed by the wrong CA, or with a revoked cert must each close with code 1015.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] `client_transport` factory has in-tree `WebSocketMtlsClientTransport`
  (`PRECEDENCE=100`) plus a test-only override at different `PRECEDENCE`.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated for public and internal APIs.
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
  explicit returns, named parameter passing, type hints on every param,
  no behavior-modifying decorators).
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Definition of Done for Phase 2 in
  specs/implementation-plan.md.
