# 6-test-catalog — Design

## Architecture

`6-test-catalog` is a durable, per-project registry of test suites that
Pychestrate can dispatch. It stores the stable identity of a suite
(`catalog_entry_id`), its human-facing metadata (name, owner, tags,
runtime hints, required capabilities), and the reference back to the
external source system that produced it. Importers — extensions
implementing `TestCatalogImporterProtocol` — populate and refresh the
catalog from pytest collect, gtest list, testbase project discovery, or
site-specific registries. Runs created through `6-test-orchestration` and
stability records tracked by `6-flake-tracking` both key off
`catalog_entry_id`, so entry identity must be preserved across
re-imports. Authoritative source of truth for catalog data is the
`test_catalog_entry` table in `0-persistence`; importers are *mirrors*,
never masters. Ships in Phase 3.

## Data Model

Table `test_catalog_entry`:

- `catalog_entry_id: UUID` — primary key.
- `project_id: UUID` — foreign key to `project`.
- `source_system: str` — importer name that owns the entry.
- `source_key: str` — stable external id; unique with `(project_id, source_system)`.
- `name: str` — human display name.
- `description: str | None`
- `owner_principal_id: UUID | None` — foreign key to `user` or `group`.
- `tags: set[str]` — stored via join table `test_catalog_entry_tag`.
- `required_capabilities: list[str]` — ordered, deduplicated.
- `runtime_hint_seconds: int | None`
- `runner_kind_hint: str | None` — suggested `test_runner_kind` name.
- `canonical_payload_sha256: str` — SHA-256 of a canonical JSON view of importer-owned fields; used to detect no-op imports.
- `created_at: datetime`
- `updated_at: datetime`
- `retired_at: datetime | None`

Indices: unique `(project_id, source_system, source_key)`, `(project_id, name varchar_pattern_ops)`, `(project_id, retired_at)`, GIN index on `tags`.

Join table `test_catalog_entry_tag(catalog_entry_id, tag)` with composite PK.

Value types:

- `ImporterEntryPayload` — dataclass returned by `discover`.
- `TestCatalogEntrySnapshot` — immutable view passed to `6-test-orchestration`.
- `TestCatalogEntryView` — API-shape for listings.

## Interfaces

### Public API

REST under `8-rest-api-v1`:

- `GET /api/v1/projects/{project_id}/test-catalog?tag=&owner=&capability=&name_prefix=&limit=&cursor=` → `ListPage[TestCatalogEntryView]`.
- `GET /api/v1/projects/{project_id}/test-catalog/{entry_id}` → `TestCatalogEntryView`.
- `POST /api/v1/projects/{project_id}/test-catalog/import` — `{importer_name: str, config: dict}` → `ImportRunResult`.
- `PATCH /api/v1/projects/{project_id}/test-catalog/{entry_id}` — body `{tags?, owner_principal_id?, runner_kind_hint?}` → `TestCatalogEntryView`.

### Internal API

```python
class TestCatalog:
    def __init__(
        self,
        repo: TestCatalogRepository,
        tag_taxonomy: TagTaxonomy,
        rbac: RbacService,
        audit: AuditLog,
        bus: MessageBus,
        importer_registry: TestCatalogImporterRegistry,
        clock: Clock
    ) -> None:
        self._repo = repo
        self._tag_taxonomy = tag_taxonomy
        self._rbac = rbac
        self._audit = audit
        self._bus = bus
        self._importer_registry = importer_registry
        self._clock = clock
        return

    def upsert_entry(
        self,
        project_id: UUID,
        source_system: str,
        source_key: str,
        payload: ImporterEntryPayload
    ) -> TestCatalogEntryView:
        """
            Insert or update a catalog entry.

            :param project_id: Owning project.
            :param source_system: Importer name.
            :param source_key: Stable external identifier.
            :param payload: Importer-provided entry fields.

            :returns: The resulting TestCatalogEntryView.
            :raises: SemanticError
        """
        ...

    def remove_entry(
        self,
        project_id: UUID,
        source_system: str,
        source_key: str
    ) -> None:
        """
            Mark an entry retired without hard-deleting history.

            :param project_id: Owning project.
            :param source_system: Importer name.
            :param source_key: Stable external identifier.

            :returns: None.
            :raises: EntryNotFoundError
        """
        ...

    def run_import(
        self,
        project_id: UUID,
        actor_id: UUID,
        importer_name: str,
        config: dict[str, object],
        aspects: ImportAspects | None = None
    ) -> ImportRunResult:
        """
            Execute an importer end-to-end for a project.

            :param project_id: Owning project.
            :param actor_id: Caller issuing the import.
            :param importer_name: Registered importer name.
            :param config: Importer-specific configuration.
            :param aspects: Behavior parameters.

            :returns: ImportRunResult with counts and errors.
            :raises: AuthorizationError, ConfigurationError
        """
        ...

    def list_entries(
        self,
        project_id: UUID,
        filters: CatalogListFilters,
        limit: int = 100,
        cursor: str | None = None
    ) -> ListPage[TestCatalogEntryView]:
        """
            List entries using keyset pagination.

            :param project_id: Owning project.
            :param filters: Declared filter set.
            :param limit: Max entries per page (<= 500).
            :param cursor: Opaque pagination cursor.

            :returns: ListPage of entries.
            :raises: SemanticError
        """
        ...

    def snapshot_for_dispatch(
        self,
        catalog_entry_id: UUID
    ) -> TestCatalogEntrySnapshot:
        """
            Produce an immutable snapshot for 6-test-orchestration.

            :param catalog_entry_id: Entry identifier.

            :returns: TestCatalogEntrySnapshot.
            :raises: EntryNotFoundError
        """
        ...
```

### Extension Surface

Factory protocol declared here:

```python
class TestCatalogImporterProtocol(FactoryProtocolBase):
    """
        Contract for test_catalog_importer implementations.
    """
    factory_protocol_name: str = "test_catalog_importer"

    @classmethod
    def importer_name(cls) -> str:
        """
            Return the stable importer identifier.

            :returns: Name used by run_import calls.
            :raises: None
        """
        ...

    @classmethod
    def discover(
        cls,
        project_id: UUID,
        config: dict[str, object]
    ) -> Iterable[ImporterEntryPayload]:
        """
            Enumerate all entries the importer currently owns.

            :param project_id: Owning project.
            :param config: Importer-specific configuration.

            :returns: Iterable of ImporterEntryPayload (may stream).
            :raises: ImporterTransientError, ConfigurationError
        """
        ...

    @classmethod
    def schedule_hint_seconds(cls) -> int:
        """
            Recommended cadence between automatic re-imports.

            :returns: Integer seconds (e.g., 3600).
            :raises: None
        """
        ...
```

Reference implementations in `source/site/automojo/factories/pychestrate/test_catalog/`:

- `TestbaseProjectImporter` — `PRECEDENCE = 1000`; walks a testbase project layout.
- `PytestCollectImporter` — `PRECEDENCE = 1000`; parses `pytest --collect-only`.
- `GtestListImporter` — `PRECEDENCE = 1000`; parses `--gtest_list_tests`.

### Events Emitted

- `entity.test.catalog.entry_upserted` — `{project_id, catalog_entry_id, source_system, source_key, was_insert}`
- `entity.test.catalog.entry_retired` — `{project_id, catalog_entry_id, source_system, source_key}`
- `entity.test.catalog.import_completed` — `{project_id, importer_name, inserted, updated, retired, duration_seconds}`
- `entity.test.catalog.import_failed` — `{project_id, importer_name, error_kind}`

### Events Consumed

- `entity.project.archived` — retires all entries under the archived project.
- `extension.reloaded` — refreshes the importer registry.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/orchestration/test/catalog/`:

- `__init__.py`
- `catalog.py` — `TestCatalog` class.
- `repository.py` — `TestCatalogRepository`.
- `importer_registry.py` — accessor over the extension host.
- `importer_protocol.py` — `TestCatalogImporterProtocol`.
- `payloads.py` — `ImporterEntryPayload`, `TestCatalogEntrySnapshot`, `TestCatalogEntryView`.
- `aspects.py` — `ImportAspects`.
- `canonicalization.py` — canonical-JSON hashing for no-op detection.
- `errors.py` — `EntryNotFoundError`, `ImporterTransientError`.
- `rest/v1_routes.py` — REST endpoints.

Factories under `source/site/automojo/factories/pychestrate/test_catalog/`.

## Key Flows

### Flow 1 — Importer run

1. `POST /.../test-catalog/import` → `TestCatalog.run_import(...)`.
2. RBAC check `catalog.import:<name>`.
3. Registry resolves importer by name; raises `ConfigurationError` if absent.
4. `discover(...)` streams payloads; each batch of 500 goes through `upsert_entry` in a single transaction.
5. `canonical_payload_sha256` compared against stored digest; unchanged entries update only `updated_at`.
6. Entries not observed during discover are marked `retired_at = now()`.
7. `entity.test.catalog.import_completed` emitted with counts.

### Flow 2 — Dispatch-side snapshot

1. `6-test-orchestration.trigger_run` calls `catalog.snapshot_for_dispatch(entry_id)`.
2. Repository reads the row plus tags (single JOIN); serializes to `TestCatalogEntrySnapshot`.
3. Snapshot stored in the `TestRun.config_snapshot` binding for reproducibility.

### Flow 3 — Listing

1. REST `GET /.../test-catalog?tag=smoke&capability=usb` → `list_entries(...)`.
2. Filters translate into a parametrized SQL query using the composite index.
3. Keyset cursor is `(name, catalog_entry_id)` last-seen; no OFFSET.

## Error Handling

- `EntryNotFoundError`: domain 404.
- `ImporterTransientError`: retried per `ImportAspects.retry_policy`; if exhausted, bubbles as `ImporterTransientError` and 503.
- `ConfigurationError`: importer contract violations or unknown importer name; bubbles.
- `SemanticError`: invalid tags, oversized `source_key`, illegal `limit`; bubbles (never caught).
- Multiline errors via `os.linesep.join([...])` — tag validation lists invalid tags and the taxonomy's expected set.

## Security Considerations

- `catalog.write` and `catalog.read` permissions gate all mutations and queries via `1-rbac`.
- Importer config values are resolved through `2-global-variables`; secret refs dereferenced only inside the importer via scoped `SecretsAccessor`.
- All upserts and retirements append to `1-audit-log`.
- `source_key` sanitized to reject control characters and bytes above 512.

## Observability

Metrics:

- `pychestrate_test_catalog_entries{project}` — gauge
- `pychestrate_test_catalog_upserts_total{project,importer}` — counter
- `pychestrate_test_catalog_import_duration_seconds{project,importer}` — histogram
- `pychestrate_test_catalog_import_failures_total{project,importer,error_kind}` — counter
- `pychestrate_test_catalog_list_duration_seconds{project}` — histogram

Log events: `pychestrate.test.catalog.entry_upserted`, `pychestrate.test.catalog.entry_retired`, `pychestrate.test.catalog.import_completed`, `pychestrate.test.catalog.import_failed`.

Trace spans: `pychestrate.test.catalog.upsert`, `pychestrate.test.catalog.list`, `pychestrate.test.catalog.import`.

## Open Questions

- Do we expose an "owner inference" extension surface (map external owner string → Pychestrate principal) or keep it inside each importer? Timebox: Phase 3 exit.
- Retention policy for `retired_at`: hard-delete after N days, or never? Timebox: Phase 3 exit.
- Canonical JSON spec — RFC 8785 or a narrower in-house form? Timebox: Phase 3 midpoint.
