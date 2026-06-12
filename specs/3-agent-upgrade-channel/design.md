# 3-agent-upgrade-channel — Design

## Architecture

The Agent Upgrade Channel lives at
`source/site/ccai/pychestrate/webservice/clients/upgrades/`. It is
two things:

1. **A rollout-orchestrator** — a small state machine that walks a
   rollout through a sequence of stages, computing the target client
   set per stage through the `rollout_policy` factory, and publishing
   offers on the transport.
2. **An outcome collector** — a subscriber that consumes
   `entity.client.upgrade_outcome` events pushed by the client and
   updates per-stage rolling statistics, triggering auto-halt if the
   failure rate crosses the threshold.

Artifact bytes are not handled by Pychestrate directly; they are served
through the `upgrade_artifact_source` factory, which may return a
redirect URL (object store, signed HTTP URL, GitHub releases URL) or a
byte stream. The announcement always includes a signed manifest so the
client can verify integrity regardless of the source. Authoritative state:
the `agent_rollout`, `agent_rollout_stage`, `agent_upgrade_offer`, and
`agent_pod_pin` tables. Pod-scoped pinning is the feature's own concept
(a pin row references `pod_id` and an explicit version); rollout offers
consult pins before announcement.

## Data Model

```
agent_rollout
    rollout_id:       UUID        primary key
    version:          str         not null   -- e.g. "2.4.1"
    artifact_source:  str         not null   -- factory name
    artifact_ref:     str         not null   -- source-specific ref (URL, key, etc.)
    artifact_sha256:  str         not null
    signature:        str         not null   -- over version+sha256+issued_at
    issued_at:        datetime
    state:            RolloutState not null
    created_by:       UUID
    halted_reason:    str         nullable
    (version) index

agent_rollout_stage
    stage_id:         UUID        primary key
    rollout_id:       UUID        fk -> agent_rollout
    stage_index:      int
    rollout_policy:   str         not null   -- factory name
    policy_params:    jsonb
    target_size:      int         not null
    state:            StageState  not null
    started_at:       datetime    nullable
    ended_at:         datetime    nullable
    success_count:    int         not null default 0
    failure_count:    int         not null default 0
    deferred_count:   int         not null default 0
    (rollout_id, stage_index) unique

agent_upgrade_offer
    offer_id:         UUID        primary key
    stage_id:         UUID
    client_id:        UUID
    version:          str
    offered_at:       datetime
    outcome:          OfferOutcome nullable
    outcome_at:       datetime    nullable
    outcome_detail:   jsonb       nullable
    (stage_id, client_id) unique

agent_pod_pin
    pod_id:           UUID        primary key
    pinned_version:   str         not null
    set_by:           UUID
    set_at:           datetime
    reason:           str         nullable
```

Enumerations (`clients/upgrades/enums.py`):

```
class RolloutState(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    HALTED = "halted"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class StageState(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    HELD = "held"
    COMPLETED = "completed"
    HALTED = "halted"


class OfferOutcome(str, Enum):
    OFFERED = "offered"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEFERRED = "deferred"
    EXPIRED = "expired"
    SHA256_MISMATCH = "sha256_mismatch"
    FETCH_FAILED = "fetch_failed"
```

## Interfaces

### Public API

REST (RBAC `agent.rollout.*`):

- `POST /api/v1/agent-rollouts` — draft rollout.
- `POST /api/v1/agent-rollouts/{rollout_id}:start` — move to ACTIVE +
  start stage 0.
- `POST /api/v1/agent-rollouts/{rollout_id}:promote` — end current stage
  and start the next.
- `POST /api/v1/agent-rollouts/{rollout_id}:halt` — manual halt.
- `POST /api/v1/agent-rollouts/{rollout_id}:resume` — resume from halt.
- `GET /api/v1/agent-rollouts/{rollout_id}` — state + per-stage counts.
- `GET /api/v1/agent-rollouts` — list.
- `PUT /api/v1/pods/{pod_id}/agent-pin` — pin a pod to a version.
- `DELETE /api/v1/pods/{pod_id}/agent-pin` — unpin.

### Internal API

```python
def start_rollout(
    *,
    rollout_id: UUID,
    actor: UUID,
) -> RolloutState:
    ...


def promote_rollout(
    *,
    rollout_id: UUID,
    actor: UUID,
) -> StageState:
    ...


def halt_rollout(
    *,
    rollout_id: UUID,
    actor: UUID,
    reason: str,
) -> RolloutState:
    ...


def compute_offer_set(
    *,
    stage: RolloutStage,
    fleet_snapshot: FleetSnapshot,
    pin_map: Mapping[UUID, str],
) -> List[UUID]:
    ...


def record_offer_outcome(
    *,
    offer_id: UUID,
    outcome: OfferOutcome,
    detail: Mapping[str, Any],
) -> None:
    ...


def set_pod_pin(
    *,
    pod_id: UUID,
    version: str,
    actor: UUID,
    reason: str,
) -> None:
    ...
```

### Extension Surface

```python
class UpgradeArtifactSourceProtocol(FactoryProtocolBase):
    factory_protocol_name = "upgrade_artifact_source"
    protocol_schema_version = 1

    @classmethod
    def describe(cls, *, artifact_ref: str) -> ArtifactDescriptor:
        ...

    @classmethod
    def fetch_stream(cls, *, artifact_ref: str) -> AsyncIterator[bytes]:
        ...


class RolloutPolicyProtocol(FactoryProtocolBase):
    factory_protocol_name = "rollout_policy"
    protocol_schema_version = 1

    @classmethod
    def compute_target_set(
        cls,
        *,
        stage: RolloutStage,
        fleet: FleetSnapshot,
        params: Mapping[str, Any],
    ) -> Sequence[UUID]:
        ...
```

Reference implementations (in-tree):

- `ObjectStoreArtifactSource` (`PRECEDENCE=100`) — backed by
  `0-object-store` drivers.
- `GithubReleasesArtifactSource` (`PRECEDENCE=110`).
- `PercentRolloutPolicy` (`PRECEDENCE=100`) — `params={"percent": int}`.
- `RingRolloutPolicy` (`PRECEDENCE=110`) — `params={"rings": [str,
  str, ...]}`, clients grouped by label.
- `CanaryFleetRolloutPolicy` (`PRECEDENCE=120`) — `params={"canary_ids":
  [UUID]}` first stage, then all eligible.

### Events Emitted

```
entity.rollout.drafted         { rollout_id, version }
entity.rollout.started         { rollout_id }
entity.rollout.stage_started   { rollout_id, stage_index, target_size }
entity.rollout.stage_completed { rollout_id, stage_index }
entity.rollout.halted          { rollout_id, reason }
entity.rollout.resumed         { rollout_id }
entity.rollout.completed       { rollout_id }
entity.upgrade.offered         { offer_id, client_id, version }
entity.upgrade.succeeded       { offer_id, client_id, version }
entity.upgrade.failed          { offer_id, client_id, reason }
entity.upgrade.deferred        { offer_id, client_id, reason }
entity.upgrade.integrity_failed{ offer_id, client_id }
```

### Events Consumed

- `entity.client.heartbeat` — detects `last_agent_version` post-upgrade.
- `entity.pod.state_changed` — deferred-offer re-evaluation when a pod
  returns to `ready`.
- `entity.client.upgrade_outcome` — transport-side report.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/clients/upgrades/
    __init__.py
    enums.py
    dtos.py                      -- RolloutStage, FleetSnapshot,
                                    OfferOutcomeReport, ArtifactDescriptor
    service.py                   -- start/promote/halt/resume/record_outcome
    orchestrator.py              -- rollout state-machine driver
    pins.py                      -- set_pod_pin, get_pin_map
    signer.py                    -- vault-backed release-key signing adapter
    subscribers.py               -- outcome + pod-state re-eval subscribers
    repository.py
    rest.py
    metrics.py

source/site/ccai/pychestrate/factories/upgrade_artifact_source/
    object_store.py             -- PRECEDENCE=100
    github_releases.py          -- PRECEDENCE=110

source/site/ccai/pychestrate/factories/rollout_policy/
    percent.py                  -- PRECEDENCE=100
    ring.py                     -- PRECEDENCE=110
    canary_fleet.py             -- PRECEDENCE=120
```

## Key Flows

**Drafting and starting a rollout.** Admin `POST /agent-rollouts` ->
signer (via `1-secrets-vault` short-lived context) signs the manifest ->
row persisted at `state=DRAFT`. Admin `:start` -> orchestrator loads
stage 0, calls `compute_offer_set`, writes `agent_upgrade_offer` rows,
emits `entity.upgrade.offered` per row. Transport layer writes an
`UpgradeOfferFrame` to each client's session.

**Client upgrades.** Client receives offer, verifies signature + sha256
against the signed manifest, calls
`upgrade_artifact_source.fetch_stream` (or follows redirect), applies
upgrade, restarts, reports outcome via `UpgradeOutcomeFrame`. Subscriber
->`record_offer_outcome` -> updates stage counters -> evaluates threshold.

**In-use pod deferral.** Offer arrives at transport; transport checks
local pod state (cached from `3-pod-lifecycle`); if `in_use` the offer
is queued client-side with `offer_ttl_seconds`. On pod return to
`ready`, client processes the queued offer.

**Pin.** Admin `PUT /pods/{pod_id}/agent-pin` -> `set_pod_pin` writes
row, audit-logged. Next `compute_offer_set` call consults
`get_pin_map` and excludes pinned clients whose pin != announced version.

**Auto-halt.** After each outcome, orchestrator recomputes stage
failure rate; if over `stage_failure_threshold`, sets `state=HALTED`
and `halted_reason="failure_threshold_exceeded"`, stops new offers.

## Error Handling

- `ArtifactSourceUnavailable` — caught in orchestrator; translated to
  `entity.rollout.halted{reason="artifact_unavailable"}` with the
  source name appended.
- `IntegrityFailed` — caught from outcome subscriber; rollout halted
  for the affected version; operator-alert fires.
- `InvalidRolloutTransition` — subclass of `SemanticError`; never
  caught; surfaced in logs as a bug indicator.
- `PinConflict` — raised when a pin is set to a version that is
  unknown to any rollout (defensive check); translated to HTTP 409.
- `ConfigurationError` — raised at startup if the release-signing key
  is unreadable or required factories are missing.
- Multiline error messages per AGENTS.md.

## Security Considerations

- Release-signing key stored in `1-secrets-vault`; the `signer` module
  holds a short-lived context per signing call; the service refuses to
  start if the key fingerprint does not match
  `expected_release_signer_fingerprint` in configuration.
- Artifact manifest signed with the above key; clients pin the signer
  fingerprint at install time.
- RBAC: `agent.rollout.read`, `agent.rollout.write`,
  `agent.rollout.admin`, `agent.pin.write`.
- Every rollout state change and pin change audit-logged.
- Artifact byte-stream transferred over the existing mTLS transport if
  the source is Pychestrate-local; external sources must present their
  own TLS certificate (validated client-side).

## Observability

Metrics:

- `pychestrate_client_upgrade_offers_total{outcome}` — counter.
- `pychestrate_client_upgrade_stage_gauge{stage,state}` — gauge.
- `pychestrate_client_upgrade_failure_rate{stage}` — gauge (ratio).
- `pychestrate_client_upgrade_artifact_fetch_seconds` — histogram.
- `pychestrate_client_upgrade_pinned_clients_gauge` — gauge.

Log events: `pychestrate_client_upgrade_announced`,
`pychestrate_client_upgrade_succeeded`,
`pychestrate_client_upgrade_failed`,
`pychestrate_client_upgrade_halted`,
`pychestrate_client_upgrade_pin_set`.

Trace spans: `agent_upgrade.announce`, `agent_upgrade.fetch`,
`agent_upgrade.collect_outcome`, `agent_upgrade.auto_halt_check`.

## Open Questions

- Support simultaneous multiple-version rollouts (e.g., new major vs
  LTS)? Lean yes; only-one-active-per-version constraint. Confirm by
  end of M2.
- How do we gate the very first ever agent install for a new enrollment?
  Likely separate from this feature — the enrollment flow itself
  provisions the current "release channel" default. Revisit with
  `10-release-channels`.
