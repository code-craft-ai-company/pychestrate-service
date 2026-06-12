# 9-admin-ui — Tasks

## Milestones

- **M1 — Skeleton:** `<pyc-admin-ui>` shell with tablist, hash router, permissions fetch, empty-state for zero-access user, themed via tokens.
- **M2 — Core Behavior:** Users, Roles, Secrets (hosting `<pyc-secret-editor>`), Feature Flags, System Health, Audit Log, Maintenance Mode, Extensions (hosting `<pyc-extension-registry>`). Command palette, toasts with audit deep-links.
- **M3 — Hardening:** Property tests, client metrics, a11y audit, palette fallback, rescan timeout, Sphinx docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/ccai/pychestrate/webservice/webinterface/components/pyc-admin-ui/` with TypeScript build wiring.
- [ ] T1.2 — Implement `pyc-admin-ui.ts::PycAdminUi` shell with observed attributes `default-tab`, `disable-palette`, `rescan-timeout-seconds`, `aria-label`.
- [ ] T1.3 — Implement `permission-set.ts` and `tab-registry.ts`; declare built-in tabs with `requiredPerms`.
- [ ] T1.4 — Implement `admin-router.ts` hash router with `push`, `parse`, `onChange`.
- [ ] T1.5 — Author `styles.css` referencing `--pyc-admin-ui-*` tokens, multi-line per AGENTS.md.
- [ ] T1.6 — Fetch `GET /api/v1/me/permissions` and render tabs accordingly; render `slot="forbidden"` when empty.
- [ ] T1.7 — Mount `GET /admin` server-side document shell that imports the bundle.

### M2 — Core Behavior

- [ ] T2.1 — Implement `tabs/pyc-admin-tab-users.ts` listing users and groups; CRUD through REST.
- [ ] T2.2 — Implement `tabs/pyc-admin-tab-roles.ts` for role/permission assignments.
- [ ] T2.3 — Implement `tabs/pyc-admin-tab-secrets.ts` listing secrets and hosting `<pyc-secret-editor>`.
- [ ] T2.4 — Implement `tabs/pyc-admin-tab-feature-flags.ts`.
- [ ] T2.5 — Implement `tabs/pyc-admin-tab-system-health.ts` rendering `0-system-health` probes.
- [ ] T2.6 — Implement `tabs/pyc-admin-tab-audit-log.ts` with filter pills and `POST /audit/export`.
- [ ] T2.7 — Implement `tabs/pyc-admin-tab-maintenance.ts` with typed-confirm toggle.
- [ ] T2.8 — Implement `tabs/pyc-admin-tab-extensions.ts` hosting `<pyc-extension-registry>` and wiring `pyc-extension-registry-rescan-request`.
- [ ] T2.9 — Implement `palette.ts` with `Ctrl/Cmd+K`, 150 ms debounce, grouped results, keyboard navigation.
- [ ] T2.10 — Implement `toast.ts` with audit deep-link builder; live-region announcements.
- [ ] T2.11 — Emit `pyc-admin-ui-ready`, `-tab-switched`, `-navigated`, `-mutation`, `-rescan`.

### M3 — Hardening

- [ ] T3.1 — Beacon client metrics per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: shell TTI p95 < 400 ms, tab switch p95 < 150 ms, palette open p95 < 80 ms, palette query p95 < 200 ms. Fail CI on regression.
- [ ] T3.3 — Axe audit: `role="tablist"`, `role="tab"`, `role="tabpanel"`, palette `role="dialog"` with focus trap; fail CI on violations.
- [ ] T3.4 — Palette fallback to client-side partial index on server failure.
- [ ] T3.5 — Rescan progress banner with 60 s timeout and retry affordance.
- [ ] T3.6 — Degraded-permissions state with 15 s retry cadence.
- [ ] T3.7 — Sphinx doc: admin surface tour, tab catalog, palette contract, observability guide.
- [ ] T3.8 — Verify no hard-coded colors / hex / absolute font sizes in `styles.css`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–5).
- [ ] TT-2 — Property-based tests implementing Property 1 (tab visibility purity), Property 2 (palette scoping), Property 3 (audit-link consistency) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 10 scenario — admin logs in, edits a secret, toggles maintenance mode, re-scans extensions; audit log contains each action and the UI surfaces deep-links.
- [ ] TT-4 — Extension-integration test: a test-only extension registers; the Extensions tab lists it; operator triggers rescan; new extension appears.
- [ ] TT-5 — Browser E2E (Playwright-style): open `/admin`, verify tablist, palette opens on `Ctrl+K`, selecting a user navigates to Users tab focused on that user; dark mode toggles without breaking the shell.
- [ ] TT-6 — RBAC test: user with only `audit_log.view` sees only the Audit Log tab; direct-URL access to other tabs shows forbidden state.
- [ ] TT-7 — Palette fallback test: stub `/admin/search` to 500; palette falls back to client-side index with a banner and no console errors.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
