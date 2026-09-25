# 0-config-formats — Design

## Overview

Four externally-authored document domains (`resource_spec`, `landscape`,
`topology`, `credentials`) enter Pychestrate through one pipeline:

```
<presence_dir>/config/<domain file>
        |
        v
  format resolver          config.format.<domain>  ->  format_name
        |
        v
  config_document_format implementation  (codecraftai @ PRECEDENCE 1000,
        |                                  enterprise @ lower)
        v
  canonical document dataclass   <-- the only thing the rest of the service sees
        |
        v
  validation report  --(errors)-->  refuse to project
        |
        v
  projection onto 4-resource-inventory / 3-pod-definitions
```

The seam is deliberate: **format knowledge stops at the protocol
boundary.** No module downstream of the canonical dataclass knows whether
the bytes on disk were `codecraftai` YAML, a ServiceNow export, or a
CMDB REST snapshot.

## Placement

```
source/site/ccai/pychestrate/webservice/configdocs/
    __init__.py            # bootstrap registration of the codecraftai defaults
    domains.py             # ConfigDocumentDomain enum, domain -> default basename
    models.py              # canonical dataclasses + AddressPlane model
    protocol.py            # ConfigDocumentFormatProtocol (FactoryProtocolBase)
    resolver.py            # presence-dir path resolution + per-domain format lookup
    loader.py              # orchestration: resolve -> parse -> validate -> report
    validation.py          # ValidationReport, diagnostic codes
    errors.py              # ConfigDocumentParseError, DomainBleedError, ...
    projection/
        resources.py       # canonical landscape -> 4-resource-inventory rows
        pods.py            # canonical topology  -> 3-pod-definitions specs
    formats/
        codecraftai_landscape.py
        codecraftai_topology.py
        codecraftai_credentials.py
        codecraftai_resource_spec.py
```

This mirrors `resources/inventory/kinds/` — protocol beside the in-tree
reference implementation, registration in the package `__init__`.

## The Protocol

```python
class ConfigDocumentFormatProtocol(FactoryProtocolBase):
    factory_protocol_name: str = "config_document_format"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000
    published_docs_url: str = "https://docs.pychestrate.io/plugin-api/config_document_format"

    @classmethod
    def document_domain(cls) -> str: ...

    @classmethod
    def format_name(cls) -> str: ...

    @classmethod
    def file_basenames(cls) -> Tuple[str, ...]: ...

    @classmethod
    def parse(cls, *, path: str, text: str) -> ConfigDocument: ...

    @classmethod
    def validate(cls, *, document: ConfigDocument) -> ValidationReport: ...
```

Resolution reuses the registry as-is. `register_factory_implementation`
already sorts each protocol bucket by `PRECEDENCE` ascending, and
`resolve_factory_implementation` returns the first predicate match — so

```python
impl = resolve_factory_implementation(
    factory_protocol_name="config_document_format",
    predicate=lambda cls: (
        cls.document_domain() == domain and cls.format_name() == selected
    ),
)
```

gives the enterprise implementation precedence over the shipped default
whenever it registers below 1000. **No registry change is required.**

## Canonical Models

`models.py` holds frozen dataclasses. The landscape model is the load
bearing one:

```python
@dataclass(frozen=True)
class DeviceAddresses:
    public: Optional[str]
    private: Optional[str]
    overlay: Mapping[str, str]      # provider -> address

    def resolve(self, *, plane: str,
                fallback_planes: Optional[Sequence[str]]) -> Optional[str]: ...


@dataclass(frozen=True)
class LandscapeDevice:
    identity: str                   # canonical identity (Requirement 7)
    name: str
    device_type: str                # landscaping 'deviceType'
    role: Optional[str]
    group: Optional[str]
    addresses: DeviceAddresses
    credential_refs: Tuple[str, ...]
    features: Mapping[str, Any]
    skipped: bool
    extra_attributes: Mapping[str, Any]


@dataclass(frozen=True)
class LandscapeDocument:
    schema_version: int
    source_path: str
    source_format: str
    environment: Mapping[str, Any]
    clients: Tuple[LandscapeDevice, ...]
    infrastructure: Tuple[LandscapeDevice, ...]
    services: Tuple[LandscapeService, ...]
    vpn: Mapping[str, Any]
    extra_attributes: Mapping[str, Any]
```

`DeviceAddresses.resolve` mirrors the total, never-raising semantics of
landscaping's `DeviceAddressSet.resolve` (`specs/device-address-set`,
Requirement 2) so that a device resolved here and the same device
resolved inside landscaping agree.

`resolve` is pure and total, which makes it cheap to property-test the
plane-priority semantics the same way landscaping does.

## Relationship to `codecraftai-landscaping`

Two options were considered.

**Depend on landscaping and reuse its loader.** Rejected for the service:
landscaping pulls in coordinators, interop, and SSH/serial/vSphere
machinery whose job is to *reach* devices. The web service must never
open an SSH session to a lab host from a request thread, and adding that
dependency tree to the service process is a large attack- and
startup-surface increase for a parser.

**Re-declare a canonical model in Pychestrate and map onto it.** Chosen.
The `codecraftai_landscape` format implementation reads the same YAML
schema and produces the canonical model. The dependency it needs is the
schema, not the runtime.

The consequence to accept: the landscape schema is now described in two
repositories, so a schema change in landscaping requires a matching
change here. Requirement 3's acceptance criteria are written against
landscaping's own spec files, and the task list adds a contract test that
loads landscaping's spec fixtures directly, so drift fails a test rather
than surfacing in production. `pychestrate-client`, which *does* run on
the pod and *does* need to reach devices, remains free to depend on
landscaping in full.

Credentials are the exception: `codecraftai-credentials` is already a
`pychestrate-service` dependency (`dbconnection.py` and `metadata.py`
use `CredentialManager` for database connections). The
credentials format implementation reuses `CredentialManager` directly for
reference resolution rather than re-declaring it.

## Layout on Disk

```
<presence_dir>/config/
    resource-specs.yaml     # or resource-specs.d/
    landscape.yaml          # or landscape.d/
    topology.yaml           # or topology.d/
    credentials.yaml        # or credentials.d/
```

The `.d/` directory form (Requirement 4.6) is what makes per-lab or
per-team split-out practical without teaching the loader about includes —
lexical concatenation with duplicate-identity detection is easier to
reason about than an include graph, and it composes with git ownership
boundaries.

Domain bleed (Requirement 4.3) is checked *before* parse dispatch: each
format implementation publishes the top-level keys it owns, and the
loader rejects a file whose top-level keys intersect another domain's
claimed set. This is what stops `credentials:` from being quietly
accepted inside `landscape.yaml` — the single most likely way an inline
secret would reach a git repository.

## Format Selection

`config.format.<domain>` is read through `2-global-variables`, which
already backs the `ui.profile.surfaces` deployment setting from Phase 11
— same storage, same admin-settings pattern, same audit path. Selection
is resolved once at bootstrap and cached with the loaded document; a
format change requires an explicit reload (or restart), so a request
thread never observes a half-swapped format.

## Projection

Projection is a separate, explicitly invoked step, never a side effect of
loading. `projection/resources.py` diffs the canonical document against
`resources_resource` and emits an ordered change set: `create`, `update`,
`adopt_identity` (Requirement 7.3), `mark_unreferenced` (7.5). The
dry-run entry point (Requirement 8.4) returns that change set without
applying it, which is what makes the first import against a populated
database reviewable.

Because projection never deletes, an operator who points the service at a
truncated landscape file gets a pile of `unreferenced` marks and their
data intact.

## Migration

`4-resource-inventory` and `3-pod-definitions` are marked Done, so this
lands as a retrofit:

- The existing `DeviceResourceKind` stays registered and the REST/UI
  registration path keeps working; hand-entry and document import are
  both supported, and the resource row records which produced it.
- One alembic migration adds `canonical_identity` (nullable, indexed) to
  `resources_resource` and a `provenance` column defaulting to `manual`.
- The legacy `(hostname, mac_address)` identity hash is retained for
  one-time adoption matching (Requirement 7.3) and stays the identity for
  rows never touched by an import.

## Testing

- Round-trip and golden-file tests per shipped format.
- A contract test that parses the fixture landscape files from
  `codecraftai-landscaping/specs/` and the emit format described by
  `codecraftai-provisioning/specs/landscape-inventory-emit`, so drift in
  either repo fails here.
- Property tests over `DeviceAddresses.resolve` covering every
  present/absent plane combination, mirroring landscaping's own
  hypothesis suite.
- A negative suite: inline secrets, domain bleed, duplicate identity,
  unknown format name, unregistered domain, shadowed `(domain, format)`.
- A fake enterprise format registered at `PRECEDENCE = 100` asserting it
  overrides the `codecraftai` default for its domain only, leaving the
  other three on defaults.
