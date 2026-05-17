# 9-admin-ui — Requirements

## Introduction

`9-admin-ui` is the Pychestrate administration surface. It composes
existing WebComponents and REST endpoints into a set of pages — Users/Groups,
Roles/Permissions, Secrets (hosting `9-wc-secret-editor`), Feature Flags,
System Health, Audit Log, Maintenance Mode, and Extensions (hosting
`E-extension-registry-ui`) — mounted as a **section within the unified
site shell** defined by `9-site-shell`. The admin surface is NOT a
standalone application: it does not own login, header chrome, or
top-level navigation. It contributes a sidebar group ("Admin") and a
family of routes under `/admin/*` (NOT `/config/*`), each declaring
the permissions the site shell uses to gate sidebar visibility. The
admin surface owns its in-section affordances — per-page command-palette
contributions, audit-log deep-link toasts, tab-RBAC enforcement —
while every cross-cutting concern (login, sidebar, header, empty
state) is delegated to `9-site-shell`. Ships in **Phase 10** when the
extension registry UI, secret editor, and unified site shell land.
Sits at the top of Layer 9, consuming Layer 1 (identity/auth/secrets),
Layer 0 (system health/maintenance), and Layer E (extension registry).
The admin UI does not own data; every action flows through
`8-rest-api-v1`.

## Requirements

### Requirement 1: RBAC-Driven Navigation and Tab Visibility

**User Story:** As an auditor without admin rights, I should see only the
admin tabs I have permission to view (and the "Admin" sidebar group
should disappear entirely if I hold none of them), so that I do not see
forbidden controls.

**Acceptance Criteria (EARS):**

1. WHEN the admin section mounts under the unified site shell THEN it SHALL declare each admin page to the shell's sidebar registry (see `9-site-shell`) with the page's `required_permissions`; the shell SHALL compute visibility by intersecting those declarations against `GET /api/v1/me/permissions`. The admin surface SHALL NOT fetch `/me/permissions` itself for the purpose of sidebar gating — the shell is authoritative.
2. IF the caller lacks `ui.admin.view` (defined in `1-rbac`) THEN the shell SHALL NOT render the "Admin" sidebar group at all, AND any direct navigation to `/admin/*` SHALL render the shell's standard 403 forbidden state.
3. WHEN the caller holds `ui.admin.view` but lacks a specific admin page's permission THEN the page's sidebar entry SHALL be hidden from the "Admin" group AND direct-URL access to that page SHALL render the shell's standard forbidden state — server-side route guards (existing per-page RBAC enforcement) remain the authoritative security layer; sidebar visibility is UX only.
4. WHERE `maintenance_mode.toggle` is held THEN the Maintenance Mode page SHALL expose a maintenance-mode toggle affordance guarded by a typed-confirm dialog. The site shell's global header is NOT used as the toggle surface — the toggle lives inside the page so it inherits page-level audit + reason capture.

### Requirement 2: Extensions Registry Tab Hosts E-extension-registry-ui

**User Story:** As an operator, I want to view loaded extensions, their
precedence, capabilities, health, and last error, so that I can diagnose
extension issues without SSH.

**Acceptance Criteria (EARS):**

1. WHEN the Extensions tab is opened THEN the UI SHALL embed the `E-extension-registry-ui` component AND populate it from `GET /api/v1/extensions`.
2. WHEN the operator triggers a re-scan via the registry UI THEN the admin shell SHALL call `POST /api/v1/extensions:rescan` AND refresh the registry listing on completion.
3. WHILE a re-scan is in progress THEN the registry UI SHALL show a progress banner AND the shell SHALL disable navigation away from the tab until completion or explicit cancellation.
4. IF a listed extension reports an error THEN the admin UI SHALL surface a deep-link into Audit Log filtered by `entity=extension&entity_id=<id>`.

### Requirement 3: Command Palette and Cross-Tab Deep Linking

**User Story:** As an admin power user, I want admin-specific entries
(users, secrets, flags, extensions, roles) to appear in the unified
site shell's command palette, so that I can jump to any admin target
without mousing.

**Acceptance Criteria (EARS):**

1. WHEN the admin section loads under the site shell THEN it SHALL contribute an admin search provider to the shell's command palette (see `9-site-shell`); the shell — not the admin surface — owns the `Ctrl/Cmd + K` keybinding, the dialog chrome, and focus management.
2. WHEN the user types at least 2 characters AND the palette has admin scope active THEN the contributed provider SHALL query `GET /api/v1/admin/search?q=<q>` AND return grouped results (users, secrets, flags, extensions, roles) to the shell for rendering.
3. WHEN the user selects an admin result THEN the shell SHALL navigate to the corresponding `/admin/<page>/<id>` route AND the admin surface SHALL emit `pyc-admin-ui-navigated` with `{kind, id}`.
4. IF the admin search endpoint is unavailable THEN the contributed provider SHALL fall back to a limited client-side index AND SHALL surface a non-blocking banner inside the palette result group.

### Requirement 4: Audit Log Deep Links on Every Mutation

**User Story:** As an auditor, I want every admin-surface mutation to emit a
visible audit-log entry and let me jump into the audit view from the mutated
entity, so that changes are traceable.

**Acceptance Criteria (EARS):**

1. WHEN a mutation completes on any admin tab THEN the UI SHALL surface an inline toast with `"<Action> succeeded"` AND a link to `GET /audit?entity=<kind>&entity_id=<id>&limit=25`.
2. WHEN the Audit Log tab is opened with a preset filter (via query string) THEN the UI SHALL render the filter pills pre-populated AND immediately query.
3. IF a user action fails with 4xx THEN the toast SHALL display the server's safe error message AND a retry affordance when the action is idempotent.
4. WHERE `audit_log.export` is held THEN the Audit Log tab SHALL expose an "Export selection" action that calls `POST /api/v1/audit/export`.

### Requirement 5: Accessibility

**User Story:** As a keyboard user, I want to navigate the admin pages
fully with the keyboard, so that I do not need a mouse.

**Acceptance Criteria (EARS):**

1. WHEN an admin page mounts inside the site shell THEN its in-page tab strip (where applicable) SHALL expose `role="tablist"` AND each tab SHALL expose `role="tab"` with proper `aria-selected`. The site shell owns sidebar a11y (arrow-key navigation, type-to-jump) and is not redeclared here.
2. WHEN the user presses `Tab` inside an admin page THEN focus SHALL traverse the page's tablist (if any), then the active tabpanel, in a predictable order.
3. WHEN the shell's palette opens with admin results focused THEN focus SHALL be trapped inside the dialog until dismissed (delegated to the shell).
4. IF a mutation completes THEN the toast SHALL land in a visually-hidden live region for screen readers; the live region MAY be the shell's shared one or a page-local one, but it SHALL be `aria-live="polite"`.

## Property-Based Test Requirements

### Property 1: Tab Visibility Is a Pure Function of Permissions

- **Invariant:** For any permission set P, the visible tab list equals a deterministic intersection of declared tab requirements with P; permuting P has no effect.
- **Generator:** Random permission sets drawn from the declared permission catalog.
- **Assertion:** `visibleTabs(P) == visibleTabs(permutation(P))`.
- **Sample size:** 1000 generated cases

### Property 2: Palette Results Respect Permission Scoping

- **Invariant:** For any search query, the palette results returned to the user never include entities the caller is not permitted to see.
- **Generator:** Random users with random permission subsets; random queries against a fixed entity catalog.
- **Assertion:** Every returned id is in the user's server-computed visible set.
- **Sample size:** 1000 generated cases

### Property 3: Toast/Audit Linkage Is Consistent

- **Invariant:** For any mutation recorded as `entity=<kind>&entity_id=<id>`, the toast's audit link query string is identical to the one the Audit Log tab would apply.
- **Generator:** Random mutation events.
- **Assertion:** Toast URL equals a canonical builder applied to `(kind, id)`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Shell TTI p95 < 400 ms with permission cache warm. Tab switch p95 < 150 ms. Palette open-to-first-keystroke-render p95 < 80 ms. Palette query p95 < 200 ms server-side.
- **NFR-2 (Security):** Same-origin REST, CSRF. All tabs gated by server-enforced RBAC in addition to client hide. Mutation flows always require confirmation and reason strings where the downstream component demands it (e.g., `9-wc-secret-editor`). The UI never caches sensitive payloads. Maintenance-mode toggle requires typed-confirm.
- **NFR-3 (Observability):** Client metrics beaconed: `pychestrate_ui_admin_tti_seconds` (histogram), `pychestrate_ui_admin_tab_switch_duration_seconds{from, to}` (histogram), `pychestrate_ui_admin_palette_query_duration_seconds` (histogram), `pychestrate_ui_admin_mutation_total{tab, kind, outcome}` (counter), `pychestrate_ui_admin_extension_rescan_total{outcome}` (counter). Log events `pychestrate.ui.admin.tab_switched`, `pychestrate.ui.admin.mutation`, `pychestrate.ui.admin.rescan`, `pychestrate.ui.admin.palette_opened`.
- **NFR-4 (Reliability):** A failed permission fetch SHALL render the shell in a degraded read-only state until recovered. A failed extensions re-scan SHALL not leave the UI stuck — the progress banner SHALL time out after 60 s and expose a retry.

## Out of Scope

- Secret creation (see a future `9-wc-secret-create`).
- Project-level admin (covered by project settings UI outside this shell).
- Agent upgrade rollouts (see `3-agent-upgrade-channel` dedicated tab which may be added in a later phase).

## Dependencies

- **Depends on:** `9-site-shell` (owns login, sidebar, header chrome, palette, empty-state), `9-ui-design-tokens`, `1-authentication`, `1-user-management`, `1-rbac` (contributes `ui.admin.view`), `1-secrets-vault`, `1-audit-log`, `1-feature-flags`, `0-maintenance-mode`, `0-system-health`, `E-extension-host`, `E-extension-registry-ui`, `9-wc-secret-editor`, `8-rest-api-v1`.
- **Depended on by:** operators and administrators.
- **Extension points exposed:** None directly; hosts `E-extension-registry-ui` which exposes extension-registry actions.
