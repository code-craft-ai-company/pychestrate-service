# 1-rbac — Requirements

## Introduction

`1-rbac` evaluates whether an authenticated principal may perform an action
against a target resource. It owns the role model, the permission key
catalog, and the project-scoped permission matrix that every other feature
consults through a single `check_permission` entry point. It ships in
**Phase 1 — Identity & Projects**, sits directly above `1-authentication`
(which supplies the principal), above `1-user-management` (which supplies
users and groups), and below `2-projects` (which is the first consumer of
the project-scoped permission namespace). The feature declares the
`PermissionExtension` and `RoleExtension` resource bases so extension
packs can contribute new permission keys and role presets.

## Requirements

### Requirement 1: Permission Key Namespace and Evaluation

**User Story:** As any feature author, I want a single `check_permission`
call that evaluates a well-defined permission key against the current
principal, so that authorization logic is uniform across the service.

**Acceptance Criteria (EARS):**

1. WHEN a caller invokes
   `check_permission(principal, permission_key="project:<id>:<action>")`
   THEN the system SHALL resolve the principal's role bindings scoped to
   that project, aggregate the union of permissions, and return an
   `AuthzDecision(allow=True|False, reason=...)`.
2. IF `permission_key` starts with `system:` THEN the system SHALL
   evaluate it against the principal's global (non-project-scoped) role
   bindings and SHALL NOT consult any project-scope bindings.
3. IF `permission_key` does not match either
   `project:<id>:<action>` or `system:<action>` THEN the system SHALL
   raise `SemanticError` with a message listing the expected namespaces
   (per AGENTS.md `SemanticError` must NEVER be caught internally).
4. WHERE a principal has both an allowing and a denying role binding
   for the same permission the system SHALL return `allow=False` with
   reason `"deny_beats_allow"` — deny always wins.

### Requirement 2: Role Assignment Lifecycle

**User Story:** As a project administrator, I want to assign and revoke
roles to users and groups, so that responsibilities follow real team
structure.

**Acceptance Criteria (EARS):**

1. WHEN an administrator assigns a role to a user scoped to a project
   THEN the system SHALL write a `RoleBinding` row, publish
   `entity.role.assigned`, and make the permission evaluable on the
   next request.
2. WHEN an administrator revokes a role binding THEN the system SHALL
   delete the `RoleBinding` row, publish `entity.role.revoked`, and
   ensure subsequent `check_permission` calls no longer honor the
   revoked grant.
3. IF a role assignment targets a role that has been removed from the
   registry THEN the system SHALL reject the assignment with
   `RoleNotFoundError` referencing the role name.
4. WHILE a user is deactivated the system SHALL continue to honor
   historical `RoleBinding` rows for audit and forensic queries but
   SHALL treat every `check_permission` for that user as
   `allow=False, reason="principal_deactivated"`.
5. WHERE a binding targets a group the system SHALL evaluate it for
   every user whose *current* group membership matches at evaluation
   time — group membership changes take effect without a new
   `role.assigned` event.

### Requirement 3: Role and Permission Extension Surface

**User Story:** As an extension author, I want to add new permission
keys and ship role presets that use them, so that my extension's actions
integrate with the existing RBAC model.

**Acceptance Criteria (EARS):**

1. WHEN an extension registers a `PermissionExtension` subclass that
   declares one or more `permission_keys` THEN the system SHALL include
   those keys in the permission catalog, validate the namespace
   (`project:<id>:<action>` pattern or `system:<action>` pattern), and
   reject duplicates with `PermissionKeyCollisionError`.
2. WHEN an extension registers a `RoleExtension` subclass that declares
   `role_name` and a `permissions` list THEN the system SHALL include
   it as an assignable role at load time.
3. IF a `RoleExtension` references a permission key that is not
   present in the catalog at load time THEN the system SHALL reject the
   extension with `ConfigurationError` and SHALL NOT load any of its
   sibling extensions from the same pack.
4. WHERE two extension packs define the same `role_name` the system
   SHALL pick the lower-precedence registration (higher effective
   priority per `E-extension-precedence`) and log a
   `rbac.role.override` event.

### Requirement 4: Project Scoping and Inheritance

**User Story:** As an organization administrator, I want roles granted
at the organization level to imply sensible defaults inside every
project, so that administrators do not have to re-bind on every project
creation.

**Acceptance Criteria (EARS):**

1. WHEN a project is created THEN the system SHALL apply the
   organization-level bindings that declare
   `inherits_into_project = True` to every permission key in the new
   project's scope.
2. WHEN an organization-level binding is revoked THEN the system SHALL
   remove inherited project-scoped permissions without affecting
   project-direct bindings.
3. IF a project-direct binding conflicts with an inherited binding
   THEN the most-specific direct binding SHALL take effect for
   `allow`; deny bindings SHALL continue to override regardless of
   specificity.

## Property-Based Test Requirements

### Property 1: Deny Beats Allow

- **Invariant:** For any generated RBAC policy (roles, bindings,
  permissions) and any `(principal, permission_key)` pair, if any
  binding in the principal's effective set denies the permission the
  final decision is `allow=False` regardless of how many bindings
  grant it.
- **Generator:** Hypothesis strategy producing up to 20 roles with
  up to 20 permissions each, up to 50 bindings, and then a random
  `(principal, permission_key)` query.
- **Assertion:** For every generated case where at least one binding
  denies and at least one binding allows, `check_permission(...)`
  returns `allow=False, reason="deny_beats_allow"`.
- **Sample size:** 1000 generated cases.

### Property 2: Deterministic Evaluation

- **Invariant:** For any policy and principal, repeated
  `check_permission(principal, permission_key)` calls inside the same
  transaction return byte-identical `AuthzDecision` results — no
  hidden per-call state.
- **Generator:** Any valid policy from Property 1's generator, plus
  repetition counts 2–50.
- **Assertion:** Every call in the repetition returns the same
  `AuthzDecision`.
- **Sample size:** 1000 generated cases.

### Property 3: Group-Based Binding Reflects Current Membership

- **Invariant:** For any sequence of group-membership mutations
  applied after a group-scoped role binding is created, the effective
  permissions for a user match their *current* group membership set —
  adds take effect, removes take effect, no stale grants.
- **Generator:** Strategy producing 1–20 users, 1–10 groups, a
  group-scoped binding, and 1–50 interleaved
  `{add_to_group, remove_from_group}` events.
- **Assertion:** After every step, `check_permission` returns `allow`
  if and only if the user is currently a member of the bound group.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** `check_permission` SHALL complete in
  < 5 ms p95, < 15 ms p99 on a warm in-process cache. Role-binding
  mutations SHALL invalidate the affected cache entries within 100 ms
  service-wide via the `0-message-bus`.
- **NFR-2 (Security):** Every mutating RBAC endpoint SHALL require
  `system:rbac.admin`. `check_permission` SHALL NEVER fall back to
  `allow=True` on internal errors — it SHALL raise and let callers
  fail closed. Role bindings SHALL NOT be editable through any path
  that bypasses `1-audit-log`.
- **NFR-3 (Observability):** The feature SHALL emit
  `pychestrate_rbac_check_total{decision,namespace}` (counter),
  `pychestrate_rbac_check_duration_seconds{namespace}` (histogram),
  `pychestrate_rbac_role_bindings_active` (gauge),
  `pychestrate_rbac_cache_hits_total` /
  `pychestrate_rbac_cache_misses_total`, and log events
  `rbac.check.allowed`, `rbac.check.denied`, `rbac.role.assigned`,
  `rbac.role.revoked`, `rbac.role.override`, `rbac.permission.denied`.
- **NFR-4 (Reliability):** A registry-load failure for a single
  `PermissionExtension` or `RoleExtension` SHALL NOT prevent the
  service from starting — affected extensions are marked `faulted`
  and surfaced on `E-extension-registry-ui`; in-tree roles always
  load.

## Out of Scope

- Authentication — owned by `1-authentication`.
- User and group records — owned by `1-user-management`.
- Project creation — owned by `2-projects`; this feature only consumes
  `entity.project.created` to seed inheritance.
- Dynamic policy languages (ABAC, OPA) — explicitly deferred; Layer 1
  RBAC is a static role/permission model.

## Dependencies

- **Depends on:** `1-user-management`, `1-authentication`,
  `0-persistence`, `0-message-bus`, `E-extension-host`,
  `E-resource-extensions`.
- **Depended on by:** every controller; directly consumed by
  `2-projects`, `2-global-variables`, `1-secrets-vault`,
  `1-feature-flags`, `1-audit-log`, and every Layer 3–9 feature.
- **Extension points exposed:** `resource: PermissionExtension`,
  `resource: RoleExtension`. See implementation-plan.md Layer 1.
