# E-extension-host — Design

## Architecture

`E-extension-host` is a process-singleton owned by Layer 0's app bootstrap. It
is constructed during the `codecraftai-webworks` startup hook after the message
bus and persistence layer come online but before any feature-level singletons
that consume drivers (e.g., `0-object-store`, `1-secrets-vault`). The host owns
two typed registries: an ordered `FactoryExtension` chain (sorted ascending by
`PRECEDENCE`, tie-broken by qualified name) and a `dict[type[ResourceExtension],
list[type[ResourceExtension]]]` grouped by declared base. The host is the
authoritative source of truth for *which implementations are installed*; each
consumer layer is the source of truth for *which protocol methods exist*.
Lookup calls mirror `codecraftai-extension`'s `SuperFactory`
(`create_instance_by_order`, `create_instance_for_each`,
`get_override_types_by_order`, `iterate_override_types_for_each`); Pychestrate
adds `rescan`, `snapshot_digest`, `list_factory_protocols`, and
`list_resource_kinds`.

## Data Model

The host keeps only in-memory state. No SQL tables are owned here; the
`E-extension-registry-ui` feature reads from `list_*` helpers and joins against
`1-audit-log` entries.

In-memory entities:

- `ExtensionHostSnapshot` — dataclass:
  - `snapshot_id: UUID`
  - `taken_at: datetime`
  - `factory_chain: tuple[type[FactoryExtension], ...]`
  - `resource_collections: Mapping[type[ResourceExtension], tuple[type[ResourceExtension], ...]]`
  - `module_names: tuple[str, ...]`
  - `digest: str`  (SHA-256 over sorted qualnames + PRECEDENCE values)
- `ExtensionLoadFailure` — dataclass:
  - `module_name: str`
  - `phase: Literal["import", "validate", "register"]`
  - `exception_type: str`
  - `message: str`
  - `traceback: str`
  - `occurred_at: datetime`

## Interfaces

### Public API

Admin HTTP (Phase 0.5 minimal; richer UI ships with `E-extension-registry-ui`):

- `POST /admin/extensions/rescan` — permission `extensions.rescan`. Request
  body empty. Response body:
  `{"modules_added": int, "modules_removed": int, "factories_added": int,
    "resources_added": int, "snapshot_id": str}`.
- `GET /admin/extensions/snapshot` — permission `extensions.read`. Response
  body contains the current snapshot fields serialized as JSON.

### Internal API

All code lives under
`source/site/ccai/pychestrate/webservice/extension/host/`.

```python
# host.py
class ExtensionHost:
    """
        Process-singleton that owns the loaded factory chain and
        resource collections for the service.
    """

    def __init__(self, *, scan_paths: List[str], strict: bool) -> None:
        ...

    def bootstrap(self, *, extra_modules: Optional[List[str]] = None) -> "ExtensionHostSnapshot":
        """
            Walks scan_paths, imports discovered modules, validates and
            registers factory and resource classes, returns the initial
            snapshot.
        """
        ...

    def rescan(self) -> "ExtensionHostSnapshot":
        """
            Re-walks scan_paths and registers any newly discovered modules.
        """
        ...

    def create_instance_by_order(self, *, factory_method: Callable, args: Optional[Tuple] = None,
                                 kwargs: Optional[Dict[str, Any]] = None) -> Optional[object]:
        ...

    def create_instance_for_each(self, *, factory_method: Callable, args: Optional[Tuple] = None,
                                 kwargs: Optional[Dict[str, Any]] = None) -> List[object]:
        ...

    def get_override_types_by_order(self, *, get_type_method: Callable) -> Optional[Type]:
        ...

    def iterate_override_types_for_each(self, *, get_type_method: Callable,
                                        iterate_type_lists: bool = True) -> Iterator[Type]:
        ...

    def list_factory_protocols(self) -> List[str]:
        ...

    def list_resource_kinds(self) -> Dict[str, List[str]]:
        ...

    def snapshot_digest(self) -> str:
        ...


def get_extension_host() -> ExtensionHost:
    """
        Returns the bootstrapped singleton. Raises SemanticError if called
        before bootstrap.
    """
    ...
```

```python
# scanner.py
def scan_pychestrate_namespaces(*, scan_paths: List[str]) -> List[str]:
    """
        Walks each scan path for ccai/factories/pychestrate and
        ccai/extensions/pychestrate descendant modules.
    """
    ...

def load_factory_extension_types(*, module_name: str) -> List[Type["FactoryExtension"]]:
    ...

def load_resource_extension_types(*, module_name: str,
                                  bases: List[Type["ResourceExtension"]]) -> List[Tuple[Type, Type]]:
    ...
```

### Extension Surface

None. This feature *implements* the host. The factory protocols and resource
kinds themselves are declared in `E-factory-protocols` and
`E-resource-extensions`.

### Events Emitted

- `extension.loaded` — `{qualname: str, precedence: int, kind:
  Literal["factory","resource"], module: str}`
- `extension.load_failed` — `{module: str, reason: str, traceback: str}`
- `extension.rescan_started` — `{actor: str, snapshot_id: str}`
- `extension.rescan_completed` — `{snapshot_id: str, added: int, removed: int}`

### Events Consumed

- None. The host is a source, not a subscriber.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/extension/
    __init__.py
    host/
        __init__.py
        host.py                # ExtensionHost class + get_extension_host()
        scanner.py             # scan + module load helpers
        registries.py          # typed registry collections
        snapshot.py            # ExtensionHostSnapshot dataclass + digest
        failures.py            # ExtensionLoadFailure + aggregation
        admin_routes.py        # flask-restx namespace for /admin/extensions/*
    protocols/                 # owned by E-factory-protocols
    resources/                 # owned by E-resource-extensions
    manifest/                  # owned by E-extension-manifest
    lifecycle/                 # owned by E-extension-lifecycle
```

## Key Flows

### Flow A — Cold startup

1. `codecraftai-webworks` app factory resolves env vars, constructs
   `ExtensionHost(scan_paths=..., strict=True)`.
2. `bootstrap()` calls `scan_pychestrate_namespaces` which walks `sys.path`
   entries (or the allow-list), producing a sorted module list.
3. For each module: `importlib.import_module(mod)`. If import raises and
   strict, record an `ExtensionLoadFailure` and continue collecting; else
   re-raise.
4. For each imported module: extract `FactoryExtension` subclasses via
   `inspect.getmembers`, defensively filter to classes whose `__module__`
   matches the module being scanned.
5. Extract `ResourceExtension` subclasses keyed by declared base from
   `E-resource-extensions`.
6. Validate no duplicate `(factory_protocol_name, PRECEDENCE)` collisions. If
   any failures were recorded, raise `ConfigurationError` with an aggregated
   multiline message; registries remain empty.
7. Sort the factory chain ascending by `PRECEDENCE`; compute digest; emit
   `extension.loaded` events; return the snapshot.
8. Mark the `extensions` probe `ready` in `0-system-health`.

### Flow B — Lookup by protocol method

1. Consumer imports its protocol class from `E-factory-protocols` and calls
   `host.create_instance_by_order(factory_method=MyProto.create_driver,
   kwargs={...})`.
2. Host resolves the qualified `factory_protocol_name` from the method's
   owning class and the method name.
3. Host walks the sorted chain; for each factory whose
   `factory_protocol_name` matches and which exposes a callable of that name,
   it retains the last match (lowest precedence among equals? — resolved by
   ascending sort: final winner = lowest PRECEDENCE number of all matching
   factories because iteration preserves order and the assignment is
   overwrite-last-wins, matching upstream semantics).
4. Host invokes the winning callable with the provided args/kwargs, captures
   any exception, reclassifies as `ExtensionCallError` with factory qualname
   in context, and re-raises. Normal return is returned to the caller.

### Flow C — Live re-scan

1. Admin POSTs `/admin/extensions/rescan` with `extensions.rescan`
   permission.
2. Host acquires a non-blocking lock (`asyncio.Lock`); if already held,
   returns 409 conflict.
3. Scanner produces a new module list; host diffs against the current
   snapshot's `module_names`.
4. For every newly present module, host performs Flow A steps 3–6 in
   isolation; failures are aggregated but do not mutate the live snapshot.
5. On success, host atomically swaps the snapshot and emits
   `extension.rescan_completed`.
6. On failure, host emits `extension.rescan_failed` and retains the previous
   snapshot.

## Error Handling

- `ConfigurationError` — raised for duplicate-precedence collisions, missing
  `factory_protocol_name`, negative `PRECEDENCE`, strict-mode import errors.
  Constructed with a multiline message built via `os.linesep.join([...])`.
- `SemanticError` — raised by `get_extension_host()` if called before
  `bootstrap()`; never caught.
- `ExtensionCallError` — new exception type; wraps any exception raised while
  invoking an extension-supplied callable, adding module name, PRECEDENCE,
  protocol name, and method name.
- Catch-and-reclassify is the only accepted handling pattern inside the host;
  catch-and-swallow is forbidden.

## Security Considerations

- Scan paths are strictly `sys.path` or the explicit allow-list; the host
  never executes arbitrary file paths.
- The `rescan` admin route requires the `extensions.rescan` permission and is
  audit-logged with actor, timestamp, added/removed lists, and resulting
  snapshot id.
- `E-extension-sandbox` (Phase 8) adds per-extension capability manifests; the
  host exposes the hook points those capabilities key off (every lookup
  passes through `host._authorize(factory_type)` which is a no-op until
  sandbox lands).
- Host never unpickles extension data; module imports are the only code-path
  that executes extension code.

## Observability

- Metrics:
  - `pychestrate_extension_scan_duration_seconds{mode="cold|rescan"}`
  - `pychestrate_extension_factories_loaded_total{protocol="..."}`
  - `pychestrate_extension_resources_loaded_total{base="..."}`
  - `pychestrate_extension_load_failures_total{phase="import|validate|register"}`
  - `pychestrate_extension_lookup_total{protocol="...",mode="by_order|for_each"}`
- Log events (structured): `pychestrate_extension_scan_started`,
  `pychestrate_extension_scan_completed`, `pychestrate_extension_load_failed`,
  `pychestrate_extension_rescan_started`, `pychestrate_extension_rescan_completed`.
- Trace spans: `pychestrate_extension.bootstrap`, `pychestrate_extension.rescan`,
  `pychestrate_extension.lookup`.

## Open Questions

- Should the host support unloading a module via `importlib`
  invalidation when the caller is confident no instances survive? Timeboxed
  to Phase 8 (sandbox lands then); default answer is no.
- Do we need to publish a stable `snapshot_digest` surface over REST for
  cluster-wide drift detection? Timebox to Phase 10, coincident with
  `E-plugin-api`.
