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

## Where We Are: `v0.0.7-preview` + unreleased work on `main` (2026-09)

**Status: developer preview.** Use it to evaluate the product and to
develop it; it is not supported for production use beyond the project
author and direct collaborators.

The latest tag is `v0.0.7-preview` (2026-05-20). `main` carries four
months of work since then, listed under **Unreleased** in
[`CHANGELOG.md`](CHANGELOG.md); it ships with the next preview tag. The
previously published `v0.1.0-alpha` and `v0.1.0-alpha.2` tags overstated
the project's maturity and remain in the git history for reference only.

### Version numbers

| Signal | Where | Meaning |
|---|---|---|
| Release | git tag `vX.Y.Z-suffix` | The release. `CHANGELOG.md` has a section per tag. |
| Package version | `version` in `pyproject.toml` | Set to the tag's number in the tagging commit; the Sphinx documentation reads its release number from it. |
| REST contract revision | `info.version` in `specs/openapi/pychestrate.yaml` | Counts revisions of the API document; it is not a service release number. |

### What works on `main`

- **Platform (Layer 0):** the web service under gunicorn (systemd unit
  and nginx TLS front in the alpha deploy), SQLite or Postgres through
  alembic migrations, the in-process message bus, object store, system
  health, the extension host, and the first-run setup wizard.
- **Identity and access (Layer 1):** sign-in at `/login`, users, roles
  and role bindings on the modern RBAC evaluator, sessions, audit log,
  secrets, feature flags; every REST route requires a signed-in
  principal unless it is on the anonymous-access allowlist.
- **Domain entities (Layer 2):** projects (members, repositories,
  builds, infrastructure, tests, releases, release templates, calendar,
  watches), resources (pools, IP pools, allocations, reservations,
  health, tags), variables and scopes, retention policies,
  notifications, project templates.
- **Pods and orchestration (Layers 3–6):** pod enrollment with a
  client-certificate CA, signed job envelopes, a long-poll dispatch
  transport, run ingest with live progress and artifacts; test, build,
  provisioning, pipeline, and RPA runs.
- **Web UI (Layer 9):** the site shell (sidebar, command palette,
  permission-aware navigation), pages for every domain above, and UI
  profiles that hide the automation domains a team does not use.
- **Operations:** the alpha deploy scripts (systemd, nginx, mutual TLS
  for pods, scoped sudoers, certificate renewal), a REST API described
  by the OpenAPI contract, and an MCP endpoint.

### What is not there yet

- Single sign-on (OIDC, SAML): the auth-provider extension point
  exists, but only local accounts ship.
- Multi-host or highly available deployments; the message bus is
  in-process.
- A packaged install for outside organizations (container image,
  installer); the dependencies are published on PyPI, but the service
  itself runs from a checkout.

### Test coverage

About 280 testbase modules under `ccai.tests.singlehost` cover the
service. Most run in-process; the Playwright and httpx suites in
`phase11` and `phase12` drive a live server named by
`PYCHESTRATE_TEST_BASE_URL`. CI runs a subset of the in-process
modules; see `.github/workflows/test.yml`.

## Path to `v0.1.0-alpha`

The first honest alpha requires a coherent product slice — a user can sit
down at the UI and complete a meaningful workflow without falling off a
cliff. The slice candidates being considered:

- **"Operate the test orchestration core."** A pod can be registered, a
  job can be dispatched to its client, the result tree can land in the
  artifact store, and a run can be inspected end-to-end in the UI. This
  is the most product-defining slice. Its phases 3 (client plane) and 5
  (run state machine, dispatch, results) now exist on `main`; what
  remains is the loop running reliably against a real enrolled pod,
  which the September 2026 experience audit found still breaks in
  places (for example, a cancel does not stop the job on the pod).
- **"Run pychestrate as an internal Jenkins replacement."** Builds in,
  results out, plus the project/resources surfaces that already work.
  Smaller scope than the orchestration core but still requires the
  client-side agent pieces.

The navigation shell both candidates compose into shipped with the
PR1–PR6 sequence below.

## Path to `v0.1.0-beta`

Beta requires *every* spec under the chosen `v0.1.0` line implemented and
documented. For the orchestration-core alpha that includes Layer 6 (build
orchestration & artifacts), Layer 7 (infrastructure orchestration), Layer
8 (webhooks + embedded views), Layer 9 (full UI), and the relevant Layer
E extension points wired and documented.

Beta also assumes the test coverage gaps in preview are closed — every
implemented surface has functional tests, the live-server suites
(`phase11`, `phase12`) run in CI against a freshly started server, and a
Playwright suite covers the unified shell's critical paths.

## REST API Contract

The authoritative contract for the `/api/v1/*` REST surface lives in
[`specs/openapi/pychestrate.yaml`](specs/openapi/pychestrate.yaml).
It is meant to cover every implemented endpoint (operations not yet
implemented are flagged with `x-pychestrate-status: planned`). The same
file is consumed by `codecraftai-restclient-base`'s `RestClientGenerator`
to generate the typed `codecraftai-restclient-pychestrate` Python
client, and is the reference the server-side route implementations
conform to. Every PR that touches the REST surface must update this spec
in the same PR. The `docs` CI workflow (`.github/workflows/docs.yml`)
runs `make openapi-validate` on every push and pull request; it checks
that the document is valid OpenAPI, not that it matches the live
routes, and the September 2026 audit found live routes missing from it
and implemented operations still flagged `planned`.

## Site-Shell Refactor Sequence (PR1–PR6) — complete

The sequence that bridged `-preview` to the navigation shell every
alpha workflow lives inside. All six landed in `v0.0.3-preview` and
`v0.0.4-preview`:

- **PR1** — Backend route rename `/config/login` → `/login`,
  `/config/*` → `/admin/*`, `ui.admin.view` permission (#200).
- **PR2** — UI/REST session cookie bridge for `/api/v1/me/*`,
  `RbacRoleBinding` seed + backfill migration (#201).
- **PR3** — M1 site shell skeleton: `<pyc-site-shell>` web component,
  sidebar registry, server-side shell document, chromeless route list
  (#203).
- **PR4** — The admin UI inside the shell (#204).
- **PR5** — M2 core behavior: command palette, keyboard sidebar
  navigation, mid-session 401 handling, permission diff events (#205).
- **PR6** — M3 hardening: property-based tests, client metrics,
  accessibility checks, and the site-shell chapter of the user guide,
  `userguide/17-00-site-shell.rst` (#206).

The next milestone-bumping work is to pick one of the alpha-slice
candidates above and drive its dependencies to completion.

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
  and `/admin` is the one administration landing page: the old
  server-rendered `/admin/dashboard` and the `/admin/overview` alias
  redirect to it.
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

Re-verified 2026-09-29 (staging, Chromium, axe-core 4.10.2): the 39
navigation pages plus the home page and the error-types page report no
axe violation of any impact at page load, in the light theme, the OS dark
theme and the explicitly chosen dark theme; and the accessibility tree of
those pages has a name on every one of its 56 form controls. The
`mj-select` item above no longer reproduces there (the `label` on the host
names its trigger). Fixed since the 2026-09-04 record, each with a test:
the skip link's target existed only after the link was used, a skipped
heading level on Enrollment Tokens, white text on the dark theme's
light-blue primary buttons (3.55:1), six `mj-text-field` / `mj-textarea`
controls with no name, the run progress bar's name, focusable chart points
inside the `aria-hidden` SVG, and sortable headers that answered only the
mouse. Four of these work around defects in `codecraftai-webworks` (its
`mj-data-table` sorts on click only, `mj-chart` makes points tabbable
inside an `aria-hidden` SVG, `mj-text-field` takes its name only from its
own `label`, and the dark `--mj-text-on-accent` is white); the workarounds
can go when the library fixes them. Not covered: a screen reader, and
pages behind a click.

Also done after the phase table above: the duplicate sidebar tables in
the admin and secrets bundle entries are gone (S-22), release templates
show repository names with links (P-53), and every fragment's
`{% block title %}` now feeds the browser tab title through the shell
wrapper (P-46, C-15), so detail pages are titled by their entity.

## Phase 11 — RPA Domain & UI Profiles (2026-09)

Specs: `specs/6-rpa-orchestration/` and `specs/9-ui-profiles/`;
catalog and phase entries in `specs/implementation-plan.md`.

### Status

| Milestone | Scope | State |
| --- | --- | --- |
| RPA M1 | `job_kind = "rpa"`; job type registry with versions and execution-mode drivers (process, tasker); project specifications; work-packet trigger (merge, JSON-schema validation, secret redaction, size cap, idempotency, capability filter) that mints a signed envelope and dispatches through Layer 5; REST under `/api/v1/rpa` and `/api/v1/projects/{id}/rpa`; project pages (jobs, specs, run form, detail, logs, cancel); client `rpa_executor` (both modes) and dispatch branch; alembic `f2a3b4c5d6e7` | Done 2026-09-05 |
| RPA M2 | Admin registry pages, progress frames `rpa.process.v1` and completion branch `rpa.result.v1`, client output streaming and process-group cancel, pipeline step and watch action, audit kinds, capability tag enrichment, pod capability advertisement (`PUT /clients/{id}/capabilities`), heartbeat-delivered cancel channel on the client, browser-side packet pre-check | Done 2026-09-06 |
| RPA M3 | `factory: rpa_job_type` for code-defined types, RBAC review, metrics, OpenAPI, docs, REST handler tests | Done 2026-09-05 (open: end-to-end run against an enrolled pod) |
| UI profiles M1 | Surface vocabulary (build, testing, rpa, infra), surface tags on the navigation manifest, filtering in `/api/v1/me/navigation` with a `ui_profile` payload, deployment setting as the `ui.profile.surfaces` global variable, admin page `/admin/ui-profile` plus REST `GET|PUT /api/v1/admin/ui-profile`, request-scoped `ui_profile` template global, project sub-nav gating | Done 2026-09-05 |
| UI profiles M2 | Per-user override (`ui_user_preference` table, `/account/preferences`, `/api/v1/me/preferences/ui.surfaces`), hidden-surface notice, header Preferences link | Done 2026-09-05 |
| UI profiles M3 | Bus event, audit kind, metric, OpenAPI, docs | Done 2026-09-05 |

### Decisions

- RPA rows keep `project_id` as a string reference so both the consumer
  web UI (integer project ids) and the orchestration REST surface (UUID
  project ids) can own specifications; Layer-5 rows use the UUID derived by
  `canonical_project_uuid` (UUID5 for consumer ids).
- Dispatch candidates for an RPA job come from the specification's target
  pod, else the project's enrolled pods (UUID projects), else every
  registered client in the deployment, narrowed by capability tags.
- Fleet navigation entries (Pods, Clients, Resources) stay core rather than
  `infra`; only Environments, Provisioning, and Blast-Radius Guards carry the
  infra surface. Runs carries build, testing, and rpa.
- The `taskplus` engine and the tasker protocol are never imported into the
  agent or the service; tasker jobs render `workflow.rendered.yaml` and run
  `taskplus workflow run` as a subprocess.

### Follow-up found while probing the alpha host

- The operator-facing agents routes (`GET /api/v1/clients:inventory`,
  `GET /api/v1/clients/{id}/capabilities`, and the agent-rollout POSTs)
  answered without any authentication, although the OpenAPI document
  declares session or API-key security for every route and the sibling
  clients routes gate on `system:clients.read`. Closed 2026-09-06: the
  reads now require `system:clients.read` and the rollout writes
  `system:clients.write` (both granted to the system-admin role); the
  route tests carry a permission seam and a 401 regression.

### Fixes surfaced by the Phase 11 browser sweep

- The audit bus wiring ran in both the phase-1 and phase-2 bootstraps, so
  every audit topic had two handlers and the second insert failed the
  `source_event_id` unique constraint (logged as a subscriber failure).
  `audit.bus_subscriber.wire_bus_subscribers` is now idempotent.
- The shared confirm delegate re-submitted from a promise microtask; when
  the confirmation came from the synchronous `window.confirm`, the browser
  ignored `requestSubmit()` because the original submit event was still
  dispatching, so `data-confirm` forms never submitted without the
  `mj-dialog` confirm helper. The resubmit now runs from a zero-delay task.
