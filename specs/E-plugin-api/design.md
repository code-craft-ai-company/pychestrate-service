# E-plugin-api — Design

## Architecture

E-plugin-api is a re-export package that curates the external-stable
subset of Layer E. It lives at
`source/site/ccai/pychestrate/plugin/v<N>/__init__.py` and
imports from the internal Layer E modules only those symbols whose
catalog entries carry `stability = "published"`. A companion
stability-review corpus under `docs/extensions/_stability_reviews/`
tracks the review record per published symbol. Deprecation metadata
is attached per symbol via a small `Deprecation` dataclass; import-
time emission of `DeprecationWarning` happens via a lazy-attr
`__getattr__` on the module.

## Data Model

In-repo (no DB):

- `Deprecation` — dataclass:
  - `symbol: str`
  - `deprecated_on: date`
  - `remove_on: date`
  - `replacement: Optional[str]`
  - `rationale: str`
- `StabilityReview` — parsed from YAML:
  - `symbol: str`
  - `reviewed_on: date`
  - `reviewer: str`
  - `notes: str`

## Interfaces

### Public API

Import surface:

- `pychestrate.plugin.v1`
  - `FactoryProtocolBase` (re-export)
  - `ResourceExtension` (re-export)
  - `ExtensionManifest`, `Capability`, `CAPABILITY_VOCABULARY`
  - `subscribes_to`, `HookAspects`
  - published protocol classes (e.g., `ObjectStoreDriverProtocol`,
    `NotificationChannelProtocol`)
  - published resource bases (e.g., `PodMemberKindExtension`,
    `ArtifactRendererExtension`)
  - `testing.service_fixture` (pytest fixture)

- `pychestrate.plugin.testing.FakeService`
  - `install_pack(*, pack_root: Path) -> ExtensionManifest`
  - `list_loaded_factories() -> List[str]`
  - `emit_event(*, topic: str, payload: Any) -> None`
  - `trigger_rescan() -> None`

### Internal API

Code under
`source/site/ccai/pychestrate/plugin/` and
`source/site/ccai/pychestrate/webservice/extension/plugin_api/`.

```python
# plugin/v1/__init__.py
__all__ = (
    "FactoryProtocolBase",
    "ResourceExtension",
    "ExtensionManifest",
    "CAPABILITY_VOCABULARY",
    "subscribes_to",
    "HookAspects",
    "ObjectStoreDriverProtocol",
    # ... populated by gen_plugin_api tool at build time ...
    "testing",
)


def __getattr__(name: str) -> Any:
    """
        Lazy attribute resolver. Emits DeprecationWarning for
        deprecated symbols and AttributeError for unknown symbols.
    """
    ...
```

```python
# extension/plugin_api/curator.py
class PluginApiCurator:
    """
        Generates or audits pychestrate.plugin.v<N>/__init__.py
        contents from the published-stability subset of the Layer E
        catalogs. Drives service CI gate.
    """

    def __init__(self, *, protocol_catalog: "FactoryProtocolCatalog",
                 resource_catalog: "ResourceExtensionCatalog",
                 reviews_dir: Path,
                 deprecations_path: Path) -> None:
        ...

    def compute_export_set(self) -> List[str]:
        ...

    def audit_reviews(self) -> List[str]:
        """
            Returns a list of missing-or-stale review paths.
        """
        ...

    def audit_deprecations(self, *, today: date) -> List[str]:
        """
            Returns overdue deprecation entries.
        """
        ...

    def regenerate_module(self, *, out_path: Path) -> None:
        ...
```

```python
# plugin/testing/__init__.py
@pytest.fixture
def service_fixture() -> Iterator["FakeService"]:
    ...
```

### Extension Surface

None new; re-exports only.

### Events Emitted

- `extension.plugin_api_overdue_deprecation` — `{symbol, remove_on}`
- `extension.plugin_api_stability_review_missing` — `{symbol}`

### Events Consumed

- None.

## Component Breakdown

```
source/site/ccai/pychestrate/plugin/
    __init__.py
    v1/
        __init__.py            # generated + manually curated re-exports
        testing/
            __init__.py
            fake_service.py
            fixtures.py
source/site/ccai/pychestrate/webservice/extension/plugin_api/
    __init__.py
    curator.py                 # PluginApiCurator
    deprecation.py             # Deprecation dataclass
    review_loader.py
docs/extensions/_stability_reviews/
    <symbol>.yaml
docs/extensions/_deprecations/
    v1.yaml
```

## Key Flows

### Flow A — Build-time curation

1. CI runs `pychestrate-admin plugin-api audit`.
2. `PluginApiCurator.audit_reviews` walks the published subset and
   confirms each has a current review file; missing or stale → CI
   failure.
3. `audit_deprecations` checks dates; overdue → warning (or strict
   failure under `--strict-plugin-api`).
4. `regenerate_module` (optional) rewrites `plugin/v1/__init__.py`
   to match the current published set; a mismatch against the
   checked-in file → CI failure (prevents drift).

### Flow B — Runtime import

1. External plugin does `from pychestrate.plugin.v1 import
   ObjectStoreDriverProtocol`.
2. Python resolves via `__getattr__`; if deprecated, emits
   `DeprecationWarning` with replacement.
3. If unknown, raises `AttributeError` with
   `"pychestrate.plugin.v1 has no attribute 'X' — see
   <docs-link>"`.

### Flow C — Fixture use in external CI

1. External test imports `from pychestrate.plugin.v1.testing import
   service_fixture`.
2. Fixture constructs a `FakeService` using in-process host,
   manifest, and lifecycle singletons with sandbox set to
   grant-all for the fixture session.
3. Test calls `fixture.install_pack(pack_root=.)`; fixture parses
   manifest, performs load, returns the parsed manifest.
4. Test asserts the plugin's expected effects; teardown releases
   resources.

## Error Handling

- `ConfigurationError` — missing reviews, overdue deprecations under
  strict mode, generated-vs-checked-in mismatch.
- `AttributeError` — unknown symbol import.
- `DeprecationWarning` — emitted once per symbol per process.
- Multiline messages via `os.linesep.join`.

## Security Considerations

- Only published-stability entries re-export; internal-only symbols
  never reach `pychestrate.plugin.*`.
- `FakeService` fixture grants all capabilities for test isolation
  but is clearly documented as non-production.
- Audit commands gated by `extensions.manage_catalog` when invoked
  via REST (Phase 10 admin CLI also supports local-only).

## Observability

- Metrics:
  - `pychestrate_plugin_api_imports_total{version}`
  - `pychestrate_plugin_api_deprecation_warnings_total{symbol}`
  - `pychestrate_plugin_api_overdue_deprecations_total`
  - `pychestrate_plugin_api_review_missing_total`
- Log events:
  `pychestrate_plugin_api_overdue_deprecation`,
  `pychestrate_plugin_api_stability_review_missing`,
  `pychestrate_plugin_api_audit_completed`.
- Trace span: `pychestrate_plugin_api.import`.

## Open Questions

- Should the plugin API package be published to PyPI independently
  of the service wheel for version-pinning ease? Decision deferred
  to Phase 10 packaging review.
- Should we support symbolic migration shims (v1→v2 forwarders)?
  Yes once v2 exists; defer until needed.
