# 6-blast-radius-guards — Tasks

## Milestones

- **M1 — Skeleton:** `guard_attachment` schema + rule registry + `FrozenEnvBlockRule` + `ApplyRequiresInfraOperatorRoleRule` + `allow`/`explain` endpoints.
- **M2 — Core Behavior:** Two-person review ledger + `ProdDestroyRequiresTwoPersonRule` + `OnCallWindowRule` + review REST endpoints + event emission.
- **M3 — Hardening:** Observability, property tests, perf, fail-closed semantics verified, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/orchestration/infra/guards/` package per design.md.
- [ ] T1.2 — Add `0-persistence` migration for `guard_attachment`, `guard_review_request`, `guard_review_entry`.
- [ ] T1.3 — Implement `rule_protocol.py::GuardRuleExtension`.
- [ ] T1.4 — Implement `FrozenEnvBlockRule`, `ApplyRequiresInfraOperatorRoleRule` under `source/site/automojo/extensions/pychestrate/guard_rule/`.
- [ ] T1.5 — Implement `engine.py::BlastRadiusGuards.allow` and `explain` with fail-closed semantics.
- [ ] T1.6 — Register REST `GET /guards/rules`, `PUT /environments/{env_id}/guards/{rule_id}`, `POST :explain`.
- [ ] T1.7 — Implement `rule_registry.py` accessor with atomic swap on `extension.reloaded`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `ProdDestroyRequiresTwoPersonRule` with `requires_two_person_review: True`.
- [ ] T2.2 — Implement `OnCallWindowRule` with declared on-call calendar inputs.
- [ ] T2.3 — Implement `review_ledger.py` and `open_review_request` / `attach_review` flows.
- [ ] T2.4 — Register REST `POST /guards/reviews` and `GET /guards/reviews`.
- [ ] T2.5 — Enforce `reviewer_id != requester_id` and `guards.review:<rule_id>` RBAC.
- [ ] T2.6 — Enforce `review_validity_seconds` expiry with scheduled sweep emitting `entity.infra.guards.review_expired`.
- [ ] T2.7 — Emit `entity.infra.guards.evaluated`, `entity.infra.guards.review_requested`, `entity.infra.guards.review_recorded`, `entity.infra.guards.review_expired`.
- [ ] T2.8 — Implement `set_attachment` RBAC-gated by `guards.admin`.

### M3 — Hardening

- [ ] T3.1 — Emit Prometheus metrics and OTel spans per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: `allow` p99 < 20 ms (10-rule); `explain` p99 < 40 ms; `attach_review` p99 < 120 ms. Fail CI on regression.
- [ ] T3.3 — Implement `actor_role_set_digest` verification against captured trigger-time set.
- [ ] T3.4 — Rate-limit `:explain` per project (default 60/min).
- [ ] T3.5 — Sphinx docs for REST, internal API, rule authoring.
- [ ] T3.6 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.7 — Add chaos test — raise inside a random rule's `evaluate` and assert engine returns `Deny("rule_error")` with the correct rule_id.
- [ ] T3.8 — Ensure registry rebuild exception leaves the engine fail-closed (engine_unavailable deny).

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (purity) and Property 2 (distinct reviewer) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 7 scenario — attempt `destroy` on `prod` env without review → `DenyPendingReview`; a second reviewer approves → next `allow(...)` returns `Allow` and `6-infra-orchestration` dispatches.
- [ ] TT-4 — Extension-point test: test-only `SitePolicyRule` (`rule_id = "site.release_eng_only"`) registered; project attaches it; `allow` denies non-release-engineers.
- [ ] TT-5 — Rule-error test: crash inside a rule's `evaluate`; engine returns `Deny("rule_error")` and emits `pychestrate.infra.guard.rule_error`.
- [ ] TT-6 — Review-expiry test: approve after validity window; next `allow` still denies; new request required.
- [ ] TT-7 — Role-set tamper test: submit `actor_role_set` with roles the user does not hold; engine rejects via digest mismatch.

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
