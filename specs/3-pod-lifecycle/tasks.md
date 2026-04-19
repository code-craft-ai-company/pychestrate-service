# 3-pod-lifecycle — Tasks

## Milestones

- **M1 — Skeleton:** Declared transition table; pure-function engine;
  apply_transition writes through SERIALIZABLE tx; `entity.pod.state_changed`
  publishes; read REST works.
- **M2 — Core Behavior:** Full subscriber coverage (registration, run,
  liveness, drain, force_release); drain-to-release automatic
  completion; audit log; client-loss / recovery branch.
- **M3 — Hardening:** Optimistic-lock race handling, invalid-transition
  telemetry, metrics, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Migration pack: `pod_runtime_state`, `pod_lifecycle_log`
  tables.
- [ ] T1.2 — Enums `PodState`, `LifecycleEventKind`.
- [ ] T1.3 — Declare `TRANSITIONS: Mapping[(PodState,
  LifecycleEventKind), PodState]` in `transitions.py`.
- [ ] T1.4 — Implement pure `transition_from` in `engine.py` raising
  `InvalidPodTransition` on missing edges.
- [ ] T1.5 — Implement `apply_transition` in `service.py` with
  SERIALIZABLE tx and `transition_cursor` optimistic lock.
- [ ] T1.6 — Implement `PodRuntimeStateRepository` with
  `load_for_update`, `update_state`, `append_log`.
- [ ] T1.7 — REST read: `GET state`, `GET state/history`.
- [ ] T1.8 — Publish `entity.pod.state_changed` on every applied
  transition.

### M2 — Core Behavior

- [ ] T2.1 — Subscriber on `entity.pod.registered` /
  `entity.pod.deregistered` -> `apply_transition(POD_REGISTERED|POD_DEREGISTERED)`.
- [ ] T2.2 — Subscriber on `entity.run.accepted|completed|failed|cancelled`
  -> update `runs_remaining`, apply `RUN_*` transitions.
- [ ] T2.3 — Subscriber on `entity.client.liveness_changed` -> apply
  `CLIENT_LIVENESS_*` transitions; save `previous_state` when entering
  `CLIENT_LOST`.
- [ ] T2.4 — REST `:drain` endpoint applying `DRAIN_REQUESTED`.
- [ ] T2.5 — REST `:force-release` endpoint applying `FORCE_RELEASE`
  (admin only).
- [ ] T2.6 — Automatic `DRAINING -> RELEASED` transition when the last
  run terminates (check inside `apply_transition(RUN_COMPLETED|FAILED|
  CANCELLED)`).
- [ ] T2.7 — Client-recovery branch: after `CLIENT_LIVENESS_ALIVE`, call
  `3-static-pods.reconcile_on_recover` and choose `previous_state` or
  `FAILED`.
- [ ] T2.8 — Audit-log writes for every admin transition.

### M3 — Hardening

- [ ] T3.1 — Optimistic-lock retry for `PodStateConflict` with single
  retry; escalate to `pychestrate_pod_lifecycle_race` log event.
- [ ] T3.2 — Emit all metrics in design.md Observability.
- [ ] T3.3 — Trace span `pod_lifecycle.transition`,
  `pod_lifecycle.subscriber.<source>`.
- [ ] T3.4 — Rate limit `:drain` and `:force-release` REST endpoints.
- [ ] T3.5 — Static analysis check that every `PodState` is reachable
  from `DEFINED` and that every non-terminal state has at least one
  outgoing edge; CI-enforced.
- [ ] T3.6 — Sphinx docs for the transition table and the engine.

## Test Tasks

- [ ] TT-1 — Unit tests for each EARS clause in Requirements 1-4.
- [ ] TT-2 — Hypothesis tests for Property 1 (transition graph
  respected), Property 2 (invalid transitions are side-effect free),
  Property 3 (runs-remaining invariant during drain).
- [ ] TT-3 — Integration test: static pod registered -> 3 runs
  accepted/completed -> drain -> last run completes -> pod reaches
  `RELEASED`.
- [ ] TT-4 — Extension-hook test: an out-of-tree subscriber on
  `entity.pod.state_changed` observes every transition in the above
  scenario.
- [ ] TT-5 — Client-loss test: pod in `IN_USE`, client goes lost,
  pod transitions to `CLIENT_LOST`; on recover with matching report
  returns to `IN_USE`; runs unchanged.
- [ ] TT-6 — Race test: two simultaneous transition attempts against
  the same pod; exactly one wins; loser retries; log event fires on
  second collision case.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] `entity.pod.state_changed` exercised by an out-of-tree subscriber
  test.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Definition of Done for Phase 2 in
  specs/implementation-plan.md.
