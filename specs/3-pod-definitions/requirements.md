# 3-pod-definitions — Requirements

## Introduction

Pod Definitions are the declarative spec of an Automation Pod: the set of
members (devices, services, synthetic roles), their links and roles, the
client binding, and any declared capabilities. This feature lives in Layer 3,
ships in Phase 2, and is the shared source of truth that both `3-static-pods`
(register-existing) and `3-dynamic-pods` (template-materialize, Phase 8)
consume. Per the architectural ground rules, pod members are never contacted
directly — the definition records members only so the client can be matched
on capability and so the UI can render the topology; Pychestrate treats a
pod's client as the single addressable endpoint. New member kinds are
contributed through `PodMemberKindExtension`; cross-kind validation is
pluggable through the `pod_spec_validator` factory protocol.

## Requirements

### Requirement 1: A pod definition validates before it is persisted

**User Story:** As a project admin, I want a pod definition to be rejected
before it is written if its members or links are invalid, so that the
registry never contains a pod the dispatcher cannot interpret.

**Acceptance Criteria (EARS):**

1. WHEN `POST /api/v1/projects/{project_id}/pod-definitions` receives a spec
   THEN the system SHALL run every registered `pod_spec_validator` factory in
   precedence order and SHALL persist the spec only if every validator returns
   `ValidationReport.ok()`.
2. IF any validator returns a report with `errors` THEN the system SHALL
   respond HTTP 422 with the full error list and SHALL NOT create any row.
3. IF the spec references a `member_kind` that is not declared by a loaded
   `PodMemberKindExtension` THEN the system SHALL reject with
   `UnknownMemberKind` naming the missing kind.
4. WHERE a validator returns `warnings` the system SHALL persist the spec and
   include the warnings in the response body.

### Requirement 2: Pod definitions are versioned and immutable per version

**User Story:** As an engineer debugging an old run, I want the pod spec at
run time to be the exact version that was dispatched against, so that member
churn in the current spec does not make historical runs unreadable.

**Acceptance Criteria (EARS):**

1. WHEN a pod definition is updated THEN the system SHALL write a new row with
   `version = previous_version + 1` and SHALL NOT mutate prior rows.
2. WHEN a dispatch references a pod THEN the envelope SHALL carry the pod
   definition's `version` and the server SHALL use exactly that version when
   hydrating the spec for display.
3. WHILE a pod has in-flight runs against `version=N` the system SHALL NOT
   delete `version=N` even if a newer version exists.
4. IF an admin requests deletion of a version that is in use THEN the system
   SHALL reject with `PodVersionInUse` listing the referencing `run_id`s.

### Requirement 3: Member kinds and roles are declared, not free-form

**User Story:** As an extension author shipping a new device type, I want to
register a `member_kind` with typed attributes and valid role names, so that
pods referencing my kind are validated by the core without kind-specific code
in Pychestrate.

**Acceptance Criteria (EARS):**

1. WHEN the extension host loads a `PodMemberKindExtension` subclass THEN the
   pod definition validator SHALL accept members of that kind from subsequent
   specs.
2. IF a member references a `role` not listed in the kind's `allowed_roles`
   THEN the validator SHALL reject with `RoleNotAllowedForKind`.
3. IF a link endpoint references a member name not present in the spec's
   `members` list THEN the validator SHALL reject with `DanglingLinkEndpoint`.
4. WHERE a member kind declares required attributes the validator SHALL
   reject any spec whose member omits those attributes.

## Property-Based Test Requirements

### Property 1: Spec validation is pure and deterministic

- **Invariant:** For any (spec, validator-registry) pair, calling
  `validate_pod_spec` twice returns reports whose `errors` and `warnings`
  fields are equal (same content, order-insensitive).
- **Generator:** hypothesis strategy producing random-but-schema-compliant
  specs (members drawn from declared kinds, links drawn from declared
  members) mixed with ~20% deliberately-broken specs.
- **Assertion:** `validate(s) == validate(s)` under set equality for
  `errors` and `warnings`; no side effect on the registry.
- **Sample size:** 1000 generated cases

### Property 2: Version bump preserves older versions

- **Invariant:** For any sequence of N pod-definition updates to the same
  `pod_id`, the DB ends in a state where `version ∈ {1..N}` exists for
  every N, each with immutable contents and with
  `max(version) = current_active_version`.
- **Generator:** hypothesis strategy generating update chains of length
  `integers(1, 20)` with random content changes at each step.
- **Assertion:** `SELECT COUNT(*) FROM pod_definition_version WHERE pod_id=?`
  equals N; deep-equality of each stored content against the captured
  snapshot at creation time.
- **Sample size:** 1000 generated cases

### Property 3: A spec's member graph must be acyclic through role `parent`

- **Invariant:** For any spec whose links include any `role=parent` edge,
  the set of `parent`-edges forms a forest (no cycles). Every spec that
  introduces a cycle is rejected.
- **Generator:** hypothesis strategy producing random member/link graphs
  plus a 30% sampled subset of graphs with intentionally-inserted cycles.
- **Assertion:** `has_parent_cycle(spec) <=> validate(spec) contains
  error(code="parent_cycle")`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** validation p99 <= 75 ms for specs with <= 32
  members and <= 64 links; persistence p99 <= 40 ms; list of project pods
  p99 <= 50 ms.
- **NFR-2 (Security):** RBAC permissions `pod.definition.read|write|admin`;
  every write audit-logged with `actor`, `pod_id`, `version`, `diff_summary`;
  spec JSON size capped at 256 KiB; member `attributes` map capped at 32 KiB
  per member.
- **NFR-3 (Observability):** metrics `pychestrate_pod_definition_rows`,
  `pychestrate_pod_definition_validations_total{outcome}`,
  `pychestrate_pod_definition_validation_seconds` (histogram),
  `pychestrate_pod_definition_versions_gauge`; log events
  `pychestrate_pod_definition_written`,
  `pychestrate_pod_definition_rejected`; trace span
  `pod_definition.validate`.
- **NFR-4 (Reliability):** writes transactional; rollback on any validator
  failure; version counter updates via `SERIALIZABLE` isolation to prevent
  two concurrent writes from colliding.

## Out of Scope

- Physical pre-wired pod registration (see `3-static-pods`).
- Template-driven materialization (see `3-dynamic-pods`, Phase 8).
- Lifecycle state machine (see `3-pod-lifecycle`).
- UI rendering (see `3-pod-topology-view`).
- Pod-scoped variables (see `3-pod-scoped-config`).

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`, `1-rbac`, `1-audit-log`,
  `2-projects`, `E-extension-host`, `E-factory-protocols`,
  `E-resource-extensions`.
- **Depended on by:** `3-static-pods`, `3-dynamic-pods`, `3-pod-lifecycle`,
  `3-pod-topology-view`, `3-pod-scoped-config`, `5-job-dispatch`.
- **Extension points exposed:**
  - `resource: PodMemberKindExtension` — declared member kinds (required
    attributes, allowed roles, default probes).
  - `factory: pod_spec_validator` — cross-cutting validators (e.g., quota,
    licensing, cross-project link restrictions).
  See implementation-plan.md Layer 3.
