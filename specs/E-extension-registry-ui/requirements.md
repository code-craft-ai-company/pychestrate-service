# E-extension-registry-ui — Requirements

## Introduction

E-extension-registry-ui is the admin-facing page under `9-admin-ui`
that lists every loaded extension with its name, version, declared
protocols, declared resource kinds, precedence, granted capabilities,
current health, last error, and call/delivery counters. It exposes the
rescan, grant/revoke, and quarantine actions as buttons. It ships in
Phase 10 alongside `9-admin-ui`, `E-extension-pack-template`, and
`E-extension-docs` once the Layer E surface is wide enough that
operators need a real view.

## Requirements

### Requirement 1: Listing page

**User Story:** As a service operator, I want to see every loaded
extension at a glance, sorted by health status, so that I can find and
act on problems quickly.

**Acceptance Criteria (EARS):**

1. WHEN an operator with `extensions.read` loads
   `/admin/extensions` THEN the system SHALL render a table of
   `(name, version, state, precedence_count, protocols_count,
   kinds_count, capabilities_count, last_error_at)`.
2. IF the operator applies a filter chip (`unhealthy`, `quarantined`,
   `schema_ahead`) THEN the system SHALL restrict the rows
   accordingly.
3. WHILE the page is open the system SHALL update row fields via a
   bus-driven WebSocket every `pychestrate_extension.ui_refresh_seconds`
   (default 5 s).

### Requirement 2: Detail page

**User Story:** As a service operator, I want to drill into an
extension to see its manifest, capabilities, subscriptions, recent
call failures, and schema-version posture, so that I can decide to
grant, revoke, quarantine, or uninstall.

**Acceptance Criteria (EARS):**

1. WHEN an operator navigates to `/admin/extensions/{name}` THEN the
   system SHALL render panels for manifest, capabilities,
   precedence pins affecting this ext, active subscriptions, lifecycle
   history, and recent `extension.call_failed` rows.
2. WHERE the operator has `extensions.grant` the page SHALL render
   grant/revoke buttons per vocabulary item.
3. WHERE the operator has `extensions.quarantine` the page SHALL
   render quarantine and unquarantine actions.

### Requirement 3: Live actions trigger audit + bus

**User Story:** As a service auditor, I want every page-initiated
action (rescan, grant, revoke, quarantine) routed through the existing
REST endpoints, so that audit log entries and bus events fire the same
way as CLI actions.

**Acceptance Criteria (EARS):**

1. WHEN an operator clicks a button on the page THEN the system
   SHALL POST to the existing REST endpoint with the operator's
   auth; the page itself performs no privileged bypass.
2. IF the operator lacks the required permission THEN the system
   SHALL hide or disable the button — never 500 on click.
3. WHILE an action is in-flight the system SHALL show an in-place
   spinner with the resulting event id once bus echo returns.

### Requirement 4: WebComponent reuse

**User Story:** As a UI maintainer, I want the registry views built
from reusable WebComponents, so that external portals can embed them
via `8-embeddable-views`.

**Acceptance Criteria (EARS):**

1. WHEN the page renders THEN the system SHALL use
   `<pychestrate-extension-list>` and
   `<pychestrate-extension-detail>` custom elements, themed via
   CSS custom properties from `9-ui-design-tokens`.
2. WHERE the consuming portal calls
   `<pychestrate-extension-detail name="...">` THEN the component
   SHALL fetch detail via the REST endpoint and render without the
   outer admin chrome.

## Property-Based Test Requirements

### Property 1: Filter/sort closure

- **Invariant:** For any set of listed extensions, applying a filter
  chip followed by clearing it returns the view to the original row
  set (modulo sort).
- **Generator:** random fleets of extension rows with various
  state/capability combinations.
- **Assertion:** Set equality on the resulting row ids after
  filter→clear.
- **Sample size:** 1000 generated cases.

### Property 2: Row data consistency

- **Invariant:** For any bus event modifying an extension's state
  (e.g., `extension.call_failed`, `extension.quarantined`), the
  page's observed row reflects the change within one refresh interval
  and matches the REST snapshot.
- **Generator:** sequences of state-change events.
- **Assertion:** UI row ≡ REST detail after one refresh tick.
- **Sample size:** 1000 generated cases.

### Property 3: Authorization hiding correctness

- **Invariant:** For any operator role missing a permission, the
  corresponding UI action is absent or disabled; POSTing the same
  action through the browser devtools returns 403 not 500.
- **Generator:** random permission bitmasks.
- **Assertion:** Button presence/absence matches permission set;
  attempted POST returns 403.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Listing page renders under 500 ms P95 for
  up to 500 loaded extensions; detail page under 300 ms P95.
- **NFR-2 (Security):** Views gated by `extensions.read`; action
  buttons gated by their specific permissions; all POSTs reuse the
  existing audited endpoints.
- **NFR-3 (Observability):** Metrics
  `pychestrate_extension_ui_view_total{page}`,
  `pychestrate_extension_ui_action_total{action,result}`; log
  events `pychestrate_extension_ui_action_requested`,
  `pychestrate_extension_ui_action_completed`; trace span
  `pychestrate_extension.ui.render`.
- **NFR-4 (Reliability):** WebSocket fallback to polling after three
  consecutive connection errors; no action lost on WS disconnect.

## Out of Scope

- The REST endpoints themselves (owned by their feature: host,
  lifecycle, sandbox, manifest).
- Theme customization (`9-ui-design-tokens`).
- External portal embed auth (`8-embeddable-views`).

## Dependencies

- **Depends on:** `9-admin-ui`, `9-ui-design-tokens`,
  `E-extension-host`, `E-extension-manifest`,
  `E-extension-lifecycle`, `E-extension-hooks`,
  `E-extension-sandbox`, `E-extension-compat-check`, `1-rbac`,
  `1-audit-log`.
- **Depended on by:** none directly; it is the operator surface for
  the Layer E fleet.
- **Extension points exposed:** `ExtensionDetailPanelExtension`
  (resource extension allowing third parties to add custom panels to
  the detail page, such as a driver-specific health panel).
