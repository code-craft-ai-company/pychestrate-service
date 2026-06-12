# 9-site-shell — Tasks

## Milestones

- **M1 — Skeleton:** `<pyc-site-shell>` registered, server-side adapter serves the shell document for every non-chromeless route, sidebar registry + permission-cache plumbing in place, empty-state renders for zero-permission users, themed via tokens.
- **M2 — Core Behavior:** Sidebar group/entry registration consumed by `9-admin-ui` and at least one other surface, command palette with provider fan-out, mid-session 401 toast, full-navigation permission refetch with diff event, keyboard sidebar navigation including type-to-jump, logout flow.
- **M3 — Hardening:** Property tests, client metrics, a11y audit, degraded-state banner, palette per-provider timeouts, Sphinx docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/ccai/pychestrate/webservice/webinterface/components/pyc-site-shell/` with TypeScript build wiring.
- [ ] T1.2 — Implement `pyc-site-shell.ts::PycSiteShell` with observed attributes `initial-route`, `permissions-endpoint`, `palette-timeout-ms`, `aria-label`.
- [ ] T1.3 — Implement `permissions/permission-set.ts` and `permissions/permission-cache.ts` (fetch, diff, degraded-state tracking).
- [ ] T1.4 — Implement `sidebar/sidebar-registry.ts` with `registerGroup`, `registerEntry`, `visible(perms)`; dedup by `route` with logged warning on collision.
- [ ] T1.5 — Implement `sidebar/sidebar-renderer.ts` with grouping, permission intersection, and an active-route highlight via `aria-current="page"`.
- [ ] T1.6 — Implement `routing/shell-router.ts` (path parsing, `history.pushState`, `popstate`, focus restoration to `<main>` `<h1>`).
- [ ] T1.7 — Implement `chrome/header.ts` with default brand + user menu + logout action wired to `POST /api/v1/auth/logout`.
- [ ] T1.8 — Implement `chrome/empty-state.ts` for the zero-visible-entries case.
- [ ] T1.9 — Author `styles.css` referencing `--pyc-site-shell-*` tokens, multi-line per AGENTS.md.
- [ ] T1.10 — Implement server-side `site_shell/shell_document.py` Jinja template, `site_shell/chromeless_routes.py`, and `site_shell/bundle_registry.py`; mount a catch-all route that serves the shell document for every non-chromeless GET.
- [ ] T1.11 — Wire the chromeless route list (`/login`, `/logout`, `/setup/*`, `/__health/*`, `/errors/{404,403,500}`) so those paths bypass the shell document.

### M2 — Core Behavior

- [ ] T2.1 — Coordinate with `9-admin-ui` to land the `shell.sidebar.registerGroup({groupId: "admin", ...})` call and per-page `registerEntry` calls in the admin bundle; verify the "Admin" group disappears when `ui.admin.view` is absent.
- [ ] T2.2 — Implement `palette/palette-registry.ts` (`registerProvider`, per-provider permission gating, 5 s default timeout).
- [ ] T2.3 — Implement `palette/palette-dialog.ts` (`role="dialog"`, `aria-modal="true"`, focus trap, `Ctrl/Cmd+K` to open, `Esc` to close, debounced fan-out).
- [ ] T2.4 — Coordinate with `9-admin-ui` to land an `admin.search` palette provider hitting `/api/v1/admin/search`.
- [ ] T2.5 — Implement permission-refetch-on-navigation; emit `pyc-site-shell-permissions-changed` with `{added, removed}` diff.
- [ ] T2.6 — Implement keyboard sidebar navigation: `ArrowDown`/`ArrowUp`, `ArrowRight`/`ArrowLeft` for group expand/collapse, `Enter` activate, type-to-jump prefix buffer with 1 s reset.
- [ ] T2.7 — Implement mid-session 401 handling: global listener for `pyc-session-401`, non-blocking toast, next-navigation redirect.
- [ ] T2.8 — Implement `chrome/degraded-banner.ts` non-blocking banner on permissions-fetch failure.
- [ ] T2.9 — Emit `pyc-site-shell-ready`, `-navigated`, `-sidebar-clicked`, `-permissions-changed`, `-empty-state-rendered`, `-palette-opened`.

### M3 — Hardening

- [ ] T3.1 — Beacon client metrics per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: shell TTI p95 < 400 ms, sidebar render p95 < 50 ms for 100 entries, navigation permission refetch p95 < 80 ms, palette open p95 < 80 ms, palette fan-out p95 < 250 ms with 5 providers. Fail CI on regression.
- [ ] T3.3 — Axe audit: `role="banner"`, `role="navigation"`, `role="main"`, palette `role="dialog"` with focus trap, `aria-current="page"` on the active entry, live-region announcements. Fail CI on violations.
- [ ] T3.4 — Property tests for sidebar visibility purity (Property 1), empty-state predicate (Property 2), palette permission scoping (Property 3), 1000 cases each.
- [ ] T3.5 — Sphinx doc: site-shell tour, sidebar registration contract for feature authors, palette provider contract, chromeless route contract, observability guide.
- [ ] T3.6 — Verify no hard-coded colors / hex / absolute font sizes in `styles.css`.
- [ ] T3.7 — Verify shell never writes the permission payload to `localStorage` / `sessionStorage`.

## Backend Tasks

- [ ] B-1 — Confirm `/api/v1/me/permissions` (owned by `1-rbac` /
      `8-rest-api-v1`) returns a JSON array of permission keys for the
      current principal, sized to fit in a single response (no
      pagination). Add the `ui.admin.view` key per `1-rbac`'s
      addition.
- [ ] B-2 — Audit every existing server-side route handler under
      `/admin/*` (after `9-admin-ui`'s rename from `/config/*`) to
      confirm each one carries the existing `require_permission`
      guard; sidebar visibility is not the security boundary.
- [ ] B-3 — Add `chromeless_routes.py` enforcement to the route
      registration pipeline so a feature accidentally putting a page
      at `/login` is rejected at startup with `ConfigurationError`.
- [ ] B-4 — Ensure `/logout` (browser convenience) is registered as
      chromeless and 303s to `/login`.

## Frontend Tasks

- [ ] F-1 — Integrate `9-admin-ui` pages into the shell main slot via
      `bundle_registry.py` so the admin bundle is injected for
      `/admin/*`.
- [ ] F-2 — Integrate `9-project-dashboard-ui` analogously so
      `/projects/<id>/dashboard` renders inside the shell.
- [ ] F-3 — Integrate `9-run-detail-ui` analogously for run-detail
      routes.
- [ ] F-4 — Migrate any existing in-page header/sidebar code in the
      already-merged surfaces to use shell-supplied chrome (delete
      duplicated logic).

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–7).
- [ ] TT-2 — Property-based tests implementing Property 1 (sidebar visibility purity), Property 2 (empty-state predicate), Property 3 (palette permission scoping) at 1000 cases each.
- [ ] TT-3 — Integration test: cold-boot scenario — authenticated admin lands at `/admin/users`, sidebar shows "Admin" group with all admin entries, sidebar clicks navigate without full page reload, permission refetch fires per navigation.
- [ ] TT-4 — Integration test: zero-permission user logs in, lands at `/`, sees empty state, can sign out via user menu.
- [ ] TT-5 — Integration test: mid-session role revocation — admin user with `ui.admin.view` navigates, role is revoked server-side, next navigation drops the "Admin" group and renders 403 if the target was `/admin/*`.
- [ ] TT-6 — Browser E2E (Playwright via `testbase`): unauthenticated visitor hits `/admin/users`, gets 303 to `/login?next=%2Fadmin%2Fusers`, signs in, lands at `/admin/users`. Second case: hits `/login?next=https%3A%2F%2Fevil.example.com%2Fphish`, signs in, lands at `/` (next-validation rejects).
- [ ] TT-7 — Browser E2E: keyboard-only user navigates the sidebar with arrow keys, type-to-jumps to "Audit Log", activates with Enter, palette opens with `Ctrl+K`, search returns results, `Esc` closes.
- [ ] TT-8 — RBAC test: user with only `audit_log.view` sees the Audit Log entry under "Admin" only if they also hold `ui.admin.view`; otherwise the "Admin" group is invisible.
- [ ] TT-9 — Palette resilience test: one provider always throws; other providers' results still render; the failing provider shows an inline error.
- [ ] TT-10 — httpx test: `/login` is served chromeless; `/admin/users` (with valid session) is served via the shell document and imports the admin bundle.

## Documentation Tasks

- [ ] D-1 — Author `usersguide/site-shell-authoring.md` covering: how
      to register a sidebar group/entry, how to register a palette
      provider, how to declare page Custom Elements, what the
      chromeless route contract is.
- [ ] D-2 — Update `9-admin-ui` Sphinx docs to reflect that admin
      pages live inside the shell (cross-link to this spec).
- [ ] D-3 — Update `specs/implementation-plan.md` Phase 10 entry to
      list `9-site-shell` as a co-shipping spec with `9-admin-ui`.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] At least two feature surfaces (`9-admin-ui` plus one other) are
      integrated into the shell via the sidebar registry, validating
      the contract works for more than the originating consumer
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
