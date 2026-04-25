# 5-offline-tolerance — Tasks

## Milestones

- **M1 — Skeleton:** Degraded/offline pod transitions with
  timers, deferred-cancel queue persistence, replay
  coordinator accepting batched records with seq gating.
- **M2 — Core Behavior:** Drain-on-reconnect orchestration
  after reconciliation, supersede path for terminal runs,
  replay-session cursor, admin listing of deferred cancels,
  orphan cleanup report.
- **M3 — Hardening:** Property tests, perf validation,
  dashboards and alerts, fault-injection suite, documentation.

## Tasks

### M1 — Skeleton

- [x] T1.1 — Create `jobs/offline/` package skeleton per design.md Component Breakdown.
- [x] T1.2 — Add Postgres migrations for `pod_offline_state`, `client_replay_cursor`, `deferred_cancel`.
      *(Migration 021.)*
- [~] T1.3 — Implement `jobs/offline/pod_state.py::PodOfflineStateService` subscribing to `entity.client.session_dropped` and `entity.client.reconnected`; arm degrade + offline timers.
      *(Service ships ``observe_session_dropped`` /
      ``observe_reconnected`` / ``evaluate_tier`` /
      ``is_eligible_for_dispatch``; bus subscribers that call
      them land when the client-protocol M2 emits the events.)*
- [~] T1.4 — Extend `5-job-dispatch` eligibility filter to exclude `degraded` and `offline` pods.
      *(``PodOfflineStateService.is_eligible_for_dispatch`` is
      the surface; the dispatcher's filter consumes it when the
      Phase-3 client capability advertisement layer is wired in
      the orchestration trigger path.)*
- [~] T1.5 — Implement `jobs/offline/cancel_queue.py::DeferredCancelQueue.queue_if_offline`; integrate with `5-cancel-reconcile.send_cancel_rpc` as the offline-branch.
      *(Queue ships with queue_if_offline / list_queued_for_pod /
      mark_delivered / mark_expired_overdue; the cancel
      dispatcher's hook into queue_if_offline lands with the M2
      bus-subscriber for client_reconnected.)*
- [x] T1.6 — Implement `ingest/progress/replay.py::ReplayCoordinator.accept_replay` including cursor check + `ReplaySeqGapError` path.
      *(In-package at ``jobs/offline/replay.py`` to keep all
      offline-tolerance code in one place; ``accept_replay``
      enforces monotonic cursor + auth + idempotent already-
      applied path.)*
- [~] T1.7 — Extend `ingest/progress/routes.py` to detect `X-Pychestrate-Replay` and dispatch to replay coordinator instead of live ingest.
      *(Coordinator ships at the service layer; HTTP route
      header dispatch lands with the broader Phase-3 REST
      surface.)*
- [x] T1.8 — Implement `jobs/offline/errors.py` with `ReplaySeqGapError` and `ReplayAuthError`.
      *(Plus ``OfflineError`` base.)*

### M2 — Core Behavior

- [ ] T2.1 — Implement `DeferredCancelQueue.drain_on_reconnect` invoked after `entity.run.reconciled` completes for all the client's runs.
- [ ] T2.2 — Implement supersede logic: drain-time check for terminal runs, mark row `superseded`, emit `pychestrate.offline.deferred_cancel_superseded`.
- [ ] T2.3 — Implement `client_replay_cursor` updates on every accepted batch; rotate on reconnect (new `session_id`).
- [ ] T2.4 — Implement `replay_completed` handling: emit event, clear cursor, unlock pod recovery transition back to `ready`.
- [ ] T2.5 — Publish `entity.pod.state_changed` for `degraded`/`offline`/`recovered` transitions (reuse `3-pod-lifecycle` topic).
- [ ] T2.6 — Implement `GET /api/v1/admin/deferred-cancels` read-only listing with RBAC `admin:read` gate.
- [ ] T2.7 — Implement orphan cleanup: rows queued > `orphan_cutoff_seconds` flagged `orphan` and surfaced in maintenance report.
- [ ] T2.8 — Implement rate-limiting + body-size enforcement on replay posts mirroring `5-progress-ingest` caps.

### M3 — Hardening

- [ ] T3.1 — Emit Prometheus metrics and OTel trace spans per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: degrade-transition p99 < 35 s; replay drain ≥ 5000 records/sec; cancel drain p99 < 1 s/row.
- [ ] T3.3 — Wire `1-audit-log` subscriber for deferred-cancel queued/drained/superseded with `deferred=true` flag.
- [ ] T3.4 — Add alerts: degraded ratio > 10% for 15 min; replay gap rate > 1% for 30 min; deferred-cancel depth > 200 for 1 h.
- [ ] T3.5 — Fault-injection test: drop session mid-run, accumulate 1k records, reconnect, assert replay completes in order.
- [ ] T3.6 — Document offline behavior under `usersguide/jobs/offline/tolerance.rst` including wire contract for replay headers.
- [ ] T3.7 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.8 — Chaos test: reconnect-flap (5 reconnects in 60 s), assert each `session_id` rotation invalidates the prior replay cursor.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (replay order + count) and Property 2 (deferred-cancel FIFO), 1000 cases each.
- [ ] TT-3 — Integration test: drop client session for 45 s, let pod go degraded, reconnect with 500 queued records and 3 deferred cancels; verify full replay + drain + pod recovery to `ready`.
- [ ] TT-4 — Seq-gap test: post replay batch with seq `[5, 6, 7]` after cursor is at 4 then post `[9, 10]`; assert 409 with `expected_seq=8`.
- [ ] TT-5 — Supersede test: queue 2 cancels; mark run terminal before reconnect; assert reconcile drain marks cancel `superseded` and does not transmit.
- [ ] TT-6 — Offline escalation test: disconnect > 600 s; assert pod transitions `degraded → offline`; reconnect later; assert recovery to `ready` after reconcile.
- [ ] TT-7 — Extension-point test: N/A — negative test verifying this feature declares no factory or resource extension.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
      — N/A for this feature.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
