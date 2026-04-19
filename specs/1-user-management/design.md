# 1-user-management — Design

## Architecture

The user-management feature is a Layer 1 service that owns the canonical
`users` and `groups` tables and the `user_directory_source` factory protocol.
It lives under
`source/site/automojo/pychestrate/webservice/identity/users/` and is wired
into the WebWorks app by `0-web-app-host` at startup. Persistence goes
through the repository abstraction provided by `0-persistence`; inbound
events from external directories run through the factory registry owned by
`E-extension-host`; every mutation publishes an entity event on
`0-message-bus` which `1-audit-log` and `1-rbac` consume. This feature is
the authoritative source of truth for *identity records*; authentication
state (sessions, MFA, credential material) lives in `1-authentication` and
references users by `user_id`.

## Data Model

The `users` table holds identity records keyed by a UUID surrogate so
external directory renames never break foreign keys:

- `user_id: UUID` — primary key, server-generated.
- `login_name: str` — unique, case-insensitive, max 128 chars.
- `primary_email: str` — unique, NFC-normalized, lowercased ASCII prefix.
- `display_name: str` — max 256 chars, NFC-normalized.
- `status: UserStatus` — enum `{ACTIVE, DEACTIVATED, PENDING}`.
- `provisioning_source: str` — name of the owning
  `user_directory_source` or `"local"`.
- `external_id: Optional[str]` — stable id provided by the external source.
- `timezone: str` — IANA timezone name.
- `created_at: datetime` / `updated_at: datetime`.

Indexes: `UNIQUE(login_name)`, `UNIQUE(primary_email)`,
`UNIQUE(provisioning_source, external_id)`, `INDEX(status)`.

The `groups` table holds named collections:

- `group_id: UUID` — primary key.
- `group_name: str` — unique.
- `description: str`.
- `created_at: datetime`.

The `group_memberships` join table carries:

- `group_id: UUID` — FK → `groups.group_id`.
- `user_id: UUID` — FK → `users.user_id`.
- `added_at: datetime`.
- `added_by: UUID` — FK → `users.user_id` for audit attribution.

Primary key: `(group_id, user_id)`. Deletion cascades from either parent.

A `user_email_verifications` table tracks pending email changes:

- `verification_id: UUID`, `user_id: UUID`, `new_email: str`,
  `token_hash: bytes`, `created_at: datetime`, `expires_at: datetime`.

## Interfaces

### Public API

REST routes under `/api/v1/identity/`:

- `POST /api/v1/identity/users` — create user. Body:
  `{login_name, primary_email, display_name, timezone}`. Returns `201` with
  `{user_id, ...}`.
- `GET /api/v1/identity/users/{user_id}` — fetch user.
- `PATCH /api/v1/identity/users/{user_id}` — update mutable profile fields.
- `POST /api/v1/identity/users/{user_id}/deactivate` — deactivate.
- `POST /api/v1/identity/users/{user_id}/reactivate` — reactivate.
- `GET /api/v1/identity/users` — list with filters `status`, `group_id`,
  `provisioning_source`, `include_inactive`.
- `POST /api/v1/identity/groups` — create group.
- `POST /api/v1/identity/groups/{group_id}/members` — add user.
- `DELETE /api/v1/identity/groups/{group_id}/members/{user_id}` — remove
  user.
- `POST /api/v1/identity/directory/{source_name}/sync` — trigger a sync
  cycle for the named `user_directory_source`.

### Internal API

Module `automojo.pychestrate.webservice.identity.users.user_service`:

```python
def create_user(
        *,
        login_name: str,
        primary_email: str,
        display_name: str,
        timezone: str,
        provisioning_source: str,
        external_id: Optional[str],
        actor_user_id: UUID
    ) -> User:
    """
        Create a new user record.

        :param login_name: Unique account login.
        :param primary_email: RFC-5321 email address.
        :param display_name: Human-facing name.
        :param timezone: IANA timezone name.
        :param provisioning_source: Source name; "local" for admin-created.
        :param external_id: Stable id from the external source, if any.
        :param actor_user_id: The acting principal, for audit attribution.

        :returns: The newly created `User`.
        :raises: UserAlreadyExistsError, SemanticError
    """
    ...


def deactivate_user(*, user_id: UUID, actor_user_id: UUID) -> User:
    """
        Deactivate a user and revoke sessions.

        :param user_id: Target user id.
        :param actor_user_id: Acting principal for audit attribution.

        :returns: The updated `User` record.
        :raises: UserNotFoundError
    """
    ...


def read_user(*, user_id: UUID) -> User:
    """
        Fetch a user by id.

        :param user_id: Target user id.

        :returns: The `User` record.
        :raises: UserNotFoundError
    """
    ...


def list_users(
        *,
        status_filter: Optional[UserStatus],
        group_id: Optional[UUID],
        provisioning_source: Optional[str],
        include_inactive: bool,
        page_size: int,
        page_token: Optional[str]
    ) -> UserPage:
    """
        List users matching the supplied filters.
    """
    ...


def add_group_member(
        *,
        group_id: UUID,
        user_id: UUID,
        actor_user_id: UUID
    ) -> GroupMembership:
    """
        Add a user to a group. Idempotent.
    """
    ...
```

Module `automojo.pychestrate.webservice.identity.users.directory_sync`:

```python
def run_directory_sync(*, source_name: str, actor_user_id: UUID) -> DirectorySyncReport:
    """
        Run a full sync cycle for the named `user_directory_source`.

        :param source_name: The `factory_protocol_name` entry to run.
        :param actor_user_id: The acting principal (scheduler service id or admin).

        :returns: A report with created, updated, deactivated counts.
        :raises: DirectoryCollisionError, ConfigurationError
    """
    ...
```

### Extension Surface

Factory protocol `user_directory_source` declared in
`automojo.pychestrate.webservice.identity.users.factories.user_directory_source`:

```python
class UserDirectorySourceProtocol(FactoryProtocolBase):
    factory_protocol_name: str = "user_directory_source"
    protocol_schema_version: int = 1

    @classmethod
    def iter_user_records(cls) -> Iterator[ExternalUserRecord]:
        """
            Yield the current full set of user records owned by this source.
        """
        ...

    @classmethod
    def iter_group_records(cls) -> Iterator[ExternalGroupRecord]:
        """
            Yield the current full set of group records owned by this source.
        """
        ...

    @classmethod
    def source_name(cls) -> str:
        """
            Return the name used as `provisioning_source` for records owned.
        """
        ...
```

Reference implementation `LocalDatabaseUserDirectorySource` ships in
`automojo.pychestrate.webservice.identity.users.factories.local_directory`
with `PRECEDENCE = 1000`, producing the local-administration path.

### Events Emitted

- `entity.user.created` — `{user_id, login_name, provisioning_source, actor_user_id, created_at}`
- `entity.user.updated` — `{user_id, changed_fields, actor_user_id, updated_at}`
- `entity.user.deactivated` — `{user_id, actor_user_id, deactivated_at}`
- `entity.group.created` — `{group_id, group_name, actor_user_id, created_at}`
- `entity.group.deleted` — `{group_id, actor_user_id, deleted_at}`
- `entity.group.membership.changed` —
  `{group_id, user_id, change: "added"|"removed", actor_user_id, at}`

### Events Consumed

- `entity.session.opened` — updates `last_login_at` for the referenced user.
- `entity.audit.backfill_requested` — re-emits user creation events for
  backfill after an audit sink swap (owned by `1-audit-log`).

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/identity/users/
    __init__.py
    models.py                       # SQLAlchemy models: User, Group, GroupMembership
    user_service.py                 # public API surface above
    directory_sync.py               # sync orchestration
    email_verification.py           # email re-verification flow
    repositories/
        user_repository.py
        group_repository.py
    factories/
        user_directory_source.py    # FactoryProtocolBase
        local_directory.py          # reference implementation
    restapi/
        v1/
            users_controller.py
            groups_controller.py
            directory_controller.py
    events.py                       # dataclasses for bus payloads
    exceptions.py                   # UserAlreadyExistsError, UserNotFoundError, DirectoryCollisionError
```

## Key Flows

**Create User (local):**

1. Admin calls `POST /api/v1/identity/users`.
2. Controller resolves actor from the session, calls `create_user(...)`.
3. `user_service.create_user` validates uniqueness via `user_repository`,
   inserts the row inside a single transaction, and stages an outbox entry
   for `entity.user.created`.
4. Transaction commit triggers the outbox publisher, which posts to
   `0-message-bus`.
5. `1-audit-log` consumes the event and writes an `audit.user.created`
   record.

**Directory Sync:**

1. Scheduler or admin invokes
   `POST /api/v1/identity/directory/{source_name}/sync`.
2. `directory_sync.run_directory_sync` calls
   `super_factory.create_instance_by_order(factory_protocol_name="user_directory_source",
    predicate=lambda impl: impl.source_name() == source_name)`.
3. The implementation yields external records; the sync loop diffs
   against the last-good snapshot table per source.
4. Creates, updates, and deactivations are applied through
   `user_service`, each producing a transactional outbox entry so events
   and rows commit together.
5. A `DirectorySyncReport` is returned; metrics and a
   `pychestrate_users_directory_sync_duration_seconds` observation are
   emitted even on partial failure.

**Email Re-verification:**

1. Profile PATCH changes `primary_email`.
2. A `user_email_verifications` row is inserted with a hashed token and a
   24-hour expiry.
3. `2-notification-hub` sends the verification email (consumes
   `entity.user.updated` with `email_changed=True`).
4. The user submits the token; on match the `primary_email` column is
   promoted and the verification row is deleted.

## Error Handling

Failure modes and responses:

- `UserAlreadyExistsError` — raised from `create_user` on unique-constraint
  violation; surfaces as HTTP 409 with a structured error body listing the
  conflicting field. Built with:
  ```python
  err_msg_lines = ["Cannot create user — conflict with existing record."]
  err_msg_lines.append("LOGIN_NAME: {}".format(login_name))
  err_msg_lines.append("CONFLICT_FIELD: {}".format(conflict_field))
  err_msg = os.linesep.join(err_msg_lines)
  raise UserAlreadyExistsError(err_msg) from None
  ```
- `UserNotFoundError` — 404 on read / deactivate when the id is unknown.
- `DirectoryCollisionError` — 409 when two sources claim the same
  `login_name`; never caught internally, bubbled to the sync report.
- `ConfigurationError` — raised if a requested `source_name` has no
  registered implementation; surfaced as HTTP 503.
- `SemanticError` — raised on unknown PATCH fields; NEVER caught per
  AGENTS.md.

Directory-sync failures catch the specific transport exceptions from the
underlying source, reclassify as `DirectorySyncTransientError` with added
source-name context, and retry on the next cycle — the persistent record
set is never partially overwritten.

## Security Considerations

- RBAC gates: `system:users.write` for create/update/deactivate;
  `system:users.read` for reads; `system:groups.admin` for group mutations.
- Email addresses are classified as PII and are tagged as
  `log_field_class=PII` in the structured logger so they are scrubbed
  before going to any non-audit sink.
- Directory-sync runs require `system:directory.sync` held by the
  invoking principal or the scheduler service identity.
- Every write produces an `entity.*` event that `1-audit-log` persists —
  there is no write path that bypasses audit.
- No secret material lives here; credential material is owned by
  `1-authentication` and referenced by `user_id`.

## Observability

Metrics (Prometheus-style names via `0-timeseries-backend`):

- `pychestrate_users_created_total{source}`
- `pychestrate_users_deactivated_total{source}`
- `pychestrate_users_reactivated_total{source}`
- `pychestrate_groups_membership_changes_total{change}` (`added|removed`)
- `pychestrate_users_directory_sync_duration_seconds{source}` (histogram)
- `pychestrate_users_directory_sync_failures_total{source}`

Log events: `user.created`, `user.updated`, `user.deactivated`,
`group.created`, `group.deleted`, `group.membership.changed`,
`directory.sync.started`, `directory.sync.completed`,
`directory.sync.failed`.

Trace spans: `user_service.create_user`, `user_service.deactivate_user`,
`directory_sync.run_directory_sync`.

## Open Questions

- Should `display_name` collisions be allowed? Current design: yes (only
  `login_name` / `primary_email` are unique). Close before Phase 1 cutover.
- Do we need soft-delete distinct from `DEACTIVATED` for GDPR erasure?
  Deferred to `2-retention-policies` in Phase 10.
- Group hierarchy: the current model is flat. If Phase 1 ships a demand
  for nested groups, add a self-referential `parent_group_id` column and
  ensure `1-rbac` resolves it before project scoping.
