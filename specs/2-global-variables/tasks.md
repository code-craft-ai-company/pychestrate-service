# 2-global-variables — Tasks

## Milestones

- **M1 — Skeleton:** `VariableBinding` table lands, set/unset at the SYSTEM
  and PROJECT scopes work, `DatabaseVariableResolver` is the only resolver.
- **M2 — Core Behavior:** Full scope chain (job → pipeline → project →
  system) resolution, inheritance trace endpoint, secret-ref
  dereferencer chain, extension-based `variable_resolver` chain.
- **M3 — Hardening:** Cache + invalidation, resolver failover semantics,
  rate limits, observability, and the Phase-1 end-to-end integration
  scenario.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — `0-persistence` migration for `variable_bindings` table
      with `UNIQUE (scope, scope_id, name)` and the null-safe index.
- [ ] T1.2 — Implement `entities.py` (`VariableBinding`, enums,
      `EffectiveValue`, `TraceEntry`).
- [ ] T1.3 — Implement `repository.py` (`upsert_binding`,
      `delete_binding`, `read_binding`, `list_bindings`,
      `list_names_in_context`).
- [ ] T1.4 — Implement `service.set_variable` and
      `service.unset_variable` with outbox writes for
      `entity.variable.set|unset`.
- [ ] T1.5 — Implement the REST endpoints
      `PUT/DELETE /api/v1/variables/{scope}/{scope_id}/{name}` and
      `GET /api/v1/variables/{scope}/{scope_id}`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `factories.VariableResolverProtocol` and ship
      `DatabaseVariableResolver` with `PRECEDENCE=1000`.
- [ ] T2.2 — Implement `resolver_chain` that walks registered
      `variable_resolver` impls in `PRECEDENCE` order and fails over
      on recoverable errors.
- [ ] T2.3 — Implement `service.resolve_effective` walking
      `JOB → PIPELINE → PROJECT → SYSTEM` using the resolver chain.
- [ ] T2.4 — Implement `factories.SecretRefDereferencerProtocol` and
      ship `VaultSecretRefDereferencer` against `1-secrets-vault`.
- [ ] T2.5 — Implement `service.collect_trace` returning the full
      four-scope trace per variable name, with secret-value
      redaction.
- [ ] T2.6 — Implement `GET /api/v1/variables/effective` and
      `GET /api/v1/variables/trace` REST endpoints including
      `include_trace` query param.
- [ ] T2.7 — Subscribe to `entity.project.deleted` and purge
      project-scoped bindings, emitting `entity.variable.unset` per
      purged row.

### M3 — Hardening

- [ ] T3.1 — Implement TTL cache in `cache.py` with
      `entity.variable.set|unset` invalidation subscriber.
- [ ] T3.2 — Implement `If-Match` / `ETag` handling for set/unset.
- [ ] T3.3 — Emit all metrics, logs, and trace spans listed in
      design.md Observability.
- [ ] T3.4 — Add rate-limiter rules (500/min resolve, 60/min set).
- [ ] T3.5 — Audit-log wiring for dereference calls (actor +
      secret id, never plaintext).
- [ ] T3.6 — Resolver failover test harness: register a faulty
      extension with lower `PRECEDENCE` and verify the chain falls
      through and logs the failover, returning `503` only when all
      resolvers fail.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in
      requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests for Property 1 (determinism) and
      Property 2 (scope-depth wins) implemented with `hypothesis`.
- [ ] TT-3 — Integration test: set a variable at system, project,
      pipeline, and job scopes; `effective` returns the deepest one;
      `trace` correctly enumerates all four with the right `present`
      flags and the UI-expected shape.
- [ ] TT-4 — Extension-point test: out-of-tree
      `ConsulVariableResolver` registers at `PRECEDENCE=500`, wins
      over `DatabaseVariableResolver` for SYSTEM scope, and falls
      through on I/O error.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (`variable_resolver`, `secret_ref_dereferencer`)
      has in-tree reference implementations and one test-only override
      per protocol using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 1 in
      specs/implementation-plan.md
