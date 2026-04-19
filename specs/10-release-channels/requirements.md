# 10-release-channels — Requirements

## Introduction

`10-release-channels` is Pychestrate's release-train surface. It governs
how new versions of the Pychestrate *service* itself and the pod-client
*agent* are published, offered to consumers, staged through
percent-rollouts, and rolled back. Every release carries a signed
manifest and a channel pin (`stable`, `beta`, `canary`); consumers
(the service's own update path for auto-hosted installs, and the agent
running on a pod client) subscribe to a channel and receive the version
that channel currently advertises, gated by the rollout fraction.
Rollback is a first-class operation — not an emergent side effect of
deleting a release row — so every promotion has a symmetric demote and
an audit trail. The feature lives in Layer 10 — Operations and ships
in **Phase 10 — Public Surface & Extensibility Completion**. It sits
next to `3-agent-upgrade-channel` (which consumes it on the agent side)
and is consumed by the service's own self-update path. Extensibility is
one factory protocol: `release_channel_policy`, which decides *which
consumers get which version at what time* for a given channel. Per
AGENTS.md the caller-visible behavior parameters live on a
`ReleaseAspects` object — no decorators modify behavior.

## Requirements

### Requirement 1: Signed Release Manifest with Channel Pin

**User Story:** As a release engineer, I want every published release to
carry a signed manifest that pins its target channel and its artifact
digest, so that consumers can verify both *what* they are installing and
*why* they are eligible.

**Acceptance Criteria (EARS):**

1. WHEN a release is published via `publish_release(component,
   version, channel, artifact_uri, aspects)` THEN the system SHALL
   construct a `ReleaseManifest` containing
   `component ∈ {service, agent}`, `version` (SemVer), `channel ∈
   {stable, beta, canary}`, `artifact_sha256`, `artifact_uri`,
   `issued_at`, `issuer_key_id`, and a detached signature over the
   canonical serialization of those fields, and SHALL persist the
   manifest under `releases`.
2. IF the signing key declared by `issuer_key_id` is not present in
   `1-secrets-vault` or is marked expired THEN the system SHALL reject
   the publish call with `ReleaseSigningKeyUnavailableError`.
3. WHEN a consumer (service self-updater or agent via
   `3-agent-upgrade-channel`) retrieves a release manifest THEN the
   system SHALL include the detached signature and the public key
   fingerprint; the consumer SHALL refuse to install if verification
   fails.
4. WHERE a publish call targets `channel=stable` the system SHALL
   require the same `(component, version)` to have previously been
   published on `channel=beta` for at least `stable_bake_min_seconds`
   (default 86400 = 24h) unless the caller presents
   `system:release.bypass_bake` permission.

### Requirement 2: Percent Rollout and Staged Promotion Per Channel

**User Story:** As a release manager, I want to roll a new version to
5% of a channel, then 25%, then 100%, with a manual promote step
between stages, so that I can halt on regression.

**Acceptance Criteria (EARS):**

1. WHEN a release is published THEN the system SHALL start at
   `rollout_fraction = channel_policy.initial_fraction(channel)`
   (default 0.05 for `canary`, 0.25 for `beta`, 1.0 for `stable`).
2. WHEN an operator calls `promote_release(release_id, next_fraction,
   aspects)` THEN the system SHALL bump the fraction, publish
   `entity.release.promoted{release_id, from_fraction, to_fraction}`,
   and the configured `release_channel_policy` SHALL recompute the
   eligible consumer set.
3. WHILE a release is at `rollout_fraction < 1.0` AND a newer release
   on the *same* channel is published THEN the system SHALL refuse
   the newer publish with `ReleaseStageInProgressError` unless the
   caller presents `system:release.preempt` permission.
4. IF the observed failure rate across eligible consumers exceeds
   `stage_failure_threshold` (default 0.10) within a stage THEN the
   system SHALL auto-demote the release to `rollout_fraction = 0.0`,
   publish `entity.release.rolled_back{reason=auto_failure_threshold}`,
   and emit the `pychestrate.release.rolled_back` alert route.

### Requirement 3: First-Class Rollback Restores the Previous Channel State

**User Story:** As an on-call operator, I want a single `rollback`
action to demote the current release and re-promote the previous good
release on the same channel, so that recovery is one step, not
archaeology.

**Acceptance Criteria (EARS):**

1. WHEN an operator invokes `rollback_channel(component, channel,
   aspects)` THEN the system SHALL set the current release's
   `rollout_fraction = 0.0`, re-activate the previous release on that
   channel at its prior `rollout_fraction`, publish
   `entity.release.rolled_back{release_id, restored_release_id,
   reason}`, and SHALL NOT touch other channels for that component.
2. IF no prior release exists on the channel THEN the system SHALL
   raise `NoPriorReleaseError` and leave the channel state
   unchanged.
3. WHEN a rollback completes THEN the system SHALL run the rollback
   verification pass (each eligible consumer's next heartbeat reports
   the restored version or explicitly declines per pod pinning) and
   SHALL emit `pychestrate_release_rollback_verified`.
4. WHERE `aspects.include_cascading_agent_rollback = True` AND
   `component = service` THEN the system SHALL also trigger the most
   recent known-good agent release on the same channel to mitigate
   service/agent protocol drift.

### Requirement 4: Channel Policies Decide Eligibility via the Factory

**User Story:** As a release operator, I want to swap in a custom
eligibility policy (e.g., ring-based by region, tenant cohort, or
opted-in testers), so that rollouts match our operational reality
without forking the service.

**Acceptance Criteria (EARS):**

1. WHEN the runtime computes eligibility for a stage THEN the system
   SHALL select the registered `release_channel_policy` for the
   given `channel` via `E-extension-precedence` (lowest number
   wins) and call `compute_eligible_consumers(release, fraction,
   universe, aspects)` to get the `EligibleConsumerSet`.
2. IF a policy returns a set that includes consumers pinned to a
   different version THEN the system SHALL silently exclude those
   consumers and SHALL NOT report them as "held back".
3. WHERE two policies claim the same channel at equal `PRECEDENCE`
   THEN the system SHALL raise `ConfigurationError` at startup
   listing the colliding policy names.
4. WHERE a policy raises during `compute_eligible_consumers` THEN the
   system SHALL fall back to the default policy (hash-ring by consumer
   id), emit `entity.release.policy_fallback{from_policy, reason}`,
   and count the failure against
   `pychestrate_release_policy_errors_total`.

## Property-Based Test Requirements

### Property 1: Canary Abort Fully Restores Pre-Canary State

- **Invariant:** For any canary rollout of fraction `F` over any
  consumer universe `U`, if the canary aborts (auto-failure threshold
  exceeded or operator `rollback_channel`), the post-abort state
  (which release each consumer is eligible for at
  `rollout_fraction = 0.0`) equals the pre-canary state.
- **Generator:** hypothesis strategy producing random
  `(U, prior_release, canary_release, F, abort_event)` tuples with
  varied pin maps and channel policies.
- **Assertion:** for every consumer `c ∈ U`, the computed eligibility
  after abort equals the computed eligibility before the canary
  publish; the set of emitted `entity.release.rolled_back` events
  includes exactly one entry referring to `canary_release`.
- **Sample size:** 1000 generated cases.

### Property 2: Manifest Signature Is Required and Sufficient

- **Invariant:** For any published release, a consumer that verifies
  the signature against the issuer public key accepts the release;
  any mutation of the manifest fields, any substitution of the
  signature, or any use of an issuer key not currently trusted causes
  rejection.
- **Generator:** hypothesis strategy producing random valid manifests
  plus a catalog of mutations (flipped byte in `artifact_sha256`,
  altered `channel`, altered `version`, swapped signature,
  expired issuer key).
- **Assertion:** verification returns `accept` for untouched manifests
  and `reject` for every mutation; rejection reasons are stable and
  match the mutation kind.
- **Sample size:** 1000 generated cases.

### Property 3: Promotion Is Monotonic Within a Stage

- **Invariant:** For any sequence of `promote_release` calls on a
  single release without an intervening `rollback_channel`, the
  observed `rollout_fraction` is monotonically non-decreasing.
- **Generator:** hypothesis strategy producing random promotion
  sequences (possibly invalid ones with lower fractions) interleaved
  with other events.
- **Assertion:** `rollout_fraction` never decreases; calls requesting
  a lower fraction raise `SemanticError` and do not mutate state.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance / Rollout Shape):**
  - **Canary initial fraction:** 0.05.
  - **Beta initial fraction:** 0.25.
  - **Stable initial fraction:** 1.0.
  - **Canary bake time (minimum before promotion to beta):** 3600
    seconds (1h).
  - **Beta bake time (minimum before promotion to stable):** 86400
    seconds (24h).
  - **Stage failure threshold (auto-demote trigger):** 10% failure
    rate across eligible consumers in a stage.
  - **Manifest lookup latency:** p99 <= 50 ms.
  - **Rollback-to-effective latency (service restart included):**
    p99 <= 120 seconds.
- **NFR-2 (Security):** All manifests signed (Ed25519) with a release
  signing key held in `1-secrets-vault`, loaded only on the dedicated
  signer process context (not the REST handler). Public keys ship with
  the agent binary and the service image; key rotation is its own
  audited operation. Every release action hits `1-audit-log`. RBAC:
  `system:release.read`, `system:release.publish`,
  `system:release.promote`, `system:release.rollback`,
  `system:release.preempt`, `system:release.bypass_bake`.
- **NFR-3 (Observability):** metrics
  `pychestrate_release_publishes_total{component,channel,outcome}`,
  `pychestrate_release_promotions_total{component,channel}`,
  `pychestrate_release_rollbacks_total{component,channel,reason}`,
  `pychestrate_release_rollout_fraction_gauge{component,channel,release_id}`,
  `pychestrate_release_consumer_failure_rate{component,channel,release_id}`,
  `pychestrate_release_policy_errors_total{policy,channel}`,
  `pychestrate_release_manifest_verification_failures_total{reason}`;
  log events `release.published`, `release.promoted`,
  `release.rolled_back`, `release.policy_fallback`,
  `release.manifest.verified`, `release.manifest.rejected`; trace spans
  `release.publish`, `release.promote`, `release.rollback`,
  `release.policy.evaluate`, `release.manifest.sign`,
  `release.manifest.verify`.
- **NFR-4 (Reliability):** Release state is durable; restart resumes
  in-flight stages from the last recorded eligibility snapshot. The
  previous good release on each channel is retained for at least the
  configured rollback window (default 14 days). Verification failures
  never block *other* channels.

## Out of Scope

- Agent-side apply mechanics (owned by `3-agent-upgrade-channel` and
  the agent binary itself).
- Service-side cold-deploy (owned by the deployment infra: systemd /
  container orchestrator); this feature coordinates *which* version
  those consumers should converge to.
- Feature flags (owned by `1-feature-flags`).
- Member / device firmware updates (not in Pychestrate's remit).

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`,
  `1-secrets-vault` (signing key storage), `1-audit-log`, `1-rbac`,
  `E-extension-host`, `E-factory-protocols`.
- **Depended on by:** `3-agent-upgrade-channel` (the agent-side
  rollout layer consumes the `service_release` and `agent_release`
  manifests from this feature), the service's self-update path.
- **Extension points exposed:** `factory: release_channel_policy` —
  hash-ring by consumer id (default in-tree), ring-based by region,
  tenant-cohort, opt-in testers, custom. Reference implementation
  `HashRingChannelPolicy` ships in-tree at `PRECEDENCE = 1000`. See
  implementation-plan.md Layer 10 and Phase 10.
