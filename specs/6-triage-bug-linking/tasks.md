# 6-triage-bug-linking — Tasks

## Milestones

- **M1 — Skeleton:** `triage_case` + ledger schema, signature normalization, classifier wired for `infra_flake` and `new_bug`, `NullBugTrackerDriver`.
- **M2 — Core Behavior:** Tracker factory protocol, Jira/GitHub/Linear drivers, auto-open queue with idempotency, REST endpoints, reclassify flow.
- **M3 — Hardening:** Caching, metrics/logs/traces, property tests, rate limiting, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/orchestration/test/triage/` package per design.md.
- [ ] T1.2 — Add `0-persistence` migration for `triage_case`, `triage_case_ledger`, `triage_signature_cache`, `triage_project_tracker_config`.
- [ ] T1.3 — Implement `signature.py::normalize_trace` and SHA-256 signature.
- [ ] T1.4 — Implement `classifier.py::classify(inputs)` as a pure function.
- [ ] T1.5 — Implement `tracker_protocol.py::BugTrackerDriverProtocol`.
- [ ] T1.6 — Implement `NullBugTrackerDriver` at `source/site/automojo/factories/pychestrate/bug_tracker/null.py` with `PRECEDENCE = 1000`.
- [ ] T1.7 — Implement `service.py::TriageService.classify_run` happy path reading flake/compare signals.
- [ ] T1.8 — Subscribe to `entity.run.completed` and invoke classify.

### M2 — Core Behavior

- [ ] T2.1 — Implement `JiraBugTrackerDriver`, `GithubIssuesBugTrackerDriver`, `LinearBugTrackerDriver` under `source/site/automojo/factories/pychestrate/bug_tracker/`.
- [ ] T2.2 — Implement `tracker_registry.py` accessor; subscribe to `extension.reloaded`.
- [ ] T2.3 — Implement `auto_open_queue.py` with idempotency key `(project, stack_signature_sha256)` and bounded backoff.
- [ ] T2.4 — Implement `set_project_tracker` persisting `triage_project_tracker_config`.
- [ ] T2.5 — Register REST endpoints: `GET /.../cases`, `GET /.../cases/{id}`, `POST /.../cases/{id}:reclassify`, `POST /.../config/tracker`.
- [ ] T2.6 — Emit `entity.triage.classified`, `entity.triage.new_bug_detected`, `entity.triage.ticket_opened`, `entity.triage.duplicate_merged`, `entity.triage.reclassified`.
- [ ] T2.7 — Write ledger row on every classification and on every manual reclassify; audit via `1-audit-log`.
- [ ] T2.8 — Implement secret-masking on ticket bodies (`password|token|secret` case-insensitive).

### M3 — Hardening

- [ ] T3.1 — Wire `triage_signature_cache` 10-min TTL; invalidate on `entity.compare.baseline_updated` and `entity.flake.classified`.
- [ ] T3.2 — Emit Prometheus metrics and OTel spans per design.md Observability.
- [ ] T3.3 — Benchmark NFR-1: classify p99 < 60 ms; cache-hit p99 < 5 ms; auto-open throughput >= 10/min per project. Fail CI on regression.
- [ ] T3.4 — Enforce `max_auto_opens_per_hour` (default 60) per project; excess deferred in the queue.
- [ ] T3.5 — Sphinx docs for public REST, `TriageService` internal API, and driver authoring guide.
- [ ] T3.6 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.7 — Tracker outage fallback: classification continues, ticket_key deferred, queue drains on recovery.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (pure classify) and Property 2 (idempotent known-issue match) at 1000 cases each.
- [ ] TT-3 — Integration test: simulate a run with a failing test whose stack matches an open Jira ticket in a mock tracker; verify classification `known_issue` and link persisted.
- [ ] TT-4 — Extension-point test: test-only `FakeBugTrackerDriver` (`PRECEDENCE = 1`) wins lookup; auto-open routes to it.
- [ ] TT-5 — Duplicate-merge test: auto-open returns duplicate; case is merged to existing ticket and reclassified as `known_issue`.
- [ ] TT-6 — Outage test: driver returns `TrackerTransientError`; classifications persist with `ticket_key = None`; after recovery, queue replays and opens exactly once per unique signature.
- [ ] TT-7 — Reclassify test: manual `POST :reclassify` appends ledger row, RBAC is enforced, event emitted.

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
