# 6-test-orchestration — Requirements

## Introduction

The `6-test-orchestration` feature is Pychestrate's user-visible entry point for
dispatching test jobs onto pod client agents and tracking their runs through
the `5-job-*` plane. It lives in **Layer 6** of the architecture (see
`specs/implementation-plan.md`) and ships in **Phase 3** as part of the
minimal end-to-end slice: a user triggers a test job, Layer 5 dispatches it
over the client-agent protocol, the client executes a testbase runner, and
progress + the final result tree flow back through `5-progress-ingest` and
`5-result-ingest-watcher`. This feature owns *test-specific* run records,
trigger semantics, per-run config resolution, and the `test_runner_kind`
factory protocol. It explicitly reuses `5-job-dispatch` — no new dispatch
plumbing is introduced. It sits between `6-test-catalog` (the suite-definition
surface) and `6-live-run-view` (the client-facing progress view).

## Requirements

### Requirement 1: Test Run Lifecycle Owned By This Feature

**User Story:** As a test operator, I want every test run to appear as a
first-class entity with a stable id, a runner kind, a target pod, and a
resolved config, so that I can audit what was dispatched and why.

**Acceptance Criteria (EARS):**

1. WHEN a caller invokes `test_orchestrator.trigger_run(project_id, catalog_entry_id, target_pod_id, runner_kind, inputs, aspects)` THEN the system SHALL persist a `TestRun` entity with state `pending`, a fresh `run_id: UUID`, a resolved `config_snapshot: dict[str, str]`, and a captured `trigger_cause: TriggerCause` before returning.
2. WHEN Layer 5 reports `entity.run.state_changed` for that `run_id` THEN the system SHALL transition the `TestRun` mirror state using only the transitions declared in `TestRunStateMachine` AND SHALL raise `SemanticError` on any disallowed transition.
3. IF the triggering caller lacks the `test.run.trigger` RBAC permission on the project THEN the system SHALL raise `AuthorizationError` before any dispatch and SHALL NOT create a `TestRun` row.
4. WHILE a `TestRun` is in state `cancelling` the system SHALL reject further state mutations other than `cancelled` or `failed` and SHALL continue to forward progress for audit correctness.
5. WHERE the catalog entry declares `required_capabilities: list[str]` the system SHALL refuse to dispatch when the target pod client's advertised capabilities (from `3-client-capability-advertisement`) do not cover the set AND SHALL raise `CapabilityMismatchError` with both sides listed.

### Requirement 2: Runner-Kind Factory Protocol

**User Story:** As an extension author shipping a new test runner (for
example an embedded-device HIL runner), I want a clear factory protocol to
implement, so that Pychestrate can dispatch my runner without modifications
to the service.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers a `TestRunnerKindProtocol` implementation with `factory_protocol_name = "test_runner_kind"` THEN the system SHALL verify every required classmethod (`kind_name`, `build_job_envelope`, `validate_inputs`, `parse_progress_format_tag`, `parse_result_format_tag`, `capability_requirements`) is present AND SHALL raise `ConfigurationError` naming any missing method.
2. IF two registered implementations return the same `kind_name()` with the same `PRECEDENCE` THEN the system SHALL raise `ConfigurationError` at load time naming both classes.
3. WHEN `trigger_run` is called with a `runner_kind` not covered by any registered implementation THEN the system SHALL raise `SemanticError` before any Layer 5 call.
4. WHERE the runner declares `parse_progress_format_tag() == "testbase.forwarding_info.v1"` the system SHALL wire `5-progress-ingest` with the matching `progress_parser` implementation AND SHALL refuse to dispatch if no such parser is registered.

### Requirement 3: Trigger Causality And Idempotency

**User Story:** As a user triggering the same test by webhook or manual
click, I want the service to deduplicate identical triggers, so that a
retry storm does not produce a forest of duplicate runs.

**Acceptance Criteria (EARS):**

1. WHEN two `trigger_run` calls arrive within `idempotency_window_seconds` with the same `(project_id, catalog_entry_id, target_pod_id, idempotency_key)` tuple THEN the system SHALL return the original `run_id` without creating a second `TestRun`.
2. IF the `idempotency_key` is omitted THEN the system SHALL generate one by hashing `(project_id, catalog_entry_id, target_pod_id, inputs_canonical_json, trigger_cause_kind)` and SHALL apply the same dedup window.
3. WHEN a trigger is accepted THEN the system SHALL emit `entity.test.run_started` on `0-message-bus` with `{run_id, project_id, catalog_entry_id, target_pod_id, runner_kind, trigger_cause, idempotency_key}`.
4. WHEN a run reaches a terminal state THEN the system SHALL emit `entity.test.run_completed` with `{run_id, final_state, started_at, finished_at, result_root_key}` on the bus.

### Requirement 4: Result Root Binding

**User Story:** As a user inspecting a completed run, I want the run entity
to point at exactly one testbase-shaped result tree under the shared
results backend, so that progress streams, artifacts, and final
`testrun_summary.json` can be resolved from a single handle.

**Acceptance Criteria (EARS):**

1. WHEN `5-dispatch-receipt` records a per-client local run id THEN the system SHALL persist it on the `TestRun` as `client_local_run_id: str` AND SHALL use the `(client_id, client_local_run_id)` tuple for all reconciliation.
2. WHEN `5-shared-results-backend` allocates the result root for the run THEN the system SHALL persist `result_root_key: str` on the `TestRun` before transitioning out of `pending`.
3. IF the final `testrun_summary.json` is not present under `result_root_key` when Layer 5 reports `completed` THEN the system SHALL transition the run to `completed_no_summary` (not `completed`) and emit a structured log at WARNING.

## Property-Based Test Requirements

### Property 1: State Machine Reachability Matches Declaration

- **Invariant:** For any sequence of Layer 5 state events applied to a freshly created `TestRun`, the set of states the mirror traverses is a subset of the states reachable from `pending` in `TestRunStateMachine`; no state is reached that is not declared as a successor in the transition table.
- **Generator:** `hypothesis.strategies.lists(sampled_from(RunStateEvent), min_size=1, max_size=20)` paired with a fresh `TestRun` in `pending`.
- **Assertion:** After applying each event in sequence (illegal events raise `SemanticError` which the test catches and records), every visited state is in `TestRunStateMachine.reachable_from("pending")`.
- **Sample size:** 1000 generated cases

### Property 2: Idempotent Trigger Returns The Same Run Id

- **Invariant:** For any fixed `(project_id, catalog_entry_id, target_pod_id, idempotency_key)` tuple, repeated calls to `trigger_run` within `idempotency_window_seconds` return the same `run_id`.
- **Generator:** `hypothesis.strategies.tuples(uuids(), uuids(), uuids(), text(min_size=1, max_size=64))` paired with a randomized number of repeat invocations between 2 and 10.
- **Assertion:** All invocations return the same `run_id`; exactly one `entity.test.run_started` event is emitted for the tuple.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `trigger_run` p99 < 120 ms from request entry to bus event emission (excluding Layer 5 dispatch latency). State mirror updates p99 < 20 ms. Dispatch-to-client end-to-end p99 < 1.5 s from `trigger_run` to Layer 5 emitting `entity.run.state_changed: dispatched`.
- **NFR-2 (Security):** Trigger is gated by `test.run.trigger` on the project; cancel is gated by `test.run.cancel`; view is gated by `test.run.view`. All mutating calls audited via `1-audit-log`. Runner-provided `inputs` validated against the runner's `validate_inputs` contract before dispatch; unvalidated inputs rejected with `SemanticError`.
- **NFR-3 (Observability):** Metrics `pychestrate_test_runs_total{project,runner_kind,final_state}` (counter), `pychestrate_test_run_duration_seconds{project,runner_kind}` (histogram), `pychestrate_test_trigger_latency_seconds{project}` (histogram), `pychestrate_test_runs_in_flight{project,runner_kind}` (gauge), `pychestrate_test_dispatch_failures_total{project,runner_kind,reason}` (counter). Log events `pychestrate.test.run.triggered`, `pychestrate.test.run.dispatched`, `pychestrate.test.run.completed`, `pychestrate.test.run.cancelled`, `pychestrate.test.run.dispatch_failed`. Trace spans `pychestrate.test.trigger_run`, `pychestrate.test.state_mirror_update`.
- **NFR-4 (Reliability):** A Layer 5 state event delivered out-of-order SHALL be buffered and reapplied in order; duplicated events are idempotent. A restart of the service SHALL NOT regress any `TestRun` state — the run table is the authoritative mirror and the Layer 5 reconciler is the recovery path.

## Out of Scope

- Suite registration, owners, tags, or runtime-hint metadata (see `6-test-catalog`).
- Fan-out/sharding across a matrix (see `6-matrix-sharding`).
- Live progress rendering (see `6-live-run-view`).
- Flake classification and quarantine (see `6-flake-tracking`).
- Cross-run diff (see `6-compare-runs`).

## Dependencies

- **Depends on:** `5-job-envelope`, `5-job-dispatch`, `5-dispatch-receipt`, `5-run-state-machine`, `5-progress-ingest`, `5-result-ingest-watcher`, `5-shared-results-backend`, `3-client-registry`, `3-client-capability-advertisement`, `6-test-catalog`, `1-rbac`, `1-audit-log`, `2-projects`.
- **Depended on by:** `6-matrix-sharding`, `6-live-run-view`, `6-flake-tracking`, `6-triage-bug-linking`, `6-compare-runs`, `7-test-metrics`, `9-run-detail-ui`.
- **Extension points exposed:** `factory: test_runner_kind` — testbase default plus gtest-native, pytest-native, embedded HIL runners contributed by packs.
