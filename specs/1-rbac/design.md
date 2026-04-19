# 1-rbac — Design

## Architecture

`1-rbac` lives under
`source/site/automojo/pychestrate/webservice/security/rbac/`. It is a
read-heavy, write-rare service providing one canonical evaluator —
`rbac_evaluator.check_permission` — consumed by every controller guard
and every internal service that needs an authorization decision. The
authoritative state (roles, permissions, bindings) lives in
`0-persistence`; a process-local LRU cache fronts reads and is
invalidated via `entity.role.assigned|revoked` events from
`0-message-bus`. The feature declares two resource extensions
(`PermissionExtension`, `RoleExtension`) so extension packs extend the
permission catalog and ship role presets. This feature ships in
**Phase 1 — Identity & Projects**.

## Data Model

`roles` — known roles keyed by human-readable name:

- `role_id: UUID` — PK.
- `role_name: str` — unique.
- `source: RoleSource` — `BUILTIN`, `EXTENSION`, `CUSTOM`.
- `source_name: Optional[str]` — name of the extension that contributed
  this role, when `source = EXTENSION`.
- `description: str`.
- `created_at: datetime`.

`permissions` — known permission keys:

- `permission_id: UUID` — PK.
- `permission_key: str` — unique; namespaced
  `project:<id>:<action>` or `system:<action>`.
- `description: str`, `source: PermissionSource`,
  `source_name: Optional[str]`.

`role_permissions` — which permissions each role carries:

- `role_id: UUID` — FK.
- `permission_key: str`.
- `effect: PermissionEffect` — `{ALLOW, DENY}`.
- Primary key `(role_id, permission_key)`.

`role_bindings` — the live assignments:

- `binding_id: UUID` — PK.
- `role_id: UUID` — FK.
- `principal_kind: PrincipalKind` — `{USER, GROUP}`.
- `principal_id: UUID` — FK to `users.user_id` or `groups.group_id`.
- `scope_kind: BindingScope` — `{SYSTEM, ORGANIZATION, PROJECT}`.
- `scope_id: Optional[UUID]` — project id when
  `scope_kind = PROJECT`.
- `inherits_into_project: bool` — only meaningful on
  `scope_kind = ORGANIZATION`.
- `created_at: datetime`, `created_by: UUID`.

Indexes: `INDEX(principal_kind, principal_id)`,
`INDEX(scope_kind, scope_id)`,
`UNIQUE(role_id, principal_kind, principal_id, scope_kind, scope_id)`.

## Interfaces

### Public API

- `GET /api/v1/rbac/roles` — list all registered roles with source.
- `GET /api/v1/rbac/permissions` — list the permission key catalog.
- `POST /api/v1/rbac/bindings` — create a binding.
- `DELETE /api/v1/rbac/bindings/{binding_id}` — revoke.
- `GET /api/v1/rbac/bindings?principal_id=...&scope_id=...` — list.
- `POST /api/v1/rbac/check` — evaluate `{principal_id, permission_key}`
  (used by out-of-process integrations such as `8-cli`).

### Internal API

Module `automojo.pychestrate.webservice.security.rbac.rbac_evaluator`:

```python
def check_permission(
        *,
        principal: AuthPrincipal,
        permission_key: str,
        now: datetime
    ) -> AuthzDecision:
    """
        Evaluate whether a principal holds a permission.

        :param principal: The authenticated principal from 1-authentication.
        :param permission_key: Canonical key, `project:<id>:<action>` or `system:<action>`.
        :param now: Evaluation timestamp (for future-dated bindings, if any).

        :returns: An `AuthzDecision` carrying allow/deny and a reason.
        :raises: SemanticError on malformed `permission_key`.
    """
    ...


def require_permission(
        *,
        principal: AuthPrincipal,
        permission_key: str,
        now: datetime
    ) -> None:
    """
        Shortcut that raises `AuthorizationError` when the decision is deny.

        :raises: AuthorizationError, SemanticError
    """
    rtnval = None
    return rtnval
```

Module `automojo.pychestrate.webservice.security.rbac.binding_service`:

```python
def assign_role(
        *,
        role_name: str,
        principal_kind: PrincipalKind,
        principal_id: UUID,
        scope_kind: BindingScope,
        scope_id: Optional[UUID],
        inherits_into_project: bool,
        actor_user_id: UUID
    ) -> RoleBinding:
    """
        Create a new role binding.

        :raises: RoleNotFoundError, SemanticError (on illegal scope combos)
    """
    ...


def revoke_role(*, binding_id: UUID, actor_user_id: UUID) -> None:
    """
        Remove a role binding.

        :raises: BindingNotFoundError
    """
    rtnval = None
    return rtnval
```

Module `automojo.pychestrate.webservice.security.rbac.catalog`:

```python
def load_catalog_from_registry() -> CatalogSnapshot:
    """
        Walk registered `PermissionExtension` and `RoleExtension`
        subclasses and produce the canonical in-memory catalog.

        :raises: PermissionKeyCollisionError, ConfigurationError
    """
    ...
```

### Extension Surface

Resource base `PermissionExtension` declared in
`automojo.pychestrate.webservice.security.rbac.extensions.permission_extension`:

```python
class PermissionExtension(ResourceExtension):
    permission_keys: tuple[str, ...]

    @classmethod
    def describe(cls, *, permission_key: str) -> PermissionDescriptor:
        """Return metadata (description, namespace) for a key."""
        ...
```

Reference implementations (in-tree):
`CorePermissionExtension` (declares `system:users.read`,
`system:users.write`, `system:rbac.admin`, etc.),
`ProjectPermissionExtension` (declares `project:<id>:variables.write`,
`project:<id>:runs.dispatch`, etc.).

Resource base `RoleExtension`:

```python
class RoleExtension(ResourceExtension):
    role_name: str
    permissions: tuple[PermissionGrant, ...]  # (permission_key, effect)
    description: str
```

Reference implementations: `SystemAdminRole`, `ProjectOwnerRole`,
`ProjectEditorRole`, `ProjectViewerRole`, `AuditorRole`.

### Events Emitted

- `entity.role.assigned` — `{binding_id, role_name, principal_kind, principal_id, scope_kind, scope_id, actor_user_id, created_at}`
- `entity.role.revoked` — `{binding_id, role_name, principal_kind, principal_id, scope_kind, scope_id, actor_user_id, revoked_at}`
- `entity.rbac.catalog.reloaded` — `{roles_count, permissions_count, reloaded_at}`

### Events Consumed

- `entity.user.deactivated` — invalidate cached principal decisions.
- `entity.group.membership.changed` — invalidate cached group-derived
  decisions.
- `entity.project.created` — seed inheritance from
  `inherits_into_project = True` organization bindings.
- `entity.project.archived` — hide project-scoped bindings from
  evaluation without deleting them.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/security/rbac/
    __init__.py
    rbac_evaluator.py              # check_permission, require_permission
    binding_service.py             # assign_role, revoke_role, list_bindings
    catalog.py                     # load_catalog_from_registry
    cache.py                       # process-local LRU + invalidation
    inheritance.py                 # organization → project seeding
    models.py                      # Role, Permission, RoleBinding, ...
    extensions/
        permission_extension.py
        role_extension.py
        core_permissions.py
        project_permissions.py
        core_roles.py              # SystemAdminRole, ProjectOwnerRole, ...
    restapi/
        v1/
            rbac_controller.py
    events.py
    exceptions.py
```

## Key Flows

**Check Permission (hot path):**

1. Controller middleware receives request, resolves principal via
   `1-authentication.middleware`.
2. Controller calls
   `rbac_evaluator.require_permission(principal=..., permission_key="project:<id>:runs.dispatch", now=utcnow())`.
3. `rbac_evaluator` asks `cache.get_effective_permissions(principal)`
   — on miss, assembles bindings from `role_bindings` filtered by
   principal's user id + current group ids, merges
   `role_permissions`, and caches the resulting set under a TTL of 60
   seconds or until an invalidation event arrives.
4. Evaluator applies deny-beats-allow and returns `AuthzDecision`.

**Assign Role:**

1. Admin POSTs to `/api/v1/rbac/bindings`.
2. `binding_service.assign_role` validates the role exists, validates
   the scope is legal (e.g., `scope_kind = PROJECT` requires
   `scope_id`), inserts the row, stages `entity.role.assigned`.
3. Commit triggers the outbox publisher; subscribers include
   `cache.invalidate_principal` and `1-audit-log`.

**Catalog Reload on Extension Load:**

1. `E-extension-lifecycle.on_service_ready` invokes
   `catalog.load_catalog_from_registry`.
2. Catalog validates uniqueness of `permission_key`, resolves
   `RoleExtension` → `PermissionExtension` dependencies, writes the
   in-memory snapshot.
3. `entity.rbac.catalog.reloaded` publishes for observers.

## Error Handling

- `SemanticError` — raised on malformed `permission_key` or illegal
  scope combinations. NEVER caught per AGENTS.md — bubbles to the
  controller and produces HTTP 500.
- `RoleNotFoundError` — HTTP 404 on assign.
- `BindingNotFoundError` — HTTP 404 on revoke.
- `PermissionKeyCollisionError` — raised at catalog load; surfaces the
  offending extension pack and aborts that pack's load.
- `AuthorizationError` — 403 from `require_permission`; never thrown
  from `check_permission` itself.
- On internal evaluator errors the system SHALL raise
  `RbacEvaluationError` (fail closed). Example multi-line error
  message:

  ```python
  err_msg_lines = ["Failed to evaluate permission."]
  err_msg_lines.append("PRINCIPAL: {}".format(principal.user_id))
  err_msg_lines.append("KEY: {}".format(permission_key))
  err_msg_lines.append("CAUSE: {}".format(cause))
  err_msg = os.linesep.join(err_msg_lines)
  raise RbacEvaluationError(err_msg) from cause
  ```

## Security Considerations

- `system:rbac.admin` gates every mutating RBAC endpoint.
- `system:rbac.read` gates binding enumeration; project-scoped
  binding reads additionally require
  `project:<id>:rbac.read`.
- Deactivated principals evaluate as `allow=False` with reason
  `principal_deactivated`.
- The evaluator never consults an unauthenticated request — controllers
  always resolve the principal first.
- Catalog load failures are visible on
  `E-extension-registry-ui`; in-tree permissions and roles load
  regardless of extension failures.

## Observability

Metrics:

- `pychestrate_rbac_check_total{decision,namespace}` — `decision` one
  of `allow|deny`, `namespace` one of `system|project`.
- `pychestrate_rbac_check_duration_seconds{namespace}` — histogram.
- `pychestrate_rbac_cache_hits_total`, `..._misses_total`.
- `pychestrate_rbac_role_bindings_active{scope_kind}` — gauge.
- `pychestrate_rbac_catalog_permissions` / `..._roles` — gauges.
- `pychestrate_rbac_catalog_load_failures_total{source_name}`.

Log events: `rbac.check.allowed`, `rbac.check.denied`,
`rbac.role.assigned`, `rbac.role.revoked`, `rbac.role.override`,
`rbac.permission.denied`, `rbac.catalog.reloaded`,
`rbac.catalog.failed`.

Trace spans: `rbac.check_permission`, `rbac.binding.assign`,
`rbac.binding.revoke`, `rbac.catalog.load`.

## Open Questions

- Should we expose a dedicated `deny-list-first` evaluation trace for
  debugging, or rely on log events? Proposed: ship a
  `reason_trace` field in `AuthzDecision` behind a feature flag.
- Do project archives hard-delete bindings or tombstone them? Current
  plan: tombstone and exclude from evaluation; revisit when
  `2-retention-policies` lands.
- Can a `RoleExtension` override an in-tree role's permissions or only
  introduce new roles? Initial answer: new roles only; overrides are
  forbidden to keep policy debuggable.
