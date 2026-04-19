# 4-resource-health — Tasks

## Milestones

- **M1 — Skeleton:** `core.resource_health` table, scheduler tick with
  hard-wired `DevicePingProbe`, bounded worker pool, pass/fail counters,
  no state transitions yet.
- **M2 — Core Behavior:** `resource_health_probe` factory protocol
  keyed per kind, six in-tree probes, quarantine/heal state transitions
  via inventory, deferred-quarantine drain on release, exponential
  backoff, REST surface.
- **M3 — Hardening:** Perf targets, metrics/logs/traces, extension
  tests, property tests, health dashboard.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/automojo/pychestrate/webservice/resources/health/` per design.md.
- [ ] T1.2 — Alembic migration `0070_resource_health` creating `core.resource_health` with PK, INDEX `(next_probe_at, probe_name)`, partial INDEX `(deferred_quarantine) WHERE deferred_quarantine = TRUE`.
- [ ] T1.3 — Implement `models.py` for `ResourceHealthRow`, `ProbeOutcome`, `ProbeResult`, `ProbeAspects`.
- [ ] T1.4 — Implement `repository.py::ResourceHealthRepository` with scheduler query using `FOR UPDATE SKIP LOCKED`.
- [ ] T1.5 — Subscribe to `entity.resource.registered`/`retired` to seed/remove `core.resource_health` rows.
- [ ] T1.6 — Hard-wire `DevicePingProbe` and implement `scheduler.py` with a bounded 16-worker pool and per-probe timeout cancellation.
- [ ] T1.7 — Implement `service.py::record_probe_outcome` updating counters and `next_probe_at` (no state transitions yet).
- [ ] T1.8 — `GET /api/v1/resources/{id}/health` endpoint.

### M2 — Core Behavior

- [ ] T2.1 — Declare `ResourceHealthProbeProtocol` (FactoryProtocolBase) and register through `E-factory-protocols`; extend the registry to key by `(protocol_name, kind_name)`.
- [ ] T2.2 — Implement the six in-tree probes: `DevicePingProbe`, `DeviceTCPProbe`, `DeviceSSHProbe`, `SubnetDhcpProbe`, `IpAddressReachabilityProbe`, `LicenseSeatCountProbe` under `source/site/automojo/factories/pychestrate/resource_health_probe/`.
- [ ] T2.3 — Honor `ResourceKindExtension.default_probe_name` at startup for initial bindings; emit `pychestrate.resource.health.no_probe_for_kind` once per kind that lacks one.
- [ ] T2.4 — Implement quarantine / heal state machine in `outcome_processor.py`; use `4-resource-inventory.transition_resource_state` exclusively.
- [ ] T2.5 — Deferred quarantine: set `deferred_quarantine=TRUE` when quarantine would collide with an active reservation; emit `pychestrate.resource.health.quarantine_deferred`.
- [ ] T2.6 — Subscribe to `entity.reservation.released`; drain `deferred_quarantine` atomically.
- [ ] T2.7 — Exponential backoff: `next_probe_at = now + probe_period_seconds * min(2^consecutive_failures, 16)`; emit `pychestrate.resource.health.backoff_applied` when the multiplier changes.
- [ ] T2.8 — `POST /api/v1/resources/{id}/health:probe-now` gated by `resource.health.probe_now`.
- [ ] T2.9 — Subscribe to `extension.reloaded` to rebuild per-kind probe bindings.

### M3 — Hardening

- [ ] T3.1 — Add every metric from design.md Observability.
- [ ] T3.2 — Benchmark probe dispatch ≥ 5,000 resources/min/service and tick overhead p99 < 50 ms at 50k resources; fail CI on regression (NFR-1).
- [ ] T3.3 — Trace spans `pychestrate.resource.health.probe` and `.tick`.
- [ ] T3.4 — Refuse startup if two probe impls share `(kind_name, probe_name)` without an override relationship; `ConfigurationError` with multiline message.
- [ ] T3.5 — Ship an out-of-tree `pychestrate-ext-packetcapture-probe` adding a probe for the `PacketCaptureResourceKind` shipped with the `4-resource-inventory` out-of-tree sample; integration test covers registration → probing → quarantine.
- [ ] T3.6 — "Resource Health" dashboard panel on `7-resource-metrics`.
- [ ] T3.7 — Sphinx docs for the factory protocol and each in-tree probe.
- [ ] T3.8 — Verify all multiline errors use `os.linesep.join([...])`; no behaviour-modifying decorators.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Hypothesis tests implementing Property 1 (quarantine monotonic under adversarial probe order) and Property 2 (held resources never auto-quarantine mid-reservation), 1000 cases each.
- [ ] TT-3 — Integration test: `AlwaysFailProbe` bound to a test kind; after 3 consecutive failures the resource is quarantined and `entity.resource.quarantined` fires; swapping to `AlwaysPassProbe` and waiting 2 passes heals the resource.
- [ ] TT-4 — Extension-point test: an out-of-tree `NoopProbe` (test-only, PRECEDENCE 100) overrides `DevicePingProbe` and is invoked for `device` kind.
- [ ] TT-5 — Deferred-quarantine test: reserve a device; force probe to fail enough to trigger quarantine; assert `state == available` while reservation is held and `deferred_quarantine == TRUE`; release; assert immediate `entity.resource.quarantined`.
- [ ] TT-6 — Backoff test: 5 consecutive failures push `next_probe_at` to `probe_period_seconds * 16` (ceiling); a pass resets it to `probe_period_seconds`.

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
