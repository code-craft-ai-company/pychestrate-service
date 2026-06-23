# 3-dynamic-pods — Design

## Architecture

Dynamic Pods live at
`source/site/ccai/pychestrate/webservice/pods/dynamic/`. The feature
owns three concepts that pod-definitions does not:

- **Template** — a parameterized description from which a concrete `PodSpec`
  is rendered.
- **Materialization** — the durable, checkpointable process of rendering a
  template, reserving resources, provisioning members, and enrolling the
  client.
- **Provisioner** — the pluggable runtime that knows how to bring a member
  up (and down). Selected per member kind through the `pod_provisioner`
  factory protocol.

The feature is a state-machine driver more than a REST CRUD surface. Each
materialization is a long-running job tracked in
`dynamic_pod_materialization`; its state is updated by a worker in the
`pods.dynamic.worker` module. On service restart the worker resumer picks
up any materialization not in a terminal state and continues. All resource
reservations go through `4-checkout-checkin`. The final step — bringing up
the client — reuses `3-client-enrollment` to issue a bootstrap token and
then waits for the client to enroll + register the static pod per
`3-static-pods` before transitioning to `state=ready` via `3-pod-lifecycle`.

## Data Model

```
pod_template
    template_id:            UUID     primary key
    project_id:             UUID     foreign key -> project
    name:                   str      not null
    template_kind:          str      not null   -- PodTemplateExtension.template_kind_name
    source_version:         int      not null default 1
    source_json:            jsonb    not null   -- the parameterized spec
    parameter_schema:       jsonb    not null
    created_by:             UUID
    created_at:             datetime
    (project_id, name) unique

dynamic_pod_materialization
    materialization_id:     UUID     primary key
    template_id:            UUID     foreign key -> pod_template
    template_source_version:int      not null
    parameters_json:        jsonb    not null
    rendered_spec_json:     jsonb    nullable  -- populated after render
    pod_id:                 UUID     nullable  -- foreign key -> pod_definition once created
    state:                  MaterializationState not null
    current_step:           str      nullable
    error_summary:          jsonb    nullable
    reservation_ids:        jsonb    not null default '[]'
    requested_by:           UUID
    requested_at:           datetime
    ready_at:               datetime nullable
    released_at:            datetime nullable
    orphaned_reason:        str      nullable
    (state) index
    (template_id) index
```

Enumeration (`pods/dynamic/enums.py`):

```
class MaterializationState(str, Enum):
    PENDING = "pending"
    RENDERING = "rendering"
    RESERVING = "reserving"
    PROVISIONING = "provisioning"
    AWAITING_CLIENT = "awaiting_client"
    READY = "ready"
    DRAINING = "draining"
    TEARING_DOWN = "tearing_down"
    RELEASED = "released"
    ORPHANED = "orphaned"
    FAILED_ROLLED_BACK = "failed_rolled_back"
```

## Interfaces

### Public API

REST (RBAC `pod.template.*` + `pod.dynamic.*`):

- `POST /api/v1/projects/{project_id}/pod-templates` — create template.
- `GET /api/v1/projects/{project_id}/pod-templates` — list.
- `POST /api/v1/projects/{project_id}/pod-templates/{template_id}:materialize`
  — start materialization; body is a parameter object.
- `GET /api/v1/projects/{project_id}/materializations/{materialization_id}`
  — view state + progress.
- `POST /api/v1/projects/{project_id}/materializations/{materialization_id}:release`
  — drain + teardown.

### Internal API

```python
def start_materialization(
    *,
    project_id: UUID,
    template_id: UUID,
    parameters: Mapping[str, Any],
    requested_by: UUID,
) -> MaterializationHandle:
    ...


def advance_materialization(
    *,
    materialization_id: UUID,
) -> MaterializationState:
    ...


def release_materialization(
    *,
    materialization_id: UUID,
    requested_by: UUID,
) -> None:
    ...


def render_template(
    *,
    template: PodTemplate,
    parameters: Mapping[str, Any],
) -> PodSpec:
    ...


def plan_provisioning(
    *,
    spec: PodSpec,
) -> Sequence[ProvisioningStep]:
    ...
```

### Extension Surface

Factory protocol:

```python
class PodProvisionerProtocol(FactoryProtocolBase):
    factory_protocol_name = "pod_provisioner"
    protocol_schema_version = 1
    required_capabilities = ("dispatch:jobs", "net:outbound")

    @classmethod
    def provision(
        cls,
        *,
        member: RenderedMember,
        pod_context: DynamicPodContext,
    ) -> ProvisionOutcome:
        ...

    @classmethod
    def teardown(
        cls,
        *,
        member: RenderedMember,
        pod_context: DynamicPodContext,
    ) -> TeardownOutcome:
        ...

    @classmethod
    def supported_member_kinds(cls) -> Sequence[str]:
        ...
```

Reference in-tree implementations (under
`source/site/ccai/pychestrate/factories/pod_provisioner/`):

- `LibvirtProvisioner` (`PRECEDENCE=100`) — local VM farm.
- `TerraformProvisioner` (`PRECEDENCE=110`) — wraps a `terraform apply`
  cycle through `6-infra-orchestration`.

Resource extension:

```python
class PodTemplateExtension(ResourceExtension):
    """
        Declares a template kind, its parameter schema, and its rendering
        convention.
    """

    template_kind_name: ClassVar[str]
    parameter_schema: ClassVar[JsonSchema]
    rendering_engine: ClassVar[str]  # e.g. "jinja2_sandboxed", "json_substitute"
```

In-tree kinds: `Jinja2SandboxedTemplate`, `JsonSubstituteTemplate`.

### Events Emitted

```
entity.pod.materialization_started     { materialization_id, template_id }
entity.pod.materialization_render_ok   { materialization_id, pod_id }
entity.pod.materialization_reserved    { materialization_id, reservation_ids }
entity.pod.provision_step_started      { materialization_id, step_name }
entity.pod.provision_step_completed    { materialization_id, step_name }
entity.pod.provision_step_failed       { materialization_id, step_name, error }
entity.pod.ready                       { materialization_id, pod_id }
entity.pod.teardown_step_started       { materialization_id, step_name }
entity.pod.teardown_step_completed     { materialization_id, step_name }
entity.pod.teardown_failed             { materialization_id, step_name, error }
entity.pod.released                    { materialization_id, pod_id }
entity.pod.orphaned                    { materialization_id, reason }
```

### Events Consumed

- `entity.pod.registered` (from `3-static-pods`) — awaited during
  `AWAITING_CLIENT`.
- `entity.client.enrolled` (from `3-client-enrollment`) — awaited during
  `AWAITING_CLIENT`.
- `entity.reservation.released` (from `4-checkout-checkin`) — correlated
  with teardown.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/pods/dynamic/
    __init__.py
    enums.py
    dtos.py                      -- PodTemplate, RenderedMember, ProvisioningStep,
                                    DynamicPodContext, MaterializationHandle, …
    templates.py                 -- template CRUD service
    render.py                    -- sandboxed rendering (Jinja2, JSON substitute)
    plan.py                      -- plan_provisioning (topological sort with client-last)
    worker.py                    -- state-machine driver (async task)
    resume.py                    -- restart resumer
    service.py                   -- start/advance/release public surface
    repository.py                -- PodTemplateRepository, MaterializationRepository
    rest.py                      -- REST router
    metrics.py

source/site/ccai/pychestrate/factories/pod_provisioner/
    libvirt.py                   -- PRECEDENCE=100
    terraform.py                 -- PRECEDENCE=110

source/site/ccai/pychestrate/extensions/pod_template_kinds/
    jinja2_sandboxed.py
    json_substitute.py
```

## Key Flows

**Materialize request.** `POST ...:materialize` -> `service.start_materialization`
writes `dynamic_pod_materialization{state=PENDING}` and enqueues an internal
job; REST returns handle. The worker picks up PENDING, transitions through
RENDERING (render_template, validate as a `PodSpec`), RESERVING (acquire
reservations for each member needing a resource), PROVISIONING (iterate
`plan_provisioning` — **non-client members first, client last**, calling the
matching `pod_provisioner` factory for each), AWAITING_CLIENT (waits for
`entity.client.enrolled` + `entity.pod.registered`), and READY.

**Failure rollback.** If any step fails, the worker transitions to
`TEARING_DOWN`, iterates completed steps in reverse, and calls
`pod_provisioner.teardown` for each. On final success state becomes
`FAILED_ROLLED_BACK`; on any teardown failure exceeding retry budget,
state becomes `ORPHANED` with `orphaned_reason` populated and an
operator alert fires via `2-notification-hub`.

**Release.** `POST ...:release` transitions state to `DRAINING`; once
`3-pod-lifecycle` confirms no in-flight runs, worker runs teardown in
reverse and ends at `RELEASED`.

**Restart-safe resume.** On service startup, `resume.py` scans
`dynamic_pod_materialization WHERE state IN {non-terminal}` and re-enqueues
each; the worker re-enters at the last recorded step.

## Error Handling

- `TemplateRenderError` (subclass of domain error) — caught at REST
  boundary, returned as HTTP 422.
- `ReservationUnavailable` — caught at worker boundary, materialization
  transitions to `FAILED_ROLLED_BACK` with reason captured; partial
  reservations released.
- `ProvisionerFailed` — caught at worker; triggers rollback.
- `TeardownFailed` — caught at worker; retried up to
  `teardown_max_attempts`; on final failure state becomes `ORPHANED`.
- `SandboxViolation` — raised if a template tries to access a disallowed
  binding. Never caught; surfaces as `SemanticError` subclass.
- `ConfigurationError` — raised if required provisioner factory for a
  member kind is not registered. Materialization fails at plan time.
- Multiline error messages per AGENTS.md with `os.linesep.join([...])`.

## Security Considerations

- Template rendering runs in a **sandboxed Jinja2** environment: no
  filesystem, no network, no imports; a static allowlist of filters and
  globals.
- Templates with secret-typed parameters read through
  `3-pod-scoped-config` / `1-secrets-vault` and are never echoed in logs
  or audit entries; the audit entry carries a SHA256 of the resolved
  parameter set with secrets blanked.
- `pod_provisioner` extensions require explicit `dispatch:jobs` and/or
  `net:outbound` capabilities granted by `E-extension-sandbox` at
  installation time. The registry refuses to call a provisioner missing
  these capabilities.
- REST permissions: `pod.template.read|write`, `pod.dynamic.materialize`,
  `pod.dynamic.release`, `pod.dynamic.admin` (covers orphaned-pod
  cleanup).

## Observability

Metrics:

- `pychestrate_pod_materializations_total{outcome}` — counter.
- `pychestrate_pod_materialization_state_gauge{state}` — gauge.
- `pychestrate_pod_provision_duration_seconds{phase,member_kind}` —
  histogram.
- `pychestrate_pod_teardown_duration_seconds{member_kind}` — histogram.
- `pychestrate_pod_orphaned_gauge` — gauge.
- `pychestrate_pod_render_duration_seconds` — histogram.

Log events: `pychestrate_pod_materialize_start`,
`pychestrate_pod_provision_step`, `pychestrate_pod_teardown_step`,
`pychestrate_pod_orphaned`.

Trace spans: `dynamic_pod.materialize`,
`dynamic_pod.provision_step.<member_name>`,
`dynamic_pod.teardown_step.<member_name>`, `dynamic_pod.resume`.

## Open Questions

- Should we support sharing a materialization across projects (e.g., a
  shared template library)? Lean no for Phase 8; revisit in Phase 10.
- Do we expose a `dry_run` variant of `:materialize` that renders + validates
  but never reserves? Likely yes; confirm by end of M1.
