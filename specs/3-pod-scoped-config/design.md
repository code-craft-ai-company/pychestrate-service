# 3-pod-scoped-config — Design

## Architecture

Pod-Scoped Config lives at
`source/site/automojo/pychestrate/webservice/pods/scoped_config/`. It is
the *scope layer* that teaches `2-global-variables` and `1-secrets-vault`
about a new `pod_run` scope. It contributes:

- Two new tables: `pod_run_variable` and `pod_run_secret_grant`.
- A resolver decorator composed on top of the
  `variable_resolver` / `secret_ref_dereferencer` factory protocols that
  prepends the `pod_run` scope to every lookup chain.
- A purge hook driven by `entity.pod.state_changed{to=released}`.
- A bearer-reference mint/verify service used when envelopes carry
  secret references instead of inline values.

This feature does not declare its own factory protocols — it extends the
scope semantics of the Layer 1 and Layer 2 protocols. Authoritative
state: the two new tables plus transient bearer entries kept in a
short-TTL redis-compatible backend.

## Data Model

```
pod_run_variable
    variable_id:     UUID     primary key
    run_id:          UUID     not null    -- FK -> run (from 5-run-state-machine)
    pod_id:          UUID     not null    -- FK -> pod_definition
    name:            str      not null
    value_json:      jsonb    not null
    value_schema:    jsonb    nullable    -- inlined for audit
    locked:          bool     not null default false
    set_by:          UUID     -- FK user or system
    set_at:          datetime not null
    (run_id, name) unique
    (pod_id) index

pod_run_secret_grant
    grant_id:        UUID     primary key
    run_id:          UUID     not null
    pod_id:          UUID     not null
    secret_ref:      str      not null  -- opaque reference resolved by secrets_backend
    policy:          jsonb    not null  -- { inline_delivery: bool, ttl_seconds: int }
    granted_at:      datetime not null
    revoked_at:      datetime nullable
    (run_id, secret_ref) unique

pod_scoped_secret_access_log
    access_id:       UUID     primary key
    grant_id:        UUID     -- FK to grant
    actor:           str      -- user:<id> | client:<id> | service
    accessed_at:     datetime not null
    outcome:         SecretAccessOutcome
    (grant_id, accessed_at) index
```

Bearer-reference store (not a relational table — a TTL'd keyvalue backed
by `0-object-store`-less in-memory cache; falls back to
`pod_scoped_bearer` table for restart durability):

```
pod_scoped_bearer
    bearer_id:       str      primary key -- 256-bit random token hex
    grant_id:        UUID     not null
    issued_at:       datetime
    expires_at:      datetime
    consumed:        bool     default false
    (grant_id) index
    (expires_at) index
```

## Interfaces

### Public API

REST (RBAC `pod.scoped_config.*`):

- `PUT /api/v1/projects/{project_id}/runs/{run_id}/variables/{name}` —
  set a pod-run variable.
- `DELETE /api/v1/projects/{project_id}/runs/{run_id}/variables/{name}`.
- `POST /api/v1/projects/{project_id}/runs/{run_id}/secret-grants` —
  grant a secret to the run.
- `POST /api/v1/clients/bearer/dereference` — client-side dereference
  of a bearer reference; requires mTLS client identity to match the
  grant's `pod_id`'s client binding.

### Internal API

```python
def set_pod_run_variable(
    *,
    run_id: UUID,
    pod_id: UUID,
    name: str,
    value: Any,
    locked: bool,
    set_by: UUID,
) -> None:
    ...


def resolve_variable(
    *,
    run_id: UUID,
    name: str,
) -> ResolvedVariable:
    ...


def grant_pod_run_secret(
    *,
    run_id: UUID,
    pod_id: UUID,
    secret_ref: str,
    policy: SecretPolicy,
    granted_by: UUID,
) -> None:
    ...


def dereference_secret(
    *,
    run_id: UUID,
    secret_ref: str,
    actor: str,
) -> DereferencedSecret:
    ...


def mint_bearer(
    *,
    grant_id: UUID,
    ttl_seconds: int,
) -> BearerReference:
    ...


def dereference_bearer(
    *,
    bearer_token: str,
    presenting_client_id: UUID,
) -> DereferencedSecret:
    ...


def purge_run_scope(*, run_id: UUID) -> None:
    ...
```

### Extension Surface

None new. The feature adds a documented requirement that any implementation
of the `variable_resolver` and `secret_ref_dereferencer` factory protocols
must accept `scope=pod_run` and honor its precedence.

### Events Emitted

```
entity.pod.scoped_variable_set     { run_id, pod_id, name }
entity.pod.scoped_variable_deleted { run_id, pod_id, name }
entity.pod.scoped_secret_granted   { run_id, pod_id, secret_ref }
entity.pod.scoped_secret_revoked   { run_id, pod_id, secret_ref }
entity.pod.scoped_purged           { run_id }
```

### Events Consumed

- `entity.pod.state_changed{to=released}` — triggers purge.
- `entity.pod.state_changed{to=orphaned}` — same as released, for
  bearer-revocation purposes (variables retained for audit).
- `entity.secrets_backend.rotated` — invalidates cached dereferences
  for affected `secret_ref`s.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/pods/scoped_config/
    __init__.py
    dtos.py                     -- ResolvedVariable, DereferencedSecret,
                                   SecretPolicy, BearerReference
    service.py                  -- variable + secret + bearer APIs
    resolver_decorator.py       -- wraps variable_resolver factories with pod_run scope
    secret_decorator.py         -- wraps secret_ref_dereferencer factories
    purge.py                    -- purge_run_scope + subscriber
    bearer.py                   -- mint / dereference / expire bearers
    repository.py               -- PodRunVariableRepository,
                                   PodRunSecretGrantRepository,
                                   PodScopedBearerRepository
    rest.py                     -- REST routers (variables, grants, bearer)
    metrics.py
```

## Key Flows

**Setting a pod-run variable.** Admin or job harness calls
`PUT /variables/{name}` -> `service.set_pod_run_variable` writes a row in
`pod_run_variable`; emits `entity.pod.scoped_variable_set`. The
resolver-decorator chain puts `pod_run` scope at the head of the resolution
chain.

**Envelope rendering.** `5-job-dispatch` asks the scoped-config service
for `render_env(run_id)`; the service collects all `pod_run` variables and
all `pod_run_secret_grant` rows with `policy.inline_delivery=true`,
dereferences them through the `secret_ref_dereferencer` factory (audit
row written per access), and returns a map the dispatcher bakes into the
envelope.

**Bearer reference path.** For grants where `inline_delivery=false`, the
envelope carries a freshly-minted bearer token with
`expires_at = min(grant.expires_at, pod_release_deadline, now + 5m)`.
The client later calls `POST /clients/bearer/dereference` with the token.
The handler verifies the presenting `client_id` matches the pod's client
binding, verifies the bearer is un-consumed and unexpired, marks it
consumed, dereferences through the factory, writes an audit row, and
returns the value.

**Purge on release.** Subscriber on
`entity.pod.state_changed{to=released}` -> `purge.purge_run_scope`
DELETEs all `pod_run_variable` rows, marks all
`pod_run_secret_grant.revoked_at`, expires all un-consumed bearers, and
emits `entity.pod.scoped_purged`.

## Error Handling

- `VariableLocked` — raised when a higher-scope write or a pod-run
  rewrite violates `locked=true`. Caught at REST boundary, translated to
  HTTP 409.
- `SecretACLDenied` — raised by the secret decorator when the pod_id is
  not in the grant ACL; translated to HTTP 403; audit row written with
  `outcome=denied`.
- `InvalidBearer` (expired / consumed / unknown / client-mismatch) —
  translated to HTTP 401 with a generic `invalid_bearer` body (no
  discriminator leaked).
- `ScopeEnded` — raised for any resolution against a released run;
  translated to HTTP 410 Gone.
- `ConfigurationError` — raised at startup if the underlying
  `variable_resolver` / `secret_ref_dereferencer` factories do not
  declare `protocol_schema_version >= 1` supporting `pod_run` scope.
- `SemanticError` — never caught.
- Multiline error messages per AGENTS.md.

## Security Considerations

- Every secret access audit-logged with `actor`, `run_id`, `secret_ref`,
  `outcome`.
- Bearer tokens 256-bit random, stored as hex in
  `pod_scoped_bearer.bearer_id` plus a SHA256 in audit entries (to
  correlate logs without leaking the raw token).
- Inline secret rendering strips values from any log line via a
  structured-log filter; the filter is enabled at bootstrap.
- RBAC: `pod.scoped_config.variable.write`,
  `pod.scoped_config.secret.grant`, `pod.scoped_config.read`,
  `pod.scoped_config.admin`.
- Bearer dereference requires mTLS client match; no session or
  cookie-based alternative.
- Pod-scoped config at rest encrypted via the configured
  `secrets_backend`; at-rest encryption keys rotated per the vault's
  policy (not this feature's concern).

## Observability

Metrics:

- `pychestrate_pod_scoped_variable_reads_total{outcome}` — counter.
- `pychestrate_pod_scoped_secret_reads_total{outcome}` — counter.
- `pychestrate_pod_scoped_purges_total` — counter.
- `pychestrate_pod_scoped_purge_duration_seconds` — histogram.
- `pychestrate_pod_scoped_bearer_rejects_total{reason}` — counter.
- `pychestrate_pod_scoped_variables_gauge` — gauge of live `pod_run`
  variables across runs.

Log events: `pychestrate_pod_scoped_secret_access`,
`pychestrate_pod_scoped_purge`,
`pychestrate_pod_scoped_bearer_reject`.

Trace spans: `pod_scoped_config.resolve_variable`,
`pod_scoped_config.resolve_secret`,
`pod_scoped_config.mint_bearer`,
`pod_scoped_config.dereference_bearer`, `pod_scoped_config.purge`.

## Open Questions

- Retain a history of pod-scoped variables post-release for triage?
  Lean toward retaining a compacted audit row (name + set_by +
  checksum), not the value.
- Expose a "dry-run render" endpoint that shows what envelope would be
  produced without dispatching? Likely yes; confirm with ops workflow
  by end of M2.
