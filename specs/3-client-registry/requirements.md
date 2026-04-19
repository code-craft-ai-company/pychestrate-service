# 3-client-registry — Requirements

## Introduction

The Client Registry is the server-side record of every enrolled pod client:
identity, transport coordinates, agent version, advertised attributes
(capability kinds contributed via `ClientAttributeExtension`), and last-seen
timestamp. It lives in Layer 3 and ships in Phase 2. Upstream it depends on
`3-client-enrollment` (which creates `client` rows) and
`3-client-agent-protocol` (which updates last-seen via heartbeats).
Downstream, it is consulted by `3-client-capability-advertisement`,
`3-pod-definitions`, `3-static-pods`, `5-job-dispatch`, and
`3-client-inventory-ui`. Per the architectural ground rule "pod client is the
sole point of contact", the registry is the authoritative directory of where
to route dispatches, and nothing outside this plane should cache the mapping
for longer than a single dispatch attempt.

## Requirements

### Requirement 1: A client is discoverable by `client_id`, by `project_id + pod_name`, and by cert serial

**User Story:** As a dispatcher, I want to look up a client by any of the three
natural keys (uuid, scoped name, cert serial), so that enrollment, dispatch, and
session routing all converge on the same row.

**Acceptance Criteria (EARS):**

1. WHEN `get_client_by_id(client_id=...)` is called THEN the system SHALL return
   a `ClientRow` in O(1) via the primary key.
2. WHEN `get_client_by_scope(project_id=..., pod_name=...)` is called THEN the
   system SHALL use the `(project_id, pod_name)` unique index.
3. WHEN `get_client_by_cert_serial(cert_serial=...)` is called THEN the system
   SHALL use the `(cert_serial)` unique index established by
   `3-client-enrollment`.
4. IF no row matches THEN each function SHALL raise `ClientNotFound` with a
   message naming the queried key.

### Requirement 2: Heartbeats and frames update `last_seen` atomically with liveness state

**User Story:** As a UI operator, I want `last_seen` and `liveness_state` to
remain consistent under high heartbeat rates, so that the fleet view never
shows a `lost` client with a 2-second-old last-seen.

**Acceptance Criteria (EARS):**

1. WHEN `entity.client.heartbeat` is consumed THEN the system SHALL update
   `last_seen`, `liveness_state`, `last_agent_version`, and `transport_name` in
   one SQL statement.
2. WHILE `liveness_state` is `lost` the system SHALL reject any update that
   would leave `last_seen` older than the value that triggered the `lost`
   transition.
3. IF a heartbeat arrives after a revocation THEN the system SHALL NOT update
   `last_seen` and SHALL emit `entity.client.ignored_heartbeat{reason=revoked}`.
4. WHEN `entity.client.liveness_changed{to=alive}` is consumed after a period of
   `suspect` or `lost` THEN the system SHALL clear the `degraded_at` timestamp.

### Requirement 3: Attributes are declared via extension and stored typed

**User Story:** As an extension author, I want to declare a new client attribute
kind (e.g., `gpu_model`) from an out-of-tree package, so that dispatchers can
filter on it without forking Pychestrate.

**Acceptance Criteria (EARS):**

1. WHEN the extension host loads a `ClientAttributeExtension` subclass THEN the
   registry SHALL accept attribute values with that kind on subsequent
   `UpdateAttributesRequest` calls.
2. IF a value arrives for an unknown kind THEN the registry SHALL reject the
   update and emit `entity.client.attribute_rejected{kind=<name>}`.
3. WHERE the extension declares a `value_schema` the registry SHALL validate
   inbound values against the schema and store the parsed object; IF validation
   fails THEN the value SHALL be rejected without partial mutation.
4. WHEN attributes change THEN the system SHALL emit
   `entity.client.attributes_changed{client_id, added, removed, modified}`.

### Requirement 4: Registry writes are idempotent and concurrent-safe

**User Story:** As the transport layer routing many heartbeats per second, I
want registry updates to tolerate duplicate deliveries and concurrent writes,
so that I do not have to serialize at the transport.

**Acceptance Criteria (EARS):**

1. WHEN two `entity.client.heartbeat` events for the same `client_id` arrive
   concurrently THEN the system SHALL persist the one with the later
   `server_received_at` and discard the earlier one.
2. IF the same `UpdateAttributesRequest` is delivered twice with the same
   `revision_token` THEN the second delivery SHALL be a no-op.

## Property-Based Test Requirements

### Property 1: `last_seen` is monotonic per client

- **Invariant:** For any sequence of heartbeat events applied (possibly out of
  order) to the same `client_id`, the persisted `last_seen` equals the
  maximum `server_received_at` across the sequence.
- **Generator:** hypothesis strategy producing lists of `(client_id,
  server_received_at)` tuples with timestamps drawn from `datetimes()` and
  applied via random interleaving across 8 worker tasks.
- **Assertion:** post-run, `SELECT last_seen FROM client WHERE client_id=?`
  equals `max(timestamps)` for each `client_id`.
- **Sample size:** 1000 generated cases

### Property 2: Attribute updates are all-or-nothing per request

- **Invariant:** For any `UpdateAttributesRequest` containing N attribute
  changes of which at least one violates its declared schema, no attribute in
  the request is persisted.
- **Generator:** hypothesis strategy producing requests with 1-10 attribute
  values, randomly seeded with a known-invalid value in a known-valid kind
  at a random index.
- **Assertion:** the pre-request DB snapshot for the client's attribute rows
  equals the post-request snapshot; `entity.client.attribute_rejected` is
  emitted once.
- **Sample size:** 1000 generated cases

### Property 3: Lookup keys agree on identity

- **Invariant:** For any persisted `ClientRow`, the three lookups
  `get_client_by_id`, `get_client_by_scope`, `get_client_by_cert_serial`
  return row objects with the same `client_id`.
- **Generator:** hypothesis strategy producing 100 random enrollments and
  200 random lookups each.
- **Assertion:** cross-key agreement holds; `ClientNotFound` is raised only
  when the key genuinely does not exist in the seed set.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** p99 registry read latency <= 5 ms under a fleet of
  10,000 clients; registry write (heartbeat update) p99 <= 15 ms; concurrent
  heartbeat ingest sustain 5000 updates/sec/process.
- **NFR-2 (Security):** mutations authorized only via trusted bus events
  (heartbeat, enroll, revoke) or RBAC-gated admin actions
  (`client.registry.read|write|admin`); attribute values validated against
  extension-declared schemas; raw attribute blobs capped at 16 KiB per client.
- **NFR-3 (Observability):** metrics `pychestrate_client_registry_rows`,
  `pychestrate_client_registry_writes_total{kind}`,
  `pychestrate_client_liveness_distribution{state}`,
  `pychestrate_client_attribute_rejected_total{kind}`; log events
  `pychestrate_client_registry_write`, `pychestrate_client_attribute_rejected`.
- **NFR-4 (Reliability):** writes are transactional; on constraint violation
  the system retries once with a refreshed read, otherwise emits
  `pychestrate_client_registry_write_failed` and raises.

## Out of Scope

- Identity issuance (see `3-client-enrollment`).
- Capability semantics (see `3-client-capability-advertisement`).
- UI rendering of the fleet (see `3-client-inventory-ui`).
- Session-level transport state (see `3-client-agent-protocol.client_session`).

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`, `3-client-enrollment`,
  `3-client-agent-protocol`, `E-extension-host`, `E-resource-extensions`.
- **Depended on by:** `3-client-capability-advertisement`, `3-pod-definitions`,
  `3-static-pods`, `3-pod-lifecycle`, `3-client-inventory-ui`,
  `3-agent-upgrade-channel`, `5-job-dispatch`.
- **Extension points exposed:** `resource: ClientAttributeExtension` — declared
  attribute kinds (value schema, display metadata, searchability flag).
  See implementation-plan.md Layer 3.
