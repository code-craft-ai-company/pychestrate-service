# E-extension-config — Tasks

## Milestones

- **M1 — Skeleton:** `ExtensionConfigScope` class exists with
  `get_variable`, `list_variable_names`; no capability check yet,
  scope created at `on_load`.
- **M2 — Core Behavior:** `get_secret` with capability check,
  `dispatch_config_change` proposal path, cache with invalidation,
  scoped event emission.
- **M3 — Hardening:** Metrics/logs/traces, rate limiting, audit log
  integration, Sphinx docs, stress tests.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create the package tree under
  `source/site/ccai/pychestrate/webservice/extension/config/`.
- [ ] T1.2 — Implement `ExtensionConfigScope` with `get_variable`
  and `list_variable_names`.
- [ ] T1.3 — Implement `build_scope_for_extension` factory.
- [ ] T1.4 — Wire scope construction into
  `LifecycleCoordinator.run_on_load` so scopes are passed to hooks.

### M2 — Core Behavior

- [ ] T2.1 — Implement `get_secret` with capability pre-check against
  manifest; raise `PermissionError` on missing capability.
- [ ] T2.2 — Implement `_require_scoped_key` validator raising
  `SemanticError` on cross-scope access attempts.
- [ ] T2.3 — Implement `ConfigChangeProposal` and
  `dispatch_config_change`; proposal emitted on bus.
- [ ] T2.4 — Implement per-ext cache with TTL and invalidation on
  `entity.variable.changed` / `entity.secret.rotated`.
- [ ] T2.5 — Subscribe to upstream change events; re-emit as
  `extension.config_changed` / `extension.secret_rotated`.
- [ ] T2.6 — Integrate secret reads with `1-audit-log`
  (actor = `extension:<name>`).

### M3 — Hardening

- [ ] T3.1 — Emit metrics and log events per design.md Observability.
- [ ] T3.2 — Emit trace spans for every scope call.
- [ ] T3.3 — Implement per-ext rate limiter (token bucket, 100 req/s
  default, configurable via `ext.<name>.cache.read_rate_limit`).
- [ ] T3.4 — Generate Sphinx docs for the scope API; wire into
  `E-extension-docs`.
- [ ] T3.5 — Stress test: 100-ext fleet reading 10 variables each
  concurrently; verify P95 latency under NFR-1.
- [ ] T3.6 — Remove all TODO/FIXME; pass lint + type checks.

## Test Tasks

- [ ] TT-1 — Unit tests for each EARS requirement including every
  permission-denied path.
- [ ] TT-2 — Property-based tests for Property 1 (scope isolation),
  2 (capability gating), 3 (read round-trip) at 1000 cases each.
- [ ] TT-3 — Integration test: extension A (with `read:secrets`) and
  extension B (without) both request `ext.<their>.api_key`; A
  succeeds, B raises; audit log shows A's read; B's denial is
  metric-counted.
- [ ] TT-4 — Extension-point test: out-of-tree
  `pychestrate-ext-sample-config` reads two variables and one
  secret; admin-triggered config change propagates and extension
  observes the new value on next read.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] Reference in-tree extension exercises variable + secret reads;
      second test-only extension with different PRECEDENCE overrides
      a scoped behavior.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated for the scope API.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Phase 1 exit criterion in
      specs/implementation-plan.md.
