# 9-ui-profiles — Design

## Architecture

UI profiles add one concept — the **surface** — and thread it through the
three places the shell decides what to show: the navigation manifest, the
bundle/palette/dashboard registrations, and the project sub-nav. The
effective surface set is resolved per request by a small service and cached
alongside the permission-filtered manifest.

```
 SYSTEM variable ui.profile.surfaces ─┐
                                      ├─▶ UiProfileService.effective_surfaces(user_id)
 user_preference[user_id, ui.surfaces]┘              │
                                                     ▼
   build_navigation_manifest(*, held_permissions, enabled_surfaces)
   palette providers / dashboard tiles / project tabs filtered by surface
                                                     │
                                                     ▼
              GET /api/v1/me/navigation  ──▶ pyc-site-shell renders
```

Deployment default lives in the existing global variables store (SYSTEM
scope) because it is deployment configuration that administrators already
manage there. Per-user overrides need a new generic `user_preference` table;
feature flags were considered (the flag store already supports per-user
contexts) but flags are operational toggles, not user settings, and the
admin UI would be confusing.

## Data Model

```
user_preference
  user_id      TEXT FK user(id) ON DELETE CASCADE
  key          TEXT NOT NULL
  value_json   JSON NOT NULL
  updated_at   TIMESTAMP NOT NULL
  PRIMARY KEY (user_id, key)
```

Global variable (no schema change): `ui.profile.surfaces`, SYSTEM scope,
JSON list, default `["build", "testing", "rpa", "infra"]`.

Python types in `webservice/webinterface/site_shell/ui_profile.py`:

```python
class UiSurface(str, Enum):
    BUILD = "build"; TESTING = "testing"; RPA = "rpa"; INFRA = "infra"

SURFACE_DISPLAY = {UiSurface.BUILD: "Build Automation", ...}
ALL_SURFACES = frozenset(UiSurface)

@dataclass(frozen=True)
class UiProfile:
    deployment_surfaces: frozenset[UiSurface]
    override_surfaces: Optional[frozenset[UiSurface]]
    effective_surfaces: frozenset[UiSurface]
    override_reset: bool   # True when override ∩ deployment was empty
```

`NavEntry` and `NavGroup` gain `surfaces: frozenset[UiSurface] = frozenset()`
(empty means core). `BundleRegistration` gains the same field; palette
providers and dashboard tiles declare `surface` in their registration
dataclasses.

## Interfaces

### Public API

- `GET /api/v1/me/navigation` — existing; response adds
  `ui_profile: { deployment_surfaces, effective_surfaces, override_surfaces, override_reset }`
  and the entries are already filtered.
- `GET /api/v1/me/preferences/ui.surfaces` → `{ surfaces: [...], effective: [...], deployment: [...] }`.
- `PUT /api/v1/me/preferences/ui.surfaces` body `{ surfaces: [...] }` → 200
  same shape; 422 on unknown surface or empty list.
- `DELETE /api/v1/me/preferences/ui.surfaces` — remove the override.
- `GET /api/v1/admin/ui-profile` → `{ surfaces: [...], governed_entries: {surface: int} }` (`admin.ui_profile.manage`).
- `PUT /api/v1/admin/ui-profile` body `{ surfaces: [...] }`.

Web pages:

- `/admin/ui-profile` — checkbox form, CSRF, save + audit.
- `/account/preferences` — checkbox form within deployment surfaces, "Use
  deployment default" button; linked from the header account menu.

### Internal API

- `UiProfileService(variables_service, preferences_repo)`:
  `deployment_surfaces()`, `override_for(user_id)`,
  `effective_profile(user_id) -> UiProfile`, `set_deployment(surfaces, actor)`,
  `set_override(user_id, surfaces)`, `clear_override(user_id)`.
- `UserPreferencesRepository`: `get(user_id, key)`, `put(user_id, key, value)`,
  `delete(user_id, key)`.
- `build_navigation_manifest(*, held_permissions, enabled_surfaces=ALL_SURFACES)`
  — filters entries whose `surfaces` is non-empty and disjoint from
  `enabled_surfaces`; drops empty groups.
- `filter_by_surface(items, enabled_surfaces)` — shared helper used for
  palette providers, dashboard tiles, project tabs.
- Template global `ui_profile` (installed by `install_template_globals`)
  resolved per request in the shell wrapper (`_wrap_fragment_handler_in_shell`,
  `_wrap_resources_handler_in_shell`) and passed to `shell_document.html`.

### Extension Surface

- Extensions registering nav entries, bundles, palette providers, or tiles
  set `surfaces`; an extension may not add a new surface value in this
  phase (vocabulary is fixed; see Open Questions).

### Events Emitted

`entity.ui_profile.deployment_changed { surfaces, actor_id }`.

### Events Consumed

None.

## Component Breakdown

- `site_shell/ui_profile.py` — enum, dataclasses, `UiProfileService`,
  `filter_by_surface`.
- `core/orm/user_preference.py` + migration; `core/managers/preferences_manager.py`.
- `site_shell/nav_manifest.py` — surface tags on entries, filtering,
  group-drop rule, `governed_entry_counts()`.
- `site_shell/bundle_registry.py` — `surfaces` on registrations (used by the
  palette and dashboards only; the catch-all known-route check ignores it).
- `security/auth/restapi/v1/me_routes.py` — navigation response fields,
  preferences routes.
- `blueprints/config/routes_ui_profile.py` + `config/templates/config/ui_profile.html`.
- `blueprints/config/routes_account.py` + `templates/config/account_preferences.html`.
- `pyc-site-shell`: `chrome/header.js` account menu link; `palette/palette-dialog.js`
  filters providers by `ui_profile.effective_surfaces`; dashboard renderer
  filters tiles; a `pyc-hidden-surface-notice` element shown when the
  current route's surface is disabled (route→surface map comes from the
  manifest's `bundles` list).
- Projects sub-nav (`projects/base.html`) and resources sub-nav read
  `ui_profile.effective_surfaces`.

## Key Flows

### Flow 1 — RPA-only deployment

Admin opens `/admin/ui-profile`, unchecks Build, Testing, Infra, saves.
Manifest cache invalidated; every user's next navigation fetch shows
Projects, RPA, Resources, Admin, Account. Project pages show only the
Overview, RPA, Settings tabs. The palette offers projects and RPA jobs.

### Flow 2 — User narrows their view

Deployment allows all four surfaces. A tester opens `/account/preferences`,
keeps Testing only, saves. The shell re-fetches navigation and re-renders the
sidebar without reload. Visiting `/builds` by URL still works and shows the
hidden-surface notice.

### Flow 3 — Deployment shrinks under an override

The tester's override is `{testing}`; the admin later restricts the
deployment to `{rpa}`. Intersection is empty; the effective set becomes
`{rpa}`, `override_reset` is true, and the preferences page shows a notice
that the selection was reset.

## Error Handling

- Unknown surface in any input → 422 with the offending values.
- Empty deployment list → 422 (an installation must show something).
- Corrupt variable value → warning log, fall back to all surfaces.

## Security Considerations

- Surfaces never grant or deny access; every route keeps its RBAC gate.
- `admin.ui_profile.manage` guards the deployment setting; users can only
  edit their own preference (path uses `me`).
- The preferences endpoints are CSRF-protected for cookie sessions like the
  rest of `/api/v1/me`.

## Observability

- Metric `ui_navigation_entries_hidden_total{surface}`; gauge
  `ui_profile_deployment_surfaces{surface}` (1/0).
- Audit entries for deployment changes; structured log
  `pychestrate.ui_profile.override_reset` when an intersection collapses.

## Open Questions

1. Should extensions be able to register new surfaces (an extension that
   adds a "Security Scanning" domain)? The fixed enum is simpler and covers
   the request; making it a registry is a small follow-up.
2. Should the header show a quick surface switcher (a segmented control) in
   addition to the preferences page? Recommended no for the first cut.
3. Should "Infrastructure" be a surface at all, or part of core? Fleet pages
   are operational rather than an automation domain; the design keeps it a
   surface so an RPA-only team can hide it, but it could be folded into core.
