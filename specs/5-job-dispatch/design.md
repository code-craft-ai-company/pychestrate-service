# 5-job-dispatch — Design

## Architecture

The dispatcher is the single entry point for moving a submitted job
from orchestration features into a pod client's process. It is a
stateful service-owned component living under
`source/site/automojo/pychestrate/webservice/jobs/dispatch/`. At
dispatch time it composes three dependencies:

1. the capability-filter over the `3-client-registry` snapshot,
2. the active `DispatchStrategyProtocol` implementation (resolved
   through `E-extension-host`), and
3. `5-job-envelope.codec` for envelope build + sign.

Authoritative source of truth for a run's `dispatched` state is the
`run` row in `0-persistence`; the dispatcher writes through
`5-run-state-machine` so every observer sees the transition via the
bus. In-flight counts per pod live in memory and are
reconciled-on-startup from the `dispatch_receipt` table so a process
restart does not oversubscribe pods. The dispatcher never reaches
past a pod client to its members — the envelope names the pod, and
the client decides *how* to use its pod members. This feature lands
in **Phase 3**.

## Data Model

Owned rows:

- `dispatch_attempt`:
  - `attempt_id: UUID` (PK, UUIDv7)
  - `run_id: UUID` (FK)
  - `envelope_id: UUID` (FK → `job_envelope.envelope_id`)
  - `pod_id: UUID | None`
  - `strategy_name: str`
  - `status: DispatchStatus` (`routing`, `transmitted`, `acked`,
    `ack_timeout`, `transport_failed`, `no_eligible_pod`)
  - `started_at: datetime`
  - `completed_at: datetime | None`
  - `last_error: str | None`
  - Indices: `(run_id)`, `(pod_id, status)`.

In-memory state:

- `_inflight_by_pod: dict[UUID, int]` — rehydrated on startup.
- `_backoff_queue: list[BackoffEntry]` — submissions awaiting eligible
  pods.
- `_strategy_cache: dict[UUID, DispatchStrategyProtocol]` — per-project
  resolved strategy.

Value types:

- `JobSubmission`:
  - `submission_id: UUID`
  - `project_id: UUID`
  - `job_id: UUID`
  - `job_name: str`
  - `job_type: str`
  - `pipeline_id: UUID | None`
  - `pipeline_instance_id: UUID | None`
  - `required_capabilities: frozenset[CapabilityRequirement]`
  - `preferred_pod_id: UUID | None`
  - `priority: int`
  - `deadline_hint: datetime | None`
  - `queue_if_unavailable: bool`
  - `params: dict[str, Any]`
  - `scope_secret_names: frozenset[str]`
- `PodLoadSnapshot`:
  - `pod_id: UUID`
  - `inflight: int`
  - `concurrency_cap: int`
  - `last_heartbeat_at: datetime`
  - `advertised_capabilities: frozenset[Capability]`

## Interfaces

### Public API

N/A at the HTTP surface. REST integration with `8-rest-api-v1` is a
Layer-8 concern and is out of scope here.

### Internal API

```python
class JobDispatcher:
    def __init__(
        self,
        client_registry: ClientRegistryFacade,
        envelope_codec: EnvelopeCodec,
        client_transport: ClientTransport,
        strategy_registry: DispatchStrategyRegistry,
        receipt_repository: DispatchReceiptRepository,
        run_state_machine: RunStateMachine,
        bus: MessageBus,
        config: DispatchConfig
    ) -> None:
        self._client_registry = client_registry
        self._envelope_codec = envelope_codec
        self._client_transport = client_transport
        self._strategy_registry = strategy_registry
        self._receipt_repository = receipt_repository
        self._run_state_machine = run_state_machine
        self._bus = bus
        self._config = config
        self._inflight_by_pod: dict[UUID, int] = {}
        self._backoff_queue: list[BackoffEntry] = []
        return

    def dispatch(
        self,
        submission: JobSubmission,
        aspects: DispatchAspects | None = None
    ) -> DispatchOutcome:
        """
            Route a submission to a capable pod and transmit a signed
            envelope.

            :param submission: The job submission to dispatch.
            :param aspects: Behavior parameters (retry, timeout,
                            logging).

            :returns: DispatchOutcome naming the run, envelope, pod,
                      and receipt.
            :raises: NoEligiblePodError, SemanticError,
                     DispatchTransportError
        """
        ...

    def rehydrate_inflight(
        self
    ) -> None:
        """
            Rebuild in-memory inflight counters from the
            dispatch_attempt table at startup.

            :returns: None
            :raises: DispatchRehydrationError
        """
        ...

    def handle_ack(
        self,
        attempt_id: UUID,
        receipt: DispatchReceipt
    ) -> None:
        """
            Apply a client-provided DispatchReceipt to the attempt,
            transition run state, and emit entity.run.dispatched.

            :param attempt_id: Dispatch attempt id.
            :param receipt: Client-reported receipt.

            :returns: None
            :raises: SemanticError
        """
        ...
```

### Extension Surface

Factory protocol declared here:

```python
class DispatchStrategyProtocol(FactoryProtocolBase):
    """
        Contract for dispatch_strategy implementations.

        Each implementation inherits FactoryExtension, sets
        factory_protocol_name = "dispatch_strategy", and assigns an
        integer PRECEDENCE (lower wins).
    """
    factory_protocol_name: str = "dispatch_strategy"

    @classmethod
    def select(
        cls,
        candidate_pods: list[PodLoadSnapshot],
        submission: JobSubmission,
        project_id: UUID
    ) -> UUID | None:
        """
            Choose a pod id for this submission or return None if no
            pod should be used at this moment.

            :param candidate_pods: Pods that satisfy capability filter
                                   and are not at cap.
            :param submission: The submission under consideration.
            :param project_id: Scope for project-tuned policies.

            :returns: The chosen pod_id, or None to queue.
            :raises: None — returning None is the canonical defer.
        """
        ...
```

Reference implementations shipped in-tree (under
`source/site/automojo/factories/pychestrate/dispatch_strategy/`):

- `FifoDispatchStrategy` — `PRECEDENCE = 1000`. Chooses the
  least-inflight pod, breaking ties by oldest `last_heartbeat_at`.
- `StickyPodDispatchStrategy` — `PRECEDENCE = 900`. Prefers a pod
  that recently ran the same `job_name` for this project; falls back
  to FIFO.

### Events Emitted

On `0-message-bus`:

- `entity.run.dispatched` — `{run_id: UUID, envelope_id: UUID,
  pod_id: UUID, project_id: UUID, strategy: str, issued_at:
  datetime}`
- `pychestrate.job_dispatch.failed` — `{submission_id, project_id,
  reason, capabilities_missing}`

### Events Consumed

- `entity.pod.state_changed` (from `3-pod-lifecycle`) — updates
  in-memory eligibility; drops drained/maintenance pods from
  candidate sets.
- `entity.client.capability.updated` (from
  `3-client-capability-advertisement`) — refreshes capability
  snapshots.
- `extension.reloaded` — re-resolves strategy registry.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/`:

- `jobs/dispatch/__init__.py`
- `jobs/dispatch/dispatcher.py` — `JobDispatcher` facade.
- `jobs/dispatch/strategy_registry.py` — factory protocol resolution.
- `jobs/dispatch/eligibility.py` — capability + lifecycle filtering.
- `jobs/dispatch/backoff_queue.py` — in-memory deferred queue.
- `jobs/dispatch/transport_adapter.py` — bridge to
  `3-client-agent-protocol`.
- `jobs/dispatch/repository.py` — `dispatch_attempt` persistence.
- `jobs/dispatch/aspects.py` — `DispatchAspects` (retry, timeout,
  logging).
- `jobs/dispatch/errors.py` — `NoEligiblePodError`,
  `DispatchTransportError`, `DispatchRehydrationError`.
- `jobs/dispatch/hooks.py` — startup rehydration hook.

Factories live under
`source/site/automojo/factories/pychestrate/dispatch_strategy/`.

## Key Flows

### Flow 1 — Happy-Path Dispatch

1. `6-test-orchestration` creates a `JobSubmission` and calls
   `dispatcher.dispatch(submission)`.
2. `eligibility.filter_candidates(submission)` returns pod snapshots
   that satisfy required capabilities and are not at cap.
3. `strategy_registry.for_project(project_id).select(...)` chooses
   `pod_id` (or `None`).
4. Dispatcher calls `envelope_codec.build(dispatch_request)` and
   `envelope_codec.sign(envelope)`.
5. `transport_adapter.send(client_id, signed_envelope, timeout)`
   transmits the envelope.
6. Client replies with `DispatchReceipt`; dispatcher calls
   `handle_ack`, persists the receipt, increments `_inflight_by_pod`,
   transitions run to `dispatched`, and emits
   `entity.run.dispatched`.

### Flow 2 — No Eligible Pod, Queued

1. Candidate set is empty (all pods draining or missing a
   capability).
2. If `queue_if_unavailable=True`, submission lands in
   `_backoff_queue` with initial delay 1 s.
3. `pychestrate.job_dispatch.failed` is *not* emitted — it's a
   retryable state. `pychestrate_job_dispatch_queue_depth` gauge
   ticks up.
4. Scheduler tick (every 500 ms) re-runs eligibility; on success,
   path rejoins Flow 1.
5. If `queue_if_unavailable=False`, `NoEligiblePodError` is raised,
   `pychestrate.job_dispatch.failed` is emitted, and the run
   transitions to `dispatch_failed`.

### Flow 3 — Ack Timeout → Reconcile

1. Envelope transmits OK; no `DispatchReceipt` within
   `dispatch_ack_timeout`.
2. Attempt flips to `ack_timeout`; run state moves to
   `dispatch_unconfirmed`.
3. On the client's next heartbeat, `5-cancel-reconcile` consults
   the client's local run ledger. If the client reports the run
   as started, state advances normally; if not, the run goes to
   `dispatch_lost` and is re-dispatchable.

## Error Handling

- `SemanticError` (invalid submission — missing `project_id`,
  unknown `pod_id` for preferred routing): never caught.
- `NoEligiblePodError`: multiline message listing every missing
  capability; bubbles to the orchestrator feature.
- `DispatchTransportError`: caught ONCE at `transport_adapter`
  boundary, reclassified with `client_id`, `envelope_id`,
  `attempt_id` context; retried per `DispatchAspects`.
- `ConfigurationError`: raised at startup for duplicate-precedence
  strategy collisions; process exits non-zero.
- `DispatchRehydrationError`: startup fails; operators must
  investigate — the alternative (silent inflight undercount) would
  oversubscribe pods.

Example multiline error:

```python
err_msg_lines = ["No eligible pod for dispatch."]
err_msg_lines.append("PROJECT: {}".format(submission.project_id))
err_msg_lines.append("JOB_TYPE: {}".format(submission.job_type))
err_msg_lines.append("MISSING CAPABILITIES:")
for cap in missing:
    err_msg_lines.append("    {} ({})".format(cap.name, cap.version_pred))

err_msg = os.linesep.join(err_msg_lines)
raise NoEligiblePodError(err_msg) from None
```

## Security Considerations

- Dispatch API is internal; REST invocation passes through
  `8-rest-api-v1` with the `jobs:dispatch` RBAC permission
  enforced at the route layer, not here.
- Every dispatch attempt writes to `1-audit-log` via a subscriber on
  `entity.run.dispatched` and `pychestrate.job_dispatch.failed` —
  who dispatched, to where, which strategy chose.
- `envelope_id` uniqueness is enforced at the DB; replays cannot
  land a second inflight count.
- Input validation: `JobSubmission` is a Pydantic model with
  `additionalProperties: false`; unknown fields rejected at parse
  time.

## Observability

Metrics:

- `pychestrate_job_dispatch_requested_total{project,job_type}` — counter
- `pychestrate_job_dispatch_succeeded_total{project,job_type,strategy}` — counter
- `pychestrate_job_dispatch_failed_total{project,reason}` — counter
- `pychestrate_job_dispatch_latency_seconds{project,strategy}` — histogram
- `pychestrate_job_dispatch_queue_depth{project}` — gauge
- `pychestrate_job_dispatch_inflight{pod_id}` — gauge
- `pychestrate_job_dispatch_ack_timeouts_total{project}` — counter

Log events:

- `pychestrate.job_dispatch.accepted`
- `pychestrate.job_dispatch.routed`
- `pychestrate.job_dispatch.ack_timeout`
- `pychestrate.job_dispatch.failed`
- `pychestrate.job_dispatch.requeued`

Trace span `pychestrate.job_dispatch.dispatch` with `project`,
`job_type`, `pod_id`, `strategy`, `envelope_id`, `attempt_id`.

Dashboards: dispatch-latency + queue-depth tile under
`7-orchestration-metrics`; pod-inflight heatmap under
`3-client-inventory-ui`.

## Open Questions

- Should the backoff queue be persisted across restarts, or is
  in-memory acceptable until persistent fair-share lands in Phase 4?
  Timebox: Phase 3 exit.
- How do we resolve a tie between `preferred_pod_id` and strategy
  preference? Current draft: preferred wins if under cap; strategy
  decides otherwise. Confirm with orchestration team. Timebox: Phase
  3 design review.
- Where does matrix/shard fan-out live — here or in
  `6-matrix-sharding`? Current draft: fan-out is upstream; the
  dispatcher always receives single-pod submissions. Timebox: Phase
  5 start.
