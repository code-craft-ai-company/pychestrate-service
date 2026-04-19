# 4-checkout-checkin — Tasks

## Milestones

- **M1 — Skeleton:** `core.reservations` table, `POST` checkout against a
  single-resource target with DB-enforced exclusivity, owner `DELETE`
  release, `entity.reservation.created|released` events.
- **M2 — Core Behavior:** Pool-targeted checkout, pod-as-lock-unit
  checkout, `CheckoutValidatorExtension` pipeline, queue forwarding to
  `4-reservation-scheduler`, expiry sweeper, force-release.
- **M3 — Hardening:** Perf targets, metrics/logs/traces, crash-safe
  sweeper, audit-log coverage, extension + property tests.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/automojo/pychestrate/webservice/resources/checkout/` per design.md.
- [ ] T1.2 — Alembic migration `0030_reservations` creating `core.reservations` with the PK, the unique partial index on `(resource_id) WHERE state='granted' AND mode='exclusive'`, and the helper indices.
- [ ] T1.3 — Alembic migration `0031_resources_pod_lock` adding `pod_locked_by UUID` to `core.resources` with partial index on `pod_locked_by`.
- [ ] T1.4 — Implement `models.py` dataclasses for `Reservation`, `ReservationMode`, `ReservationState`, `ReservationAspects`, `ReservationTarget`, `WaitStrategy`.
- [ ] T1.5 — Implement `repository.py::ReservationRepository` with `insert`, `load`, `update_state`, and the exclusive-grant unique-violation reclassification.
- [ ] T1.6 — Implement `service.py::reserve` for a single-resource target (no pool, no pod) and `release` with idempotency.
- [ ] T1.7 — Add Flask-RestX `api.py`; wire `reservation.create`, `reservation.release`, `reservation.read`, `reservation.force_release` permissions.
- [ ] T1.8 — Emit `entity.reservation.created` and `entity.reservation.released` through `0-message-bus`.

### M2 — Core Behavior

- [ ] T2.1 — Add pool-targeted branch: call `4-resource-pools.pick_from_pool` and handle `None` via `wait_strategy=queue`/`fail_fast`.
- [ ] T2.2 — Implement pod-targeted branch using `3-pod-definitions` member resolution; atomic UPDATE on `pod_locked_by` with rowcount check; raise `PodMemberLockedError` on conflict.
- [ ] T2.3 — Implement `validator_pipeline.py` running `CheckoutValidatorExtension` subclasses in order; short-circuit on first deny; emit `pychestrate.reservation.validator_denied`.
- [ ] T2.4 — Ship in-tree validators: `RequireReasonValidator`, `PodMemberExclusionValidator`, `ProjectScopeValidator`.
- [ ] T2.5 — Call `4-conflict-deconfliction.evaluate` between validator pipeline and DB insert; reclassify rule violations as `ReservationConflictError`.
- [ ] T2.6 — Enqueue path: persist `state='queued'`, emit `entity.reservation.queued`, hand off to `4-reservation-scheduler`.
- [ ] T2.7 — Callback path `grant_from_queue` with fresh validator + conflict re-evaluation and `from_queue=true` on `entity.reservation.granted`.
- [ ] T2.8 — Implement `force-release` endpoint with mandatory reason and `1-audit-log` entry.
- [ ] T2.9 — Implement `expiry_sweeper.py` with `SELECT ... FOR UPDATE SKIP LOCKED` batch of 500, 1s tick.
- [ ] T2.10 — Subscribe to `entity.lease.expired`; call `release(release_reason="lease_lost")`.

### M3 — Hardening

- [ ] T3.1 — Add every metric from design.md Observability (Prometheus).
- [ ] T3.2 — Benchmark checkout p99 < 25 ms and release p99 < 15 ms; fail CI on regression (NFR-1).
- [ ] T3.3 — Benchmark expiry sweep ≥ 5,000 reservations/sec/worker; fail CI on regression.
- [ ] T3.4 — Add trace spans `pychestrate.reservation.checkout|release|expiry_sweep`.
- [ ] T3.5 — Audit-log every create, release, force-release, and expired release with actor + reason (no sensitive cleartext).
- [ ] T3.6 — Ship an out-of-tree `pychestrate-ext-checkout-gate` that adds a `ChangeTicketRequiredValidator`; integration test its deny response is surfaced verbatim.
- [ ] T3.7 — Sphinx docs for the public REST API, internal API, and validator contract.
- [ ] T3.8 — Verify multiline errors use `os.linesep.join([...])`; no behaviour-modifying decorators.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Hypothesis tests implementing Property 1 (no-leak across matched checkout/release streams) and Property 2 (concurrent exclusive checkouts serialize), 1000 cases each, against a real Postgres.
- [ ] TT-3 — Integration test: two jobs contend for a one-member pool; first wins and gets `granted`, second queues and is `granted` on release; event stream is `created, granted, created, queued, released, granted, released`.
- [ ] TT-4 — Extension-point test: `AlwaysDenyValidator` (test-only) at lower `PRECEDENCE` short-circuits every checkout with the expected deny reason.
- [ ] TT-5 — Crash-safe expiry test: kill the worker mid-sweep; restart; assert no expired reservation is missed and no reservation is double-released.
- [ ] TT-6 — Pod-as-lock-unit test: hold a pod reservation; attempt independent checkout of a member; assert `409` naming the pod reservation; release pod; independent checkout now succeeds.

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
