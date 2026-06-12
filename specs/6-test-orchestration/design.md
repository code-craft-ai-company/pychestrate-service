# 6-test-orchestration — Design

## Architecture

`6-test-orchestration` is the test-domain orchestrator that sits above Layer 5.
It accepts trigger calls (REST, webhook, pipeline step, manual) and mints
`TestRun` entities backed by `0-persistence`. It binds a registered catalog
entry (`6-test-catalog`) and a selected `test_runner_kind` implementation to
a target pod client, then hands off an envelope to `5-job-dispatch`. It does
not execute anything itself and does not talk to pod members — the pod
client is the sole point of contact. The authoritative source of truth for
*run lifecycle* is the Layer 5 `5-run-state-machine`; this feature owns a
*test-specific mirror* of that state, plus test-specific fields (runner
kind, catalog entry id, config snapshot, result root key). The feature
ships in Phase 3 as part of the first end-to-end test slice; `6-test-catalog`
and `6-live-run-view` land alongside it.

## Data Model

Persistent table `test_run` in `0-persistence`:

- `run_id: UUID` — primary key.
- `project_id: UUID` — foreign key to `project`.
- `catalog_entry_id: UUID` — foreign key to `test_catalog_entry`.
- `target_pod_id: UUID` — foreign key to `pod`.
- `runner_kind: str` — matches a registered `TestRunnerKindProtocol.kind_name()`.
- `state: TestRunState` — enum {`pending`, `dispatching`, `dispatched`, `running`, `cancelling`, `cancelled`, `failed`, `completed`, `completed_no_summary`}.
- `trigger_cause: TriggerCause` — dataclass-embedded JSON: `{kind: "manual"|"webhook"|"pipeline"|"schedule", actor_id: UUID | None, reference: str | None}`.
- `idempotency_key: str` — indexed with `(project_id, catalog_entry_id, target_pod_id)` as unique composite.
- `config_snapshot: dict[str, str]` — resolved variables at trigger time.
- `inputs_canonical_json: bytes` — canonicalized runner inputs.
- `client_local_run_id: str | None` — set after `5-dispatch-receipt`.
- `result_root_key: str | None` — set after `5-shared-results-backend` allocation.
- `started_at: datetime | None`
- `finished_at: datetime | None`
- `final_state_reason: str | None`

Indices: `(project_id, state)`, `(target_pod_id, state)`, `(catalog_entry_id, started_at DESC)`, unique `(project_id, idempotency_key)`.

In-memory value types:

- `TriggerRunResult` — `{run_id: UUID, was_duplicate: bool, envelope_id: UUID}`.
- `TestRunStateMachine` — static transition table owned by this module.

## Interfaces

### Public API

REST under `8-rest-api-v1`:

- `POST /api/v1/projects/{project_id}/test-runs` — body `TriggerRunRequest`, returns `TriggerRunResult`.
- `GET /api/v1/projects/{project_id}/test-runs/{run_id}` — returns `TestRunView`.
- `POST /api/v1/projects/{project_id}/test-runs/{run_id}:cancel` — returns `TestRunView`.
- `GET /api/v1/projects/{project_id}/test-runs?state=...&catalog_entry_id=...&limit=...` — paginated list.

WebComponent: `<px-test-run-summary run-id="...">` (element detail owned by `9-run-detail-ui`; contract here).

### Internal API

```python
class TestOrchestrator:
    def __init__(
        self,
        runs_repo: TestRunRepository,
        catalog: TestCatalog,
        dispatcher: JobDispatcher,
        envelope_builder: JobEnvelopeBuilder,
        rbac: RbacService,
        audit: AuditLog,
        bus: MessageBus,
        runner_registry: TestRunnerRegistry,
        config_resolver: VariableResolver,
        shared_results: SharedResultsBackend,
        clock: Clock
    ) -> None:
        self._runs_repo = runs_repo
        self._catalog = catalog
        self._dispatcher = dispatcher
        self._envelope_builder = envelope_builder
        self._rbac = rbac
        self._audit = audit
        self._bus = bus
        self._runner_registry = runner_registry
        self._config_resolver = config_resolver
        self._shared_results = shared_results
        self._clock = clock
        return

    def trigger_run(
        self,
        project_id: UUID,
        actor_id: UUID,
        catalog_entry_id: UUID,
        target_pod_id: UUID,
        runner_kind: str,
        inputs: dict[str, object],
        trigger_cause: TriggerCause,
        idempotency_key: str | None = None,
        aspects: TriggerAspects | None = None
    ) -> TriggerRunResult:
        """
            Create a TestRun, build its envelope, dispatch via Layer 5.

            :param project_id: Owning project.
            :param actor_id: User or service principal issuing the trigger.
            :param catalog_entry_id: Registered test-catalog entry.
            :param target_pod_id: Pod whose client will execute the run.
            :param runner_kind: Registered test_runner_kind name.
            :param inputs: Runner-specific inputs (validated by the runner).
            :param trigger_cause: Source of the trigger (manual, webhook, etc.).
            :param idempotency_key: Optional external dedup key.
            :param aspects: Behavior parameters (timeout, retry, logging).

            :returns: TriggerRunResult with run_id and was_duplicate flag.
            :raises: AuthorizationError, CapabilityMismatchError,
                     SemanticError, ConfigurationError
        """
        ...

    def cancel_run(
        self,
        project_id: UUID,
        actor_id: UUID,
        run_id: UUID,
        reason: str,
        aspects: CancelAspects | None = None
    ) -> TestRunView:
        """
            Request cancellation of an in-flight run via Layer 5.

            :param project_id: Owning project.
            :param actor_id: User or service principal requesting cancel.
            :param run_id: Target test run.
            :param reason: Free-text reason stored on the run.
            :param aspects: Behavior parameters.

            :returns: Updated TestRunView.
            :raises: AuthorizationError, SemanticError
        """
        ...

    def apply_layer5_state_event(
        self,
        run_id: UUID,
        event: RunStateEvent
    ) -> None:
        """
            Mirror a Layer 5 state transition onto the TestRun record.

            :param run_id: Target test run.
            :param event: Deserialized Layer 5 state event.

            :returns: None.
            :raises: SemanticError
        """
        ...
```

### Extension Surface

Factory protocol declared here:

```python
class TestRunnerKindProtocol(FactoryProtocolBase):
    """
        Contract for test_runner_kind implementations.

        Implementing classes inherit FactoryExtension, set
        factory_protocol_name = "test_runner_kind", and assign PRECEDENCE.
    """
    factory_protocol_name: str = "test_runner_kind"

    @classmethod
    def kind_name(cls) -> str:
        """
            Return the stable kind identifier (e.g., "testbase").

            :returns: Short name used by callers.
            :raises: None
        """
        ...

    @classmethod
    def build_job_envelope(
        cls,
        run_id: UUID,
        project_id: UUID,
        target_pod_id: UUID,
        catalog_entry: TestCatalogEntrySnapshot,
        inputs: dict[str, object],
        result_root_key: str
    ) -> JobEnvelope:
        """
            Produce a Layer 5 JobEnvelope for this runner.

            :param run_id: TestRun identifier.
            :param project_id: Owning project.
            :param target_pod_id: Target pod.
            :param catalog_entry: Immutable snapshot of the catalog entry.
            :param inputs: Validated runner inputs.
            :param result_root_key: Allocated shared-results path.

            :returns: Fully formed JobEnvelope ready for dispatch.
            :raises: ConfigurationError, SemanticError
        """
        ...

    @classmethod
    def validate_inputs(
        cls,
        inputs: dict[str, object]
    ) -> None:
        """
            Validate runner-specific inputs; raise on malformed input.

            :param inputs: Caller-supplied inputs.

            :returns: None.
            :raises: SemanticError
        """
        ...

    @classmethod
    def parse_progress_format_tag(cls) -> str:
        """
            Return the format tag routed into 5-progress-ingest.

            :returns: Progress parser key (e.g., "testbase.forwarding_info.v1").
            :raises: None
        """
        ...

    @classmethod
    def parse_result_format_tag(cls) -> str:
        """
            Return the format tag routed into 5-result-ingest-watcher.

            :returns: Result parser key (e.g., "testbase.tree.v1").
            :raises: None
        """
        ...

    @classmethod
    def capability_requirements(
        cls,
        catalog_entry: TestCatalogEntrySnapshot
    ) -> list[str]:
        """
            Declare capabilities required on the target pod.

            :param catalog_entry: Immutable snapshot of the catalog entry.

            :returns: List of capability identifiers.
            :raises: None
        """
        ...
```

Reference implementation shipped in-tree under
`source/site/ccai/factories/pychestrate/test_runner/testbase.py`:

- `TestbaseRunnerKind` — `kind_name() == "testbase"`, `PRECEDENCE = 1000`.
  Builds an envelope that invokes `codecraftai-testbase`'s runner on the
  pod client, declares `parse_progress_format_tag() == "testbase.forwarding_info.v1"`,
  and `parse_result_format_tag() == "testbase.tree.v1"`.

### Events Emitted

On `0-message-bus`:

- `entity.test.run_started` — `{run_id, project_id, catalog_entry_id, target_pod_id, runner_kind, trigger_cause, idempotency_key}`
- `entity.test.run_completed` — `{run_id, final_state, started_at, finished_at, result_root_key}`
- `entity.test.run_cancelled` — `{run_id, actor_id, reason}`
- `entity.test.run_dispatch_failed` — `{run_id, reason, error_kind}`

### Events Consumed

- `entity.run.state_changed` from `5-run-state-machine` — mirrored onto `TestRun`.
- `entity.run.completed` and `entity.run.failed` — drive terminal transitions.
- `extension.reloaded` — re-resolves the runner registry so newly loaded runner kinds are addressable without restart.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/orchestration/test/`:

- `__init__.py`
- `orchestrator.py` — `TestOrchestrator` class (public internal API).
- `repository.py` — `TestRunRepository` backed by `0-persistence`.
- `state_machine.py` — `TestRunStateMachine` transition table.
- `runner_registry.py` — accessor over the extension host for `test_runner_kind`.
- `runner_protocol.py` — `TestRunnerKindProtocol` declaration.
- `trigger.py` — trigger-causality and idempotency helpers.
- `mirror.py` — Layer 5 state-event consumer.
- `aspects.py` — `TriggerAspects`, `CancelAspects`.
- `errors.py` — `CapabilityMismatchError`, `DispatchFailedError`.
- `events.py` — typed event payload dataclasses.
- `rest/v1_routes.py` — REST route registration under Flask-RestX.

Reference runner under `source/site/ccai/factories/pychestrate/test_runner/testbase.py`.

## Key Flows

### Flow 1 — Trigger a testbase run end-to-end

1. REST handler receives `POST /api/v1/projects/{id}/test-runs`.
2. Handler calls `TestOrchestrator.trigger_run(...)`.
3. RBAC check `test.run.trigger`; fail → `AuthorizationError`.
4. Catalog lookup produces `TestCatalogEntrySnapshot`.
5. Runner registry resolves `runner_kind` → `TestbaseRunnerKind`; inputs validated.
6. Capability requirements checked against `3-client-capability-advertisement`; mismatch → `CapabilityMismatchError`.
7. Idempotency key resolved (provided or hashed); dedup lookup may return the original `run_id`.
8. `TestRun` row persisted in `pending`; audit event written.
9. Shared results root allocated; `result_root_key` persisted; state transitions to `dispatching`.
10. `TestRunnerKindProtocol.build_job_envelope(...)` produces a `JobEnvelope`.
11. `JobDispatcher.dispatch(envelope)` returns a `DispatchReceipt`; `client_local_run_id` stored.
12. `entity.test.run_started` emitted.

### Flow 2 — Mirror Layer 5 state

1. `5-run-state-machine` emits `entity.run.state_changed` on the bus.
2. `mirror.py` subscriber resolves the matching `TestRun` by envelope id.
3. `TestRunStateMachine.validate_transition(current, next)` — illegal → `SemanticError` (never caught; logged at ERROR and the bus client re-raises).
4. Row updated; `test_run_state_changed` log entry written.
5. Terminal states publish `entity.test.run_completed` / `entity.test.run_cancelled` and finalize `finished_at`.

### Flow 3 — Cancel

1. REST `:cancel` handler → `cancel_run`.
2. RBAC check `test.run.cancel`.
3. Current state check: cancel allowed only from `pending`, `dispatching`, `dispatched`, `running`.
4. Row transitioned to `cancelling`.
5. `5-cancel-reconcile` RPC invoked; reconciliation against client truth governs final state.
6. `entity.test.run_cancelled` emitted on terminal arrival.

## Error Handling

- `AuthorizationError`, `CapabilityMismatchError`, `DispatchFailedError`: domain errors; handlers translate to 403, 409, 502 respectively.
- `SemanticError` (illegal state transition, missing runner kind, invalid inputs): never caught; bubble.
- `ConfigurationError` (runner protocol contract violation, missing progress parser): bubble to the extension host at load time.
- Layer 5 events arriving for an unknown `run_id`: logged at WARNING and dropped; emit `pychestrate.test.run.orphan_state_event` log once per hour per `run_id` seen.
- Multiline error messages built via `os.linesep.join([...])`; `CapabilityMismatchError` lists required and advertised side-by-side.

## Security Considerations

- Routes gated by `test.run.trigger`, `test.run.cancel`, `test.run.view` via `1-rbac`.
- Trigger and cancel append to `1-audit-log` with `actor_id`, `project_id`, `run_id`, resolved `config_snapshot` digest.
- `config_snapshot` is resolved through `2-global-variables` with `secret_ref_dereferencer`; secret values never stored on the `TestRun` — only references.
- `inputs` body size capped at `max_inputs_bytes` (default 256 KiB); larger requests rejected with `SemanticError`.
- Rate limit per project: `max_triggers_per_minute_per_project` (default 120).

## Observability

Metrics:

- `pychestrate_test_runs_total{project,runner_kind,final_state}` — counter
- `pychestrate_test_run_duration_seconds{project,runner_kind}` — histogram
- `pychestrate_test_trigger_latency_seconds{project}` — histogram
- `pychestrate_test_runs_in_flight{project,runner_kind}` — gauge
- `pychestrate_test_dispatch_failures_total{project,runner_kind,reason}` — counter

Log events:

- `pychestrate.test.run.triggered`
- `pychestrate.test.run.dispatched`
- `pychestrate.test.run.completed`
- `pychestrate.test.run.cancelled`
- `pychestrate.test.run.dispatch_failed`

Trace spans: `pychestrate.test.trigger_run`, `pychestrate.test.state_mirror_update`, `pychestrate.test.cancel_run`.

Dashboards: `7-test-metrics` rolls these up per project and runner_kind.

## Open Questions

- Do we allow multi-pod targeting in Phase 3 or defer until `6-matrix-sharding` in Phase 5? Timebox: Phase 3 scope freeze.
- Should `inputs_canonical_json` be included in the envelope signature scope, or only its SHA-256 digest? Timebox: Phase 3 exit.
- Do we surface `completed_no_summary` as a distinct final state in the UI, or fold it into `failed` with a reason code? Timebox: Phase 3 UX review.
