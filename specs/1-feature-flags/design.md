# 1-feature-flags — Design

## Architecture

`1-feature-flags` lives under
`source/site/automojo/pychestrate/webservice/identity/flags/`. Its public
surface is one hot-path function — `flag_evaluator.evaluate_flag` — and
a small REST surface for lifecycle operations. The authoritative store
is a pair of tables in `0-persistence` (`feature_flags` +
`feature_flag_versions`); a process-local cache with a configurable
staleness window (default 60 seconds) fronts the hot path. A
`feature_flag_backend` factory protocol lets operators delegate matched
flag keys to external flag services, while the in-tree
`LocalDatabaseFeatureFlagBackend` serves everything else. Every
lifecycle operation publishes an `entity.flag.*` event that
`1-audit-log` records. This feature ships in
**Phase 1 — Identity & Projects** (UI slice lands in Phase 10 with
`9-admin-ui`).

## Data Model

`feature_flags` — current view of each flag:

- `flag_key: str` — PK.
- `flag_kind: FlagKind` — `{BOOLEAN, STRING, ENUM, PERCENTAGE}`.
- `current_version: int`.
- `state: FlagState` — `{ACTIVE, RETIRED}`.
- `retired_at: Optional[datetime]`,
  `grace_expires_at: Optional[datetime]`.
- `owner_user_id: UUID`, `created_at: datetime`,
  `updated_at: datetime`.

`feature_flag_versions` — immutable history:

- `version_id: UUID` — PK.
- `flag_key: str` — FK.
- `version: int`.
- `default_value: JSON` — encoded to flag kind.
- `rules_json: JSONB` — targeting rules + rollout percentage.
- `created_at: datetime`, `created_by: UUID`.

Unique on `(flag_key, version)`. Rules JSON shape (pseudo-schema):

```
{
    "rollout_percentage_bp": 2500,   // basis points (0..10000), PERCENTAGE
    "attribute_matches": [
        {"attr": "project_id", "equals": "<uuid>", "return": true}
    ],
    "enum_choices": ["off", "dark", "light"]  // ENUM only
}
```

`feature_flag_backend_registrations` — runtime registry view:

- `backend_name: str` — PK.
- `flag_key_pattern: str`, `precedence: int`,
  `last_health_at: datetime`, `healthy: bool`.

`feature_flag_eval_cache` (in-process, not persisted) — hashed by
`(flag_key, flag_version, bucketing_key)` with TTL equal to the
staleness window.

## Interfaces

### Public API

REST routes:

- `POST /api/v1/flags` — create.
- `GET /api/v1/flags` — list.
- `GET /api/v1/flags/{flag_key}` — read current.
- `GET /api/v1/flags/{flag_key}/history` — versions.
- `PATCH /api/v1/flags/{flag_key}` — update rollout rules (bumps
  version).
- `POST /api/v1/flags/{flag_key}/retire` — retire.
- `POST /api/v1/flags/{flag_key}/evaluate` — evaluate given context
  (used by `8-cli` and integration tests).

### Internal API

Module `automojo.pychestrate.webservice.identity.flags.flag_evaluator`:

```python
@dataclass(frozen=True)
class FlagContext:
    bucketing_key: str
    user_id: Optional[UUID]
    project_id: Optional[UUID]
    attributes: tuple[tuple[str, str], ...]


def evaluate_flag(
        *,
        flag_key: str,
        context: FlagContext,
        default: FlagValue
    ) -> FlagValue:
    """
        Evaluate a feature flag for the given context.

        :param flag_key: Registered flag key.
        :param context: Evaluation context with a stable `bucketing_key`.
        :param default: Returned if the flag is unknown or backend is exhausted.

        :returns: The flag's value for `context`.
        :raises: SemanticError on missing `bucketing_key`.
    """
    ...


def evaluate_boolean(
        *,
        flag_key: str,
        context: FlagContext,
        default: bool
    ) -> bool:
    """
        Type-safe wrapper for boolean flags.
    """
    ...
```

Module `automojo.pychestrate.webservice.identity.flags.flag_service`:

```python
def create_flag(
        *,
        flag_key: str,
        flag_kind: FlagKind,
        default_value: FlagValue,
        rules: FlagRules,
        actor_user_id: UUID
    ) -> Flag:
    """
        Persist a new flag at version 1.

        :raises: FlagAlreadyExistsError, SemanticError
    """
    ...


def update_flag_rules(
        *,
        flag_key: str,
        rules: FlagRules,
        actor_user_id: UUID
    ) -> Flag:
    """
        Persist a new version with updated rules.

        :raises: FlagNotFoundError, SemanticError on kind changes
    """
    ...


def retire_flag(
        *,
        flag_key: str,
        grace_seconds: int,
        actor_user_id: UUID
    ) -> Flag:
    """
        Mark a flag retired and schedule removal at grace end.
    """
    ...
```

Module `automojo.pychestrate.webservice.identity.flags.backend_router`:

```python
def resolve_backend(*, flag_key: str) -> FeatureFlagBackendProtocol:
    """
        Select backend by pattern match, breaking ties on PRECEDENCE.
    """
    ...
```

### Extension Surface

Factory protocol `feature_flag_backend` declared in
`automojo.pychestrate.webservice.identity.flags.factories.feature_flag_backend`:

```python
class FeatureFlagBackendProtocol(FactoryProtocolBase):
    factory_protocol_name: str = "feature_flag_backend"
    protocol_schema_version: int = 1

    @classmethod
    def backend_name(cls) -> str:
        ...

    @classmethod
    def flag_key_pattern(cls) -> str:
        """Glob claimed by this backend."""
        ...

    @classmethod
    def evaluate(
            cls,
            *,
            flag_key: str,
            context: FlagContext,
            default: FlagValue
        ) -> BackendEvaluation:
        ...

    @classmethod
    def list_flags(cls) -> tuple[FlagDescriptor, ...]:
        ...

    @classmethod
    def health_check(cls) -> BackendHealth:
        ...
```

Reference implementation: `LocalDatabaseFeatureFlagBackend` at
`PRECEDENCE = 1000`, claiming `flag_key_pattern = "*"`.

### Events Emitted

- `entity.flag.created` — `{flag_key, version, default_value, actor_user_id, created_at}`
- `entity.flag.updated` — `{flag_key, old_version, new_version, actor_user_id, updated_at}`
- `entity.flag.retired` — `{flag_key, actor_user_id, retired_at, grace_expires_at}`
- `entity.flag.removed` — `{flag_key, removed_at}` (grace end)
- `entity.flag.backend.unhealthy` — `{backend_name, reason, at}`
- `entity.flag.backend.healthy` — `{backend_name, at}`

### Events Consumed

- `entity.audit.sink.unhealthy` — pauses lifecycle writes (lifecycle
  rows must be audit-backed).
- `entity.user.deactivated` — invalidates cached attribute matches
  keyed on that user.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/identity/flags/
    __init__.py
    flag_evaluator.py             # evaluate_flag, evaluate_boolean
    flag_service.py               # create, update, retire
    backend_router.py             # resolve_backend
    cache.py                      # staleness-window cache
    rules.py                      # rule evaluation + percentage rollout hashing
    models.py                     # Flag, FlagVersion, FlagRules, FlagContext
    factories/
        feature_flag_backend.py
        local_backend.py          # LocalDatabaseFeatureFlagBackend
    restapi/
        v1/
            flags_controller.py
    events.py
    exceptions.py
```

## Key Flows

**Evaluate (hot path):**

1. Caller constructs a `FlagContext(bucketing_key=user_id_str, ...)`.
2. `flag_evaluator.evaluate_flag` looks up the cache keyed on
   `(flag_key, flag_version, bucketing_key)`; on hit, returns.
3. On miss, resolves backend via `backend_router`, calls
   `backend.evaluate(...)`, stores the result in cache with the
   staleness-window TTL, increments
   `pychestrate_flags_evaluations_total`.
4. If the backend raises `FeatureFlagBackendTransientError`, the
   evaluator returns the last-good cached value if available; if
   the last-good entry is older than the staleness window, returns
   `default` and increments
   `pychestrate_flags_backend_errors_total`.

**Create/Update:**

1. Admin hits `POST /api/v1/flags` or PATCH.
2. `flag_service` writes the `feature_flags` row and a
   `feature_flag_versions` row in a single transaction with an
   outbox entry.
3. Commit publishes `entity.flag.created|updated`; subscribers
   include `1-audit-log` and the cache invalidator.

**Backend Health Degradation:**

1. Periodic health prober calls `backend.health_check()` every
   30 seconds.
2. After three consecutive failures, publishes
   `entity.flag.backend.unhealthy` and marks the registration row.
3. `backend_router` continues to route to the backend for pattern
   matching, but the evaluator prefers last-good cache for up to
   the staleness window.

## Error Handling

- `SemanticError` — raised on missing `bucketing_key`, on
  attempting to change `flag_key` / `flag_kind`, or on malformed
  rules. NEVER caught internally.
- `FlagAlreadyExistsError` — HTTP 409.
- `FlagNotFoundError` — HTTP 404 on update/retire/read.
- `FeatureFlagBackendTransientError` — caught and reclassified
  with context in the evaluator; falls back to cache or `default`
  per NFR-4.
- `ConfigurationError` — raised at startup if no backend matches
  `*`.

Multi-line messages per AGENTS.md:

```python
err_msg_lines = ["Feature flag evaluation context missing bucketing_key."]
err_msg_lines.append("FLAG_KEY: {}".format(flag_key))
err_msg_lines.append("CONTEXT_ATTRIBUTES: {}".format(sorted(context.attributes)))
err_msg = os.linesep.join(err_msg_lines)
raise SemanticError(err_msg) from None
```

## Security Considerations

- `system:flags.admin` for create/update/retire;
  `system:flags.read` for list/read.
- Flag rules SHALL NOT contain plaintext secrets; rules may
  reference a `secret_ref` that the evaluator resolves via
  `1-secrets-vault` at evaluation time under the service's own
  principal.
- Backend credentials (e.g., LaunchDarkly SDK key) live in
  `1-secrets-vault` under `system:flags.backend.<name>`.
- Every lifecycle change emits an `entity.flag.*` event that
  `1-audit-log` captures — there is no bypass path.

## Observability

Metrics:

- `pychestrate_flags_evaluations_total{flag_key,outcome}` (`outcome
  ∈ {hit,miss,error,unknown,default_fallback}`)
- `pychestrate_flags_evaluation_duration_seconds{flag_key}` (histogram)
- `pychestrate_flags_unknown_total{flag_key}`
- `pychestrate_flags_backend_errors_total{backend,kind}`
- `pychestrate_flags_active` (gauge)
- `pychestrate_flags_cache_stale_served_total`

Log events: `flag.created`, `flag.updated`, `flag.retired`,
`flag.removed`, `flag.evaluated` (sampled at 1/1000),
`flag.backend.unhealthy`, `flag.backend.healthy`,
`flag.backend.override`.

Trace spans: `flags.evaluate`, `flags.backend.call`,
`flags.cache.resolve`, `flags.rules.match`.

## Open Questions

- Do we support scheduled rollouts (e.g., "ramp to 50% at
  2025-06-01T00:00Z")? Proposed: add a `scheduled_changes` array
  on `FlagRules` in a follow-up; keep the initial Phase 1 shape
  simple.
- Targeting by group vs. by explicit user list — which comes
  first? Proposed: attribute matches on `project_id`, `user_id`,
  `group_ids` tuple. Richer targeting belongs in an external
  backend.
- Eval telemetry privacy: do we emit `flag.evaluated` with
  `bucketing_key` present, or hashed? Default to hashed in Phase 1.
