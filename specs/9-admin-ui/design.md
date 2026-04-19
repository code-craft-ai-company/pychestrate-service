# 9-admin-ui — Design

## Architecture

`9-admin-ui` is a composition shell implemented as a parent Custom Element
`<pyc-admin-ui>` that hosts a deterministic set of tab panels. Each tab is
itself a Custom Element that consumes existing Layer-1/Layer-0 REST surfaces
and, where relevant, embeds a single-purpose `9-wc-*` element (e.g.,
`9-wc-secret-editor`). Routing is handled via a lightweight hash router
owned by the shell; browser history is respected. Permission state is
fetched once at mount and cached per-session; tab visibility and in-tab
affordances are a pure function of that state. The Extensions tab embeds
`E-extension-registry-ui`'s Custom Element and delegates to it. Ships in
**Phase 10** when secrets management, extension-registry UI, and
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

Bundle emitted at `/ui/components/pyc-admin-ui/pyc-admin-ui.js`. The admin page server-side route is `GET /admin` which serves the document shell importing the bundle.

## Key Flows

### Flow 1 — Boot

1. `pyc-admin-ui` mounts, loads design tokens, fetches `GET /me/permissions`.
2. `TabRegistry.visibleTabs(perms)` determines navigation.
3. Router parses `location.hash`; activates default or hash-specified tab.
4. Element emits `pyc-admin-ui-ready`.

### Flow 2 — Edit a secret

1. User opens Secrets tab; list renders; user clicks a secret.
2. Router pushes `#secrets/<id>`; tab mounts `<pyc-secret-editor secret-id="<id>">`.
3. User edits metadata and saves; `pyc-secret-editor-saved` fires.
4. Shell translates the event into a toast with audit deep-link; emits `pyc-admin-ui-mutation`.

### Flow 3 — Palette navigation

1. User presses `Ctrl/Cmd+K`; palette dialog opens; focus traps on the input.
2. Each keystroke (after 150 ms debounce) calls `/api/v1/admin/search?q=...`.
3. Grouped results render; user navigates via arrows; `Enter` activates.
4. Shell navigates to `(tab, entityId)` and closes palette.

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
