# 1-feature-flags — Tasks

## Milestones

- **M1 — Skeleton:** Flag tables live, in-tree local backend,
  `evaluate_flag` hot path for boolean and percentage flags, lifecycle
  create/read, audit emission.
- **M2 — Core Behavior:** Enum + string flags, update/retire
  lifecycle with version history, `feature_flag_backend` factory
  protocol with `LocalDatabaseFeatureFlagBackend` reference, REST
  surface, cache with staleness window, backend health checks.
- **M3 — Hardening:** Last-good-cache fallback, metrics / logs / traces,
  perf baseline, Sphinx docs, out-of-tree backend extension exercised.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Land the `feature_flags` and `feature_flag_versions`
      tables via `EntityMigrationExtension`.
- [ ] T1.2 — Declare `FeatureFlagBackendProtocol`
      `FactoryProtocolBase` with `protocol_schema_version = 1`.
- [ ] T1.3 — Ship `LocalDatabaseFeatureFlagBackend` at
      `PRECEDENCE = 1000` claiming `flag_key_pattern = "*"`.
- [ ] T1.4 — Implement `rules.compute_bucket` using
      `sha256(flag_key || bucketing_key)` and
      `rules.evaluate_rollout` for PERCENTAGE flags.
- [ ] T1.5 — Implement `flag_evaluator.evaluate_flag` +
      `evaluate_boolean` with cache-miss → backend path and
      `SemanticError` on missing `bucketing_key`.
- [ ] T1.6 — Implement `flag_service.create_flag` with outbox
      publication of `entity.flag.created`.

### M2 — Core Behavior

- [ ] T2.1 — Implement ENUM and STRING kinds with rule validation
      (reject `flag_kind` changes as `SemanticError`).
- [ ] T2.2 — Implement `flag_service.update_flag_rules` that bumps
      `current_version` and inserts a new `feature_flag_versions`
      row.
- [ ] T2.3 — Implement `flag_service.retire_flag` + grace scheduler
      that emits `entity.flag.removed` at grace end.
- [ ] T2.4 — Implement `cache.staleness_window_cache` with
      configurable TTL (default 60 s) and bus-driven invalidation
      on `entity.flag.updated` / `entity.flag.retired`.
- [ ] T2.5 — Implement `backend_router.resolve_backend` with pattern
      matching + precedence tie-break and
      `flags.backend.override` log event.
- [ ] T2.6 — Implement backend health prober and
      `entity.flag.backend.unhealthy` / `healthy` emissions.
- [ ] T2.7 — Wire REST controllers (`/api/v1/flags` CRUD +
      `/evaluate`).

### M3 — Hardening

- [ ] T3.1 — Implement last-good-cache fallback when backend returns
      transient errors; emit
      `pychestrate_flags_cache_stale_served_total`.
- [ ] T3.2 — Emit every metric listed in requirements.md NFR-3.
- [ ] T3.3 — Emit every log event in NFR-3 and add trace spans
      `flags.evaluate`, `flags.backend.call`,
      `flags.cache.resolve`, `flags.rules.match`.
- [ ] T3.4 — Benchmark warm-cache `evaluate_flag` and hold < 1 ms
      p95; cold local evaluation < 5 ms p95.
- [ ] T3.5 — Generate Sphinx docs for public and internal API and
      the `feature_flag_backend` contract.
- [ ] T3.6 — Ship an out-of-tree `pychestrate-ext-flags-fixture`
      sample backend at `PRECEDENCE = 500` claiming
      `flag_key_pattern = "experiment.*"`; exercised in the
      integration suite.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS acceptance criterion in
      Requirements 1–3.
- [ ] TT-2 — Hypothesis-based property tests: Property 1 (same
      inputs → same result within staleness window), Property 2
      (percentage rollout monotone step), Property 3 (default
      fallback on unknown key), 1000 cases each.
- [ ] TT-3 — Integration test: create a boolean flag, flip it,
      update its rollout percentage, retire it; assert
      `1-authentication`'s `auth.local_fallback_enabled` consumer
      sees the change within the staleness window and that
      `1-audit-log` records each lifecycle event exactly once.
- [ ] TT-4 — Extension-point test: out-of-tree backend claims
      `experiment.*`; flags under that pattern route to the
      extension while unrelated flags continue to use the default
      local backend.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface has at least one in-tree reference
      implementation (`LocalDatabaseFeatureFlagBackend`) and one
      test-only override using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 1 —
      Identity & Projects in specs/implementation-plan.md
