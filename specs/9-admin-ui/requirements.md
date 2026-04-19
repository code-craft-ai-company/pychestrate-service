# 9-admin-ui — Requirements

## Introduction

`9-admin-ui` is the Pychestrate administration surface. It composes
existing WebComponents and REST endpoints into a navigable application with
tabs for Users/Groups, Roles/Permissions, Secrets (hosting
`9-wc-secret-editor`), Feature Flags, System Health, Audit Log, Maintenance
Mode, and Extensions (hosting `E-extension-registry-ui`). The admin surface
itself is a composition shell — it owns navigation, breadcrumbs, a global
command palette, and the RBAC-driven tab visibility logic. Ships in
**Phase 10** when the extension registry UI and secret editor land. Sits at
the top of Layer 9, consuming Layer 1 (identity/auth/secrets), Layer 0
(system health/maintenance), and Layer E (extension registry). The admin UI
does not own data; every action flows through `8-rest-api-v1`.

## Requirements

### Requirement 1: RBAC-Driven Navigation and Tab Visibility

**User Story:** As an auditor without admin rights, I should see only the
tabs I have permission to view, so that I do not see forbidden controls.

**Acceptance Criteria (EARS):**

1. WHEN the admin UI mounts THEN it SHALL call `GET /api/v1/me/permissions` AND compute the visible tab set by intersecting declared tab requirements against granted permissions.
2. IF the caller lacks every permission in the computed set THEN the UI SHALL render a "no admin access" empty state AND SHALL NOT expose any tab.
3. WHEN the caller lacks a specific tab's permission THEN the tab SHALL be hidden from navigation AND direct-URL access SHALL render a "forbidden" state.
4. WHERE `maintenance_mode.toggle` is held THEN the global header SHALL expose a maintenance-mode toggle affordance guarded by a typed-confirm dialog.

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

**User Story:** As an admin power user, I want a keyboard-invoked palette
that lets me jump to any admin target (user, secret, flag, extension, role),
so that I can navigate without mousing.

**Acceptance Criteria (EARS):**

1. WHEN the user presses `Ctrl/Cmd + K` THEN the UI SHALL open a command palette dialog with `role="dialog"` AND focus the search input.
2. WHEN the user types at least 2 characters THEN the UI SHALL query `GET /api/v1/admin/search?q=<q>` AND render grouped results (users, secrets, flags, extensions, roles).
3. WHEN the user selects a result THEN the UI SHALL navigate to the tab and entity context AND emit `pyc-admin-ui-navigated` with `{kind, id}`.
4. IF the search endpoint is unavailable THEN the palette SHALL fall back to client-side filtering over a limited cached index AND SHALL surface a non-blocking banner.

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

**User Story:** As a keyboard user, I want to navigate the admin UI fully
with the keyboard, so that I do not need a mouse.

**Acceptance Criteria (EARS):**

1. WHEN the UI mounts THEN the tab bar SHALL expose `role="tablist"` AND each tab SHALL expose `role="tab"` with proper `aria-selected`.
2. WHEN the user presses `Tab` THEN focus SHALL traverse the header, tablist, then the active tabpanel in a predictable order.
3. WHEN the palette opens THEN focus SHALL be trapped inside the dialog until dismissed.
4. IF a mutation completes THEN the toast SHALL land in a visually-hidden live region for screen readers.

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

- **Depends on:** `9-ui-design-tokens`, `1-authentication`, `1-user-management`, `1-rbac`, `1-secrets-vault`, `1-audit-log`, `1-feature-flags`, `0-maintenance-mode`, `0-system-health`, `E-extension-host`, `E-extension-registry-ui`, `9-wc-secret-editor`, `8-rest-api-v1`.
- **Depended on by:** operators and administrators.
- **Extension points exposed:** None directly; hosts `E-extension-registry-ui` which exposes extension-registry actions.
