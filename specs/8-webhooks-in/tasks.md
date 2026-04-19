# 8-webhooks-in — Tasks

## Milestones

- **M1 — Skeleton:** `inbound_webhook_parser` factory protocol
  declared, dispatcher pipeline wired through `8-rest-api-v1`,
  configuration CRUD endpoints, `GenericHmacWebhookParser`
  reference implementation covering end-to-end verification
  and normalized-event publishing.
- **M2 — Core Behavior:** `GithubWebhookParser`,
  `GitlabWebhookParser`, `BitbucketWebhookParser` references;
  replay-cache de-duplication; deadletter storage + replay
  endpoint; multi-event atomic publish.
- **M3 — Hardening:** 100 ms parser budget with cancellation;
  constant-time signature compare audit; full metric/log/trace
  coverage; 50 req/s load test; Sphinx docs; out-of-tree parser
  extension onboarding test.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Declare `InboundWebhookParserProtocol` with
      `factory_protocol_name = "inbound_webhook_parser"` and
      `protocol_schema_version = 1`.
- [ ] T1.2 — Land `webhooks_in_configurations`,
      `webhooks_in_seen_deliveries`, and
      `webhooks_in_deadletter_index` tables via an
      `EntityMigrationExtension` pack.
- [ ] T1.3 — Implement `configuration_service.create_webhook`,
      `list_webhooks`, `update_webhook`, `delete_webhook` and wire
      the `/api/v1/projects/{id}/webhooks/in` endpoints.
- [ ] T1.4 — Implement `dispatcher.dispatch_inbound_webhook`
      pipeline (resolve → verify → dedup → parse → publish).
- [ ] T1.5 — Implement `verification.verify_signature` with
      constant-time comparison.
- [ ] T1.6 — Implement `replay_cache.record_delivery_or_replay`
      with row-level insert contention.
- [ ] T1.7 — Implement `normalization.publish_domain_events` with
      atomic multi-event transaction semantics.
- [ ] T1.8 — Ship `GenericHmacWebhookParser` reference parser
      (`PRECEDENCE = 1500`).

### M2 — Core Behavior

- [ ] T2.1 — Ship `GithubWebhookParser` with support for
      `X-Hub-Signature-256` (strong) and `X-Hub-Signature` (weak +
      rejected-if-sole), `X-GitHub-Delivery` replay key, and
      emission of `entity.scm.push`, `entity.scm.pull_request`,
      `entity.scm.issue_comment`.
- [ ] T2.2 — Ship `GitlabWebhookParser`
      (`X-Gitlab-Token`, `X-Gitlab-Event-UUID`).
- [ ] T2.3 — Ship `BitbucketWebhookParser`.
- [ ] T2.4 — Implement `deadletter.store_deadletter` writing raw
      payloads to `0-object-store` under a 7-day TTL.
- [ ] T2.5 — Implement the
      `POST .../webhooks/in/{id}:replay` endpoint and
      `deadletter.replay_deadletter`.
- [ ] T2.6 — Enforce `mtls_required` by consulting the request's
      peer certificate resolved in `1-authentication`.
- [ ] T2.7 — Implement
      `POST /api/v1/webhooks/in/<provider>/<hook_name>` controller
      delegating to `dispatch_inbound_webhook`.
- [ ] T2.8 — Extend controller to reject `415 Unsupported Media
      Type` when `Content-Type` is not in
      `parser.accepted_content_types()`.

### M3 — Hardening

- [ ] T3.1 — Wrap parser invocations in a 100 ms wall-clock budget;
      cancel past it and reclassify as
      `StructuredRejection(reason="parser_timeout")`.
- [ ] T3.2 — Catch-and-reclassify any escaping exception from a
      parser as
      `StructuredRejection(reason="parser_crashed", recoverable=True)`.
- [ ] T3.3 — Emit every metric in requirements.md NFR-3.
- [ ] T3.4 — Emit every log event
      (`webhook.received|verified|dispatched|failed|replay_ignored|deadlettered|configured`).
- [ ] T3.5 — Add trace spans `webhook.ingest`, `webhook.verify`,
      `webhook.parse`, `webhook.dedup`, `webhook.publish`,
      `webhook.deadletter_write`.
- [ ] T3.6 — Background sweeper for expired
      `webhooks_in_seen_deliveries` and
      `webhooks_in_deadletter_index` rows.
- [ ] T3.7 — Load-test at 50 req/s per pod; ack latency p95 < 50 ms,
      ack-to-bus-publish p95 < 150 ms.
- [ ] T3.8 — Sphinx docs for the
      `inbound_webhook_parser` protocol + every reference parser.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS acceptance criterion in
      Requirements 1–5.
- [ ] TT-2 — Hypothesis property tests: Property 1 (parser
      totality), Property 2 (replay de-duplication), Property 3
      (signature tamper resistance), 1000 cases each.
- [ ] TT-3 — Integration test: fake GitHub posts a push, Pychestrate
      verifies, publishes `entity.scm.push`, and
      `6-source-integrations` consumes the event (end-to-end under a
      real message bus).
- [ ] TT-4 — Extension-point test: register a sample
      `pychestrate-ext-webhooks-fixture` parser at
      `PRECEDENCE = 500`, deliver a signed payload, and assert the
      extension parser runs in preference to an in-tree parser when
      names collide.
- [ ] TT-5 — Deadletter replay test: corrupt a fixture payload so it
      triggers `parser_crashed`, fix the parser, replay via
      `:replay` endpoint, assert the normalized event is published
      exactly once.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface has `GithubWebhookParser`,
      `GitlabWebhookParser`, `BitbucketWebhookParser`,
      `GenericHmacWebhookParser` in-tree references and one
      test-only override using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 10 —
      Public Surface & Extensibility Completion in
      specs/implementation-plan.md
