# 6-drift-detection — Tasks

## Milestones

- **M1 — Skeleton:** `drift_schedule` + `drift_run` schema + Terraform checker + scheduler with exactly-once ledger + happy path dispatch.
- **M2 — Core Behavior:** Pulumi + Ansible checkers, ingest + digest, `run_now`, drift-detected events, capability checks.
- **M3 — Hardening:** Metrics/logs/traces, perf, property tests, docs, ingest retry.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/orchestration/infra/drift/` package per design.md.
- [ ] T1.2 — Add `0-persistence` migration for `drift_schedule`, `drift_run`, `drift_tick_ledger`.
- [ ] T1.3 — Implement `checker_protocol.py::DriftCheckerProtocol`.
- [ ] T1.4 — Implement `TerraformDriftChecker` at `source/site/automojo/factories/pychestrate/drift_checker/terraform.py` with `PRECEDENCE = 500`.
- [ ] T1.5 — Implement `scheduler.py` with cron evaluator (croniter-based) and exactly-once tick insert.
- [ ] T1.6 — Implement `service.py::DriftDetection.set_schedule` and `tick`.
- [ ] T1.7 — Register REST `PUT /.../drift-schedule` and `GET /.../drift-runs`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `PulumiDriftChecker`, `AnsibleDriftChecker`.
- [ ] T2.2 — Implement `ingest.py` parsing reports and computing `diff_digest_sha256`.
- [ ] T2.3 — Implement Layer 5 state-mirror subscriber.
- [ ] T2.4 — Implement `run_now` endpoint `POST /.../drift-runs:run-now`.
- [ ] T2.5 — Implement capability-check skip with WARNING log for scheduled; 409 for manual.
- [ ] T2.6 — Emit `entity.env.drift.scheduled`, `entity.env.drift.dispatched`, `entity.env.drift.completed`, `entity.env.drift_detected`, `entity.env.drift.manual_triggered`.
- [ ] T2.7 — Implement `checker_registry.py` accessor; subscribe to `extension.reloaded`.
- [ ] T2.8 — Subscribe to `entity.env.declared|archived|destroyed` to manage schedule lifecycle.

### M3 — Hardening

- [ ] T3.1 — Emit Prometheus metrics and OTel spans per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: scheduler fire→dispatch p99 < 500 ms; ingest+persist p99 < 300 ms at 5 MiB; digest p99 < 80 ms. Fail CI on regression.
- [ ] T3.3 — Implement ingest-failure retry with bounded backoff; mark `state = ingest_failed` on terminal failure.
- [ ] T3.4 — Sphinx docs for REST, internal API, checker authoring.
- [ ] T3.5 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.6 — Enforce `run_now` rate limit per env (default 12/hour).
- [ ] T3.7 — Reject checkers advertising `may_mutate: True`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (idempotent digest) and Property 2 (exactly-once tick) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 7 scenario — declare env `staging-eu`, set hourly drift schedule; simulate tick; drift report with 2 adds + 1 destroy → `entity.env.drift_detected` emitted; second unchanged run → no new detect event.
- [ ] TT-4 — Extension-point test: test-only `FakeDriftChecker` (`PRECEDENCE = 1`) wins lookup and produces the expected report.
- [ ] TT-5 — Missed-tick catchup test: stop scheduler across two ticks; restart; at most `max_missed_tick_catchup` replays dispatched.
- [ ] TT-6 — Capability-mismatch test: no pod advertises the checker's capability; scheduled tick → WARNING + `skipped`; manual → `CapabilityMismatchError`.

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
