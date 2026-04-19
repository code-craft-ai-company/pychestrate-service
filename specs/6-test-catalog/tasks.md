# 6-test-catalog — Tasks

## Milestones

- **M1 — Skeleton:** `test_catalog_entry` schema + repository + REST listing + single in-tree importer (`TestbaseProjectImporter`).
- **M2 — Core Behavior:** `run_import` with batching, canonical-hash no-op detection, retirement sweep, `TestCatalogImporterProtocol`, tags, keyset pagination, audit + events.
- **M3 — Hardening:** `PytestCollectImporter`, `GtestListImporter`, metrics/logs/traces, property tests, extension-point test, perf benchmarks, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create the `source/site/automojo/pychestrate/webservice/orchestration/test/catalog/` package per design.md Component Breakdown.
- [ ] T1.2 — Add `0-persistence` migration for `test_catalog_entry` + `test_catalog_entry_tag` with indices listed in design.md Data Model.
- [ ] T1.3 — Implement `repository.py::TestCatalogRepository` with `upsert`, `retire`, `snapshot`, `list_paginated`.
- [ ] T1.4 — Implement `payloads.py` with `ImporterEntryPayload`, `TestCatalogEntryView`, `TestCatalogEntrySnapshot`, `CatalogListFilters`.
- [ ] T1.5 — Implement `canonicalization.py` producing a stable canonical JSON encoding and SHA-256 digest.
- [ ] T1.6 — Implement `catalog.py::TestCatalog.upsert_entry` and `snapshot_for_dispatch` happy paths.
- [ ] T1.7 — Register `GET /api/v1/projects/{id}/test-catalog` and `GET /api/v1/projects/{id}/test-catalog/{entry_id}`.
- [ ] T1.8 — Implement `TestbaseProjectImporter` at `source/site/automojo/factories/pychestrate/test_catalog/testbase_project.py` with `PRECEDENCE = 1000`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `importer_protocol.py::TestCatalogImporterProtocol` declaring `factory_protocol_name = "test_catalog_importer"`.
- [ ] T2.2 — Implement `importer_registry.py` accessor over the extension host; subscribe to `extension.reloaded`.
- [ ] T2.3 — Implement `run_import` with 500-entry transactional batches, canonical-hash comparison, retirement of unseen entries.
- [ ] T2.4 — Implement tag validation against `2-tagging` taxonomy with multiline-error listing invalid tags.
- [ ] T2.5 — Implement `remove_entry` retirement semantics (soft delete via `retired_at`).
- [ ] T2.6 — Emit `entity.test.catalog.entry_upserted`, `entity.test.catalog.entry_retired`, `entity.test.catalog.import_completed`, `entity.test.catalog.import_failed`.
- [ ] T2.7 — Register `POST /.../test-catalog/import` and `PATCH /.../test-catalog/{entry_id}`.
- [ ] T2.8 — Wire audit log entries for upsert/retire/import through `1-audit-log`.
- [ ] T2.9 — Subscribe to `entity.project.archived` to retire all catalog entries under that project.

### M3 — Hardening

- [ ] T3.1 — Implement `PytestCollectImporter` (parses `pytest --collect-only --quiet`).
- [ ] T3.2 — Implement `GtestListImporter` (parses `--gtest_list_tests`).
- [ ] T3.3 — Benchmark NFR-1: `upsert_entry` p99 < 40 ms at 100 000 entries; `list_entries` with filters p99 < 150 ms; `run_import` >= 2 000 entries/sec. Fail CI on regression.
- [ ] T3.4 — Emit Prometheus metrics and OTel spans per design.md Observability.
- [ ] T3.5 — Enforce `limit <= 500` in listings; reject larger with `SemanticError`.
- [ ] T3.6 — Sphinx docs for the public REST API and `TestCatalog` internal API.
- [ ] T3.7 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.8 — Implement keyset pagination cursor encoding/decoding (opaque base64url).

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (upsert preserves id) and Property 2 (importer idempotence) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 3 scenario — run a testbase importer against a fixture project, trigger a run through `6-test-orchestration` against the resulting entry, verify `snapshot_for_dispatch` yields the exact entry.
- [ ] TT-4 — Extension-point test: in-tree `TestbaseProjectImporter` (`PRECEDENCE = 1000`) plus a test-only `FakeImporter` (`PRECEDENCE = 1`); verify the fake wins lookup and its payloads land in the DB.
- [ ] TT-5 — Retirement test: run import A yielding {X, Y}, then import A yielding {X, Z}; verify Y is retired, Z is inserted, X is unchanged (no `updated_at` change beyond the batch).
- [ ] TT-6 — Cursor pagination test: 10 000 entries paged at 100/page; union of pages equals the full set with no duplicates.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
