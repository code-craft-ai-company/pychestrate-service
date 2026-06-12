# 7-project-dashboards — Tasks

## Milestones

- **M1 — Skeleton:** `dashboard` table, `DashboardService.create` + `get`, `DashboardTileKindExtension` base + registry, one reference tile kind, basic REST.
- **M2 — Core Behavior:** Full CRUD with optimistic concurrency, validation (overlap/kind/config schema), reflow helper, tile-kind listing, remaining reference tile kinds.
- **M3 — Hardening:** Quota enforcement, audit diff, metrics/logs/traces, perf benchmarks, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/ccai/pychestrate/webservice/dashboards/` package per design.md.
- [ ] T1.2 — Add `0-persistence` migration for `dashboard` and `dashboard_audit` with JSONB columns and indices `(project_id)`, `(project_id, name)` unique.
- [ ] T1.3 — Implement `extension_base.py::DashboardTileKindExtension` and `registry.py::TileKindRegistry.build()`.
- [ ] T1.4 — Ship reference tile kind `source/site/ccai/extensions/pychestrate/dashboard_tile_kind/metric_line.py`.
- [ ] T1.5 — Implement `service.py::DashboardService.create_dashboard` + `get_dashboard` wiring through repository.
- [ ] T1.6 — Register REST endpoints `POST /` and `GET /{id}` + `GET /tile-kinds` under `8-rest-api-v1`.
- [ ] T1.7 — Emit `entity.dashboard.saved` on create.

### M2 — Core Behavior

- [ ] T2.1 — Implement `validation.py::validate_definition` (kind resolution, JSON Schema config check, overlap check, bounds check).
- [ ] T2.2 — Implement `update_dashboard` with `If-Match` ETag concurrency; return 412 on mismatch.
- [ ] T2.3 — Implement `replace_tiles` PATCH endpoint (atomic replacement).
- [ ] T2.4 — Implement `delete_dashboard`; emit `entity.dashboard.deleted`; cascade on `entity.project.deleted` subscription.
- [ ] T2.5 — Implement `reflow.py::reflow_tiles` with deterministic column-pack algorithm preserving z-order.
- [ ] T2.6 — Register `POST /{id}/reflow` endpoint.
- [ ] T2.7 — Ship reference tile kinds `metric_stat.py`, `slo_burn.py`, `pipeline_health.py`.
- [ ] T2.8 — Enforce `min_width_columns` in reflow (full-width row when viewport < min).
- [ ] T2.9 — Audit diff persisted in `dashboard_audit` on each write.

### M3 — Hardening

- [ ] T3.1 — Enforce `dashboards_per_project_max` (default 50) with 409 response.
- [ ] T3.2 — Rate-limit `max_dashboard_writes_per_hour_per_actor` (default 300).
- [ ] T3.3 — Emit metrics `pychestrate_dashboard_save_total`, `pychestrate_dashboard_get_duration_seconds`, `pychestrate_dashboard_reflow_duration_seconds`, `pychestrate_dashboard_tile_kinds_registered`, `pychestrate_dashboard_validation_error_total`, `pychestrate_dashboard_concurrency_conflict_total`.
- [ ] T3.4 — Emit OTel spans per design.md Observability.
- [ ] T3.5 — Benchmark NFR-1: dashboard read p99 < 600 ms; save p99 < 800 ms; reflow p99 < 15 ms for 30 tiles.
- [ ] T3.6 — Sphinx docs for REST API, `DashboardService` internal API, `DashboardTileKindExtension` authoring guide.
- [ ] T3.7 — Subscribe to `extension.reloaded` to rebuild the registry in place.
- [ ] T3.8 — Validate `description` length <= 4 KiB.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (reflow preserves z-order), Property 2 (no overlap after save), Property 3 (registry idempotent) at 1000 cases each.
- [ ] TT-3 — Integration test: author a dashboard with all four reference tile kinds; render at widths `[4, 8, 12]`; verify deterministic positions.
- [ ] TT-4 — Extension-point test: test-only `DashboardTileKindExtension` (`kind="test_only_tile"`) registers and appears via `GET /tile-kinds`; a dashboard referencing it saves and loads.
- [ ] TT-5 — Concurrency test: two parallel PATCH calls with the same ETag — one succeeds, the other gets 412.
- [ ] TT-6 — Overlap test: PATCH tiles including overlapping rects returns 400; dashboard unchanged.
- [ ] TT-7 — Quota test: 51st create on a single project returns 409; 50 existing survive intact.
- [ ] TT-8 — Schema test: tile config failing JSON Schema validation returns 400 with failing path in error message.

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
