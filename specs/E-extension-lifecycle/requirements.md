# E-extension-lifecycle — Requirements

## Introduction

E-extension-lifecycle standardizes the hooks that factory and resource
extensions may implement to participate in the service lifecycle:
`on_load`, `on_service_ready`, `on_project_loaded(project)`,
`on_service_draining`, `on_unload`. The host invokes hooks in PRECEDENCE
order with a per-hook timeout, captures exceptions as
`extension.call_failed` events, and refuses to advance the service to
`ready` if any `on_service_ready` hook fails under strict mode. This
feature ships in Phase 0.5 with `E-extension-host` and provides the
missing long-lived-service semantics that `codecraftai-extension` leaves to
the caller.

## Requirements

### Requirement 1: Standardized hook surface

**User Story:** As an extension author, I want a fixed set of lifecycle
hook names with documented signatures, so that my extension can
participate in startup, project load, drain, and unload without
inventing patterns per feature.

**Acceptance Criteria (EARS):**

1. WHEN an extension class declares any of
   `on_load`, `on_service_ready`, `on_project_loaded`,
   `on_service_draining`, `on_unload` as a classmethod THEN the host
   SHALL treat the class as a lifecycle participant for that hook.
2. IF the declared method signature does not match the contract (see
   design.md) THEN the system SHALL raise `ConfigurationError` at load
   time naming the class and the expected signature.
3. WHERE an extension declares no lifecycle hooks THEN the system SHALL
   load it unchanged and SHALL skip it during every lifecycle phase
   without overhead.

### Requirement 2: Ordered invocation with timeout

**User Story:** As a service operator, I want lifecycle hooks to run in
a deterministic order with a bounded per-hook timeout, so that a
misbehaving extension cannot indefinitely stall service startup or
drain.

**Acceptance Criteria (EARS):**

1. WHEN a lifecycle phase begins THEN the system SHALL invoke every
   registered hook in ascending `PRECEDENCE` order, tie-broken by
   qualified class name.
2. IF any single hook exceeds its per-hook timeout (default 10 s,
   configurable per phase via `lifecycle.<phase>.timeout_seconds`)
   THEN the system SHALL abandon that hook, emit
   `extension.call_failed` with reason `hook_timeout`, and continue to
   the next hook in order.
3. WHILE `on_service_draining` is running the system SHALL NOT accept
   new incoming HTTP requests (drain flag owned by `0-maintenance-mode`).
4. WHEN `on_project_loaded` fires THEN the system SHALL pass the
   project entity as a named parameter `project=<Project>` to every
   participating hook.

### Requirement 3: Fail-closed startup

**User Story:** As a service operator, I want a failing
`on_service_ready` hook to block the service from reaching `ready`
in strict mode, so that partial startup never masquerades as healthy.

**Acceptance Criteria (EARS):**

1. WHEN any `on_service_ready` hook raises in strict mode THEN the
   system SHALL mark `0-system-health` readiness as `failed`, emit
   `extension.call_failed` with phase `on_service_ready`, and refuse
   to accept traffic.
2. IF the extension host is in permissive mode THEN the system SHALL
   still log the failure, emit the event, and proceed to accept
   traffic with the failing extension quarantined (marked unhealthy in
   the registry).
3. WHERE an extension is quarantined THEN subsequent lookup calls
   through the host SHALL skip it and SHALL log
   `pychestrate_extension_skipped_quarantined`.

### Requirement 4: Unload is best-effort and idempotent

**User Story:** As a platform engineer, I want `on_unload` to be
best-effort and safe to call more than once, so that rescan-driven
replacement and service shutdown share the same code path.

**Acceptance Criteria (EARS):**

1. WHEN `on_unload` is called twice on the same extension without an
   intervening `on_load` THEN the second call SHALL be a no-op.
2. IF `on_unload` raises THEN the system SHALL log the failure and
   continue shutdown; it SHALL NOT re-raise.
3. WHERE shutdown is triggered THEN the system SHALL invoke
   `on_unload` hooks in descending `PRECEDENCE` order (reverse of
   load).

## Property-Based Test Requirements

### Property 1: Deterministic phase ordering

- **Invariant:** For any set of `N` extensions with distinct
  `PRECEDENCE`, the invocation order of hooks within a phase is
  determined solely by `PRECEDENCE` (ascending for load-ish phases,
  descending for `on_unload`), independent of discovery order.
- **Generator:** permutations of a list of
  `(PRECEDENCE, qualname)` pairs.
- **Assertion:** For every permutation, the captured invocation trace
  matches the canonical order.
- **Sample size:** 1000 generated cases.

### Property 2: Timeout containment

- **Invariant:** For any hook that exceeds its timeout, total phase
  wall-clock time is bounded by `sum(per-hook timeouts)` and every
  subsequent hook still runs.
- **Generator:** a list of hook durations, each drawn from
  `integers(0, 30000)` ms, plus a per-phase timeout.
- **Assertion:** `phase_duration <= sum(min(duration_i, timeout))` plus
  bookkeeping slack; every non-timed-out hook appears in the trace.
- **Sample size:** 1000 generated cases.

### Property 3: Unload idempotence

- **Invariant:** For any extension `E`, calling `on_unload(E)` any
  number of additional times without re-loading produces no additional
  state change beyond the first call.
- **Generator:** any valid extension + `N in range(1, 20)` unload
  calls.
- **Assertion:** Post-call state equality across iterations 1..N;
  observed exception count equals exception count on first call only.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Default per-hook timeout is 10 s; phase
  startup overhead (zero hooks) is under 5 ms.
- **NFR-2 (Security):** Hook calls pass through the sandbox-authorization
  checkpoint once `E-extension-sandbox` lands (Phase 8); before then
  it is a no-op.
- **NFR-3 (Observability):** Metrics
  `pychestrate_extension_hook_duration_seconds{phase,extension}`,
  `pychestrate_extension_hook_failures_total{phase,reason}`,
  `pychestrate_extension_hook_timeouts_total{phase}`; log events
  `pychestrate_extension_hook_started`,
  `pychestrate_extension_hook_completed`,
  `pychestrate_extension_hook_failed`; trace span
  `pychestrate_extension.hook.<phase>`.
- **NFR-4 (Reliability):** Strict mode fails closed on
  `on_service_ready` failure; other phases are best-effort and
  quarantine the failing extension.

## Out of Scope

- The sandbox capability check itself (`E-extension-sandbox`).
- Project entity shape (owned by `2-projects`).
- Maintenance drain flag (owned by `0-maintenance-mode`).

## Dependencies

- **Depends on:** `E-extension-host`, `E-extension-manifest`,
  `0-message-bus`, `0-system-health`, `10-observability`,
  `0-maintenance-mode` (for drain signaling).
- **Depended on by:** `E-extension-sandbox` (quarantine hook),
  `E-extension-registry-ui` (health/last-error display),
  every downstream feature that installs per-project state.
- **Extension points exposed:** the five hook names are themselves the
  surface (Aspects-pattern: behavior parameters — timeouts — are
  passed, not decorator-style controlled).
