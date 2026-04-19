# E-extension-hooks — Tasks

## Milestones

- **M1 — Skeleton:** `@subscribes_to` decorator attaches metadata;
  `SubscriptionRouter` registers/unregisters subscriptions; delivery
  routes to handlers with no timeout yet.
- **M2 — Core Behavior:** Timeout + retry via `HookAspects`; isolation
  across subscribers (concurrent executor); quarantine on consecutive
  failures; admin REST surface.
- **M3 — Hardening:** Full metrics/logs/traces, sandbox capability
  pre-check hook, Sphinx docs, stress tests for dispatch throughput.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create the package tree under
  `source/site/automojo/pychestrate/webservice/extension/hooks/`.
- [ ] T1.2 — Implement `subscribes_to` decorator in `decorator.py`
  attaching `_subscribes_to_metadata` to the method.
- [ ] T1.3 — Implement `HookAspects` dataclass with the fields listed
  in design.md.
- [ ] T1.4 — Implement `SubscriptionRouter.register_for_class` and
  `unregister_for_class` walking the class for decorated methods.
- [ ] T1.5 — Wire registration into
  `LifecycleCoordinator.run_on_load` post-success and
  `run_on_unload` before teardown.

### M2 — Core Behavior

- [ ] T2.1 — Implement `_deliver` with
  `concurrent.futures.ThreadPoolExecutor` timeout enforcement.
- [ ] T2.2 — Implement retry loop driven by `HookAspects.retry_max`
  and `retry_backoff_seconds`.
- [ ] T2.3 — Implement per-subscriber consecutive-failure tracking;
  on exceed, update `ExtensionHealthTable` to `quarantined` and emit
  `extension.quarantined`.
- [ ] T2.4 — Ensure concurrent dispatch across subscribers of the
  same topic; one failure does not block others.
- [ ] T2.5 — Implement pattern-subscription support
  (`entity.job.*`) via `bus.subscribe_pattern`.
- [ ] T2.6 — Add `GET /admin/extensions/{name}/subscriptions` REST
  route gated by `extensions.read`.

### M3 — Hardening

- [ ] T3.1 — Emit metrics, log events, and trace spans per design.md.
- [ ] T3.2 — Add the `extension_sandbox.authorize` pass-through hook
  to be populated by Phase 8; emit
  `extension.subscription_rejected` when a capability is missing
  (even in pass-through, it logs the intent).
- [ ] T3.3 — Integration with `E-extension-docs` to enumerate topics
  any loaded extension subscribes to.
- [ ] T3.4 — Stress test: 100 subscribers, 10k events/sec, P95 ≤ 3 ms
  overhead.
- [ ] T3.5 — Remove all TODO/FIXME; pass lint + type checks.

## Test Tasks

- [ ] TT-1 — Unit tests for each EARS requirement, including
  orphan-decorator detection.
- [ ] TT-2 — Property-based tests for Property 1 (load/unload
  balance), 2 (subscriber isolation), 3 (timeout containment) at
  1000 cases each.
- [ ] TT-3 — Integration test: two subscribers on
  `entity.job.completed`, one intentionally times out; other still
  receives; timeout subscriber quarantines after configured failures.
- [ ] TT-4 — Extension-point test: out-of-tree
  `pychestrate-ext-sample-hook` subscribes to
  `entity.project.created`, receives an emitted event, and appears in
  the admin subscriptions listing.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] Reference in-tree extension ships a subscriber for
      `entity.run.completed`; a test-only override with a different
      PRECEDENCE demonstrates both are called.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated for `@subscribes_to` and `HookAspects`.
- [ ] Code conforms to AGENTS.md coding standards — the single
      decorator present is metadata-attachment only (registering with
      a mapping system).
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Phase 1 exit criterion in
      specs/implementation-plan.md.
