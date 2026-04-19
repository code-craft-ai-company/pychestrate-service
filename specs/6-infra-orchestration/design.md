# 6-infra-orchestration — Design

## Architecture

`6-infra-orchestration` is the infra-domain orchestrator. It persists
`InfraRun` entities, invokes `6-blast-radius-guards.allow(...)` for
destructive actions, binds runs to `6-environment-registry`
environments, and dispatches jobs via the existing Layer 5 plane —
no new dispatcher. Plan/apply is modeled explicitly: `plan` produces
a stored plan summary + plan file reference; `apply_planned`
re-dispatches using that reference inside a validity window. Drivers
are contributed via `infra_tool_driver` — Terraform, Pulumi, Ansible,
and custom tools each supply their own envelope shape. Ships in
Phase 7.

## Data Model

Tables in `0-persistence`:

- `infra_run`:
  - `run_id: UUID` PK
  - `project_id: UUID`
  - `environment_id: UUID`
  - `driver_name: str`
  - `action: InfraAction` — `{plan, apply, destroy}`
  - `state: InfraRunState` — mirrors Layer 5 + `rejected_by_guard`
  - `trigger_cause: TriggerCause`
  - `actor_role_set: list[str]` — captured at trigger time
  - `inputs_canonical_json: bytes`
  - `plan_summary_ref: str | None` — object-store key
  - `plan_artifact_ref: str | None` — the encrypted plan file
  - `plan_diff_digest: bytes(32) | None`
  - `plan_issued_at: datetime | None`
  - `replay_of: UUID | None` — for `apply_planned`
  - `output_digest_sha256: bytes(32) | None`
  - `client_local_run_id: str | None`
  - `started_at, finished_at, final_state_reason`
- `infra_guard_decision_cache`:
  - `(project_id, environment_id, action, actor_role_set_digest) PK`
  - `decision: bool`
  - `failing_rule_id: str | None`
  - `decided_at: datetime`
  - TTL 60 s.

Indices: `(project_id, environment_id, state)`, `(replay_of)`, `(driver_name, state)`.

Value types:

- `InfraInputs` — driver-specific dict.
- `PlanSummary` — `{resources_to_add: int, resources_to_change: int, resources_to_destroy: int, resource_list: list[ResourceOp]}`.
- `ResourceOp` — `{resource_address, op: "add"|"change"|"destroy"|"no_op", module_path}`.

## Interfaces

### Public API

REST under `8-rest-api-v1`:

- `POST /api/v1/projects/{project_id}/infra-runs` body `{environment_id, driver_name, action, inputs}` → `InfraRunView`.
- `GET /api/v1/projects/{project_id}/infra-runs/{run_id}`.
- `POST /api/v1/projects/{project_id}/infra-runs/{run_id}:cancel`.
- `POST /api/v1/projects/{project_id}/infra-runs/{plan_run_id}:apply-planned` → new apply `InfraRunView`.

### Internal API

```python
class InfraOrchestrator:
    def __init__(
        self,
        runs_repo: InfraRunRepository,
        dispatcher: JobDispatcher,
        envelope_builder: JobEnvelopeBuilder,
        shared_results: SharedResultsBackend,
        driver_registry: InfraToolDriverRegistry,
        guards: BlastRadiusGuards,
        env_registry: EnvironmentRegistry,
        variable_resolver: VariableResolver,
        rbac: RbacService,
        audit: AuditLog,
        bus: MessageBus,
        clock: Clock,
        config: InfraConfig
    ) -> None:
        self._runs_repo = runs_repo
        self._dispatcher = dispatcher
        self._envelope_builder = envelope_builder
        self._shared_results = shared_results
        self._driver_registry = driver_registry
        self._guards = guards
        self._env_registry = env_registry
        self._variable_resolver = variable_resolver
        self._rbac = rbac
        self._audit = audit
        self._bus = bus
        self._clock = clock
        self._config = config
        return

    def trigger_run(
        self,
        actor_id: UUID,
        project_id: UUID,
        driver_name: str,
        environment_id: UUID,
        action: InfraAction,
        inputs: InfraInputs,
        trigger_cause: TriggerCause,
        aspects: TriggerAspects | None = None
    ) -> InfraRunView:
        """
            Create an InfraRun and dispatch via Layer 5 with guard gating
            for destructive actions.

            :returns: InfraRunView.
            :raises: AuthorizationError, GuardDeniedError,
                     FrozenEnvironmentError, SemanticError
        """
        ...

    def apply_planned(
        self,
        actor_id: UUID,
        plan_run_id: UUID,
        aspects: ApplyPlannedAspects | None = None
    ) -> InfraRunView:
        """
            Promote a prior plan to an apply.

            :returns: InfraRunView for the new apply.
            :raises: AuthorizationError, GuardDeniedError,
                     FrozenEnvironmentError, PlanExpiredError,
                     UnsupportedOperationError
        """
        ...

    def cancel_run(
        self,
        actor_id: UUID,
        run_id: UUID,
        reason: str
    ) -> InfraRunView:
        """
            Request cancellation via 5-cancel-reconcile.

            :returns: InfraRunView.
            :raises: AuthorizationError, SemanticError
        """
        ...

    def apply_layer5_state_event(
        self,
        run_id: UUID,
        event: RunStateEvent
    ) -> None:
        """
            Mirror Layer 5 transitions onto InfraRun; on apply-success,
            record the new environment state.

            :returns: None.
            :raises: SemanticError
        """
        ...
```

### Extension Surface

Factory protocol declared here:

```python
class InfraToolDriverProtocol(FactoryProtocolBase):
    factory_protocol_name: str = "infra_tool_driver"

    @classmethod
    def driver_name(cls) -> str: ...

    @classmethod
    def build_job_envelope(
        cls,
        run_id: UUID,
        project_id: UUID,
        environment_id: UUID,
        action: InfraAction,
        inputs: InfraInputs,
        plan_artifact_ref: str | None,
        result_root_key: str
    ) -> JobEnvelope: ...

    @classmethod
    def validate_inputs(cls, inputs: InfraInputs) -> None: ...

    @classmethod
    def parse_plan_summary(cls, plan_bytes: bytes) -> PlanSummary: ...

    @classmethod
    def compute_plan_diff_digest(cls, plan_bytes: bytes) -> bytes: ...

    @classmethod
    def capability_requirements(cls, inputs: InfraInputs) -> list[str]: ...

    @classmethod
    def capabilities(cls) -> InfraDriverCapabilities: ...  # supports_plan_replay, supports_destroy
```

Reference implementations under
`source/site/automojo/factories/pychestrate/infra/`:

- `TerraformInfraDriver` — `PRECEDENCE = 500`; supports plan replay.
- `PulumiInfraDriver` — `PRECEDENCE = 500`.
- `AnsibleInfraDriver` — `PRECEDENCE = 500`; `supports_plan_replay = False`.

### Events Emitted

- `entity.infra.run_started` — `{run_id, project_id, environment_id, driver_name, action}`
- `entity.infra.run_completed` — `{run_id, final_state, action, environment_id, plan_diff_digest}`
- `entity.infra.plan.promoted` — `{plan_run_id, apply_run_id}`
- `entity.infra.guard.denied` — `{project_id, environment_id, action, rule_id}`
- `entity.infra.frozen.rejected` — `{project_id, environment_id, action}`

### Events Consumed

- `entity.run.state_changed|completed|failed|cancelled` — mirror onto InfraRun.
- `entity.env.frozen|unfrozen` — invalidate guard cache for the affected environment.
- `extension.reloaded` — refresh driver registry.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/orchestration/infra/`:

- `__init__.py`
- `orchestrator.py` — `InfraOrchestrator`.
- `repository.py` — `InfraRunRepository`.
- `state_mirror.py` — Layer 5 subscriber.
- `plan_window.py` — plan validity and reference resolution.
- `driver_protocol.py` — `InfraToolDriverProtocol`.
- `driver_registry.py`.
- `aspects.py` — `TriggerAspects`, `ApplyPlannedAspects`.
- `errors.py` — `GuardDeniedError`, `FrozenEnvironmentError`, `PlanExpiredError`.
- `rest/v1_routes.py`.

Factories under `source/site/automojo/factories/pychestrate/infra/`.

## Key Flows

### Flow 1 — Plan

1. `POST /infra-runs` with `action="plan"` → `InfraOrchestrator.trigger_run(...)`.
2. RBAC `infra.run.trigger:plan`; env lookup; frozen check does not apply to plan.
3. Driver resolved; `validate_inputs`; capability check against target pod.
4. `shared_results.allocate(...)` → `result_root_key`; envelope built (no plan ref).
5. Dispatch via `JobDispatcher`.
6. On terminal, `state_mirror` reads `plan_summary.json` and `plan.bin` from result root; stores `plan_summary_ref`, `plan_artifact_ref`, `plan_diff_digest`.

### Flow 2 — Apply planned

1. `POST /.../apply-planned` → `InfraOrchestrator.apply_planned(...)`.
2. RBAC `infra.run.trigger:apply`.
3. Guard: `guards.allow(actor_role_set, environment_id, "apply")` — deny → `GuardDeniedError(rule_id)`.
4. Frozen-env check; plan validity check (else `PlanExpiredError`).
5. Driver `supports_plan_replay` — else `UnsupportedOperationError`.
6. New `InfraRun(action="apply", replay_of=plan_run_id, plan_artifact_ref=<same ref>)`; dispatch.
7. On terminal success, `env_registry.record_apply(...)`.

### Flow 3 — Destroy

1. `POST /infra-runs` with `action="destroy"`.
2. Same flow as apply but with stricter guard (`action=destroy`).
3. On success, `env_registry.mark_destroyed(...)`.

## Error Handling

- `GuardDeniedError`: 403 with multiline body (`rule_id`, guard description, actor roles).
- `FrozenEnvironmentError`: 409.
- `PlanExpiredError`: 409, include elapsed seconds.
- `UnsupportedOperationError`: 501.
- `SemanticError`: unknown env, unknown driver, bad inputs → 400.
- `ConfigurationError`: bubble to host.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- Plan bytes encrypted-at-rest using object-store driver capabilities; access gated by `infra.plan.read`.
- `actor_role_set` snapshotted at trigger time to prevent role-revocation race during promote.
- All destructive actions audit-logged with `environment_id`, `driver_name`, `plan_diff_digest`.
- Rate limit per project `max_infra_triggers_per_minute_per_project` (default 30).

## Observability

Metrics:

- `pychestrate_infra_runs_total{project,driver,action,final_state}` — counter
- `pychestrate_infra_run_duration_seconds{project,driver,action}` — histogram
- `pychestrate_infra_guard_denies_total{project,rule_id}` — counter
- `pychestrate_infra_plan_apply_promotions_total{project,outcome}` — counter
- `pychestrate_infra_plan_expired_total{project}` — counter
- `pychestrate_infra_frozen_rejects_total{project}` — counter

Log events: `pychestrate.infra.run.triggered`, `pychestrate.infra.run.completed`, `pychestrate.infra.guard.denied`, `pychestrate.infra.plan.promoted`, `pychestrate.infra.frozen.rejected`, `pychestrate.infra.plan.expired`.

Trace spans: `pychestrate.infra.trigger`, `pychestrate.infra.guard_check`, `pychestrate.infra.apply_planned`, `pychestrate.infra.state_mirror_update`.

## Open Questions

- Plan validity window — 900 s vs 3600 s default. Timebox: Phase 7 midpoint.
- Do we require two-person apply for `destroy` in high-risk envs, or leave that to guards? Timebox: Phase 7 exit.
- Driver capability polymorphism for custom actions beyond plan/apply/destroy (e.g., `taint`). Timebox: Phase 7 exit.
