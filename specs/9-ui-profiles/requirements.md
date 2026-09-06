# 9-ui-profiles — Requirements

## Introduction

The `9-ui-profiles` feature lets a deployment, and then each user, choose
which **automation surfaces** the web UI presents. Pychestrate now serves
four domains — Build Automation, Testing Automation, Infrastructure, and
Robotic Process Automation (`6-rpa-orchestration`) — and a team that only
runs RPA jobs should not navigate past build pipelines, test catalogs, and
release templates to reach them. A **surface** is a named slice of the UI
(navigation entries, dashboard tiles, palette providers, project sub-nav
tabs, and bundles) that can be shown or hidden as a unit. The feature lives
in **Layer 9** beside `9-site-shell` and ships in **Phase 11**.

Surfaces gate *presentation*, not *access*: a hidden route stays reachable by
URL and stays governed by `1-rbac`. Today navigation is filtered only by held
permissions (`build_navigation_manifest(*, held_permissions)`); this feature
adds a second filter, enabled surfaces, computed from a deployment default
and an optional per-user override.

## Requirements

### Requirement 1: Surfaces Are A Fixed, Tagged Vocabulary

**User Story:** As a maintainer, I want every navigation entry, dashboard
tile, palette provider, and bundle to declare which surface it belongs to,
so that hiding a surface hides all of it and nothing else.

**Acceptance Criteria (EARS):**

1. THE system SHALL define the surface vocabulary `UiSurface = { "build", "testing", "rpa", "infra" }` with display names "Build Automation", "Testing Automation", "Robotic Process Automation", "Infrastructure", AND SHALL treat entries without a surface tag as **core** (always shown: Projects, Resources, Admin, Account, Help).
2. WHEN a `NavEntry`, `NavGroup`, dashboard tile, palette provider, project sub-nav tab, or bundle registration is declared THEN it SHALL accept an optional `surface: UiSurface` attribute, AND a startup lint SHALL fail if a tag names an unknown surface.
3. WHEN all entries of a `NavGroup` are hidden by surface filtering THEN the group SHALL be hidden as well.
4. THE system SHALL tag existing entries as follows: Builds, Pipelines, Release Templates → `build`; Runs, Catalog, Metrics → `testing`; Infra, Pods, Ops (fleet) → `infra`; RPA entries → `rpa`. Entries that serve several domains (Runs when RPA jobs also appear there) SHALL carry a set of surfaces and show when any is enabled.

### Requirement 2: The Deployment Sets A Default Profile

**User Story:** As an administrator, I want to choose which surfaces this
deployment presents by default, so that a single-purpose installation shows
only what it is for.

**Acceptance Criteria (EARS):**

1. THE system SHALL store the deployment profile as a SYSTEM-scope global variable `ui.profile.surfaces` whose value is a JSON list of `UiSurface` values, defaulting to all four surfaces when absent.
2. WHEN an administrator saves the deployment profile from `/admin/ui-profile` THEN the system SHALL validate the list (known surfaces, at least one), persist it, write an audit entry, and SHALL invalidate the navigation manifest cache so the next request reflects it.
3. IF the variable holds an unparseable or empty value THEN the system SHALL fall back to all surfaces and SHALL log a warning naming the variable.
4. WHEN an administrator opens `/admin/ui-profile` THEN the system SHALL render one checkbox per surface with its display name, a description of what it shows, and a count of navigation entries it governs.

### Requirement 3: A User May Override The Profile

**User Story:** As a user, I want to narrow or widen the surfaces I see
within what the deployment allows, so that my daily view matches my work.

**Acceptance Criteria (EARS):**

1. THE system SHALL persist per-user preferences in a `user_preference` table `{ user_id, key, value_json, updated_at }` with key `ui.surfaces` holding a JSON list of `UiSurface`, AND SHALL expose `GET|PUT /api/v1/me/preferences/ui.surfaces`.
2. WHEN a user has an override THEN the effective surfaces SHALL be `override ∩ deployment_surfaces`; IF the intersection is empty THEN the system SHALL use the deployment surfaces and SHALL show a notice on the preferences page that the selection was reset.
3. WHEN a user opens `/account/preferences` THEN the system SHALL render the surfaces the deployment allows as checkboxes, pre-checked from the effective set, with a "Use deployment default" action that deletes the override.
4. WHEN the override is saved THEN the site shell SHALL refresh navigation without a full reload (re-fetching `/api/v1/me/navigation`).

### Requirement 4: Effective Surfaces Gate Every Presentation Point

**User Story:** As a user with only the RPA surface enabled, I want the
sidebar, palette, dashboard, project tabs, and empty states to show only RPA
and core items, so that the product feels purpose-built.

**Acceptance Criteria (EARS):**

1. WHEN `GET /api/v1/me/navigation` is served THEN the manifest SHALL contain only entries whose surface is enabled or core, AND SHALL include `effective_surfaces: list[UiSurface]` and `deployment_surfaces` in the response so the shell can render preference controls.
2. WHEN the site shell renders THEN the palette SHALL query only providers whose surface is enabled, AND the dashboard SHALL render only tiles whose surface is enabled.
3. WHEN a project page renders the project sub-nav THEN tabs tagged with a disabled surface SHALL be omitted; IF the current route belongs to a disabled surface THEN the tab SHALL still render as active so the user is never on a page with no active tab.
4. WHEN a user navigates by URL to a route of a disabled surface THEN the route SHALL render normally (subject to RBAC) and the shell SHALL show a dismissible notice "This area is hidden from your navigation" with a link to `/account/preferences`.
5. WHEN the effective surfaces change THEN the catch-all route's known-route check SHALL be unaffected (bundles remain registered), so no hidden surface produces a 404.

### Requirement 5: The Profile Is Observable And Testable

**Acceptance Criteria (EARS):**

1. THE system SHALL expose `effective_surfaces` in the template context of every shell-wrapped page under `ui_profile`.
2. WHEN the navigation manifest is built THEN the system SHALL record a metric `ui_navigation_entries_hidden_total{surface}`.
3. THE test suite SHALL render the shell for every subset of surfaces (16 combinations) and assert that no group is empty and no core entry is missing.

## Property-Based Test Requirements

### Property 1: Filtering Is Monotonic

For any manifest and surface sets A ⊆ B, the entries shown under A are a
subset of those shown under B, and core entries are shown under both.

### Property 2: Effective Set Is Well-Defined

For any deployment list D (non-empty, valid) and override O, the effective
set is `O ∩ D` when non-empty, else D; it is never empty and never contains
a surface outside D.

### Property 3: Round Trip

Saving any valid surface list through the preferences API and reading it
back yields the same list in canonical order.

## Non-Functional Requirements

- Filtering adds under 1 ms to manifest construction; the effective surface
  set is computed once per request and cached with the manifest per
  `(permission set, surface set)`.
- The `user_preference` table is generic (string key, JSON value) so later
  preferences (theme, density, default project) reuse it.

## Out of Scope

- Per-project surface settings; the profile is deployment-wide with user
  overrides.
- Hiding REST endpoints or enforcing access through surfaces; RBAC does that.
- Theme, density, or layout preferences (the table supports them later).
- A visual "role picker" onboarding wizard.

## Dependencies

- `9-site-shell` (`nav_manifest.py`, `bundle_registry.py`, palette,
  dashboards, `me_routes.py::/api/v1/me/navigation`).
- Global variables service (`variables/service.py`, SYSTEM scope) for the
  deployment profile.
- `1-identity` users table for the `user_preference` foreign key; `1-rbac`
  permission `admin.ui_profile.manage` for the admin page.
- `1-audit-log` for profile changes.
- `6-rpa-orchestration` supplies the `rpa`-tagged entries.
