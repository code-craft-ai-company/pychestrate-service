# 3-dynamic-pods — Requirements

## Introduction

Dynamic Pods take a pod *template* — a pattern describing members, links, and
provisioning steps — and materialize it into a live pod on demand. The client
agent is the *last* member brought up, per the architectural ground rule that
the client is the single contact point: members come up first (so that by the
time the client is up, the pod it will own is already physically assembled),
then the client registers itself. This feature lives in Layer 3 and ships in
Phase 8, after the extension sandbox lands so third-party `pod_provisioner`
implementations can be safely onboarded. Upstream it depends on
`3-pod-definitions` (template materialization produces a concrete definition),
`3-client-enrollment` (materialized client must enroll), and `4-resource-*`
(it reserves physical resources for members). Downstream it feeds
`3-pod-lifecycle` (transitions from `provisioning` through `ready`).

## Requirements

### Requirement 1: A template materialization produces a fully-validated pod definition before any provisioning

**User Story:** As a developer requesting a pod from a template, I want
Pychestrate to render my template into a concrete pod definition and
validate it before spending money on provisioning, so that I never get a
half-provisioned pod because of a trivial spec error.

**Acceptance Criteria (EARS):**

1. WHEN `POST /api/v1/projects/{project_id}/pod-templates/{template_id}:materialize`
   is called with parameters THEN the system SHALL render the template into a
   `PodSpec`, run `3-pod-definitions.validate_pod_spec`, and SHALL proceed to
   provisioning only if validation returns no errors.
2. IF template rendering fails (missing required parameter, undefined variable)
   THEN the system SHALL respond HTTP 422 and SHALL NOT allocate any
   resources.
3. WHERE the materialization requests members that need resource reservations
   the system SHALL acquire those reservations through `4-checkout-checkin`
   *before* calling the provisioner and SHALL release them on failure.

### Requirement 2: Provisioning order is members-first, client-last

**User Story:** As a pod operator, I want all non-client members to be ready
before the client comes up, so that the client can present an accurate initial
`StaticPodRegisterRequest` on its first heartbeat.

**Acceptance Criteria (EARS):**

1. WHEN the provisioner runs THEN the system SHALL schedule member
   provisioning steps in a topological order that places every non-client
   member before the `client` member.
2. IF any non-client member provisioning step fails THEN the system SHALL
   tear down already-provisioned members in reverse order and SHALL NOT
   attempt to bring up the client.
3. WHEN all non-client members report ready THEN the system SHALL dispatch
   the client bring-up step and SHALL wait for the client's enrollment +
   static-pod registration before transitioning pod state to `ready`.
4. WHILE the pod is in `state=provisioning` the system SHALL refuse any job
   dispatch targeting it.

### Requirement 3: Teardown releases every acquired resource

**User Story:** As a finance-conscious operator, I want a finished or failed
dynamic pod to release every resource it holds, so that we do not accumulate
orphaned VMs, reservations, or cloud bills.

**Acceptance Criteria (EARS):**

1. WHEN a dynamic pod transitions to `state=released` THEN the system SHALL
   tear down every provisioned member in reverse provisioning order and
   SHALL release every reservation held on `4-checkout-checkin`.
2. IF teardown of a member fails THEN the system SHALL retry the teardown
   up to the `teardown_max_attempts` configured on the template and SHALL
   emit `entity.pod.teardown_failed` on final failure, marking the pod
   `state=orphaned` for operator review.
3. WHILE teardown is in progress the system SHALL not mark the pod
   `released` and SHALL continue to show it in fleet inventory with the
   `teardown_in_progress` flag set.

## Property-Based Test Requirements

### Property 1: Provisioning is reverse-ordered on failure

- **Invariant:** For any ordered provisioning plan `[s1, s2, ..., sn]`, if
  step `s_k` fails, teardown runs in the exact order `s_{k-1}, s_{k-2},
  ..., s_1`, touching each provisioned step exactly once.
- **Generator:** hypothesis strategy producing plans of length 2-16 with a
  random failing-index.
- **Assertion:** the recorded `teardown_invocations` list equals
  `list(reversed(plan[:k-1]))`; no element appears more than once.
- **Sample size:** 1000 generated cases

### Property 2: Template rendering is referentially transparent

- **Invariant:** For any `(template, parameters)` pair where rendering
  succeeds, calling `render_template` twice returns byte-identical
  rendered `PodSpec` objects.
- **Generator:** hypothesis strategy generating templates with loops,
  conditionals, and variable references; parameter sets drawn from
  hypothesis-synthesized JSON objects matching each template's parameter
  schema.
- **Assertion:** `canonical_json(render(t, p)) ==
  canonical_json(render(t, p))`.
- **Sample size:** 1000 generated cases

### Property 3: Client-last ordering always holds

- **Invariant:** For any rendered `PodSpec` whose members include a
  `role=client` member, the provisioning plan places that member strictly
  after every other non-client member.
- **Generator:** hypothesis strategy producing specs with random topology
  (including deliberately adversarial parent/child graphs that would
  naturally place the client earlier in a naive topological sort).
- **Assertion:** the index of the client member in the plan equals
  `len(plan) - 1` when the client has no intentional post-steps,
  otherwise strictly greater than the max index of any non-client member.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** template render p99 <= 250 ms for templates
  <= 64 KiB; time-to-`ready` bounded by provisioner work (not Pychestrate
  overhead), with Pychestrate-side scheduling overhead p99 <= 1 s per
  member transition.
- **NFR-2 (Security):** template rendering runs in a sandbox with no
  network/file access; provisioner factories must carry the
  `dispatch:jobs` and/or `net:outbound` capabilities declared in
  `E-extension-sandbox`; all template + parameter bodies audit-logged
  (parameters scrubbed of secret-typed fields per
  `3-pod-scoped-config`).
- **NFR-3 (Observability):** metrics
  `pychestrate_pod_materializations_total{outcome}`,
  `pychestrate_pod_provision_duration_seconds{phase}`,
  `pychestrate_pod_teardown_duration_seconds`,
  `pychestrate_pod_orphaned_gauge`; log events
  `pychestrate_pod_materialize_start`,
  `pychestrate_pod_provision_step`, `pychestrate_pod_teardown_step`,
  `pychestrate_pod_orphaned`; trace spans `dynamic_pod.materialize`,
  `dynamic_pod.provision_step.<name>`, `dynamic_pod.teardown`.
- **NFR-4 (Reliability):** every in-flight materialization has a durable
  checkpoint in `dynamic_pod_materialization` that survives a service
  restart; on restart a resumer picks up work at the last recorded step.

## Out of Scope

- The physical member provisioning itself (lives behind
  `pod_provisioner` factory implementations).
- Definition schema and validation (see `3-pod-definitions`).
- Pod-scoped variables (see `3-pod-scoped-config`).
- Overall pod lifecycle states (see `3-pod-lifecycle`).
- Topology UI (see `3-pod-topology-view`).

## Dependencies

- **Depends on:** `3-pod-definitions`, `3-pod-lifecycle`,
  `3-client-enrollment`, `4-resource-inventory`, `4-checkout-checkin`,
  `1-secrets-vault`, `2-global-variables`, `E-extension-host`,
  `E-extension-sandbox`, `E-factory-protocols`,
  `E-resource-extensions`.
- **Depended on by:** `3-pod-topology-view`, `6-infra-orchestration`,
  `6-test-orchestration` (when tests ask for a materialized pod rather
  than a static one).
- **Extension points exposed:**
  - `factory: pod_provisioner` — per provisioning backend (Terraform-driven,
    libvirt-driven, cloud SDK, in-house scheduler).
  - `resource: PodTemplateExtension` — declared template kinds and their
    parameter schemas.
  See implementation-plan.md Layer 3 and Phase 8.
