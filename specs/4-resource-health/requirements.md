# 4-resource-health — Requirements

## Introduction

The `4-resource-health` feature runs pluggable health probes against
inventory resources, quarantines resources that fail consecutively, heals
them when they recover, and tracks `last_good_at` so flake tracking and
capacity planning have ground truth. Probes are chosen per resource
*kind* — the canonical per-kind extension pattern — via the
`resource_health_probe` factory protocol keyed by `kind_name`. Pychestrate
ships reference probes for `device` (ping/TCP/SSH-reachability),
`ip_subnet` (DHCP lease check), `ip_address` (in-use/idle probe), and
`license` (seat-count vendor query). An external pack can register a
probe for a custom kind without forking the service.
The feature hooks into `4-resource-inventory` (drives state transitions
`available ↔ quarantined`) and `4-checkout-checkin` (quarantined
resources are refused for new reservations). Pod members respect
pod-as-lock-unit: probes continue while a pod holds a member but state
changes do not disrupt the active pod reservation; they affect only
*future* reservations. Ships in Phase 4.

## Requirements

### Requirement 1: Probe Selection is Keyed by Resource Kind

**User Story:** As a site operator, I want each resource kind to have
its own health probe, so that devices, subnets, and licenses are each
checked in a way that makes sense for that kind.

**Acceptance Criteria (EARS):**

1. WHEN the probe scheduler selects a resource for probing THEN the
   system SHALL look up `resource_health_probe` factory implementations
   keyed by the resource's `kind_name` and run the lowest-PRECEDENCE
   match.
2. IF no probe is registered for a kind THEN the system SHALL skip
   probing for that kind, emit
   `pychestrate.resource.health.no_probe_for_kind` exactly once per
   kind at startup, and SHALL NOT quarantine any resource of that kind
   via this feature.
3. WHERE a `ResourceKindExtension` declares
   `default_probe_name="<probe>"` THEN the system SHALL honor that
   binding at startup and use the named probe unless an override is
   configured per resource.

### Requirement 2: Quarantine on Consecutive Failures; Heal on Recovery

**User Story:** As an operator, I want one-off probe failures ignored
and persistent failures to quarantine the resource, so that an
intermittent blip doesn't take devices offline.

**Acceptance Criteria (EARS):**

1. IF a probe fails `quarantine_threshold_consecutive` times in a row
   (default 3) for a resource THEN the system SHALL transition the
   resource to `quarantined` via
   `4-resource-inventory.transition_resource_state`, emit
   `entity.resource.quarantined` with the probe name and last error,
   and SHALL NOT re-probe it until the heal-watch schedule runs.
2. WHEN a quarantined resource's heal-watch probe passes
   `heal_threshold_consecutive` times in a row (default 2) THEN the
   system SHALL transition the resource to `available`, emit
   `entity.resource.healed`, and update `last_good_at = now()`.
3. WHILE a resource is under an active reservation THEN the system
   SHALL continue to probe it but SHALL NOT transition it to
   `quarantined` until the reservation is released (recorded as
   `deferred_quarantine=true` instead).
4. WHEN the held reservation is released AND `deferred_quarantine ==
   true` THEN the system SHALL immediately quarantine the resource and
   clear the deferred flag.

### Requirement 3: Probe Cadence and Backoff

**User Story:** As an operator, I want probe cadence tuned per kind and
configurable under load, so that probing doesn't overwhelm the lab
network during heavy test activity.

**Acceptance Criteria (EARS):**

1. WHEN the probe scheduler ticks THEN each probe-kind binding SHALL
   run probes at the per-kind cadence declared by the probe
   (`probe_period_seconds`, default 60 for `device`, 300 for
   `ip_subnet`, 900 for `license`).
2. IF a probe exceeds its soft-timeout budget (`probe_timeout_seconds`,
   default 10) THEN the system SHALL treat the tick as a failure, emit
   `pychestrate.resource.health.probe_timeout`, and continue.
3. WHERE a kind's probe has N recent failures in a row the system
   SHALL apply exponential backoff — next-tick interval is
   `probe_period_seconds * min(2^N, 16)` — so a chronically-dead
   resource does not generate probe traffic every minute.

### Requirement 4: Last-Good Bookkeeping for Capacity Analytics

**User Story:** As a capacity planner, I want `last_good_at` recorded on
every pass so I can tell when a resource was last healthy without
parsing logs.

**Acceptance Criteria (EARS):**

1. WHEN a probe passes THEN the system SHALL update `last_good_at =
   probe_completed_at` and `consecutive_failures = 0` atomically.
2. WHEN a probe fails THEN the system SHALL increment
   `consecutive_failures`, record the last error message
   (truncated to 1 KB), and emit
   `pychestrate.resource.health.probe_failed`.
3. WHERE a resource has never been probed successfully THEN
   `last_good_at` SHALL be `NULL` and the `9-admin-ui` health column
   SHALL render it as "never".

## Property-Based Test Requirements

### Property 1: Quarantine is Monotonic Under Adversarial Probe Order

- **Invariant:** For any deterministic sequence of `pass`/`fail` probe
  outcomes, the resource's final state is decided solely by the
  *suffix* of consecutive results — specifically, `N` consecutive
  failures at the tail produce `quarantined`, `M` consecutive passes at
  the tail produce `available`, and interleaved runs flip at the
  correct boundary.
- **Generator:**
  `hypothesis.strategies.lists(sampled_from(["pass", "fail"]),
  min_size=1, max_size=200)` coupled with
  `quarantine_threshold_consecutive in [2, 5]` and
  `heal_threshold_consecutive in [1, 4]`.
- **Assertion:** Replaying the sequence yields the state predicted by a
  pure function on the suffix; no lost transitions, no extra
  transitions.
- **Sample size:** 1000 generated cases.

### Property 2: Held Resources Never Auto-Quarantine Mid-Reservation

- **Invariant:** For any interleaving of probe outcomes and reservation
  activity on a single resource, at no moment during an active
  reservation does the resource's `state` equal `quarantined`.
- **Generator:**
  `hypothesis.strategies.lists(sampled_from(["probe_pass",
  "probe_fail", "reserve", "release"]), min_size=2, max_size=64)`
  driving the combined state machine.
- **Assertion:** For every simulated time point where a reservation is
  active, `state != quarantined`; any pending quarantine is applied
  only after release.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Probe dispatch at 5,000 resources / minute
  per service with typical per-probe cost < 100 ms. Scheduler-tick
  overhead p99 < 50 ms at 50k resources. Probe timeout budget default
  10 s, caller-configurable per probe.
- **NFR-2 (Security):** Probes run with their granted
  `E-extension-sandbox` capabilities (Phase 8); in-tree device probes
  need `net:outbound`, license probes need `net:outbound` +
  `read:secrets` (for vendor API tokens). Probe credentials come from
  `1-secrets-vault` via the kind's sensitive attrs.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_resource_probe_runs_total{kind,probe,outcome}`,
  `pychestrate_resource_probe_duration_seconds{kind,probe}`
  (histogram), `pychestrate_resource_probe_timeout_total{kind,probe}`,
  `pychestrate_resource_quarantine_duration_seconds{kind}`
  (histogram observed on heal),
  `pychestrate_resource_consecutive_failures{kind}` (gauge),
  `pychestrate_resource_health_last_good_age_seconds{kind}` (gauge).
  Log events `pychestrate.resource.health.probe_failed`,
  `.probe_timeout`, `.quarantine_deferred`,
  `.no_probe_for_kind`. Trace span
  `pychestrate.resource.health.probe` with attributes
  `kind`, `probe`, `resource_id`, `outcome`, `duration_ms`.
- **NFR-4 (Reliability):** A probe that raises never kills the
  scheduler. A probe crash is caught at the probe boundary and treated
  as a `fail` outcome with the exception string as the recorded error.
  Per-kind backoff prevents probe storms against a dead fabric.

## Out of Scope

- Remediation actions (power-cycling, reboot, factory-reset) —
  Pychestrate does not *fix* externally-owned resources, only observes
  them.
- Client-agent liveness (see `3-client-agent-protocol`).
- Lease liveness (see `4-lease-heartbeat`).
- Usage / flake analytics rolled up over long windows — see
  `4-usage-history` for the timeline and `6-flake-tracking` for
  per-test roll-ups.

## Dependencies

- **Depends on:** `4-resource-inventory`, `0-message-bus`,
  `0-persistence`, `E-factory-protocols`, `1-secrets-vault`,
  `1-rbac`.
- **Depended on by:** `4-resource-pools` (membership recompute on
  `entity.resource.quarantined|healed`), `4-checkout-checkin`
  (refuses quarantined), `4-usage-history`, `5-job-dispatch`.
- **Extension points exposed:** `factory: resource_health_probe` —
  keyed by `kind_name`; in-tree: `DevicePingProbe`, `DeviceTCPProbe`,
  `DeviceSSHProbe`, `SubnetDhcpProbe`, `IpAddressReachabilityProbe`,
  `LicenseSeatCountProbe`.
