# 9-ui-profiles — Tasks

## Milestones

- **M1 — Skeleton:** Surface enum and tags, `UiProfileService` reading the
  SYSTEM variable, `build_navigation_manifest` filtering, `/api/v1/me/navigation`
  response fields, admin page.
- **M2 — Core Behavior:** `user_preference` table and repository, preferences
  API and page, shell re-fetch, palette/dashboard/project-tab filtering,
  hidden-surface notice.
- **M3 — Hardening:** Property tests, 16-combination render sweep, metrics,
  audit, docs.

## Tasks

### M1 — Skeleton

- [x] T1.1 — `site_shell/ui_profile.py`: `UiSurface`, `SURFACE_DISPLAY`, `UiProfile`, `filter_by_surface`, `UiProfileService.deployment_surfaces()` reading `ui.profile.surfaces` with fallback and warning.
- [x] T1.2 — Add `surfaces` to `NavEntry`, `NavGroup`, `BundleRegistration`; tag existing entries (build: Builds, Pipelines, Release Templates; testing: Runs, Catalog, Metrics; infra: Infra, Pods, Ops); startup lint for unknown tags. *Done 2026-09-05. Fleet entries were kept core (pods and clients serve every domain); only Environments, Provisioning, and Blast-Radius Guards carry `infra`. Runs carries build, testing, and rpa.*
- [x] T1.3 — `build_navigation_manifest(*, held_permissions, enabled_surfaces)` filtering and empty-group drop; cache key includes the surface set.
- [x] T1.4 — `/api/v1/me/navigation` passes the effective surfaces and adds `ui_profile` to the response.
- [x] T1.5 — Admin page `/admin/ui-profile` (checkboxes, governed-entry counts, CSRF, audit) and `PUT /api/v1/admin/ui-profile`; nav entry in the Admin group; permission `admin.ui_profile.manage`. *Done 2026-09-05; the permission key is `system:ui.profile.manage`, the REST routes live in `site_shell/ui_profile_routes.py`, and the audit entry is still open (M3).*
- [x] T1.6 — Template global `ui_profile` installed by `install_template_globals` and resolved in the shell wrappers; register a fixture in `template_contexts.py`. *Done 2026-09-05 as a request-scoped proxy (`request_profile_scope` in the shell wrappers) rather than a per-render context entry.*

### M2 — Core Behavior

- [x] T2.1 — `user_preference` ORM + migration; `UserPreferencesRepository`; `PreferencesManager`. *Done 2026-09-05 as `site_shell/preferences_models.py` (`ui_user_preference`, migration `a3b4c5d6e7f8`) with repository functions in `ui_profile.py`.*
- [x] T2.2 — `GET|PUT|DELETE /api/v1/me/preferences/ui.surfaces` with validation and intersection rule.
- [x] T2.3 — `/account/preferences` page with checkboxes limited to deployment surfaces, "Use deployment default", reset notice; header account-menu link. *Done 2026-09-05 (`config/routes_account.py`, `/account/preferences`, header link in the shell).*
- [x] T2.4 — Shell: re-fetch navigation after preference save without reload; palette provider filtering; dashboard tile filtering. *Done 2026-09-05: navigation is re-fetched on the full page load that follows a save; the palette's only provider searches the already-filtered manifest and the home view builds from it, so both follow the profile.*
- [x] T2.5 — Project and resources sub-nav filtering with the active-tab exception. *Done 2026-09-05 for the project sub-nav (Builds, Infrastructure, Tests, RPA tabs) with the active-tab exception; resources sub-nav has no surface-tagged tabs.*
- [x] T2.6 — Hidden-surface notice element when the current route's surface is disabled. *Done 2026-09-05 (`chrome/hidden-surface-notice.js` driven by `ui_profile.hidden_routes`; project tabs render the notice server-side).*
- [x] T2.7 — Tag RPA entries, tiles, and palette provider with `rpa` (coordinated with `6-rpa-orchestration` T3.4). *Done 2026-09-05 for the RPA project tab; no global RPA nav entry, tile, or palette provider exists yet.*

### M3 — Hardening

- [x] T3.1 — Metrics and structured logs; bus event on deployment change. *Done 2026-09-05 (`entity.ui_profile.deployment_changed` bus event, audit kind, `pychestrate_ui_profile_deployment_changed_total` counter).*
- [x] T3.2 — `openapi/pychestrate.yaml` entries for the new routes. *Done 2026-09-05 (`/admin/ui-profile`, `/me/preferences/ui.surfaces` under the `ui-profile` tag).*
- [x] T3.3 — Userguide section "Choosing what the UI shows" and glossary entries (surface, profile). *Done 2026-09-05 (`userguide/20-00-ui-profiles.rst`, glossary entries).*

## Test Tasks

- [x] Property 1 (monotonic filtering), Property 2 (effective set), Property 3 (round trip) as testbase property tests.
- [x] Render sweep: shell rendered for all 16 surface subsets; no empty groups, core entries present, RPA-only shows exactly the expected sidebar.
- [x] Route tests: admin PUT validation (422 on unknown/empty), preferences PUT/DELETE, navigation response fields, override reset notice.
- [ ] Browser test: save a preference, sidebar updates without reload; visit a hidden route, notice appears and dismisses.

## Definition of Done

- An administrator can restrict the deployment to any non-empty subset of
  surfaces; a user can narrow within it; navigation, palette, dashboard, and
  project tabs follow; hidden routes remain reachable with a notice.
- Phase-13 guardrails and the full singlehost suite pass; the browser sweep
  is clean on the two new pages.
