# E-extension-registry-ui — Tasks

## Milestones

- **M1 — Skeleton:** List + detail routes return composed JSON; two
  WebComponents render the data statically (no stream yet).
- **M2 — Core Behavior:** Live WebSocket stream for row updates;
  filter chips; action buttons wired to existing REST endpoints with
  permission-based hide/disable.
- **M3 — Hardening:** Reliability (WS fallback to polling), metrics/
  logs/traces, third-party panel extension surface, accessibility
  audit.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create the package tree under
  `source/site/ccai/pychestrate/webservice/extension/ui/`.
- [ ] T1.2 — Implement `ExtensionViewComposer` with `build_list` and
  `build_detail`.
- [ ] T1.3 — Add `GET /admin/extensions` and
  `GET /admin/extensions/{name}` REST routes under `extensions.read`.
- [ ] T1.4 — Create the `<pychestrate-extension-list>` and
  `<pychestrate-extension-detail>` WebComponents with static fetch.
- [ ] T1.5 — Register the two pages in `9-admin-ui` navigation.

### M2 — Core Behavior

- [ ] T2.1 — Implement `ExtensionViewStream` WebSocket endpoint at
  `GET /admin/extensions/stream`.
- [ ] T2.2 — Subscribe to the relevant `extension.*` topics and fan
  out row diffs.
- [ ] T2.3 — Wire filter chips (`unhealthy`, `quarantined`,
  `schema_ahead`) with URL-state preservation.
- [ ] T2.4 — Wire action buttons (rescan, grant/revoke, quarantine)
  to existing REST endpoints; hide/disable per permission.
- [ ] T2.5 — Implement the `ExtensionDetailPanelExtension`
  ResourceExtension base in `panels.py`; composer picks up
  contributed panels and renders `<pychestrate-extension-panel>`
  slots.

### M3 — Hardening

- [ ] T3.1 — Implement WS fallback-to-polling after 3 failures.
- [ ] T3.2 — Emit metrics and log events per design.md Observability.
- [ ] T3.3 — Add OpenTelemetry trace spans around composer and
  stream endpoint calls.
- [ ] T3.4 — Accessibility audit: ARIA roles, keyboard navigation,
  contrast on `9-ui-design-tokens` themes.
- [ ] T3.5 — Sphinx docs for the panel-extension surface; wire into
  `E-extension-docs`.
- [ ] T3.6 — Remove all TODO/FIXME; pass lint + type checks.

## Test Tasks

- [ ] TT-1 — Unit tests for each EARS requirement including the
  permission-based hide/disable path.
- [ ] TT-2 — Property-based tests for Property 1 (filter closure), 2
  (row consistency), 3 (authorization hiding) at 1000 cases each.
- [ ] TT-3 — Integration test: browserless (Playwright)
  verification that grant button for `dispatch:jobs` POSTs and UI
  updates within one stream tick.
- [ ] TT-4 — Extension-point test: out-of-tree
  `pychestrate-ext-sample-ui-panel` contributes an
  `ExtensionDetailPanelExtension`; detail page renders the panel in
  the contributed slot.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] WebComponent extension surface has an in-tree reference panel
      and a test-only override panel with a different PRECEDENCE.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated for the panel extension surface.
- [ ] Code conforms to AGENTS.md coding standards (backend); CSS
      spread across lines per repo convention.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Phase 10 exit criterion in
      specs/implementation-plan.md.
