# 2-projects — Design

## Architecture

`2-projects` lives in Layer 2 — Core Entity Model — and is the anchor entity
that every downstream feature scopes against. It is owned by the
`automojo.pychestrate.webservice.model.projects` package. The project row in
Postgres (`0-persistence`) is the authoritative source of truth for a
project's existence, state, and slug; membership lives in a child table
(`project_member_bindings`) keyed by `(project_id, user_id)`. Events are
published through `0-message-bus` using the transactional outbox provided by
`0-persistence`. Reads go through a thin repository layer; writes pass a
service-layer API (`project_service`) that the REST surface in
`8-rest-api-v1` calls. Ships in **Phase 1**.

## Data Model

```python
class ProjectState(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"

@dataclass
class Project:
    project_id: UUID            # PK
    slug: str                   # UNIQUE, lowercased, matches ^[a-z][a-z0-9-]{1,62}$
    display_name: str
    description: str
    state: ProjectState         # default ACTIVE
    owning_group_id: UUID       # FK -> 1-user-management groups
    created_at: datetime        # set server-side
    updated_at: datetime
    archived_at: datetime | None
    template_id: UUID | None    # FK -> 2-project-templates (nullable in Phase 1)
    extension_fields: dict[str, Any]  # JSONB, validated against registered
                                      # ProjectMetadataFieldExtension schema

@dataclass
class ProjectMemberBinding:
    binding_id: UUID            # PK
    project_id: UUID            # FK -> projects, ON DELETE CASCADE
    user_id: UUID               # FK -> users
    role_name: str              # references 1-rbac roles, NOT FK (extensible)
    added_at: datetime
    added_by_user_id: UUID

@dataclass
class ProjectMetadataFieldSpec:
    field_name: str             # PK, must be unique across all extensions
    field_type: Literal["string", "integer", "boolean", "enum", "url"]
    required: bool
    default_value: Any | None
    enum_values: list[str] | None
    source_extension: str       # informational: ext pack that registered it
```

Indexes: `UNIQUE (lower(slug))`; `INDEX (state, updated_at)`;
`INDEX project_member_bindings (user_id)` for reverse lookup;
`GIN (extension_fields)` for custom-field queries.

## Interfaces

### Public API

- `POST /api/v1/projects` — body
  `{slug, display_name, description, owning_group_id, initial_members?, template_id?, extension_fields?}`;
  returns `201` with `Project` body. Requires `project.create`.
- `GET /api/v1/projects` — list with filters
  `?state=active|archived&member_of=<user_id>&tag=<tag>&offset=&limit=`.
- `GET /api/v1/projects/{slug}` — returns `Project`.
- `PATCH /api/v1/projects/{slug}` — partial update of
  `display_name, description, extension_fields`; requires `project.update`.
- `POST /api/v1/projects/{slug}/archive` — requires `project.archive`.
- `POST /api/v1/projects/{slug}/unarchive` — requires `project.archive`.
- `DELETE /api/v1/projects/{slug}` — requires `project.delete`; only
  valid when `state == ARCHIVED` unless `?force=true` + `platform.admin`.
- `POST /api/v1/projects/{slug}/members` — body `{user_id, role}`;
  requires `project.member.manage`.
- `DELETE /api/v1/projects/{slug}/members/{user_id}` — requires
  `project.member.manage`.
- `GET /api/v1/projects/{slug}/members` — list bindings.

### Internal API

```python
# source/site/automojo/pychestrate/webservice/model/projects/service.py

def create_project(
    *,
    slug: str,
    display_name: str,
    description: str,
    owning_group_id: UUID,
    actor_user_id: UUID,
    template_id: UUID | None = None,
    extension_fields: dict[str, Any] | None = None,
    initial_members: list[MemberSpec] | None = None,
    idempotency_key: str | None = None,
) -> Project:
    """
        Create a new Project and publish entity.project.created.

        :param slug: Canonicalized slug (validated before this call)
        :param display_name: Human label
        :param description: Free-form description
        :param owning_group_id: Owner group from 1-user-management
        :param actor_user_id: Principal performing the action (for audit)
        :param template_id: Optional 2-project-templates id
        :param extension_fields: Values for registered metadata fields
        :param initial_members: Optional list of initial memberships
        :param idempotency_key: Client-supplied dedup key

        :returns: The newly-persisted Project
        :raises: SlugValidationError, DuplicateSlugError, ValidationError
    """
    ...


def archive_project(
    *,
    project_id: UUID,
    actor_user_id: UUID,
) -> Project:
    ...


def delete_project(
    *,
    project_id: UUID,
    actor_user_id: UUID,
    force: bool = False,
) -> None:
    ...


def add_member(
    *,
    project_id: UUID,
    user_id: UUID,
    role_name: str,
    actor_user_id: UUID,
) -> ProjectMemberBinding:
    ...


def remove_member(
    *,
    project_id: UUID,
    user_id: UUID,
    actor_user_id: UUID,
    force: bool = False,
) -> None:
    ...


# source/site/automojo/pychestrate/webservice/model/projects/slug.py

def canonicalize_project_slug(raw: str) -> str:
    """
        Lowercase, strip, collapse whitespace-to-dash, validate pattern.

        :param raw: Raw user input

        :returns: Canonicalized slug string
        :raises: SlugValidationError
    """
    ...
```

### Extension Surface

- `resource: ProjectMetadataFieldExtension`
  (`source/site/automojo/pychestrate/webservice/model/projects/extensions.py`)
  - Subclasses declare class attributes `field_name: str`,
    `field_type: Literal[...]`, `required: bool`,
    `default_value: Any | None`, `enum_values: list[str] | None`, and a
    classmethod `validate_value(cls, value: Any) -> None` that raises
    `ValidationError` on failure.
  - Reference implementation shipped in-tree: `CostCenterFieldExtension`
    under
    `automojo/extensions/pychestrate/projects/cost_center_field.py`.

### Events Emitted

```python
@dataclass
class ProjectCreatedEvent:
    project_id: UUID
    slug: str
    owning_group_id: UUID
    actor_user_id: UUID
    occurred_at: datetime

@dataclass
class ProjectArchivedEvent:
    project_id: UUID
    slug: str
    actor_user_id: UUID
    occurred_at: datetime

@dataclass
class ProjectDeletedEvent:
    project_id: UUID
    slug: str
    actor_user_id: UUID
    occurred_at: datetime

@dataclass
class ProjectMemberAddedEvent:
    project_id: UUID
    user_id: UUID
    role_name: str
    actor_user_id: UUID
    occurred_at: datetime

@dataclass
class ProjectMemberRemovedEvent:
    project_id: UUID
    user_id: UUID
    actor_user_id: UUID
    occurred_at: datetime
```

Topics (published via `0-message-bus`):
`entity.project.created`, `entity.project.archived`,
`entity.project.deleted`, `entity.project.member_added`,
`entity.project.member_removed`.

### Events Consumed

- `entity.user.deleted` (from `1-user-management`) — remove bindings
  where `user_id` references the deleted user; emit
  `entity.project.member_removed` per removal.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/model/projects/
    __init__.py
    entities.py         # Project, ProjectMemberBinding dataclasses + ORM
    repository.py       # DB access
    service.py          # create/archive/delete/add_member/remove_member
    slug.py             # canonicalize_project_slug + SlugValidationError
    extensions.py       # ProjectMetadataFieldExtension base
    events.py           # event dataclasses and topic constants
    errors.py           # DuplicateSlugError, etc.
source/site/automojo/pychestrate/webservice/restapi/versions/v1/projects.py
                        # Flask-RestX resources delegating to service.py
```

## Key Flows

**Create project**
1. REST resource validates body, calls `canonicalize_project_slug`.
2. `service.create_project` opens a transaction, acquires advisory lock on
   `hash(slug)`, inserts `Project`, inserts initial member bindings,
   inserts outbox row for `entity.project.created`, commits.
3. Outbox publisher picks up the row and posts to `0-message-bus`.
4. `1-audit-log` subscriber writes a `project.created` record.

**Archive**
1. REST resource checks `project.archive` via `1-rbac`.
2. `service.archive_project` updates state, sets `archived_at`, writes
   outbox `entity.project.archived`, commits.
3. Downstream features observe the event and stop accepting writes
   scoped to the project.

**Delete**
1. Caller must have archived first. `service.delete_project` verifies
   `state == ARCHIVED`, performs cascade delete inside one transaction,
   writes outbox `entity.project.deleted`, commits.

## Error Handling

- `SlugValidationError` (subclass of `ValidationError`) for malformed
  slugs — bubbles to REST layer as `400`.
- `DuplicateSlugError` → REST `409 Conflict`.
- `ConfigurationError` raised when two `ProjectMetadataFieldExtension`
  subclasses collide on `field_name` — service refuses to start.
- `SemanticError` is never caught; any call that misuses the service API
  (e.g. archive on already-archived project via internal caller) bubbles.
- Multiline error messages composed via `os.linesep.join([...])` with a
  leading summary line, then `DETAILS:` block per Python coding
  standards.
- Bus publish failure rolls back the DB txn via the outbox; no silent
  drops.

## Security Considerations

- Every route is behind `1-authentication`; `1-rbac` gates writes on
  `project.*` permissions.
- Input validation: slug regex, display name length ≤ 120, description
  length ≤ 4096, `extension_fields` validated through registered
  extensions.
- Audit-log hooks fire on every mutating action with
  `actor_user_id, actor_ip, request_id`.
- Rate limit: `POST /api/v1/projects` limited to 10/minute per session,
  30/minute per source IP.

## Observability

- Counters: `pychestrate_project_created_total`,
  `pychestrate_project_archived_total`,
  `pychestrate_project_deleted_total`,
  `pychestrate_project_member_added_total`,
  `pychestrate_project_member_removed_total`.
- Histogram: `pychestrate_project_request_duration_seconds{route,status}`.
- Structured logs: `project.created`, `project.archived`,
  `project.deleted`, `project.member_added`, `project.member_removed`,
  `project.slug_collision`.
- Trace spans: `project.create`, `project.archive`, `project.delete`,
  `project.member_add`, `project.member_remove`.

## Open Questions

- Phase-1 blocker: should `DELETE` with `?force=true` skip the archive
  precondition entirely, or still require a 24-hour archive age? Decide
  before T2.4.
- Phase-10 blocker: do we need soft-delete with a grace window, or is
  `10-backup-dr` snapshot recovery sufficient? Close with the
  `2-retention-policies` phase.
