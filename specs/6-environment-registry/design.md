# 6-environment-registry — Design

## Architecture

`6-environment-registry` is a declarative catalog. It owns the
`environment` table, the current-version pointer state, and the
`EnvironmentKindExtension` resource surface. It exposes a small,
consistent API used by `6-infra-orchestration` (to bind a run to an
env), `6-drift-detection` (to enumerate envs to check), and
`6-blast-radius-guards` (to read env attributes during rule
evaluation). Ships in Phase 7. Authoritative source of truth for
declaration state is the table; infra state itself lives in the infra
tool's backend (Terraform state, etc.).

## Data Model

Tables in `0-persistence`:

- `environment`:
  - `environment_id: UUID` PK
  - `project_id: UUID`
  - `kind_name: str`
  - `name: str`
  - `state: EnvironmentState` — `{active, frozen, archived, destroyed}`
  - `attrs_json: bytes` — validated against kind schema
  - `frozen_by: UUID | None`
  - `frozen_reason: str | None`
  - `frozen_at: datetime | None`
  - `last_applied_run_id: UUID | None`
  - `last_output_digest: bytes(32) | None`
  - `last_applied_at: datetime | None`
  - `archived_reason: str | None`
  - `archived_at: datetime | None`
  - `destroyed_at: datetime | None`
  - `created_at, updated_at`
  - Unique `(project_id, kind_name, name)` when `require_unique_kind_names` is true.

- `environment_probe_assignment`:
  - `(environment_id, probe_id)` PK
  - `added_by: UUID`
  - `added_at: datetime`

- `environment_guard_assignment`:
  - `(environment_id, guard_rule_id)` PK
  - `added_by: UUID`
  - `added_at: datetime`

- `environment_history`:
  - `(environment_id, history_id: BIGSERIAL)` PK
  - `event_kind: str` — `declared|archived|frozen|unfrozen|applied|destroyed`
  - `actor_id: UUID | None`
  - `run_id: UUID | None`
  - `payload_json: bytes`
  - `at: datetime`

Indices: `(project_id, kind_name)`, `(project_id, state)`, `(project_id, name varchar_pattern_ops)`.

Value types:

- `EnvironmentView`, `HealthProbeSpec`, `GuardRuleRef`.

## Interfaces

### Public API

REST under `8-rest-api-v1`:

- `POST /api/v1/projects/{project_id}/environments` body `{name, kind_name, attrs}` → `EnvironmentView`.
- `GET /api/v1/projects/{project_id}/environments?kind=&state=&limit=&cursor=` → list.
- `GET /api/v1/projects/{project_id}/environments/{environment_id}`.
- `POST /api/v1/projects/{project_id}/environments/{environment_id}:archive` body `{reason}`.
- `POST /api/v1/projects/{project_id}/environments/{environment_id}:freeze` body `{reason}`.
- `POST /api/v1/projects/{project_id}/environments/{environment_id}:unfreeze` body `{reason}`.
- `PATCH /api/v1/projects/{project_id}/environments/{environment_id}/attrs` body `{attrs}`.

### Internal API

```python
class EnvironmentRegistry:
    def __init__(
        self,
        repo: EnvironmentRepository,
        kind_registry: EnvironmentKindRegistry,
        rbac: RbacService,
        audit: AuditLog,
        bus: MessageBus,
        clock: Clock
    ) -> None:
        self._repo = repo
        self._kind_registry = kind_registry
        self._rbac = rbac
        self._audit = audit
        self._bus = bus
        self._clock = clock
        return

    def declare(
        self,
        actor_id: UUID,
        project_id: UUID,
        name: str,
        kind_name: str,
        attrs: dict[str, object]
    ) -> EnvironmentView:
        """
            :returns: EnvironmentView.
            :raises: AuthorizationError, SemanticError
        """
        ...

    def list(
        self,
        project_id: UUID,
        kind_name: str | None,
        state: EnvironmentState | None,
        limit: int,
        cursor: str | None
    ) -> ListPage[EnvironmentView]:
        ...

    def get(
        self,
        environment_id: UUID
    ) -> EnvironmentView:
        ...

    def archive(
        self,
        actor_id: UUID,
        environment_id: UUID,
        reason: str
    ) -> EnvironmentView:
        ...

    def freeze(
        self,
        actor_id: UUID,
        environment_id: UUID,
        reason: str
    ) -> EnvironmentView:
        ...

    def unfreeze(
        self,
        actor_id: UUID,
        environment_id: UUID,
        reason: str
    ) -> EnvironmentView:
        ...

    def record_apply(
        self,
        environment_id: UUID,
        run_id: UUID,
        output_digest_sha256: bytes
    ) -> None:
        """
            Called by 6-infra-orchestration on successful apply.

            :returns: None.
            :raises: SemanticError
        """
        ...

    def mark_destroyed(
        self,
        environment_id: UUID,
        run_id: UUID
    ) -> None:
        ...

    def is_frozen(
        self,
        environment_id: UUID
    ) -> bool:
        ...

    def set_probes(
        self,
        actor_id: UUID,
        environment_id: UUID,
        probes: list[HealthProbeSpec]
    ) -> EnvironmentView:
        ...

    def set_guards(
        self,
        actor_id: UUID,
        environment_id: UUID,
        guards: list[GuardRuleRef]
    ) -> EnvironmentView:
        ...
```

### Extension Surface

Resource extension declared here:

```python
class EnvironmentKindExtension(ResourceExtension):
    """
        Declares a new kind of environment.
    """
    kind_name: str
    attrs_schema: dict  # JSON Schema

    @classmethod
    def default_probes(cls) -> list[HealthProbeSpec]:
        ...

    @classmethod
    def default_guards(cls) -> list[GuardRuleRef]:
        ...

    @classmethod
    def describe(cls) -> KindDescription:
        ...
```

Reference kinds shipped in-tree under
`source/site/ccai/extensions/pychestrate/environment_kind/`:

- `K8sClusterEnvironmentKind` — schema includes `cluster_name`, `region`, `kubeconfig_secret_ref`.
- `VmPoolEnvironmentKind` — `pool_name`, `region`, `hypervisor_type`.
- `CloudAccountEnvironmentKind` — `provider`, `account_id`, `default_region`.
- `DatabaseServiceEnvironmentKind` — `engine`, `version`, `endpoint_secret_ref`.

### Events Emitted

- `entity.env.declared` — `{environment_id, project_id, kind_name, name}`
- `entity.env.archived` — `{environment_id, reason, actor_id}`
- `entity.env.frozen` — `{environment_id, reason, actor_id}`
- `entity.env.unfrozen` — `{environment_id, actor_id}`
- `entity.env.applied` — `{environment_id, run_id, output_digest_sha256}`
- `entity.env.destroyed` — `{environment_id, run_id}`

### Events Consumed

- `extension.reloaded` — refresh kind registry.
- `entity.project.archived` — cascade archive environments.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/orchestration/infra/environment/`:

- `__init__.py`
- `registry.py` — `EnvironmentRegistry`.
- `repository.py` — `EnvironmentRepository`.
- `kind_protocol.py` — `EnvironmentKindExtension`.
- `kind_registry.py` — extension-host accessor.
- `history.py` — append-only history writes.
- `errors.py` — `EnvironmentNotFoundError`, `KindNotFoundError`.
- `rest/v1_routes.py`.

Kind extensions under `source/site/ccai/extensions/pychestrate/environment_kind/`.

## Key Flows

### Flow 1 — Declare an environment

1. REST POST → `EnvironmentRegistry.declare(...)`.
2. RBAC `env.declare` checked.
3. Kind looked up; `attrs` validated against schema.
4. Environment row inserted; default probes + guards attached.
5. `environment_history` row written.
6. `entity.env.declared` emitted.

### Flow 2 — Record apply (internal)

1. `InfraOrchestrator` calls `record_apply(env_id, run_id, digest)` inside its state-mirror completion path.
2. Row locked; monotonicity check: accept only if `(applied_at, run_id) > stored`.
3. Pointer + history updated; `entity.env.applied` emitted.

### Flow 3 — Freeze / unfreeze

1. REST freeze → `freeze(...)`.
2. RBAC `env.admin` or `env.admin:<kind>`.
3. State → `frozen`; `frozen_by`, `frozen_reason`, `frozen_at` set.
4. `entity.env.frozen` emitted; `6-infra-orchestration` invalidates its guard decision cache.

## Error Handling

- `SemanticError`: schema validation, archived-env modification, duplicate `(kind_name, name)` when required → bubble.
- `AuthorizationError`: 403.
- `EnvironmentNotFoundError` / `KindNotFoundError`: 404.
- `ConfigurationError`: bubble for kind-schema loader failures.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- Sensitive attributes held as `_secret_ref` fields that are validated but not stored expanded; resolution occurs only in callers (drivers, probes) with proper `SecretsAccessor`.
- `env.admin` RBAC guards mutation.
- Audit entries written for declare/archive/freeze/unfreeze/set_probes/set_guards/record_apply.

## Observability

Metrics:

- `pychestrate_infra_environments_total{project,kind,state}` — gauge
- `pychestrate_infra_env_declare_duration_seconds{project}` — histogram
- `pychestrate_infra_env_freeze_changes_total{project,direction}` — counter
- `pychestrate_infra_env_record_apply_total{project,kind}` — counter
- `pychestrate_infra_env_attribute_schema_failures_total{project,kind}` — counter

Log events: `pychestrate.infra.env.declared`, `pychestrate.infra.env.archived`, `pychestrate.infra.env.frozen`, `pychestrate.infra.env.unfrozen`, `pychestrate.infra.env.record_apply`, `pychestrate.infra.env.destroyed`.

Trace spans: `pychestrate.infra.env.declare`, `pychestrate.infra.env.record_apply`, `pychestrate.infra.env.freeze`, `pychestrate.infra.env.list`.

## Open Questions

- Multi-region environment dedup — a `prod-eu` and `prod-us` kind share `prod` semantics; expose a parent-id or just relation via tags? Timebox: Phase 7 midpoint.
- Archived vs destroyed semantics when re-declaring same `(kind_name, name)` — accept or require unique across history? Timebox: Phase 7 exit.
- Expose `attrs` patch with partial update semantics (merge) or replace? Timebox: Phase 7 exit.
