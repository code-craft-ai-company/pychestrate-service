# 2-notification-hub — Tasks

## Milestones

- **M1 — Skeleton:** Channel + rule + preference tables; channel
  registration; `notification_channel` protocol declared;
  `SmtpEmailChannel` reference impl; a hard-coded in-tree
  `RunFailedTemplate`; routing subscriber receiving `entity.run.failed`
  and dispatching via SMTP.
- **M2 — Core Behavior:** Slack/Teams/PagerDuty/webhook reference
  channels; full per-project routing rules CRUD; per-user preferences
  with quiet hours; templates registered via extension; dead-letter
  queue + replay; `entity.notification.dispatched|failed` emission.
- **M3 — Hardening:** Rate limiting + digests; secret-ref resolution
  for channel config; observability; extension collision detection;
  Phase-1 exit-criterion end-to-end test with an out-of-tree channel.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Migration for `notification_channels`,
      `notification_routing_rules`,
      `user_notification_preferences`,
      `dispatch_envelopes`, `dispatch_attempts`, `dead_letters`.
- [ ] T1.2 — Implement `entities.py` dataclasses + enums.
- [x] T1.3 — Declare `NotificationChannelProtocol` in `factories.py`.
      *Done in `factories/channel.py`; since 2026-10-15 a kind also declares its
      settings (`config_fields`, which are secret) and its labels.*
- [x] T1.4 — Ship `SmtpEmailChannel` reference impl.
- [x] T1.5 — Implement `service.register_channel` and the channel
      CRUD REST endpoints.
      *Done as `service.create_channel`, `update_channel` (switch, settings,
      secrets), `delete_channel` and `send_test_message`, with
      `POST|GET|PATCH|DELETE /api/v1/notifications/channels` and `POST .../test`,
      and the Admin, Notifications page (2026-10-15, audit ORG-F08). Not done:
      project-scoped channels in the page (the API takes `scope_level`).*
- [x] T1.6 — Implement a hard-coded in-tree `RunFailedTemplate` as
      the first `NotificationTemplateExtension`.
- [x] T1.7 — Implement `subscriber.py` wildcard bus subscription and
      wire it to `router.compute_routes` → `dispatcher.dispatch`.
      *Done as `run_notifier.py`: subscribes to `entity.run.failed` and
      `entity.run.completed` (not a wildcard), queues events, and one daemon
      thread per process delivers them, so sending never runs in the request
      that commits the run's end; wired from `bootstrap_phase2_runtime`.*
- [x] T1.8 — Implement a minimal `router.compute_routes` (no tag
      filter, no preferences) for M1 end-to-end smoke.
      *Done in `router.py`, with event-pattern globs, a template-versus-event
      guard and a per-rule, per-process rate limit.*

### M2 — Core Behavior

- [x] T2.1 — Ship `SlackWebhookChannel`, `MsTeamsWebhookChannel`,
      `PagerDutyEventsV2Channel`, `GenericWebhookChannel` reference
      impls.
- [ ] T2.2 — Implement `service.create_routing_rule` and routing rule
      CRUD endpoints including `filter_tag_expression` validation
      against `2-tagging`.
      *Partly: `/api/v1/notifications/routing-rules` (create, list, disable or
      enable, delete; system administrators). Not done: the project-scoped path
      of Requirement 2, project-owner permissions, tag filters (refused, not
      ignored).*
- [ ] T2.3 — Implement `service.update_user_preferences` and
      `GET/PUT /users/me/notification-preferences`.
- [ ] T2.4 — Expand `router.compute_routes` to honor rule event-pattern
      globs, tag filters, preferences, quiet hours, and severity
      bypass.
- [ ] T2.5 — Implement `NotificationTemplateExtension` base and the
      template registry; load via `E-resource-extensions`.
- [ ] T2.6 — Ship `RunSucceededTemplate` and
      `ProjectMemberAddedTemplate` in-tree.
      *`RunSucceededTemplate` (`run_succeeded`, for `entity.run.completed`)
      is done; `ProjectMemberAddedTemplate` is not.*
- [ ] T2.7 — Implement DLQ persistence, retry backoff, and the
      `GET/DELETE /notifications/dead-letter` endpoints.
- [ ] T2.8 — Implement `POST /notifications/dead-letter/{id}/replay`
      with `notification.dlq.replay` permission check.
- [ ] T2.9 — Publish `entity.notification.dispatched|failed` events.

### M3 — Hardening

- [ ] T3.1 — Implement `rate_limiter.py` per-recipient sliding window
      and digest buffer with 60 s flush.
- [ ] T3.2 — Implement `digest.py` rendering.
- [x] T3.3 — Resolve channel config secret refs at send time; ensure
      plaintext never leaves the dispatcher.
      *Changed 2026-10-15: through the secrets vault directly
      (`read_secret_for_service`), not the variables module's stub
      `secret_ref_dereferencer`. See design.md, Security Considerations.*
- [ ] T3.4 — Subscribe to `entity.project.deleted` and
      `entity.user.deleted` to scrub rules, channels, and prefs.
- [ ] T3.5 — Emit all metrics, logs, and trace spans listed in
      design.md Observability.
- [ ] T3.6 — Extension collision test: two
      `NotificationTemplateExtension`s with the same
      `template_name` and equal `PRECEDENCE` refuse startup with
      a readable `ConfigurationError`.
- [ ] T3.7 — Channel worker-pool configuration; sized via service
      config, graceful drain on shutdown.
- [ ] T3.8 — Add Flask rate-limiter rules for channel / rule /
      preference endpoints.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in
      requirements.md (Requirements 1–6).
- [ ] TT-2 — Property-based tests for Property 1 (pure routing
      determinism) and Property 2 (rate limiter conservation) using
      `hypothesis.stateful`.
- [ ] TT-3 — Integration test with a mock SMTP and mock Slack:
      simulate 200 `entity.run.failed` events/min, verify rate
      limiting defers to digest, DLQ captures injected SMTP
      failures, replay returns them to delivery.
- [ ] TT-4 — Extension-point test — Phase 1 exit criterion: an
      out-of-tree `pychestrate-ext-discord` registers a new
      `notification_channel` and a routing rule targets it; a test
      event produces a successful dispatch.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (`notification_channel`,
      `NotificationTemplateExtension`) has five in-tree channel
      reference impls, three template reference impls, and one
      test-only override per protocol at a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 1 in
      specs/implementation-plan.md
