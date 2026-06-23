# 9-ui-design-tokens — Design

## Architecture

`9-ui-design-tokens` is a static-CSS dispatcher plus a resource-extension
registry. It owns no entities and no per-tenant state beyond a registered
cascade. At startup it scans `DesignTokenPackExtension` subclasses through
`E-extension-host`, orders them by `PRECEDENCE`, validates each pack's source
against the canonical token manifest, and renders three artifacts per pack: a
canonical multi-line CSS file, an ETag, and a gzipped payload. Requests to
`/ui/design-tokens/active.css` resolve the caller-selected pack through the
cascade and serve from cache. The feature ships with two in-tree default packs
(`pychestrate.default.light`, `pychestrate.default.dark`) and a reference
override (`pychestrate.example-tenant`) used only by tests. Authoritative source
of truth for the token namespace is `token_manifest.py`; pack source files are
only allowed to declare tokens the manifest publishes.

## Data Model

No persistent entities. In-memory registry:

- `TokenPackRecord` — `{pack_id: str, extension: DesignTokenPackExtension, precedence: int, inherits_from: str | None, css_body: str, etag: str, gzipped: bytes, registered_at: datetime}`.
- `PackCascade` — `{selected_pack_id: str, ordered_pack_ids: list[str], composed_css: str, composed_etag: str, composed_gzipped: bytes}`.
- `TokenManifest` — `{namespaces: dict[str, list[TokenDecl]]}` where `TokenDecl = {name: str, group: str, fallback: str, notes: str}`.

Caches:

- `pack_cache: dict[str, TokenPackRecord]` — keyed by `pack_id`.
- `cascade_cache: LruCache[str, PackCascade]` — keyed by selected `pack_id`, rebuilt on `extension.reloaded`.

## Interfaces

### Public API

HTTP under `0-web-app-host` (mounted as static namespace, not versioned under `/api/v1`):

- `GET /ui/design-tokens/active.css?pack=<pack_id>` → canonical multi-line CSS with ETag and `Cache-Control: public, max-age=300`.
- `GET /ui/design-tokens/active.css?pack=<pack_id>&min=1` → minified payload; separate ETag.
- `GET /ui/design-tokens/packs.json` → `{packs: [{pack_id, precedence, inherits_from, label}]}` for `9-admin-ui` listing.
- `GET /ui/design-tokens/manifest.json` → published token manifest for documentation and component authoring.

There is no WebComponent here; components consume the served CSS by linking it in the document shell. A minimal JavaScript helper `pyc-theme.js` is served for toggling `data-pyc-theme="light|dark"` on the document element.

### Internal API

```python
class DesignTokenRegistry:
    def __init__(
        self,
        manifest: TokenManifest,
        extension_host: ExtensionHost,
        clock: Clock,
        config: DesignTokenConfig
    ) -> None:
        self._manifest = manifest
        self._extension_host = extension_host
        self._clock = clock
        self._config = config
        self._pack_cache: dict[str, TokenPackRecord] = {}
        self._cascade_cache: LruCache[str, PackCascade] = LruCache(capacity=config.cascade_cache_size)
        return

    def register_pack(
        self,
        pack: DesignTokenPackExtension
    ) -> TokenPackRecord:
        """
            Register a token pack from a loaded extension class.

            :param pack: The loaded extension class.

            :returns: The registered TokenPackRecord.
            :raises: ConfigurationError
        """
        ...

    def resolve_cascade(
        self,
        selected_pack_id: str
    ) -> PackCascade:
        """
            Resolve and cache the cascade for a selected pack id.

            :param selected_pack_id: Pack id requested by the caller.

            :returns: The composed PackCascade.
            :raises: ConfigurationError
        """
        ...

    def rebuild_all(
        self
    ) -> None:
        """
            Rebuild every registered pack and clear the cascade cache.
        """
        ...


class DesignTokenDispatcher:
    def __init__(
        self,
        registry: DesignTokenRegistry,
        clock: Clock
    ) -> None:
        self._registry = registry
        self._clock = clock
        return

    def serve_active(
        self,
        selected_pack_id: str,
        minified: bool
    ) -> StaticCssResponse:
        """
            Serve the composed cascade CSS for a selected pack.

            :param selected_pack_id: Pack id from query or cookie.
            :param minified: True when the minified variant is requested.

            :returns: StaticCssResponse with bytes, content_type, etag, cache_control.
            :raises: SemanticError
        """
        ...
```

### Extension Surface

```python
class DesignTokenPackExtension(ResourceExtension):
    """
        Base class for a design-token pack.

        Subclasses declare `pack_id`, optional `inherits_from`, a
        `PRECEDENCE`, and `css_source_path` pointing at a multi-line CSS
        file on disk. The host loads the file, validates declarations
        against the canonical manifest, and registers the record.
    """
    pack_id: str
    inherits_from: str | None = None
    label: str
    css_source_path: str

    @classmethod
    def load_css(cls) -> str:
        """
            Read the pack's multi-line CSS body from source.

            :returns: The multi-line CSS body.
            :raises: ConfigurationError
        """
        ...
```

Reference implementations in-tree under `source/site/ccai/extensions/pychestrate/design_tokens/`:

- `PychestrateDefaultLightPack` — `pack_id="pychestrate.default.light"`, `PRECEDENCE=1000`.
- `PychestrateDefaultDarkPack` — `pack_id="pychestrate.default.dark"`, `inherits_from="pychestrate.default.light"`, `PRECEDENCE=900`.
- `PychestrateExampleTenantPack` — test-only, `pack_id="pychestrate.example-tenant"`, `PRECEDENCE=500`.

### Events Emitted

- `entity.ui.design_tokens.pack_registered` — `{pack_id, precedence, inherits_from, registered_at}`
- `entity.ui.design_tokens.cascade_rebuilt` — `{pack_ids, duration_ms}`

### Events Consumed

- `extension.reloaded` — trigger `rebuild_all`.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/webinterface/design_tokens/`:

- `__init__.py`
- `registry.py` — `DesignTokenRegistry`.
- `dispatcher.py` — `DesignTokenDispatcher` and HTTP route binding.
- `manifest.py` — `TokenManifest` loader and canonical namespace.
- `pack_protocol.py` — `DesignTokenPackExtension` base.
- `validator.py` — multi-line CSS enforcement and token-name enforcement.
- `cascade.py` — pack cascade composition.
- `config.py` — defaults.
- `errors.py` — `DesignTokenConfigurationError`.

Default pack source under `source/site/ccai/pychestrate/webservice/webinterface/components/design_tokens/styles/`:

- `pychestrate.default.light.css`
- `pychestrate.default.dark.css`

Document-shell helper at `source/site/ccai/pychestrate/webservice/webinterface/components/design_tokens/pyc-theme.js`.

## Key Flows

### Flow 1 — Serve active pack CSS

1. Browser requests `/ui/design-tokens/active.css?pack=pychestrate.default.dark`.
2. `DesignTokenDispatcher.serve_active(...)` calls `registry.resolve_cascade("pychestrate.default.dark")`.
3. Cascade cache hits; dispatcher returns the composed multi-line CSS with ETag.
4. Browser caches per `Cache-Control` and applies tokens through `:root`.

### Flow 2 — Tenant pack load on startup

1. `E-extension-host` scans namespaces and discovers `AcmeTenantPack` (`pack_id="acme.default"`, `PRECEDENCE=200`, `inherits_from="pychestrate.default.light"`).
2. `DesignTokenRegistry.register_pack(...)` loads `css_source_path`, validates against manifest, rejects minified source with `ConfigurationError`, publishes `entity.ui.design_tokens.pack_registered`.
3. Admin UI lists the new pack; operator selects it via cookie; cascade is built and served.

### Flow 3 — Dark-mode toggle without reload

1. `pyc-theme.js` toggles `data-pyc-theme="dark"` on the document element.
2. `pychestrate.default.light.css` declares `:root[data-pyc-theme="dark"] { ... }` overrides inline in the same pack.
3. Components re-resolve tokens through `var(--pyc-color-surface)` on the next style recomputation.

## Error Handling

- `ConfigurationError` — duplicate `pack_id`, unknown token in pack source, minified pack source, missing `inherits_from` parent, or `css_source_path` not readable. Multi-line messages built via `os.linesep.join([...])`.
- `SemanticError` — a request targets a `pack_id` that is not registered; bubbles (the API contract is that the caller controls `pack_id`).
- Extension-level failures during `on_load` are quarantined by the host; the dispatcher continues serving previously-registered packs.

## Security Considerations

- No authentication on `/ui/design-tokens/*`; these are public static assets. Per-tenant pack selection is cookie-driven (`pyc_token_pack`) and can only pick among registered `pack_id` values; unknown values fall back to `pychestrate.default.light`.
- `@import` rules in packs are scanned and rejected unless they target registered local packs by id. Remote `@import` raises `ConfigurationError`.
- ETag and `Cache-Control` are set so a rotated pack is picked up within 300 s or immediately via ETag revalidation.
- Manifest JSON is public; it contains only token names and grouping, never secrets.

## Observability

Metrics:

- `pychestrate_ui_design_tokens_pack_served_total{pack_id, minified}` — counter
- `pychestrate_ui_design_tokens_cascade_rebuild_duration_seconds` — histogram
- `pychestrate_ui_design_tokens_pack_missing_total{pack_id}` — counter
- `pychestrate_ui_design_tokens_registered_total{pack_id}` — counter

Log events: `pychestrate.ui.design_tokens.pack_registered`, `pychestrate.ui.design_tokens.pack_served`, `pychestrate.ui.design_tokens.pack_missing`, `pychestrate.ui.design_tokens.cascade_rebuilt`.

Trace spans: `pychestrate.ui.design_tokens.serve`, `pychestrate.ui.design_tokens.rebuild`, `pychestrate.ui.design_tokens.register_pack`.

## Open Questions

- Should the manifest ship semantic color aliases (`--pyc-color-danger`, `--pyc-color-success`) in addition to scale tokens? Timebox: Phase 5 midpoint.
- Runtime toggling of a `data-pyc-density="compact|comfortable"` axis in addition to light/dark? Timebox: Phase 5 exit.
- How to safely precompile Sass-like mixins into manifest-authored packs without requiring an external toolchain? Timebox: Phase 10.
