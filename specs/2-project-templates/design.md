# 2-project-templates — Design

## Architecture

`2-project-templates` lives in Layer 2 under
`automojo.pychestrate.webservice.model.project_templates`. It is a thin
service that composes three existing services — `2-global-variables` for
variable seeding, `2-tagging` for tag seeding, `2-notification-hub` for
routing-rule seeding — inside the same DB transaction as the project
create in `2-projects`. The template registry is populated at startup
by `E-resource-extensions` scanning for `ProjectTemplateExtension`
subclasses. Ships in **Phase 10 — Public Surface & Extensibility
Completion**.

## Data Model

```python
@dataclass
class TemplateVariableSpec:
    scope: Literal["project"]    # project-scope only at template level
    name: str
    value_type: VariableType     # from 2-global-variables
    value_text: str

@dataclass
class TemplateTagSpec:
    tag: str                     # canonical form "taxonomy:value"

@dataclass
class TemplateNotificationRuleSpec:
    event_pattern: str
    filter_tag_expression: str | None
    channel_names: list[str]     # resolved against system channels at apply
    template_name: str           # must be a registered
                                 # NotificationTemplateExtension
    rate_limit_per_minute: int | None

@dataclass
class ProjectTemplateRecord:
    template_id: str
    template_version: str         # SemVer string stamped on project
    display_name: str
    description: str
    variables: list[TemplateVariableSpec]
    tags: list[TemplateTagSpec]
    notification_rules: list[TemplateNotificationRuleSpec]
    recommended_roles: list[str]
    source_extension: str         # ext pack that registered it
    precedence: int

@dataclass
class TemplateApplyDiff:
    variables_added: list[str]
    variables_skipped: list[tuple[str, str]]   # (name, reason)
    variables_overwritten: list[str]
    tags_added: list[str]
    tags_skipped: list[tuple[str, str]]
    notification_rules_added: list[str]
    notification_rules_skipped: list[tuple[str, str]]
```

`projects` table gains nullable columns `template_id: str`,
`template_version: str` already declared in `2-projects` — this feature
populates them.

## Interfaces

### Public API

- `GET /api/v1/project-templates` — list registered templates.
- `GET /api/v1/project-templates/{template_id}` — fetch metadata.
- `POST /api/v1/projects/{slug}/reapply-template` — body
  `{template_id, template_version, overwrite_policy}`.
- The existing `POST /api/v1/projects` accepts `template_id`; when
  present this feature's `apply_template_to_project` runs inside the
  create transaction.

### Internal API

```python
# source/site/automojo/pychestrate/webservice/model/project_templates/service.py

def list_templates() -> list[ProjectTemplateRecord]:
    ...


def get_template(
    *,
    template_id: str,
) -> ProjectTemplateRecord:
    ...


def apply_template_to_project(
    *,
    template: ProjectTemplateRecord,
    project_id: UUID,
    actor_user_id: UUID,
    transaction,
) -> TemplateApplyDiff:
    """
        Apply a template's variables, tags, and notification rules
        to a just-created project. MUST execute inside the caller's
        already-open transaction so rollback is atomic with project
        create.

        :param template: Resolved template record
        :param project_id: Target project
        :param actor_user_id: Caller (for audit)
        :param transaction: Shared DB transaction handle

        :returns: TemplateApplyDiff describing what was applied
        :raises: TemplateApplyError (wraps per-item failures)
    """
    ...


def reapply_template(
    *,
    project_id: UUID,
    template_id: str,
    template_version: str,
    overwrite_policy: Literal["skip_existing", "overwrite_all", "dry_run"],
    actor_user_id: UUID,
) -> TemplateApplyDiff:
    ...


def diff_template_against_project(
    *,
    template: ProjectTemplateRecord,
    project_id: UUID,
) -> TemplateApplyDiff:
    ...
```

### Extension Surface

- `resource: ProjectTemplateExtension`
  (`source/site/automojo/pychestrate/webservice/model/project_templates/extensions.py`)

```python
class ProjectTemplateExtension(ResourceExtension):
    template_id: ClassVar[str]
    template_version: ClassVar[str]
    display_name: ClassVar[str]
    description: ClassVar[str]
    variables: ClassVar[list[TemplateVariableSpec]] = []
    tags: ClassVar[list[TemplateTagSpec]] = []
    notification_rules: ClassVar[list[TemplateNotificationRuleSpec]] = []
    recommended_roles: ClassVar[list[str]] = []
    PRECEDENCE: ClassVar[int] = 1000
```

Reference impls shipped in-tree under
`automojo/extensions/pychestrate/project_templates/`:
- `StandardCiTemplate` — one `environment:dev` tag, two variables
  (`default_timeout_seconds=900`, `notify_on_failure=true`), one
  notification rule `entity.run.failed → #ci-failures`, roles
  `ci-admin`, `ci-developer`.
- `ComplianceProjectTemplate` — `compliance:soc2` tag, audit-heavy
  variables, role `compliance-reviewer`.

### Events Emitted

```python
@dataclass
class ProjectTemplateAppliedEvent:
    project_id: UUID
    template_id: str
    template_version: str
    diff: TemplateApplyDiff
    actor_user_id: UUID
    occurred_at: datetime

@dataclass
class ProjectTemplateReappliedEvent:
    project_id: UUID
    template_id: str
    template_version: str
    overwrite_policy: str
    diff: TemplateApplyDiff
    actor_user_id: UUID
    occurred_at: datetime
```

Topics: `entity.project.template_applied`,
`entity.project.template_reapplied`.

### Events Consumed

None.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/model/project_templates/
    __init__.py
    entities.py         # ProjectTemplateRecord, specs, TemplateApplyDiff
    registry.py         # loaded from ProjectTemplateExtension on startup
    service.py          # list/get/apply/reapply/diff
    extensions.py       # ProjectTemplateExtension base
    events.py
    errors.py           # TemplateApplyError, UnknownTemplateError
source/site/automojo/pychestrate/webservice/restapi/versions/v1/project_templates.py
```

## Key Flows

**Apply at project create**
1. REST resource for `POST /projects` validates body.
2. `projects.service.create_project` opens txn, inserts Project row
   with `template_id` + `template_version` stamped from registry.
3. If `template_id` is set, calls
   `project_templates.service.apply_template_to_project(transaction=txn, …)`.
4. The function invokes
   `variables.service.set_variable`, `tagging.service.assign_tag`, and
   `notifications.service.create_routing_rule` — all accepting an
   explicit `transaction` argument so they enlist on the same txn.
5. Any failure aborts the entire transaction. Audit entry
   `project.template_applied` is written after commit.

**Reapply**
1. Caller supplies policy; service computes a diff via
   `diff_template_against_project` (variables by name, tags by
   canonical form, routing rules by `(event_pattern, template_name)`
   tuple).
2. `skip_existing` → only additions. `overwrite_all` → additions +
   updates for matching keys. `dry_run` → no writes.
3. All writes go through the respective feature services to preserve
   their validation + event emission.
4. Event `entity.project.template_reapplied` fired on success.

## Error Handling

- `UnknownTemplateError` → REST `400`.
- `TemplateApplyError` wraps the per-item failure list; REST returns
  `422` with a multiline body built via `os.linesep.join([...])`.
- `ConfigurationError` raised at startup on `template_id` collision
  with equal `PRECEDENCE`.
- Validation failures from downstream services
  (`VariableValidationError`, `TagValidationError`,
  `NotificationTemplateNotFoundError`) are caught and reclassified to
  `TemplateApplyError` items with the originating service named.
- `SemanticError` is never caught.

## Security Considerations

- `project.template.reapply` is required for the reapply endpoint.
- Template registration happens via extension install; operators
  control which extensions are loaded. The `source_extension` field
  is surfaced in the admin UI so operators can audit template
  sources.
- Templates cannot grant permissions directly; they only
  **recommend** roles via `recommended_roles`.
- Audit-log entries include template_id, template_version, and the
  TemplateApplyDiff counts.

## Observability

- Counters: `pychestrate_project_template_applied_total{template_id}`,
  `pychestrate_project_template_reapplied_total{template_id,policy}`,
  `pychestrate_project_template_failed_total{template_id,reason}`.
- Histogram: `pychestrate_project_template_apply_duration_seconds{template_id}`.
- Structured logs: `project.template_applied`,
  `project.template_reapplied`, `project.template_apply_failed`,
  `project.template_diff_computed`.
- Trace spans: `project.template.apply`, `project.template.reapply`,
  `project.template.diff`.

## Open Questions

- Phase-10 blocker: should the channel references in
  `notification_rules` be `channel_name` (resolved at apply) or a
  literal channel config (created on apply)? Decision: `channel_name`
  only — templates assume system-scoped channels exist.
- Does reapply with `overwrite_all` need a confirmation token to
  prevent accidental reset? Decide before T3.x.
