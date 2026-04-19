# 1-rbac — Tasks

## Milestones

- **M1 — Skeleton:** Tables live, in-tree permission catalog and role
  presets loaded, `check_permission` evaluates `system:<action>` keys
  from explicit bindings, hot-path middleware wired in one controller.
- **M2 — Core Behavior:** Project-scoped evaluation, organization
  inheritance, full binding CRUD REST surface, `PermissionExtension`
  and `RoleExtension` surfaces with reference implementations, event
  emission, cache invalidation over `0-message-bus`.
- **M3 — Hardening:** Out-of-tree extension loads new permissions and
  roles, metrics/logs/traces complete, perf baseline, Sphinx docs, and
  catalog load-failure resilience.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Land the `roles`, `permissions`, `role_permissions`, and
      `role_bindings` tables as an `EntityMigrationExtension` pack.
- [ ] T1.2 — Declare `PermissionExtension` and `RoleExtension`
      `ResourceExtension` bases.
- [ ] T1.3 — Implement `catalog.load_catalog_from_registry` with
      duplicate-key detection and namespace validation.
- [ ] T1.4 — Ship `CorePermissionExtension` declaring the
      `system:*` keys (`users.read`, `users.write`, `rbac.admin`,
      `rbac.read`, `secrets.admin`, `audit.read`, `flags.admin`).
- [ ] T1.5 — Ship `SystemAdminRole` and `AuditorRole` in-tree.
- [ ] T1.6 — Implement `rbac_evaluator.check_permission` covering the
      `system:<action>` path with deny-beats-allow.
- [ ] T1.7 — Implement `rbac_evaluator.require_permission` shortcut.
- [ ] T1.8 — Wire the middleware hook that controllers call to guard a
      route.

### M2 — Core Behavior

- [ ] T2.1 — Implement `binding_service.assign_role` with scope
      validation and outbox publication of `entity.role.assigned`.
- [ ] T2.2 — Implement `binding_service.revoke_role` with
      `entity.role.revoked`.
- [ ] T2.3 — Extend `check_permission` to the `project:<id>:<action>`
      namespace with group-based binding resolution.
- [ ] T2.4 — Implement `inheritance.seed_project_permissions` on
      `entity.project.created` consumption.
- [ ] T2.5 — Ship `ProjectPermissionExtension` and the project role
      presets (`ProjectOwnerRole`, `ProjectEditorRole`,
      `ProjectViewerRole`).
- [ ] T2.6 — Implement `cache.get_effective_permissions` LRU with
      bus-driven invalidation on `entity.role.assigned|revoked`,
      `entity.user.deactivated`, `entity.group.membership.changed`.
- [ ] T2.7 — Wire REST controllers under `/api/v1/rbac/...`
      (list roles, list permissions, CRUD bindings, `/check`).
- [ ] T2.8 — Implement `RoleNotFoundError`, `BindingNotFoundError`,
      `PermissionKeyCollisionError`, and `AuthorizationError` with
      `os.linesep.join(...)` multiline messages.

### M3 — Hardening

- [ ] T3.1 — Emit every metric listed in requirements.md NFR-3
      (`pychestrate_rbac_*`).
- [ ] T3.2 — Emit every log event listed in NFR-3.
- [ ] T3.3 — Add trace spans `rbac.check_permission`,
      `rbac.binding.assign`, `rbac.binding.revoke`,
      `rbac.catalog.load`.
- [ ] T3.4 — Benchmark `check_permission` against a 10k-binding
      fixture and hold < 5 ms p95.
- [ ] T3.5 — Implement resilience: a single
      `PermissionExtension|RoleExtension` failure marks the pack
      `faulted` but does not prevent boot.
- [ ] T3.6 — Generate Sphinx docs for the public and internal API.
- [ ] T3.7 — Ship an out-of-tree `pychestrate-ext-rbac-fixture` sample
      adding a new permission key and role preset; exercise via
      `E-extension-host`.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS acceptance criterion in
      Requirements 1–4.
- [ ] TT-2 — Hypothesis-based property tests: Property 1 (deny beats
      allow), Property 2 (deterministic evaluation), Property 3
      (group-binding reflects current membership), 1000 cases each.
- [ ] TT-3 — Integration test: create project, assign owner role to
      user, add user to a group bound at organization scope with
      `inherits_into_project = True`, revoke a binding, assert every
      step produces exactly one audit record and that subsequent
      `check_permission` calls reflect the change within 100 ms.
- [ ] TT-4 — Extension-point test: an out-of-tree extension declares
      a new permission key and a role that uses it at
      `PRECEDENCE = 500`; an assignment exercises the new permission
      against `check_permission`.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface has at least one in-tree reference
      implementation (`CorePermissionExtension`,
      `ProjectPermissionExtension`, `SystemAdminRole`,
      `ProjectOwnerRole`, ...) and one test-only override using a
      different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 1 —
      Identity & Projects in specs/implementation-plan.md
