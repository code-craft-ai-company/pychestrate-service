# 2-retention-policies — Requirements

## Introduction

`2-retention-policies` defines lifecycle rules per **data class** —
`run_result`, `artifact`, `log_stream`, `audit_record`, `metric_sample`, and
extension-registered classes — so that data ages out of hot storage through
configurable stages: **archive**, **tier-move**, or **delete**. Policies may
target all data of a class or a tag-filtered subset (leveraging `2-tagging`).
Actions are executed by extension-supplied `retention_action` factory impls.
Artifact retention specifically cooperates with `0-object-store` tiers
(hot → cold → cold-archive). This feature sits in Layer 2 but **ships in
Phase 10 — Public Surface & Extensibility Completion**, because the earlier
phases don't yet accumulate the volume of data that makes lifecycle
management urgent.

## Requirements

### Requirement 1: Policy definition per data class

**User Story:** As a platform admin, I want to define a retention policy
(name, data class, selector, action chain, trigger) scoped to system or
project, so that stale data is cleaned up automatically without manual
intervention.

**Acceptance Criteria (EARS):**

1. WHEN `POST /api/v1/retention/policies` is received with a valid body
   THEN the system SHALL persist a `RetentionPolicy` row with
   `state = DRAFT` and return `201 Created`.
2. IF `data_class` is not registered THEN the system SHALL respond
   `400 Bad Request` listing known classes.
3. IF any `action_step` names a `retention_action` impl that is not
   registered THEN the system SHALL respond `400 Bad Request`
   identifying the missing action name and the known actions.
4. WHEN `POST /api/v1/retention/policies/{id}/publish` is received
   THEN the system SHALL set `state = PUBLISHED` and schedule the
   policy for evaluation at its configured interval.

### Requirement 2: Dry-run and scheduled evaluation

**User Story:** As an admin I want to dry-run a policy, so that I can
see which rows would be affected before any destructive action runs.

**Acceptance Criteria (EARS):**

1. WHEN `POST /api/v1/retention/policies/{id}/dry-run` is received
   THEN the system SHALL evaluate the selector, return the matching
   entity ids (paginated), and SHALL NOT invoke any `retention_action`
   impl.
2. WHILE a published policy is scheduled for execution THEN the system
   SHALL run it at `interval` cadence, batch matches at
   `batch_size` per invocation, and emit `entity.retention.applied`
   after each successful batch with counts per action step.
3. IF an action step raises a recoverable error for an entity THEN the
   system SHALL mark that entity as `retry` and re-attempt on the
   next invocation up to `max_attempts`; after exhaustion the entity
   is recorded as `failed` with the full error chain.
4. WHERE the data class is `artifact` THEN the system SHALL respect
   `0-object-store` tier transitions and SHALL call the `tier_move`
   action (if present) before `delete`.

### Requirement 3: Archive vs delete vs tier-move semantics

**User Story:** As an archival-policy owner, I want to compose a multi-step
action (tier-move to cold at 30 days, tier-move to cold-archive at 180
days, delete at 730 days), so that I can balance cost and recoverability.

**Acceptance Criteria (EARS):**

1. WHEN a policy's `action_chain` is evaluated for an entity THEN the
   system SHALL dispatch each step in order, stopping on the first
   terminal action (`delete` or `permanent_archive`).
2. IF a `tier_move` step is applied to an `artifact` and the target
   tier equals the current tier THEN the step SHALL be a no-op and
   SHALL record `skipped=tier_already_matching`.
3. IF a `delete` step is applied to an entity whose owning parent has
   `legal_hold = True` THEN the system SHALL skip the entity and
   record `skipped=legal_hold` in the per-entity result.

### Requirement 4: `retention_action` factory protocol

**User Story:** As an extension author, I want to register a
`retention_action` (e.g., `export_to_glacier`, `notify_owner_before_delete`)
so that bespoke lifecycle behavior plugs into the evaluator without
forking Pychestrate.

**Acceptance Criteria (EARS):**

1. WHEN the host loads a class implementing
   `retention_action` with `action_name = X` THEN the system SHALL
   register it under `X`; policies can reference it by name.
2. IF two impls share the same `action_name` THEN the lower
   `PRECEDENCE` wins; dispatch calls the winner only.
3. WHEN an action impl is invoked the system SHALL pass
   `(entity_kind, entity_id, context, dry_run)` and expect a
   `RetentionActionResult`; IF the impl raises `SemanticError` THEN
   the service SHALL let the error bubble (never swallow).

## Property-Based Test Requirements

### Property 1: Retention-action dispatch is idempotent

- **Invariant:** For any policy and any entity, invoking
  `dispatch(policy, entity)` N times produces exactly one terminal
  side-effect (tier-move, archive, or delete) across the sequence —
  repeated calls after the terminal action SHALL be no-ops with
  `skipped=already_terminal`.
- **Generator:** `hypothesis.strategies.builds` producing random
  `RetentionPolicy` action chains and random entity states;
  `hypothesis.stateful` drives repeated `dispatch` invocations.
- **Assertion:** The observed side-effect counter advances by at most
  one per run and stays at one after the terminal step, irrespective
  of how many times dispatch is invoked.
- **Sample size:** 1000 generated cases.

### Property 2: Selector + action composition preserves entity count
invariants

- **Invariant:** For any population of entities and any policy with a
  non-deletion action chain, `evaluate(policy)` leaves the total
  entity count unchanged; for a policy whose chain terminates in
  `delete`, `evaluate(policy)` reduces the entity count by exactly
  the number of entities matching the selector (minus any `legal_hold`
  skips).
- **Generator:** `hypothesis.strategies.lists` of
  `(entity_id, tag_set, legal_hold)` tuples + random policy
  definitions; a simulator applies `evaluate` in-memory.
- **Assertion:** Pre-count − post-count equals
  `len(selector_matches) − len(legal_hold_skips)` for deletion
  policies; equals `0` otherwise.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Policy evaluation processes ≥ 10,000
  candidate rows per minute per policy on the reference deployment;
  scheduler overhead ≤ 2 % of a worker CPU.
- **NFR-2 (Security):** Policy write requires `retention.policy.write`
  at system scope or `project.retention.policy.write` at project scope;
  dry-run requires read-only `retention.policy.read`. Actions run
  under a service principal whose identity is recorded in audit
  entries.
- **NFR-3 (Observability):** Counters
  `pychestrate_retention_evaluated_total{policy_id}`,
  `pychestrate_retention_matched_total{policy_id}`,
  `pychestrate_retention_actioned_total{policy_id,action}`,
  `pychestrate_retention_skipped_total{policy_id,reason}`,
  `pychestrate_retention_failed_total{policy_id,action}`;
  histogram `pychestrate_retention_policy_duration_seconds`;
  log events `retention.policy.published`,
  `retention.policy.evaluated`, `retention.action.applied`,
  `retention.action.skipped`, `retention.action.failed`; trace spans
  `retention.evaluate`, `retention.dispatch_action`.
- **NFR-4 (Reliability):** Scheduler uses leader election so only one
  worker evaluates a given policy per interval. Crash mid-batch must
  not re-delete already-deleted entities (idempotence is load-bearing).

## Out of Scope

- GDPR / privacy-specific data-subject erasure workflows — a separate
  feature reusing this evaluator.
- Cross-tenant retention — every policy is scoped to either system
  or a single project.
- Restoration from archive tiers — provided by `0-object-store` and
  `10-backup-dr`, not here.

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`, `0-object-store`
  (tier semantics), `1-rbac`, `1-audit-log`, `2-projects`, `2-tagging`.
- **Depended on by:** Deployment-hardening concerns across `5-artifact-store`,
  `6-build-artifacts`, `7-metrics-ingest`.
- **Extension points exposed:** `factory: retention_action`;
  `event: entity.retention.applied`.
