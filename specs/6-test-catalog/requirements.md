# 6-test-catalog — Requirements

## Introduction

The `6-test-catalog` feature is the registry of test suites that Pychestrate
knows how to dispatch. Each catalog entry pairs a **source system**
(testbase project, pytest directory, gtest binary, custom registry) with
owner, tags, required capabilities, and runtime hints. Catalog entries
are the `catalog_entry_id` referenced by `6-test-orchestration` and the
subject addressed by `6-flake-tracking`. The feature ships in **Phase 3**
beside `6-test-orchestration` and `6-live-run-view` and sits between
`6-test-orchestration` (the consumer) and the extension surface
`test_catalog_importer` (the importer factory protocol). The catalog is
a durable store — importers *populate* it but do not replace it — so
flake metrics, ownership, and run history survive across importer re-runs.

## Requirements

### Requirement 1: Registered Catalog Entries

**User Story:** As a test author, I want my test suites visible in
Pychestrate so that they can be triggered, filtered, and reported on with
stable identifiers.

**Acceptance Criteria (EARS):**

1. WHEN an importer calls `catalog.upsert_entry(project_id, source_key, payload)` THEN the system SHALL either insert a new `TestCatalogEntry` or update the existing entry keyed by `(project_id, source_key)` AND SHALL preserve the `catalog_entry_id: UUID` across updates.
2. WHEN an entry is upserted THEN the system SHALL record `owner_principal_id: UUID | None`, `tags: set[str]`, `required_capabilities: list[str]`, `runtime_hint_seconds: int | None`, and `source_system: str` (the importer's name) on the row.
3. IF the `source_key` is longer than 512 bytes or contains a newline THEN the system SHALL raise `SemanticError` before any DB write.
4. WHEN `catalog.remove_entry(project_id, source_key)` is called THEN the system SHALL mark the entry `retired_at: datetime` rather than hard-deleting so run history remains resolvable.
5. WHERE the project has `catalog.public_read` enabled for a role THEN `catalog.list_entries(project_id)` SHALL succeed for that role without write permission.

### Requirement 2: Importer Factory Protocol

**User Story:** As an extension author, I want a factory protocol for
catalog importers, so that I can register suites from our internal test
index without modifying Pychestrate.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers a `TestCatalogImporterProtocol` implementation THEN the system SHALL verify `importer_name`, `discover`, `upsert_from_payload`, `schedule_hint_seconds` classmethods are present AND raise `ConfigurationError` naming any missing one.
2. WHEN `catalog.run_import(project_id, importer_name, aspects)` is called THEN the system SHALL invoke `discover(project_id, config)` and then `upsert_from_payload(...)` for each returned `ImporterEntryPayload` inside a single DB transaction per 500-entry batch.
3. IF a `discover(...)` call raises `ImporterTransientError` THEN the system SHALL honor the `aspects.retry_policy` (default 3 attempts, 500 ms → 10 s backoff) before surfacing the failure.
4. WHERE two importers register the same `importer_name` with the same `PRECEDENCE` THEN the system SHALL raise `ConfigurationError` at load time.

### Requirement 3: Tags, Owners, Search

**User Story:** As a project lead, I want to filter the catalog by tag,
owner, or capability, so that I can find the right suite without scrolling
through thousands of entries.

**Acceptance Criteria (EARS):**

1. WHEN `catalog.list_entries(project_id, tag=None, owner_principal_id=None, capability=None, limit=100, cursor=None)` is called THEN the system SHALL return a `ListPage[TestCatalogEntryView]` filtered by the provided criteria AND ordered by `(name, catalog_entry_id)` ascending.
2. WHEN `tags` are updated via `catalog.set_tags(entry_id, tags)` THEN the system SHALL validate each tag against `2-tagging`'s declared taxonomy AND SHALL raise `SemanticError` listing invalid tags.
3. WHILE an entry is `retired_at != None` the system SHALL omit it from default listings but SHALL include it when `include_retired=True`.
4. WHEN a user searches by free-text `name_prefix` THEN the system SHALL use the `(project_id, name varchar_pattern_ops)` index AND return results in under 100 ms p99 for projects with 100 000 entries.

## Property-Based Test Requirements

### Property 1: Upsert Preserves `catalog_entry_id`

- **Invariant:** For any `(project_id, source_key, payload_v1, payload_v2)` with the same `source_key`, two consecutive `upsert_entry` calls return the same `catalog_entry_id` and the second call overwrites the mutable fields with `payload_v2`.
- **Generator:** `hypothesis.strategies.tuples(uuids(), text(min_size=1, max_size=256, alphabet=ascii_letters + digits + ":/._-"), payloads(), payloads())`.
- **Assertion:** `first.catalog_entry_id == second.catalog_entry_id` and every field on the final row equals the corresponding field in `payload_v2`.
- **Sample size:** 1000 generated cases

### Property 2: Importer Idempotence

- **Invariant:** For any importer `I` and fixed external source state `S`, running `catalog.run_import(project, I)` twice in a row produces identical rows (ignoring `updated_at`): no new rows, no field changes on the second run.
- **Generator:** `hypothesis.strategies.lists(importer_entry_payloads(), min_size=0, max_size=200)` stubbed as the importer's `discover` output.
- **Assertion:** After the second import, the observed diff between DB states is empty except for `updated_at` timestamps.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `catalog.upsert_entry` p99 < 40 ms at 100 000 entries per project. `catalog.list_entries` with filters p99 < 150 ms. `catalog.run_import` throughput >= 2 000 entries/sec on synthetic payloads.
- **NFR-2 (Security):** Catalog writes gated by `catalog.write` on the project; reads gated by `catalog.read` or project membership. Importers invoked through `catalog.run_import` require the caller to hold `catalog.import:<importer_name>`; importers themselves run with a scoped principal derived from the caller for audit.
- **NFR-3 (Observability):** Metrics `pychestrate_test_catalog_entries{project}` (gauge), `pychestrate_test_catalog_upserts_total{project,importer}` (counter), `pychestrate_test_catalog_import_duration_seconds{project,importer}` (histogram), `pychestrate_test_catalog_import_failures_total{project,importer,error_kind}` (counter). Log events `pychestrate.test.catalog.entry_upserted`, `pychestrate.test.catalog.entry_retired`, `pychestrate.test.catalog.import_completed`, `pychestrate.test.catalog.import_failed`. Trace spans `pychestrate.test.catalog.upsert`, `pychestrate.test.catalog.list`, `pychestrate.test.catalog.import`.
- **NFR-4 (Reliability):** An importer that crashes mid-batch SHALL NOT leave partial state — each 500-entry batch is a transaction. Listings SHALL NOT OOM on projects with 1M entries by enforcing `limit <= 500` and using keyset pagination.

## Out of Scope

- Running the tests themselves (see `6-test-orchestration`).
- Flake classification per entry (see `6-flake-tracking`).
- Sharding an entry into many jobs (see `6-matrix-sharding`).
- Bug-linking (see `6-triage-bug-linking`).

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`, `2-projects`, `2-tagging`, `1-rbac`, `1-audit-log`, `E-extension-host`.
- **Depended on by:** `6-test-orchestration`, `6-flake-tracking`, `6-triage-bug-linking`, `7-test-metrics`.
- **Extension points exposed:** `factory: test_catalog_importer` — testbase project importer, pytest discovery importer, gtest-list importer, custom registry importer.
