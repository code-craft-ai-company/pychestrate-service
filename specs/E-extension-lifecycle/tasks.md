# E-extension-lifecycle — Tasks

## Milestones

- **M1 — Skeleton:** `LifecycleCoordinator` exists; `on_load` fires in
  PRECEDENCE order for all factories that declare it; exceptions are
  captured into records.
- **M2 — Core Behavior:** Full phase surface (`on_service_ready`,
  `on_project_loaded`, `on_service_draining`, `on_unload`); per-phase
  timeouts; strict-mode ready gating; health table; quarantine routes.
- **M3 — Hardening:** Metrics/logs/traces, bus-driven phase triggers,
  audit-log integration, idempotent unload, stress tests for timeouts.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create the package tree under
  `source/site/automojo/pychestrate/webservice/extension/lifecycle/`.
- [ ] T1.2 — Implement `ExtensionLifecycleRecord` and
  `ExtensionHealthState` dataclasses.
- [ ] T1.3 — Implement signature-validation helper in
  `hook_signatures.py` that confirms a class's declared hook matches
  the expected contract.
- [ ] T1.4 — Implement `LifecycleCoordinator.run_on_load` walking the
  host's sorted factory chain and resource collections.
- [ ] T1.5 — Wire bootstrap integration so `run_on_load` runs after
  host registration completes.

### M2 — Core Behavior

- [ ] T2.1 — Implement `invoke_hook` with
  `concurrent.futures.ThreadPoolExecutor` timeouts and
  reclassification to `ExtensionHookError`.
- [ ] T2.2 — Implement `run_on_service_ready` with strict-mode
  fail-closed readiness gating via `0-system-health`.
- [ ] T2.3 — Implement `run_on_project_loaded(project=...)` with named
  parameter passing.
- [ ] T2.4 — Implement `run_on_service_draining` and `run_on_unload`;
  descending PRECEDENCE for unload; idempotent on repeat.
- [ ] T2.5 — Implement `ExtensionHealthTable` with quarantine /
  unquarantine semantics.
- [ ] T2.6 — Add `/admin/extensions/{name}/lifecycle`,
  `/admin/extensions/{name}/quarantine`,
  `/admin/extensions/{name}/unquarantine` REST routes with their
  permissions.
- [ ] T2.7 — Subscribe to `entity.project.loaded`,
  `system.drain_started`, `system.shutdown_requested` bus events.

### M3 — Hardening

- [ ] T3.1 — Emit metrics and log events per design.md Observability.
- [ ] T3.2 — Emit bus events
  (`extension.hook_started|completed|call_failed`,
  `extension.quarantined|unquarantined`).
- [ ] T3.3 — Integrate quarantine/unquarantine with `1-audit-log`.
- [ ] T3.4 — Add a stress test harness that injects slow hooks (~2 s)
  into a 50-extension fleet and confirms phase wall-clock stays within
  bounds.
- [ ] T3.5 — Document the hook surface in `E-extension-docs`.
- [ ] T3.6 — Remove all TODO/FIXME; pass lint + type checks.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement.
- [ ] TT-2 — Property-based tests for Property 1 (ordering), 2
  (timeout containment), 3 (unload idempotence) at 1000 cases each.
- [ ] TT-3 — Integration test: a three-extension fleet with one
  slow-load, one fast-load, one fails-on-ready; strict mode blocks
  readiness; permissive mode quarantines the failing one.
- [ ] TT-4 — Extension-point test: out-of-tree
  `pychestrate-ext-sample-lifecycle` implements all five hooks;
  service observes the expected trace across bootstrap, project
  load, drain, shutdown.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] Reference in-tree extension provides a hook in each phase; a
      test-only override with a different `PRECEDENCE` demonstrates
      ordering.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated for the hook surface.
- [ ] Code conforms to AGENTS.md coding standards (no behavior-modifying
      decorators; timeouts are parameters, not decorators).
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Phase 0.5 exit criterion in
      specs/implementation-plan.md.
