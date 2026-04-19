# 6-drift-detection — Requirements

## Introduction

The `6-drift-detection` feature runs scheduled declared-vs-actual
checks per environment, per infra tool, producing a stable `DriftReport`
that records resources which have moved out of sync with the declared
configuration. It ships in **Phase 7** with `6-infra-orchestration`,
`6-environment-registry`, and `6-blast-radius-guards`. Drift checks run
on pod client agents via Layer 5 — no new dispatch pipeline — using
read-only driver paths (Terraform `plan -refresh-only`, Pulumi
`preview`, Ansible check mode). Checkers are pluggable via
`drift_checker`. Authoritative source of truth for declared state is
the infra tool's backend (e.g., Terraform state); this feature
persists the *diff* and a digest.

## Requirements

### Requirement 1: Scheduled Drift Checks Per Environment

**User Story:** As an operator, I want each environment drift-checked
on a cadence so that configuration drift is surfaced before release.

**Acceptance Criteria (EARS):**

1. WHEN a project declares a `drift_schedule` (cron expression) on an environment via `drift.set_schedule(env_id, cron)` THEN the system SHALL dispatch a drift-check job at every cron tick.
2. WHEN the cron fires THEN the system SHALL build a Layer 5 envelope for the environment's configured `drift_checker` AND dispatch it through `5-job-dispatch` — no new dispatcher.
3. IF the environment is `frozen` OR `archived` THEN scheduled drift checks SHALL STILL run (operators need drift visibility when frozen); however no auto-remediation apply SHALL be triggered.
4. WHERE the pod client does not have the required drift capability THEN the system SHALL log at WARNING `pychestrate.infra.drift.capability_mismatch` and skip that tick without raising.
5. WHEN a drift run completes THEN the system SHALL persist a `DriftReport` with `{drift_count, added, changed, destroyed, diff_digest_sha256, ran_at, report_blob_key}`.

### Requirement 2: Drift Checker Factory Protocol

**User Story:** As an extension author, I want a factory protocol for
drift checkers so that a new infra tool's read-only checker can plug in.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers a `DriftCheckerProtocol` implementation THEN the system SHALL verify `checker_name`, `build_job_envelope`, `parse_report`, `compute_diff_digest`, `capability_requirements` classmethods AND raise `ConfigurationError` naming missing members.
2. IF two checkers share `checker_name` and `PRECEDENCE` THEN the system SHALL raise `ConfigurationError` at load time.
3. WHEN a project configures `drift_checker_name = "<name>"` but the name is not registered THEN the system SHALL raise `SemanticError`.
4. WHERE a checker declares `report_format_tag` THEN the system SHALL register the matching `result_tree_parser` under `5-result-ingest-watcher` for ingest.

### Requirement 3: Deterministic Diff Digests

**User Story:** As a consumer, I want the same underlying drift to
produce the same digest across runs, so that unchanged infra produces
identical reports and alert-noise stays low.

**Acceptance Criteria (EARS):**

1. WHEN two drift checks run back-to-back against an unchanged environment THEN the system SHALL produce identical `diff_digest_sha256` values.
2. WHEN drift changes between two consecutive runs THEN the system SHALL emit `entity.env.drift_detected` on the bus with `{environment_id, previous_digest, current_digest, drift_count}`.
3. IF an operator invokes `drift.run_now(env_id, reason)` outside of the schedule AND RBAC `drift.run` passes THEN the system SHALL dispatch an ad-hoc check AND emit `entity.env.drift.manual_triggered`.

## Property-Based Test Requirements

### Property 1: Repeated Runs Produce Identical Diffs

- **Invariant:** For any fixed declared state `D` and observed state `A`, any two `parse_report` invocations on the canonical report bytes produce the same `diff_digest_sha256`.
- **Generator:** `hypothesis.strategies.lists(tuples(text(min_size=1, max_size=64), sampled_from(["add","change","destroy","no_op"]), dictionaries(text(), text(), max_size=10)), min_size=0, max_size=200)` as declared resource ops; mutate with identity mappings to prove digest invariance.
- **Assertion:** `compute_diff_digest(report_bytes) == compute_diff_digest(report_bytes)` and permutations of resource order do not change the digest.
- **Sample size:** 1000 generated cases

### Property 2: Schedule Tick → Dispatch Exactly Once

- **Invariant:** For any cron expression and any time window, the scheduler dispatches exactly one drift check per scheduled tick; service restart within the window SHALL NOT produce duplicates.
- **Generator:** `hypothesis.strategies.sampled_from([...valid cron exprs...])` plus restart events inserted at random times.
- **Assertion:** `count(dispatches_for_env(env_id, window)) == count(ticks_in_window(cron, window))`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Scheduler fire-to-dispatch latency p99 < 500 ms. `DriftReport` persist-on-ingest p99 < 300 ms for 5 MiB reports. `diff_digest_sha256` compute p99 < 80 ms per report.
- **NFR-2 (Security):** Drift jobs use read-only credentials scoped per environment via `1-secrets-vault`. `drift.set_schedule`, `drift.run_now` gated by `drift.admin`. No destructive action may be chained from drift detection without an explicit operator apply through `6-infra-orchestration` (gated by guards).
- **NFR-3 (Observability):** Metrics `pychestrate_infra_drift_runs_total{project,env,checker,outcome}` (counter), `pychestrate_infra_drift_run_duration_seconds{project,checker}` (histogram), `pychestrate_infra_drift_changes_total{project,env,kind}` (counter by `add|change|destroy`), `pychestrate_infra_drift_skipped_total{project,env,reason}` (counter). Log events `pychestrate.infra.drift.scheduled`, `pychestrate.infra.drift.dispatched`, `pychestrate.infra.drift.completed`, `pychestrate.infra.drift.detected`, `pychestrate.infra.drift.manual_triggered`, `pychestrate.infra.drift.capability_mismatch`. Trace spans `pychestrate.infra.drift.schedule_tick`, `pychestrate.infra.drift.dispatch`, `pychestrate.infra.drift.persist_report`.
- **NFR-4 (Reliability):** Missed ticks caused by outage SHALL be replayed up to `max_missed_tick_catchup` (default 1 per env) once the service recovers. Reports whose ingest fails SHALL be marked `ingest_failed` and retried with bounded backoff.

## Out of Scope

- Auto-remediation via apply (operator-gated only; see `6-infra-orchestration`).
- Per-resource ownership or tag-based filtering of drift — can be layered later.
- Notification routing (delegated to `2-notification-hub` via subscribers).

## Dependencies

- **Depends on:** `6-environment-registry`, `6-infra-orchestration`, `5-job-dispatch`, `5-result-ingest-watcher`, `0-persistence`, `0-message-bus`, `1-rbac`, `1-secrets-vault`, `1-audit-log`, `E-extension-host`, `2-notification-hub`.
- **Depended on by:** `7-orchestration-metrics`, `9-admin-ui`.
- **Extension points exposed:** `factory: drift_checker` — Terraform, Pulumi, Ansible, custom.
