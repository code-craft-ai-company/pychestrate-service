# 9-ui-design-tokens — Requirements

## Introduction

`9-ui-design-tokens` is the shared CSS custom-property theme layer that every
Pychestrate WebComponent in Layer 9 consumes for colors, spacing, typography,
radii, elevations, motion, and focus semantics. It defines the canonical token
namespace (`--pyc-*`), ships a default light pack and a default dark pack,
exposes a static dispatcher that serves token CSS under a stable URL, and
registers the `DesignTokenPackExtension` resource so extensions (or per-tenant
white-label packs) can override tokens without forking Pychestrate. It ships in
**Phase 5** as the foundation of the first WebComponents slice alongside
`9-wc-log-stream`, `9-wc-result-viewer`, and `9-run-detail-ui`. Sits between
`0-web-app-host` (static serving) and every `9-wc-*` component (consumer).
Tokens are the single source of truth for visual theming; components NEVER
hard-code color, spacing, or radius values.

## Requirements

### Requirement 1: Canonical Token Namespace and Default Packs

**User Story:** As a UI developer building any `9-wc-*` component, I want a
stable set of named CSS custom properties to read from, so that I can theme my
component correctly without inventing my own token names.

**Acceptance Criteria (EARS):**

1. WHEN the service serves the document shell THEN the system SHALL inline or link a stylesheet defining the token namespace `--pyc-color-*`, `--pyc-space-*`, `--pyc-font-*`, `--pyc-radius-*`, `--pyc-elevation-*`, `--pyc-motion-*`, `--pyc-focus-*` on `:root`.
2. IF the active pack id is `pychestrate.default.light` THEN the system SHALL emit the light palette on `:root` AND SHALL emit the dark palette under `@media (prefers-color-scheme: dark)` unless overridden.
3. WHILE a page is loaded AND the user toggles `data-pyc-theme="dark"` on the document element THEN the system SHALL resolve tokens to the dark palette without a page reload.
4. WHERE a WebComponent attaches a shadow root AND references a token via `var(--pyc-color-surface)` THEN the token SHALL resolve because custom properties inherit through shadow DOM.

### Requirement 2: DesignTokenPackExtension Override Chain

**User Story:** As a tenant operator, I want to install a white-label token
pack via `pychestrate-ext-<tenant>-theme`, so that my deployment uses tenant
brand colors without editing Pychestrate source.

**Acceptance Criteria (EARS):**

1. WHEN the extension host loads a `DesignTokenPackExtension` subclass THEN the system SHALL register its `pack_id`, `PRECEDENCE`, and generated CSS under `/ui/design-tokens/packs/<pack_id>.css`.
2. IF two packs declare the same `pack_id` THEN the system SHALL raise `ConfigurationError` with a multiline message naming both source extensions.
3. WHEN a request arrives for `/ui/design-tokens/active.css` AND the caller has selected pack `<pack_id>` via query string or cookie `pyc_token_pack` THEN the system SHALL serve the resolved cascade: default base pack, then any `PRECEDENCE`-ordered inheriting packs, terminated by the selected pack.
4. WHERE a pack declares `inherits_from: "pychestrate.default.light"` THEN the system SHALL emit the base pack's declarations before the overriding pack's declarations so overrides win by cascade order.

### Requirement 3: Multi-Line CSS Output Conformance

**User Story:** As a reviewer diffing generated token CSS, I want each
declaration on its own line, so that I can read, review, and blame token
changes in source control.

**Acceptance Criteria (EARS):**

1. WHEN the dispatcher serializes a pack THEN every CSS rule SHALL have its opening brace on the same line as the selector, each declaration on its own line indented four spaces, and the closing brace on its own line.
2. IF minification is requested via query `?min=1` THEN the system SHALL serve a minified variant under a separate URL AND SHALL NOT alter the canonical multi-line form served at `/ui/design-tokens/active.css`.
3. WHEN a token pack file is loaded from disk THEN the system SHALL refuse (raise `ConfigurationError`) to serve a pack whose source file collapses multiple declarations onto a single line.

### Requirement 4: Reload-Safe Pack Switching

**User Story:** As an operator running the admin extension reload, I want token
packs to update without restarting the process, so that tenant theme changes
take effect immediately.

**Acceptance Criteria (EARS):**

1. WHEN the bus publishes `extension.reloaded` THEN the system SHALL rebuild the active pack cascade AND invalidate the pack ETag cache.
2. IF a pack file is missing or its parent pack is not registered after reload THEN the system SHALL fall back to `pychestrate.default.light` AND emit a `pychestrate.ui.design_tokens.pack_missing` log event.
3. WHILE a reload is in progress the system SHALL continue serving the previously active pack until the new cascade is built, then swap atomically.

## Property-Based Test Requirements

### Property 1: Token Resolution Is Idempotent Across Repeated Reads

- **Invariant:** For any token name `t` drawn from the declared namespace and any active pack `p`, `resolve(t, p)` returns the same value on every call within a cache generation.
- **Generator:** `hypothesis.strategies.sampled_from(declared_token_names)` combined with `sampled_from(registered_pack_ids)`; tokens generated across 64 declared names.
- **Assertion:** `resolve(t, p) == resolve(t, p)` for all 1000 pairs AND no call raises.
- **Sample size:** 1000 generated cases

### Property 2: Cascade Ordering Is Stable Under PRECEDENCE Permutation

- **Invariant:** For any set of token packs `P = {p0, p1, ..., pN}` with distinct `PRECEDENCE` values, the CSS emitted for the cascade places the lowest-`PRECEDENCE` pack first and the selected pack last, regardless of registration order.
- **Generator:** Synthesize between 2 and 8 packs with random `PRECEDENCE` integers in `[0, 1000]`, random permutation of registration order, random choice of selected pack.
- **Assertion:** The concatenated output bytes are byte-for-byte identical to the expected ordered concatenation.
- **Sample size:** 1000 generated cases

### Property 3: Every Declared Token Has a Default Pack Value

- **Invariant:** For any name in the canonical token namespace manifest, the default light pack emits a declaration for it.
- **Generator:** Token names drawn from the published manifest.
- **Assertion:** `default_light_pack_css` contains `<name>:` for every manifest entry.
- **Sample size:** 1000 generated cases (with repetition to cover manifest churn)

## Non-Functional Requirements

- **NFR-1 (Performance):** Active pack CSS served from cache p99 < 5 ms. Cascade rebuild on `extension.reloaded` completes < 200 ms for up to 16 registered packs. First-paint token CSS gzipped < 12 KiB for the default pack.
- **NFR-2 (Security):** Pack CSS is served with `Content-Type: text/css; charset=utf-8` and `Cache-Control: public, max-age=300, must-revalidate`. No pack may emit `@import` of a remote origin; imports to other local packs only. Tenant pack URLs never contain user-supplied path segments beyond the registered `pack_id`.
- **NFR-3 (Observability):** Metrics `pychestrate_ui_design_tokens_pack_served_total{pack_id}` (counter), `pychestrate_ui_design_tokens_cascade_rebuild_duration_seconds` (histogram), `pychestrate_ui_design_tokens_pack_missing_total{pack_id}` (counter). Log events `pychestrate.ui.design_tokens.pack_registered`, `pychestrate.ui.design_tokens.pack_served`, `pychestrate.ui.design_tokens.pack_missing`, `pychestrate.ui.design_tokens.cascade_rebuilt`. Trace spans `pychestrate.ui.design_tokens.serve`, `pychestrate.ui.design_tokens.rebuild`.
- **NFR-4 (Reliability):** A malformed pack SHALL be quarantined (not registered) without taking down the dispatcher. The base default pack SHALL be guaranteed to register even when zero extension packs are installed.

## Out of Scope

- Component-level theming beyond CSS custom properties (see each `9-wc-*` spec).
- Runtime design-token authoring UIs (operators edit source or ship a pack).
- Icon / glyph themes (see a future `9-wc-iconography` feature).
- Per-user color customization stored in a database.

## Dependencies

- **Depends on:** `0-web-app-host`, `E-extension-host`, `E-extension-lifecycle`, `E-extension-precedence`.
- **Depended on by:** every `9-wc-*` component, `9-admin-ui`, `9-project-dashboard-ui`, `9-run-detail-ui`.
- **Extension points exposed:** `resource: DesignTokenPackExtension` — white-label / per-tenant token overrides.
