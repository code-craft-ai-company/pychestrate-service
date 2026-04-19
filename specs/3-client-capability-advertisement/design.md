# 3-client-capability-advertisement — Design

## Architecture

Client Capability Advertisement lives at
`source/site/automojo/pychestrate/webservice/clients/capabilities/`. It
consumes `CapabilityAdvertisementFrame` messages from the transport
(`3-client-agent-protocol`), validates each value against its
extension-declared `CapabilityKind` schema, and writes the delta
transactionally to `client_capability` rows. A query module exposes a
predicate evaluator used by `5-job-dispatch` that answers "which clients
match this predicate right now". Sensitive values are stored encrypted
via `1-secrets-vault`; non-sensitive values live as `jsonb`. An index
on `(kind, value_json->>'key')` supports common match predicates; full
JSON-path queries fall back to a sequential scan bounded by
`liveness_state != lost`.

## Data Model

```
client_capability
    capability_id:     UUID      primary key
    client_id:         UUID      foreign key -> client, cascade
    kind:              str       not null   -- CapabilityKindExtension.capability_kind_name
    value_json:        jsonb     nullable   -- non-sensitive
    sensitive_ref:     str       nullable   -- secret reference for sensitive values
    revision_token:    str       not null   -- matches advertisement's revision
    updated_at:        datetime  not null
    (client_id, kind) unique
    (kind)            index  -- GIN-or-expression index on (kind, value_json) for common paths

client_capability_revision
    client_id:         UUID      primary key
    current_revision:  str       not null
    last_applied_at:   datetime  not null
```

## Interfaces

### Public API

REST (RBAC `client.capability.read`):

- `GET /api/v1/clients/{client_id}/capabilities` — non-sensitive
  capabilities + kind metadata.
- `GET /api/v1/clients/{client_id}/capabilities/{kind}` — single kind.
- `GET /api/v1/clients/{client_id}/capabilities?kind=...&value.key=...`
  — parameterized search (limited to kinds with `searchable=true`).

Admin-only (permission `client.capability.admin`):

- `GET /api/v1/clients/{client_id}/capabilities/sensitive` — includes
  sensitive values (audit-logged).

### Internal API

```python
def apply_advertisement(
    *,
    client_id: UUID,
    advertisement: CapabilityAdvertisement,
) -> AdvertisementApplyResult:
    ...


def find_clients_matching(
    *,
    predicate: CapabilityPredicate,
    limit: int,
    include_suspect: bool,
) -> List[UUID]:
    ...


def get_client_capabilities(
    *,
    client_id: UUID,
    include_sensitive: bool,
) -> List[CapabilityRow]:
    ...


def load_capability_kinds(
    *,
    extension_host: ExtensionHost,
) -> Mapping[str, CapabilityKind]:
    ...
```

### Extension Surface

```python
class CapabilityKindExtension(ResourceExtension):
    """
        Declares a client capability kind.
    """

    capability_kind_name: ClassVar[str]
    value_schema: ClassVar[JsonSchema]
    searchable: ClassVar[bool] = True
    sensitive: ClassVar[bool] = False
    max_value_bytes: ClassVar[int] = 64 * 1024
    display_label: ClassVar[str]
```

Reference implementations (in-tree, under
`source/site/automojo/pychestrate/extensions/capability_kinds/`):

- `ToolchainCapability` (`capability_kind_name="toolchain"`) — value:
  `{"name": str, "version": str, "path": str}`.
- `PodMemberOwnershipCapability`
  (`capability_kind_name="pod_member_ownership"`) — value:
  `{"member_kind": str, "instance_ids": [str]}`.
- `ConcurrencyCapability` (`capability_kind_name="concurrency"`) —
  value: `{"max_runs": int, "current_runs": int}`.
- `AcceleratorCapability` (`capability_kind_name="accelerator"`) —
  value: `{"vendor": str, "model": str, "memory_gib": int, "count": int}`.
- `AgentFeatureFlagCapability` (`capability_kind_name="agent_feature_flag"`,
  sensitive=true) — value: opaque map of enabled flags.

### Events Emitted

```
entity.client.capabilities_applied     { client_id, revision, added, modified, removed }
entity.client.capability_rejected      { client_id, kind, reason }
```

### Events Consumed

- `entity.extension.host_rescan` — invalidates cached kind map.
- `entity.client.revoked` — deletes all capability rows for the
  revoked client.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/clients/capabilities/
    __init__.py
    dtos.py                      -- CapabilityAdvertisement, CapabilityRow,
                                    CapabilityPredicate, AdvertisementApplyResult
    service.py                   -- apply_advertisement, get_*
    matcher.py                   -- find_clients_matching (predicate evaluator)
    kinds.py                     -- load_capability_kinds + schema validation
    repository.py                -- ClientCapabilityRepository
    handlers.py                  -- transport frame bridge
    rest.py
    metrics.py

source/site/automojo/pychestrate/extensions/capability_kinds/
    toolchain.py
    pod_member_ownership.py
    concurrency.py
    accelerator.py
    agent_feature_flag.py
```

## Key Flows

**Initial advertisement.** Post-enrollment, the client sends a
`CapabilityAdvertisementFrame` with its full capability set. Handler ->
`apply_advertisement` -> validates every value against the loaded kind
map -> opens a tx -> clears existing rows for this client -> inserts new
rows -> updates `client_capability_revision` -> publishes
`entity.client.capabilities_applied`.

**Delta advertisement.** Subsequent frames carry `delta.add`,
`delta.modify`, `delta.remove`. Handler -> `apply_advertisement` -> tx
with UPSERT per `add`/`modify` and DELETE per `remove` -> bumps revision.

**Dispatch match.** `5-job-dispatch` calls
`find_clients_matching(predicate)`. The evaluator compiles the predicate
into a SQL WHERE clause with an `EXISTS` subquery per term, joins with
`client` on `liveness_state in ('alive','suspect')`, returns a short
list of `client_id`s.

## Error Handling

- `UnknownCapabilityKind` — rejected advertisement with a detailed
  message; bus event `entity.client.capability_rejected`.
- `CapabilitySchemaError` — same path.
- `MaxValueBytesExceeded` — same path.
- `NonSearchableCapability` — raised by the matcher when a predicate
  touches a kind with `searchable=false`.
- `SensitiveValueLeak` — raised if a non-admin read path attempts to
  return a sensitive value; treated as `SemanticError` and never caught
  (indicates a programming bug).
- `ConfigurationError` — raised at startup on duplicate
  `capability_kind_name` or unloadable kind extensions.
- Multiline error messages per AGENTS.md.

## Security Considerations

- Sensitive values stored as `sensitive_ref` pointing into
  `1-secrets-vault`; the registry never materializes them on
  non-admin reads; admin reads audit-logged with actor and accessed
  kinds.
- Advertisement body capped at 1 MiB; individual values at
  `max_value_bytes` (default 64 KiB, kind can override up to 1 MiB).
- RBAC permissions: `client.capability.read`, `client.capability.admin`.
- The match API is only callable internally by other features; there
  is no public REST surface for arbitrary predicate queries (to prevent
  fleet enumeration attacks).

## Observability

Metrics:

- `pychestrate_client_capability_advertisements_total{outcome}` —
  counter.
- `pychestrate_client_capability_rows` — gauge.
- `pychestrate_client_capability_rejected_total{reason}` — counter.
- `pychestrate_client_capability_match_duration_seconds` — histogram.
- `pychestrate_client_capability_apply_duration_seconds` — histogram.

Log events: `pychestrate_client_capability_applied`,
`pychestrate_client_capability_rejected`,
`pychestrate_client_capability_match`.

Trace spans: `client_capability.apply`, `client_capability.match`.

## Open Questions

- Do we persist historical revisions for audit of capability drift?
  Lean toward a lightweight append-only log (revision + diff) capped at
  N=50 per client.
- Should `find_clients_matching` support weighted matching (best-fit)
  at this feature, or keep it boolean-only and defer scoring to
  `5-job-dispatch`? Keep it boolean-only here; dispatch owns scoring.
