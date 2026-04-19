# E-extension-config — Requirements

## Introduction

E-extension-config gives every loaded extension a scoped view into
`2-global-variables` (typed variables) and `1-secrets-vault` (secrets)
keyed by `ext.<ext-name>.*`. Extensions never read unscoped config
directly; the host exposes a `ExtensionConfigScope` object whose
accessor methods return only keys under that prefix. This prevents one
extension from reading another's config and keeps operator intent
explicit about which values belong to which extension. This feature
lands in Phase 1 alongside `1-secrets-vault` and `2-global-variables`.

## Requirements

### Requirement 1: Scoped variable access

**User Story:** As an extension author, I want a read-only view into my
extension's scoped variables, so that I can pull configuration without
touching other extensions' values.

**Acceptance Criteria (EARS):**

1. WHEN an extension calls
   `scope.get_variable(name="retry_max", default=5)` THEN the system
   SHALL look up `ext.<ext-name>.retry_max` in `2-global-variables` and
   return the typed value (or the default if absent).
2. IF the extension attempts to read a variable whose key does not
   begin with `ext.<ext-name>.` THEN the system SHALL raise
   `SemanticError` (always bubbles).
3. WHERE the variable resolution chain returns a reference to a secret
   (`$ref:secrets://...`) THEN the system SHALL dereference it only if
   the extension's manifest declares the `read:secrets` capability;
   otherwise it SHALL raise `PermissionError`.

### Requirement 2: Scoped secrets access

**User Story:** As an extension author, I want to request a secret
under my scope by name and receive a decrypted value, so that I can
authenticate to external systems without touching unscoped secrets.

**Acceptance Criteria (EARS):**

1. WHEN an extension calls `scope.get_secret(name="api_key")` THEN the
   system SHALL look up `ext.<ext-name>.api_key` in `1-secrets-vault`
   and return the decrypted value.
2. IF the extension's manifest does not declare `read:secrets` THEN
   the system SHALL raise `PermissionError` without touching the
   vault.
3. WHEN a secret lookup fails (not found, rotation in-progress) THEN
   the system SHALL raise `ConfigurationError` naming the extension
   and the missing key.

### Requirement 3: Scoped write is dispatch-only

**User Story:** As a platform maintainer, I want extensions unable to
mutate config directly, so that every change flows through the
audited admin API.

**Acceptance Criteria (EARS):**

1. WHEN an extension attempts to write a variable via its scope THEN
   the system SHALL raise `SemanticError` (no write surface in the
   scope object).
2. WHERE the extension needs to propose a write THEN the system SHALL
   expose `scope.dispatch_config_change(proposal=...)` which enqueues
   a change proposal on the message bus for operator review.

### Requirement 4: Scope change observability

**User Story:** As a service operator, I want to see when an
extension's scoped config changes, so that I can trace behavior drift
to a config edit.

**Acceptance Criteria (EARS):**

1. WHEN any variable under `ext.<ext-name>.*` changes THEN the system
   SHALL emit `extension.config_changed` with `{ext_name, keys}`.
2. WHILE a config change is being applied the system SHALL continue
   to serve reads from the old value until the applier commits.
3. WHEN a secret under `ext.<ext-name>.*` rotates THEN the system
   SHALL emit `extension.secret_rotated` with `{ext_name, key}`.

## Property-Based Test Requirements

### Property 1: Scope isolation

- **Invariant:** For any two loaded extensions A and B with disjoint
  scoped key sets, A's `scope.get_variable` / `get_secret` calls
  cannot return any value that belongs to B, and vice versa.
- **Generator:** two random scoped key sets with some keys biased to
  near-collide on prefix.
- **Assertion:** For every key in A's set, A's scope returns its
  value; B's scope raises `SemanticError` on the same key.
- **Sample size:** 1000 generated cases.

### Property 2: Capability-gated secret access

- **Invariant:** For any extension without `read:secrets` in its
  manifest, `scope.get_secret(name=any)` always raises
  `PermissionError`; with the capability, access behaves identically to
  the unscoped vault API for keys under its prefix.
- **Generator:** random (capability_list, key) pairs.
- **Assertion:** Outcome matches `"read:secrets" in capabilities`.
- **Sample size:** 1000 generated cases.

### Property 3: Read round-trip stability

- **Invariant:** For any scoped variable value `v` written through
  the admin API and any unchanged state, `scope.get_variable(name=...)`
  returns a deep-equal value across repeated calls.
- **Generator:** random (name, typed value) pairs covering every
  supported type in `2-global-variables`.
- **Assertion:** `get(get()) == v` across N calls; no drift.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Scope read latency < 2 ms P95 for cached
  hits; secret reads < 20 ms P95 including decryption.
- **NFR-2 (Security):** Capability check short-circuits before any
  secret lookup; extensions never receive raw vault handles; scope
  object does not expose `__dict__` containing unscoped data.
- **NFR-3 (Observability):** Metrics
  `pychestrate_extension_config_read_total{ext,kind=variable|secret,result}`,
  `pychestrate_extension_config_permission_denied_total{ext,capability}`;
  log events `pychestrate_extension_config_changed`,
  `pychestrate_extension_secret_rotated`,
  `pychestrate_extension_config_permission_denied`; trace span
  `pychestrate_extension.config.read`.
- **NFR-4 (Reliability):** Scope view survives a
  `variable_resolver`-factory rescan; caches invalidated on
  `extension.config_changed` events.

## Out of Scope

- Variable type system (owned by `2-global-variables`).
- Secret rotation mechanics (owned by `1-secrets-vault`).
- Capability enforcement surface outside config (`E-extension-sandbox`).

## Dependencies

- **Depends on:** `E-extension-host`, `E-extension-manifest`,
  `1-secrets-vault`, `2-global-variables`.
- **Depended on by:** every extension that reads configuration;
  `E-extension-sandbox` reuses the capability-check helper.
- **Extension points exposed:** none directly; re-uses
  `variable_resolver` and `secret_ref_dereferencer` factories via
  `E-factory-protocols`.
