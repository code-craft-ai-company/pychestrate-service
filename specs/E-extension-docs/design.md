# E-extension-docs — Design

## Architecture

E-extension-docs is a Sphinx site plus a small in-tree Sphinx
extension that walks the two Layer E catalogs and emits per-entry
pages. The site is built from the service repo, and its output is
published per `10-release-channels`. The Sphinx extension imports only
the declaration modules (not implementation modules) to keep the build
hermetic — it never executes extension code.

## Data Model

No persistent state. Build-time transient:

- `DocProtocolPage` — dataclass:
  - `name: str`
  - `stability: Literal["internal","published"]`
  - `schema_version: int`
  - `required_capabilities: Tuple[str, ...]`
  - `classmethod_signatures: Tuple[str, ...]`
  - `reference_impl_module: Optional[str]`
  - `deprecation: Optional[DeprecationInfo]`
- `DocResourcePage` — dataclass:
  - `base_name: str`
  - `owning_feature_id: str`
  - `attribute_schema: Mapping[str, str]`
  - `allow_indirect_subclasses: bool`
  - `reference_kind_qualname: Optional[str]`

## Interfaces

### Public API

`make -C docs html` builds the site; output served from
`10-release-channels`.

### Internal API

Code under `docs/` (Sphinx root) and
`source/site/automojo/pychestrate/webservice/extension/docs_ext/`
(Sphinx extension).

```python
# docs_ext/__init__.py
def setup(app: "Sphinx") -> Dict[str, Any]:
    """
        Sphinx extension entry point.
    """
    ...


# docs_ext/catalog_walker.py
class CatalogWalker:
    """
        Walks FactoryProtocolCatalog and ResourceExtensionCatalog and
        emits rst pages.
    """

    def __init__(self, *, protocol_catalog: "FactoryProtocolCatalog",
                 resource_catalog: "ResourceExtensionCatalog",
                 out_dir: Path,
                 stability_filter: Optional[str] = None) -> None:
        ...

    def emit_protocol_pages(self) -> List[Path]:
        ...

    def emit_resource_pages(self) -> List[Path]:
        ...

    def emit_compat_table(self) -> Path:
        ...
```

### Extension Surface

None.

### Events Emitted

None (build-time tool).

### Events Consumed

None.

## Component Breakdown

```
docs/
    conf.py
    index.rst
    extensions/
        protocols/  (generated)
        resources/  (generated)
        compat.rst  (generated)
source/site/automojo/pychestrate/webservice/extension/docs_ext/
    __init__.py
    catalog_walker.py
    templates/
        protocol_page.rst.jinja
        resource_page.rst.jinja
```

## Key Flows

### Flow A — Docs build

1. `make -C docs html` runs; `conf.py` loads the
   `pychestrate_extension_docs_ext` extension.
2. The extension constructs `CatalogWalker` using the in-tree
   catalog singletons (loaded by importing the declaration modules
   under `_declarations/`).
3. `emit_protocol_pages` renders each catalog entry into
   `docs/extensions/protocols/<name>.rst` using the Jinja template;
   embeds the reference implementation via `literalinclude`.
4. `emit_resource_pages` and `emit_compat_table` likewise.
5. Sphinx runs `linkcheck` and `build html`; build fails if
   `linkcheck -W` surfaces any broken or orphan pages.

### Flow B — Stability filter

1. `conf.py` reads the build flag `PYCHESTRATE_DOCS_STABILITY`
   (`all` default; `published` filters).
2. Walker skips entries whose stability does not match; templates
   hide internal sidebar groups.

## Error Handling

- `ConfigurationError` — missing reference file referenced from a
  page; broken `:ref:` target; catalog declaration import failure.
- Multiline error messages via `os.linesep.join`.
- Build never writes a partial output directory: walker writes to a
  temp `_build_tmp/`, then renames into place on success.

## Security Considerations

- Build does not execute extension code — only imports declaration
  modules from in-tree `_declarations/`.
- `linkcheck` does not follow arbitrary external links from
  ext-contributed docstrings; only internal + allow-list external.

## Observability

- Metrics (emitted via build-time exporter):
  - `pychestrate_extension_docs_pages_emitted_total{kind}`
  - `pychestrate_extension_docs_broken_links_total`
  - `pychestrate_extension_docs_build_duration_seconds`
- Log events: `pychestrate_extension_docs_build_started`,
  `pychestrate_extension_docs_build_completed`,
  `pychestrate_extension_docs_build_failed`.
- Trace span: `pychestrate_extension.docs.build`.

## Open Questions

- Should extension packs contribute docs that are rebuilt alongside
  the service site? Deferred — pack docs live in pack repos.
- Should the published-only site be a separate artifact? Decision:
  published filter is a build flag; same pipeline produces both.
