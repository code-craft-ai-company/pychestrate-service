# 4-lease-heartbeat — Tasks

## Milestones

- **M1 — Skeleton:** `core.leases` table, grant-subscriber attaches
  lease, heartbeat endpoint with hard-wired `FixedTtlRenewalPolicy`,
  sweeper that releases expired leases.
- **M2 — Core Behavior:** `lease_renewal_policy` factory protocol,
  four in-tree policies, nearing-expiry scan, pod-lease handling
  (one lease per pod reservation), cap + capped-state handling.
- **M3 — Hardening:** Perf targets, metrics/logs/traces, crash-safe
  sweeper, extension tests, property tests guaranteeing the 2×TTL bound.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/automojo/pychestrate/webservice/resources/lease/` per design.md.
- [ ] T1.2 — Alembic migration `0060_leases` creating `core.leases` with PK, UNIQUE on `reservation_id`, INDEX `(state, expires_at)`, INDEX `(pool_id)`.
- [ ] T1.3 — Implement `models.py` for `Lease`, `LeaseState`, `LeaseAspects`, `RenewalDecision`.
- [ ] T1.4 — Implement `repository.py::LeaseRepository` with `insert`, `update_expires`, `close`, and the sweeper query with `FOR UPDATE SKIP LOCKED`.
- [ ] T1.5 — Hard-wire `FixedTtlRenewalPolicy` in service.
- [ ] T1.6 — Subscribe on `0-message-bus` to `entity.reservation.granted`; call `attach_lease` when `aspects.lease_kind != "none"`.
- [ ] T1.7 — Subscribe to `entity.reservation.released`; close the lease row regardless of prior state.
- [ ] T1.8 — Implement `POST /api/v1/reservations/{id}:heartbeat` and `GET /api/v1/reservations/{id}/lease`; wire `1-rbac` permissions (owner or `reservation.lease.heartbeat_others`).
- [ ] T1.9 — Implement `sweeper.py` with tick cadence `min(ttl)/4` (min 5s); call `4-checkout-checkin.release(release_reason="lease_lost")` and emit `entity.lease.expired`.

### M2 — Core Behavior

- [ ] T2.1 — Declare `LeaseRenewalPolicyProtocol` (FactoryProtocolBase) and register it through `E-factory-protocols`.
- [ ] T2.2 — Implement the four in-tree policies: `FixedTtlRenewalPolicy` (1000), `SlidingRenewalPolicy` (1100), `CappedTotalHoldRenewalPolicy` (1200), `DeadlineAwareRenewalPolicy` (1300).
- [ ] T2.3 — Per-pool policy selection by name; fall back to `FixedTtlRenewalPolicy` on missing policy, log `pychestrate.lease.policy_missing` once per pool.
- [ ] T2.4 — Implement `capped` state: record `final_expires_at`, emit `pychestrate.lease.cap_reached`, reject further heartbeats with `409`.
- [ ] T2.5 — Enforce TTL clamp `[10s, min(max_reservation_ttl_seconds, 3600)s]` at `attach_lease`; reject out-of-range TTLs.
- [ ] T2.6 — Pod-lease handling: one `Lease` row for pod-target reservations; on expiry the release clears `pod_locked_by` on every member in the same transaction (already enforced by `4-checkout-checkin`).
- [ ] T2.7 — Nearing-expiry scan: `pychestrate.lease.nearing_expiry` emitted once per lease when `time_remaining < ttl * 0.25`; flag reset on successful heartbeat.
- [ ] T2.8 — Policy-exception safety: on policy crash, log `pychestrate.lease.policy_error`, fall back to `FixedTtlRenewalPolicy` for that heartbeat; increment `pychestrate_lease_policy_fallback_total`.
- [ ] T2.9 — Subscribe to `extension.reloaded` to rebuild policy bindings.

### M3 — Hardening

- [ ] T3.1 — Add every metric from design.md Observability.
- [ ] T3.2 — Benchmark heartbeat p99 < 10 ms and sweeper throughput ≥ 5,000 leases/sec/worker; fail CI on regression (NFR-1).
- [ ] T3.3 — Trace spans `pychestrate.lease.heartbeat` and `.expiry_sweep`.
- [ ] T3.4 — Ship an out-of-tree `pychestrate-ext-lease-exponential` demonstrating an `ExponentialBackoffRenewalPolicy`; integration test selects it by name.
- [ ] T3.5 — Chaos test: kill service during a sweep; restart; assert no lease is missed and the 2×TTL bound still holds.
- [ ] T3.6 — Sphinx docs for the factory protocol and each in-tree policy.
- [ ] T3.7 — "Leases" dashboard panel on `7-resource-metrics` with active-count, renewal rate, expired rate, p95 interval, nearing-expiry gauge.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Hypothesis tests implementing Property 1 (expiring heartbeats release within 2×TTL) and Property 2 (valid heartbeats preserve the lease), 1000 cases each; use a simulated clock.
- [ ] TT-3 — Integration test: grant with `lease_kind=sliding` → repeated heartbeats → assert `expires_at` advances and `entity.lease.renewed` fires on every heartbeat.
- [ ] TT-4 — Integration test: grant → stop heartbeating → assert `entity.reservation.released` with `release_reason=lease_lost` fires within 2×TTL.
- [ ] TT-5 — Extension-point test: `NeverRenewPolicy` (test-only, PRECEDENCE 100) rejects every heartbeat; assert `409` with the rejected reason and the lease still expires as normal.
- [ ] TT-6 — Pod-lease test: pod reservation with lease; stop heartbeat; assert single pod-level `entity.lease.expired`, single pod-level `entity.reservation.released`, and `pod_locked_by` cleared on every member.

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
