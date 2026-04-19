# 6-flake-tracking — Tasks

## Milestones

- **M1 — Skeleton:** `test_outcome` + `flake_classification` schema, ingest worker, `WindowRatioClassifier`, basic REST read.
- **M2 — Core Behavior:** Classifier factory protocol, quarantine ledger, per-env classification, retry hook wiring, broken-alert notification.
- **M3 — Hardening:** Retention sweep, property tests, metrics/logs/traces, perf benchmarks, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/orchestration/test/flake/` package per design.md.
- [ ] T1.2 — Add `0-persistence` migration for `test_outcome`, `test_case_identity`, `flake_classification`, `flake_quarantine_ledger` with indices.
- [ ] T1.3 — Implement `ingest_worker.py` subscribing to `entity.run.completed`, pulling `testrun_results.json` via `5-result-ingest-watcher`, inserting outcomes idempotently.
- [ ] T1.4 — Implement `classifier_protocol.py::FlakeClassifierProtocol`.
- [ ] T1.5 — Implement `WindowRatioClassifier` at `source/site/automojo/factories/pychestrate/flake_classifier/window_ratio.py` with `PRECEDENCE = 1000`.
- [ ] T1.6 — Implement `tracker.py::FlakeTracker.classify_for_entry` and `GET /api/v1/projects/{id}/flake/catalog-entry/{entry_id}`.
- [ ] T1.7 — Implement `window.py` building `TestHistoryWindow` with configurable lookback.

### M2 — Core Behavior

- [ ] T2.1 — Implement `classifier_registry.py` accessor; subscribe to `extension.reloaded`.
- [ ] T2.2 — Implement `set_quarantine` / `clear_quarantine` with ledger rows, RBAC, multiline-reason validation.
- [ ] T2.3 — Register `POST /.../quarantine` and `POST /.../clear-quarantine` REST endpoints.
- [ ] T2.4 — Emit `entity.flake.classified`, `entity.flake.quarantined`, `entity.flake.quarantine_cleared`, `entity.flake.broken_alerted`.
- [ ] T2.5 — Wire broken-transition alert via `2-notification-hub` to `6-test-catalog.owner_principal_id`.
- [ ] T2.6 — Expose `RetryAdvisor.should_retry(run_id, test_case_identity_sha256)` consumed by `6-test-orchestration` when `retry_flaky: True` is set at the pipeline stage.
- [ ] T2.7 — Implement per-env classification by partitioning history on `runtime_env_digest`.
- [ ] T2.8 — Register `GET /api/v1/projects/{id}/flake/history` with keyset pagination.

### M3 — Hardening

- [ ] T3.1 — Implement retention sweep dropping `test_outcome` rows older than `test_outcome_max_age_days`; preserves `flake_classification`.
- [ ] T3.2 — Emit Prometheus metrics and OTel spans per design.md Observability.
- [ ] T3.3 — Benchmark NFR-1: 5 000-test ingest p99 < 2 s; per-test `classify` p99 < 5 ms; `flake.get` p99 < 60 ms. Fail CI on regression.
- [ ] T3.4 — Enforce rate limit `max_quarantine_ops_per_hour_per_actor` (default 120); 429 on excess.
- [ ] T3.5 — Sphinx docs for public REST, `FlakeTracker` internal API, and classifier authoring guide.
- [ ] T3.6 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.7 — Demote misbehaving classifiers via the host when they raise on `classify`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (pure function) and Property 2 (monotonic quarantine) at 1000 cases each.
- [ ] TT-3 — Integration test: run 30 synthetic runs with a test flipping pass/fail every 3rd run; verify classification progresses from `insufficient_data` → `intermittent` → `flaky`.
- [ ] TT-4 — Extension-point test: test-only `BayesianClassifier` (`PRECEDENCE = 1`) wins lookup; its `classify` output is stored with its name/version.
- [ ] TT-5 — Retry test: pipeline declares `retry_flaky: True`; a failing flaky test is retried twice and a subsequent pass finalizes the run as pass.
- [ ] TT-6 — Quarantine monotonicity test: after quarantine, 50 consecutive pass outcomes do not auto-clear; explicit clear restores classification.
- [ ] TT-7 — Retention test: outcomes older than retention are deleted; classification still resolves against remaining window.

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
