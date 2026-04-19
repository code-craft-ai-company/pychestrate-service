# 2-project-templates — Requirements

## Introduction

`2-project-templates` provides scaffolded "new project" presets so that
creating a new project produces a usable workspace instead of a blank
row. A template declares default variables, default tags, default
notification rules, optional starter pipeline skeletons, and a list of
recommended member roles. Templates are registered via
`ProjectTemplateExtension`, making it possible to ship per-team starter
kits without forking the service. This feature lives in Layer 2 and
**ships in Phase 10 — Public Surface & Extensibility Completion**
because the earlier-phase work of stabilizing `2-projects`,
`2-global-variables`, `2-tagging`, and `2-notification-hub` has to be
complete before they can be composed into a template.

## Requirements

### Requirement 1: Template registration and listing

**User Story:** As an extension author, I want to register a
`ProjectTemplateExtension` that declares the starting content for a new
project, so that any team can launch a pre-configured workspace.

**Acceptance Criteria (EARS):**

1. WHEN the host loads a subclass of `ProjectTemplateExtension` with
   class attributes `template_id`, `display_name`, `description`,
   `variables`, `tags`, `notification_rules`,
   `recommended_roles` THEN the system SHALL register the template in
   the template registry.
2. IF two subclasses share a `template_id` with equal `PRECEDENCE`
   THEN the service SHALL raise `ConfigurationError` at startup.
3. WHEN `GET /api/v1/project-templates` is received THEN the system
   SHALL return the list of currently registered templates with
   their summary metadata.

### Requirement 2: Applying a template at project create time

**User Story:** As a platform admin, I want to create a project using a
template id so that variables, tags, notification rules, and role
recommendations are installed atomically.

**Acceptance Criteria (EARS):**

1. WHEN `POST /api/v1/projects` is received with `template_id = X` AND
   `X` is a registered template THEN the system SHALL apply — in one
   DB transaction with the project create — every declared variable,
   tag, and notification rule that the template specifies, and SHALL
   record a `project.template_applied` audit entry.
2. IF any applied item fails validation (e.g., a declared variable
   type is rejected, a tag references an unknown taxonomy) THEN the
   entire transaction SHALL roll back and the project SHALL NOT be
   created; the response SHALL list every failing item.
3. WHERE the template declares `recommended_roles` THEN the response
   body SHALL include a `recommended_roles` array so the UI can
   prompt the admin to add members into those roles.

### Requirement 3: Template upgrade / reapply to an existing project

**User Story:** As a project owner, I want to re-apply a newer version
of my original template to my existing project, so that shared defaults
can propagate without manual copy-paste.

**Acceptance Criteria (EARS):**

1. WHEN `POST /api/v1/projects/{slug}/reapply-template` is received with
   `{template_id, template_version, overwrite_policy}` where
   `overwrite_policy ∈ {skip_existing, overwrite_all, dry_run}`
   THEN the system SHALL compute the diff and apply per policy.
2. IF `overwrite_policy == "dry_run"` THEN the system SHALL return the
   diff without mutating any state.
3. WHERE the caller lacks `project.template.reapply` THEN the system
   SHALL respond `403 Forbidden`.
4. WHEN reapply succeeds THEN the system SHALL emit
   `entity.project.template_reapplied` with the diff summary.

## Property-Based Test Requirements

### Property 1: Template application is atomic

- **Invariant:** For any generated template definition and any random
  failure injected into one of the N applied items, the post-state
  contains zero items from the template — every variable, tag, and
  notification rule the template tried to create is rolled back with
  the project row.
- **Generator:** `hypothesis.strategies.builds` generating templates
  with 0–10 variables, 0–20 tags, 0–5 notification rules; a random
  fault injector fails one item during apply.
- **Assertion:** DB counts for project-scoped variables, tag
  assignments, and routing rules for the failing project are all 0.
- **Sample size:** 1000 generated cases.

### Property 2: Reapply with `skip_existing` is idempotent

- **Invariant:** For any template and any existing project, calling
  `reapply_template(template_id, "skip_existing")` twice in succession
  produces identical post-state after the second call as after the
  first; the second call's diff SHALL list zero writes.
- **Generator:** `hypothesis.strategies.builds` producing template +
  pre-existing project states.
- **Assertion:** Second-call `applied_count == 0` and the post-state
  snapshot byte-equals the post-state after the first call.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Template apply at project create adds
  ≤ 300 ms to `POST /projects` p95 for a template with 20 variables
  and 5 notification rules.
- **NFR-2 (Security):** Template registration is scanned and loaded
  through `E-resource-extensions` (requires extension install).
  `project.template.reapply` is a distinct permission from
  `project.create`. Template content cannot bypass per-feature
  validation (variable type checks, tag taxonomy checks, notification
  rule template-name checks all still run).
- **NFR-3 (Observability):** Counters
  `pychestrate_project_template_applied_total{template_id}`,
  `pychestrate_project_template_reapplied_total{template_id,policy}`,
  `pychestrate_project_template_failed_total{template_id,reason}`;
  histogram
  `pychestrate_project_template_apply_duration_seconds{template_id}`;
  log events `project.template_applied`,
  `project.template_reapplied`, `project.template_apply_failed`;
  trace spans `project.template.apply`, `project.template.reapply`,
  `project.template.diff`.
- **NFR-4 (Reliability):** Apply and reapply run inside a single DB
  transaction. Extension reload SHALL NOT invalidate references from
  already-created projects — the `template_id` + `template_version`
  stamped on the project is what drives reapply, not the current
  in-memory template.

## Out of Scope

- Authoring templates through a UI — templates are code-only in
  `ProjectTemplateExtension` subclasses.
- Seeding starter pipelines with source-repo content — deferred to
  Layer 6 (`6-pipeline-definition`) integration; in Phase 10 the
  template only declares pipeline metadata, not committed YAML.

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`,
  `1-authentication`, `1-rbac`, `1-audit-log`, `2-projects`,
  `2-global-variables`, `2-tagging`, `2-notification-hub`.
- **Depended on by:** `6-pipeline-definition` (optional pipeline
  skeleton hook), `9-admin-ui` (template picker).
- **Extension points exposed:** `resource: ProjectTemplateExtension`.
