# 4-resource-inventory — Design

## Architecture

Resource inventory is the root of Layer 4 and is wired between the pod plane
and the dispatcher. It owns a single Postgres-backed catalog table, a
per-kind registry populated from `ResourceKindExtension` subclasses, and a
small REST surface under `/api/v1/resources`. The authoritative source of
truth for every resource row is the `core.resources` table; the in-process
registry of loaded kinds is rebuilt on every extension-host rescan. Other
Layer 4 features (`4-resource-pools`, `4-checkout-checkin`,
`4-conflict-deconfliction`, `4-resource-health`, `4-usage-history`) read
this catalog through an internal read API rather than duplicating state.
The feature ships in Phase 4.

## Data Model

Schema `core`:

- `core.resources`
  - `resource_id: UUID` — PK, v7, time-ordered
  - `kind: str` — FK-by-name to in-memory kind registry
  - `identity_hash: str` — sha256 of normalized `identity_attrs` tuple
  - `state: ResourceState` — enum: `available`, `quarantined`, `retired`
  - `attrs: jsonb` — kind-validated attribute bag
  - `tags: jsonb` — list of strings from `2-tagging`
  - `notes: str | None`
  - `version: int`
  - `created_at: datetime`
  - `updated_at: datetime`
  - `retired_at: datetime | None`

Indices:

- PRIMARY KEY on `resource_id`
- UNIQUE on `(kind, identity_hash) WHERE state != 'retired'`
- INDEX on `(kind, state)`
- GIN INDEX on `tags` (jsonb ops)
- Per-kind expression indices declared by the kind (e.g. `(attrs->>'mac')`)

Sensitive attributes are stored as `{"secret_ref": "<vault-path>"}` inside
`attrs`; the raw value never lives in Postgres.

Resource kinds are *not* persisted rows — they live in the in-process
registry built from loaded `ResourceKindExtension` subclasses. The
`kind` column is a name only.

## Interfaces

### Public API

REST under `/api/v1/resources`:

- `POST /api/v1/resources` — register a resource. Body: `{kind, attrs, tags,
  notes}`. `201` on success with the persisted resource; `409` on identity
  clash; `422` on validator failure.
- `GET /api/v1/resources/{resource_id}` — fetch by id.
- `GET /api/v1/resources?kind=&state=&tags=&<kind-attr>=` — filtered list,
  paged.
- `PATCH /api/v1/resources/{resource_id}` — update mutable attrs / tags.
- `POST /api/v1/resources/{resource_id}:quarantine` — state transition.
- `POST /api/v1/resources/{resource_id}:heal` — state transition.
- `POST /api/v1/resources/{resource_id}:retire` — terminal state.

### Internal API

```python
def register_resource(
    kind_name: str,
    attrs: dict,
    tags: list[str],
    notes: str | None,
    actor: UserRef
) -> Resource:
    """
        Validate and persist a newly-registered external resource.

        :param kind_name: The declared resource kind.
        :param attrs: The kind-validated attribute payload.
        :param tags: Zero or more tags from the 2-tagging model.
        :param notes: Free-form operator notes.
        :param actor: The authenticated user performing the registration.

        :returns: The persisted Resource.
        :raises: ResourceKindUnknownError, ResourceAttributeError,
                 ResourceIdentityConflictError
    """
    ...


def load_resource(
    resource_id: UUID
) -> Resource | None:
    """
        Load a resource by primary key.

        :param resource_id: The resource id.

        :returns: The Resource, or None if not found.
    """
    ...


def query_resources(
    kind_name: str | None,
    state: ResourceState | None,
    tags: list[str] | None,
    attr_filters: dict | None,
    limit: int,
    offset: int
) -> list[Resource]:
    """
        Filter the inventory. Uses per-kind indices declared by the kind.

        :param kind_name: Optional kind filter.
        :param state: Optional state filter.
        :param tags: Optional tag-AND filter.
        :param attr_filters: Optional {attr_name: value} exact matches.
        :param limit: Page size.
        :param offset: Page offset.

        :returns: Matching resources ordered by (kind, resource_id).
    """
    ...


def transition_resource_state(
    resource_id: UUID,
    new_state: ResourceState,
    reason: str,
    actor: UserRef
) -> Resource:
    """
        Move a resource between lifecycle states with audit metadata.

        :param resource_id: The resource id.
        :param new_state: The target state.
        :param reason: Operator-provided reason, recorded in the audit log.
        :param actor: The authenticated user.

        :returns: The Resource after the transition.
        :raises: ResourceStateTransitionError
    """
    ...
```

### Extension Surface

Resource extension:

```python
class ResourceKindExtension(ResourceExtension):
    """
        Base class declaring a resource kind Pychestrate will track.

        Subclasses declare class attributes:
          - kind_name: str — globally-unique kind identifier
          - attribute_schema: dict — jsonschema for attrs validation
          - identity_attrs: tuple[str, ...] — attrs that define identity
          - indexed_attrs: tuple[str, ...] — attrs promoted to SQL indices
          - default_probe_name: str | None — health-probe binding
          - sensitive_attrs: tuple[str, ...] — routed to 1-secrets-vault
    """
    kind_name: str
    attribute_schema: dict
    identity_attrs: tuple
    indexed_attrs: tuple
    default_probe_name: str | None
    sensitive_attrs: tuple

    @classmethod
    def validate_attributes(
        cls,
        attrs: dict
    ) -> None:
        """
            Validate a payload against the kind's attribute_schema.

            :param attrs: The caller-supplied attribute payload.

            :raises: ResourceAttributeError
        """
        ...

    @classmethod
    def normalize_attributes(
        cls,
        attrs: dict
    ) -> dict:
        """
            Return a canonical form of attrs (e.g. CIDR normalization).

            :param attrs: The validated attribute payload.

            :returns: The normalized attribute payload.
        """
        ...

    @classmethod
    def render_public(
        cls,
        attrs: dict
    ) -> dict:
        """
            Redact sensitive fields for REST responses.

            :param attrs: The persisted attribute payload.

            :returns: A copy safe for external serialization.
        """
        ...
```

Reference implementations shipped in-tree under
`source/site/automojo/extensions/pychestrate/resources/kinds/`:

- `DeviceResourceKind` — generic lab device (attrs: `mac`, `serial`,
  `vendor`, `model`, `rack_slot`).
- `IPAddressResourceKind` — `address`, `subnet_ref`, `role`.
- `IPSubnetResourceKind` — `cidr`, `vlan`, `gateway`.
- `LicenseResourceKind` — `product`, `seat_count`, sensitive `token_ref`.

A test-only override `TestDeviceResourceKind` ships under `tests/` with a
lower numeric `PRECEDENCE` so extension-override semantics are covered.

### Events Emitted

On `0-message-bus`:

- `entity.resource.registered` — `{resource_id: UUID, kind: str, actor: UUID}`
- `entity.resource.quarantined` — `{resource_id: UUID, kind: str, reason: str, actor: UUID}`
- `entity.resource.healed` — `{resource_id: UUID, kind: str, reason: str, actor: UUID}`
- `entity.resource.retired` — `{resource_id: UUID, kind: str, actor: UUID}`
- `entity.resource.attributes_updated` — `{resource_id: UUID, kind: str, actor: UUID}`

### Events Consumed

- `extension.reloaded` from `E-extension-host` — rebuilds the in-process
  `ResourceKindExtension` registry and re-evaluates per-kind indices.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/`:

- `resources/inventory/__init__.py`
- `resources/inventory/models.py` — `Resource` dataclass, `ResourceState` enum.
- `resources/inventory/repository.py` — CRUD, index routing, state transitions.
- `resources/inventory/kind_registry.py` — in-process `ResourceKindExtension` index.
- `resources/inventory/service.py` — orchestrates validate → normalize → save.
- `resources/inventory/api.py` — Flask-RestX namespace under `/api/v1/resources`.
- `resources/inventory/errors.py` — `ResourceKindUnknownError`,
  `ResourceAttributeError`, `ResourceIdentityConflictError`,
  `ResourceStateTransitionError` (all domain errors, none caught-and-swallowed).
- `resources/inventory/events.py` — emitter wrappers for
  `entity.resource.*`.

Extension home:
`source/site/automojo/extensions/pychestrate/resources/kinds/`.

## Key Flows

### Flow 1 — Register a new device

1. `POST /api/v1/resources` arrives with `kind="device"` and a payload.
2. API handler resolves the kind in the kind registry — missing → `400`
   `ResourceKindUnknownError`.
3. Handler calls `kind.validate_attributes(attrs)` — failure → `422`.
4. Handler calls `kind.normalize_attributes(attrs)`.
5. Sensitive fields are written to `1-secrets-vault`; the persisted payload
   holds `{"secret_ref": "<path>"}` in their place.
6. `identity_hash = sha256(tuple(attrs[k] for k in kind.identity_attrs))`.
7. Inside `unit_of_work`, insert into `core.resources`; on unique-constraint
   violation raise `ResourceIdentityConflictError` → `409`.
8. Emit `entity.resource.registered`.
9. Handler returns `201` with `kind.render_public(attrs)`.

### Flow 2 — Quarantine on probe failure

1. `4-resource-health` observes a failing probe and calls
   `transition_resource_state(resource_id, ResourceState.QUARANTINED,
   reason="probe X failed", actor=<system>)`.
2. The transition rejects `retired → anything` with
   `ResourceStateTransitionError`.
3. `entity.resource.quarantined` fires; `4-checkout-checkin` subscribes
   and blocks new reservations. Active reservations are left alone so
   in-flight jobs may finish and release cleanly.

### Flow 3 — Filtered query hits a per-kind index

1. `GET /api/v1/resources?kind=device&state=available&mac=aa:bb:cc:dd:ee:ff`.
2. The API maps `mac=...` onto the `device` kind's declared indexed attr.
3. The repository issues `SELECT ... WHERE kind='device' AND state='available'
   AND attrs->>'mac' = :mac` — planner uses the expression index
   `idx_resources_device_mac`.
4. Result serialized through `kind.render_public` per row.

## Error Handling

- `ResourceKindUnknownError` → `400`, lists known kinds.
- `ResourceAttributeError` → `422`, includes per-field error list.
- `ResourceIdentityConflictError` → `409`, includes existing `resource_id`.
- `ResourceStateTransitionError` → `409`, includes current + attempted state.
- `SemanticError` (kind registry accessed before startup) MUST bubble per
  AGENTS.md.
- DB-layer errors (`DatabaseAcquireTimeoutError`,
  `DatabaseUnavailableError`) bubble to the request handler which translates
  them to `503`.
- Multiline errors built via `os.linesep.join([...])`:

```python
err_msg_lines = ["Rejected resource registration; duplicate identity."]
err_msg_lines.append("KIND: {}".format(kind_name))
err_msg_lines.append("IDENTITY ATTRS: {}".format(list(kind.identity_attrs)))
err_msg_lines.append("EXISTING RESOURCE_ID: {}".format(existing_id))

err_msg = os.linesep.join(err_msg_lines)
raise ResourceIdentityConflictError(err_msg) from None
```

## Security Considerations

- REST endpoints require permissions from `1-rbac`:
  `resource.inventory.read`, `resource.inventory.write`,
  `resource.inventory.transition`, `resource.inventory.retire`.
- Sensitive attributes (per-kind declared) are stored through
  `1-secrets-vault`; REST returns `secret_ref` only.
- All inputs validated before the kind validator runs — malformed JSON
  never reaches extension code.
- Registrations and state transitions emit `1-audit-log` events with actor
  and reason.
- Rate limit `POST /api/v1/resources` at 20/s per API token to prevent
  bulk-registration abuse.

## Observability

Metrics:

- `pychestrate_resource_registered_total{kind}` — counter
- `pychestrate_resource_quarantined_total{kind}` — counter
- `pychestrate_resource_healed_total{kind}` — counter
- `pychestrate_resource_retired_total{kind}` — counter
- `pychestrate_resource_inventory_size{kind,state}` — gauge
- `pychestrate_resource_query_duration_seconds{kind}` — histogram
- `pychestrate_resource_attribute_validation_failed_total{kind,field}` — counter

Log events:

- `pychestrate.resource.registered`
- `pychestrate.resource.quarantined`
- `pychestrate.resource.healed`
- `pychestrate.resource.retired`
- `pychestrate.resource.attribute_validation_failed`

Trace spans:

- `pychestrate.resource.register`
- `pychestrate.resource.query`
- `pychestrate.resource.transition`

Dashboards: "Resource Inventory" tile on `9-admin-ui` (per-kind counts, 24h
registration / quarantine / heal deltas), "Resource Health" burn-rate panel
on `7-resource-metrics`.

## Open Questions

- Do identity attrs need to be case-normalized (MAC addresses, serials)? The
  reference `DeviceResourceKind` normalizes to lowercase, but this should be
  a per-kind decision. Timebox: decide before Phase 4 exit.
- Should `retired` resources be soft-purged after N days, or kept forever
  for history? `2-retention-policies` owns the policy but needs a hook
  here. Timebox: Phase 4 hardening.
- Do we allow a kind to declare a *computed* identity hash (e.g. hash of
  MAC + serial when either may be missing)? Current model requires both.
  Timebox: defer to Phase 5.
