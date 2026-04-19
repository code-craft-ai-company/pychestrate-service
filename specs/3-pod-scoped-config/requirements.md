# 3-pod-scoped-config — Requirements

## Introduction

Pod-Scoped Config layers `2-global-variables` (typed hierarchical variables)
and `1-secrets-vault` (encrypted values with ACLs) with a new innermost
scope: a specific pod *run*. A run of a dynamic pod (`3-dynamic-pods`,
Phase 8) or an ad-hoc operator overlay on a static pod can provision
variables and secrets that are visible only for that run and are
automatically discarded when the pod releases. This feature lives in
Layer 3 and ships in Phase 8 alongside dynamic pods. It *reuses* the
factory protocols declared by `2-global-variables` (`variable_resolver`,
`secret_ref_dereferencer`) and the backends of `1-secrets-vault`; it
contributes no new factory protocol of its own, but it does introduce a
new resolution scope that those factories must honor. Per the architectural
ground rules, the client is still the sole contact point: pod-scoped
values are rendered into the job envelope server-side, then handed to the
client; pod members never fetch them directly.

## Requirements

### Requirement 1: Pod-scoped variables shadow project and global scopes

**User Story:** As a job author, I want to override a variable for a
single pod run without mutating the project-level value, so that my
temporary test parameter does not bleed into other runs.

**Acceptance Criteria (EARS):**

1. WHEN a `VariableResolutionRequest{name}` is evaluated in the scope of
   a pod run THEN the system SHALL consult scopes in the order
   `pod_run -> pod_definition -> project -> global` and return the first
   matching value.
2. IF a variable is set at `pod_run` scope and at a higher scope THEN
   the `pod_run` value SHALL win and the higher-scope value SHALL NOT be
   observable in the resolved context.
3. WHERE the `pod_run` variable is marked `locked=true` the system SHALL
   prevent any higher scope from overriding it within the same run and
   SHALL prevent updates during the run's lifetime.
4. WHEN the pod transitions to `state=released` THEN the system SHALL
   purge all `pod_run`-scoped variables for that run.

### Requirement 2: Pod-scoped secrets are ACL-guarded and audit-logged

**User Story:** As a security operator, I want every pod-scoped secret
access to be auditable and gated by an ACL, so that a compromised run
cannot exfiltrate secrets across pods.

**Acceptance Criteria (EARS):**

1. WHEN a pod-scoped secret is read via `SecretRefDereferencer.dereference`
   THEN the system SHALL record a `pod_scoped_secret_access` row with
   (caller, run_id, secret_ref, access_time) before returning the value.
2. IF the secret's ACL does not include the requesting run's
   `pod_id` THEN the system SHALL raise `SecretACLDenied` and SHALL NOT
   disclose the value.
3. WHILE the run is live the system SHALL honor secret rotation
   signals from the configured `secrets_backend`; on rotation the next
   dereference SHALL return the new value.
4. WHEN the pod transitions to `state=released` THEN the system SHALL
   revoke any time-bound secret leases acquired on the pod's behalf
   within 5 seconds.

### Requirement 3: Pod-scoped config is injected into the dispatch envelope, not fetched by members

**User Story:** As a pod member, I do not connect to Pychestrate — so
my config must already be in the dispatch payload handed to my client.

**Acceptance Criteria (EARS):**

1. WHEN `5-job-dispatch` renders an envelope targeting a pod THEN the
   system SHALL bake all `pod_run`-scoped variables (and dereferenced
   secrets, where allowed by the envelope's `5-job-envelope` surface)
   into the envelope server-side before handing it to the client.
2. IF a secret is not allowed to be baked (policy
   `inline_delivery=false`) THEN the envelope SHALL carry a short-lived
   bearer reference instead, and the client SHALL dereference it via a
   scoped subrequest back to Pychestrate.
3. WHERE the pod's client is currently `client_lost` the system SHALL
   defer envelope rendering and SHALL NOT dispatch until the client
   recovers.

## Property-Based Test Requirements

### Property 1: Scope precedence is total and deterministic

- **Invariant:** For any set of variables assigned at scopes
  `{global, project, pod_definition, pod_run}` with arbitrary key
  collisions, `resolve(name, scope=pod_run)` returns the value from
  the innermost scope containing `name` (or `VariableNotFound` if no
  scope contains it). The outcome is independent of evaluation order.
- **Generator:** hypothesis strategy producing random scope-value maps
  across all four scopes and random access sequences.
- **Assertion:** for every query `name`, the returned value equals the
  outcome of a reference implementation that walks scopes in declared
  order.
- **Sample size:** 1000 generated cases

### Property 2: Purge on release is total

- **Invariant:** For any pod with `pod_run`-scope variables `V` and
  secrets `S` that was released, post-release:
  `resolve(v, scope=pod_run) == VariableNotFound` for every `v in V`
  and `dereference(s)` raises `ScopeEnded` for every `s in S`.
- **Generator:** hypothesis strategy producing pods with 0-50 `pod_run`
  variables and 0-10 `pod_run` secrets; releases triggered at random
  points.
- **Assertion:** no `pod_run` row for the released run remains in the
  variable or secret tables; bearer references issued for the run are
  invalidated.
- **Sample size:** 1000 generated cases

### Property 3: Bearer references are unforgeable

- **Invariant:** For any issued bearer reference `b` bound to
  `(run_id, secret_ref, expires_at)`, substituting any component of the
  reference yields rejection; replay after `expires_at` yields rejection.
- **Generator:** hypothesis strategy producing bearer references, then
  applying random perturbations to one random component.
- **Assertion:** `dereference_bearer(b')` raises `InvalidBearer` for
  every perturbed `b'` and every expired replay.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** variable resolution p99 <= 10 ms with a hot
  cache; secret dereference p99 <= 40 ms including audit write; purge
  on release p99 <= 500 ms for pods with up to 50 `pod_run` variables.
- **NFR-2 (Security):** every pod-scoped secret access audit-logged;
  bearer references 256-bit random, tied to `run_id` and
  `expires_at <= min(ttl_cap, pod_release_deadline)`; rendered envelopes
  redact secret values from any log line; pod-scoped config stored at
  rest encrypted via the configured `secrets_backend`.
- **NFR-3 (Observability):** metrics
  `pychestrate_pod_scoped_variable_reads_total`,
  `pychestrate_pod_scoped_secret_reads_total{outcome}`,
  `pychestrate_pod_scoped_purges_total`,
  `pychestrate_pod_scoped_bearer_rejects_total{reason}`; log events
  `pychestrate_pod_scoped_secret_access`,
  `pychestrate_pod_scoped_purge`; trace span
  `pod_scoped_config.resolve`, `pod_scoped_config.purge`.
- **NFR-4 (Reliability):** purge is idempotent (safe to call N times);
  bearer-reference revocation is eventually-consistent under a 5s bound.

## Out of Scope

- New factory protocols — reuses `2-global-variables` and
  `1-secrets-vault` surfaces.
- Project-level variable UI (owned by `2-global-variables`).
- Pod definition validation (owned by `3-pod-definitions`).
- Envelope schema itself (owned by `5-job-envelope`).

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`, `1-secrets-vault`,
  `1-audit-log`, `1-rbac`, `2-global-variables`,
  `3-pod-definitions`, `3-pod-lifecycle`, `5-job-envelope`.
- **Depended on by:** `3-dynamic-pods`, `5-job-dispatch`,
  `6-test-orchestration` (Phase 8+ pod-request workflow).
- **Extension points exposed:** none new. Reuses
  `factory: variable_resolver`, `factory: secret_ref_dereferencer`,
  `factory: secrets_backend` — these protocols' implementations must
  honor the `pod_run` scope argument added by this feature. See
  implementation-plan.md Layer 3.
