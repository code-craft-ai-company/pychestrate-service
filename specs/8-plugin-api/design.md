# 8-plugin-api — Design

## Architecture

`8-plugin-api` lives under
`source/site/automojo/pychestrate/webservice/plugin_api/`. It is a
thin catalog + policy layer that sits on top of `E-extension-host`.
Its job is *not* to discover or load extensions — the host already
does that — but to (a) publish the supported subset of factory
protocols and resource bases, (b) enforce version-compatibility
policy, (c) emit structured observability around every external
extension load, and (d) refuse to start the service when the
published set and the in-tree reference implementations drift.
The catalog is built by reading class-level annotations on each
protocol / resource base flagged `is_published = True`; the result
is cached for the service process lifetime and served via
`GET /api/v1/plugin-api/_meta/catalog`. This feature ships in
**Phase 10 — Public Surface & Extensibility Completion**.

## Data Model

No persistent state of its own. The feature reads:

- `E-factory-protocols` — every `FactoryProtocolBase` subclass in
  the process.
- `E-resource-extensions` — every `ResourceExtension` base.
- `E-extension-manifest` — per-extension manifest (`name`,
  `version`, `is_external`, `min_service_version`,
  `max_service_version`, `capabilities_required`,
  `targets` = list of protocol/resource names + schema versions).

In-memory dataclasses:

```python
@dataclass(frozen=True)
class PublishedProtocolEntry:
    name: str
    kind: Literal["factory_protocol", "resource_extension"]
    version: str                   # semver
    protocol_schema_version: int
    min_supported_schema_version: int
    status: Literal["supported", "deprecated", "removed-in-next-major"]
    deprecation_date: Optional[datetime]
    sunset_date: Optional[datetime]
    docs_url: str
    reference_implementation_dotted_path: str


@dataclass(frozen=True)
class PluginApiCatalog:
    built_at: datetime
    service_version: str
    entries: list[PublishedProtocolEntry]
```

An in-memory counter keeps track of per-process deprecation events
so `entity.plugin_api.deprecation_hit` is published exactly once
per `(extension_name, protocol_name)`.

## Interfaces

### Public API

- `GET /api/v1/plugin-api/_meta/catalog` — JSON catalog (per
  `PluginApiCatalog`). Requires `system:plugin_api.read`.
- `GET /api/v1/plugin-api/_meta/extensions` — loaded extensions
  with `via_plugin_api` flag and targeted published protocols.
  Requires `system:plugin_api.read`.
- `GET /api/v1/plugin-api/_meta/catalog/{protocol_name}` — detail
  page with the reference implementation path, supported schema
  versions, and links to deprecation notes.

### Internal API

Module
`automojo.pychestrate.webservice.plugin_api.catalog_builder`:

```python
def build_catalog(
        *,
        service_version: str,
        factory_protocols: list[type],
        resource_bases: list[type]
    ) -> PluginApiCatalog:
    """
        Construct the published plugin API catalog from class annotations.

        :raises: ConfigurationError
    """
    ...


def validate_catalog_against_code(
        *,
        catalog: PluginApiCatalog
    ) -> None:
    """
        Assert every catalog entry has a loadable reference
        implementation whose `protocol_schema_version` matches.

        :raises: ConfigurationError
    """
    rtnval = None
    return rtnval
```

Module
`automojo.pychestrate.webservice.plugin_api.load_policy`:

```python
def evaluate_extension_load(
        *,
        extension_manifest: ExtensionManifest,
        service_version: str,
        catalog: PluginApiCatalog,
        sandbox_policy: SandboxPolicy,
        strict_mode: bool
    ) -> LoadEvaluation:
    """
        Decide whether an extension may load.

        :returns: `LoadEvaluation(allowed, refused_reasons, deprecation_hits)`.
    """
    ...
```

Module
`automojo.pychestrate.webservice.plugin_api.deprecation_reporter`:

```python
def report_deprecation_hit(
        *,
        extension_name: str,
        protocol_name: str,
        sunset_date: Optional[datetime]
    ) -> None:
    """
        Publish `entity.plugin_api.deprecation_hit` exactly once
        per (extension_name, protocol_name) per process.
    """
    rtnval = None
    return rtnval
```

Module
`automojo.pychestrate.webservice.plugin_api.promotion_check`:

```python
def assert_promotion_criteria_met(
        *,
        protocol_name: str,
        stability_criteria: dict
    ) -> None:
    """
        Used at release time to gate adding a new published
        protocol: checks RFC age, reference impl presence, and
        compat test coverage.

        :raises: ConfigurationError
    """
    rtnval = None
    return rtnval
```

### Extension Surface

None. This feature does not introduce a new factory protocol or
resource base. Its entire purpose is to catalog and gate the
*existing* published surface. Each already-declared protocol /
resource base gets a class-level annotation marker:

```python
class AuthProviderProtocol(FactoryProtocolBase):
    factory_protocol_name: str = "auth_provider"
    protocol_schema_version: int = 1
    is_published: bool = True
    published_min_schema_version: int = 1
    published_status: str = "supported"
    published_deprecation_date: Optional[datetime] = None
    published_sunset_date: Optional[datetime] = None
    published_docs_url: str = "/docs/plugin-api/auth_provider"
    published_reference: str = \
        "automojo.pychestrate.webservice.security.auth." \
        "factories.oidc_provider.OidcAuthProvider"
```

Protocols lacking `is_published = True` remain internal-only.

### Events Emitted

- `entity.plugin_api.catalog_built` —
  `{built_at, service_version, entry_count}`.
- `entity.plugin_api.extension_loaded` —
  `{extension_name, extension_version, via_plugin_api,
  targeted_protocols, loaded_at}`.
- `entity.plugin_api.extension_refused` —
  `{extension_name, reasons, refused_at}`.
- `entity.plugin_api.deprecation_hit` —
  `{extension_name, protocol_name, sunset_date, observed_at}`.
- `entity.plugin_api.schema_bumped` —
  `{protocol_name, old_version, new_version, bumped_at}`.

### Events Consumed

- `entity.extension.discovered` — trigger load evaluation per
  `load_policy.evaluate_extension_load`.
- `entity.extension.unloaded` — clear the once-per-process
  deprecation de-duplication set for that extension.
- `entity.service.shutting_down` — emit a final catalog state
  summary to logs.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/plugin_api/
    __init__.py
    catalog_builder.py             # build_catalog, validate_catalog_against_code
    load_policy.py                 # evaluate_extension_load
    deprecation_reporter.py        # report_deprecation_hit
    promotion_check.py             # release-time gating
    annotations.py                 # helpers for class-level markers
    restapi/
        v1/
            catalog_controller.py
            extensions_controller.py
    models.py                      # PublishedProtocolEntry, PluginApiCatalog
    exceptions.py
```

## Key Flows

**Service Startup — Catalog Assembly:**

1. `E-extension-host` finishes its scan and exposes the in-process
   registries of factory protocols and resource bases.
2. `catalog_builder.build_catalog` walks them, picking those with
   `is_published = True`, and emits `PluginApiCatalog`.
3. `catalog_builder.validate_catalog_against_code` asserts every
   published protocol has a loadable reference implementation;
   failure raises `ConfigurationError` and the service refuses
   to start.
4. Catalog is cached; `entity.plugin_api.catalog_built` publishes.

**External Extension Load:**

1. `E-extension-host` discovers a
   `pychestrate-ext-<name>` package.
2. The host calls
   `load_policy.evaluate_extension_load` with the manifest, the
   service version, the catalog, and the sandbox policy.
3. Evaluation:
   - Rejects if `service_version` outside
     `[min_service_version, max_service_version]`.
   - Rejects if any targeted protocol is internal-only and the
     manifest declares `is_external = True`.
   - Rejects if any targeted protocol's schema version is below
     `min_supported_schema_version` (or strict mode is on and
     the version is deprecated).
   - Rejects if `capabilities_required` exceed sandbox clamps.
4. For allowed loads, if any targeted protocol is `deprecated`,
   `deprecation_reporter.report_deprecation_hit` fires once per
   `(extension_name, protocol_name)`.
5. `entity.plugin_api.extension_loaded` or
   `entity.plugin_api.extension_refused` publishes.

**Catalog Endpoint:**

1. Caller hits `GET /api/v1/plugin-api/_meta/catalog` with
   `system:plugin_api.read`.
2. Controller serializes the cached `PluginApiCatalog`.
3. `plugin_api.catalog.served` logs; counter
   `pychestrate_plugin_api_catalog_requests_total` increments.

**Deprecation Bump (Release Time, In-Tree):**

1. Engineer edits a published protocol's annotation to set
   `published_status = "deprecated"`, `published_deprecation_date`,
   and `published_sunset_date` (at least 18 months out).
2. A CI check (part of
   `promotion_check.assert_promotion_criteria_met`, inverse form)
   ensures the sunset date respects the minimum window.
3. On the next release, extensions targeting the now-deprecated
   protocol emit one `deprecation_hit` per process lifetime.

## Error Handling

- `ConfigurationError` — raised on every catalog-code drift:
  missing reference, mismatched schema version, catalog empty,
  un-catalogued "published" class, sunset date too close.
  Always a hard startup failure.
- `ExtensionRefusedError` — parent type carrying
  `reasons: list[str]`. Reasons enumerated:
  `service_version_out_of_range`, `internal_protocol_targeted`,
  `schema_version_unsupported`, `capability_exceeds_sandbox`,
  `manifest_invalid`. Extensions failing load surface this
  reclassified into the host's error stream; service continues.
- `SemanticError` — raised on internal misuse (e.g., reporting a
  deprecation hit for a protocol that does not exist); never
  caught.
- Multiline error messages assembled with
  `os.linesep.join([...])` listing the protocol name, extension
  name, and the precise reason per line.

## Security Considerations

- Catalog endpoint requires `system:plugin_api.read`; no write
  endpoints.
- Extension manifests are validated against a JSON Schema;
  `unknownProperties` must be namespaced `x-<vendor>-`
  otherwise rejected.
- Capability clamps: requested capabilities are intersected with
  the sandbox policy before enforcement; a manifest requesting
  `process:subprocess` when the policy forbids it is refused at
  load time.
- The catalog exposes only public metadata; internal protocol
  names and internal reference dotted paths are never surfaced.
- Audit log records every refused load (`extension_name`,
  `reasons[]`) so operators can triage third-party package drift.
- `strict_mode` is an operator lever, not an extension opt-in.

## Observability

Metrics:

- `pychestrate_plugin_api_extensions_loaded_total{source,status}`
- `pychestrate_plugin_api_deprecation_hits_total{protocol}`
- `pychestrate_plugin_api_schema_bumps_total{protocol}`
- `pychestrate_plugin_api_refused_loads_total{reason}`
- `pychestrate_plugin_api_catalog_requests_total`
- `pychestrate_plugin_api_catalog_entries` (gauge)

Log events: `plugin_api.extension.loaded`,
`plugin_api.extension.refused`, `plugin_api.deprecation.hit`,
`plugin_api.schema.bumped`, `plugin_api.catalog.built`,
`plugin_api.catalog.served`.

Trace spans: `plugin_api.load`, `plugin_api.validate`,
`plugin_api.catalog.build`, `plugin_api.catalog.serve`.

## Open Questions

- Do we cut a separate semver per protocol, or keep a single
  monotonic `protocol_schema_version: int`? Proposed: keep int
  for simplicity; expose the service `version` alongside for
  context.
- Should the catalog include *internal* protocols marked
  `x-internal` for diagnostic purposes? Leaning no — internal
  protocols should remain invisible externally to avoid
  accidental adoption.
- How do we handle a critical-security-revocation of a
  published protocol mid-deprecation-window? Fast-path revoke
  with an operator override, documented. Close during Phase 10
  GA review.
