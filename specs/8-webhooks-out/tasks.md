# 8-webhooks-out — Tasks

## Milestones

- **M1 — Skeleton:** Target CRUD endpoints, `WebhookNotificationChannel`
  registered via `notification_channel` factory, signing function
  operational, single-target delivery on one topic.
- **M2 — Core Behavior:** Topic-prefix matching,
  `FilterExpression` evaluation, secret rotation with 48 h grace,
  delivery history + redrive endpoint, auto-disable after three
  consecutive abandoned deliveries, honor `Retry-After`.
- **M3 — Hardening:** Full metric/log/trace coverage, URL policy
  enforcement, 200 events/s sustained drain, Sphinx docs,
  extension-override test.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Land `webhooks_out_targets`,
      `webhooks_out_deliveries`, `webhooks_out_secret_rotations`
      tables via an `EntityMigrationExtension` pack.
- [ ] T1.2 — Implement `target_service.create_target`,
      `update_target`, `delete_target`, `list_targets`, `get_target`.
- [ ] T1.3 — Implement `signing.sign_payload` with
      HMAC-SHA-256 and deterministic canonical JSON body encoding.
- [ ] T1.4 — Implement `WebhookNotificationChannel.deliver` using
      the shared HTTP client with 30 s timeout.
- [ ] T1.5 — Register `HttpWebhookChannel` as a
      `notification_channel` factory implementation at
      `PRECEDENCE = 1000`.
- [ ] T1.6 — Wire `/api/v1/projects/{id}/webhooks/out` CRUD
      controllers.

### M2 — Core Behavior

- [ ] T2.1 — Implement `filter_engine.decide_delivery` with
      topic-prefix match and optional `FilterExpression` evaluation;
      default-to-skip on evaluation error.
- [ ] T2.2 — Implement `target_service.rotate_secret` with 48 h
      grace-window semantics; emit `entity.webhook.secret_rotated`.
- [ ] T2.3 — Extend `signing.sign_payload` to emit both `v1` and
      `v1-previous` segments when `previous_secret` is set and
      still in window.
- [ ] T2.4 — Implement retry backoff in the hub adapter — 30 s start,
      doubling, 1 h cap, 24-attempt limit, honor `Retry-After`.
- [ ] T2.5 — Implement `delivery_recorder.record_attempt` with
      consecutive-abandoned counter and auto-disable at 3.
- [ ] T2.6 — Wire
      `POST .../webhooks/out/{target_id}:rotate_secret`,
      `POST .../webhooks/out/{target_id}:test` (synthetic
      `entity.webhook.test` event), and redrive endpoint.
- [ ] T2.7 — Enforce URL allow/deny policy from
      `2-global-variables` key `webhooks.out.url_policy` at create
      and update time.
- [ ] T2.8 — Refuse plaintext `http://` unless
      `allow_plaintext=True`; emit gauge
      `pychestrate_webhook_plaintext_targets_total`.

### M3 — Hardening

- [ ] T3.1 — Emit every metric in requirements.md NFR-3.
- [ ] T3.2 — Emit every log event
      (`webhook.dispatched|failed|retry_scheduled|target_disabled|secret_rotated|target_created|target_updated|target_deleted`).
- [ ] T3.3 — Add trace spans `webhook.sign`, `webhook.filter`,
      `webhook.dispatch`, `webhook.receive_response`,
      `webhook.record_attempt`.
- [ ] T3.4 — Persist dispatcher in-flight state so process restart
      resumes deliveries exactly-once-per-retry-slot.
- [ ] T3.5 — Background sweep for expired previous secrets
      (clears `previous_secret_ref` after
      `previous_secret_valid_until`).
- [ ] T3.6 — Load-test 200 events/s per pod; verify p95 dispatch
      < 500 ms against an external sink.
- [ ] T3.7 — Sphinx docs for target CRUD + signing contract +
      receiver verification example code.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS acceptance criterion in
      Requirements 1–5.
- [ ] TT-2 — Hypothesis property tests: Property 1 (signature
      determinism + tamper sensitivity), Property 2 (backoff
      monotonicity), Property 3 (topic-filter totality), 1000 cases
      each.
- [ ] TT-3 — Integration test: create a target, drive three
      `entity.run.completed` events through `0-message-bus`, assert
      receiver sees three signed POSTs each verifying under the
      current secret.
- [ ] TT-4 — Extension-point test: override
      `HttpWebhookChannel` with a fixture
      `MtlsHttpWebhookChannel` at `PRECEDENCE = 500`, assert
      deliveries route through the override while signing
      invariants remain intact.
- [ ] TT-5 — Rotation test: rotate secret mid-flight, assert
      in-flight retries remain verifiable with the previous
      secret until the 48 h window expires.
- [ ] TT-6 — Auto-disable test: fail three consecutive 24-attempt
      chains, assert target transitions to disabled and the
      `system:webhook.admin` notification fires.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface: `HttpWebhookChannel` reference registered
      via `notification_channel`; at least one test-only override
      using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs including
      a receiver-side verification code example
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 10 —
      Public Surface & Extensibility Completion in
      specs/implementation-plan.md
