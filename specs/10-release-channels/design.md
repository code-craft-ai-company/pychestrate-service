# 10-release-channels — Design

## Architecture

`10-release-channels` lives under
`source/site/ccai/pychestrate/webservice/ops/release/`. It owns the
`releases` table and the channel-state table, the signing/verification
surface (via a dedicated signer subprocess that holds the signing key
far from REST handlers), the stage machine (initial → promoted →
rolled_back / completed), and a policy router that looks up the
registered `release_channel_policy` for the channel. Agents that update
in the field talk to `3-agent-upgrade-channel`; that feature consults
this one for the canonical manifest and eligibility. The service's own
self-update path also consults this feature. Authoritative state for
"which release is currently advertised on channel C for component X" is
the `channel_state` row; everything else reads from it. The feature
ships in **Phase 10 — Public Surface & Extensibility Completion**, after
`8-plugin-api` stabilizes, so its REST surface can safely appear on the
public API.

## Data Model

`releases` — one row per published (component, version, channel):

- `release_id: UUID` — PK.
- `component: ReleaseComponent` — `{SERVICE, AGENT}`.
- `version: str` — SemVer.
- `channel: ReleaseChannel` — `{STABLE, BETA, CANARY}`.
- `artifact_uri: str` — opaque to this feature; the consumer fetches
  via the upgrade artifact source or the service's own update path.
- `artifact_sha256: str`.
- `manifest_bytes: bytes` — canonical serialization, signed.
- `signature: bytes` — detached Ed25519 signature over
  `manifest_bytes`.
- `issuer_key_id: str`.
- `issued_at: datetime`, `issued_by: UUID`.
- `status: ReleaseStatus` — `{ACTIVE, SUPERSEDED, ROLLED_BACK,
  WITHDRAWN}`.
- `rollout_fraction: float` — 0.0 ≤ f ≤ 1.0.
- `stage_started_at: datetime`.
- `previous_release_id: Optional[UUID]` — the release this one
  displaced on the channel; used for first-class rollback.
- Uniqueness: `(component, version, channel)`.

`channel_state` — authoritative "what is on the channel now":

- `component: ReleaseComponent`, `channel: ReleaseChannel` — composite PK.
- `current_release_id: Optional[UUID]` — FK into `releases`.
- `previous_release_id: Optional[UUID]` — FK into `releases`; used by
  `rollback_channel`.
- `last_promotion_at: Optional[datetime]`.
- `last_rollback_at: Optional[datetime]`.

`release_stage_events` — append-only stage log:

- `event_id: UUID`, `release_id: UUID`, `kind: StageEventKind`
  (`{PUBLISHED, PROMOTED, DEMOTED, ROLLED_BACK, AUTO_HALTED}`),
  `from_fraction: Optional[float]`, `to_fraction: Optional[float]`,
  `reason: Optional[str]`, `actor_user_id: Optional[UUID]`,
  `occurred_at: datetime`.

`consumer_outcomes` — rolled-up view of consumer reports per release:

- `release_id: UUID`, `consumer_id: str`, `component: ReleaseComponent`,
  `outcome: ConsumerOutcome` (`{SUCCESS, FAILURE, DEFERRED}`),
  `reason: Optional[str]`, `reported_at: datetime`.
- Composite PK `(release_id, consumer_id)`.

`trusted_issuer_keys` — valid public keys for manifest verification:

- `issuer_key_id: str` — PK.
- `public_key_bytes: bytes` — Ed25519 public key.
- `valid_from: datetime`, `valid_until: Optional[datetime]`.
- `replaced_by: Optional[str]` — for rotation lineage.

Indexes: `releases(component, channel, status)`,
`releases(issued_at DESC)`,
`consumer_outcomes(release_id, outcome, reported_at DESC)`.

## Interfaces

### Public API

REST routes under `/api/v1/ops/release/`:

- `POST /releases` — publish `{component, version, channel,
  artifact_uri, artifact_sha256}`; signer subprocess produces the
  signature.
- `GET /releases` — list with filter `{component, channel, status}`.
- `GET /releases/{release_id}` — full manifest + signature.
- `POST /releases/{release_id}/promote` — `{next_fraction}`.
- `POST /channels/{component}/{channel}/rollback` —
  `{include_cascading_agent_rollback}`.
- `GET /channels/{component}/{channel}` — current + previous release.
- `GET /manifests/{component}/{channel}/current` — consumer-facing
  endpoint: returns manifest + signature + public key fingerprint.
- `POST /consumers/{consumer_id}/outcomes` — consumer posts
  `{release_id, outcome, reason}`; used to drive the stage failure
  threshold.

CLI (under `8-cli`):

- `pychestrate release publish --component <service|agent> --version
  <semver> --channel <canary|beta|stable> --artifact <uri>`
- `pychestrate release promote <release_id> --to <fraction>`
- `pychestrate release rollback --component <c> --channel <ch>
  [--cascade-agent]`
- `pychestrate release list [--component=…] [--channel=…]`

### Internal API

Module
`ccai.pychestrate.webservice.ops.release.release_service`:

```python
@dataclass(frozen=True)
class ReleaseAspects:
    """
        Caller-supplied behavior knobs — AGENTS.md "Aspects" pattern.

        :param sync: If True, wait for signer + publish to settle before returning.
        :param timeout_seconds: Per-call deadline (signer, verify, policy).
        :param include_cascading_agent_rollback: On service rollback, also
                                                 roll agent on same channel.
        :param bypass_bake_window: Honor only when caller has
                                   system:release.bypass_bake permission.
        :param log_verbosity: NORMAL | DEBUG — never logs private key bytes.
    """
    sync: bool
    timeout_seconds: float
    include_cascading_agent_rollback: bool
    bypass_bake_window: bool
    log_verbosity: LogVerbosity


def build_default_release_aspects() -> ReleaseAspects:
    """
        Construct the default aspects for routine release operations.

        Per AGENTS.md we never use mutable defaults; callers call this
        builder explicitly.
    """
    rtnval = ReleaseAspects(
        sync=True,
        timeout_seconds=30.0,
        include_cascading_agent_rollback=False,
        bypass_bake_window=False,
        log_verbosity=LogVerbosity.NORMAL
    )
    return rtnval


def publish_release(
        *,
        principal: AuthPrincipal,
        component: ReleaseComponent,
        version: str,
        channel: ReleaseChannel,
        artifact_uri: str,
        artifact_sha256: str,
        aspects: ReleaseAspects
    ) -> ReleaseRecord:
    """
        Create a signed release manifest on a channel at its initial fraction.

        :raises: ReleaseSigningKeyUnavailableError,
                 ReleaseStageInProgressError, ReleaseBakeNotMetError,
                 SemanticError
    """
    ...


def promote_release(
        *,
        principal: AuthPrincipal,
        release_id: UUID,
        next_fraction: float,
        aspects: ReleaseAspects
    ) -> ReleaseRecord:
    """
        Bump a release's rollout fraction on its channel.

        :raises: SemanticError (non-monotonic fraction),
                 ReleaseNotActiveError
    """
    ...


def rollback_channel(
        *,
        principal: AuthPrincipal,
        component: ReleaseComponent,
        channel: ReleaseChannel,
        reason: str,
        aspects: ReleaseAspects
    ) -> RollbackRecord:
    """
        Demote current, re-activate previous on the channel.

        :raises: NoPriorReleaseError, SemanticError
    """
    ...


def record_consumer_outcome(
        *,
        consumer_id: str,
        release_id: UUID,
        outcome: ConsumerOutcome,
        reason: Optional[str]
    ) -> None:
    """
        Ingest a consumer's outcome report; may trigger auto-demote.
    """
    rtnval = None
    return rtnval
```

Module
`ccai.pychestrate.webservice.ops.release.manifest_signer`:

```python
def sign_manifest(
        *,
        manifest_bytes: bytes,
        issuer_key_id: str,
        aspects: ReleaseAspects
    ) -> bytes:
    """
        Produce a detached Ed25519 signature; runs in a dedicated
        signer subprocess that alone holds the private key.

        :raises: ReleaseSigningKeyUnavailableError
    """
    ...


def verify_manifest(
        *,
        manifest_bytes: bytes,
        signature: bytes,
        issuer_key_id: str
    ) -> ManifestVerificationResult:
    """
        Verify a manifest + signature against the trusted issuer keys.
    """
    ...
```

Module
`ccai.pychestrate.webservice.ops.release.policy_router`:

```python
def resolve_policy(
        *,
        channel: ReleaseChannel
    ) -> ReleaseChannelPolicyProtocol:
    """
        Look up the registered policy with the lowest PRECEDENCE for the
        channel; fall back to HashRingChannelPolicy on startup collision.

        :raises: ConfigurationError on equal-precedence collision at startup.
    """
    ...
```

### Extension Surface

Factory protocol `release_channel_policy` declared in
`ccai.pychestrate.webservice.ops.release.factories.release_channel_policy`:

```python
class ReleaseChannelPolicyProtocol(FactoryProtocolBase):
    factory_protocol_name: str = "release_channel_policy"
    protocol_schema_version: int = 1

    @classmethod
    def channel(cls) -> ReleaseChannel:
        """Which channel this policy claims."""
        ...

    @classmethod
    def initial_fraction(cls, *, channel: ReleaseChannel) -> float:
        ...

    @classmethod
    def compute_eligible_consumers(
            cls,
            *,
            release: ReleaseRecord,
            fraction: float,
            universe: list[ConsumerDescriptor],
            aspects: ReleaseAspects
        ) -> EligibleConsumerSet:
        """
            Return the set of consumers eligible for this release at this fraction.
        """
        ...

    @classmethod
    def observe_outcome(
            cls,
            *,
            release: ReleaseRecord,
            consumer_id: str,
            outcome: ConsumerOutcome
        ) -> None:
        """Optional hook — default is no-op; policies may use it to update sticky
        ring assignments or cohort caches."""
        ...
```

Reference implementation: `HashRingChannelPolicy` at
`PRECEDENCE = 1000` claiming every channel (so it is the default
selected when no override exists). It uses
`HMAC-SHA256(consumer_id, release_id)` modulo 10000 and selects the
lowest-ranked `fraction * 10000` consumers. Alternatives shipped as
in-tree guidance skeletons: `RingBasedChannelPolicy` (by region),
`TenantCohortChannelPolicy`.

### Events Emitted

- `entity.release.published` — `{release_id, component, channel,
  version, artifact_sha256, issuer_key_id, issued_at, issued_by}`
- `entity.release.promoted` — `{release_id, component, channel,
  from_fraction, to_fraction, actor_user_id, at}`
- `entity.release.rolled_back` — `{release_id, restored_release_id,
  component, channel, reason, actor_user_id, at}`
- `entity.release.canary_started` — `{release_id, component, channel,
  fraction, at}`
- `entity.release.policy_fallback` — `{from_policy, reason, channel,
  at}`
- `entity.release.manifest.rejected` — `{release_id, reason, at}`

### Events Consumed

- `entity.client.heartbeat` — for agent-component releases, a
  heartbeat carries the current agent version; the service updates
  `consumer_outcomes` and may trigger auto-demote.
- `entity.audit.sink.unhealthy` — trips write-blocked flag on the
  publish / promote / rollback paths.
- `entity.secret.rotated` where `secret_ref = system:release.signing_key`
  — rotates the active signing key and records the new
  `issuer_key_id`.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/ops/release/
    __init__.py
    release_service.py             # publish / promote / rollback / record_outcome
    release_aspects.py             # ReleaseAspects dataclass + default builder
    manifest_signer.py             # subprocess IPC to the signer process
    manifest_signer_worker.py      # the dedicated signer subprocess entry point
    manifest_verifier.py           # standalone verification (used by service + agent)
    policy_router.py               # registry lookup + fallback
    stage_machine.py               # state transitions for releases
    auto_demote.py                 # failure-threshold watcher
    channel_state.py               # authoritative channel pointer
    factories/
        release_channel_policy.py  # FactoryProtocolBase
        hash_ring_policy.py        # HashRingChannelPolicy
        ring_based_policy.py       # RingBasedChannelPolicy (guidance)
        tenant_cohort_policy.py    # TenantCohortChannelPolicy (guidance)
    models.py
    restapi/
        v1/
            release_controller.py
            manifest_controller.py
            consumer_outcome_controller.py
    events.py
    exceptions.py
```

## Key Flows

**Publish + canary start:**

1. Release engineer calls `release_service.publish_release(component=AGENT,
   version="1.42.0", channel=CANARY, artifact_uri=..., artifact_sha256=...)`
   with `ReleaseAspects(sync=True, ...)`.
2. The service constructs the canonical `manifest_bytes`, calls the
   signer subprocess via `manifest_signer.sign_manifest`, and the
   subprocess returns a detached signature using the private key loaded
   only in that subprocess (from `1-secrets-vault` at startup).
3. The service inserts a `releases` row at
   `rollout_fraction = channel_policy.initial_fraction(CANARY)` = 0.05,
   updates `channel_state.current_release_id`, moves the previous
   release to `previous_release_id`, emits
   `entity.release.published` and `entity.release.canary_started`.
4. `3-agent-upgrade-channel` consumes the event and begins offering the
   release to the eligible consumer subset computed by the registered
   `release_channel_policy`.

**Promote from canary to beta:**

1. Release manager calls `promote_release(release_id,
   next_fraction=0.25)` — the service enforces monotonicity
   (SemanticError if lower), enforces the canary bake (rejects if
   `now - stage_started_at < canary_bake_min_seconds` unless
   `bypass_bake_window=True` with the corresponding RBAC).
2. The service updates `rollout_fraction = 0.25`, records a
   `release_stage_events` row, emits `entity.release.promoted`.
3. Policy router re-evaluates eligibility for consumers reporting
   heartbeats; new eligible consumers receive the updated manifest
   from `GET /manifests/.../current`.

**Rollback:**

1. On-call calls `rollback_channel(component=SERVICE,
   channel=STABLE, reason="regression:crash-loop")` with
   `ReleaseAspects(include_cascading_agent_rollback=True)`.
2. The service sets `current.rollout_fraction = 0.0`, swaps
   `channel_state.current_release_id` to `previous_release_id`,
   sets the restored release's fraction to its prior value, writes
   `release_stage_events`, and emits `entity.release.rolled_back`.
3. Because cascading is on, the same flow runs for
   `component=AGENT, channel=STABLE`, mitigating protocol drift.
4. The verifier watches the next heartbeat/outcome batch; consumers
   reporting the restored version flip
   `pychestrate_release_rollback_verified` to 1.0; failures raise the
   metric.

**Auto-demote on stage failure:**

1. `auto_demote` subscribes to the internal outcome stream; when the
   rolling failure fraction across eligible consumers for a release
   exceeds 0.10, it issues an internal `rollback_channel` call with
   `reason="auto_failure_threshold"` and fires the
   `pychestrate.release.rolled_back` alert.

## Error Handling

Failure modes:

- `ReleaseSigningKeyUnavailableError` — HTTP 503; the signer
  subprocess is down or key is expired. Publish fails closed.
- `ReleaseStageInProgressError` — HTTP 409; preempting an in-flight
  stage requires `system:release.preempt`.
- `ReleaseBakeNotMetError` — HTTP 409; the bake window has not
  elapsed. Bypass requires `system:release.bypass_bake`.
- `NoPriorReleaseError` — HTTP 409 on rollback when no prior release
  exists.
- `ReleaseNotActiveError` — HTTP 409 promoting a superseded /
  rolled-back release.
- `ManifestVerificationError` — HTTP 400 when a consumer posts an
  outcome referring to an unverifiable manifest.
- `ConfigurationError` — startup: two policies claim the same channel
  at equal precedence; no trusted issuer key loaded.
- `SemanticError` — illegal fraction (<0 or >1), non-monotonic
  promotion, unknown channel; NEVER caught.

Multi-line error messages use the AGENTS.md pattern:

```python
err_msg_lines = ["Release publish rejected: bake window not satisfied."]
err_msg_lines.append("COMPONENT: {}".format(component.name))
err_msg_lines.append("VERSION: {}".format(version))
err_msg_lines.append("CHANNEL: {}".format(channel.name))
err_msg_lines.append("BAKE_REQUIRED: {} seconds".format(bake_required))
err_msg_lines.append("BAKE_OBSERVED: {} seconds".format(bake_observed))
err_msg = os.linesep.join(err_msg_lines)
raise ReleaseBakeNotMetError(err_msg) from None
```

The signer subprocess never logs the private key, and its stderr is
piped through a redactor that scrubs any base64-shaped string matching
the key's length class.

## Security Considerations

- The release signing key lives in `1-secrets-vault` under
  `system:release.signing_key` and is loaded ONLY by the signer
  subprocess, not by the REST handler process.
- Manifests are Ed25519-signed; verification uses
  `trusted_issuer_keys` which can carry multiple active keys during
  rotation; `replaced_by` chains the lineage.
- RBAC permissions: `system:release.read`, `system:release.publish`,
  `system:release.promote`, `system:release.rollback`,
  `system:release.preempt`, `system:release.bypass_bake`. Two
  permissions — `rollback` and `preempt` — are deliberately separate
  so roles can grant emergency rollback without preempt power.
- Every entry point writes to `1-audit-log` with the canonical
  manifest fields and the actor; failed audit writes fail the
  operation closed.
- The consumer-outcome endpoint is authenticated by the consumer's
  mTLS identity (for agents, via `3-client-agent-protocol`; for the
  service self-updater, via an internal service-to-service token).
- Rate limiting on `POST /consumers/{id}/outcomes` per consumer id so
  a compromised client cannot fabricate a failure storm that forces
  auto-rollback across the fleet.
- `E-extension-sandbox` capability required for a
  `release_channel_policy` extension: `read:releases`,
  `read:consumers`. Policies are not granted any write capability.

## Observability

Metrics (per NFR-3):
`pychestrate_release_publishes_total{component,channel,outcome}`,
`pychestrate_release_promotions_total{component,channel}`,
`pychestrate_release_rollbacks_total{component,channel,reason}`,
`pychestrate_release_rollout_fraction_gauge{component,channel,release_id}`,
`pychestrate_release_consumer_failure_rate{component,channel,release_id}`,
`pychestrate_release_policy_errors_total{policy,channel}`,
`pychestrate_release_manifest_verification_failures_total{reason}`,
`pychestrate_release_rollback_verified{component,channel,release_id}` (gauge).

Log events: `release.published`, `release.promoted`,
`release.rolled_back`, `release.policy_fallback`,
`release.manifest.verified`, `release.manifest.rejected`,
`release.signer.unavailable`, `release.stage.bake_not_met`.

Trace spans: `release.publish`, `release.promote`,
`release.rollback`, `release.policy.evaluate`,
`release.manifest.sign`, `release.manifest.verify`,
`release.auto_demote`.

## Open Questions

- Do we support per-tenant channel overrides (tenant A on beta, tenant
  B on stable for the same component)? Tentative: yes via the
  `TenantCohortChannelPolicy` path; deferred to 10.1.
- How do we model service-side "frozen" channels where stable never
  auto-advances? Tentative: a `channel_state.frozen` bool with
  `system:release.unfreeze` RBAC.
- Should the signer subprocess live on the same host as the service
  or on a dedicated signer host? Initial: same host with strict
  seccomp; revisit if / when an HSM becomes available.
- Does `include_cascading_agent_rollback` need per-channel policy
  (e.g., do it for stable, not canary)? Tentative: yes, add a
  channel-scoped flag in 10.1.
