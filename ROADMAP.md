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

## REST API Contract

The authoritative contract for the `/api/v1/*` REST surface lives in
[`specs/openapi/pychestrate.yaml`](specs/openapi/pychestrate.yaml).
It covers every currently-implemented endpoint and the Phase 3
minimum-viable test-run slice (planned operations are flagged with
`x-pychestrate-status: planned`). The same file is consumed by
`codecraftai-restclient-base`'s `RestClientGenerator` to generate the
typed `codecraftai-restclient-pychestrate` Python client in a follow-on
PR, and is the reference the parallel server-side route
implementations conform to. Every PR that touches the REST surface
must update this spec in the same PR; `make openapi-validate` is the
enforcement gate.

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

## UI Remediation Program (2026-09)

A usability and presentation audit of the consumer web UI (September
2026) produced 179 findings; the remediation runs as seven phases. The
audit and the phase plan are tracked outside the repo; this section
records the decisions and status that the code alone does not show.

### Decisions

- **`/resources/*` stays, inside the shell.** The server-rendered
  resources blueprint covers IP pools, reservations, allocation
  history, tags, and health monitoring that the `/resource-pools`
  web-component bundle does not. Rather than retire it, every
  `/resources/*` handler now renders as a fragment inside the site
  shell (`_wrap_resources_handler_in_shell`), and the shell navigation
  links the three pages the bundle lacks (IP Pools, Reservations,
  Resource Health). The overlap between the legacy pools/resources
  pages and the bundle remains a known duplication; retiring the
  legacy pools and resources list pages is deferred until the bundle
  exposes checkout / checkin.
- **One owner per concept.** Bundle pages own the global,
  cross-project view of Builds, Pipelines, Tests, and Secrets; the
  project-scoped server pages own the per-project view. The
  `/admin` landing routes owned by `pyc-admin-bundle` no longer
  render the server dashboard first (they emit an empty mount point),
  and `/admin/dashboard` remains the only server-rendered landing
  page.
- **Strict templates.** The jinja environment runs with
  `StrictUndefined`; a template that reads an attribute the handler
  never supplied fails loudly instead of rendering a blank. The
  phase-13 render-smoke suite renders every template against fixtures
  derived from the manager response dataclasses. Roll back for one
  release with `PYCHESTRATE_TEMPLATE_STRICT_UNDEFINED=0`.
- **Sign-in and sign-out are CSRF-gated.** `GET /login` mints a token
  into the anonymous session and the form carries it; `GET /logout`
  renders a confirmation page whose button POSTs. The shell's sign-out
  control POSTs with the token the shell document carries.
- **Unknown paths are 404s, not sign-in prompts.** The catch-all only
  redirects anonymous browsers to `/login` for paths a registered
  bundle owns; everything else gets the shared error page
  (`site_shell/error_pages.py`), inside the shell when signed in.
- **Static assets are content-hashed.** Templates link assets through
  `static_url(...)`, which appends a content hash; versioned URLs are
  served immutable for a year, bare URLs with `no-cache` plus an
  `ETag`. Bundle stylesheets are linked in the shell document's
  `<head>` so bundle views no longer paint unstyled.

### Status

| Phase | Scope | State |
|---|---|---|
| 0 | Guardrails: strict templates, render-smoke suite, endpoint lint | Done |
| 1 | Crashing pages, wrong data, broken controls | Done |
| 2 | Resources in the shell, error pages, catch-all, CSRF, caching, dead assets | Done |
| 3 | Shared fragment stylesheet (`pyc-fragment.css`), macros (`site_shell/_macros.html`), filters, confirm dialog delegate, field errors, permission flags, glossary (`userguide/18-00-ui-glossary.rst`) | Done |
| 4 | Per-area migration: icons as inline SVG, status badges, pagers, empty states, breadcrumbs, table semantics, tokens, setup wizard, log viewer, calendar, forms | Done |
| 5 | Shell and bundle accessibility: landmarks, skip link, theme toggle, palette combobox, list-valid sidebar, live regions, component labels | Done |
| 6 | Browser verification (Playwright + axe-core against a local dev server), regression tests (`phase13`), this record | Done |

Verification (2026-09-04, local dev server, Chromium): every audited
page renders inside the shell with one `main` landmark and one `h1`,
in light and dark themes, with zero serious or critical axe-core
violations, except the two pages below. Anonymous requests for unknown
paths receive a 404; signed-in requests receive the shell-wrapped 404;
sign-out requires a POST.

Known remaining items:

- `mj-select`'s internal trigger button has no accessible name when
  nothing is selected (`/builds`, `/runs`, and any bundle list using
  it). The `label` attribute is set on the host; the fix belongs in
  `codecraftai-webworks`.
- Low-severity polish deferred: one shared stylesheet for the eleven
  bundle CSS files (A-7) and host-level styling of `mj-button` and
  scope chips in the bundle CSS (B-9, B-10), both of which depend on
  component internals in `codecraftai-webworks`.
- About 30 layout-only inline `style` attributes remain in the
  fragments (calendar grid rows, a few form widths); all colours and
  font sizes flow through tokens.

Also done after the phase table above: the duplicate sidebar tables in
the admin and secrets bundle entries are gone (S-22), release templates
show repository names with links (P-53), and every fragment's
`{% block title %}` now feeds the browser tab title through the shell
wrapper (P-46, C-15), so detail pages are titled by their entity.
