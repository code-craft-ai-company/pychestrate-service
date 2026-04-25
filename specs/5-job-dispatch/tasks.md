# 5-job-dispatch — Tasks

## Milestones

- **M1 — Skeleton:** `JobDispatcher` facade, eligibility filter,
  `FifoDispatchStrategy`, `dispatch_attempt` persistence, transport
  adapter stub, startup rehydration.
- **M2 — Core Behavior:** `DispatchStrategyProtocol` registry,
  backoff queue, `DispatchReceipt` ack handling, run state
  transition hand-off, `entity.run.dispatched` emission,
  `StickyPodDispatchStrategy` in-tree extension.
- **M3 — Hardening:** Property tests, perf validation against
  NFR-1, audit-log subscriber, dashboards, fault-injection
  suite for ack-timeout and transport failures.

## Tasks

### M1 — Skeleton

- [x] T1.1 — Create `jobs/dispatch/` package skeleton per design.md Component Breakdown.
      *(``source/site/automojo/pychestrate/webservice/jobs/dispatch/``
      with ``dispatcher.py``, ``repository.py``, ``models.py``,
      ``transport_adapter.py``, ``factories/{strategy,fifo}.py``,
      ``errors.py``, and ``__init__.py`` with
      ``register_builtin_extensions``.)*
- [x] T1.2 — Implement `jobs/dispatch/repository.py` writing the `dispatch_attempt` Postgres table; add migration.
      *(Table ``jobs_dispatch_attempt`` + ``dispatch_attempt_status``
      enum in migration ``018_phase3_dispatch_receipt``. Repository
      exposes ``create_attempt / mark_attempt_transmitted /
      mark_attempt_transport_failed / mark_attempt_acked /
      get_attempt / list_attempts_for_run /
      list_inflight_attempts``.)*
- [~] T1.3 — Implement `jobs/dispatch/eligibility.py::filter_candidates` consuming `3-client-registry` and `3-pod-lifecycle` snapshots.
      *(M1 takes candidates directly on the
      ``DispatchRequestInputs.candidates`` field — callers
      (tests / orchestration) pre-filter. Live integration with
      ``3-client-registry`` + ``3-pod-lifecycle`` lands in M2
      when the dispatcher owns its own in-memory state snapshot.)*
- [~] T1.4 — Implement `FifoDispatchStrategy` at `source/site/automojo/factories/pychestrate/dispatch_strategy/fifo.py` with `PRECEDENCE = 1000`.
      *(In-package location instead of external factories tree:
      ``jobs/dispatch/factories/fifo.py``. PRECEDENCE=1000 preserved.
      Registered via ``jobs.dispatch.register_builtin_extensions``.)*
- [x] T1.5 — Implement `jobs/dispatch/transport_adapter.py` wrapping `3-client-agent-protocol.send_envelope`.
      *(``ClientTransportProtocol`` + reference ``InMemoryTransport``
      with ``configure_failure`` for tests. Real agent-protocol
      wrapper lands when the ``3-client-agent-protocol.send_envelope``
      entry point is finalized.)*
- [x] T1.6 — Implement `jobs/dispatch/dispatcher.py::JobDispatcher.dispatch` happy path (build envelope → transmit → record attempt).
      *(Also handles the transport-failure path — the attempt row
      commits in ``TRANSPORT_FAILED`` with ``failure_reason``
      populated before the error surfaces.)*
- [~] T1.7 — Register `dispatch_rehydrate_hook` at web-app startup priority `50` calling `rehydrate_inflight`.
      *(``repository.list_inflight_attempts`` is the rehydration
      data source; the hook-registration plumbing lands with M2's
      in-memory concurrency gauge.)*
- [x] T1.8 — Implement `jobs/dispatch/errors.py` with the full error hierarchy.
      *(``DispatchError`` base + ``DispatchNoCandidatesError``,
      ``DispatchTransportError``,
      ``DispatchStrategyNotRegisteredError``.)*

### M2 — Core Behavior

- [ ] T2.1 — Implement `jobs/dispatch/strategy_registry.py::DispatchStrategyRegistry` resolving through `E-extension-host`.
- [ ] T2.2 — Declare `DispatchStrategyProtocol` factory protocol at `jobs/dispatch/protocol.py`.
- [ ] T2.3 — Implement `jobs/dispatch/backoff_queue.py` with exponential 1 s → 60 s backoff and scheduler tick every 500 ms.
- [ ] T2.4 — Implement `handle_ack`: persist `DispatchReceipt` through `5-dispatch-receipt`, increment `_inflight_by_pod`, transition run state.
- [ ] T2.5 — Publish `entity.run.dispatched` and `pychestrate.job_dispatch.failed` on `0-message-bus`.
- [ ] T2.6 — Implement `StickyPodDispatchStrategy` at `source/site/automojo/factories/pychestrate/dispatch_strategy/sticky.py` with `PRECEDENCE = 900`.
- [ ] T2.7 — Implement `DispatchAspects` (retry policy, timeout, logging knobs).
- [ ] T2.8 — Implement ack-timeout path transitioning run to `dispatch_unconfirmed` and deferring to `5-cancel-reconcile`.

### M3 — Hardening

- [ ] T3.1 — Emit Prometheus metrics and OTel trace span per design.md Observability section.
- [ ] T3.2 — Benchmark NFR-1: dispatch p99 < 75 ms with 1000-pod fleet and ≤ 16 caps; sustain ≥ 200 dispatches/sec.
- [ ] T3.3 — Wire `1-audit-log` subscriber for `entity.run.dispatched` and `pychestrate.job_dispatch.failed`.
- [ ] T3.4 — Subscribe to `entity.pod.state_changed` and `entity.client.capability.updated` to keep in-memory eligibility current.
- [ ] T3.5 — Add fault-injection test: kill the transport mid-transmit; assert attempt row reflects `transport_failed` with retry count.
- [ ] T3.6 — Document strategy authoring guide under `usersguide/jobs/dispatch/strategies.rst`.
- [ ] T3.7 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.8 — Implement `pychestrate_job_dispatch_queue_depth` emission from the backoff queue tick.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (concurrency cap invariant, stateful) and Property 2 (strategy determinism), 1000 cases each.
- [ ] TT-3 — Integration test: end-to-end dispatch through a mock client agent — submission → envelope → ack → `entity.run.dispatched` observed on the bus.
- [ ] TT-4 — Extension-point test: in-tree `FifoDispatchStrategy` plus a test-only `DeadlineAwareDispatchStrategy` (`PRECEDENCE = 10`); assert the deadline strategy wins and reverts on removal.
- [ ] TT-5 — Rehydration test: populate `dispatch_attempt` rows in `transmitted` state, restart process, assert `_inflight_by_pod` reflects only inflight attempts (acked and failed excluded).
- [ ] TT-6 — Chaos test: flap `entity.pod.state_changed` to `draining` for a selected pod; assert in-flight dispatches complete but no new dispatch is routed to that pod.

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
