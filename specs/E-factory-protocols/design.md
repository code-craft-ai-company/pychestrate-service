# E-factory-protocols — Design

## Architecture

E-factory-protocols lives one layer above `E-extension-host`. The host owns
*loaded implementations*; this feature owns *declared protocols*. It ships
the `FactoryProtocolCatalog` singleton, the module tree under
`source/site/ccai/pychestrate/webservice/extension/protocols/` where
each protocol is its own Python module, the reference-implementation
convention under `source/site/ccai/factories/pychestrate/_reference/`,
and a lint step that enforces the declaration template. Downstream
consumers import their protocol class directly; they never hand-write
magic strings against the host. The catalog is the authoritative source
of truth for `(name, schema_version, owning_feature, reference_impl)`.

## Data Model

In-memory entities (no SQL):

- `FactoryProtocolCatalogEntry` — dataclass:
  - `name: str`  (matches `factory_protocol_name`)
  - `protocol_cls: Type[FactoryProtocolBase]`
  - `schema_version: int`
  - `owning_feature_id: str`   (e.g., `"0-object-store"`)
  - `reference_impl_qualname: Optional[str]`
  - `declared_methods: Tuple[str, ...]`
  - `sphinx_contract: str`
  - `stability: Literal["internal", "published"]`
- `FactoryProtocolCatalog` holds `Dict[str, FactoryProtocolCatalogEntry]`.

## Interfaces

### Public API

CLI via `pychestrate-admin`:

- `pychestrate-admin protocols list [--json]` — print catalog rows.
- `pychestrate-admin protocols show <name>` — print catalog entry plus the
  Sphinx contract.
- `pychestrate-admin protocols check` — run the declaration-template
  linter; exit non-zero on missing fields.

REST under `9-admin-ui` (Phase 10, surfaced by
`E-extension-registry-ui`):

- `GET /admin/extensions/protocols` — permission `extensions.read` —
  returns the full catalog as JSON.

### Internal API

Code lives under
`source/site/ccai/pychestrate/webservice/extension/protocols/`.

```python
# catalog.py
class FactoryProtocolCatalog:
    """
        Process-singleton catalog of declared FactoryProtocolBase subclasses.
    """

    def __init__(self) -> None:
        ...

    def register(self, *, entry: FactoryProtocolCatalogEntry) -> None:
        """
            Adds an entry to the catalog. Raises ConfigurationError on
            duplicate name.
        """
        ...

    def register_from_module(self, *, module_name: str) -> List[FactoryProtocolCatalogEntry]:
        ...

    def get(self, *, name: str) -> Optional[FactoryProtocolCatalogEntry]:
        ...

    def resolve(self, *, protocol_cls: Type[FactoryProtocolBase]) -> "ProtocolProxy":
        ...

    def list_entries(self) -> List[FactoryProtocolCatalogEntry]:
        ...


def get_factory_protocol_catalog() -> FactoryProtocolCatalog:
    ...


# proxy.py
class ProtocolProxy:
    """
        Thin adapter bound to (catalog_entry, extension_host) that exposes
        typed lookup methods keyed to a specific protocol class.
    """

    def __init__(self, *, entry: FactoryProtocolCatalogEntry, host: "ExtensionHost") -> None:
        ...

    def create_instance(self, *, factory_method: Callable,
                        args: Optional[Tuple] = None,
                        kwargs: Optional[Dict[str, Any]] = None) -> Optional[object]:
        ...

    def create_instance_for_each(self, *, factory_method: Callable,
                                 args: Optional[Tuple] = None,
                                 kwargs: Optional[Dict[str, Any]] = None) -> List[object]:
        ...

    def get_override_type(self, *, get_type_method: Callable) -> Optional[Type]:
        ...

    def iterate_override_types(self, *, get_type_method: Callable,
                               iterate_type_lists: bool = True) -> Iterator[Type]:
        ...
```

### Declaration Template

Every protocol module under `protocols/` follows:

```python
from ccai.extension.factory.factoryprotocolbase import FactoryProtocolBase


class ObjectStoreDriverProtocol(FactoryProtocolBase):
    """
        Protocol for object store driver factories.

        :stability: internal
        :owning_feature: 0-object-store
    """

    factory_protocol_name = "object_store_driver"
    FACTORY_PROTOCOL_SCHEMA_VERSION = 1

    @classmethod
    def create_driver(cls, *, config: "ObjectStoreConfig") -> "ObjectStoreDriver":
        ...
```

### Extension Surface

- `FactoryProtocolBase` (re-exported) — base class extension packs
  subclass to declare new internal protocols. External-stable declarations
  live in `E-plugin-api`.
- Reference implementations live under
  `source/site/ccai/factories/pychestrate/_reference/` and set
  `PRECEDENCE = 1000` (the "reference" band; lower is higher priority).

### Events Emitted

- `extension.protocol_registered` —
  `{name: str, schema_version: int, owning_feature: str}`
- `extension.protocol_schema_ahead` —
  `{name: str, catalog_version: int, factory_version: int, factory_qualname: str}`

### Events Consumed

- `extension.loaded` — to validate that every loaded factory's
  `factory_protocol_name` exists in the catalog; if not, emit
  `extension.load_failed` with reason `unknown_protocol`.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/extension/protocols/
    __init__.py
    catalog.py             # FactoryProtocolCatalog + singleton accessor
    proxy.py               # ProtocolProxy
    entry.py               # FactoryProtocolCatalogEntry dataclass
    lint.py                # Declaration-template linter
    admin_routes.py        # GET /admin/extensions/protocols
    _declarations/         # One file per declared protocol; populated as
                           # each owning feature ships its Ext surface.
```

## Key Flows

### Flow A — Declaration + registration at import time

1. A feature (e.g., `0-object-store`) adds
   `_declarations/object_store_driver.py` with the template above.
2. Lint step `protocols/lint.py` runs in CI and asserts the declaration
   meets the template contract; fails the build otherwise.
3. At service bootstrap, `register_from_module` imports every declared
   module and registers a `FactoryProtocolCatalogEntry`.
4. If any duplicate `name` is seen, catalog raises `ConfigurationError`
   and aborts startup.

### Flow B — Consumer lookup

1. `0-object-store` imports `ObjectStoreDriverProtocol` from
   `protocols/_declarations/object_store_driver.py`.
2. Calls `get_factory_protocol_catalog().resolve(
   protocol_cls=ObjectStoreDriverProtocol)` — returns a `ProtocolProxy`.
3. Calls `proxy.create_instance(factory_method=
   ObjectStoreDriverProtocol.create_driver, kwargs={"config": cfg})`.
4. Proxy delegates to host's `create_instance_by_order`, surfacing the
   winning implementation.

### Flow C — Schema version gate

1. At `extension.loaded` consumption, catalog compares the loaded factory's
   `FACTORY_PROTOCOL_SCHEMA_VERSION_IMPLEMENTED` against the catalog
   entry's `schema_version`.
2. Lower impl version → host is asked to deregister the factory and
   record an `ExtensionLoadFailure` with reason `schema_version_too_old`.
3. Higher impl version → emit `extension.protocol_schema_ahead` warning
   but keep the factory registered.

## Error Handling

- `ConfigurationError` for duplicate names, missing declaration fields,
  unknown protocol on a loaded factory (strict mode).
- `SemanticError` when a caller `resolve`s a protocol class never
  registered — always bubbles.
- Every caught exception from catalog operations is reclassified with the
  offending name appended to the `lines` list before re-raise.

## Security Considerations

- Catalog is read-only post-bootstrap; registration helpers are module-
  private and only re-entered by the host's rescan path.
- REST surface (`GET /admin/extensions/protocols`) requires the
  `extensions.read` RBAC permission.
- `stability: "published"` entries are the only ones re-exported from
  `E-plugin-api`; internal protocols never leak through that surface.

## Observability

- Metrics:
  - `pychestrate_extension_protocol_registered_total{protocol,schema_version}`
  - `pychestrate_extension_protocol_lookup_total{protocol,result}`
  - `pychestrate_extension_protocol_schema_ahead_total{protocol}`
- Log events: `pychestrate_extension_protocol_registered`,
  `pychestrate_extension_protocol_schema_ahead`,
  `pychestrate_extension_protocol_unknown`.
- Trace spans: `pychestrate_extension.protocol_catalog.register`,
  `pychestrate_extension.protocol_catalog.resolve`.

## Open Questions

- Should schema bumps require a deprecation window for
  `stability: "published"` protocols? Timebox to Phase 10 when
  `E-plugin-api` lands.
- Should the catalog expose a JSON-schema-like declarative form for
  non-Python consumers? Deferred pending real demand.
