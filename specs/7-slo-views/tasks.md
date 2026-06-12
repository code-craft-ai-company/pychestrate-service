# 7-slo-views — Tasks

## Milestones

- **M1 — Skeleton:** `slo` table, `SLODefinitionExtension` base + registry, `availability_ratio` reference kind, `SLOService.create` + `SLOStatusService.compute_status`, basic REST.
- **M2 — Core Behavior:** Burn-rate computation (multi-window), `BurnRateEvaluator.tick`, `SLOBurnRateAlertRuleKind` contribution, auto-attach burn-rate alerts, `latency_quantile` + `threshold_budget` kinds.
- **M3 — Hardening:** Cascade delete, status caching, redaction-aware reads, metrics/logs/traces, perf benchmarks, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/ccai/pychestrate/webservice/slo/` package per design.md.
- [ ] T1.2 — Add `0-persistence` migration for `slo` and `slo_burn_rate_state`.
- [ ] T1.3 — Implement `extension_base.py::SLODefinitionExtension` and `registry.py::SLODefinitionKindRegistry.build()`.
- [ ] T1.4 — Ship reference `source/site/ccai/extensions/pychestrate/slo_definition/availability_ratio.py`.
- [ ] T1.5 — Implement `service.py::SLOService.create_slo` + `get_slo`.
- [ ] T1.6 — Implement `status.py::SLOStatusService.compute_status`.
- [ ] T1.7 — Register REST endpoints `POST /`, `GET /`, `GET /{id}`, `GET /{id}/status`, `GET /kinds` under `8-rest-api-v1`.
- [ ] T1.8 — Emit `entity.slo.saved`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `status.py::compute_burn_rate` and `compute_multi_window_burn_rate` (fast 2 h + slow 6 h).
- [ ] T2.2 — Register `GET /{id}/burn-rate` endpoint.
- [ ] T2.3 — Implement `evaluator.py::BurnRateEvaluator.tick` with per-severity hysteresis.
- [ ] T2.4 — Emit `entity.slo.burn_rate_high{severity}` events honoring `burn_rate_slow_for_seconds`.
- [ ] T2.5 — Implement `alert_kind.py::SLOBurnRateAlertRuleKind` against `7-alerts-budgets`'s `AlertRuleKindExtension`.
- [ ] T2.6 — Auto-attach fast + slow burn-rate alerts on save when `auto_attach_burn_rate_alerts = True`.
- [ ] T2.7 — Ship `latency_quantile.py` and `threshold_budget.py` reference kinds.
- [ ] T2.8 — Register `PUT`, `DELETE` with `If-Match` ETag concurrency; cascade-delete dependent alert rules on SLO delete.
- [ ] T2.9 — Register `GET /{id}/history` read-through endpoint.

### M3 — Hardening

- [ ] T3.1 — Implement status cache (`status_cache_ttl_seconds`, default 30) in `SLOStatusService`.
- [ ] T3.2 — Implement redaction when caller lacks `slo.definition.read:details`.
- [ ] T3.3 — Rate-limit `max_slo_writes_per_hour_per_actor` (default 60).
- [ ] T3.4 — Emit metrics `pychestrate_slo_target`, `pychestrate_slo_achieved`, `pychestrate_slo_error_budget_remaining_ratio`, `pychestrate_slo_burn_rate`, `pychestrate_slo_burn_rate_high_total`, `pychestrate_slo_status_duration_seconds`, `pychestrate_slo_definitions_registered`.
- [ ] T3.5 — Emit OTel spans per design.md Observability.
- [ ] T3.6 — Benchmark NFR-1: status API p99 < 1.2 s; burn-rate tick for 200 SLOs p99 < 3 s.
- [ ] T3.7 — Sphinx docs for REST API, `SLODefinitionExtension` authoring guide, and burn-rate alert attachment.
- [ ] T3.8 — Handle partial `ts_facade.query_range` results by setting `partial: True` in response and emitting `pychestrate.slo.partial_result`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (burn rate monotonic in error count), Property 2 (error budget identity), Property 3 (quiet when healthy) at 1000 cases each.
- [ ] TT-3 — Integration test: declare an availability-ratio SLO with `target=0.99`, inject 1 000 samples with 10 errors, assert achieved ratio ≈ 0.99 and error_budget_remaining ≈ 0.0.
- [ ] TT-4 — Extension-point test: test-only `SLODefinitionExtension` (`kind="test_only_slo"`) registers and is usable end-to-end.
- [ ] TT-5 — Burn-rate test: inject error rate equivalent to 20x burn rate over 2 h window; assert `entity.slo.burn_rate_high{severity="fast"}` emitted immediately.
- [ ] TT-6 — Burn-rate slow-hysteresis test: burn rate at 8x for 500 s then drops; assert no slow event fires (needs 900 s).
- [ ] TT-7 — Cascade delete test: SLO with two auto-attached alerts; delete SLO; both alert rules deleted; `entity.alert.rule_deleted` emitted twice.
- [ ] TT-8 — Partial result test: mock `ts_facade.query_range` returns `partial=True`; status response includes `partial: True` and logs `pychestrate.slo.partial_result`.

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
