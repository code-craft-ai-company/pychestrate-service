# Project Model Bridge — Design

## 1. The two models (confirmed)

**Legacy `Project`** — `source/packages/ccai/pychestrate/core/orm.py:1494`
- Table `projects`; PK `id` mapped to column `proj_id` (`BigInteger`, autoincrement).
- Identity key in practice: `proj_name` (`VARCHAR(128)`, unique) — managers look up by `Project.name`.
- Scope/RBAC: owner via `proj_owner_id` (FK `user.user_id`); membership via `project_members` (`pm_role` strings: owner/administrator/developer/viewer). RBAC enforced by `ProjectManager.check_permission(project_id:int, user_id, permission)`.
- Base: `PychestrateModelBase` (a `declarative_base()` at orm.py:79).
- Every legacy feature manager FKs `projects.proj_id`: members, variables, repositories, build_specs, infra_specs, test_specs, release_pipelines, releases, release_channels, release_templates, watches, calendar/phase/merge/pull events (all confirmed via `__tablename__` + `ForeignKey('projects.proj_id')`).

**New slug `Project`** — `source/site/ccai/pychestrate/webservice/projects/models.py:46`
- Table `projects_projects`; PK `project_id` (`UUIDType`).
- `slug` (`String(63)`, unique), `display_name`, `description`, `state` (enum ACTIVE/ARCHIVED), `owning_group_id` (UUID, nullable), `template_id/version`, `extension_fields` (JSONB), timestamps + `archived_at`.
- Scope/RBAC: membership via `projects_project_member_bindings` (`role_name` strings, FK `projects_projects.project_id` ON DELETE CASCADE); REST gated on `system:projects.*` permission keys via `rbac_evaluator`.
- Base: `PychestratePhase1Base` (a *separate* `declarative_base()` at `persistence/schema.py:25`). Created by migration `006_phase2_projects`.

Correction worth noting: the legacy model's real lookup key is `proj_name`, not the BigInt (the BigInt is an internal surrogate).

## 2. Call-sites audit

**Uses LEGACY (`projects.proj_id`, keyed on int id / `proj_name`):**
- All managers in `core/managers/`: `project_manager.py` (CRUD + members + `check_permission`, keys `Project.id`/`Project.name`), `release_manager.py`, `release_template_manager.py`, `repository_manager.py`, `build_manager.py`, `infrastructure_manager.py`, `test_manager.py`, `watch_manager.py`, `secret_manager.py`, `global_variable_store.py`, `allocation_manager.py`, `resource_manager.py`.
- UI blueprints `webinterface/blueprints/projects/*` (`routes.py`, `routes_releases.py`, `routes_calendar.py`, `routes_tests.py`, `routes_infrastructure.py`, `routes_watches.py`, `routes_builds.py`, `routes_repositories.py`, `routes_release_templates.py`) — URLs key on int `{project_id}` and call legacy managers.
- Migration `003_project_management_tables.py`.

**Uses NEW (`projects_projects`, keyed on UUID `project_id` / `slug`):**
- `projects/restapi/v1/projects_routes.py` (lifecycle, keys `{slug}`), `projects/repository.py`, `projects/service.py`, `projects/slug.py`, `projects/bus_subscriber.py`, `projects/metadata_registry.py`, `projects/extensions/*`.
- All orchestration REST routes resolve the project via `projects_repo.get_project_by_id(project_id=UUID)` and read `.slug`: `orchestration/build/.../build_runs_routes.py`, `test/test_runs_routes.py`, `infra/{provisioning_runs,drift,environments,guards}_routes.py`, `pipelines/{pipeline_definitions,pipeline_runs}_routes.py`, `source/source_integrations_routes.py`, `test/test_catalog_routes.py`, `metrics/{metrics,dashboards,metric_alerts,slos}_routes.py`.
- Feature models store a *loose* UUID `project_id` column (no DB FK) pointing at the new project: `orchestration/{build,test,source}/models.py`, `pods/models.py`, `metrics/{dashboards,alerts,slos}/models.py`, `secrets/models.py` (`owner_project_id`), `secrets/secrets_service.py` (scope_ref = project UUID, checks `ProjectMemberBinding`).

**Uses BOTH (the actual fault line):**
- `projects/restapi/v1/release_templates_routes.py`: mounted at `/api/v1/projects/{project_id}/release-templates` — the *same* prefix the orchestration routes treat as a UUID — but it parses `{project_id}` with `_parse_path_int` and delegates to the legacy `ReleaseTemplateManager` (FK `projects.proj_id`). Its own module docstring documents the missing bridge. This is the single REST endpoint that interprets `{project_id}` differently from its siblings.

## 3. Recommended bridge direction

**Choose (A): add a nullable `legacy_proj_id BigInt` column (+ unique index) to `projects_projects`.**

Rationale:
- The new slug-Project is the forward-facing identity (REST + orchestration already standardize on its UUID and slug). All net-new writes flow through `projects/service.py`, so adding one column there is a single, contained write-path change.
- Blast radius is minimal: legacy tables and their FKs (`projects.proj_id`) are untouched; legacy managers keep working unchanged. We only need a lookup `UUID/slug → legacy int` to let `release_templates_routes` (and any future legacy-manager-backed REST) resolve the correct legacy row.
- Backfill is a one-column update, not a table populate.

Rejected:
- (B) `project_uuid + slug` on legacy `Project` — touches the most heavily-FK'd, most-referenced table and the `proj_name` uniqueness story; every legacy manager would gain a second identity to keep consistent. Highest blast radius.
- (C) `project_id_map` join table — cleanest separation but adds a third entity, a join on every resolve, and two-sided write coordination with no offsetting benefit for a near-empty host. Keep as fallback if a many-to-one or historical-remap requirement ever appears.

The two ORMs use separate `declarative_base()` metadata but share one Alembic chain (`core/migrations`), so a cross-schema column addition is mechanically fine — but a real cross-base SQLAlchemy `ForeignKey` is awkward. Model `legacy_proj_id` as a **plain indexed BigInt column, not an ORM relationship** (soft link), mirroring how feature models already hold a bare UUID `project_id` with no DB FK.

## 4. Backfill strategy

Assumption (stated explicitly): the alpha host is near-empty; expect a handful of rows, possibly zero overlap. The migration must be correct on a populated DB but is not perf-sensitive.

- New Alembic revision (downstream of the current head): `ALTER TABLE projects_projects ADD COLUMN legacy_proj_id BIGINT NULL` + unique index `uq_projects_projects_legacy_proj_id`.
- Data backfill in the same revision, matching on the only shared natural key: `projects.proj_name == projects_projects.slug` (and/or `display_name`). Where a deterministic match exists, set `legacy_proj_id`.
- Orphans, new→legacy: a `projects_projects` row with no matching legacy row keeps `legacy_proj_id = NULL`. Endpoints that need a legacy row return 404/409 with a clear "project not provisioned in legacy store" detail.
- Orphans, legacy→new: a legacy `projects` row with no `projects_projects` counterpart is left as-is (legacy managers still serve it). Optionally a follow-up data script mints a slug-Project for each, but that is *not* required for the bridge and is gated behind a human decision (see §7).
- Idempotent + reversible: downgrade drops the index and column. No legacy data is mutated.

## 5. The resolver

`resolve_project(...)` — new function in `source/site/ccai/pychestrate/webservice/projects/repository.py` (it already owns `get_project_by_slug` / `get_project_by_id` and imports the new model).

- Accepts: `db_session`, plus exactly one of `slug: str | uuid: str | legacy_id: int` (keyword-only, mirroring existing repo style). A thin `resolve_project_ref(ref: str)` wrapper sniffs the token: parseable UUID → uuid; all-digits → legacy_id; otherwise → slug.
- Returns: the new `Project` ORM row (canonical), from which callers read `.project_id`, `.slug`, and the new `.legacy_proj_id`. Return `None` when unresolved (callers raise their own 404 problem doc).
- A companion `resolve_legacy_proj_id(...) -> Optional[int]` returns `legacy_proj_id` for callers that must drive a legacy manager (i.e. `release_templates_routes`).
- Lives entirely on the new side; legacy managers stay ignorant of UUIDs.

## 6. Sequencing into PRs

1. **Schema + resolver (no behavior change).** Add `legacy_proj_id` column/index migration with match-on-slug backfill; add `legacy_proj_id` to the new `Project` model; add `resolve_project`/`resolve_legacy_proj_id` to `repository.py` + unit tests. *Mechanical, lowest risk.*
2. **Provision legacy counterpart on create.** In `projects/service.create_project`, after writing the slug-Project, create (or link) the legacy `projects` row and stamp `legacy_proj_id`. *Risky — write path; needs the §7 ownership decision.*
3. **Migrate `release_templates_routes` to UUID/slug.** Resolve `{project_id}` via the resolver, translate to `legacy_proj_id` before calling `ReleaseTemplateManager`; the URL now matches its sibling orchestration routes. *Risky — public REST contract change; update tests `test_p22a_*`.*
4. **Backfill data script for legacy→new orphans** (mint slug-Projects), if §7 approves. *Risky — data creation.*
5. **Bridge UI blueprints.** Let `webinterface/blueprints/projects/*` accept slug and resolve to legacy int internally. *Mechanical-ish, broad surface.*
6. **Retire dual-model awareness.** Remove `_parse_path_int` special-casing and the "two models" docstrings; document the resolver as the single entry point. *Mechanical.*

PRs 1, 3, 6 are independently shippable with no data assumptions. PRs 2/4/5 depend on the §7 decision.

## 7. Risks + open questions

- **Identity authority:** which model is the system-of-record going forward? The plan assumes the slug-Project is canonical and legacy is a satellite — confirm.
- **Auto-provisioning legacy rows (PR 2):** should every new slug-Project get a legacy `projects` row, and who owns `proj_owner_id` when the new model only has `owning_group_id`? Needs a mapping rule.
- **Slug vs proj_name collisions:** legacy `proj_name` allows chars a slug forbids; backfill matching may miss/mis-match. Decide normalization.
- **RBAC divergence:** new side uses `system:projects.*` + bindings; legacy uses `ProjectManager.check_permission`. After bridging, which governs `release-templates`? Pick one to avoid a permission gap.
- **Cross-base migrations:** confirm the single Alembic env (`core/migrations/env.py`) sees both metadatas so the new column lands cleanly.
