# 3-client-agent-protocol — Requirements

## Introduction

The Client Agent Protocol defines the wire contract between Pychestrate and a
pod's client agent. It covers the five message families that flow across the
boundary: `enroll`, `heartbeat`, `dispatch`, `progress`, and `result`. This
feature lives in Layer 3 of the implementation plan and lands in Phase 2. It
sits upstream of `3-client-enrollment` (which produces the identity used on
this wire), `3-client-registry` (which stores the endpoint metadata learned
from enroll/heartbeat), and downstream of `0-message-bus` (every inbound
message becomes a bus event). Per the architectural ground rules, the client
agent is the **sole point of contact**: Pychestrate never opens a connection
to a pod member; every job dispatch is to the client, and every result is
pushed by the client. The protocol must therefore be robust to asymmetric
connectivity (outbound from client, server push via long-lived stream) and
client-side outages where the client owns the authoritative run state on
reconnect.

## Requirements

### Requirement 1: Enrollment handshake completes before any other message is accepted

**User Story:** As a pod client agent, I want an enrollment handshake to produce a session
bound to my mTLS identity before any job traffic flows, so that unenrolled agents can
never dispatch progress or results on behalf of an unknown pod.

**Acceptance Criteria (EARS):**

1. WHEN a TCP connection is established on the client transport endpoint THEN the system
   SHALL require a `ClientEnrollRequest` frame as the first application-level message and
   SHALL close the connection with code `1008` if any other frame arrives first.
2. IF the `ClientEnrollRequest.enrollment_token` is expired or has been revoked THEN the
   system SHALL respond with `ClientEnrollReject{reason="token_revoked"}` and close the
   session within 100 ms.
3. WHILE the enrollment handshake is in progress the system SHALL reject all inbound
   `HeartbeatFrame`, `DispatchAck`, `ProgressFrame`, and `ResultManifest` frames with
   `ProtocolError{code="not_enrolled"}`.
4. WHERE the client presents a previously-issued mTLS certificate whose serial matches a
   registry entry the system SHALL short-circuit enrollment and emit
   `entity.client.resumed` instead of `entity.client.enrolled`.

### Requirement 2: Heartbeats are the authoritative liveness signal

**User Story:** As a Pychestrate operator, I want heartbeats to drive the client's
liveness state deterministically, so that a temporarily unreachable client does not
cause cascading run-failure reporting.

**Acceptance Criteria (EARS):**

1. WHEN a `HeartbeatFrame` is received THEN the system SHALL update `ClientRow.last_seen`
   to the server-side receive time and SHALL emit `entity.client.heartbeat` on the bus.
2. IF no `HeartbeatFrame` is received within `3 * heartbeat_interval_seconds` THEN the
   system SHALL transition the client to `liveness_state=suspect` and emit
   `entity.client.liveness_changed{from=alive,to=suspect}`.
3. IF no `HeartbeatFrame` is received within `10 * heartbeat_interval_seconds` THEN the
   system SHALL transition the client to `liveness_state=lost` and mark every in-flight
   dispatch owned by that client `reconciliation_required=true`.
4. WHERE the heartbeat carries a `client_reported_clock` whose skew versus server clock
   exceeds `max_clock_skew_seconds` the system SHALL record the skew in a structured log
   but SHALL NOT reject the heartbeat.

### Requirement 3: Dispatch is one-way to the client; results are pushed by the client

**User Story:** As a Pychestrate dispatcher, I want dispatch to hand an envelope to the
client and then never touch the pod again, so that the client's reported run state is
always authoritative.

**Acceptance Criteria (EARS):**

1. WHEN a `DispatchFrame` is sent to the client THEN the system SHALL require a
   `DispatchAck{dispatch_id, client_run_id}` before considering the dispatch accepted.
2. WHILE a dispatch is pending ack the system SHALL NOT re-dispatch the same envelope to
   any other client and SHALL NOT initiate any outbound probe of pod members.
3. WHEN a `ProgressFrame` or `ResultManifest` arrives referencing an unknown
   `client_run_id` from a known client THEN the system SHALL accept the frame as the
   creation of a new run row in state `adopted` and emit `entity.run.adopted`.
4. IF a `ResultManifest.client_run_id` matches a run already in state `completed` then
   the system SHALL treat the message as an idempotent re-delivery and SHALL NOT emit a
   second `entity.run.completed`.

### Requirement 4: Reconnection reconciles to client-reported truth

**User Story:** As a pod client recovering from a network partition, I want Pychestrate
to accept my reported run state as authoritative on reconnect, so that runs that
finished during the outage are not marked failed.

**Acceptance Criteria (EARS):**

1. WHEN a client reconnects after its session expired THEN the system SHALL accept a
   `ReconcileFrame{runs: [ClientRunState, ...]}` within the first 5 seconds of the new
   session.
2. IF a server-held run row disagrees with the client-reported state THEN the server
   SHALL overwrite its row with the client-reported state and SHALL emit
   `entity.run.reconciled{from=<server_state>,to=<client_state>}`.
3. WHILE reconciliation is in progress the system SHALL suppress liveness alerting for
   that client.

## Property-Based Test Requirements

### Property 1: Heartbeat liveness detection is monotonic under bounded clock skew

- **Invariant:** For any sequence of heartbeats with inter-arrival times `dt_i` where
  `|server_clock_i - client_reported_clock_i| <= max_clock_skew_seconds`, the derived
  `liveness_state` transitions follow the lattice `alive -> suspect -> lost` with no
  skips and no reversals except via an explicit new heartbeat.
- **Generator:** hypothesis strategy producing lists of heartbeats with `dt_i` drawn from
  `floats(min_value=0, max_value=60)` and skew from `floats(-max_clock_skew_seconds,
  +max_clock_skew_seconds)`.
- **Assertion:** the sequence of emitted `entity.client.liveness_changed` events contains
  no `lost -> alive` without an intervening `HeartbeatFrame` receipt and no
  `alive -> lost` without passing through `suspect`.
- **Sample size:** 1000 generated cases

### Property 2: Dispatch / result exchange is idempotent under duplicate delivery

- **Invariant:** For any permutation of the multiset
  `{DispatchFrame, DispatchAck, ProgressFrame*, ResultManifest}` where each frame may be
  delivered 1..3 times, the final server state equals the state produced by the
  deduplicated ordered delivery.
- **Generator:** hypothesis strategy generating frame multisets keyed by a synthetic
  `client_run_id`, each frame duplicated `integers(1, 3)` times, then shuffled.
- **Assertion:** the final `RunRow` tuple `(state, progress_fraction, result_manifest_id)`
  is invariant under duplicates; exactly one `entity.run.completed` is emitted per
  `client_run_id`.
- **Sample size:** 1000 generated cases

### Property 3: Protocol state machine rejects out-of-order frames without partial state

- **Invariant:** For any frame sequence that violates the declared per-session state
  machine (e.g., `ProgressFrame` before `DispatchAck`), the session ends with no
  mutation of any `ClientRow` or `RunRow` observed before the offending frame.
- **Generator:** hypothesis strategy producing frame sequences including deliberate
  ordering violations.
- **Assertion:** server-side DB snapshot taken immediately before the offending frame
  equals the snapshot taken immediately after the session is closed.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** p99 enrollment handshake latency <= 250 ms; p99 dispatch
  frame write -> `DispatchAck` round trip <= 500 ms on a LAN (<2 ms RTT); progress
  frame ingest sustained throughput >= 2000 frames/sec/process.
- **NFR-2 (Security):** all frames carried over mTLS; server validates client
  certificate chain and pins issuer; token reuse detection via monotonic
  `enrollment_nonce`; frame size capped at 1 MiB (configurable via
  `client_transport.max_frame_bytes`); all decoded fields validated against a strict
  schema before any DB write.
- **NFR-3 (Observability):** emit metrics `pychestrate_client_frames_total{kind,result}`,
  `pychestrate_client_heartbeat_rtt_seconds` (histogram),
  `pychestrate_client_sessions_open`, `pychestrate_client_reconcile_total`; emit
  structured log events `pychestrate_client_enroll`, `pychestrate_client_frame_rejected`,
  `pychestrate_client_reconcile`; emit trace spans `client_transport.session`,
  `client_transport.frame.<kind>`.
- **NFR-4 (Reliability):** tolerate arbitrary client disconnects without losing any
  `ResultManifest` that reached the transport (at-least-once ingest + idempotent keying
  by `client_run_id`); bounded-memory handling of stalled sessions (peer write timeout
  30 s, idle timeout 120 s, max in-flight frames per session 256).

## Out of Scope

- Identity issuance itself (see `3-client-enrollment`).
- Capability schema (see `3-client-capability-advertisement`).
- Dispatch payload shape and signing (see `5-job-envelope`, `5-job-dispatch`).
- Result tree parsing (see `5-result-ingest-watcher`).
- Upgrade negotiation (see `3-agent-upgrade-channel`).

## Dependencies

- **Depends on:** `0-web-app-host`, `0-message-bus`, `0-persistence`,
  `1-secrets-vault` (CA material), `E-extension-host`, `E-factory-protocols`.
- **Depended on by:** `3-client-enrollment`, `3-client-registry`,
  `3-client-capability-advertisement`, `3-pod-lifecycle`, `3-agent-upgrade-channel`,
  `5-job-dispatch`, `5-progress-ingest`.
- **Extension points exposed:** `factory: client_transport` — named transports
  (`http2`, `websocket`, `grpc`, `mtls_raw`). See implementation-plan.md Layer 3.
