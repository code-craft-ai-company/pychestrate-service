# 6-artifact-browser — Requirements

## Introduction

The `6-artifact-browser` feature is the in-UI file walker for the
testbase-shaped `artifacts/<label>/...` subtree plus neighbors
(`taskings/`, `tc-by-products/`, `diagnostics/`) attached to every run.
It lists directory contents, previews individual files through
registered `ArtifactRendererExtension` WebComponents (image, audio, log,
packet capture, flamegraph, and custom), and issues signed-URL downloads
via `5-artifact-store` and `0-object-store`. Ships in **Phase 5** with
the first-WebComponents slice (`9-ui-design-tokens`, `9-wc-log-stream`,
`9-wc-result-viewer`, `9-run-detail-ui`). Sits between
`5-result-ingest-watcher` (which classifies tree contents) and the UI
(which renders them). Authoritative source of truth for bytes is
`0-object-store`; this feature owns the directory projection + render
dispatch, not the bytes themselves.

## Requirements

### Requirement 1: Typed Directory Listing For A Run's Result Tree

**User Story:** As a user opening a completed run, I want to browse its
`artifacts/` subtree like a filesystem with types attached to each leaf,
so that I can navigate to the thing I need.

**Acceptance Criteria (EARS):**

1. WHEN `artifacts.list(run_id, path, limit, cursor)` is called AND the caller has `run.artifacts.view` THEN the system SHALL return a `DirectoryListing` with `entries: list[EntryRef]` where each entry has `{name: str, kind: "file" | "dir", size_bytes: int | None, content_type: str | None, classifier_tag: str | None}`.
2. IF `path` is missing or escapes the run's result root (contains `..` segments after normalization) THEN the system SHALL raise `SemanticError` before touching the object store.
3. WHILE a run is not yet in a terminal state THEN the system SHALL still list any artifacts already streamed into the result root AND SHALL NOT block waiting for completion.
4. WHERE `5-result-ingest-watcher` has classified an entry via `ArtifactClassifierExtension` THEN `classifier_tag` SHALL carry the classifier's assigned category (e.g., `core_dump`, `pcap`, `flamegraph`, `log`).
5. WHEN listing returns THEN entries SHALL be ordered directories-first then files, each sorted lexicographically.

### Requirement 2: Renderer Dispatch By Content Type

**User Story:** As a user clicking an artifact, I want the browser to
show me the right viewer (image preview, PCAP table, flamegraph SVG,
log stream), so that I do not have to download and open locally.

**Acceptance Criteria (EARS):**

1. WHEN `artifacts.select_renderer(entry)` is called THEN the system SHALL consult the registered `ArtifactRendererExtension` chain in `PRECEDENCE` order AND return the first renderer whose `matches(entry)` returns True.
2. IF no renderer matches THEN the system SHALL return the default `GenericDownloadRenderer` whose WebComponent is `<px-artifact-generic-download>`.
3. WHERE an extension's renderer declares `requires_streaming: True` THEN the system SHALL issue the renderer a streaming URL bound to `5-artifact-store` rather than a one-shot signed URL.
4. WHEN a renderer is returned THEN the response SHALL include `{component_tag: str, bundle_url: str, content_url: str, ttl_seconds: int}`.

### Requirement 3: Signed-URL Downloads Scoped To The Caller

**User Story:** As a user, I want to download an artifact with a URL my
browser can hit directly, so that the byte stream does not proxy through
the Pychestrate app tier.

**Acceptance Criteria (EARS):**

1. WHEN `artifacts.sign_download(run_id, path, expires_seconds)` is called AND the caller has `run.artifacts.download` THEN the system SHALL return a signed URL with effective TTL `min(expires_seconds, max_presign_expires_seconds)` (default 900 s).
2. IF the driver does not support presigning (capability `presign_get == False`) THEN the system SHALL fall back to a proxied streaming endpoint `/api/v1/runs/{run_id}/artifacts/{path}:proxy` bound to the same RBAC.
3. WHEN a sign call succeeds THEN the system SHALL append a `1-audit-log` entry `{actor_id, run_id, path, size_bytes, expires_at}`.

## Property-Based Test Requirements

### Property 1: Path Normalization Never Escapes The Run Root

- **Invariant:** For any user-supplied path string `p`, the resolved backend key is always a descendant of `<result_root_key>/` — no path can traverse out via `..`, symlinks, URL encoding, or mixed separators.
- **Generator:** `hypothesis.strategies.text(alphabet=ascii_letters + digits + "/._- %", min_size=0, max_size=512)` plus a bag of adversarial suffixes `["../", "%2e%2e/", "..\\", ".\u002e/"]` randomly interleaved.
- **Assertion:** Either resolution succeeds with a key that starts with `<result_root_key>/`, or `SemanticError` is raised. No other outcome.
- **Sample size:** 1000 generated cases

### Property 2: Listing Is A Stable Lexicographic Projection

- **Invariant:** For any directory under a run root, two consecutive `list(run_id, path)` calls return identical `entries` order (assuming no concurrent writes).
- **Generator:** `hypothesis.strategies.sets(text(alphabet=ascii_letters + digits + "._-", min_size=1, max_size=32), min_size=0, max_size=200)` as the contents written to a synthetic backend.
- **Assertion:** `list1.entries == list2.entries` and entries are ordered dirs-first then files, each lex-sorted.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `artifacts.list` p99 < 150 ms for directories up to 10 000 entries. `artifacts.sign_download` p99 < 50 ms. Renderer dispatch p99 < 20 ms. Proxied streaming sustains >= 20 MiB/s per connection.
- **NFR-2 (Security):** Views behind `run.artifacts.view`; downloads behind `run.artifacts.download`. All paths normalized against `5-shared-results-backend`'s root; bytes scoped to the caller's project. Presigned URLs capped at `max_presign_expires_seconds` (default 900 s). Renderer bundles served only from registered extension namespaces; no arbitrary URL reflection.
- **NFR-3 (Observability):** Metrics `pychestrate_test_artifact_list_duration_seconds{project}` (histogram), `pychestrate_test_artifact_sign_total{project}` (counter), `pychestrate_test_artifact_renderer_dispatch_total{project,renderer}` (counter), `pychestrate_test_artifact_proxy_bytes_total{project}` (counter). Log events `pychestrate.test.artifact.listed`, `pychestrate.test.artifact.signed`, `pychestrate.test.artifact.renderer_selected`, `pychestrate.test.artifact.denied`. Trace spans `pychestrate.test.artifact.list`, `pychestrate.test.artifact.sign`, `pychestrate.test.artifact.renderer_select`.
- **NFR-4 (Reliability):** A renderer-registry reload SHALL NOT interrupt an in-flight listing call. The object-store driver being unavailable SHALL surface a 503 and the run detail UI SHALL degrade to the generic-download renderer.

## Out of Scope

- Writing artifacts (handled by pod clients and `5-result-ingest-watcher`).
- Artifact typing and classification (see `5-result-ingest-watcher` and `ArtifactClassifierExtension`).
- Artifact promotion (see `5-artifact-store`).
- Cross-run artifact diff (see `6-compare-runs`).

## Dependencies

- **Depends on:** `5-shared-results-backend`, `5-artifact-store`, `5-result-ingest-watcher`, `0-object-store`, `1-rbac`, `1-audit-log`, `9-ui-design-tokens`, `E-extension-host`.
- **Depended on by:** `9-run-detail-ui`, `6-compare-runs`.
- **Extension points exposed:** `resource: ArtifactRendererExtension` — image, audio, log-stream, PCAP, flamegraph, markdown, custom site renderers.
