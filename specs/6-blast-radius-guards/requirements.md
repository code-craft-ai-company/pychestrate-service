# 6-blast-radius-guards — Requirements

## Introduction

The `6-blast-radius-guards` feature is the rule engine that authorizes
destructive infrastructure actions. It evaluates configured guards
(`GuardRuleExtension` instances) against `(actor_role_set, environment,
action)` tuples and returns an allow/deny decision plus a referenceable
failing rule id on deny. Every apply/destroy in `6-infra-orchestration`
passes through this engine; drift detection never does (read-only).
Ships in **Phase 7** with the rest of the infra slice. This is where
Pychestrate's "two-person integrity", "environment pinning", and
"blast radius" policies land. Authoritative source of truth for rule
definitions is the `guard_rule` table combined with
`GuardRuleExtension`-provided code. Decisions are pure functions over
their inputs.

## Requirements

### Requirement 1: Pure, Deterministic Allow Decisions

**User Story:** As an infra reviewer, I want guard decisions to be
deterministic and explainable, so that I know why a destructive action
was blocked.

**Acceptance Criteria (EARS):**

1. WHEN `guards.allow(project_id, actor_role_set, environment_id, action)` is called THEN the system SHALL iterate applicable rules in declared order AND return `Allow` OR `Deny(rule_id, reason)` WITHOUT mutating any state.
2. WHEN two calls have identical inputs THEN the system SHALL return identical outputs (same decision and same failing rule_id on deny).
3. IF an applicable rule raises a non-`ConfigurationError` exception THEN the system SHALL fail-closed: treat the decision as `Deny(rule_id, "rule_error")` AND log `pychestrate.infra.guard.rule_error`.
4. WHERE a rule declares `requires_two_person_review: True` THEN `Allow` SHALL additionally require `guards.attach_review(...)` with a second principal before the action is dispatched.
5. WHEN `explain(project_id, actor_role_set, environment_id, action)` is called THEN the system SHALL return a structured trace `[{rule_id, verdict, reason}, ...]` covering every evaluated rule.

### Requirement 2: Guard Rule Resource Extension

**User Story:** As an extension author, I want to ship a site-specific
guard (e.g., "prod apply requires a member of the release-engineers
group") so that blast radius policy can be declared rather than coded.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers a `GuardRuleExtension` subclass THEN the system SHALL verify `rule_id: str`, `description: str`, `applies_to(env, action) -> bool`, `evaluate(ctx) -> GuardVerdict` class members AND raise `ConfigurationError` naming missing ones.
2. IF two extensions share `rule_id` THEN the system SHALL raise `ConfigurationError` at load time. `rule_id` is namespaced across all projects (e.g., `core.prod_destroy_requires_soc`, `site.release_eng_only`).
3. WHEN a project scopes a guard via `guards.attach_to_environment(env_id, rule_id, enabled)` THEN the engine SHALL evaluate the rule only when `enabled == True` on that env.
4. WHERE a guard declares `global_default: True` THEN newly created environments SHALL inherit it by default; operators may disable it per env.

### Requirement 3: Two-Person Review Ledger

**User Story:** As a release manager, I want a documented second
signature on destructive `prod` actions so that we meet audit
requirements.

**Acceptance Criteria (EARS):**

1. WHEN a rule with `requires_two_person_review: True` fires THEN `guards.allow(...)` SHALL return `DenyPendingReview` (distinct from `Deny`) and the caller SHALL wait for `attach_review`.
2. WHEN `guards.attach_review(request_id, reviewer_id, decision: "approve"|"reject", rationale)` is called AND `reviewer_id != requester_id` AND RBAC `guards.review:<rule_id>` passes THEN the system SHALL persist a `GuardReview` row AND emit `entity.infra.guards.review_recorded`.
3. WHEN all required approvals have been attached THEN a subsequent `guards.allow(...)` with the same request id SHALL return `Allow` AND reference the review ledger in the audit trail.
4. IF the review window `review_validity_seconds` (default 7200) has elapsed THEN the review SHALL be rejected AND a new request SHALL be required.

## Property-Based Test Requirements

### Property 1: Decisions Are Pure Functions

- **Invariant:** For any `(project_id, actor_role_set, environment_id, action)`, two `allow(...)` calls within the same rule-set version return the same decision and the same failing rule_id (if any).
- **Generator:** `hypothesis.strategies.tuples(uuids(), sets(text(min_size=1, max_size=32), max_size=10), uuids(), sampled_from(["plan","apply","destroy"]))`.
- **Assertion:** `allow(t) == allow(copy(t))`.
- **Sample size:** 1000 generated cases

### Property 2: Two-Person Review Requires Distinct Principals

- **Invariant:** For any request requiring a second review, a review submitted by the same principal as the requester never satisfies the condition; a review submitted by a distinct principal with the required role does.
- **Generator:** `hypothesis.strategies.tuples(uuids(), uuids(), booleans(), booleans())` as `(requester_id, reviewer_id, reviewer_has_role, reviewer_same_as_requester)`.
- **Assertion:** Decision progresses to `Allow` iff `reviewer_has_role == True AND reviewer_same_as_requester == False AND review within validity`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `allow` p99 < 20 ms (10-rule average). `explain` p99 < 40 ms. `attach_review` p99 < 120 ms. Rule-registry cache refresh p99 < 150 ms.
- **NFR-2 (Security):** Rule-edit actions behind `guards.admin`; review attachment behind `guards.review:<rule_id>`. Fail-closed on rule errors. `actor_role_set` must match the role set captured by `6-infra-orchestration` at trigger time — the engine rejects tampered role sets by comparing `actor_role_set_digest` against the captured value.
- **NFR-3 (Observability):** Metrics `pychestrate_infra_guards_evaluations_total{project,env,action,decision}` (counter), `pychestrate_infra_guards_denies_total{project,rule_id}` (counter), `pychestrate_infra_guards_review_requests_total{project,rule_id,outcome}` (counter), `pychestrate_infra_guards_rule_errors_total{project,rule_id}` (counter). Log events `pychestrate.infra.guard.decided`, `pychestrate.infra.guard.review_requested`, `pychestrate.infra.guard.review_recorded`, `pychestrate.infra.guard.rule_error`. Trace spans `pychestrate.infra.guard.allow`, `pychestrate.infra.guard.explain`, `pychestrate.infra.guard.attach_review`.
- **NFR-4 (Reliability):** Guard engine failure (e.g., registry cache rebuild exception) SHALL NOT admit actions — fail-closed. Rule loads happen atomically (swap of a precomputed rule pack); partial-load states are never observed.

## Out of Scope

- Dispatching infra jobs (see `6-infra-orchestration`).
- RBAC itself (see `1-rbac`) — this feature consumes RBAC, does not define it.
- Environment declaration (see `6-environment-registry`).
- Audit log writing (see `1-audit-log`) — this feature emits events; the audit subscriber records them.

## Dependencies

- **Depends on:** `6-environment-registry`, `1-rbac`, `1-audit-log`, `0-persistence`, `0-message-bus`, `E-extension-host`.
- **Depended on by:** `6-infra-orchestration`, `7-orchestration-metrics`, `9-admin-ui`.
- **Extension points exposed:** `resource: GuardRuleExtension` — site-specific rules; in-tree rules `core.prod_destroy_requires_two_person`, `core.frozen_env_block`, `core.apply_requires_infra_operator_role`, plus custom.
