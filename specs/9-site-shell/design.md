# 9-site-shell — Design

## Architecture

`9-site-shell` is the Jenkins-style unified UI chrome that wraps every
authenticated page in Pychestrate. It is implemented as a parent Custom
Element `<pyc-site-shell>` plus a small server-side adapter that serves
the shell document for every non-chromeless route. The shell owns the
header, the left sidebar (rendered from a declarative registry
contributed by feature bundles at load time), the main content slot
(which mounts the active page's Custom Element), and the global
command palette. Every cross-cutting concern feature surfaces used to
solve themselves — login redirection, permission-cache management,
empty-state handling, palette dispatch, keyboard navigation — is
centralized here. The shell does NOT own the contents of any specific
page; pages are passed in as Custom Elements selected by the active
route. The shell consumes `1-authentication` (session cookie, `/login`
redirect contract, `next`-parameter validation), `1-rbac`
(`/api/v1/me/permissions` and the `ui.admin.view` permission), and
`9-ui-design-tokens` (every color, spacing, and font). Ships in
**Phase 10** as a co-requisite of `9-admin-ui` so the unified UI lands
as one product change.

## Data Model

No persistent entities. Runtime state held in the shell document:

- `ShellSession` — `{actorId: string, permissions: Set<string>, fetchedAt: string, degraded: boolean}`.
- `SidebarRegistry` — `{groups: SidebarGroup[], entries: SidebarEntry[], registeredBy: Map<route, bundleId>}`.
- `SidebarGroup` — `{groupId: string, label: string, icon: string | null, requiredPermissions: string[], collapsed: boolean}`.
- `SidebarEntry` — `{entryId: string, label: string, route: string, icon: string | null, requiredPermissions: string[], group: string | null}`.
- `PaletteProviderRegistry` — `{providers: PaletteProvider[]}`.
- `PaletteProvider` — `{providerId: string, label: string, requiredPermissions: string[], query: (q: string) => Promise<PaletteResult[]>, timeoutMs: number}`.
- `RouteContext` — `{path: string, params: Record<string, string>, pageTag: string}`.
- `NavigationState` — `{current: RouteContext, previous: RouteContext | null, isNavigating: boolean}`.

The registries are populated by feature bundles at load time before the
shell renders its first frame; subsequent mutations (e.g., a
hot-loaded extension) trigger a re-render of the sidebar.

## Interfaces

### Public API

**Tag name:** `<pyc-site-shell>`

**Observed attributes:**

- `initial-route` (string) — server-supplied initial path; defaults to `location.pathname`.
- `permissions-endpoint` (string) — overrideable for testing; default `/api/v1/me/permissions`.
- `palette-timeout-ms` (string; integer; default `5000`).
- `aria-label` (string).

**Properties (JS):**

- `session: ShellSession | null`
- `sidebar: SidebarRegistryApi`
- `palette: PaletteRegistryApi`
- `activeRoute: RouteContext | null`
- `navigateTo(route: string): Promise<void>`
- `openPalette(): void`
- `closePalette(): void`
- `reloadPermissions(): Promise<void>`

**Events (bubbling, composed):**

- `pyc-site-shell-ready` — `{visibleEntryCount, degraded}`.
- `pyc-site-shell-navigated` — `{from, to}`.
- `pyc-site-shell-sidebar-clicked` — `{group, route}`.
- `pyc-site-shell-permissions-changed` — `{added, removed}`.
- `pyc-site-shell-empty-state-rendered` — `{}`.
- `pyc-site-shell-palette-opened` — `{}`.

**Slots:**

- `slot="brand"` — consumer-supplied brand/logo (defaults to "Pychestrate" wordmark).
- `slot="user-menu"` — consumer-supplied user-menu content (defaults to a built-in menu with display name + logout).
- `slot="header-extra"` — optional right-of-search header content.
- `slot="empty-state"` — override the default "ask your admin" empty-state content.

**CSS custom properties respected:**

- `--pyc-site-shell-bg` → `var(--pyc-color-app-bg)`
- `--pyc-site-shell-header-bg` → `var(--pyc-color-surface-elevated)`
- `--pyc-site-shell-header-fg` → `var(--pyc-color-on-surface-elevated)`
- `--pyc-site-shell-sidebar-bg` → `var(--pyc-color-surface)`
- `--pyc-site-shell-sidebar-fg` → `var(--pyc-color-on-surface)`
- `--pyc-site-shell-sidebar-fg-active` → `var(--pyc-color-accent-on-surface)`
- `--pyc-site-shell-sidebar-width` → `var(--pyc-space-sidebar-default)`
- `--pyc-site-shell-sidebar-width-collapsed` → `var(--pyc-space-sidebar-collapsed)`
- `--pyc-site-shell-focus-ring` → `var(--pyc-focus-ring)`
- `--pyc-site-shell-font-family` → `var(--pyc-font-family-ui)`

**A11y requirements:**

- Header: `role="banner"`; user menu `role="menu"`, items `role="menuitem"`.
- Sidebar: `role="navigation"`, `aria-label="Primary"`; groups expose `aria-expanded`; entries are `<a>` elements with `aria-current="page"` on the active route.
- Main content: `role="main"` with focus management on navigation.
- Palette: `role="dialog"`, `aria-modal="true"`, focus trapped, first focus on the search input, results rendered as `role="listbox"` with `role="option"` rows.
- Live region: `aria-live="polite"` for page-title announcements and palette result counts.

Server REST surfaces consumed:

- `GET /api/v1/me/permissions` — once per full navigation.
- `POST /api/v1/auth/logout` — on user-menu logout action.
- Per-page surfaces — owned by the active page, not the shell.

### Internal API

```typescript
class PermissionSet {
    has(perm: string): boolean
    hasAll(perms: string[]): boolean
    diff(other: PermissionSet): {added: string[], removed: string[]}
}

class SidebarRegistry {
    registerGroup(desc: SidebarGroup): void
    registerEntry(desc: SidebarEntry): void
    visible(perms: PermissionSet): {groups: SidebarGroup[], entries: SidebarEntry[]}
}

class PaletteRegistry {
    registerProvider(desc: PaletteProvider): void
    queryAll(q: string, perms: PermissionSet): Promise<PaletteGroupedResults>
}

class ShellRouter {
    parse(path: string): RouteContext
    navigateTo(route: string): Promise<void>
    onNavigate(cb: (s: NavigationState) => void): void
}

class PermissionCache {
    get(): PermissionSet | null
    fetch(): Promise<{set: PermissionSet, changed: boolean}>
    isDegraded(): boolean
}
```

### Extension Surface

The shell exposes two in-browser JavaScript registries; these are NOT
Python `FactoryProtocolBase` extension points but they fill the same
role for the front-end. Feature bundles import the registries at load
time and call `registerGroup` / `registerEntry` / `registerProvider`.

```typescript
// In a feature bundle (e.g., 9-admin-ui):
import { shell } from "/ui/site-shell/registry.js"

shell.sidebar.registerGroup({
    groupId: "admin",
    label: "Admin",
    requiredPermissions: ["ui.admin.view"]
})

shell.sidebar.registerEntry({
    entryId: "admin.users",
    label: "Users",
    route: "/admin/users",
    requiredPermissions: ["users.read"],
    group: "admin"
})

shell.palette.registerProvider({
    providerId: "admin.search",
    label: "Admin",
    requiredPermissions: ["ui.admin.view"],
    query: async (q) => admin_search(q),
    timeoutMs: 3000
})
```

A built-in fallback group ("Workspace") receives every entry that
declares no `group`.

### Events Emitted

DOM CustomEvents only — see Public API above.

### Events Consumed

The shell listens to `popstate` for browser back/forward, to a global
`pyc-session-401` (any fetch in any page can dispatch it) to surface
the re-auth toast, and to `keydown` for `Ctrl/Cmd + K` and sidebar
keyboard navigation.

## Component Breakdown

All paths rooted at
`source/site/automojo/pychestrate/webservice/webinterface/components/pyc-site-shell/`:

- `pyc-site-shell.ts` — shell Custom Element.
- `sidebar/sidebar-registry.ts` — registry + visibility intersection.
- `sidebar/sidebar-renderer.ts` — DOM rendering, keyboard handling, type-to-jump.
- `palette/palette-registry.ts` — provider registry + query fan-out.
- `palette/palette-dialog.ts` — dialog, focus trap, result rendering.
- `permissions/permission-cache.ts` — fetch + diff + degraded-state tracking.
- `permissions/permission-set.ts` — set operations.
- `routing/shell-router.ts` — path parsing, navigation, focus restoration.
- `chrome/header.ts` — header region (brand, search trigger, user menu).
- `chrome/empty-state.ts` — zero-entry empty-state render.
- `chrome/degraded-banner.ts` — non-blocking degraded-permissions banner.
- `keybindings.ts` — global key handler.
- `styles.css` — multi-line CSS referencing `--pyc-site-shell-*` tokens.
- `tests/`.

Server-side adapter under
`source/site/automojo/pychestrate/webservice/webinterface/site_shell/`:

- `shell_document.py` — Jinja template that emits the shell HTML and
  imports the feature bundles registered for the current route.
- `chromeless_routes.py` — the canonical list of routes that bypass the
  shell document (`/login`, `/logout`, `/setup/*`, `/__health/*`,
  `/errors/{404,403,500}`).
- `bundle_registry.py` — server-side mirror of which feature bundles to
  inject for which route prefix; consumed by `shell_document.py`.

Shell bundle emitted at `/ui/site-shell/pyc-site-shell.js`. Every
non-chromeless server-side route serves the same shell document and
relies on client-side routing to mount the right page Custom Element.

## Key Flows

### Flow 1 — Cold boot, authenticated user with admin role

1. Browser hits `/admin/users` with a valid `pychestrate_session` cookie.
2. Server-side gate passes; `shell_document.py` renders the shell HTML, importing the `pyc-site-shell` bundle plus the bundles registered for `/admin/*`.
3. `pyc-site-shell` mounts, fans out registration calls from each loaded bundle (admin, project-dashboard, run-detail — whichever are bundled).
4. Shell calls `GET /api/v1/me/permissions`, builds `PermissionSet`, intersects against the sidebar registry, renders sidebar + header + main slot.
5. Shell instantiates the page Custom Element for `/admin/users` and emits `pyc-site-shell-ready`.

### Flow 2 — Cold boot, authenticated user with no permissions

1. Boot proceeds identically through step 3.
2. `PermissionSet` is empty; sidebar registry intersection yields zero entries.
3. Shell renders the empty-state panel ("Your account has no access yet — ask an administrator to grant you a role") with header + user menu so the user can still sign out.
4. Shell emits `pyc-site-shell-empty-state-rendered`.

### Flow 3 — Cold boot, unauthenticated visitor

1. Browser hits any non-chromeless route without a session cookie.
2. Server-side gate (per `1-authentication` Requirement 5) responds HTTP 303 to `/login?next=<encoded-original>`.
3. Browser follows; `/login` is chromeless and serves its own minimal document.
4. After login completes, the next navigation lands at `next` (or `/` if `next` failed same-origin validation) and Flow 1 or Flow 2 runs.

### Flow 4 — Full navigation with role change in flight

1. User clicks "Audit Log" in the sidebar.
2. Shell updates URL via `history.pushState`, calls `GET /api/v1/me/permissions`.
3. New payload differs from the cached payload (admin role was just revoked); shell emits `pyc-site-shell-permissions-changed` with the diff.
4. Shell intersects the new payload, removes the "Admin" group from the sidebar in the same render cycle, and renders the 403 page if the now-disallowed `/admin/audit` was the target.

### Flow 5 — Palette query across multiple providers

1. User presses `Ctrl/Cmd + K`; shell opens the palette dialog and focus-traps.
2. User types "kubectl"; shell debounces 150 ms and fans out to every visible provider with a 5 s per-provider timeout.
3. Each provider returns results; shell renders grouped results as they arrive (no head-of-line blocking).
4. User selects a result; shell navigates to `result.route` and closes the palette.

### Flow 6 — Mid-session 401

1. An XHR from the active page returns 401.
2. The page dispatches `pyc-session-401`; shell shows a non-blocking re-auth toast ("Your session expired — sign in again to continue").
3. On the next full navigation the server-side gate redirects to `/login?next=<current>`.

## Error Handling

- **Permissions fetch failure:** retain the previous cached `PermissionSet`, set `degraded = true`, render the non-blocking degraded banner; retry on the next navigation (no automatic background polling).
- **Sidebar registration with malformed `required_permissions` (non-string entries):** drop the entry, emit a `pychestrate.ui.shell.sidebar_dup_route` or `..._malformed_registration` log event, continue.
- **Duplicate route registration:** first registration wins, second is dropped with a log event identifying both labels.
- **Palette provider throws / times out:** render the provider's group with an inline error message ("Admin search unavailable"), continue rendering other providers.
- **Unknown route:** render the chromeless 404 page (no shell), per Requirement 3.
- **Page Custom Element fails to load:** render a chromeless 500 page with the request id for support.

## Security Considerations

- Sidebar visibility is UX only — the authoritative security boundary is the per-route server-side guard owned by each feature.
- The shell never writes the permission payload to `localStorage` or `sessionStorage`; cache is in-memory per document and dies with the tab.
- The shell never logs full permission payloads — only counts (`{count: N}`) and diffs (`{added: [...], removed: [...]}`).
- All XHRs are same-origin with CSRF.
- Palette queries are capped at 128 characters and trimmed before fan-out.
- The user-menu logout flow uses the standard `POST /api/v1/auth/logout` endpoint and follows the server's 303 to `/login`; the shell never crafts its own logout redirect target.
- Sidebar entry labels and icons are rendered as text/SVG-by-name (no innerHTML); feature bundles cannot inject markup into the shell chrome.
- Chromeless routes (`/login`, `/setup/*`, error pages) explicitly do NOT load the shell bundle, so a compromised page Custom Element cannot influence the login surface.

## Observability

Client metrics beaconed:

- `pychestrate_ui_shell_tti_seconds` — histogram.
- `pychestrate_ui_shell_sidebar_render_duration_seconds` — histogram.
- `pychestrate_ui_shell_navigation_duration_seconds` — histogram.
- `pychestrate_ui_shell_permissions_fetch_duration_seconds{outcome}` — histogram.
- `pychestrate_ui_shell_palette_query_duration_seconds{provider, outcome}` — histogram.
- `pychestrate_ui_shell_sidebar_entry_clicked_total{group, route}` — counter.
- `pychestrate_ui_shell_empty_state_total` — counter.
- `pychestrate_ui_shell_permissions_degraded_total` — counter.
- `pychestrate_ui_shell_palette_provider_failures_total{provider, reason}` — counter.

Log events: `pychestrate.ui.shell.rendered`,
`pychestrate.ui.shell.sidebar_entry_clicked`,
`pychestrate.ui.shell.palette_opened`,
`pychestrate.ui.shell.permissions_changed`,
`pychestrate.ui.shell.empty_state_rendered`,
`pychestrate.ui.shell.sidebar_dup_route`,
`pychestrate.ui.shell.degraded`.

Trace spans (server-side at metric ingestion):
`pychestrate.ui.shell.metric_ingest`.

## Open Questions

- Should the user-menu surface include a "Switch tenant" affordance once multi-tenant ships, or should that live in the brand area? Timebox: Phase 10 midpoint.
- Should sidebar collapsed-state per-user persist server-side via a small `user_preferences` table, or remain session-scoped? Defer until `1-user-management` exposes a preferences API.
- Live permission updates over WebSocket (so revocations propagate without a navigation) — interesting but adds a transport dependency we don't otherwise need at Phase 10. Defer to a follow-on once `2-notification-hub` lands.
- Mobile-responsive layout — explicitly deferred; revisit after Phase 10 ships and we have usage telemetry on viewport sizes.
