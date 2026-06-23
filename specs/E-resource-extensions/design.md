# E-resource-extensions — Design

## Architecture

E-resource-extensions is the sibling of `E-factory-protocols` for the
"new kind of thing" extension surface. The `ResourceExtensionCatalog`
tracks declared base classes and, for each base, maintains a sorted
tuple of discovered subclasses. The feature re-uses `E-extension-host`
for module discovery and is invoked during host bootstrap and every
rescan. Downstream consumers never scan modules themselves; they call
`collect_kinds(base_cls=...)`.

## Data Model

In-memory (no SQL):

- `ResourceExtensionBaseEntry` — dataclass:
  - `base_name: str`
  - `base_cls: Type[ResourceExtension]`
  - `owning_feature_id: str`
  - `allow_indirect_subclasses: bool`
  - `attribute_schema_required: bool`
- `ResourceExtensionKindEntry` — dataclass:
  - `base_cls: Type[ResourceExtension]`
  - `kind_name: str`
  - `kind_cls: Type[ResourceExtension]`
  - `attribute_schema: Mapping[str, Type]`
  - `owning_module: str`
- `ResourceExtensionCatalog` keeps:
  - `bases: Dict[str, ResourceExtensionBaseEntry]`
  - `kinds: Dict[Type[ResourceExtension], Tuple[ResourceExtensionKindEntry, ...]]`

## Interfaces

### Public API

CLI:

- `pychestrate-admin resources list [--base=<name>] [--json]`
- `pychestrate-admin resources show <base> <kind>`

REST (Phase 10 via `E-extension-registry-ui`):

- `GET /admin/extensions/resources` — permission `extensions.read`.

### Internal API

Code under
`source/site/ccai/pychestrate/webservice/extension/resources/`.

```python
# catalog.py
class ResourceExtensionCatalog:
    """
        Process-singleton catalog of declared ResourceExtension bases and
        their discovered subclasses.
    """

    def __init__(self) -> None:
        ...

    def register_base(self, *, entry: ResourceExtensionBaseEntry) -> None:
        ...

    def register_kind(self, *, entry: ResourceExtensionKindEntry) -> None:
        ...

    def rebuild_from_host_snapshot(self, *, snapshot: "ExtensionHostSnapshot") -> None:
        """
            Re-derives the per-base kind collections from the host's
            current snapshot. Atomic swap on success.
        """
        ...

    def collect_kinds(self, *, base_cls: Type[ResourceExtension]) -> List[ResourceExtensionKindEntry]:
        ...

    def get_kind(self, *, base_cls: Type[ResourceExtension],
                 name: str) -> Optional[ResourceExtensionKindEntry]:
        ...

    def list_bases(self) -> List[ResourceExtensionBaseEntry]:
        ...


def get_resource_extension_catalog() -> ResourceExtensionCatalog:
    ...


# scanner.py
def collect_resource_extensions_under_module(*, module_name: str,
                                             base_cls: Type[ResourceExtension],
                                             allow_indirect: bool) -> List[Type[ResourceExtension]]:
    ...
```

### Declaration Template

Every base declaration module under `resources/_declarations/` follows:

```python
from ccai.extension.resource.resourceextension import ResourceExtension


class PodMemberKindExtension(ResourceExtension):
    """
        Base class for contributed pod member kinds.

        :owning_feature: 3-pod-definitions
    """

    is_resource_extension_base = True
    resource_base_name = "pod_member_kind"
    attribute_schema_required = True
```

### Extension Surface

This feature *declares the declaration surface* for every `resource:`
point used by downstream features; see implementation-plan.md for the
full list. Consumer subclasses live in extension packs.

### Events Emitted

- `extension.resource_base_registered` —
  `{base_name: str, owning_feature: str}`
- `extension.resource_kind_registered` —
  `{base_name: str, kind_name: str, kind_qualname: str,
    owning_module: str}`
- `extension.resource_kinds_changed` —
  `{base_name: str, added: List[str], removed: List[str]}`

### Events Consumed

- `extension.loaded` and `extension.rescan_completed` — triggers catalog
  rebuild.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/extension/resources/
    __init__.py
    catalog.py             # ResourceExtensionCatalog + singleton accessor
    entry.py               # Dataclasses
    scanner.py             # Reuses codecraftai-extension helpers with
                           # Pychestrate filters
    admin_routes.py        # GET /admin/extensions/resources
    _declarations/         # Per-base declaration modules
```

## Key Flows

### Flow A — Base declaration

1. Feature (`3-pod-definitions`) adds
   `_declarations/pod_member_kind.py`.
2. During bootstrap, `register_base` inserts the entry into
   `catalog.bases`.
3. Duplicate `resource_base_name` raises `ConfigurationError`.

### Flow B — Kind discovery

1. `E-extension-host` bootstrap completes with a snapshot.
2. Catalog subscribes to `extension.loaded`; after the final load event,
   it calls `rebuild_from_host_snapshot`.
3. For every declared base, rebuild walks the snapshot's module list
   and extracts subclasses (direct or indirect per the base flag).
4. Duplicate `kind_name` under a single base raises
   `ConfigurationError`.
5. Build new `kinds` dict; atomic-swap replace; emit
   `extension.resource_kinds_changed` with diff vs previous.

### Flow C — Consumer iteration

1. `3-pod-definitions` calls
   `get_resource_extension_catalog().collect_kinds(
   base_cls=PodMemberKindExtension)`.
2. Catalog returns the cached sorted tuple.
3. Consumer iterates `(entry.kind_name, entry.kind_cls)`.

## Error Handling

- `ConfigurationError` — duplicate `resource_base_name`, duplicate
  `kind_name` under a base, missing required `attribute_schema` when the
  base requires it.
- `SemanticError` — `collect_kinds` with an unregistered `base_cls`;
  always bubbles.
- Multiline error messages for bootstrap-time failures assembled via
  `os.linesep.join`.

## Security Considerations

- Catalog is read-only post-bootstrap; mutation helpers are module-
  private.
- REST surface gated by `extensions.read`.
- Indirect-subclass inclusion is opt-in per base; default is direct-only
  to prevent a rogue base class from capturing unrelated subclasses.

## Observability

- Metrics:
  - `pychestrate_extension_resource_base_registered_total{base}`
  - `pychestrate_extension_resource_kind_registered_total{base,kind}`
  - `pychestrate_extension_resource_collect_total{base}`
  - `pychestrate_extension_resource_rebuild_duration_seconds`
- Log events: `pychestrate_extension_resource_base_registered`,
  `pychestrate_extension_resource_kind_registered`,
  `pychestrate_extension_resource_kinds_changed`.
- Trace span: `pychestrate_extension.resource_catalog.rebuild`,
  `pychestrate_extension.resource_catalog.collect`.

## Open Questions

- Should kinds carry a stability flag equivalent to factory protocols'
  so `E-plugin-api` can publish only published kinds? Timebox to Phase
  10.
- Should the attribute schema support Pydantic rather than plain
  `Mapping[str, Type]`? Deferred pending real need.
