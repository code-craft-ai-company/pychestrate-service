# 4-usage-history — Tasks

## Milestones

- **M1 — Skeleton:** Timeline table, bus subscribers for the resource
  events, idempotent append, `GET /timeline` endpoint, no hooks yet.
- **M2 — Core Behavior:** `UsageAnalyticsHookExtension` pipeline with
  four in-tree hooks, pod event expansion, rollup worker, rollup
  endpoint, forced-release-burst alert.
- **M3 — Hardening:** Perf targets, metrics/logs/traces, extension
  tests, property tests.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/automojo/pychestrate/webservice/resources/usage_history/` per design.md.
- [ ] T1.2 — Alembic migration `0080_resource_timeline_events` creating `core.resource_timeline_events` with PK, UNIQUE `(event_id, resource_id)`, INDEX `(resource_id, at_ts DESC)`, INDEX `(event_type, at_ts DESC)`, INDEX `(pod_event_group_id)`.
- [ ] T1.3 — Alembic migration `0081_resource_usage_rollups` creating `core.resource_usage_rollups` with PK `(resource_id, window)` and INDEX `(window, computed_at DESC)`.
- [ ] T1.4 — Implement `models.py`: `ResourceTimelineEvent`, `ResourceUsageRollup`, `RollupWindow`, `UsageHookContext`.
- [ ] T1.5 — Implement `repository.py::UsageHistoryRepository` with idempotent insert (swallowing unique-constraint violations silently) and timeline query.
- [ ] T1.6 — Implement `subscribers.py` for every event in the Events Consumed list, translating each into a `ResourceTimelineEvent`.
- [ ] T1.7 — Redact payloads via the kind's `render_public` before persist.
- [ ] T1.8 — Implement `GET /api/v1/resources/{id}/timeline`; wire `resource.usage.read` and `resource.usage.deep_history_read` permissions.

### M2 — Core Behavior

- [ ] T2.1 — Implement `pod_expansion.py::expand_pod_event`; assign a fresh `pod_event_group_id` and emit per-member rows plus the pod-level row.
- [ ] T2.2 — Implement `hook_pipeline.py` running `UsageAnalyticsHookExtension.decorate` in PRECEDENCE order with lower-PRECEDENCE-wins key-conflict resolution.
- [ ] T2.3 — Ship the four in-tree hooks: `ProjectAttributionHook`, `OwnerTeamHook`, `ReservationDurationHook`, `QuarantineSpanHook`.
- [ ] T2.4 — Implement `rollup_worker.py` with 60s tick and `payload_hash`-based write suppression; compute `granted_count`, `release_count`, `forced_release_count`, `held_seconds`, `quarantined_seconds`, `last_good_age_seconds` per window.
- [ ] T2.5 — Implement `GET /api/v1/resources/{id}/usage-rollups?window=`.
- [ ] T2.6 — Forced-release-burst alert: emit `pychestrate.resource.usage.forced_release_burst` once per hour per resource when ratio > 0.1.
- [ ] T2.7 — Post-retention flagging: events arriving after `retired_at + 90d` get `post_retention=true` and emit `pychestrate.resource.usage.post_retention_event`.
- [ ] T2.8 — Subscribe to `extension.reloaded` to rebuild hook registry.
- [ ] T2.9 — Hook-crash containment: exceptions caught at hook boundary, metric + log, surviving hooks continue.

### M3 — Hardening

- [ ] T3.1 — Add every metric from design.md Observability.
- [ ] T3.2 — Benchmark append throughput ≥ 5,000 rows/sec/service; 7d timeline query p99 < 80 ms; 50k-resource rollup tick ≤ 30 s; fail CI on regression (NFR-1).
- [ ] T3.3 — Trace spans `pychestrate.resource.usage.append` and `.rollup_tick`.
- [ ] T3.4 — Ship an out-of-tree `pychestrate-ext-usage-costcenter` that adds a `CostCenterHook` annotating `{cost_center}`; integration test verifies the annotation lands.
- [ ] T3.5 — "Resource Usage" dashboard panel on `7-resource-metrics`.
- [ ] T3.6 — Sphinx docs for `UsageAnalyticsHookExtension` and each in-tree hook.
- [ ] T3.7 — Verify all multiline errors use `os.linesep.join([...])`; no behaviour-modifying decorators.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Hypothesis tests implementing Property 1 (every event yields exactly one row, modulo pod expansion) and Property 2 (rollup idempotence and commutativity), 1000 cases each.
- [ ] TT-3 — Integration test: drive Layer 4 through a full grant→release→quarantine→heal cycle, assert every timeline row is present with correct annotations and per-member pod expansion.
- [ ] TT-4 — Extension-point test: `AlwaysCrashHook` (test-only) raises; assert the row is still persisted with annotations from surviving hooks and the hook-error metric increments.
- [ ] TT-5 — Replay test: deliver the same bus event twice; assert exactly one timeline row exists (UNIQUE constraint suppresses the duplicate).
- [ ] TT-6 — Rollup determinism test: replay the same event bag in two random orders; assert the rollup rows are byte-equal and the second tick performs zero writes.

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
