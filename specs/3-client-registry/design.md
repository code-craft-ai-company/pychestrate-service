# 3-client-registry — Design

## Architecture

The Client Registry lives at
`source/site/ccai/pychestrate/webservice/clients/registry/`. It owns the
server-side mutable view of every enrolled client — authoritative for
`liveness_state`, `last_seen`, agent version, transport name, and the set of
typed attributes contributed by extensions. Writes flow in through two
paths: bus events (heartbeat, enroll, revoke, liveness_changed) consumed by
`subscribers.py`, and admin-or-transport RPC calls into `service.py`. Reads
are exposed through a REST surface (for `3-client-inventory-ui`), an internal
Python API (for `5-job-dispatch`), and a message-bus "broadcast current
state" topic used when other plane features boot and need to prime local
caches. Attribute kinds come from the extension host via
`ClientAttributeExtension` subclasses discovered at service startup; the
registry never accepts values for unknown kinds.

## Data Model

```
client                                  -- row partly owned by 3-client-enrollment
    client_id:              UUID        primary key
    project_id:             UUID        foreign key -> project
    pod_name:               str
    status:                 ClientStatus
    enrolled_at:            datetime
    last_seen:              datetime    nullable
    liveness_state:         LivenessState not null default 'alive'
    last_agent_version:     str         nullable
    transport_name:         str         nullable
    degraded_at:            datetime    nullable
    revision_token:         str         not null -- monotonic per update
    (project_id, pod_name) unique
    (liveness_state)       index
    (last_seen)            index

client_attribute
    attribute_id:           UUID        primary key
    client_id:              UUID        foreign key -> client, cascade
    kind:                   str         not null
    value_json:             jsonb       not null
    updated_at:             datetime    not null
    (client_id, kind) unique
```

Enumerations extend those declared by sibling features — `LivenessState` is
imported from `3-client-agent-protocol.enums`; `ClientStatus` is imported
from `3-client-enrollment.enums`.

## Interfaces

### Public API

REST (admin only, `client.registry.read`):

- `GET /api/v1/clients` — paginated list; filters: `project_id`, `status`,
  `liveness_state`, `kind=<attr_kind>&value=<...>`.
- `GET /api/v1/clients/{client_id}` — full row plus attribute map.
- `PUT /api/v1/clients/{client_id}/attributes` — admin override for an
  attribute (behind `client.registry.admin`). Body:
  `{ "updates": [{ "kind": str, "value": Any }, ...] }`.

### Internal API

```python
class ClientRegistry:
    """
        Read/write facade over the registry. One instance per service process.
    """

    def __init__(
        self,
        *,
        repository: ClientRegistryRepository,
        attribute_kinds: Mapping[str, ClientAttributeKind],
        bus: MessageBus,
        clock: Clock,
    ) -> None:
        ...

    def get_client_by_id(self, *, client_id: UUID) -> ClientRow:
        ...

    def get_client_by_scope(
        self,
        *,
        project_id: UUID,
        pod_name: str,
    ) -> ClientRow:
        ...

    def get_client_by_cert_serial(self, *, cert_serial: str) -> ClientRow:
        ...

    def list_clients(self, *, filters: ClientFilter) -> List[ClientRow]:
        ...

    def apply_heartbeat(self, *, event: HeartbeatEvent) -> None:
        ...

    def update_attributes(
        self,
        *,
        client_id: UUID,
        updates: Sequence[AttributeUpdate],
        revision_token: str,
    ) -> AttributeUpdateResult:
        ...


def load_attribute_kinds(
    *,
    extension_host: ExtensionHost,
) -> Mapping[str, ClientAttributeKind]:
    ...
```

### Extension Surface

```python
class ClientAttributeExtension(ResourceExtension):
    """
        Base class for declared client attribute kinds. Subclasses are
        discovered at service startup by the extension host.
    """

    attribute_kind_name: ClassVar[str]
    value_schema: ClassVar[JsonSchema]
    display_label: ClassVar[str]
    searchable: ClassVar[bool] = False
```

Reference implementations shipped in-tree (under
`source/site/ccai/pychestrate/extensions/client_attributes/`):

- `OsKindAttribute` (`attribute_kind_name="os"`), value is
  `{"family": "linux|macos|windows|other", "version": str}`.
- `CpuArchAttribute` (`attribute_kind_name="cpu_arch"`), value is one of
  `{"x86_64", "arm64", "riscv64", "other"}`.
- `ConcurrencyAttribute` (`attribute_kind_name="concurrency"`), value is
  `{"max_runs": int, "current_runs": int}`.

### Events Emitted

```
entity.client.registered              { client_id, project_id, pod_name }
entity.client.attributes_changed      { client_id, added, removed, modified }
entity.client.attribute_rejected      { client_id, kind, reason }
entity.client.ignored_heartbeat       { client_id, reason }
entity.client.registry_write_failed   { client_id, kind, error_class }
```

### Events Consumed

- `entity.client.enrolled` — create registry row.
- `entity.client.heartbeat` — update `last_seen` + `last_agent_version` +
  `transport_name`.
- `entity.client.liveness_changed` — update `liveness_state` and
  `degraded_at`.
- `entity.client.revoked` — update `status=revoked`.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/clients/registry/
    __init__.py
    enums.py                     -- imports + small re-exports
    dtos.py                      -- ClientRow, ClientFilter, AttributeUpdate,
                                    AttributeUpdateResult, HeartbeatEvent
    registry.py                  -- ClientRegistry service class
    repository.py                -- ClientRegistryRepository (SQL, asyncpg)
    attribute_kinds.py           -- load_attribute_kinds, schema validation
    subscribers.py               -- bus subscriber glue
    rest.py                      -- admin REST router
    metrics.py                   -- pychestrate_client_registry_* instruments

source/site/ccai/pychestrate/extensions/client_attributes/
    os_kind.py
    cpu_arch.py
    concurrency.py
```

## Key Flows

**New enrollment.** `entity.client.enrolled` arrives -> subscriber calls
`registry.on_enrolled` -> repository writes `client` row with
`liveness_state=alive` and no attributes -> `entity.client.registered` is
published for downstream consumers (inventory UI, dispatcher cache priming).

**Heartbeat update.** `entity.client.heartbeat` arrives -> subscriber calls
`registry.apply_heartbeat` -> repository runs a single UPDATE stmt with a
`last_seen < :received_at` guard -> on a concurrent loser the stmt affects
zero rows and the subscriber logs a `pychestrate_client_registry_write` at
`outcome=no_op_stale`.

**Attribute update from client.** `3-client-capability-advertisement` calls
`registry.update_attributes` with `updates=[(kind, value), ...]` and a
`revision_token` supplied by the client. The service validates every value
against the extension-declared `value_schema`; on any failure the entire
request is rejected. On success, a transaction writes all changed rows and
emits `entity.client.attributes_changed` with the diff.

## Error Handling

- `ClientNotFound` — looked-up key does not exist. Caught at REST boundary,
  translated to HTTP 404.
- `UnknownAttributeKind` — value submitted for a kind no extension has
  declared. Caught at the service boundary, re-classified with the set of
  registered kinds appended, and returned as HTTP 400 / bus event
  `entity.client.attribute_rejected`.
- `AttributeSchemaError` — value fails schema validation. Same handling as
  above.
- `ConcurrentUpdateRejected` — optimistic-lock collision on `revision_token`.
  Caught at the subscriber boundary and retried once against a refreshed read;
  on a second collision emitted as `entity.client.registry_write_failed`.
- `SemanticError` — never caught; indicates an internal invariant violation.
- Multiline errors use `os.linesep.join([...])`:

```python
err_msg_lines = ["Rejecting client attribute update."]
err_msg_lines.append("CLIENT_ID:       {}".format(client_id))
err_msg_lines.append("UNKNOWN_KINDS:")
for kind_name in unknown_kinds:
    err_msg_lines.append("    - {}".format(kind_name))
err_msg_lines.append("REGISTERED_KINDS:")
for kind_name in registered_kinds:
    err_msg_lines.append("    - {}".format(kind_name))

err_msg = os.linesep.join(err_msg_lines)
raise UnknownAttributeKind(err_msg) from None
```

## Security Considerations

- RBAC permissions: `client.registry.read`, `client.registry.write`,
  `client.registry.admin`.
- Attribute values JSON-validated before any SQL write; no stringified JSON
  passthrough.
- Per-client attribute blob capped at 16 KiB total.
- Admin `PUT` attribute endpoint is audit-logged with actor + before/after
  values.
- The registry never exposes the cert serial on the public REST surface —
  only on admin surfaces (least-privilege disclosure).

## Observability

Metrics:

- `pychestrate_client_registry_rows` — gauge of total non-revoked clients.
- `pychestrate_client_registry_writes_total{kind,outcome}` — counter keyed
  by `kind in {heartbeat, enroll, revoke, attribute}` and `outcome in
  {applied, no_op_stale, rejected}`.
- `pychestrate_client_liveness_distribution{state}` — gauge per
  `liveness_state`.
- `pychestrate_client_attribute_rejected_total{kind,reason}` — counter.
- `pychestrate_client_registry_read_latency_seconds` — histogram.
- `pychestrate_client_registry_write_latency_seconds` — histogram.

Log events: `pychestrate_client_registry_write`,
`pychestrate_client_registry_read_failed`,
`pychestrate_client_attribute_rejected`.

Trace spans: `client_registry.read`, `client_registry.write`,
`client_registry.attribute_update`.

## Open Questions

- Should attribute history be retained (delta log) or only the current value?
  Retention cost vs. fleet-analytics value. Decide before M3.
- When an extension is unloaded at runtime (admin re-scan), do we purge
  attribute rows for its kinds or keep them in a `stale_attribute` bucket?
  Lean toward keep + flag; confirm with `E-extension-lifecycle` owners.
