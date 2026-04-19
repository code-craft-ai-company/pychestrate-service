# 2-retention-policies — Tasks

## Milestones

- **M1 — Skeleton:** Policy + run tables land; create/list/draft/publish
  endpoints; `retention_action` factory protocol declared;
  `DeleteAction` reference impl.
- **M2 — Core Behavior:** Selector compilers for all built-in data
  classes; evaluator + dispatcher + scheduler; dry-run; artifact tier
  cooperation with `0-object-store`; archive and tier-move reference
  impls; `entity.retention.applied` wired.
- **M3 — Hardening:** Legal hold, failure/retry semantics, crash
  recovery, rate limits, observability, extension collision detection,
  full E2E integration with `5-artifact-store`.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Migration for `retention_policies`,
      `retention_run_records`, `retention_entity_results` tables.
- [ ] T1.2 — Implement `entities.py` dataclasses + enums.
- [ ] T1.3 — Implement `RetentionActionProtocol` in `factories.py`.
- [ ] T1.4 — Ship `DeleteAction` reference impl (terminal, respects
      `legal_hold`).
- [ ] T1.5 — Implement `service.create_policy` + `service.publish_policy`
      + `service.pause_policy` with validation of `data_class` and
      each `action_chain` step's action name against the registry.
- [ ] T1.6 — Wire REST endpoints for create / list / get / publish /
      pause under `restapi/versions/v1/retention.py`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `selectors/artifact.py`,
      `selectors/run_result.py`, `selectors/log_stream.py`,
      `selectors/audit_record.py`, `selectors/metric_sample.py`.
- [ ] T2.2 — Implement `evaluator.evaluate_policy` streaming matches
      in `batch_size` chunks.
- [ ] T2.3 — Implement `dispatcher.dispatch_action_chain` honoring
      step order, wait-days, and terminal semantics.
- [ ] T2.4 — Implement `scheduler.py` with per-policy advisory-lock
      leader election and interval cadence.
- [ ] T2.5 — Implement `service.dry_run_policy` and the dry-run
      REST endpoint (no side effects).
- [ ] T2.6 — Ship `TierMoveAction` reference impl delegating to
      `0-object-store` tier API (hot → cold → cold-archive).
- [ ] T2.7 — Ship `ArchiveAction` and `PermanentArchiveAction`
      reference impls.
- [ ] T2.8 — Publish `entity.retention.applied` after each successful
      batch with `RetentionAppliedEvent` payload.
- [ ] T2.9 — Implement `GET /retention/data-classes` and
      `GET /retention/actions` endpoints.

### M3 — Hardening

- [ ] T3.1 — Implement `legal_hold` check in `DeleteAction` and
      `PermanentArchiveAction`; record `skipped=legal_hold`.
- [ ] T3.2 — Implement retry / max-attempts logic and per-entity
      `failed` recording with full error chain preserved via
      `raise ... from err`.
- [ ] T3.3 — Implement crash-recovery: `finished_at IS NULL` runs
      are resumed by the next leader acquisition.
- [ ] T3.4 — Add rate-limiter rules (20/min policy write,
      5/min dry-run).
- [ ] T3.5 — Emit all metrics / logs / trace spans listed in
      design.md Observability; register counters through
      `7-metrics-ingest`.
- [ ] T3.6 — Subscribe to `entity.project.deleted` and archive
      project-scoped policies automatically.
- [ ] T3.7 — Extension collision detection: two
      `retention_action` impls at equal `PRECEDENCE` with the same
      `action_name` make startup fail with
      `ConfigurationError`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in
      requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests for Property 1 (dispatch
      idempotence) and Property 2 (selector/action count
      invariants) using `hypothesis.stateful` + `hypothesis.strategies`.
- [ ] TT-3 — Integration test with `5-artifact-store` and
      `0-object-store`: uploads 50 artifacts, runs a 3-step policy
      (hot → cold at 30d, cold → archive at 180d, delete at 730d)
      with simulated clock, and verifies exactly the expected rows
      move tier and are deleted.
- [ ] TT-4 — Extension-point test: out-of-tree
      `NotifyOwnerBeforeDeleteAction` registers, is referenced
      by a policy's `action_chain`, and its side effect is observed
      (a mock email send counter increments).

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (`retention_action`) has four in-tree
      reference implementations and at least one test-only override
      at a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 10 in
      specs/implementation-plan.md
