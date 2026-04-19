# 3-pod-definitions — Design

## Architecture

Pod Definitions live at
`source/site/automojo/pychestrate/webservice/pods/definitions/`. Two
persistence tiers: a logical `pod_definition` row per project-scoped pod
(metadata, current version pointer) and an append-only
`pod_definition_version` row per version (full spec JSON). Validation runs
through `SuperFactory.create_instance_for_each("pod_spec_validator")`,
aggregating reports; the in-tree validators
(`IntegrityValidator`, `MemberKindValidator`, `LinkGraphValidator`) cover the
baseline checks and extensions can layer more. Member kinds come from the
extension host via `PodMemberKindExtension` subclasses and are cached at
startup. Authoritative state: the two tables plus the dictionary of loaded
member kinds. This feature is the *schema* layer for the rest of Layer 3 —
it does not run anything and does not touch the client plane directly.

## Data Model

```
pod_definition
    pod_id:             UUID     primary key
    project_id:         UUID     foreign key -> project
    pod_name:           str      not null
    current_version:    int      not null default 1
    created_at:         datetime not null
    created_by:         UUID     foreign key -> user
    deleted_at:         datetime nullable -- soft-delete
    (project_id, pod_name) unique

pod_definition_version
    pod_id:             UUID     composite primary key (with version)
    version:            int      composite primary key
    spec_json:          jsonb    not null -- full spec (members, links, client_binding, metadata)
    spec_hash:          str      not null -- sha256(canonical(spec_json))
    validator_report:   jsonb    not null -- captured warnings
    created_at:         datetime not null
    created_by:         UUID
    (pod_id, version) primary key
    (spec_hash) index
```

Canonical spec shape (JSON schema lives at
`pods/definitions/schemas/pod_spec.schema.json`):

```
{
    "pod_name": str,
    "description": str,
    "client_binding": {
        "pod_name": str,                   # client registry scope
        "required_capabilities": [str]
    },
    "members": [
        {
            "name": str,
            "kind": str,                   # maps to PodMemberKindExtension.member_kind_name
            "role": str,
            "attributes": { ... },
            "tags": [str]
        }
    ],
    "links": [
        {
            "from_member": str,
            "to_member": str,
            "role": str,                   # e.g. parent, peer, uplink
            "attributes": { ... }
        }
    ],
    "metadata": {
        "owner": str,
        "tags": [str]
    }
}
```

## Interfaces

### Public API

REST (RBAC `pod.definition.*`):

- `POST /api/v1/projects/{project_id}/pod-definitions` — create version 1 of
  a new pod.
- `PUT /api/v1/projects/{project_id}/pod-definitions/{pod_id}` — create a
  new version.
- `GET /api/v1/projects/{project_id}/pod-definitions` — list current
  versions.
- `GET /api/v1/projects/{project_id}/pod-definitions/{pod_id}` — current
  version (latest).
- `GET /api/v1/projects/{project_id}/pod-definitions/{pod_id}/versions` —
  all versions.
- `GET /api/v1/projects/{project_id}/pod-definitions/{pod_id}/versions/{version}`
  — a specific version.
- `DELETE /api/v1/projects/{project_id}/pod-definitions/{pod_id}` —
  soft-delete; fails if any in-flight run references any version.

### Internal API

```python
def validate_pod_spec(
    *,
    spec: PodSpec,
    project_id: UUID,
    validator_registry: FactoryRegistry,
    member_kind_registry: Mapping[str, PodMemberKind],
) -> ValidationReport:
    ...


def create_pod_definition(
    *,
    project_id: UUID,
    spec: PodSpec,
    created_by: UUID,
) -> PodDefinitionCreateResult:
    ...


def create_pod_definition_version(
    *,
    pod_id: UUID,
    spec: PodSpec,
    created_by: UUID,
) -> PodDefinitionVersionResult:
    ...


def get_pod_definition_version(
    *,
    pod_id: UUID,
    version: int,
) -> PodDefinitionVersion:
    ...


def list_pod_definitions(
    *,
    project_id: UUID,
    include_deleted: bool,
) -> List[PodDefinition]:
    ...
```

### Extension Surface

Factory protocol:

```python
class PodSpecValidatorProtocol(FactoryProtocolBase):
    factory_protocol_name = "pod_spec_validator"
    protocol_schema_version = 1

    @classmethod
    def validate(
        cls,
        *,
        spec: PodSpec,
        project_id: UUID,
        member_kind_registry: Mapping[str, PodMemberKind],
    ) -> ValidationReport:
        ...
```

In-tree implementations:

- `IntegrityValidator` (`PRECEDENCE=10`) — schema shape, unique names.
- `MemberKindValidator` (`PRECEDENCE=20`) — kind known, required attributes
  present, role allowed for kind.
- `LinkGraphValidator` (`PRECEDENCE=30`) — no dangling endpoints, parent-role
  acyclicity.

Resource extension:

```python
class PodMemberKindExtension(ResourceExtension):
    """
        Declares a new pod member kind, its required attributes, and its
        allowed roles.
    """

    member_kind_name: ClassVar[str]
    required_attributes: ClassVar[Mapping[str, JsonSchema]]
    optional_attributes: ClassVar[Mapping[str, JsonSchema]] = {}
    allowed_roles: ClassVar[Sequence[str]]
    display_label: ClassVar[str]
    renderer_hint: ClassVar[str] = "generic"
```

In-tree kinds shipped as reference: `LinuxHost`, `WindowsHost`, `NetworkSwitch`,
`SerialConsole`, `PowerDistributionUnit`, `SyntheticRole`.

### Events Emitted

```
entity.pod.definition_created       { pod_id, project_id, version }
entity.pod.definition_updated       { pod_id, project_id, version }
entity.pod.definition_deleted       { pod_id, project_id }
entity.pod.definition_validation_failed
                                    { project_id, errors }
```

### Events Consumed

- `entity.extension.host_rescan` — invalidates the cached member-kind
  registry and reloads from the extension host.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/pods/definitions/
    __init__.py
    dtos.py                      -- PodSpec, PodDefinition, PodDefinitionVersion,
                                    ValidationReport, ValidationError, ValidationWarning
    service.py                   -- create / update / get / list / delete
    validation.py                -- validate_pod_spec + aggregator
    repository.py                -- PodDefinitionRepository (SQL, SERIALIZABLE tx)
    rest.py                      -- Flask-RestX router
    member_kinds.py              -- load_member_kinds from extension host
    schemas/
        pod_spec.schema.json
    metrics.py

source/site/automojo/pychestrate/factories/pod_spec_validator/
    integrity.py                 -- PRECEDENCE=10
    member_kind.py               -- PRECEDENCE=20
    link_graph.py                -- PRECEDENCE=30

source/site/automojo/pychestrate/extensions/pod_member_kinds/
    linux_host.py
    windows_host.py
    network_switch.py
    serial_console.py
    pdu.py
    synthetic_role.py
```

## Key Flows

**New pod creation.** Admin POSTs spec -> `service.create_pod_definition` ->
`validate_pod_spec` iterates every registered validator in precedence order
-> on clean report, a serializable tx creates `pod_definition` + version 1
row; emits `entity.pod.definition_created`. On errors, HTTP 422 with the
aggregated list.

**Version bump.** Admin PUTs new spec -> service validates, opens a
serializable tx, reads `pod_definition.current_version`, writes
`pod_definition_version{version = current+1}`, updates
`pod_definition.current_version`, commits; emits
`entity.pod.definition_updated`.

**Soft-delete with in-flight runs.** Admin DELETEs -> service asks
`5-run-state-machine` whether any non-terminal run references any version
of this pod; if yes, responds 409 with the list; if no, writes `deleted_at`
and emits `entity.pod.definition_deleted`.

## Error Handling

- `ValidationError`, `UnknownMemberKind`, `RoleNotAllowedForKind`,
  `DanglingLinkEndpoint`, `ParentCycle` — all domain errors; caught at the
  REST boundary and translated to HTTP 422 with a structured body.
- `PodVersionInUse` — caught at the REST boundary, translated to HTTP 409.
- `ConcurrentVersionCollision` — serializable tx retry detector; retried
  once with a fresh read.
- `ConfigurationError` — raised at startup if the JSON schema file or a
  required validator factory is missing.
- `SemanticError` — never caught.
- Multiline error messages use `os.linesep.join([...])`:

```python
err_msg_lines = ["Pod definition failed validation."]
err_msg_lines.append("POD_NAME:        {}".format(spec.pod_name))
err_msg_lines.append("PROJECT_ID:      {}".format(project_id))
err_msg_lines.append("ERRORS:")
for err in report.errors:
    err_msg_lines.append("    - [{}] {}: {}".format(err.code, err.path, err.message))

err_msg = os.linesep.join(err_msg_lines)
raise PodSpecInvalid(err_msg) from None
```

## Security Considerations

- RBAC: `pod.definition.read`, `pod.definition.write`, `pod.definition.admin`.
- JSON request body capped at 256 KiB; per-member `attributes` map at 32 KiB.
- Every write audit-logged with compact `diff_summary` (added / removed /
  modified member names, link counts, role changes).
- Specs are scoped to project; cross-project link references rejected by
  `IntegrityValidator` unless `client.definition.cross_project` role is
  explicitly granted.

## Observability

Metrics:

- `pychestrate_pod_definition_rows` — gauge.
- `pychestrate_pod_definition_validations_total{outcome}` — counter
  (`outcome in {ok, rejected}`).
- `pychestrate_pod_definition_validation_seconds` — histogram.
- `pychestrate_pod_definition_versions_gauge` — gauge, labeled per pod.
- `pychestrate_pod_definition_members_total` — gauge.

Log events: `pychestrate_pod_definition_written`,
`pychestrate_pod_definition_rejected`.

Trace spans: `pod_definition.validate`, `pod_definition.write`,
`pod_definition.read`.

## Open Questions

- Do we support schema-less "draft" versions, or is every saved version
  fully-validated? Lean toward fully-validated only; defer drafts to
  client-side editor state.
- Should a pod definition reference `1-secrets-vault` secrets directly, or
  only through `3-pod-scoped-config`? Lean toward the latter for clean
  separation.
