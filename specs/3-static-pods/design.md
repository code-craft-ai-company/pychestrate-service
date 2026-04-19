# 3-static-pods — Design

## Architecture

Static Pods live at
`source/site/automojo/pychestrate/webservice/pods/static/`. Responsibility
split:

- The client agent announces a pod via the transport (`3-client-agent-protocol`)
  with a `StaticPodRegisterRequest` frame family.
- `pods/static/service.py` verifies the claim against the pinned pod
  definition version, writes a `pod_registration` row, and emits bus
  events.
- A bus subscriber reacts to `entity.client.liveness_changed` to cascade
  the client's state onto every static pod registration the client owns.

The feature does not itself define pod lifecycle states — it publishes
transitions into the `3-pod-lifecycle` state machine and consumes a
side-channel for `client_lost` cascades. Authoritative state: the
`pod_registration` table plus the content hash of the last-accepted report.
This feature is the register/deregister *path* only; member health probing
belongs to `3-pod-lifecycle` and (later) resource-health probing in
Layer 4.

## Data Model

```
pod_registration
    registration_id:        UUID     primary key
    pod_id:                 UUID     foreign key -> pod_definition
    pod_definition_version: int      not null
    client_id:              UUID     foreign key -> client
    state:                  PodRegistrationState not null
    report_hash:            str      not null
    report_json:            jsonb    not null   -- member_reports payload
    registered_at:          datetime not null
    last_report_at:         datetime not null
    deregistered_at:        datetime nullable
    deregister_reason:      str      nullable
    client_lost_at:         datetime nullable
    (pod_id) unique where deregistered_at is null   -- one live registration per pod
    (client_id) index
```

Enumeration (`pods/static/enums.py`):

```
class PodRegistrationState(str, Enum):
    REGISTERED = "registered"
    CLIENT_LOST = "client_lost"
    DRAINING = "draining"
    DEREGISTERED = "deregistered"
```

## Interfaces

### Public API

No direct REST for register/deregister — these flow only through the
transport. Read-only REST (RBAC `pod.registration.read`):

- `GET /api/v1/projects/{project_id}/pods/{pod_id}/registration` — current
  active registration.
- `GET /api/v1/projects/{project_id}/pods/{pod_id}/registrations` — history.

### Internal API

```python
def register_static_pod(
    *,
    client_id: UUID,
    pod_id: UUID,
    pod_definition_version: int,
    member_reports: Sequence[MemberReport],
    received_at: datetime,
) -> StaticPodRegistrationResult:
    ...


def deregister_static_pod(
    *,
    client_id: UUID,
    pod_id: UUID,
    reason: str,
    received_at: datetime,
) -> StaticPodDeregistrationResult:
    ...


def on_client_liveness_changed(
    *,
    event: ClientLivenessChangedEvent,
) -> None:
    ...


def reconcile_on_recover(
    *,
    client_id: UUID,
    pod_id: UUID,
    fresh_report: Sequence[MemberReport],
) -> ReconcileOnRecoverResult:
    ...
```

### Extension Surface

None at the factory protocol level. This feature contributes two public bus
topics (`entity.pod.registered`, `entity.pod.deregistered`) as its
extension surface for `E-extension-hooks`.

### Events Emitted

```
entity.pod.registered                     { pod_id, registration_id, client_id, version, report_hash }
entity.pod.deregistered                   { pod_id, registration_id, reason }
entity.pod.registered_client_lost         { pod_id, registration_id, client_id }
entity.pod.registered_client_recovered    { pod_id, registration_id, client_id }
entity.pod.registration_rejected          { client_id, pod_id, code, reason }
```

### Events Consumed

- `entity.client.liveness_changed` — cascade client liveness to pod state.
- `entity.client.revoked` — mark any owned registrations as deregistered
  with `reason=client_revoked`.
- `entity.pod.definition_deleted` — soft-deregister active registrations
  with `reason=definition_deleted`.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/pods/static/
    __init__.py
    enums.py
    dtos.py                       -- MemberReport, StaticPodRegistrationResult,
                                     StaticPodDeregistrationResult, ReconcileOnRecoverResult
    service.py                    -- register / deregister / reconcile
    repository.py                 -- PodRegistrationRepository
    subscribers.py                -- bus subscribers (liveness, revocation, def_deleted)
    handlers.py                   -- transport-frame bridges
    rest.py                       -- read-only REST router
    metrics.py
```

## Key Flows

**Fresh registration.** Client sends `StaticPodRegisterRequest` frame ->
`handlers.on_register_frame` -> `service.register_static_pod`. Service
fetches the pinned `pod_definition_version` row, compares member-name sets
with `member_reports`, invokes per-kind validation, computes `report_hash =
sha256(canonical(report))`, opens a transaction, writes `pod_registration`
with `state=registered`, commits, publishes `entity.pod.registered`.

**Idempotent re-register.** Client re-sends same frame after a retry.
Service computes the same hash, finds existing live row with same hash,
updates `last_report_at` only, publishes no new event.

**Client goes lost.** Bus delivers `entity.client.liveness_changed{to=lost}`
-> `subscribers.on_liveness_changed` -> for every active registration
owned by that client, updates `state=client_lost`, sets `client_lost_at`,
publishes `entity.pod.registered_client_lost`.

**Client recovers.** `entity.client.liveness_changed{to=alive}`. Subscriber
marks the pod as expecting a reconcile; when the client re-sends a
register frame, `service.reconcile_on_recover` compares the fresh report
hash with the stored one. If equal, transitions back to `registered` and
publishes `entity.pod.registered_client_recovered`; if different, the
registration stays in `client_lost` and an operator action is required.

## Error Handling

- `MemberNotInDefinition`, `MissingMember`, `UnknownDefinitionVersion`,
  `DefinitionVersionDeleted`, `PodNotOwnedByClient` — domain errors
  translated at the frame handler boundary to
  `ClientEnrollReject`-style responses and bus event
  `entity.pod.registration_rejected`.
- `ConcurrentRegistrationConflict` — two simultaneous registrations for
  the same `pod_id`. Caught at service boundary; retried once; on second
  failure surfaced as a rejection.
- `ConfigurationError` — raised at startup if required bus topics are
  missing from the `0-message-bus` topology.
- `SemanticError` — never caught.
- Multiline error messages:

```python
err_msg_lines = ["Static pod registration rejected."]
err_msg_lines.append("POD_ID:         {}".format(pod_id))
err_msg_lines.append("CLIENT_ID:      {}".format(client_id))
err_msg_lines.append("CODE:           {}".format(code))
err_msg_lines.append("MISSING_MEMBERS:")
for m in missing_members:
    err_msg_lines.append("    - {}".format(m))
err_msg_lines.append("UNKNOWN_MEMBERS:")
for m in unknown_members:
    err_msg_lines.append("    - {}".format(m))

err_msg = os.linesep.join(err_msg_lines)
raise StaticPodRegistrationInvalid(err_msg) from None
```

## Security Considerations

- Caller identity = session's `client_id` (bound by mTLS). The service
  cross-checks against `pod_definition.client_binding` via
  `3-client-registry`; any mismatch yields `PodNotOwnedByClient`.
- REST read surface gated by `pod.registration.read`.
- Audit log entries for every register / deregister / rejection, tagged
  with `actor=client:<client_id>`.
- Member reports treated as untrusted input: every field is schema-validated
  before persistence; blobs capped at 128 KiB per registration.

## Observability

Metrics:

- `pychestrate_pod_registrations_total{outcome}` — counter (ok, rejected,
  idempotent_noop).
- `pychestrate_pod_state_distribution{state}` — gauge.
- `pychestrate_pod_registration_latency_seconds` — histogram.
- `pychestrate_pod_client_lost_cascades_total` — counter.

Log events: `pychestrate_pod_registered`, `pychestrate_pod_deregistered`,
`pychestrate_pod_registration_rejected`,
`pychestrate_pod_client_lost_cascade`.

Trace spans: `static_pod.register`, `static_pod.deregister`,
`static_pod.reconcile_on_recover`.

## Open Questions

- Should a pod's registration survive client *revocation* in any form
  (e.g., a "dormant" state) so that history is retained, or is
  revocation an immediate hard-deregister? Lean toward hard-deregister
  with history intact in the historical rows.
- For registrations that stay `client_lost` beyond a threshold, should we
  auto-deregister? Defer to Phase 3 operator policy; parameterize the
  threshold in `2-global-variables`.
