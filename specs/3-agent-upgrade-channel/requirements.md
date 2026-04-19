# 3-agent-upgrade-channel — Requirements

## Introduction

The Agent Upgrade Channel is Pychestrate's mechanism for rolling out new
versions of the pod client agent: announcing a target version to a staged
set of clients, serving the upgrade artifact, gating by per-pod pinning
policy, and observing the rollout's health. It lives in Layer 3 and ships
in Phase 10, after `10-release-channels` and the plugin-API surface have
landed. Per the architectural ground rules, the client is the only thing
that talks to Pychestrate, so the upgrade path is client-agent-only — pod
members are never upgraded through this surface. The rollout is
client-pull, not push: Pychestrate announces availability on the
transport, the client fetches and applies the artifact on its own
schedule (respecting pod lifecycle — never upgrade an `in_use` pod
mid-run). Two factory protocols drive extensibility:
`upgrade_artifact_source` (how to fetch artifacts: object store, GitHub
releases, internal artifact registry) and `rollout_policy` (which clients
get a version at a given time: percent rollout, ring-based, per-pod pin
overrides).

## Requirements

### Requirement 1: Upgrade announcements respect per-pod pinning

**User Story:** As an operator running a production pod on a known-good
agent version, I want to pin that pod to that version, so that a cluster-
wide rollout never touches it until I say so.

**Acceptance Criteria (EARS):**

1. WHEN a rollout announcement is published THEN the system SHALL consult
   each client's pod's `pinned_agent_version`; IF pinned and the pin does
   not match the announced version THEN the system SHALL NOT offer the
   upgrade to that client.
2. IF an admin updates a pin while a rollout is in progress THEN
   subsequent offers SHALL honor the new pin immediately; already-offered
   clients SHALL be allowed to complete but SHALL NOT be offered again
   for a version newer than the pin.
3. WHERE a pod is in `state=in_use` the system SHALL defer any offer
   until the pod returns to `state=ready`; IF the pod never returns to
   `ready` within `offer_ttl_seconds` THEN the offer SHALL expire
   without being delivered.
4. WHEN a client reports a successful upgrade THEN the system SHALL
   update `client.last_agent_version` via `3-client-registry`.

### Requirement 2: Rollout policy controls the offered set per batch

**User Story:** As a release manager, I want to run a staged rollout
(5% -> 25% -> 100%) with manual promotion between stages, so that I can
halt on the first sign of regression.

**Acceptance Criteria (EARS):**

1. WHEN a rollout enters a new stage THEN the configured `rollout_policy`
   factory SHALL compute the target client set and the system SHALL
   announce the version only to that set.
2. IF the policy returns a set that contains clients pinned to a
   different version THEN the system SHALL silently exclude those
   clients and SHALL NOT report them as "held back".
3. WHILE a stage is active the system SHALL collect outcome events
   (`upgrade.succeeded`, `upgrade.failed`, `upgrade.deferred`) and expose
   rolling totals for operator inspection.
4. IF the failure rate in a stage exceeds `stage_failure_threshold`
   THEN the system SHALL auto-halt the rollout and emit
   `entity.rollout.halted{reason=failure_threshold_exceeded}`.

### Requirement 3: Artifact delivery is integrity-checked

**User Story:** As a client agent about to replace my own binary, I want
to verify the artifact's signature and digest before install, so that a
MITM cannot slip me a bad binary.

**Acceptance Criteria (EARS):**

1. WHEN the transport offers an upgrade THEN the announcement SHALL
   include `artifact_sha256` and a `signature` over
   `(version, artifact_sha256, issued_at)` signed by the Pychestrate
   release-signing key.
2. IF the client reports a `sha256_mismatch` THEN the system SHALL mark
   the offer failed, SHALL emit `entity.upgrade.integrity_failed`, and
   SHALL halt offers for that version pending operator review.
3. WHERE the `upgrade_artifact_source` factory fails to deliver bytes
   the client SHALL retry up to `artifact_fetch_max_attempts` and then
   report `fetch_failed`; the system SHALL count fetch_failed toward the
   stage failure threshold.

## Property-Based Test Requirements

### Property 1: Pin enforcement is absolute

- **Invariant:** For any set of clients `C`, any rollout announcement
  `A`, and any assignment of pins `P`, no client `c ∈ C` with
  `P[c.pod_id] != A.version` is ever offered `A`.
- **Generator:** hypothesis strategy producing random `(C, A, P)`
  triples and simulating rollouts.
- **Assertion:** for every recorded offer `(c, v)`, `P.get(c.pod_id)`
  is either None or equal to `v`.
- **Sample size:** 1000 generated cases

### Property 2: Failure-threshold halt is monotonic

- **Invariant:** For any stage with observed outcomes, once the failure
  rate first exceeds the threshold, the rollout never transitions back
  to active without explicit operator action.
- **Generator:** hypothesis strategy producing random outcome streams
  against varying thresholds and stage sizes.
- **Assertion:** `rollout.state` never equals `active` after a
  `halted{reason=failure_threshold_exceeded}` event without an
  intervening `entity.rollout.resumed` from an admin.
- **Sample size:** 1000 generated cases

### Property 3: In-use deferral preserves run integrity

- **Invariant:** For any pod that receives an upgrade offer while
  `state=in_use`, every run in-flight at offer time either completes
  on the pre-upgrade version or is still non-terminal when the offer
  expires. The agent is never swapped while a run is non-terminal.
- **Generator:** hypothesis strategy producing runs with random
  durations and offers arriving at random intervals.
- **Assertion:** for every run's `final_agent_version`, the value
  equals the agent version that was running at `run.accepted` time; no
  run's version changes mid-flight.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** announcement publish latency p99 <= 300 ms
  to all currently-connected clients in the target set; artifact fetch
  latency dominated by the backing store (measured separately).
- **NFR-2 (Security):** artifacts signed with a release key held in
  `1-secrets-vault`; signing key material never loaded in the same
  process context as the REST handler; every rollout action
  audit-logged; RBAC `agent.rollout.read|write|admin`.
- **NFR-3 (Observability):** metrics
  `pychestrate_client_upgrade_offers_total{outcome}`,
  `pychestrate_client_upgrade_stage_gauge{stage,state}`,
  `pychestrate_client_upgrade_failure_rate`,
  `pychestrate_client_upgrade_artifact_fetch_seconds`; log events
  `pychestrate_client_upgrade_announced`,
  `pychestrate_client_upgrade_succeeded`,
  `pychestrate_client_upgrade_failed`,
  `pychestrate_client_upgrade_halted`; trace spans
  `agent_upgrade.announce`, `agent_upgrade.collect_outcome`.
- **NFR-4 (Reliability):** rollout progress is durable; on service
  restart, in-flight stages resume from the last recorded offered set;
  no double-offer to the same client within one stage.

## Out of Scope

- Service (server-side) upgrade — owned by `10-release-channels`.
- Client-side upgrade apply mechanics (owned by the agent binary).
- Member (device / VM) firmware updates — not in Pychestrate's remit.
- Feature-flag toggles — owned by `1-feature-flags`.

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`,
  `0-object-store`, `1-secrets-vault`, `1-audit-log`, `1-rbac`,
  `3-client-agent-protocol`, `3-client-registry`,
  `3-pod-lifecycle`, `3-pod-definitions`,
  `10-release-channels`, `E-extension-host`,
  `E-factory-protocols`.
- **Depended on by:** none (terminal in the layer graph).
- **Extension points exposed:**
  - `factory: upgrade_artifact_source` — object store, GitHub
    releases, internal artifact registry, air-gapped mirror.
  - `factory: rollout_policy` — percent, ring-based,
    canary-then-fleet, custom.
  See implementation-plan.md Layer 3 and Phase 10.
