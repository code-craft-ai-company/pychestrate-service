# 3-pod-lifecycle — Design

## Architecture

Pod Lifecycle lives at
`source/site/ccai/pychestrate/webservice/pods/lifecycle/`. It is a
state-machine engine driven by bus events from neighbouring features and
REST admin actions. The engine itself is a pure function
(`transition_from`) that takes `(current_state, event_kind, context)` and
returns `(next_state, effects)` or raises `InvalidPodTransition`.
Persistence of the new state plus publication of `entity.pod.state_changed`
happens in a SERIALIZABLE transaction that loads the row, asks the engine
for the next state, and commits. Authoritative state: the
`pod_runtime_state` row per pod.

## Data Model

```
pod_runtime_state
    pod_id:             UUID     primary key (FK -> pod_definition)
    state:              PodState not null
    previous_state:     PodState nullable
    last_transition_at: datetime not null
    last_transition_event: str   not null
    in_use_since:       datetime nullable
    drain_requested_at: datetime nullable
    drain_completed_at: datetime nullable
    failure_reason:     str      nullable
    runs_remaining:     int      not null default 0
    transition_cursor:  int      not null default 0   -- optimistic lock
    (state)            index

pod_lifecycle_log
    log_id:             UUID     primary key
    pod_id:             UUID
    from_state:         PodState
    to_state:           PodState
    event_kind:         str
    event_payload:      jsonb
    actor:              str      -- client:<uuid> | user:<uuid> | system
    applied_at:         datetime
    (pod_id, applied_at) index
```

Enumeration (`pods/lifecycle/enums.py`):

```
class PodState(str, Enum):
    DEFINED = "defined"
    PROVISIONING = "provisioning"
    READY = "ready"
    IN_USE = "in_use"
    DRAINING = "draining"
    RELEASED = "released"
    CLIENT_LOST = "client_lost"
    FAILED = "failed"


class LifecycleEventKind(str, Enum):
    POD_REGISTERED = "pod.registered"
    POD_DEREGISTERED = "pod.deregistered"
    RUN_ACCEPTED = "run.accepted"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    CLIENT_LIVENESS_ALIVE = "client.liveness.alive"
    CLIENT_LIVENESS_SUSPECT = "client.liveness.suspect"
    CLIENT_LIVENESS_LOST = "client.liveness.lost"
    DRAIN_REQUESTED = "drain.requested"
    FORCE_RELEASE = "force.release"
    MEMBER_REPORT_UNHEALTHY = "member.report.unhealthy"
```

Transition table is declared as a `Mapping[Tuple[PodState,
LifecycleEventKind], PodState]` in `lifecycle/transitions.py`.

## Interfaces

### Public API

REST (RBAC `pod.lifecycle.*`):

- `GET /api/v1/projects/{project_id}/pods/{pod_id}/state` — current state +
  last transition metadata.
- `GET /api/v1/projects/{project_id}/pods/{pod_id}/state/history` — paginated
  transition log.
- `POST /api/v1/projects/{project_id}/pods/{pod_id}:drain` — request drain;
  permission `pod.lifecycle.drain`.
- `POST /api/v1/projects/{project_id}/pods/{pod_id}:force-release` —
  force-release; permission `pod.lifecycle.admin`.

### Internal API

```python
def transition_from(
    *,
    current_state: PodState,
    event_kind: LifecycleEventKind,
    context: TransitionContext,
) -> TransitionResult:
    ...


def apply_transition(
    *,
    pod_id: UUID,
    event_kind: LifecycleEventKind,
    event_payload: Mapping[str, Any],
    actor: str,
) -> PodState:
    ...


def get_pod_state(*, pod_id: UUID) -> PodRuntimeState:
    ...


def list_transitions(
    *,
    pod_id: UUID,
    limit: int,
    after_log_id: Optional[UUID],
) -> List[PodLifecycleLogEntry]:
    ...
```

### Extension Surface

No factory protocols or resource extensions. The extensibility surface is
the `entity.pod.state_changed` bus topic, published with a full payload
that downstream subscribers (including extension-contributed subscribers
via `E-extension-hooks`) can react to.

### Events Emitted

```
entity.pod.state_changed   {
    pod_id,
    project_id,
    from_state,
    to_state,
    event_kind,
    actor,
    applied_at,
}
```

### Events Consumed

- `entity.pod.registered` / `entity.pod.deregistered` (from `3-static-pods`).
- `entity.run.accepted|completed|failed|cancelled` (from
  `5-run-state-machine`).
- `entity.client.liveness_changed` (from `3-client-agent-protocol`).
- `entity.pod.provision_step_completed` / `entity.pod.ready` (from
  `3-dynamic-pods`, Phase 8 only).

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/pods/lifecycle/
    __init__.py
    enums.py
    dtos.py                    -- TransitionContext, TransitionResult,
                                  PodRuntimeState, PodLifecycleLogEntry
    transitions.py             -- the declared transition table
    engine.py                  -- transition_from (pure function)
    service.py                 -- apply_transition (SERIALIZABLE tx)
    repository.py              -- PodRuntimeStateRepository
    subscribers.py             -- bus subscribers bridging to apply_transition
    rest.py                    -- REST router (read + drain + force_release)
    metrics.py
```

## Key Flows

**Dynamic pod coming up.** Pod is inserted at `DEFINED` by `3-pod-definitions`;
dynamic path transitions to `PROVISIONING` on `entity.pod.materialization_started`.
Static path stays `DEFINED` until the client registers, then moves
`DEFINED -> READY` directly via `entity.pod.registered`.

**Normal run lifecycle.** Dispatch request fires `entity.run.accepted`;
subscriber calls `apply_transition(event=RUN_ACCEPTED)`; engine returns
`READY -> IN_USE`; tx writes row, publishes `entity.pod.state_changed`.
Run completes -> `apply_transition(event=RUN_COMPLETED)`; engine inspects
`runs_remaining` (tracked atomically), returns `IN_USE -> READY` when the
last run terminates.

**Drain + release.** Admin calls `:drain` REST -> `apply_transition
(event=DRAIN_REQUESTED, actor=user:<id>)` -> engine returns `*_ -> DRAINING`.
Subsequent run terminations drive `apply_transition` until `runs_remaining
== 0`; engine returns `DRAINING -> RELEASED` on the last termination.

**Client loss.** `entity.client.liveness_changed{to=lost}` ->
`apply_transition(event=CLIENT_LIVENESS_LOST)` -> engine returns
`{READY, IN_USE} -> CLIENT_LOST`; row's `pre_loss_state` saved in
`previous_state`. On `ALIVE`, engine consults the pod-definition compare
(via `3-static-pods.reconcile_on_recover`) and transitions to the saved
`previous_state` (report matched) or to `FAILED` (report diverged).

## Error Handling

- `InvalidPodTransition` (subclass of `SemanticError` — must NEVER be
  caught except at the subscriber boundary where it is translated into a
  `pychestrate_pod_lifecycle_invalid_transition` log event and dropped;
  the original exception is NOT swallowed to telemetry — it is rethrown
  after the log entry).
- `PodStateConflict` — raised on transition-cursor collision. Caught at
  service boundary; retried once against the refreshed row; on second
  collision emitted as `pychestrate_pod_lifecycle_race` and raised.
- `PodNotFound` — caught at REST boundary, translated to HTTP 404.
- `ConfigurationError` — raised at startup if the transition table is
  malformed (e.g., a missing terminal reachability check).
- Multiline error messages use `os.linesep.join([...])`:

```python
err_msg_lines = ["Invalid pod state transition."]
err_msg_lines.append("POD_ID:        {}".format(pod_id))
err_msg_lines.append("FROM_STATE:    {}".format(current_state.value))
err_msg_lines.append("EVENT:         {}".format(event_kind.value))
err_msg_lines.append("ALLOWED_FROM_CURRENT:")
for allowed in allowed_events:
    err_msg_lines.append("    - {}".format(allowed.value))

err_msg = os.linesep.join(err_msg_lines)
raise InvalidPodTransition(err_msg) from None
```

## Security Considerations

- Client-driven transitions are tied to the transport session's
  `client_id`; mismatch rejected before reaching `apply_transition`.
- Admin endpoints RBAC-gated; every admin transition audit-logged with
  actor, pod, from/to.
- REST endpoints rate-limited to prevent abuse (`:drain` 10/min/admin,
  `:force-release` 2/min/admin).

## Observability

Metrics:

- `pychestrate_pod_state_transitions_total{from,to,event}` — counter.
- `pychestrate_pod_state_gauge{state}` — gauge.
- `pychestrate_pod_drain_duration_seconds` — histogram.
- `pychestrate_pod_lifecycle_invalid_transition_total{from,event}` —
  counter.
- `pychestrate_pod_transition_latency_seconds` — histogram (ingest to
  publish).

Log events: `pychestrate_pod_state_changed`,
`pychestrate_pod_lifecycle_invalid_transition`,
`pychestrate_pod_lifecycle_race`.

Trace spans: `pod_lifecycle.transition`,
`pod_lifecycle.subscriber.<source>`.

## Open Questions

- Do we model `suspect` liveness as its own pod state, or collapse it
  into `in_use`/`ready` with only a client-side annotation? Lean toward
  collapse for Phase 2; revisit if operator feedback demands it.
- Where does the `failed` state auto-recover from? Likely manual-only
  (operator action transitions it back to `ready` after investigation);
  confirm with ops stakeholders before M2.
