# 1-feature-flags — Requirements

## Introduction

`1-feature-flags` is Pychestrate's runtime toggle surface. It lets
operators stage rollouts, gate experimental features, and shut off
misbehaving code paths without a redeploy. It ships in
**Phase 1 — Identity & Projects** (though full admin UI lands later in
Phase 10), sits alongside `1-secrets-vault` and `1-audit-log` in Layer
1, and is consumed by every feature that needs a toggle — most visibly
`1-authentication` (for `auth.local_fallback_enabled` and
`auth.mfa.<method>.enabled`) and `1-rbac` (for
`rbac.reason_trace`). The feature exposes the `feature_flag_backend`
factory protocol so operators can route evaluations to a local store
or an external flag service (LaunchDarkly-style, custom).

## Requirements

### Requirement 1: Deterministic Evaluation

**User Story:** As a feature author, I want flag evaluation to be
deterministic for a given context, so that staged rollouts behave
predictably and logs are reproducible.

**Acceptance Criteria (EARS):**

1. WHEN a caller invokes
   `evaluate_flag(flag_key, context, default)` with a context that
   carries a stable `bucketing_key` (usually `user_id` or `project_id`)
   THEN the system SHALL return the same value for the same
   `(flag_key, flag_version, context)` tuple within the configured
   staleness window.
2. IF the flag key is not registered in the current catalog THEN the
   system SHALL return `default` and emit
   `pychestrate_flags_unknown_total{flag_key}` without raising — the
   evaluator fails soft to preserve availability.
3. WHERE a flag declares a percentage rollout (e.g., "50% of users")
   the system SHALL compute the bucket via
   `sha256(flag_key || bucketing_key)` modulo 10000 and compare
   against the rollout threshold, so that the same bucketing key
   lands in the same bucket across processes.
4. WHEN `evaluate_flag` is called with a `context` missing the
   required `bucketing_key` the system SHALL raise `SemanticError`
   — AGENTS.md forbids soft fallback for API misuse.

### Requirement 2: Flag Lifecycle Operations

**User Story:** As an operator, I want to create, update, and retire
flags with a documented audit trail, so that the set of runtime
toggles stays intentional rather than accidental.

**Acceptance Criteria (EARS):**

1. WHEN an operator calls `create_flag` with a unique `flag_key`,
   `default_value`, and optional rollout rules THEN the system SHALL
   persist a `Flag` row with `version = 1`, publish
   `entity.flag.created`, and mirror to every registered
   `feature_flag_backend` in declaration order.
2. WHEN an operator updates a flag's rollout rules THEN the system
   SHALL increment `version`, persist the new row as immutable
   history, publish `entity.flag.updated`, and invalidate
   evaluator caches within the configured staleness window (default
   60 seconds).
3. WHEN a flag is retired THEN the system SHALL mark it `retired`,
   publish `entity.flag.retired`, continue to evaluate it to its
   final `default_value` for a grace period (default 7 days), and
   remove it from the catalog at grace-end.
4. IF an operator attempts to change `flag_key` or `flag_kind`
   (boolean vs enum vs string) after creation THEN the system SHALL
   reject with `SemanticError` — schema-changing updates are
   out-of-scope; operators must retire and re-create.

### Requirement 3: Backend Delegation and Health

**User Story:** As an enterprise operator, I want Pychestrate to
defer to our existing flag service for a declared set of flags, so
that our rollout tooling continues to own them.

**Acceptance Criteria (EARS):**

1. WHEN an operator configures a `feature_flag_backend` extension
   with a `flag_key_pattern` THEN the system SHALL evaluate every
   matching flag through that backend and SHALL NOT consult the
   local catalog for those keys.
2. IF a backend returns a transient error during evaluation THEN
   the system SHALL fall back to the evaluator's local cache for
   up to the configured staleness window and emit
   `pychestrate_flags_backend_errors_total{backend,kind}`.
3. WHILE a backend is marked unhealthy (three consecutive failed
   health checks) the system SHALL evaluate its flags from the
   last-good cached value and publish
   `entity.flag.backend.unhealthy`.
4. WHERE two registered `feature_flag_backend` extensions claim the
   same `flag_key_pattern` the system SHALL pick the lower
   `PRECEDENCE` (higher priority) and log a
   `flags.backend.override` event.

## Property-Based Test Requirements

### Property 1: Same Inputs, Same Result Within Staleness Window

- **Invariant:** For any flag version V and any context C with a
  stable `bucketing_key`, all calls to
  `evaluate_flag(flag_key, C, default)` within a single staleness
  window return the same value, regardless of how many processes
  make the call or in what order.
- **Generator:** Strategy producing flag definitions (boolean,
  percentage rollout 0–10000, enum), a set of contexts with fixed
  `bucketing_key`s, and an interleaving of 2–500 evaluation calls
  across simulated processes inside a single staleness window.
- **Assertion:** For each `(flag_key, context)` pair, the set of
  returned values across the interleaving has cardinality 1.
- **Sample size:** 1000 generated cases.

### Property 2: Percentage Rollout Is a Monotone Step

- **Invariant:** For any bucketing key set and any fixed
  `flag_key`, raising a percentage rollout from `p1` to `p2` where
  `p2 >= p1` SHALL only add keys to the on-cohort — no key that was
  on at `p1` turns off at `p2`.
- **Generator:** Strategy producing random bucketing-key sets of
  size 1–10000 and two rollout percentages `p1 <= p2`.
- **Assertion:** `on_cohort(p1) ⊆ on_cohort(p2)` for every
  generated case.
- **Sample size:** 1000 generated cases.

### Property 3: Default Fallback on Unknown Key

- **Invariant:** For any context and any `default`, calling
  `evaluate_flag` with a `flag_key` that is not in the catalog
  returns `default` and does not raise.
- **Generator:** Strategy producing arbitrary `flag_key` strings
  (including empty, unicode, whitespace-padded) outside the
  registered catalog.
- **Assertion:** Returned value equals `default` and
  `pychestrate_flags_unknown_total{flag_key}` is incremented by
  exactly one per call.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** `evaluate_flag` on a warm cache SHALL
  complete in < 1 ms p95. Cold evaluations against the local
  backend SHALL complete in < 5 ms p95. Backend-delegated
  evaluations are bounded by the backend's own SLO but SHALL NOT
  block beyond `aspects.timeout_seconds` (default 100 ms).
- **NFR-2 (Security):** `system:flags.admin` gates flag
  create/update/retire; `system:flags.read` gates the read-only
  catalog surface. Flag definitions SHALL NOT carry secret values;
  if a rollout depends on a secret, the rule references a
  `secret_ref` resolved through `1-secrets-vault` at evaluation
  time. Every lifecycle operation audits through `1-audit-log`.
- **NFR-3 (Observability):** The feature SHALL emit
  `pychestrate_flags_evaluations_total{flag_key,outcome}`,
  `pychestrate_flags_evaluation_duration_seconds{flag_key}` (histogram),
  `pychestrate_flags_unknown_total{flag_key}`,
  `pychestrate_flags_backend_errors_total{backend,kind}`,
  `pychestrate_flags_active` (gauge of active flags), and log
  events `flag.created`, `flag.updated`, `flag.retired`,
  `flag.evaluated` (sampled), `flag.backend.unhealthy`,
  `flag.backend.override`.
- **NFR-4 (Reliability):** A total backend outage SHALL degrade to
  last-good cached values rather than fail the request path; once
  the staleness window elapses, evaluations for delegated flags
  SHALL return `default` and continue emitting the unknown /
  backend-error metrics so operators notice.

## Out of Scope

- Admin UI for managing flags — lives in `9-admin-ui` (Phase 10).
- A/B experimentation statistics — not a flag concern; owned by
  future analytics features.
- User-targeting rules beyond a bucketing key + simple attribute
  match — richer targeting is deferred to an external
  `feature_flag_backend`.

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`, `1-rbac`,
  `1-audit-log`, `E-extension-host`, `E-factory-protocols`,
  `1-secrets-vault` (for backend credentials).
- **Depended on by:** `1-authentication` (`auth.local_fallback_enabled`,
  `auth.mfa.<method>.enabled`), `1-rbac` (`rbac.reason_trace`),
  every feature that wants a staged-rollout switch.
- **Extension points exposed:** `factory: feature_flag_backend` —
  local, LaunchDarkly-style, custom. Reference implementation
  `LocalDatabaseFeatureFlagBackend` ships in-tree. See
  implementation-plan.md Layer 1.
