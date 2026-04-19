# 2-projects — Requirements

## Introduction

`2-projects` is the top-level workspace entity in the Pychestrate core entity
model (Layer 2). A Project groups every downstream entity a team cares about —
pipelines, jobs, pods, resources, secrets, dashboards, and members — under one
RBAC boundary. Projects are where `1-rbac` role bindings attach, where
`2-global-variables` anchors its mid-tier scope, where `2-tagging` resolves
taxonomies, and where `2-notification-hub` applies per-project routing rules.
This feature ships in **Phase 1 — Identity & Projects** and sits between
`1-rbac` (upstream, for role gating) and `3-pod-definitions` /
`6-pipeline-definition` (downstream, for the entities nested inside a Project).

## Requirements

### Requirement 1: Project creation with owner and audit event

**User Story:** As a platform admin, I want to create a Project with a slug,
display name, owning group, and initial members, so that a team gets a
self-contained workspace whose creation is auditable end-to-end.

**Acceptance Criteria (EARS):**

1. WHEN a request is received at `POST /api/v1/projects` with a valid body
   THEN the system SHALL persist a new `Project` row, publish
   `entity.project.created` on the message bus, and write a
   `project.created` record through `1-audit-log`.
2. IF the supplied `slug` already exists (case-insensitive) or fails the
   pattern `^[a-z][a-z0-9-]{1,62}$` THEN the system SHALL respond
   `409 Conflict` or `400 Bad Request` respectively and SHALL NOT publish the
   create event.
3. WHILE a creation transaction is in flight the system SHALL hold an
   advisory lock keyed by the lowercased slug so that two concurrent
   creates with the same slug cannot both succeed.
4. WHERE the request body supplies `template_id`
   (from `2-project-templates`, optional in Phase 1, required wiring in
   Phase 10) the system SHALL apply the template's variable, tag, and
   notification-rule scaffolding before returning `201 Created`.

### Requirement 2: Project archive and delete lifecycle

**User Story:** As a project owner, I want to archive a project (read-only,
recoverable) and later hard-delete it, so that inactive workspaces stop
accruing cost without destroying history prematurely.

**Acceptance Criteria (EARS):**

1. WHEN `POST /api/v1/projects/{slug}/archive` is received from a principal
   holding `project.archive` THEN the system SHALL set `state=ARCHIVED`,
   reject all mutating sub-entity writes scoped to the project, emit
   `entity.project.archived`, and record an audit row.
2. WHEN `DELETE /api/v1/projects/{slug}` is received for an archived
   project THEN the system SHALL cascade-delete owned rows (members,
   variables at project scope, tag assignments, notification rules), emit
   `entity.project.deleted`, and return `204 No Content`.
3. IF a delete is attempted against a project whose `state != ARCHIVED`
   THEN the system SHALL respond `409 Conflict` with message
   `"project must be archived before delete"` and SHALL NOT touch state.
4. WHILE a project is archived the system SHALL continue to serve `GET`
   requests on all sub-entities so audit and investigation remain possible.

### Requirement 3: Member add/remove with role binding

**User Story:** As a project owner, I want to add or remove members with a
specific project-scoped role, so that access is least-privilege and every
change is observable.

**Acceptance Criteria (EARS):**

1. WHEN `POST /api/v1/projects/{slug}/members` is received with
   `{user_id, role}` THEN the system SHALL create a
   `ProjectMemberBinding` row, emit `entity.project.member_added`, and
   record a `project.member_added` audit entry including the role name.
2. IF the supplied `role` is not a registered `1-rbac` role THEN the
   system SHALL respond `400 Bad Request` with a list of acceptable role
   names.
3. WHEN `DELETE /api/v1/projects/{slug}/members/{user_id}` is received
   THEN the system SHALL remove the binding, emit
   `entity.project.member_removed`, and write an audit entry; IF the
   removal would leave the project with zero principals holding
   `project.admin` THEN the system SHALL respond `409 Conflict` unless
   the caller sets `?force=true` and holds `platform.admin`.

### Requirement 4: ProjectMetadataFieldExtension contributes typed fields

**User Story:** As an extension author, I want to register a
`ProjectMetadataFieldExtension` that adds a typed metadata field (e.g.,
`cost_center`, `compliance_tier`), so that third-party packs can extend the
project schema without forking Pychestrate.

**Acceptance Criteria (EARS):**

1. WHEN the extension host loads a class derived from
   `ProjectMetadataFieldExtension` THEN the system SHALL register the
   field name, type, validator, and default into the project metadata
   registry exactly once per `on_service_ready`.
2. WHERE a project payload includes a key matching a registered metadata
   field THEN the system SHALL validate the value through the
   extension-supplied validator and reject with
   `422 Unprocessable Entity` on validation failure.
3. IF two `ProjectMetadataFieldExtension` subclasses declare the same
   `field_name` THEN the system SHALL raise `ConfigurationError` during
   `on_service_ready` and refuse to start.

## Property-Based Test Requirements

### Property 1: Slug canonicalization is idempotent

- **Invariant:** For any input string `s`, applying
  `canonicalize_project_slug(canonicalize_project_slug(s))` equals
  `canonicalize_project_slug(s)` and the output either matches
  `^[a-z][a-z0-9-]{1,62}$` or raises `SlugValidationError`.
- **Generator:** `hypothesis.strategies.text(alphabet=st.characters(), min_size=0, max_size=128)`.
- **Assertion:** For 1000 random strings, the double-applied result equals the
  single-applied result or both raise identically with equal message text.
- **Sample size:** 1000 generated cases.

### Property 2: Create-then-delete leaves no orphaned sub-entities

- **Invariant:** For any sequence of member add/remove, variable set/unset,
  and tag assign/unassign operations performed against a freshly-created
  project, `POST /archive` followed by `DELETE /{slug}` SHALL leave zero
  rows in `ProjectMemberBinding`, `VariableBinding(scope='project')`, and
  `TagAssignment(scope_type='project')` for that project id.
- **Generator:** `hypothesis.stateful.RuleBasedStateMachine` cycling create →
  random op sequence (length 0–50) → archive → delete.
- **Assertion:** Post-delete SQL counts are zero for every
  project-scoped child table.
- **Sample size:** 1000 generated scenarios.

## Non-Functional Requirements

- **NFR-1 (Performance):** `GET /api/v1/projects/{slug}` p95 ≤ 75 ms and
  `POST /api/v1/projects` p95 ≤ 250 ms at 50 req/s sustained.
- **NFR-2 (Security):** Every route requires a valid session from
  `1-authentication`; write routes gate on `1-rbac` permissions
  (`project.create`, `project.archive`, `project.delete`,
  `project.member.manage`); audit-log entries include
  `actor_user_id`, `actor_ip`, `request_id`.
- **NFR-3 (Observability):** Emit counters
  `pychestrate_project_created_total`,
  `pychestrate_project_archived_total`,
  `pychestrate_project_deleted_total`,
  `pychestrate_project_member_added_total`,
  `pychestrate_project_member_removed_total`; histogram
  `pychestrate_project_request_duration_seconds` labeled by
  `route,status`; structured log events `project.created`,
  `project.archived`, `project.deleted`, `project.member_added`,
  `project.member_removed`; trace spans `project.create`,
  `project.archive`, `project.delete`.
- **NFR-4 (Reliability):** All mutating endpoints are idempotent via
  `Idempotency-Key` header (48-hour dedup window); bus publish failures
  SHALL roll back the DB transaction (outbox pattern).

## Out of Scope

- Per-project quota enforcement — deferred to `0-maintenance-mode` and
  Phase 10 operations work.
- Soft-delete recovery window / undelete UI — covered by `10-backup-dr`.
- Cross-project move operations — not supported; downstream entities are
  project-bound for life.

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`, `1-authentication`,
  `1-rbac`, `1-audit-log`.
- **Depended on by:** `2-global-variables`, `2-tagging`,
  `2-notification-hub`, `2-project-templates`, `2-retention-policies`,
  every Layer 3–7 feature that scopes to a project.
- **Extension points exposed:**
  `resource: ProjectMetadataFieldExtension`;
  `event: entity.project.created|archived|deleted|member_added|member_removed`.
