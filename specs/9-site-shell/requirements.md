# 9-site-shell — Requirements

## Introduction

`9-site-shell` is the top-level UI shell that wraps every authenticated
page in Pychestrate. It owns the unified site chrome — header (product
name, user menu, global search), left sidebar (collapsible groups,
permission-gated entries), main content area, and an optional right rail
for context panels. It owns the unified `Ctrl/Cmd + K` command palette,
the post-login routing logic, the "no visible entries" empty state, and
keyboard a11y for navigation. The shell is feature-agnostic: every
feature surface (admin, project dashboard, run detail, etc.) declares
its sidebar entries through a registry the shell intersects against the
caller's permissions; the shell never hard-codes which features exist.
The shell is also what `/login`, `/logout`, the first-run setup wizard,
and the canonical error pages are explicitly *outside* of — those pages
render chromeless. Ships in **Phase 10** alongside `9-admin-ui` so the
Jenkins-style unified UI lands as one coherent product change. Sits at
the top of Layer 9, consuming `1-authentication`, `1-rbac`, and
`9-ui-design-tokens`.

## Requirements

### Requirement 1: Unified Site Chrome and Layout

**User Story:** As any authenticated user of Pychestrate, I want a
single, consistent chrome — header, sidebar, content — that wraps every
page I visit, so that I learn the navigation model once.

**Acceptance Criteria (EARS):**

1. WHEN any authenticated browser navigation lands on a non-chromeless route THEN the system SHALL render the site shell document, which SHALL contain a header region (product brand, global search trigger, user menu), a left sidebar region (collapsible permission-gated entries), a main content region (the page-specific Custom Element), and an optional right-rail region (filled only when the active page declares context panels).
2. WHEN the user collapses the sidebar via the toggle affordance THEN the shell SHALL persist the collapsed state for the lifetime of the session AND SHALL re-expand to the previous width on the next explicit user action; collapsed-state persistence SHALL NOT use `localStorage` (session-scoped only).
3. WHEN the active page declares a right-rail panel THEN the shell SHALL render it; otherwise the main content region SHALL consume the right-rail's space.
4. WHILE the viewport is narrower than the documented minimum (mobile breakpoint — out of scope for v1) the shell MAY render in a degraded narrow-mode but SHALL NOT lose any sidebar entry; mobile-specific layout is explicitly deferred per "Out of Scope".

### Requirement 2: Declarative Sidebar Registration

**User Story:** As a feature author shipping a new page, I want to
declare my sidebar entries and let the shell handle visibility, so that
I never have to write RBAC or render code for the sidebar.

**Acceptance Criteria (EARS):**

1. WHEN a feature bundle loads THEN it SHALL be able to register one or more sidebar entries with the shell registry, each entry shaped as `{label, route, icon?, required_permissions: [...], group?}`. An entry with `required_permissions: []` (or omitted) SHALL be visible to every authenticated user.
2. WHEN a feature declares a `group` THEN the shell SHALL render its entry under that group heading; entries without a `group` SHALL render at the top level of the sidebar.
3. WHEN the shell renders the sidebar THEN it SHALL intersect each entry's `required_permissions` against the live permissions payload from `GET /api/v1/me/permissions` AND SHALL include the entry if and only if every required permission is present (set semantics — not predicate).
4. WHERE a group declares its own `required_permissions` (e.g., "Admin" requires `ui.admin.view`) THEN the entire group SHALL be hidden — header label and all entries — when the caller lacks any of the group's required permissions, regardless of per-entry permissions.
5. WHEN the same route is registered twice (e.g., duplicate bundles) THEN the shell SHALL deduplicate by `route` AND emit a `pychestrate.ui.shell.sidebar_dup_route` log event identifying the colliding labels; the first registration wins.

### Requirement 3: Chromeless Routes and Login Redirection

**User Story:** As a visitor hitting a protected page without a session,
I want to be redirected to a single canonical login page rather than
seeing a half-rendered shell or a JSON error.

**Acceptance Criteria (EARS):**

1. WHEN a browser GETs a non-chromeless route without a valid session THEN the shell's server-side gate SHALL respond per `1-authentication` Requirement 5 with HTTP 303 to `/login?next=<encoded-path>`.
2. WHILE rendering a chromeless route — `/login`, `/logout` (transition), the first-run setup wizard, the 404 page, the 403 forbidden page, and the 500 error page — the shell document SHALL NOT be loaded; these pages SHALL render their own minimal HTML and import only the design-tokens stylesheet.
3. WHEN the active session expires mid-navigation (any XHR/fetch returns 401) THEN the shell SHALL surface a non-blocking re-auth toast AND, on the next full navigation, the gate SHALL redirect to `/login?next=<current-path>` per Requirement 1 above.
4. WHEN the user logs out via the user-menu logout action THEN the shell SHALL POST to the logout endpoint AND the browser SHALL follow the 303 to `/login` per `1-authentication` Requirement 5; the shell SHALL NOT attempt to render any post-logout chrome.

### Requirement 4: Permission-Cache Freshness

**User Story:** As a user whose role just changed, I want my visible
sidebar to reflect the new role without having to manually reload, so
that revocations and grants take effect promptly.

**Acceptance Criteria (EARS):**

1. WHEN the shell completes a full navigation (a top-level route change, NOT an in-page XHR) THEN it SHALL refetch `GET /api/v1/me/permissions` AND recompute the visible sidebar from the fresh payload.
2. WHEN the permissions payload differs from the previous navigation's payload THEN the shell SHALL emit `pychestrate.ui.shell.permissions_changed` with `{added: [...], removed: [...]}` AND apply the diff to the rendered sidebar in the same render cycle.
3. IF the `/me/permissions` fetch fails THEN the shell SHALL reuse the previously-cached payload AND surface a non-blocking degraded-state banner; the shell SHALL NOT block navigation on a permissions fetch.
4. WHILE the shell holds a stale permissions cache (degraded state) THEN every sidebar entry click SHALL still navigate, AND the per-page server-side route guard SHALL remain the authoritative check (sidebar visibility is UX only, never the security boundary).

### Requirement 5: Empty-State Handling

**User Story:** As a newly-provisioned user who has not yet been granted
any project or admin permissions, I want a clear "ask your admin"
message rather than a blank sidebar, so that I understand what to do
next.

**Acceptance Criteria (EARS):**

1. IF the authenticated user's visible sidebar entry count (after permission intersection) is zero THEN the shell SHALL render the documented "no access" empty state — product brand, user menu (so the user can sign out), and a centered "Your account has no access yet — ask an administrator to grant you a role" panel.
2. WHEN the empty state is rendered THEN the shell SHALL emit `pychestrate.ui.shell.empty_state_rendered` with `{user_id_hash}` for observability.
3. WHEN the user has at least one visible entry but the entry list is short (1–2) THEN the shell SHALL render the sidebar normally — the empty state is only for the zero-entry case.

### Requirement 6: Keyboard Accessibility

**User Story:** As a keyboard user, I want to navigate the sidebar with
arrow keys and reach any entry without leaving the keyboard, so that I
can use the product without a mouse.

**Acceptance Criteria (EARS):**

1. WHEN focus is inside the sidebar THEN `ArrowDown` / `ArrowUp` SHALL move between sibling entries, `ArrowRight` SHALL expand a collapsed group, `ArrowLeft` SHALL collapse an expanded group, and `Enter` SHALL navigate to the focused entry's route.
2. WHEN focus is inside the sidebar AND the user types one or more printable characters within 1 second of each other THEN the shell SHALL jump focus to the first sibling entry whose label starts with the typed prefix (case-insensitive); the prefix buffer SHALL reset after 1 second of inactivity.
3. WHEN a full navigation completes THEN the shell SHALL move focus to the main content region's `<h1>` (or the first focusable element if no `<h1>` exists) AND announce the new page title via an `aria-live="polite"` region.
4. WHEN the user presses `Ctrl/Cmd + K` THEN the shell SHALL open the command palette dialog with `role="dialog"`, `aria-modal="true"`, focus trapped on the search input until dismissed with `Esc`.

### Requirement 7: Command Palette

**User Story:** As a power user, I want a single `Ctrl/Cmd + K` palette
that searches across every feature's contributed providers, so that I
can jump to any entity without first navigating to its tab.

**Acceptance Criteria (EARS):**

1. WHEN a feature bundle loads THEN it MAY register one or more palette search providers `{providerId, label, query: (q: string) => Promise<PaletteResult[]>}`; providers SHALL declare their own `required_permissions` and SHALL only be invoked when the caller holds them.
2. WHEN the user opens the palette and types at least 2 characters THEN the shell SHALL fan out (with per-query debounce of 150 ms) to every visible provider AND render grouped results labeled by provider.
3. WHEN the user selects a result THEN the shell SHALL navigate to `result.route` AND close the palette.
4. IF a provider's query throws or times out (5 s default) THEN the shell SHALL render the provider's group with an inline error AND SHALL NOT block the other providers' results.

## Property-Based Test Requirements

### Property 1: Sidebar Visibility Is a Pure Function of Permissions

- **Invariant:** For any registry state R and any permission set P, the visible sidebar entry list is a deterministic intersection of each entry's `required_permissions` with P; permuting P or permuting registration order has no effect on the resulting list.
- **Generator:** Random registry states with 1–50 entries across 0–10 groups, each entry declaring 0–5 required permissions drawn from a fixed catalog; random permission sets drawn from the same catalog.
- **Assertion:** `visibleSidebar(R, P) == visibleSidebar(R, permutation(P))` and `visibleSidebar(R, P) == visibleSidebar(permutation(R), P)`.
- **Sample size:** 1000 generated cases.

### Property 2: Empty-State Is Exactly the Zero-Entry Predicate

- **Invariant:** For any registry state R and any permission set P, the shell renders the empty state if and only if `len(visibleSidebar(R, P)) == 0`.
- **Generator:** Same as Property 1, with bias toward both extremes (no permissions, all permissions).
- **Assertion:** Empty-state render flag equals `len(visibleSidebar(R, P)) == 0` for every case.
- **Sample size:** 1000 generated cases.

### Property 3: Palette Provider Permission Scoping

- **Invariant:** For any palette search query, results from a provider declaring `required_permissions = [p1, ..., pn]` appear in the rendered output if and only if the caller holds every `pi`.
- **Generator:** Random sets of providers with random required-permission declarations; random permission sets.
- **Assertion:** Every rendered result's source provider's `required_permissions` is a subset of the caller's permissions.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Shell TTI p95 < 400 ms on a warm permission cache. Sidebar render p95 < 50 ms for registries up to 100 entries. Full-navigation permission refetch p95 < 80 ms (server). Palette open-to-first-keystroke-render p95 < 80 ms. Palette query fan-out total latency p95 < 250 ms with 5 providers.
- **NFR-2 (Security):** Sidebar visibility is UX only — every protected route SHALL be guarded server-side by the owning feature's existing RBAC enforcement. The shell SHALL NOT cache the permissions payload across browser tabs or to `localStorage` / `sessionStorage`; cache is in-memory per document. The shell SHALL NOT log full permission payloads — only counts and diffs (added/removed key lists). Palette query strings SHALL be capped at 128 characters and SHALL be sent same-origin with CSRF.
- **NFR-3 (Observability):** Client metrics beaconed: `pychestrate_ui_shell_tti_seconds` (histogram), `pychestrate_ui_shell_sidebar_render_duration_seconds` (histogram), `pychestrate_ui_shell_navigation_duration_seconds` (histogram), `pychestrate_ui_shell_permissions_fetch_duration_seconds{outcome}` (histogram), `pychestrate_ui_shell_palette_query_duration_seconds{provider, outcome}` (histogram), `pychestrate_ui_shell_sidebar_entry_clicked_total{group, route}` (counter), `pychestrate_ui_shell_empty_state_total` (counter), `pychestrate_ui_shell_permissions_degraded_total` (counter). Log events `pychestrate.ui.shell.rendered`, `pychestrate.ui.shell.sidebar_entry_clicked`, `pychestrate.ui.shell.palette_opened`, `pychestrate.ui.shell.permissions_changed`, `pychestrate.ui.shell.empty_state_rendered`, `pychestrate.ui.shell.sidebar_dup_route`.
- **NFR-4 (Reliability):** A failed permissions fetch SHALL NOT prevent navigation — the previous cached payload SHALL continue to drive sidebar visibility while the degraded banner is shown. A single palette provider failure SHALL NOT prevent other providers' results from rendering. A malformed sidebar registration (missing `route`, malformed `required_permissions`) SHALL be dropped with a logged warning AND SHALL NOT crash the shell.

## Out of Scope

- **Theming and dark mode** — covered by `9-ui-design-tokens`; the
  shell consumes tokens but does not define them.
- **The contents of any specific page** — every page (admin, project
  dashboard, run detail, etc.) has its own spec; the shell only owns
  the wrapping chrome and the sidebar/palette registries.
- **Real-time notifications** — a future notification feature will plug
  into a header notification affordance; the affordance itself and the
  push transport are not specified here.
- **Mobile responsive layout** — explicitly deferred; v1 targets
  desktop browser viewports. A future `9-site-shell-mobile` (or an
  extension of this spec) covers narrow viewports.
- **The login page itself** — owned by `1-authentication` Requirement 5;
  the shell only declares the redirection contract.
- **The first-run setup wizard** — owned by `1-user-management` /
  `0-web-app-host`; the shell defers to the setup gate.

## Dependencies

- **Depends on:** `9-ui-design-tokens`, `1-authentication` (login
  surface, `next` validation, session cookie), `1-rbac` (permission
  evaluation, the `ui.admin.view` permission), `1-user-management`
  (user-menu display name), `0-web-app-host` (setup-gate
  precedence, base routing), `8-rest-api-v1` (`/api/v1/me/permissions`).
- **Depended on by:** every Layer-9 feature surface that wants to
  appear inside the unified UI — `9-admin-ui`,
  `9-project-dashboard-ui`, `9-run-detail-ui`, future surfaces.
- **Extension points exposed:** sidebar registry (`registerGroup`,
  `registerEntry`), palette provider registry (`registerProvider`).
  These are in-browser JavaScript registries, not Python factory
  protocols — they are consumed by feature bundles at load time.
