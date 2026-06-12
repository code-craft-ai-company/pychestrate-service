# 6-artifact-browser — Design

## Architecture

`6-artifact-browser` is the navigation + render-dispatch layer over the
per-run result tree. It holds no bytes and mirrors no directory state:
it queries `0-object-store` lazily via `5-artifact-store` and layers on
classification metadata from `5-result-ingest-watcher`. Rendering is
delegated to `ArtifactRendererExtension` WebComponents discovered
through `E-extension-host` — the service selects the right renderer but
does not render itself. Signed download URLs come from the active
`object_store_driver`; when the driver cannot presign, a proxied
streaming endpoint takes over. The feature lives in Phase 5 and is
composed inside `9-run-detail-ui`.

## Data Model

No persistent entities owned here. Per-call values:

- `EntryRef` — `{name, kind, size_bytes, content_type, classifier_tag, etag}`.
- `DirectoryListing` — `{path, entries, continuation}`.
- `RendererChoice` — `{component_tag, bundle_url, content_url, ttl_seconds}`.
- `SignedDownload` — `{url, expires_at, size_bytes, etag}`.

In-memory caches:

- `renderer_registry_cache: list[RendererRecord]` — rebuilt on `extension.reloaded`.
- `classifier_tag_cache: LruCache[(run_id, path), str]` — 60 s TTL; populated from `5-result-ingest-watcher`.

## Interfaces

### Public API

REST under `8-rest-api-v1`:

- `GET /api/v1/runs/{run_id}/artifacts?path=&limit=&cursor=` → `DirectoryListing`.
- `POST /api/v1/runs/{run_id}/artifacts/sign` body `{path, expires_seconds}` → `SignedDownload`.
- `GET /api/v1/runs/{run_id}/artifacts/{path}:proxy` — streamed bytes (fallback).
- `GET /api/v1/runs/{run_id}/artifacts/{path}:renderer` → `RendererChoice`.

WebComponent: `<px-artifact-browser run-id="...">` is a WebComponent that
reads `DirectoryListing`, rides dispatches, and mounts the chosen
renderer.

### Internal API

```python
class ArtifactBrowser:
    def __init__(
        self,
        store: ObjectStore,
        artifact_store: ArtifactStore,
        classifier_query: ClassifierQuery,
        renderer_registry: ArtifactRendererRegistry,
        rbac: RbacService,
        audit: AuditLog,
        clock: Clock,
        config: ArtifactBrowserConfig
    ) -> None:
        self._store = store
        self._artifact_store = artifact_store
        self._classifier_query = classifier_query
        self._renderer_registry = renderer_registry
        self._rbac = rbac
        self._audit = audit
        self._clock = clock
        self._config = config
        return

    def list(
        self,
        actor_id: UUID,
        run_id: UUID,
        path: str,
        limit: int = 200,
        cursor: str | None = None
    ) -> DirectoryListing:
        """
            List a directory inside a run's result tree.

            :param actor_id: Authenticated caller.
            :param run_id: Owning run.
            :param path: Directory path relative to the result root.
            :param limit: Entries per page (<= 1000).
            :param cursor: Opaque continuation cursor.

            :returns: DirectoryListing.
            :raises: AuthorizationError, SemanticError, RunNotFoundError
        """
        ...

    def sign_download(
        self,
        actor_id: UUID,
        run_id: UUID,
        path: str,
        expires_seconds: int
    ) -> SignedDownload:
        """
            Produce a signed URL or a proxy URL for a single artifact.

            :param actor_id: Authenticated caller.
            :param run_id: Owning run.
            :param path: File path relative to the result root.
            :param expires_seconds: Requested TTL, clamped to config max.

            :returns: SignedDownload.
            :raises: AuthorizationError, ArtifactNotFoundError,
                     UnsupportedOperationError
        """
        ...

    def select_renderer(
        self,
        actor_id: UUID,
        run_id: UUID,
        path: str
    ) -> RendererChoice:
        """
            Choose the best-matching renderer for an artifact.

            :param actor_id: Authenticated caller.
            :param run_id: Owning run.
            :param path: File path relative to the result root.

            :returns: RendererChoice with component tag and content URL.
            :raises: AuthorizationError, ArtifactNotFoundError
        """
        ...

    def open_proxy_stream(
        self,
        actor_id: UUID,
        run_id: UUID,
        path: str
    ) -> Iterable[bytes]:
        """
            Yield bytes from the object store for fallback proxying.

            :param actor_id: Authenticated caller.
            :param run_id: Owning run.
            :param path: File path relative to the result root.

            :returns: Iterable of bytes chunks.
            :raises: AuthorizationError, ArtifactNotFoundError
        """
        ...
```

### Extension Surface

Resource extension declared here:

```python
class ArtifactRendererExtension(ResourceExtension):
    """
        Base class for per-kind artifact renderer bundles.

        Subclasses set `component_tag: str`, `bundle_path: str`, and
        implement `matches(entry: EntryRef) -> bool` plus
        `capabilities() -> RendererCapabilities`.
    """
    component_tag: str
    bundle_path: str
    requires_streaming: bool = False

    @classmethod
    def matches(cls, entry: EntryRef) -> bool:
        """
            Decide whether this renderer handles the entry.

            :returns: True if this renderer should be preferred.
        """
        ...

    @classmethod
    def capabilities(cls) -> RendererCapabilities:
        """
            :returns: RendererCapabilities (supports_lazy_load, requires_streaming, max_size_bytes).
        """
        ...
```

Reference renderers in-tree under
`source/site/ccai/extensions/pychestrate/artifact_renderer/`:

- `PxLogStreamRenderer` — log files (`classifier_tag == "log"` or `content_type startswith "text/"`).
- `PxImageRenderer` — `image/*`.
- `PxAudioRenderer` — `audio/*`.
- `PxPcapRenderer` — classifier_tag `pcap`.
- `PxFlamegraphRenderer` — classifier_tag `flamegraph`.
- `PxMarkdownRenderer` — `.md` files.
- `GenericDownloadRenderer` — default fallback.

WebComponent bundles are served under `/ext/<ext-name>/bundle/<path>` by `9-ui-design-tokens` static dispatcher.

### Events Emitted

- `entity.test.artifact.accessed` — `{actor_id, run_id, path, access_kind: "list"|"sign"|"proxy"|"renderer"}`

### Events Consumed

- `extension.reloaded` — rebuild `renderer_registry_cache`.
- `entity.run.completed` / `entity.run.failed` — warm the classifier cache for likely-opened runs.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/orchestration/test/artifact_browser/`:

- `__init__.py`
- `browser.py` — `ArtifactBrowser` class.
- `path_safety.py` — normalization and escape detection.
- `renderer_registry.py` — accessor over the extension host.
- `renderer_protocol.py` — `ArtifactRendererExtension` base.
- `proxy.py` — streaming proxy implementation.
- `config.py` — defaults.
- `errors.py` — `ArtifactNotFoundError`.
- `rest/v1_routes.py` — REST endpoints.

Renderer bundles under `source/site/ccai/extensions/pychestrate/artifact_renderer/`.

## Key Flows

### Flow 1 — List a run's artifacts

1. Browser calls `GET /api/v1/runs/{id}/artifacts?path=artifacts/smoke_2024/`.
2. `ArtifactBrowser.list(...)` checks RBAC `run.artifacts.view`.
3. `path_safety.normalize(path, run.result_root_key)` yields the backend prefix or raises `SemanticError`.
4. `ObjectStore.list(prefix, limit, cursor)` returns the page.
5. For each entry, classifier tag resolved via `ClassifierQuery.get((run_id, path))`.
6. Entries sorted: directories first (by name), then files (by name).
7. `DirectoryListing` returned.

### Flow 2 — Open an artifact viewer

1. User clicks an artifact; UI calls `GET /.../artifacts/{path}:renderer`.
2. `ArtifactBrowser.select_renderer(...)` iterates `renderer_registry_cache` in `PRECEDENCE` order; first `matches(entry)` wins.
3. `content_url` is either a signed URL (if driver supports it) or the `:proxy` endpoint.
4. Response includes `component_tag`, `bundle_url` (extension-scoped), `content_url`, `ttl_seconds`.

### Flow 3 — Presigned download with fallback

1. User clicks Download; UI POSTs `/.../artifacts/sign`.
2. Browser tries `ObjectStore.presign_get(key, min(requested, max_presign_expires_seconds))`.
3. On `UnsupportedOperationError` the browser returns a `:proxy` URL with the same TTL semantics.
4. Audit entry written.

## Error Handling

- `SemanticError` for path escape, invalid `limit`, oversized `path`: bubble.
- `AuthorizationError`: 403 per RBAC rules.
- `ArtifactNotFoundError`: 404.
- `UnsupportedOperationError` from driver: caught once at the `sign_download` boundary and translated into the proxy fallback; the user never sees it.
- Renderer protocol breakage (extension returns non-boolean from `matches`): reclassified as `ConfigurationError`, extension is quarantined by the host, generic download used.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- `run.artifacts.view` gates listing and renderer dispatch; `run.artifacts.download` gates signing and proxy.
- `path` normalization uses `os.path.normpath` plus an explicit descendant-of-root check on the joined key.
- Renderer bundle URLs namespaced by extension name; a renderer cannot redirect the browser to arbitrary origins.
- Presigned URLs capped at 900 s default; configurable ceiling.
- Proxy endpoint enforces Flask `send_file` with `as_attachment=True` and a `Content-Disposition` header to prevent in-browser execution.

## Observability

Metrics:

- `pychestrate_test_artifact_list_duration_seconds{project}` — histogram
- `pychestrate_test_artifact_sign_total{project}` — counter
- `pychestrate_test_artifact_renderer_dispatch_total{project,renderer}` — counter
- `pychestrate_test_artifact_proxy_bytes_total{project}` — counter
- `pychestrate_test_artifact_denied_total{project,reason}` — counter

Log events: `pychestrate.test.artifact.listed`, `pychestrate.test.artifact.signed`, `pychestrate.test.artifact.renderer_selected`, `pychestrate.test.artifact.denied`.

Trace spans: `pychestrate.test.artifact.list`, `pychestrate.test.artifact.sign`, `pychestrate.test.artifact.renderer_select`, `pychestrate.test.artifact.proxy`.

## Open Questions

- Do renderers receive the signed URL or always a content-proxy URL to make extension origins uniform? Timebox: Phase 5 midpoint.
- Directory contents with > 10 000 entries — do we paginate only or also chunk into subtrees? Timebox: Phase 5 exit.
- Renderer capability negotiation with the browser (e.g., WebGL availability for flamegraph). Timebox: Phase 9 when dashboards land.
