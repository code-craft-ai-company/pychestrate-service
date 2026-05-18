# Pychestrate Service — Roadmap

This document defines what each release milestone means for this project and
tracks where we are in that progression. The detailed feature catalog and
per-feature specifications live in [`specs/implementation-plan.md`](specs/implementation-plan.md)
and the `specs/` subdirectory; this document is the *milestone-level* view
that sits above them.

## Milestone Definitions

The version-suffix convention is more conservative than typical SemVer
pre-release labels because the spec catalog in `specs/` is large (~108
features across 10 layers) and only a fraction is in `main`. Suffixes are
chosen to set honest expectations.

| Suffix | What it means | Stability |
|---|---|---|
| `-preview` | Early development. Foundation + a few domain surfaces work end-to-end on a deployed instance. Most of the spec catalog is unstarted. Breaking changes between preview tags are expected. | Not for use beyond the project author and direct collaborators. |
| `-alpha` | Feature-complete for a well-defined product slice — every layer the slice depends on is implemented, exercised by tests, and reachable through the UI. Schema and contracts still allowed to change, but only with a migration story. | Internal pilot. Data may need manual migration between alpha tags. |
| `-beta` | All spec-catalog features for the targeted release line are implemented. Focus shifts to hardening, performance, documentation, and operability. No new features land in `-beta`. | External pilot. Schema changes only via migrations; deprecation cycles begin. |
| `-rc` (release candidate) | All known issues resolved. No code changes accepted except for regressions found by RC testers. | Production trial for early adopters. |
| (no suffix) | General availability. Backwards-compatibility guarantees per SemVer. | Production. |

A `-preview` tag does **not** progress to `-alpha` of the same `MAJOR.MINOR`
version. When the project crosses the threshold from preview to alpha, the
version is bumped (e.g. `0.0.x-preview` → `0.1.0-alpha`).

## Where We Are: `v0.0.3-preview` (2026-05-17)

The previously published `v0.1.0-alpha` and `v0.1.0-alpha.2` tags
overstated the project's maturity — alpha implies feature-complete for a
slice, and at the time those tags were cut roughly two-thirds of the spec
catalog was unstarted. Those tags remain in the git history for reference;
the active line is `v0.0.x-preview`.

What works in `v0.0.3-preview`:

- **Layer 0 — Platform foundation:** web app host (gunicorn under systemd,
  fronted by nginx with Tailscale-issued HTTPS), persistence (SQLite +
  Postgres via alembic), message bus, object store, system health,
  extension host scaffolding.
- **Layer 1 — Identity & auth:** unified `/login`, RBAC on the modern
  `rbac_evaluator`, users / roles / role bindings (with seed + backfill
  migration), audit log, secrets, sessions, feature flags, first-run
  setup wizard at `/setup/*`.
- **Layer 2 — Domain entities:** projects (dashboard, CRUD, members,
  repositories, builds, infrastructure, tests, releases, calendar,
  watches), resources (core CRUD, pools, ip_pools, allocations,
  reservations, health, tags), variables / scopes, tagging, retention
  policies, notifications, project templates.
- **Layer 3 — Client / agent surfaces (partial):** clients, agents, pods
  REST APIs exist; consumer UI is thinner than for Layer 2.
- **Deploy + operations:** one-shot deploy script, scoped passwordless
  sudoers, GitHub Actions deploy via Tailscale, alembic migrations
  applied automatically per deploy, nginx HTTPS termination.

What is explicitly *not* in `v0.0.3-preview` (visible in `specs/` but
without source implementation):

- The unified site shell + sidebar / command palette / chromeless route
  registry (in flight as PR3–PR6 of the current refactor).
- Webhooks-in, release channels, agent upgrade channel,
  extension-registry UI.
- Most of phases 4–10 in the spec hierarchy: test orchestration, build
  orchestration & artifacts, infrastructure orchestration, observability
  beyond system-health, backup / DR.
- All `9-*` UI specs beyond admin / project-dashboard / run-detail (which
  exist as routes but not as a navigation-coherent app).
- The `1-authentication` SSO providers (OIDC, SAML) — only local-flow
  works today.

Test coverage in `v0.0.3-preview` is partial: route-level smokes for most
implemented surfaces plus a 14-test phase-11 suite that exercises the live
deploy. Approximately 20 phase-10 tests are broken on main due to
pre-existing `UI_COOKIE_SECRET` infrastructure issues; the gap between
"route is implemented" and "all CRUD operations on the route are tested
end-to-end" is significant.

## Path to `v0.1.0-alpha`

The first honest alpha requires a coherent product slice — a user can sit
down at the UI and complete a meaningful workflow without falling off a
cliff. The slice candidates being considered:

- **"Operate the test orchestration core."** A pod can be registered, a
  job can be dispatched to its client, the result tree can land in the
  artifact store, and a run can be inspected end-to-end in the UI. This
  is the most product-defining slice; depends on phases 3 (client plane)
  and 5 (run state machine, dispatch, results) which are largely
  unimplemented.
- **"Run pychestrate as an internal Jenkins replacement."** Builds in,
  results out, plus the project/resources surfaces that already work.
  Smaller scope than the orchestration core but still requires the
  client-side agent pieces.

Neither is in scope for `v0.0.x-preview`. The current refactor sequence
(PR1–PR6) is a prerequisite for either alpha candidate because it
delivers the navigation shell that the operator surfaces need to compose
into.

## Path to `v0.1.0-beta`

Beta requires *every* spec under the chosen `v0.1.0` line implemented and
documented. For the orchestration-core alpha that includes Layer 6 (build
orchestration & artifacts), Layer 7 (infrastructure orchestration), Layer
8 (webhooks + embedded views), Layer 9 (full UI), and the relevant Layer
E extension points wired and documented.

Beta also assumes the test coverage gaps in preview are closed — every
implemented surface has functional tests, the ~20 broken phase-10 tests
are either fixed or retired, and a Playwright suite covers the unified
shell's critical paths.

## Current Refactor Sequence (PR1–PR6)

This is the in-flight work that bridges `-preview` to the navigation
shell that any alpha workflow will live inside. Tracked here so the
roadmap reflects current activity:

- **PR1** — Backend route rename `/config/login` → `/login`,
  `/config/*` → `/admin/*`, `ui.admin.view` permission. **Merged.**
- **PR2** — UI/REST session cookie bridge for `/api/v1/me/*`,
  `RbacRoleBinding` seed + backfill migration. *Open as #201.*
- **PR3** — M1 site shell skeleton: `<pyc-site-shell>` Web Component,
  sidebar registry, server-side shell document, chromeless route
  registry enforcement. *Not started.*
- **PR4** — Integrate the existing admin UI into the new shell. *Not
  started.*
- **PR5** — M2 core behavior: command palette, keyboard sidebar
  navigation, mid-session 401 handling, permission diff events. *Not
  started.*
- **PR6** — M3 hardening: property-based tests, client metrics,
  accessibility audit, Sphinx documentation. *Not started.*

After PR6 lands, the next milestone-bumping work is to pick one of the
alpha-slice candidates above and drive its dependencies to completion.
