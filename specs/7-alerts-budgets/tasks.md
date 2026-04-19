# 7-alerts-budgets — Tasks

## Milestones

- **M1 — Skeleton:** `alert_rule` + `alert_live_state` tables, `AlertRuleKindExtension` base + registry, `threshold` reference kind, `AlertEvaluator.tick` loop, basic REST CRUD.
- **M2 — Core Behavior:** Full state machine (fire/resolve/no_change with hysteresis), notification routing + throttling, retry queue, `rate_of_change` + `absence` reference kinds.
- **M3 — Hardening:** Recovery on restart, redaction-aware reads, metrics/logs/traces, perf benchmarks, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/alerts/` package per design.md.
- [ ] T1.2 — Add `0-persistence` migration for `alert_rule`, `alert_live_state`, `alert_notification_retry_queue`.
- [ ] T1.3 — Implement `extension_base.py::AlertRuleKindExtension`, `EvaluationContext`, `FiringResult`.
- [ ] T1.4 — Implement `registry.py::AlertRuleKindRegistry.build()`.
- [ ] T1.5 — Ship reference `source/site/automojo/extensions/pychestrate/alert_rule_kind/threshold.py`.
- [ ] T1.6 — Implement `service.py::AlertRuleService.create_rule` + `get_rule` + `list_rules`.
- [ ] T1.7 — Implement `evaluator.py::AlertEvaluator.tick` loading due rules and calling `evaluate_rule` → stdout + counter.
- [ ] T1.8 — Register REST endpoints `POST /`, `GET /`, `GET /{id}`, `GET /kinds` under `8-rest-api-v1`.

### M2 — Core Behavior

- [ ] T2.1 — Implement full state machine transitions (`firing → resolved` with `resolve_hysteresis_seconds`; `no_change` paths).
- [ ] T2.2 — Emit `entity.alert.fired` and `entity.alert.resolved` exactly once per transition.
- [ ] T2.3 — Implement `notifier.py::AlertNotifier.send` wrapping `NotificationHub.send` with `notification_enqueue_timeout_seconds`.
- [ ] T2.4 — Implement throttling per rule (`notifications_per_rule_max_per_hour`, default 12); suppress + counter + log.
- [ ] T2.5 — Implement retry queue writer + `retry_worker.py` draining with exponential backoff.
- [ ] T2.6 — Validate `notification_route_key` against `NotificationHub.has_route(...)` at rule save.
- [ ] T2.7 — Ship reference kinds `rate_of_change.py`, `absence.py`.
- [ ] T2.8 — Register `PUT`, `DELETE`, `POST /{id}/enable`, `POST /{id}/disable`, `GET /{id}/live`, `GET /api/v1/projects/{id}/alerts/live`.
- [ ] T2.9 — Implement `absent_strategy` handling (`fire | resolve | ignore`) per rule.

### M3 — Hardening

- [ ] T3.1 — Implement evaluator recovery: hydrate `_live_state_cache` from `alert_live_state` at boot.
- [ ] T3.2 — Implement rule-definition redaction when caller lacks `alerts.rule_definition.read:details`.
- [ ] T3.3 — Validate `runbook_url` against `runbook_url_allowlist`.
- [ ] T3.4 — Emit metrics `pychestrate_alert_evaluations_total`, `pychestrate_alert_evaluation_duration_seconds`, `pychestrate_alert_firing_count`, `pychestrate_alert_notifications_suppressed_total`, `pychestrate_alert_notification_failed_total`, `pychestrate_alert_retry_queue_depth`, `pychestrate_alert_rules_registered`.
- [ ] T3.5 — Emit OTel spans per design.md Observability.
- [ ] T3.6 — Benchmark NFR-1: 2 000 rules evaluated per tick with p99 < 250 ms per rule.
- [ ] T3.7 — Sphinx docs for REST API, `AlertRuleKindExtension` authoring guide, and runbook URL allow-list policy.
- [ ] T3.8 — Implement optimistic concurrency (`If-Match` ETag) on `PUT` and `DELETE`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (quiet below threshold), Property 2 (single fire per episode), Property 3 (fire/resolve pairing) at 1000 cases each.
- [ ] TT-3 — Integration test: create a threshold rule; synthesize a metric series crossing threshold; verify fire event, notification sent, hysteresis honored, resolve event.
- [ ] TT-4 — Extension-point test: test-only `AlertRuleKindExtension` (`kind="test_only_kind"`) registers and is evaluable end-to-end.
- [ ] TT-5 — Throttle test: force a rule to fire 20 times in one hour; assert 12 notifications sent + suppression metric increments 8.
- [ ] TT-6 — Channel-unavailable test: mock `NotificationHub.send` to raise `ChannelUnavailableError` thrice; assert retry queue row and eventual delivery on recovery.
- [ ] TT-7 — Recovery test: kill evaluator mid-tick; restart; live alerts restored and next evaluation fires on schedule.
- [ ] TT-8 — Redaction test: user without `alerts.rule_definition.read:details` sees `threshold` masked in `GET /{id}`.

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
