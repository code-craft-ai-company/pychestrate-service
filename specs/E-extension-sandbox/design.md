# E-extension-sandbox — Design

## Architecture

E-extension-sandbox is a two-point authorization layer: it intercepts
the host's factory-lookup path and the hook router's delivery path.
The `CapabilityAuthority` singleton owns the active per-extension
capability set (manifest-declared + operator-granted, minus operator-
revoked). Every authorization decision is a set-subset check:
`required ⊆ granted`. Grants and revocations persist in a small DB
table so restart behavior is preserved.

## Data Model

SQL (persistent):

- `extension_capability_grant` — table:
  - `ext_name: str`   (PK part)
  - `capability: str` (PK part)
  - `source: Literal["manifest","admin"]`
  - `granted_at: datetime`
  - `granted_by: Optional[str]`
  - `revoked_at: Optional[datetime]`
  - `revoked_by: Optional[str]`

In-memory:

- `CapabilityAuthority` holds:
  - `active: Dict[str, FrozenSet[str]]`  (ext_name → capabilities)
  - `vocabulary: FrozenSet[str]`         (closed set)
  - `protocol_requirements: Dict[str, FrozenSet[str]]`
  - `topic_requirements: Dict[str, FrozenSet[str]]`

## Interfaces

### Public API

Admin REST:

- `GET /admin/extensions/{name}/capabilities` — permission
  `extensions.read`.
- `POST /admin/extensions/{name}/capabilities/grant` body
  `{capability}` — permission `extensions.grant`.
- `POST /admin/extensions/{name}/capabilities/revoke` body
  `{capability, reason}` — permission `extensions.grant`.

### Internal API

Code under
`source/site/automojo/pychestrate/webservice/extension/sandbox/`.

```python
# authority.py
class CapabilityAuthority:
    """
        Process-singleton that tracks active capability grants and
        authorizes factory lookups and hook deliveries.
    """

    VOCABULARY: FrozenSet[str] = frozenset({
        "read:secrets",
        "write:artifacts",
        "dispatch:jobs",
        "net:outbound",
        "process:subprocess",
    })

    def __init__(self, *, repo: "CapabilityGrantRepo") -> None:
        ...

    def reload_from_manifests(self, *, manifests: Iterable["ExtensionManifest"]) -> None:
        ...

    def grant(self, *, ext_name: str, capability: str, actor: str) -> None:
        ...

    def revoke(self, *, ext_name: str, capability: str, actor: str,
               reason: str) -> None:
        ...

    def authorize_factory_call(self, *, ext_name: str,
                               protocol_name: str) -> None:
        """
            :raises PermissionError: required capabilities not granted.
        """
        ...

    def authorize_hook_delivery(self, *, ext_name: str,
                                topic: str) -> bool:
        ...

    def granted_for(self, *, ext_name: str) -> FrozenSet[str]:
        ...

    def required_for_protocol(self, *, protocol_name: str) -> FrozenSet[str]:
        ...


def get_capability_authority() -> CapabilityAuthority:
    ...


# repo.py
class CapabilityGrantRepo:
    """
        Persistence layer for capability grants and revocations.
    """

    def __init__(self, *, db: "Database") -> None:
        ...

    def list_active_for(self, *, ext_name: str) -> List[str]:
        ...

    def upsert_grant(self, *, ext_name: str, capability: str,
                     source: str, actor: Optional[str]) -> None:
        ...

    def mark_revoked(self, *, ext_name: str, capability: str,
                     actor: str, reason: str) -> None:
        ...
```

### Extension Surface

- `required_capabilities: FrozenSet[str]` class attribute on
  `FactoryProtocolBase` subclasses (declared in
  `E-factory-protocols`).
- `required_subscriber_capabilities: FrozenSet[str]` attribute on bus
  topic declaration records.

### Events Emitted

- `extension.capability_granted` — `{ext, capability, actor}`
- `extension.capability_revoked` — `{ext, capability, actor, reason}`
- `extension.call_denied` — `{ext, protocol, missing}`
- `extension.hook_denied` — `{ext, topic, missing}`

### Events Consumed

- `extension.manifest_parsed` — bootstraps manifest-sourced grants.
- `extension.manifest_rejected` — clears any stale grants.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/extension/sandbox/
    __init__.py
    authority.py           # CapabilityAuthority singleton
    repo.py                # CapabilityGrantRepo (DB-backed)
    vocabulary.py          # Closed capability vocabulary
    admin_routes.py        # Grant / revoke REST endpoints
    requirements.py        # Helpers to read required_capabilities off
                           # protocol classes and bus topics
```

## Key Flows

### Flow A — Authorize a factory call

1. Consumer calls
   `host.create_instance_by_order(factory_method=...)`.
2. Host resolves winning factory; identifies its owning extension
   (manifest name that shipped the factory's module).
3. Host calls `authority.authorize_factory_call(ext_name=...,
   protocol_name=...)` before invoking the callable.
4. Authority looks up `required = protocol_requirements[protocol_name]`
   and `granted = active[ext_name]`; checks `required ⊆ granted`.
5. On mismatch → raise `PermissionError`, emit
   `extension.call_denied`, metric increment.
6. On match → record positive-check metric and return.

### Flow B — Authorize a hook delivery

1. Router dispatches; calls
   `authority.authorize_hook_delivery(ext_name=..., topic=...)`.
2. Returns True/False; False → router drops delivery and emits
   `extension.hook_denied`.
3. Re-check at every delivery (not cached across events) so
   revocation takes effect instantly.

### Flow C — Operator grant + revoke

1. Admin POSTs `/admin/extensions/foo/capabilities/grant` with
   `{"capability": "dispatch:jobs"}` and `extensions.grant` permission.
2. Authority validates capability is in `VOCABULARY`; refuses
   otherwise with 400.
3. `repo.upsert_grant` writes a row; in-memory `active[foo]` is
   rebuilt from repo.
4. Emits `extension.capability_granted`; audit-logged via
   `1-audit-log`.
5. Revoke is symmetric: writes the revoked-at columns, rebuilds the
   in-memory set, emits `extension.capability_revoked`.

### Flow D — Runtime revocation with active lease

1. Revoke invoked while the extension holds a `process:subprocess`
   lease.
2. Authority emits `extension.capability_revoked` and signals the
   lifecycle coordinator to fire `on_service_draining` for that
   extension.
3. Extension is expected to wind down its lease; subsequent calls
   through the host deny.

## Error Handling

- `PermissionError` for denied factory calls; never swallowed.
- `ConfigurationError` for unknown capability in a manifest
  (bootstrap) or admin grant (API).
- Delivery denials are not exceptions; they are logged drops.
- Multiline messages via `os.linesep.join`.

## Security Considerations

- Closed vocabulary prevents string-splicing attacks.
- Grants + revocations persisted so they survive restart.
- Every grant and revoke audit-logged via `1-audit-log` with actor +
  reason.
- Admin endpoints require RBAC permission `extensions.grant`.
- Authority is the only component that reads the grant table; all
  other code asks via `authorize_*`.

## Observability

- Metrics:
  - `pychestrate_extension_capability_check_total{ext,capability,result}`
  - `pychestrate_extension_call_denied_total{ext,protocol}`
  - `pychestrate_extension_hook_denied_total{ext,topic}`
  - `pychestrate_extension_capability_granted_total{capability}`
  - `pychestrate_extension_capability_revoked_total{capability}`
- Log events: `pychestrate_extension_call_denied`,
  `pychestrate_extension_hook_denied`,
  `pychestrate_extension_capability_granted`,
  `pychestrate_extension_capability_revoked`.
- Trace span: `pychestrate_extension.sandbox.authorize`.

## Open Questions

- Should we support time-bounded grants (expiring capabilities)?
  Timebox to Phase 10.
- Should the vocabulary grow per-layer as new capabilities are added,
  or should capabilities be composed? Decision: grow-and-document.
