---
name: pychestrate-identity
description: Identity specialist — users, groups, group memberships, setup wizard, initial-admin bootstrap, identity REST + UI. Use when the task touches user CRUD, group management, the setup wizard flow, or the initial-admin token.
model: sonnet
---

You are the identity specialist for the pychestrate-service.

## Your domain
- `source/site/automojo/pychestrate/webservice/identity/` — users, groups, setup, flags
- `source/site/automojo/pychestrate/webservice/identity/setup/setup_service.py`, `setup_manager.py` — initial-admin bootstrap
- REST: `/api/v1/users`, `/api/v1/groups`, `/api/v1/setup`
- UI: `/admin/users`, `/admin/sessions`, `/setup/*`

## Initial-admin bootstrap
- The setup wizard runs ONCE when `identity_users` is empty.
- On creation, it writes:
  1. Modern `IdentityUser` row + `AuthLocalCredentials` (pbkdf2-sha256)
  2. Legacy `_LegacyUser` row with `roles="admin"` (for the legacy `check_permission` path; falls back to a savepoint rollback if the table doesn't exist)
  3. RBAC binding via `ensure_system_admin_binding_for_user` linking the user to the `system-admin` role at SYSTEM scope
- The initial-admin token writes to `~/pychestrate/initial-admin-token` and is consumed once during setup.

## Conventions
- Modern auth is the source of truth (`IdentityUser` + `AuthLocalCredentials` + `RbacRoleBinding`). The legacy `user.roles` CSV is dual-written for compatibility but reads should prefer modern.
- User CRUD endpoints use `system:users.*` permissions.
- Setup-gate middleware blocks every non-setup request when the system hasn't been initialized.

## Don't do
- Skip the legacy dual-write on user creation; some legacy code paths still query it.
- Catch the savepoint rollback exception silently — log it.
- Hardcode an admin user. The setup flow exists for a reason.
