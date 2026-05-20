# Changelog

All notable changes to `pychestrate-service` are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Pre-1.0 releases use the milestone suffixes defined in
[`ROADMAP.md`](ROADMAP.md) (`-preview`, `-alpha`, `-beta`, `-rc`).
Backward compatibility is not guaranteed across pre-1.0 tags; the schema
and runtime contracts are still in flux. A `-preview` tag does not
progress to `-alpha` of the same `MAJOR.MINOR` version — the version is
bumped when the project crosses the preview-to-alpha threshold.

## [Unreleased]

### Changed

- **Breaking:** Renamed the PR p19g long-poll routes from the
  `/api/v1/agents/{client_id}/...` namespace to
  `/api/v1/clients/{client_id}/...` to match the canonical "client"
  naming for the pod-side runtime. The two affected operations are
  `GET /clients/{client_id}/dispatches:next` and
  `GET /clients/{client_id}/heartbeat`. The supporting code module
  moved from
  `automojo.pychestrate.webservice.agents.restapi.v1.agent_dispatch_routes`
  to
  `automojo.pychestrate.webservice.clients.restapi.v1.client_dispatch_routes`,
  and the registration symbol from `register_agent_dispatch_routes`
  to `register_client_dispatch_routes`. No redirect shim is provided
  — this is an alpha pre-stability rename. OpenAPI spec bumped to
  `0.0.5-preview` (PR p19h).

## [0.0.3-preview] — 2026-05-17

Renamed the active release line from `v0.1.0-alpha` to `v0.0.x-preview`
to set honest expectations. The previously published `v0.1.0-alpha` and
`v0.1.0-alpha.2` tags overstated the project's maturity — alpha implies
feature-complete for a slice, and at the time those tags were cut
roughly two-thirds of the spec catalog was unstarted. Those tags remain
in the git history for reference.

### Changed

- Active release line is now `v0.0.x-preview`. See
  [`ROADMAP.md`](ROADMAP.md) for milestone definitions and what
  `v0.0.3-preview` includes.

### Added (since `v0.1.0-alpha.2`)

- **Unified `/login` HTML surface** with `?next=<path>` redirect and
  same-origin validation; the legacy `/config/login` is retired (#200).
- **`/admin/*` route mount** for the administrator surface; the legacy
  `/config/*` blueprint moved verbatim (#200).
- **`system:ui.admin.view` permission** granted by `SystemAdminRole`,
  intended as the UX-gating key for the upcoming sidebar (#200).
- **`GET /api/v1/me/permissions`** endpoint returning the principal's
  full system-permission set (#200).
- **`htmlui/next_validator.NextValidator`** enforcing the
  spec-1-authentication NFR-2 same-origin rules on the `?next` parameter
  (#200).
- **Cookie bridge in `PychestrateSessionMiddleware`** so `/api/v1/me/*`
  resolves principals from both the UI signed cookie and the REST
  DB-backed cookie (#201).
- **`RbacRoleBinding` seed helper + alembic backfill migration** so the
  modern RBAC evaluator returns the expected permission set for the
  setup-wizard-created admin user (#201).
- **Tailscale-issued HTTPS** at the nginx frontend, with `:80` → `:443`
  redirect to the canonical hostname (#197, #198).
- **`SECURITY` / `NETWORK` / `RUNTIME` env vars** routed through
  `PychestrateVariables` (#196).
- **Phase-11 login-flow tests** (httpx + Playwright) targeting the live
  HTTPS deploy; 14/14 passing (#195, #201).

## [0.1.0-alpha] — 2026-05-09

First tagged alpha. Closes the **Phase 1 — Identity & Projects** slice
of `specs/implementation-plan.md`. The service can be deployed,
operated end-to-end, and exercised by an admin against either SQLite
(development) or Postgres (production) with the deploy runbook in
`userguide/13-00-alpha-deployment.rst`.

### Added

- **Modern auth stack on the consumer UI.** The
  `/config` / `/resources` / `/projects` blueprints' login flow,
  session validation, and logout now route through
  `security.auth.local_flow` + `session_service`. Implemented via
  `ConsumerUISecurityAdapter` so handler call shapes were preserved
  (#164).
- **RBAC on `rbac_evaluator`.** Consumer-UI permission gating now
  routes through `rbac_evaluator.check_permission` against the
  modern `rbac_*` tables; consumer-UI gates pass canonical
  `system:<action>` permission keys (e.g. `system:resources.manage`).
  Permission catalog populated by the in-tree
  `CorePermissionExtension`; `SystemAdminRole` preset grants the
  default admin set (#167).
- **Alembic migrations** as the production schema strategy. Two
  revisions ship: `b26815647a3c` (modern `PychestratePhase1Base`
  baseline) and `340748287bde` (legacy `PychestrateModelBase`
  stopgap for the consumer-UI surfaces still on `core.managers`).
  Both pass `alembic upgrade head` against fresh SQLite and Postgres.
- **CI workflow** (`.github/workflows/test.yml`) gating six jobs:
  poetry install + sanity import, alembic-upgrade-sqlite,
  alembic-upgrade-postgres, testbase-singlehost-sweep,
  phase10-e2e-isolated, production-startup-smoke. All gating
  (#168, #169, #170, #171, #172, #173, #175).
- **Production-startup smoke test** that forks
  `build_wsgi_application_for_production()` in a subprocess
  against an alembic-migrated SQLite DB and probes `GET /` (#165).
- **Phase-1 acceptance test** (`test_p13ae_alpha_acceptance_m1`)
  that walks the create-project → assign-member → set-variable
  chain and asserts each step emits an audit event (#168).
- **Tier-1..4 consumer-UI e2e coverage.** Anonymous (p13q),
  authenticated happy path (p13r), RBAC permission gating
  (p13v), static assets (p13u), tier-4 session lifecycle
  (concurrent sessions, CSRF rotation, expiry, post-logout)
  (#155, #163, #166).
- **Deploy runbook** (`userguide/13-00-alpha-deployment.rst`)
  covering environment variables, KEK / pepper / cookie-secret
  provisioning, alembic migrations, gunicorn invocation, and
  CI prerequisites (`AUTOMOJO_REPO_TOKEN` setup) (#168, #170).
- **Auth-stack documentation** (`userguide/12-00-consumer-ui-auth-stack.rst`)
  covering the legacy-vs-modern split, the migration history, and a
  detailed audit of the residual legacy import surface
  (Tier A: 225 utility imports — non-blocking; Tier B: 81 manager
  imports — Phase-2/3 territory) (#157, #176).
- **Extension authoring guide** (`userguide/11-00-extensions.rst`)
  covering factory protocols vs resource extensions, out-of-tree
  packaging recipe, and a complete worked example for a
  production Argon2id password hasher.
- **Phase 1..6 builtin extensions** registered through the
  `extensions/bootstrap.py` chain: phase1 (identity / RBAC /
  audit / project-templates / notification-channels),
  phase2..phase6 (audit-sinks, scopes, retention, etc.).

### Changed

- **`pychestrate-core` git-source dependency removed.** It shipped
  an empty `automojo/pychestrate/__init__.py` that converted
  `automojo.pychestrate` from a PEP-420 namespace package into a
  regular package, blocking access to
  `automojo.pychestrate.webservice` (which lives at
  `source/site/...`). Audit confirmed the dep was unused; removing
  it restored namespace package semantics. The `dbio.py` module
  in `source/packages/automojo/pychestrate/core/` that referenced
  pychestrate-core's content is left as dead code (no consumer)
  (#171).
- **`werkzeug` dependency removed.** Was a transitive of
  `pychestrate-core`. Used only by the legacy `SecurityManager`'s
  password-history and authenticate paths, both dead at runtime
  via the modern adapter. Top-level import in `security_manager.py`
  removed; the two call sites use lazy imports so an explicit
  invocation of the legacy auth path is the only thing that would
  trip an `ImportError` (a useful signal that the legacy auth
  surface needs full retirement) (#172).
- **Python `alembic` is a direct dependency** (was transitive
  through pychestrate-core). Pinned `^1.13.0` (#171).
- **CI workflow private-repo authentication** uses a fine-grained
  PAT injected as `AUTOMOJO_REPO_TOKEN` repo / org secret. The
  workflow installs a global `git url.<base>.insteadOf` rewrite
  before each `poetry install`, silently authenticating clones
  of the nine private `automojo-*` / `pychestrate-core` git deps.
  Setup procedure documented in the deploy runbook (#170).
- **Consumer-UI handlers no longer treat empty CSRF as a refresh
  signal.** `ConsumerUISecurityAdapter.validate_token` returns
  `csrf_token=""`; the cookie's CSRF is the source of truth on the
  modern stack so the dashboard handler now preserves it rather
  than overwriting (#164).

### Fixed

- **Postgres FK ordering bug** in the
  `include_legacy_core_orm_tables` migration. 123 inline
  `ForeignKeyConstraint` declarations on `op.create_table` calls
  were emitted in alphabetical order without respect to FK
  dependency order; SQLite was lenient at CREATE-TABLE time but
  Postgres rejected with `UndefinedTable`. All FKs now emit as
  separate `op.create_foreign_key` calls after every table exists,
  dialect-gated to skip on SQLite (which doesn't support
  `ALTER TABLE ADD CONSTRAINT`) (#175).
- **Postgres ENUM/table name collision.** The `orch_test_outcome`
  table shared a name with its `Outcome` enum; Postgres treats
  tables as implicit composite types in the same namespace so the
  second `CREATE` collided. Renamed to `orch_test_outcome_value`
  to follow the `<table>_<column>` enum-naming convention used
  elsewhere in the migration (#173).
- **`python -m alembic` shadow.** Repo root contains an
  `./alembic/` migrations directory; running `python -m alembic`
  from repo root resolved to the local namespace package which has
  no `__main__`. Switched to the `alembic` console script (whose
  launcher does not add cwd to `sys.path`) in CI and tests (#171).
- **`register_phase1_builtin_extensions` not idempotent.**
  Production startup hit `ConfigurationError: Project metadata
  field registry is already frozen` because `bootstrap_runtime`
  and `register_service_extensions` both invoked phase-1
  registration. Added an `is_registry_frozen()` guard (#165).
- **Test isolation in singlehost sweep.** Including the bare
  `phase1` package matched both `phase1/` AND `phase10/`
  directories via testbase's `startswith` path-prefix check, then
  pulled in every brittle p13 module via
  `collect_python_modules_for_tests`. phase1 is now enumerated by
  18 specific module names (phase2..phase9 are unaffected — no
  phase20+ siblings exist). The underlying testbase bug is logged
  for upstream report (#175).
- **`*ListResponse` dataclass unwrap** at consumer-UI handler
  call sites (`resources/`, `projects/`, `config/` blueprints).
  REST API was returning typed dataclasses; consumer-UI handlers
  expected plain lists. Single-call adapters added at every call
  site (#161, #162).
- **WSGI cookie handling** in `app_pychestrate_main`. Cookies set
  by the response were being dropped on the way out; tier-2 e2e
  surfaced the loss. Added a thin shim that copies `Set-Cookie`
  headers through (#155).
- **Watch create/edit form field translation.** Form fields
  shipped to `WatchManager.create` did not match the dataclass
  shape; the handler now translates form keys to manager keys
  before invoking (#156).

### Known limitations

These are documented in `userguide/13-00-alpha-deployment.rst`'s
"Known alpha limitations" section. None block alpha shipping;
all are tracked for follow-up:

- **Single-host only.** Persistence is centralized but the message
  bus is the in-process stub; multi-host deploys require Phase-2
  bus implementation.
- **Legacy schema co-resident with modern.** 21 consumer-UI route
  files still call into `core.managers.*`; the
  `include_legacy_core_orm_tables` migration ships them. Migrating
  off is Phase-2/3 territory.
- **No audit retention policy.** Audit subscriber writes
  indefinitely.
- **No HA story.** Process restart drops in-flight requests.

### Operator action required

For first-time deployments and CI:

1. Create a fine-grained PAT against the `automationmojo` org
   with `Contents: Read` on the nine private `automojo-*` /
   `pychestrate-core` repos.
2. Add it as a repo or org secret named `AUTOMOJO_REPO_TOKEN`.
3. Provision the KEK, pepper, and UI cookie secret per the
   procedure in the deploy runbook.
4. Run `alembic upgrade head` against your production database
   before first start.

[0.1.0-alpha]: https://github.com/automationmojo/pychestrate-service/releases/tag/v0.1.0-alpha
