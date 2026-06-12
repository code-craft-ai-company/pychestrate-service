# 4-conflict-deconfliction — Tasks

## Milestones

- **M1 — Skeleton:** Package scaffold, `evaluate` entry point with
  `ExclusiveModeRule` and `SharedModeRule` hard-wired, read-only
  repository handle raising on writes.
- **M2 — Core Behavior:** `ConflictRuleExtension` discovery via
  `E-resource-extensions`, the five in-tree rules, subnet GiST index,
  license-seat rule, pod-member cross-lock rule, rebuild on
  `extension.reloaded`.
- **M3 — Hardening:** Perf targets, metrics/logs/traces, startup
  configuration checks, extension tests, property tests.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/ccai/pychestrate/webservice/resources/conflict/` per design.md.
- [ ] T1.2 — Implement `models.py` dataclasses: `RuleDecision`, `ConflictEvaluation`, `ActiveReservationSnapshot`.
- [ ] T1.3 — Implement `repository_views.py::ReadOnlyRepositoryHandle` wrapping `0-persistence`; every write method raises `SemanticError`.
- [ ] T1.4 — Implement `rule_registry.py` with per-kind lookup and wildcard routing.
- [ ] T1.5 — Implement `evaluator.py::evaluate` with priority-sorted iteration and single-boundary exception reclassification to violation.
- [ ] T1.6 — Ship `ExclusiveModeRule` and `SharedModeRule` as in-tree `ConflictRuleExtension` subclasses (hard-registered initially).
- [ ] T1.7 — Integrate with `4-checkout-checkin.reserve` flow — call `evaluate` after validator pipeline and before DB commit.

### M2 — Core Behavior

- [ ] T2.1 — Alembic migration `0050_network_generated_columns` adding `network cidr` generated column on `core.resources` (filter by kind='ip_subnet') and `address inet` (filter by kind='ip_address') and the GiST index `idx_resources_subnet_gist`.
- [ ] T2.2 — Add view `core.active_reservations_with_network` joining granted reservations with generated network columns.
- [ ] T2.3 — Implement `SubnetOverlapRule` using `&&` against the view; verify GiST usage via `EXPLAIN`.
- [ ] T2.4 — Implement `LicenseSeatCountRule` counting granted reservations against the same `license.resource_id`; violated when count ≥ `attrs->seat_count`.
- [ ] T2.5 — Implement `PodMemberCrossLockRule` that re-asserts `pod_locked_by IS NULL` for non-pod targets.
- [ ] T2.6 — Implement `supports_shared=false` downgrade in `SharedModeRule`; emit `pychestrate.resource.conflict.shared_downgraded`.
- [ ] T2.7 — Wire `ConflictRuleExtension` discovery via `E-resource-extensions`; rebuild registry on `extension.reloaded`.
- [ ] T2.8 — Startup check: refuse to start with zero rules of `applies_to_kinds=("*",)` containing an exclusivity rule — raise `ConfigurationError`.
- [ ] T2.9 — Duplicate `rule_name` detection at registry build; `ConfigurationError` with multiline message via `os.linesep.join`.

### M3 — Hardening

- [ ] T3.1 — Add every metric from design.md Observability.
- [ ] T3.2 — Benchmark `evaluate` p99 < 5 ms at 100 active reservations / 20 rules; subnet rule p99 < 3 ms at 500 active subnets; fail CI on regression (NFR-1).
- [ ] T3.3 — Implement per-rule 200 ms soft timeout; treat timeout as a violation and emit `pychestrate.resource.conflict.rule_timeout`.
- [ ] T3.4 — Trace span `pychestrate.resource.conflict.evaluate` with a child `.rule` per rule.
- [ ] T3.5 — Ship an out-of-tree `pychestrate-ext-powercircuit` demonstrating a site-specific `PowerCircuitRule`; integration test it blocks incompatible pairs.
- [ ] T3.6 — Sphinx docs for `ConflictRuleExtension` and each in-tree rule.
- [ ] T3.7 — Dashboard panel on `7-resource-metrics` showing violations per rule, error rate, p95 evaluation time.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Hypothesis tests implementing Property 1 (exclusive never coexists under concurrency) and Property 2 (subnet overlap symmetric and transitive-safe), 1000 cases each.
- [ ] TT-3 — Integration test: register two overlapping subnets; attempt both reservations concurrently; assert exactly one is granted, the other returns `409` with a body naming the overlapping CIDR.
- [ ] TT-4 — Extension-point test: `AlwaysViolateRule` at priority 0 (test-only) short-circuits every evaluation with a fixed reason.
- [ ] TT-5 — Crash-containment test: a `BuggyRule` whose `check` raises `ValueError` is treated as a violation; `pychestrate_resource_conflict_rule_error_total{rule_name="BuggyRule"}` increments; no uncaught exception reaches the checkout response.
- [ ] TT-6 — Read-only handle test: a rule that attempts `db.save(...)` raises `SemanticError`, which bubbles to test assertion (no wrapping).

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
