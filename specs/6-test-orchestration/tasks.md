# 6-test-orchestration — Tasks

## Milestones

- **M1 — Skeleton:** `TestRun` persistence, state machine skeleton, `TestOrchestrator.trigger_run` happy path wiring to Layer 5 with the in-tree `TestbaseRunnerKind`, minimal REST route.
- **M2 — Core Behavior:** Cancel flow, Layer 5 state mirror, idempotency, capability gating, audit + bus events, runner registry via the extension host.
- **M3 — Hardening:** Observability, property tests, extension-point test, RBAC enforcement, rate limiting, error-taxonomy polish, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create the `source/site/automojo/pychestrate/webservice/orchestration/test/` package per design.md Component Breakdown.
- [ ] T1.2 — Implement `repository.py::TestRunRepository` with the `test_run` schema (`0-persistence` migration included).
- [ ] T1.3 — Implement `state_machine.py::TestRunStateMachine` transition table covering all nine states.
- [ ] T1.4 — Implement `errors.py` exporting `CapabilityMismatchError`, `DispatchFailedError`, and re-exporting `AuthorizationError`.
- [ ] T1.5 — Implement `runner_protocol.py::TestRunnerKindProtocol` declaring `factory_protocol_name = "test_runner_kind"` and every required classmethod.
- [ ] T1.6 — Implement `TestbaseRunnerKind` at `source/site/automojo/factories/pychestrate/test_runner/testbase.py` with `PRECEDENCE = 1000`.
- [ ] T1.7 — Implement `orchestrator.py::TestOrchestrator.trigger_run` happy path: RBAC → catalog lookup → input validate → shared-results allocate → envelope build → `5-job-dispatch.dispatch`.
- [ ] T1.8 — Register `POST /api/v1/projects/{project_id}/test-runs` and `GET /api/v1/projects/{project_id}/test-runs/{run_id}` under Flask-RestX.

### M2 — Core Behavior

- [ ] T2.1 — Implement `trigger.py` idempotency resolver (explicit key or hash of inputs/cause) with a `(project_id, idempotency_key)` unique index.
- [ ] T2.2 — Implement `mirror.py` subscriber for `entity.run.state_changed` / `completed` / `failed`; route through `TestRunStateMachine.validate_transition`.
- [ ] T2.3 — Implement `cancel_run`: RBAC check, state check, transition to `cancelling`, RPC into `5-cancel-reconcile`.
- [ ] T2.4 — Implement capability-gating: call `3-client-capability-advertisement.get(target_pod_id)` and cross-check against `capability_requirements(...)`; raise `CapabilityMismatchError` with a multiline required-vs-advertised body.
- [ ] T2.5 — Implement `runner_registry.py` accessor over the extension host; subscribe to `extension.reloaded` to refresh.
- [ ] T2.6 — Emit `entity.test.run_started`, `entity.test.run_completed`, `entity.test.run_cancelled`, `entity.test.run_dispatch_failed` events on `0-message-bus`.
- [ ] T2.7 — Write audit log entries for trigger and cancel via `1-audit-log` including actor, project, run, and a `config_snapshot` digest.
- [ ] T2.8 — Implement `aspects.py::TriggerAspects` and `CancelAspects` (timeout, retry policy, log verbosity).

### M3 — Hardening

- [ ] T3.1 — Emit Prometheus metrics and OTel spans per design.md Observability; verify label cardinality bounded by `project × runner_kind`.
- [ ] T3.2 — Enforce per-project rate limit `max_triggers_per_minute_per_project` (default 120); return 429.
- [ ] T3.3 — Enforce `max_inputs_bytes` (default 256 KiB); reject larger with `SemanticError`.
- [ ] T3.4 — Benchmark NFR-1: `trigger_run` p99 < 120 ms; state mirror update p99 < 20 ms; dispatch-to-client p99 < 1.5 s (synthetic client). Fail CI on regression.
- [ ] T3.5 — Sphinx docs for the public REST API and `TestOrchestrator` internal API.
- [ ] T3.6 — Handle orphan `entity.run.state_changed` events (unknown `run_id`) with once-per-hour WARNING log dedup.
- [ ] T3.7 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.8 — Implement `completed_no_summary` handling: absence of `testrun_summary.json` under `result_root_key` flips the final state and logs at WARNING.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (state-machine reachability) and Property 2 (idempotent trigger) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 3 exit criterion — a manually triggered testbase run dispatches to a registered pod (synthetic client), progress streams, and a full result tree surfaces; `testrun_summary.json` binds to the run row.
- [ ] TT-4 — Extension-point test: in-tree `TestbaseRunnerKind` (`PRECEDENCE = 1000`) plus a test-only `FakeRunnerKind` (`PRECEDENCE = 1`) registered at test setup; verify the fake wins lookup and emits its envelope on dispatch.
- [ ] TT-5 — Cancel test: trigger a run, flip it to `cancelling`, verify `5-cancel-reconcile` is invoked and terminal `cancelled` event fires.
- [ ] TT-6 — Idempotency test: concurrent duplicate `trigger_run` calls from 16 goroutines return the same `run_id`; exactly one `entity.test.run_started` event is observed.
- [ ] TT-7 — Capability-mismatch test: target pod missing advertised capability refuses dispatch with `CapabilityMismatchError` carrying both sides.

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
