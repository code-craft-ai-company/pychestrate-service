# 9-admin-ui — Design

## Architecture

`9-admin-ui` is a family of pages mounted under `/admin/*` (NOT
`/config/*`) inside the unified site shell defined by `9-site-shell`.
Each admin page is a Custom Element that consumes existing
Layer-1/Layer-0 REST surfaces and, where relevant, embeds a
single-purpose `9-wc-*` element (e.g., `9-wc-secret-editor`). Routing,
header chrome, sidebar gating, command-palette dispatch, login
redirection, and the no-access empty state are owned by `9-site-shell`;
this feature only contributes (a) the per-page Custom Elements, (b) a
single sidebar group ("Admin") declaration registered with the shell's
sidebar registry, and (c) an admin search provider plugged into the
shell's command palette. Permission state is fetched and cached by the
shell on every full navigation; pages read it via the shell's
`PermissionSet` accessor — they do NOT fetch `/me/permissions`
themselves. The Extensions page embeds `E-extension-registry-ui`'s
Custom Element and delegates to it. Ships in **Phase 10** when the
unified site shell, secrets management, extension-registry UI, and
maintenance-mode toggle all land.

## Data Model

No persistent entities. Runtime state:

- `AdminSession` — `{actorId: string, permissions: Set<string>, tabs: TabDescriptor[], defaultTab: TabId}`.
- `TabDescriptor` — `{tabId: TabId, label: string, icon: string, requiredPerms: string[], componentTag: string}`.
- `PaletteIndex` — `{entities: PaletteEntity[], builtAt: string, partial: boolean}` (client-side fallback cache).
- `Toast` — `{kind: "success"|"error", message: string, auditHref: string | null, idempotencyKey: string | null}`.
- `RescanState` — `{inFlight: boolean, startedAt: string | null, message: string, timeoutAt: string | null}`.

## Interfaces

### Public API

**Tag name:** `<pyc-admin-ui>`

**Observed attributes:**

- `default-tab` (string) — override the default landing tab.
- `disable-palette` (boolean attribute) — disable the command palette.
- `rescan-timeout-seconds` (string; integer; default `60`).
- `aria-label` (string).

**Properties (JS):**

- `session: AdminSession | null`
- `activeTabId: TabId`
- `navigateTo(tabId: TabId, entityId?: string): void`
- `openPalette(): void`
- `closePalette(): void`
- `reloadPermissions(): Promise<void>`

**Events (bubbling, composed):**

- `pyc-admin-ui-ready` — `{visibleTabs, defaultTab}`.
- `pyc-admin-ui-tab-switched` — `{from, to}`.
- `pyc-admin-ui-navigated` — `{kind, id}`.
- `pyc-admin-ui-mutation` — `{tab, entityKind, entityId, kind, outcome}`.
- `pyc-admin-ui-rescan` — `{outcome, durationMs}`.

**Slots:**

- `slot="brand"` — consumer-supplied brand/logo.
- `slot="header-right"` — consumer-supplied header content.
- `slot="footer"`.
- `slot="forbidden"` — empty state when no tabs are visible.

**CSS custom properties respected:**

- `--pyc-admin-ui-bg` → `var(--pyc-color-app-bg)`
- `--pyc-admin-ui-nav-bg` → `var(--pyc-color-surface-elevated)`
- `--pyc-admin-ui-nav-fg` → `var(--pyc-color-on-surface-elevated)`
- `--pyc-admin-ui-nav-fg-active` → `var(--pyc-color-accent-on-surface)`
- `--pyc-admin-ui-toast-success-bg`, `--pyc-admin-ui-toast-error-bg`
- `--pyc-admin-ui-palette-bg` → `var(--pyc-color-surface-elevated)`
- `--pyc-admin-ui-palette-input-bg` → `var(--pyc-color-input-bg)`
- `--pyc-admin-ui-focus-ring` → `var(--pyc-focus-ring)`
- `--pyc-admin-ui-font-family` → `var(--pyc-font-family-ui)`

**A11y requirements:**

- Tab bar: `role="tablist"`. Each tab: `role="tab"`, `aria-selected`, `aria-controls="<panel-id>"`.
- Each tab panel: `role="tabpanel"`, `aria-labelledby="<tab-id>"`.
- Palette: `role="dialog"` with `aria-modal="true"`, focus trapped, first focus on the search input.
- Toast: live region `aria-live="polite"`.
- Keyboard: `ArrowLeft`/`ArrowRight` to move between tabs, `Home`/`End` jump, `Ctrl/Cmd+K` palette, `Esc` close palette, `Tab` traverses within panel.

Server REST surfaces consumed:

- `GET /api/v1/me/permissions`.
- `GET /api/v1/admin/search?q=<q>`.
- `GET /api/v1/extensions` + `POST /api/v1/extensions:rescan`.
- Per-tab: `/api/v1/users`, `/api/v1/groups`, `/api/v1/roles`, `/api/v1/secrets`, `/api/v1/feature_flags`, `/api/v1/audit`, `/api/v1/system_health`, `/api/v1/maintenance_mode`.

### Internal API

```typescript
class PermissionSet {
    has(perm: string): boolean
    hasAll(perms: string[]): boolean
}

class TabRegistry {
    declare(desc: TabDescriptor): void
    visibleTabs(perms: PermissionSet): TabDescriptor[]
}

class AdminRouter {
    parse(hash: string): RouteSnapshot
    push(tabId: TabId, entityId?: string): void
    onChange(cb: (s: RouteSnapshot) => void): void
}

class CommandPalette {
    open(): void
    close(): void
    query(q: string): Promise<PaletteResults>
}
```

### Extension Surface

None declared here. `E-extension-registry-ui` is embedded as an already-declared
component exposing its own events; this shell simply listens for its
`pyc-extension-registry-rescan-request` and forwards to the REST API.

### Events Emitted

DOM CustomEvents only.

### Events Consumed

Events from embedded tab components (e.g., `pyc-secret-editor-saved`,
`pyc-extension-registry-rescan-request`). Each is translated to a toast and
metric.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/webinterface/components/pyc-admin-ui/`:

- `pyc-admin-ui.ts` — shell Custom Element.
- `tabs/pyc-admin-tab-users.ts` — users + groups.
- `tabs/pyc-admin-tab-roles.ts` — roles + permissions.
- `tabs/pyc-admin-tab-secrets.ts` — list + host `<pyc-secret-editor>`.
- `tabs/pyc-admin-tab-feature-flags.ts`.
- `tabs/pyc-admin-tab-system-health.ts`.
- `tabs/pyc-admin-tab-audit-log.ts`.
- `tabs/pyc-admin-tab-maintenance.ts`.
- `tabs/pyc-admin-tab-extensions.ts` — hosts `<pyc-extension-registry>`.
- `permission-set.ts`.
- `tab-registry.ts`.
- `admin-router.ts`.
- `palette.ts`.
- `toast.ts`.
- `keybindings.ts`.
- `styles.css` — multi-line CSS referencing `--pyc-admin-ui-*` tokens.
- `tests/`.

Bundle emitted at `/ui/components/pyc-admin-ui/pyc-admin-ui.js`. The
admin pages are mounted under `/admin/*` (NOT `/config/*`) and the
server-side route family (`/admin`, `/admin/users`, `/admin/roles`,
`/admin/secrets`, `/admin/feature-flags`, `/admin/system-health`,
`/admin/audit`, `/admin/maintenance`, `/admin/extensions`) all serve
the unified site shell document from `9-site-shell` with the
appropriate admin page Custom Element wired in. The legacy `/config/*`
routes are explicitly retired.

### Sidebar Registration

At bundle load, the admin surface registers a single sidebar group with
the site shell's registry (see `9-site-shell` for the registry shape):

```typescript
shell.sidebar.registerGroup({
    groupId: "admin",
    label: "Admin",
    icon: "shield",
    requiredPermissions: ["ui.admin.view"],
    entries: [
        {label: "Users",         route: "/admin/users",         requiredPermissions: ["users.read"]},
        {label: "Roles",         route: "/admin/roles",         requiredPermissions: ["rbac.read"]},
        {label: "Secrets",       route: "/admin/secrets",       requiredPermissions: ["secrets.read"]},
        {label: "Feature Flags", route: "/admin/feature-flags", requiredPermissions: ["feature_flags.read"]},
        {label: "System Health", route: "/admin/system-health", requiredPermissions: ["system_health.read"]},
        {label: "Audit Log",     route: "/admin/audit",         requiredPermissions: ["audit_log.view"]},
        {label: "Maintenance",   route: "/admin/maintenance",   requiredPermissions: ["maintenance_mode.view"]},
        {label: "Extensions",    route: "/admin/extensions",    requiredPermissions: ["extensions.read"]}
    ]
});
```

The shell intersects each entry's `requiredPermissions` against the
live permission payload to decide what to render; the group itself is
hidden entirely if the caller lacks `ui.admin.view`.

## Key Flows

### Flow 1 — Boot

1. The site shell handles login and mounts a chrome with header + sidebar; it fetches `GET /api/v1/me/permissions` once per navigation and computes the visible sidebar set, including the "Admin" group declared by this surface.
2. On a navigation to any `/admin/*` route, the shell instantiates the corresponding admin page Custom Element inside its main content area and passes the shared `PermissionSet`.
3. The page reads its scoped permissions from the shell, renders its in-page tablist (when applicable), and emits `pyc-admin-ui-ready`.

### Flow 2 — Edit a secret

1. User opens Secrets via the sidebar; the shell navigates to `/admin/secrets`; the page renders the list.
2. User clicks a secret; the shell navigates to `/admin/secrets/<id>`; the page mounts `<pyc-secret-editor secret-id="<id>">`.
3. User edits metadata and saves; `pyc-secret-editor-saved` fires.
4. The page translates the event into a toast with audit deep-link; emits `pyc-admin-ui-mutation`.

### Flow 3 — Palette navigation

1. User presses `Ctrl/Cmd+K`; the site shell opens the palette dialog and focus-traps on the input.
2. Each keystroke (after 150 ms debounce) fans out to registered providers; this surface's admin provider calls `/api/v1/admin/search?q=...`.
3. Grouped results render; user navigates via arrows; `Enter` activates.
4. The shell navigates to `/admin/<page>/<entityId>` and closes the palette.

### Flow 4 — Extensions rescan

1. Extensions tab hosts `<pyc-extension-registry>`.
2. User clicks Rescan; registry emits `pyc-extension-registry-rescan-request`.
3. Shell POSTs `/api/v1/extensions:rescan` and sets `RescanState.inFlight=true` with a timeout.
4. On response or timeout, shell refreshes registry data and emits `pyc-admin-ui-rescan`.

## Error Handling

- Permissions fetch failure: shell renders a degraded "permissions unavailable" banner; tabs are disabled; retry affordance every 15 s.
- Tab-level failures surface through per-tab error slots; shell never swallows child-tab errors.
- Palette endpoint failure: fall back to client-side partial index; surface non-blocking banner.
- Rescan timeout: surface retry; avoid locking the UI past `rescan-timeout-seconds`.
- 403 on tab data fetch: render forbidden state in the tabpanel and log metric.

## Security Considerations

- All REST calls same-origin with CSRF.
- Permissions drive client visibility, but the server remains authoritative.
- Palette queries debounced and capped at 128 characters.
- Maintenance-mode toggle requires typed-confirm and an `audit_log` reason string.
- The shell never stores session data in `localStorage`.

## Observability

Client metrics beaconed:

- `pychestrate_ui_admin_tti_seconds` — histogram.
- `pychestrate_ui_admin_tab_switch_duration_seconds{from, to}` — histogram.
- `pychestrate_ui_admin_palette_query_duration_seconds` — histogram.
- `pychestrate_ui_admin_mutation_total{tab, kind, outcome}` — counter.
- `pychestrate_ui_admin_extension_rescan_total{outcome}` — counter.
- `pychestrate_ui_admin_permission_fetch_fail_total` — counter.

Log events: `pychestrate.ui.admin.tab_switched`, `pychestrate.ui.admin.mutation`, `pychestrate.ui.admin.rescan`, `pychestrate.ui.admin.palette_opened`, `pychestrate.ui.admin.permission_fetch_fail`.

Trace spans (server-side at ingestion): `pychestrate.ui.admin.metric_ingest`.

## Open Questions

- Should per-tab state (pagination cursors) persist in URL hash or sessionStorage? Timebox: Phase 10 midpoint.
- Palette grouping and relevance scoring: server-side ranking or strictly lexical? Timebox: Phase 10 kickoff.
- Multi-tenant admin: does the shell surface a tenant switcher in the header? Timebox: Phase 10 exit.
