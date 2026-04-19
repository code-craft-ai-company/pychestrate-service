# E-extension-sandbox — Requirements

## Introduction

E-extension-sandbox gates what a loaded extension may touch via a
declarative capability manifest with a closed vocabulary:
`read:secrets`, `write:artifacts`, `dispatch:jobs`, `net:outbound`,
`process:subprocess`. Capabilities are declared in the
`pychestrate_ext.yaml` manifest (`E-extension-manifest`) and enforced
at registry-lookup time and at bus-delivery time: an extension cannot
call a factory protocol or receive a bus event that its capability set
does not cover. This feature ships in Phase 8 — after the protocol
catalog is broad enough that capability gating has teeth.

## Requirements

### Requirement 1: Closed capability vocabulary

**User Story:** As a platform maintainer, I want a fixed, documented
capability vocabulary, so that the security review of a new extension
reduces to checking the manifest's capability list.

**Acceptance Criteria (EARS):**

1. WHEN a manifest declares a capability outside the closed
   vocabulary THEN the system SHALL refuse to load the package and
   emit `extension.manifest_rejected` with reason
   `unknown_capability`.
2. WHERE the manifest omits the `capabilities:` key THEN the system
   SHALL treat the extension as zero-capability (can register types
   but cannot call outbound protocols or receive sensitive events).
3. WHEN the operator enables a new capability via
   `/admin/extensions/{name}/capabilities` THEN the system SHALL
   audit-log the grant and hot-reload the capability set without
   service restart.

### Requirement 2: Lookup-time factory gate

**User Story:** As a service operator, I want extensions blocked from
calling factory protocols whose invocation requires a capability they
have not been granted, so that a rogue pack cannot dispatch jobs it
was not authorized to dispatch.

**Acceptance Criteria (EARS):**

1. WHEN the host resolves a factory invocation THEN the system SHALL
   check the winning factory's owning-ext capabilities against the
   protocol's required-capabilities.
2. IF required capabilities are not a subset of the extension's
   granted capabilities THEN the system SHALL raise `PermissionError`
   and emit `extension.call_denied` with
   `{ext, protocol, missing_capabilities}`.
3. WHERE a protocol does not declare required capabilities THEN the
   system SHALL treat it as requiring none (back-compat default).

### Requirement 3: Delivery-time hook gate

**User Story:** As a platform maintainer, I want each bus subscription
gated by a capability check, so that a subscriber cannot observe
payloads that carry scoped secrets.

**Acceptance Criteria (EARS):**

1. WHEN a hook subscription is evaluated at registration time THEN
   the system SHALL check the topic's
   `required_subscriber_capabilities` against the ext's granted
   capabilities; refuse registration on mismatch.
2. WHEN a bus event is delivered THEN the system SHALL re-check
   capabilities in case the grant was revoked between registration
   and delivery; on mismatch, SHALL drop the delivery and emit
   `extension.hook_denied`.

### Requirement 4: Runtime revocation

**User Story:** As an incident responder, I want to revoke a
capability from a suspect extension immediately, so that its next
outbound call is denied without a service restart.

**Acceptance Criteria (EARS):**

1. WHEN an admin POSTs
   `/admin/extensions/{name}/capabilities/revoke` with a capability
   THEN the system SHALL remove the capability from the active grant
   set, emit `extension.capability_revoked`, and audit-log the
   action.
2. IF a revocation removes a capability that the extension currently
   holds a long-running lease on (e.g., a subprocess with
   `process:subprocess`) THEN the system SHALL signal the lifecycle
   coordinator to initiate `on_service_draining` for that extension
   while leaving the broader service running.

## Property-Based Test Requirements

### Property 1: Capability-closed invariance

- **Invariant:** For any (extension, protocol) pair where the
  extension's capability set does not include the protocol's required
  capabilities, every lookup call results in `PermissionError` and no
  protocol method is invoked.
- **Generator:** random (granted_set, required_set) pairs.
- **Assertion:** Outcome matches `required_set ⊆ granted_set`; mock
  protocol call-count stays at 0 on denial paths.
- **Sample size:** 1000 generated cases.

### Property 2: Delivery-time re-check correctness

- **Invariant:** For any subscription registered under capability set
  `G0` and any later grant-set change to `G1`, delivery succeeds
  if-and-only-if `required ⊆ G1` at delivery time, independent of
  `G0`.
- **Generator:** sequences of `(event, grant_change)` operations.
- **Assertion:** Observed delivery count equals the count of events
  where the runtime `G_t` satisfies the requirement.
- **Sample size:** 1000 generated cases.

### Property 3: Zero-capability default safety

- **Invariant:** For any extension loaded with an empty capability
  list, no factory call with nonzero `required` succeeds, no sensitive
  hook delivery occurs, yet type registration and enumeration APIs
  continue to work.
- **Generator:** any loaded package + random factory/hook requests.
- **Assertion:** Registration-only behavior intact; every other
  action denies.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Capability check adds < 0.2 ms P99
  overhead per lookup / per delivery (in-memory set operation).
- **NFR-2 (Security):** Capability vocabulary is closed (no free-form
  strings); revocation is immediate and persisted to DB so it
  survives restart; grants + revocations always audit-logged.
- **NFR-3 (Observability):** Metrics
  `pychestrate_extension_capability_check_total{ext,capability,result}`,
  `pychestrate_extension_call_denied_total{ext,protocol}`,
  `pychestrate_extension_hook_denied_total{ext,topic}`,
  `pychestrate_extension_capability_revoked_total{ext,capability}`;
  log events `pychestrate_extension_call_denied`,
  `pychestrate_extension_hook_denied`,
  `pychestrate_extension_capability_granted`,
  `pychestrate_extension_capability_revoked`; trace span
  `pychestrate_extension.sandbox.authorize`.
- **NFR-4 (Reliability):** Denials never crash the caller; they raise
  `PermissionError` (for lookups) or drop and log (for deliveries).

## Out of Scope

- Process-level sandboxing (seccomp, namespaces) — out of scope for
  in-process Python; only API-surface gating.
- Per-call quota enforcement (future feature).
- Network-level egress controls (delegated to network stack).

## Dependencies

- **Depends on:** `E-extension-host`, `E-extension-manifest`,
  `E-extension-lifecycle`, `E-extension-hooks`,
  `E-factory-protocols`, `1-audit-log`, `1-rbac`, `0-persistence`.
- **Depended on by:** `E-extension-registry-ui`, `E-plugin-api`.
- **Extension points exposed:** `required_capabilities` class
  attribute on `FactoryProtocolBase` subclasses and
  `required_subscriber_capabilities` on bus topic declarations.
