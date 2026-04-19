# 6-source-integrations — Tasks

## Milestones

- **M1 — Skeleton:** `scm_project_config` + `scm_webhook_delivery` schema, webhook endpoint, `GithubScmProvider` reference driver, signature verification + dedup + file read + trigger handoff.
- **M2 — Core Behavior:** Commit-status posting subscriber, polling fallback, GitLab/Bitbucket/Gitea providers, `WebhookPayloadParserExtension`, REST config endpoints.
- **M3 — Hardening:** Metrics/logs/traces, rate limiting, property tests, perf benchmarks, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/orchestration/source/` package per design.md.
- [ ] T1.2 — Add `0-persistence` migration for `scm_project_config`, `scm_webhook_delivery`, `scm_last_seen_head`.
- [ ] T1.3 — Implement `provider_protocol.py::ScmProviderProtocol` and `parser_extension.py::WebhookPayloadParserExtension`.
- [ ] T1.4 — Implement `GithubScmProvider` at `source/site/automojo/factories/pychestrate/scm_provider/github.py` with `PRECEDENCE = 500`.
- [ ] T1.5 — Implement `service.py::SourceIntegrations.handle_webhook` happy path (verify → dedup → parse → read file → `PipelineService.trigger_run`).
- [ ] T1.6 — Register `POST /api/v1/webhooks/scm/{project_id}`.
- [ ] T1.7 — Implement `dedup.py` delivery store with `dedup_window_seconds` TTL.

### M2 — Core Behavior

- [ ] T2.1 — Implement `GitlabScmProvider`, `BitbucketScmProvider`, `GiteaScmProvider` reference factories.
- [ ] T2.2 — Implement `provider_registry.py` accessor; subscribe to `extension.reloaded`.
- [ ] T2.3 — Implement `status_poster.py` subscribing to `entity.pipeline.run_started|completed|failed|cancelled`; post status with dedup.
- [ ] T2.4 — Implement `poll_worker.py` scheduling sweeps per project with `use_polling: True`.
- [ ] T2.5 — Register `POST /api/v1/projects/{id}/scm/config` and `GET /api/v1/projects/{id}/scm/deliveries`.
- [ ] T2.6 — Implement `set_project_config` with RBAC `scm.config.write` and audit entries.
- [ ] T2.7 — Emit `entity.source.webhook.received`, `entity.source.pipeline_triggered_by_webhook`, `entity.source.commit_status_posted`.
- [ ] T2.8 — Implement `WebhookPayloadParserExtension` chain matching before default provider parser.

### M3 — Hardening

- [ ] T3.1 — Enforce `max_webhook_payload_bytes` (default 1 MiB) with 413 and multiline error.
- [ ] T3.2 — Enforce `max_webhooks_per_minute_per_project` (default 600) with 429.
- [ ] T3.3 — Emit Prometheus metrics and OTel spans per design.md Observability.
- [ ] T3.4 — Benchmark NFR-1: webhook handler p99 < 150 ms; status post p99 < 800 ms; poll sweep p99 < 3 s at 100 refs; dedup lookup p99 < 5 ms. Fail CI on regression.
- [ ] T3.5 — Sphinx docs for REST, `SourceIntegrations` internal API, and provider authoring guide.
- [ ] T3.6 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.7 — Implement `status_poster` retry logic with bounded backoff and idempotent duplicate-detection.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (dedup idempotence) and Property 2 (status dedup collapses bursts) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 6 scenario — open a PR on a fixture GitHub repo → signed webhook → pipeline file read → `PipelineService.trigger_run` invoked → on pipeline completion, status posted back to the PR head.
- [ ] TT-4 — Extension-point test: in-tree `GithubScmProvider` plus a test-only `FakeScmProvider` (`PRECEDENCE = 1`); configure a project to use `FakeScmProvider` and verify the fake sees the webhook.
- [ ] TT-5 — Signature-failure test: bad HMAC returns 401 and does not dispatch.
- [ ] TT-6 — Polling test: seed `last_seen_head` empty, inject two new refs on provider stub; sweep dispatches two pipeline runs.
- [ ] TT-7 — Missing-file test: webhook with `filename` absent at commit responds 200 without dispatching.
- [ ] TT-8 — Payload-parser-extension test: a `GithubQuirkParser` (`PRECEDENCE = 1`) overrides default parser and interprets a custom field in the payload.

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
