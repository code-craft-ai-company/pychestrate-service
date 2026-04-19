# E-extension-compat-check — Design

## Architecture

E-extension-compat-check is a thin coordinator that runs two checks at
load time: (1) service-version window against the manifest and (2)
protocol schema version per loaded factory. It is invoked after
`E-extension-manifest` parses and before `E-extension-host` registers
types. Decisions are recorded in `ManifestRegistry` refusals and in
per-factory rejection records. A diagnostic surface (CLI + REST) lets
operators see why a pack was rejected and inspect the installed fleet's
schema-version posture.

## Data Model

In-memory (no SQL):

- `CompatRejection` — dataclass:
  - `ext_name: str`
  - `reason: Literal["service_version_out_of_bounds",
    "schema_version_too_old", "schema_version_unspecified"]`
  - `detail: str`
  - `factory_qualname: Optional[str]`
  - `protocol_name: Optional[str]`
  - `checked_at: datetime`
- `CompatReportRow` — dataclass:
  - `protocol_name: str`
  - `declared_version: int`
  - `worst_impl_version: int`
  - `ext_count_below: int`
  - `ext_count_at: int`
  - `ext_count_ahead: int`

## Interfaces

### Public API

CLI:

- `pychestrate-admin compat check <manifest-path>` — dry-run the
  checks against a given manifest path.
- `pychestrate-admin compat report` — emit the full fleet report.

REST:

- `GET /admin/extensions/{name}/compat` — permission
  `extensions.read`.
- `GET /admin/extensions/compat/report` — permission
  `extensions.read`.

### Internal API

Code under
`source/site/automojo/pychestrate/webservice/extension/compat/`.

```python
# checker.py
class CompatChecker:
    """
        Runs service-version and protocol-schema compatibility checks.
    """

    def __init__(self, *, running_service_version: "Version",
                 catalog: "FactoryProtocolCatalog") -> None:
        ...

    def check_manifest_window(self, *, manifest: "ExtensionManifest") -> Optional[CompatRejection]:
        ...

    def check_factory_schema(self, *, factory_cls: Type["FactoryExtension"],
                             manifest: "ExtensionManifest") -> Optional[CompatRejection]:
        ...

    def check_all_factories(self, *, loaded_factories: List[Type["FactoryExtension"]],
                            manifests_by_ext: Mapping[str, "ExtensionManifest"]) -> List[CompatRejection]:
        ...

    def generate_report(self, *, loaded_factories: List[Type["FactoryExtension"]],
                        manifests_by_ext: Mapping[str, "ExtensionManifest"]) -> List[CompatReportRow]:
        ...


def get_compat_checker() -> CompatChecker:
    ...
```

### Extension Surface

- `FACTORY_PROTOCOL_SCHEMA_VERSION` class attribute on each
  `FactoryProtocolBase` subclass (declared in `E-factory-protocols`).
- `FACTORY_PROTOCOL_SCHEMA_VERSION_IMPLEMENTED` class attribute on
  each `FactoryExtension` subclass (plain attribute; no decorator).

### Events Emitted

- `extension.compat_rejected` —
  `{ext, reason, detail, factory_qualname?}`
- `extension.compat_schema_ahead` —
  `{protocol, catalog_version, factory_version, ext}`
- `extension.compat_report_generated` —
  `{row_count, generated_by}`

### Events Consumed

- `extension.manifest_parsed` — triggers window check.
- `extension.loaded` — triggers per-factory schema check.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/extension/compat/
    __init__.py
    checker.py            # CompatChecker
    rejection.py          # CompatRejection dataclass
    report.py             # CompatReportRow + builder
    cli.py                # pychestrate-admin compat ...
    admin_routes.py       # GET /admin/extensions/{name}/compat,
                          # GET /admin/extensions/compat/report
```

## Key Flows

### Flow A — Load-time window check

1. `E-extension-manifest.parse_manifest` returns a manifest.
2. Before passing it to the host's module-import step, the compat
   checker runs `check_manifest_window`.
3. On failure, records a `CompatRejection` in `ManifestRegistry`,
   emits `extension.compat_rejected`, and aborts further processing
   for that package.

### Flow B — Load-time schema check

1. Host completes module import and yields loaded factory classes.
2. For each factory, checker runs `check_factory_schema`:
   - Below catalog version → rejection + `extension.compat_rejected`
     with reason `schema_version_too_old`; factory is not registered.
   - At catalog version → accept.
   - Above catalog version → accept and emit
     `extension.compat_schema_ahead`.
   - Missing attribute + catalog version ≥ 1 → rejection with reason
     `schema_version_unspecified`.

### Flow C — Report generation

1. Admin runs `pychestrate-admin compat report`.
2. Checker walks `host.list_loaded_factories()`; groups by
   `protocol_name`; computes per-protocol counters.
3. Emits `extension.compat_report_generated` and prints the table.

## Error Handling

- `ConfigurationError` raised only when a hard inconsistency exists
  (e.g., factory claims a protocol not in the catalog) — multiline
  message via `os.linesep.join`.
- Rejections are data, not exceptions (except for the
  `ConfigurationError` the host raises upstream to abort bootstrap).
- No catch-and-swallow anywhere.

## Security Considerations

- Diagnostic endpoints gated by `extensions.read`.
- No ext-supplied data is echoed into logs without escaping.

## Observability

- Metrics:
  - `pychestrate_extension_compat_rejected_total{reason}`
  - `pychestrate_extension_compat_schema_ahead_total{protocol}`
  - `pychestrate_extension_compat_report_duration_seconds`
- Log events: `pychestrate_extension_compat_rejected`,
  `pychestrate_extension_compat_schema_ahead`,
  `pychestrate_extension_compat_report_generated`.
- Trace span: `pychestrate_extension.compat.check`,
  `pychestrate_extension.compat.report`.

## Open Questions

- Should the report include `last_seen_call_at` per factory to help
  plan deprecation windows? Timebox to Phase 10.
- Should schema versions be semver-ish (major.minor) instead of a
  single integer? Decision: integer for simplicity; revisit in Phase
  10.
