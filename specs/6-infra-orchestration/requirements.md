# 6-infra-orchestration — Requirements

## Introduction

The `6-infra-orchestration` feature dispatches infrastructure jobs —
Terraform, Pulumi, Ansible, and custom tools — onto pod client agents
via Layer 5. It tracks `InfraRun` entities, plan/apply phases,
generated plan summaries, and the environment context the run targets.
It must integrate with `6-blast-radius-guards` so that every
destructive action passes a role + env check before dispatch, and with
`6-environment-registry` so that runs declare a target environment
whose current version is updated on apply. Ships in **Phase 7** with
`6-environment-registry`, `6-drift-detection`, and
`6-blast-radius-guards`. Infra jobs dispatch through the existing Layer
5 plane — no new dispatcher per tool.

## Requirements

### Requirement 1: Dispatch Infra Jobs With Plan/Apply Phases

**User Story:** As an infra engineer, I want `plan` and `apply` as
first-class phases so that the plan can be reviewed before applying.

**Acceptance Criteria (EARS):**

1. WHEN `infra_orchestrator.trigger_run(project_id, actor_id, tool_driver, environment_id, action: "plan"|"apply"|"destroy", inputs, trigger_cause)` is called AND RBAC `infra.run.trigger:<action>` passes THEN the system SHALL persist an `InfraRun` AND dispatch via Layer 5.
2. WHEN `action == "apply"` or `action == "destroy"` THEN the system SHALL consult `6-blast-radius-guards.allow(...)` BEFORE dispatch AND SHALL raise `GuardDeniedError` listing the failing guard rule when denied.
3. WHERE `action == "plan"` the system SHALL dispatch without guard evaluation but SHALL persist the plan summary returned by `5-result-ingest-watcher` in `InfraRun.plan_summary_ref`.
4. WHEN a planned run is later promoted with `infra_orchestrator.apply_planned(plan_run_id)` AND the plan is still within `plan_validity_seconds` (default 900) THEN the system SHALL dispatch an `apply` using the stored plan reference AND SHALL gate via guards.
5. WHEN a run transitions to terminal THEN the system SHALL emit `entity.infra.run_completed` with `{action, environment_id, outcome, plan_diff_digest}`.

### Requirement 2: Infra Tool Driver Factory Protocol

**User Story:** As an extension author, I want to plug in a driver for
our internal infra tool, so that Pychestrate can dispatch our specific
invocation pattern.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers an `InfraToolDriverProtocol` implementation THEN the system SHALL verify `driver_name`, `build_job_envelope`, `validate_inputs`, `parse_plan_summary`, `compute_plan_diff_digest`, `capability_requirements` classmethods AND raise `ConfigurationError` naming missing members.
2. IF two drivers share `driver_name` and `PRECEDENCE` THEN the system SHALL raise `ConfigurationError` at load time.
3. WHEN `trigger_run` references a driver not registered THEN the system SHALL raise `SemanticError`.
4. WHERE the driver declares `supports_plan_replay: True` THEN the system SHALL allow `apply_planned` to submit the plan file for apply; WHERE it declares `False` `apply_planned` SHALL raise `UnsupportedOperationError`.

### Requirement 3: Environment Context On Every Run

**User Story:** As a reviewer, I want every infra run to name its
target environment, so that I can tell which environment is changing.

**Acceptance Criteria (EARS):**

1. WHEN `trigger_run` is called THEN the system SHALL require a valid `environment_id` registered in `6-environment-registry` AND SHALL raise `SemanticError` when it is not present.
2. WHEN `action == "apply"` succeeds terminally THEN the system SHALL call `6-environment-registry.record_apply(environment_id, run_id, output_digest_sha256)` to update current version state.
3. WHERE an environment is marked `frozen: True` THEN any `apply` or `destroy` SHALL be denied with `FrozenEnvironmentError` before dispatch.

## Property-Based Test Requirements

### Property 1: Plan/Apply Linkage Is Immutable

- **Invariant:** For any plan run `P` with stored plan reference `r`, `apply_planned(P.run_id)` dispatches an `apply` whose envelope carries exactly `r` — no other plan bytes, no rewriting, across the validity window.
- **Generator:** `hypothesis.strategies.binary(min_size=1, max_size=65536)` for plan bytes; `hypothesis.strategies.integers(min_value=0, max_value=3600)` for elapsed seconds.
- **Assertion:** If `elapsed <= plan_validity_seconds`, envelope's plan-ref equals `r`; else `PlanExpiredError` is raised.
- **Sample size:** 1000 generated cases

### Property 2: Guard Decisions Are Pure

- **Invariant:** For any `(actor_role_set, environment_id, action)` triple, the guard `allow` function returns the same decision (and the same failing rule id, if any) across invocations.
- **Generator:** `hypothesis.strategies.tuples(sets(text(min_size=1, max_size=32)), uuids(), sampled_from(["plan","apply","destroy"]))`.
- **Assertion:** `allow(inputs) == allow(copy(inputs))`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `trigger_run` p99 < 200 ms excluding guard evaluation; guard evaluation p99 < 40 ms. `apply_planned` p99 < 250 ms including plan validity check. Plan diff digest compute p99 < 100 ms for 2 MiB plans.
- **NFR-2 (Security):** `infra.run.trigger:plan|apply|destroy` per action; all destructive dispatches pass through `6-blast-radius-guards` with `actor_role_set` captured at trigger time and re-validated on promote. Plan bytes stored encrypted-at-rest via the object-store driver. Audit entries for every trigger/promote/cancel.
- **NFR-3 (Observability):** Metrics `pychestrate_infra_runs_total{project,driver,action,final_state}` (counter), `pychestrate_infra_run_duration_seconds{project,driver,action}` (histogram), `pychestrate_infra_guard_denies_total{project,rule_id}` (counter), `pychestrate_infra_plan_apply_promotions_total{project,outcome}` (counter). Log events `pychestrate.infra.run.triggered`, `pychestrate.infra.run.completed`, `pychestrate.infra.guard.denied`, `pychestrate.infra.plan.promoted`, `pychestrate.infra.frozen.rejected`. Trace spans `pychestrate.infra.trigger`, `pychestrate.infra.guard_check`, `pychestrate.infra.apply_planned`.
- **NFR-4 (Reliability):** Layer 5 events delivered out-of-order SHALL be buffered and reapplied. A guard-registry reload SHALL NOT cause an in-flight trigger to be evaluated with a partially loaded rule set — atomic swap.

## Out of Scope

- Environment lifecycle (see `6-environment-registry`).
- Drift detection (see `6-drift-detection`).
- Guard rule definition and admin (see `6-blast-radius-guards`).

## Dependencies

- **Depends on:** `5-job-dispatch`, `5-job-envelope`, `5-run-state-machine`, `5-result-ingest-watcher`, `5-artifact-store`, `6-environment-registry`, `6-blast-radius-guards`, `3-client-registry`, `0-persistence`, `0-message-bus`, `1-rbac`, `1-audit-log`, `E-extension-host`.
- **Depended on by:** `6-pipeline-definition` (infra step kind), `6-drift-detection`, `7-orchestration-metrics`.
- **Extension points exposed:** `factory: infra_tool_driver` — Terraform, Pulumi, Ansible, custom.
