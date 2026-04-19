# 9-project-dashboard-ui — Tasks

## Milestones

- **M1 — Skeleton:** `<pyc-project-dashboard>` registered, fetches layout, renders tiles in a read-only 12-column grid, forwards attrs to `<pyc-metric-tile>`, themed via tokens.
- **M2 — Core Behavior:** Edit mode (add/remove/resize/reorder), save with conflict handling, add-tile dialog with extension kind listing, starter template seeding, broken-tile state.
- **M3 — Hardening:** Property tests, client metrics, a11y, keyboard drag, Sphinx docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/automojo/pychestrate/webservice/webinterface/components/pyc-project-dashboard/` with TypeScript build wiring.
- [ ] T1.2 — Implement `pyc-project-dashboard.ts::PycProjectDashboard` with observed attributes `project-id`, `edit-mode`, `refresh-multiplier`, `aria-label`.
- [ ] T1.3 — Implement `grid-model.ts` for 12-column non-overlapping placements, `serialize` / `deserialize`, validity checks.
- [ ] T1.4 — Implement `transport/dashboard-transport.ts` against `/api/v1/projects/{project_id}/dashboard`.
- [ ] T1.5 — Author `styles.css` referencing `--pyc-project-dashboard-*` tokens, multi-line per AGENTS.md.
- [ ] T1.6 — Instantiate `<pyc-metric-tile>` per placement and forward attributes.
- [ ] T1.7 — Mount `GET /projects/<id>/dashboard` server-side shell and serve bundle at `/ui/components/pyc-project-dashboard/pyc-project-dashboard.js`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `dnd.ts` with pointer drag + keyboard drag (Space to pick up, arrows to move, Space to drop, Esc to cancel).
- [ ] T2.2 — Implement resize handles + keyboard resize (Shift+arrows).
- [ ] T2.3 — Implement `tile-kind-catalog.ts` loader hitting `/api/v1/extensions/dashboard_tile_kinds.json` and merging built-ins.
- [ ] T2.4 — Implement `add-tile-dialog.ts` with per-kind attribute form, RBAC-gated extension-kind visibility.
- [ ] T2.5 — Implement save flow PUTing to the REST endpoint with revision check; handle 409 with merge banner and `pyc-project-dashboard-conflict`.
- [ ] T2.6 — Implement starter-template seeding when project has no layout; mark `dirty=true`.
- [ ] T2.7 — Implement broken-tile state aggregated from child `pyc-metric-tile-error` / `-extension-error` events; expose `slot="broken-tile-fix"`.
- [ ] T2.8 — Implement refresh-multiplier handling for tab-backgrounded state.
- [ ] T2.9 — Surface `slot="header"`, `slot="empty"`, `slot="save-error"`.

### M3 — Hardening

- [ ] T3.1 — Beacon client metrics per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: TTI p95 < 500 ms warm cache, 60 fps refresh across 20 tiles, insert p95 < 120 ms, save p95 < 600 ms. Fail CI on regression.
- [ ] T3.3 — Axe audit: `role="grid"`, `role="gridcell"`, `aria-rowindex` / `aria-colindex`, focus ring honored; fail CI on violations.
- [ ] T3.4 — Help dialog on `?` with focus trap and full keybinding list.
- [ ] T3.5 — Layout schema validator that ignores unknown fields for forward-compat.
- [ ] T3.6 — Sphinx authoring doc: tag contract, attributes, properties, events, slots, tokens, a11y, tile-kind authoring guide.
- [ ] T3.7 — Verify no hard-coded colors / hex / absolute font sizes in `styles.css`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (layout round-trip), Property 2 (drag-preserves-validity), Property 3 (stable kind-registry dispatch) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 9 scenario — a project dashboard with 12 mixed-kind tiles loads, edit mode reorders three tiles, save succeeds, conflict path exercised when revision is stale.
- [ ] TT-4 — Extension-point test: register an out-of-tree `AcmeSloBurnRateTile` kind; add-tile picker lists it; inserting creates a working tile; on extension removal the tile enters broken state with a fix affordance.
- [ ] TT-5 — Browser E2E (Playwright-style): keyboard-only user opens the dashboard, activates edit mode, Space-picks up a tile, arrow-moves it, Space-drops, saves, and verifies persistence across reload.
- [ ] TT-6 — Broken-tile isolation test: one tile's metric kind is removed server-side; it renders broken, neighbors keep refreshing.
- [ ] TT-7 — RBAC test: user without `project.dashboard.edit` sees no drag handles; direct call to `addTile` no-ops.

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
