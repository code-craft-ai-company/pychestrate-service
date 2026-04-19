# 6-compare-runs — Design

## Architecture

`6-compare-runs` builds a diff projection between two completed runs
and dispatches per-artifact viewers through a registered
`ArtifactDiffViewerExtension` chain. It does not modify run data; all
data is loaded lazily from `5-result-ingest-watcher` (per-test
outcomes), `0-object-store` (logs/artifacts), and `6-artifact-browser`
(listings). Reports are cached (durably, TTL 72 h) in a `compare_report`
table keyed by `(base_run_id, candidate_run_id)`; a cache hit avoids
recomputation. Ships in Phase 5 beside the rest of the polish features.

## Data Model

Tables in `0-persistence`:

- `compare_report`:
  - `report_id: UUID` PK
  - `project_id: UUID`
  - `base_run_id: UUID`
  - `candidate_run_id: UUID`
  - `status: CompareStatus` — `{building, ready, stale}`
  - `warnings: list[str]`
  - `per_test_count: int`
  - `per_test_blob_key: str` — object-store key for the serialized `list[TestDiff]`
  - `computed_at: datetime`
  - `expires_at: datetime`
  - unique `(base_run_id, candidate_run_id)`

Value types:

- `TestDiff` — `{test_case_identity_sha256, base_outcome, candidate_outcome, status, log_excerpt: LogExcerptPair | None, artifact_viewer_hint: str | None}`.
- `LogExcerptPair` — `{base: LogExcerpt | "absent", candidate: LogExcerpt | "absent"}`.
- `LogExcerpt` — `{lines: list[str], anchor_byte_offset: int | None, signed_url: str | None}`.
- `CompareReport` — top-level response with pagination cursor over `per_test`.

## Interfaces

### Public API

REST under `8-rest-api-v1`:

- `POST /api/v1/projects/{project_id}/compare` body `{base_run_id, candidate_run_id}` → `CompareReportRef`.
- `GET /api/v1/projects/{project_id}/compare/{report_id}?cursor=&limit=` → paged `CompareReport`.
- `GET /api/v1/projects/{project_id}/compare/{report_id}/artifacts/{path}:diff-viewer` → `DiffViewerChoice`.

WebComponent: `<px-compare-runs report-id="...">` renders the diff.

### Internal API

```python
class CompareRunsService:
    def __init__(
        self,
        repo: CompareReportRepository,
        runs_repo: TestRunRepository,
        object_store: ObjectStore,
        artifact_store: ArtifactStore,
        result_parser: ResultTreeParser,
        diff_viewer_registry: ArtifactDiffViewerRegistry,
        rbac: RbacService,
        bus: MessageBus,
        clock: Clock,
        config: CompareConfig
    ) -> None:
        self._repo = repo
        self._runs_repo = runs_repo
        self._object_store = object_store
        self._artifact_store = artifact_store
        self._result_parser = result_parser
        self._diff_viewer_registry = diff_viewer_registry
        self._rbac = rbac
        self._bus = bus
        self._clock = clock
        self._config = config
        return

    def build(
        self,
        actor_id: UUID,
        project_id: UUID,
        base_run_id: UUID,
        candidate_run_id: UUID,
        aspects: CompareAspects | None = None
    ) -> CompareReportRef:
        """
            Build (or return cached) compare report between two runs.

            :returns: CompareReportRef (id + status).
            :raises: AuthorizationError, SemanticError, RunNotFoundError
        """
        ...

    def fetch_page(
        self,
        actor_id: UUID,
        report_id: UUID,
        cursor: str | None,
        limit: int = 100
    ) -> CompareReportPage:
        """
            Paginated fetch of per-test diffs.

            :returns: CompareReportPage.
            :raises: AuthorizationError, ReportNotFoundError
        """
        ...

    def select_artifact_diff_viewer(
        self,
        actor_id: UUID,
        report_id: UUID,
        path: str
    ) -> DiffViewerChoice:
        """
            Choose a diff viewer for the artifact pair at path.

            :returns: DiffViewerChoice with component_tag, bundle_url,
                      base_url, candidate_url.
            :raises: AuthorizationError, ArtifactNotFoundError
        """
        ...
```

### Extension Surface

Resource extension declared here:

```python
class ArtifactDiffViewerExtension(ResourceExtension):
    """
        Base class for per-kind artifact diff viewer bundles.
    """
    component_tag: str
    bundle_path: str
    declared_classifications: set[str]

    @classmethod
    def matches(
        cls,
        entry_a: EntryRef,
        entry_b: EntryRef
    ) -> bool:
        """
            :returns: True if this viewer handles the pair.
        """
        ...

    @classmethod
    def capabilities(cls) -> DiffViewerCapabilities:
        """
            :returns: supports_binary, supports_streaming, max_size_bytes.
        """
        ...
```

Reference viewers in-tree under
`source/site/automojo/extensions/pychestrate/artifact_diff_viewer/`:

- `PxGenericTwoPaneDiffViewer` — default fallback.
- `PxTextLineDiffViewer` — text/* with classifier `log` or size < 2 MiB.
- `PxImageDiffViewer` — `image/*`.
- `PxFlamegraphDiffViewer` — classifier `flamegraph`.
- `PxPcapDiffViewer` — classifier `pcap`.

### Events Emitted

- `entity.compare.built` — `{report_id, project_id, base_run_id, candidate_run_id, diff_counts: dict[str, int]}`
- `entity.compare.baseline_updated` — `{project_id, base_run_id}` (emitted when a project's "gold baseline" is changed; consumed by `6-triage-bug-linking`).
- `entity.compare.viewer_selected` — `{report_id, path, viewer}`

### Events Consumed

- `entity.run.completed` — opportunistically precompute reports against the project's declared baseline (optional).
- `extension.reloaded` — refresh viewer registry.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/orchestration/test/compare/`:

- `__init__.py`
- `service.py` — `CompareRunsService`.
- `repository.py` — `CompareReportRepository`.
- `diff_engine.py` — pure per-test diff algebra.
- `log_excerpt.py` — log window locator + signed-URL fallback.
- `viewer_protocol.py` — `ArtifactDiffViewerExtension` base.
- `viewer_registry.py` — extension-host accessor.
- `config.py` — `CompareConfig`.
- `errors.py` — `ReportNotFoundError`.
- `rest/v1_routes.py` — REST endpoints.

## Key Flows

### Flow 1 — Build a report

1. `POST /.../compare` → `CompareRunsService.build`.
2. RBAC `run.compare` + same-project check.
3. Both runs resolved; terminal-state assertion; otherwise `SemanticError`.
4. Cache lookup `(base_run_id, candidate_run_id)` — return existing if `status == ready` and not expired.
5. New `compare_report` row persisted with `status = building`.
6. Worker loads per-test outcomes for both runs via `ResultTreeParser`; runs `diff_engine.compute(...)` producing `list[TestDiff]`.
7. List uploaded to `0-object-store` under `per_test_blob_key`; row flipped to `ready`.
8. `entity.compare.built` emitted.

### Flow 2 — Viewer dispatch

1. UI calls `GET /.../compare/{id}/artifacts/{path}:diff-viewer`.
2. Service loads both `EntryRef`s via `6-artifact-browser`.
3. Registry iterated in `PRECEDENCE` order; first `matches(a, b)` returns `True` wins.
4. Signed URLs minted for both artifacts; `DiffViewerChoice` returned.

### Flow 3 — Log excerpt fallback

1. `diff_engine` annotates regressed/fixed tests with a log locator.
2. On `fetch_page`, `log_excerpt.resolve(...)` attempts to fetch up to `max_log_context_lines` around the first diff line.
3. If log size > `max_log_bytes`, returns an anchor byte offset plus a signed URL so the UI can do a range fetch.

## Error Handling

- `SemanticError` for non-terminal runs, cross-project compares, oversized `limit`: bubble.
- `AuthorizationError`: 403.
- `ReportNotFoundError`: 404.
- `RunNotFoundError`: 404.
- Missing-log conditions do not raise — marked `absent` in the diff pair.
- Viewer extension raising non-`ConfigurationError` exceptions is reclassified and the extension quarantined; fallback viewer used.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- `run.compare` gates all endpoints; cross-project requests rejected with 403 and audited.
- Signed URLs inherit `6-artifact-browser`'s clamping rules.
- Report blobs stored in per-project scope; retention bounded by `compare_report_ttl_hours` (default 72); cleanup job purges expired blobs.

## Observability

Metrics:

- `pychestrate_test_compare_build_duration_seconds{project}` — histogram
- `pychestrate_test_compare_diff_count_total{project,status}` — counter
- `pychestrate_test_compare_viewer_dispatch_total{project,viewer}` — counter
- `pychestrate_test_compare_cache_hits_total{project}` — counter
- `pychestrate_test_compare_cache_misses_total{project}` — counter

Log events: `pychestrate.test.compare.built`, `pychestrate.test.compare.viewer_selected`, `pychestrate.test.compare.denied`, `pychestrate.test.compare.log_excerpt_missing`.

Trace spans: `pychestrate.test.compare.build`, `pychestrate.test.compare.log_excerpt`, `pychestrate.test.compare.viewer_select`, `pychestrate.test.compare.fetch_page`.

## Open Questions

- N-way compare (3+ runs) — Phase 5 or defer? Timebox: Phase 5 midpoint.
- Should we maintain a rolling "project baseline" pointer for auto-compare on every run? Timebox: Phase 5 exit (intersects with `6-triage-bug-linking`).
- Report blob serialization format — gzipped JSON or arrow? Timebox: Phase 5 midpoint after measuring sizes.
