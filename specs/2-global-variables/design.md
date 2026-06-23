# 2-global-variables — Design

## Architecture

`2-global-variables` lives in Layer 2 and is owned by
`ccai.pychestrate.webservice.model.variables`. Bindings persist in
`0-persistence`; resolution is stateless and layered through a chain of
`variable_resolver` factory impls (lowest `PRECEDENCE` first). The in-tree
reference implementation, `DatabaseVariableResolver`, reads directly from the
DB. Secret references are dereferenced through an independent factory chain
(`secret_ref_dereferencer`), with the in-tree reference implementation
delegating to `1-secrets-vault`. A small in-process LRU cache
(`cachetools.TTLCache`) backs repeated reads and is invalidated on
`entity.variable.set|unset`. Ships in **Phase 1**.

## Data Model

```python
class VariableScope(str, enum.Enum):
    SYSTEM = "system"
    PROJECT = "project"
    PIPELINE = "pipeline"
    JOB = "job"

SCOPE_DEPTH: dict[VariableScope, int] = {
    VariableScope.SYSTEM: 0,
    VariableScope.PROJECT: 1,
    VariableScope.PIPELINE: 2,
    VariableScope.JOB: 3,
}

class VariableType(str, enum.Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    JSON = "json"
    SECRET_REF = "secret_ref"

@dataclass
class VariableBinding:
    binding_id: UUID             # PK
    scope: VariableScope
    scope_id: UUID | None        # NULL only for scope=SYSTEM
    name: str                    # matches ^[A-Z][A-Z0-9_]{0,63}$
    value_type: VariableType
    value_text: str              # canonical text form; bool/int/float parsed on read
    set_by_user_id: UUID
    set_at: datetime
    etag: UUID                   # rotates on update; used for If-Match
```

Uniqueness: `UNIQUE (scope, scope_id, name)` with expression index
`COALESCE(scope_id, '00000000-0000-0000-0000-000000000000')` so SYSTEM rows
are still unique.

Indexes: `(scope, scope_id)`, `(name)` for scan-by-name queries.

```python
@dataclass
class EffectiveValue:
    name: str
    value_type: VariableType
    value: Any                   # decoded from value_text
    source_scope: VariableScope
    source_scope_id: UUID | None
    dereferenced: bool           # True if a secret was resolved

@dataclass
class TraceEntry:
    scope: VariableScope
    scope_id: UUID | None
    present: bool
    value: Any | None            # redacted for secrets unless authorized
    value_type: VariableType | None
    set_by_user_id: UUID | None
    set_at: datetime | None
```

## Interfaces

### Public API

- `PUT /api/v1/variables/{scope}/{scope_id}/{name}` — body
  `{type, value}`; requires `project.variable.write` or
  `system.variable.write`.
- `DELETE /api/v1/variables/{scope}/{scope_id}/{name}` — same perms.
- `GET /api/v1/variables/{scope}/{scope_id}` — list bindings at scope.
- `GET /api/v1/variables/effective` — query params
  `project, pipeline?, job?, name, include_trace?`.
- `GET /api/v1/variables/trace` — query params
  `project, pipeline?, job?`; returns merged view with full trace
  array.

### Internal API

```python
# source/site/ccai/pychestrate/webservice/model/variables/service.py

def set_variable(
    *,
    scope: VariableScope,
    scope_id: UUID | None,
    name: str,
    value_type: VariableType,
    value_text: str,
    actor_user_id: UUID,
    if_match_etag: UUID | None = None,
) -> VariableBinding:
    """
        Upsert a variable binding at the requested scope.

        :param scope: Target scope
        :param scope_id: Owning entity id (None only for SYSTEM)
        :param name: Variable name
        :param value_type: Declared type
        :param value_text: Canonical textual encoding
        :param actor_user_id: Principal performing the write
        :param if_match_etag: Optional optimistic-concurrency etag

        :returns: The stored VariableBinding
        :raises: ValidationError, ConcurrentUpdateError
    """
    ...


def unset_variable(
    *,
    scope: VariableScope,
    scope_id: UUID | None,
    name: str,
    actor_user_id: UUID,
) -> None:
    ...


def resolve_effective(
    *,
    name: str,
    project_id: UUID,
    pipeline_id: UUID | None,
    job_id: UUID | None,
    actor_user_id: UUID,
    include_trace: bool = False,
) -> EffectiveValue | tuple[EffectiveValue, list[TraceEntry]]:
    """
        Walk job -> pipeline -> project -> system and return the first hit.

        :param name: Variable name
        :param project_id: Project scope
        :param pipeline_id: Optional pipeline scope
        :param job_id: Optional job scope
        :param actor_user_id: Caller for audit-trail redaction decisions
        :param include_trace: If True, also return the trace array

        :returns: EffectiveValue or (EffectiveValue, trace)
        :raises: VariableNotBoundError
    """
    ...


def collect_trace(
    *,
    project_id: UUID,
    pipeline_id: UUID | None,
    job_id: UUID | None,
    actor_user_id: UUID,
) -> dict[str, list[TraceEntry]]:
    """
        Return every variable name visible in the context with a full
        four-scope trace — drives the UI "where did this come from" view.

        :param project_id: Target project
        :param pipeline_id: Optional pipeline context
        :param job_id: Optional job context
        :param actor_user_id: Caller for redaction decisions

        :returns: Mapping of variable name to list of TraceEntry (one per scope)
    """
    ...
```

### Extension Surface

- `factory: variable_resolver`
  (`source/site/ccai/pychestrate/webservice/model/variables/factories.py`)

```python
class VariableResolverProtocol(FactoryProtocolBase):
    factory_protocol_name = "variable_resolver"

    @classmethod
    def read_binding(
        cls,
        *,
        scope: VariableScope,
        scope_id: UUID | None,
        name: str,
    ) -> VariableBinding | None:
        """Return the binding at scope/scope_id/name or None."""
        ...

    @classmethod
    def list_bindings(
        cls,
        *,
        scope: VariableScope,
        scope_id: UUID | None,
    ) -> list[VariableBinding]:
        ...
```

  Reference impl: `DatabaseVariableResolver` (`PRECEDENCE = 1000`)
  reads from Postgres.

- `factory: secret_ref_dereferencer`

```python
class SecretRefDereferencerProtocol(FactoryProtocolBase):
    factory_protocol_name = "secret_ref_dereferencer"

    @classmethod
    def dereference(
        cls,
        *,
        secret_ref: str,
        actor_user_id: UUID,
    ) -> str:
        """Resolve ${secret:…} to its plaintext value."""
        ...
```

  Reference impl: `VaultSecretRefDereferencer` (`PRECEDENCE = 1000`)
  delegates to `1-secrets-vault`.

### Events Emitted

```python
@dataclass
class VariableSetEvent:
    scope: VariableScope
    scope_id: UUID | None
    name: str
    value_type: VariableType
    actor_user_id: UUID
    occurred_at: datetime

@dataclass
class VariableUnsetEvent:
    scope: VariableScope
    scope_id: UUID | None
    name: str
    actor_user_id: UUID
    occurred_at: datetime
```

Topics: `entity.variable.set`, `entity.variable.unset`.

### Events Consumed

- `entity.project.deleted` — purge all `(scope='project', scope_id=X)`
  bindings and emit one `entity.variable.unset` per row.
- `entity.variable.set|unset` — internal cache invalidator subscribes and
  drops the affected entries.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/model/variables/
    __init__.py
    entities.py         # VariableBinding, EffectiveValue, TraceEntry
    repository.py       # DB access used by DatabaseVariableResolver
    service.py          # set/unset/resolve_effective/collect_trace
    resolver_chain.py   # composes factory impls by PRECEDENCE
    cache.py            # TTLCache + invalidation subscriber
    factories.py        # VariableResolverProtocol,
                        # SecretRefDereferencerProtocol,
                        # DatabaseVariableResolver,
                        # VaultSecretRefDereferencer
    events.py
    errors.py           # VariableNotBoundError, ConcurrentUpdateError
source/site/ccai/pychestrate/webservice/restapi/versions/v1/variables.py
```

## Key Flows

**Set variable**
1. REST resource validates `{scope, scope_id, name, type, value}`.
2. `service.set_variable` opens a transaction, executes upsert, writes
   outbox row for `entity.variable.set`, commits.
3. Cache invalidator (bus subscriber) drops entries whose scope chain
   contains `(scope, scope_id)`.

**Resolve effective**
1. REST resource authenticates and authorizes.
2. `service.resolve_effective` calls `resolver_chain.read_binding` for
   each scope in order `JOB, PIPELINE, PROJECT, SYSTEM`, stopping at the
   first non-`None` result.
3. If `value_type == SECRET_REF`, dispatch through the
   `secret_ref_dereferencer` chain; audit-log the dereference.
4. Return `EffectiveValue` (+ trace when requested).

**Collect trace for UI**
1. REST resource loads all variable names visible in the context via
   `repository.list_names_in_context`.
2. For each name, the service calls `resolver_chain.read_binding` for
   every scope (not short-circuit) and composes a `TraceEntry` list.
3. Secrets are redacted unless the caller holds `secret.reveal`.
4. UI renders a strike-through cascade (system → project → pipeline →
   job), highlighting the single scope whose value wins.

## Error Handling

- `VariableNotBoundError` → REST `404`.
- `ConcurrentUpdateError` (etag mismatch) → REST `412`.
- `ValidationError` (bad type, bad value encoding) → REST `400`
  with a multiline message built via `os.linesep.join([...])`.
- Resolver failover: recoverable errors (`IOError`, `TimeoutError`,
  driver-specific errors) are caught, reclassified to
  `ResolverFailoverError` with extension name, counter incremented,
  next resolver tried. If all fail, the REST layer returns `503` — no
  silent default.
- `SemanticError` is never caught.
- `ConfigurationError` is raised if the registered
  `secret_ref_dereferencer` list is empty while any binding has
  `value_type == SECRET_REF`.

## Security Considerations

- All routes require an authenticated session.
- `1-rbac` gates writes; reads are gated per project.
- Secrets are never logged in plain text; audit entries reference the
  secret by id, not value.
- `collect_trace` redacts secret values by default and only reveals
  when the caller holds `secret.reveal` on the specific referenced
  secret.
- Variable names across projects are isolated — the effective and
  trace endpoints refuse to resolve names outside the caller's
  permitted project scope.
- Rate limit: `resolve_effective` 500/min/session;
  set/unset 60/min/session.

## Observability

- Counters: `pychestrate_variable_set_total{scope}`,
  `pychestrate_variable_unset_total{scope}`,
  `pychestrate_variable_resolve_total{source_scope}`,
  `pychestrate_variable_resolver_error_total{extension}`,
  `pychestrate_variable_secret_dereference_total`.
- Histogram:
  `pychestrate_variable_resolve_duration_seconds{cache_hit}`.
- Structured logs: `variable.set`, `variable.unset`, `variable.resolved`,
  `variable.trace_queried`, `variable.resolver_failover`,
  `variable.secret_dereferenced`.
- Trace spans: `variable.resolve`, `variable.trace`,
  `variable.set`, `variable.unset`, `variable.dereference_secret`.

## Open Questions

- Phase-1 blocker: is `pipeline_id` meaningful before Layer 6 lands?
  Decision: accept `NULL` pipeline_id and allow the scope chain to skip
  missing scopes. Revisit when Layer 6 ships.
- Should the trace API return only names the caller set, or all names
  visible? Decision: all visible names, with secret-value redaction.
  Re-confirm against UI wireframes before Phase 1 exit.
