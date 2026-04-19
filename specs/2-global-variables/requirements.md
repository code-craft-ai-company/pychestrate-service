# 2-global-variables — Requirements

## Introduction

`2-global-variables` is Pychestrate's hierarchical, typed configuration store
for Layer 2. Variables are bound at one of four scopes —
**system → project → pipeline → job** — and values cascade downward; a lower
scope overrides a higher scope. The feature also resolves
`${secret:…}` references against `1-secrets-vault` and exposes a
**resolution-trace API** so the UI can show *where* each effective value came
from. It ships in **Phase 1 — Identity & Projects**, sits between `2-projects`
(which owns the project scope) and `3-pod-scoped-config` / Layer 6 pipeline &
job features (which consume effective values), and provides the
`variable_resolver` and `secret_ref_dereferencer` factory protocols.

## Requirements

### Requirement 1: Hierarchical set / unset with typed values

**User Story:** As a project admin, I want to set a typed variable at any of
the four scopes, so that higher-scope defaults can be overridden precisely
where needed without duplicating config.

**Acceptance Criteria (EARS):**

1. WHEN `PUT /api/v1/variables/{scope}/{scope_id}/{name}` is received with
   a JSON body `{type, value}` THEN the system SHALL upsert a
   `VariableBinding` row at that scope, publish `entity.variable.set`,
   and record an audit entry.
2. IF the supplied `type` is not one of
   `string | integer | float | boolean | json | secret_ref` THEN the
   system SHALL respond `400 Bad Request` with the list of accepted
   types.
3. IF `type == "secret_ref"` AND `value` does not match
   `^\$\{secret:[a-zA-Z0-9_./-]+\}$` THEN the system SHALL respond
   `400 Bad Request`.
4. WHEN `DELETE /api/v1/variables/{scope}/{scope_id}/{name}` is received
   THEN the system SHALL remove the binding at that exact scope only,
   publish `entity.variable.unset`, and return `204 No Content`.
5. WHERE the caller supplies `If-Match: <etag>` THEN the system SHALL
   reject with `412 Precondition Failed` if the stored binding's etag
   has changed since the etag was issued.

### Requirement 2: Effective-value resolution with explicit precedence

**User Story:** As a job runner, I want to fetch the effective value of a
variable for a specific `(project, pipeline, job)` context, so that job
execution uses one deterministic value.

**Acceptance Criteria (EARS):**

1. WHEN `GET /api/v1/variables/effective?project=<p>&pipeline=<pl>&job=<j>&name=<n>`
   is received THEN the system SHALL return
   `{name, type, value, source_scope, source_scope_id}` using the
   **first** binding found while walking scopes in order
   `job → pipeline → project → system`.
2. IF the variable name is not bound at any scope in the chain THEN the
   system SHALL respond `404 Not Found` with
   `{"name": n, "reason": "unbound"}`.
3. IF the resolved type is `secret_ref` THEN the system SHALL call the
   active `secret_ref_dereferencer` factory impl and return the
   dereferenced value; the response body SHALL NOT include the raw
   `${secret:…}` literal when a dereferencer is registered.
4. WHERE `?include_trace=true` is set THEN the system SHALL include a
   `trace` array enumerating every scope visited with
   `{scope, scope_id, present, value_ref?}`.

### Requirement 3: Inheritance trace for UI display

**User Story:** As a developer looking at the UI, I want to see where each
effective variable value came from (system default, project override,
pipeline override, or job override), so that I can understand which scope
to change to fix a bad value.

**Acceptance Criteria (EARS):**

1. WHEN `GET /api/v1/variables/trace?project=<p>&pipeline=<pl>&job=<j>`
   is received THEN the system SHALL return a list of every variable
   name visible in that context, each with a full `trace` array showing
   all four scopes with `present: bool`, `value` (when present and not a
   secret), `set_by_user_id`, `set_at`.
2. IF the caller lacks `project.variable.read` on the project THEN the
   system SHALL respond `403 Forbidden` and SHALL NOT leak variable
   names.
3. WHERE a scope holds a `secret_ref` THEN the trace entry's `value`
   field SHALL be replaced by `"<secret:redacted>"` unless the caller
   also holds `secret.reveal` on the referenced secret.

### Requirement 4: `variable_resolver` factory protocol

**User Story:** As an extension author, I want to plug in an external config
source (Consul, etcd, AppConfig) for the `system` scope, so that global
defaults can be managed outside Pychestrate.

**Acceptance Criteria (EARS):**

1. WHEN the extension host loads an impl of the `variable_resolver`
   factory protocol at precedence `P` THEN the system SHALL consult
   that impl ahead of the local DB for `system`-scope reads, honoring
   precedence order (lower number = higher priority).
2. IF no `variable_resolver` impl is registered THEN the system SHALL
   use the built-in `DatabaseVariableResolver` reference implementation.
3. WHEN a registered resolver raises a recoverable error THEN the
   system SHALL emit a counter increment, log a warning with the
   extension name, and fall through to the next-precedence resolver;
   IF no resolver succeeds THEN the request SHALL return
   `503 Service Unavailable` rather than silently default.

## Property-Based Test Requirements

### Property 1: Variable resolution is deterministic given a fixed inheritance chain

- **Invariant:** For any four-tuple of bindings
  `(system_val?, project_val?, pipeline_val?, job_val?)` and variable name
  `n`, calling `resolve_effective(n, context)` 1000 times SHALL produce the
  identical `(value, source_scope)` result.
- **Generator:** `hypothesis.strategies.tuples` of four optional typed
  values plus a random context tuple; same inputs replayed with random
  interleaving of concurrent `resolve_effective` calls.
- **Assertion:** All returned results are byte-equal.
- **Sample size:** 1000 generated cases.

### Property 2: Precedence order matches scope depth

- **Invariant:** For any set of bindings where the same variable `n` is
  bound at scopes `S ⊆ {system, project, pipeline, job}`, the
  `source_scope` returned by `resolve_effective` SHALL equal the
  deepest scope in `S` for the given context.
- **Generator:** `hypothesis.strategies.lists` producing random subsets of
  the scope set plus a random context.
- **Assertion:** For 1000 cases,
  `returned.source_scope == max(S, key=SCOPE_DEPTH)`.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** `GET /variables/effective` p95 ≤ 40 ms at
  200 req/s with warm cache; `GET /variables/trace` p95 ≤ 150 ms.
- **NFR-2 (Security):** All routes gated by `1-rbac` permissions
  (`project.variable.read`, `project.variable.write`,
  `system.variable.write`, `secret.reveal`). Secret dereferences are
  audit-logged with the actor id. Variable names are not leaked across
  project boundaries.
- **NFR-3 (Observability):** Counters
  `pychestrate_variable_set_total`,
  `pychestrate_variable_unset_total`,
  `pychestrate_variable_resolve_total{source_scope}`,
  `pychestrate_variable_resolver_error_total{extension}`;
  histogram `pychestrate_variable_resolve_duration_seconds`;
  log events `variable.set`, `variable.unset`, `variable.resolved`,
  `variable.resolver_failover`; trace spans `variable.resolve`,
  `variable.trace`.
- **NFR-4 (Reliability):** Resolution is deterministic (no RNG, no wall
  clock affecting outcome); resolver failover order is stable; the
  resolution cache is invalidated synchronously on
  `entity.variable.set|unset`.

## Out of Scope

- A GUI variable editor — covered by `9-admin-ui` and per-project UI in
  later phases.
- Encryption-at-rest for non-secret values — non-secret values are
  considered configuration and live in plain text in Postgres.
- Cross-project variable sharing — explicitly not supported; use the
  `system` scope.

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`, `1-authentication`,
  `1-rbac`, `1-audit-log`, `1-secrets-vault`, `2-projects`.
- **Depended on by:** `3-pod-scoped-config`, `5-job-envelope`,
  `6-pipeline-definition`, `6-build-orchestration`,
  `6-infra-orchestration`, every feature consuming effective config.
- **Extension points exposed:**
  `factory: variable_resolver`; `factory: secret_ref_dereferencer`;
  `event: entity.variable.set|unset`.
