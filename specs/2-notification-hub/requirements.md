# 2-notification-hub — Requirements

## Introduction

`2-notification-hub` is the central router that turns Pychestrate events
into user-visible notifications across email, Slack, Microsoft Teams,
PagerDuty, and generic webhook channels. It pairs three concerns: a
**channel registry** populated by the `notification_channel` factory
protocol, a **template registry** populated by
`NotificationTemplateExtension`, and a **routing engine** that combines
per-project routing rules with per-user channel preferences. The hub also
handles dead-letter buffering on channel failure and enforces per-recipient
rate limiting so a misbehaving alert storm cannot page an on-call engineer
500 times in a minute. It ships in **Phase 1 — Identity & Projects** and
sits between `0-message-bus` (source of events) and every feature that
needs to notify a human (`7-alerts-budgets`, `6-build-orchestration` failure
callbacks, etc.).

## Requirements

### Requirement 1: Channel registration and dispatch

**User Story:** As a platform admin, I want to register channels (Slack
webhook URLs, SMTP relay, PagerDuty integration keys) so that events can
be routed to the right destination type.

**Acceptance Criteria (EARS):**

1. WHEN `POST /api/v1/notifications/channels` is received with a valid
   body including `kind` (registered `notification_channel` name) and
   `config` matching that channel's config schema THEN the system
   SHALL persist a `NotificationChannel` row and return `201 Created`.
2. IF `kind` is not a registered `notification_channel` factory name
   THEN the system SHALL respond `400 Bad Request` listing known
   kinds.
3. WHEN a `DispatchEnvelope` is routed to a channel THEN the system
   SHALL call the channel impl's `send` classmethod with the
   rendered template, timeout at `channel.max_send_seconds`, and
   record the result (`delivered` / `failed`) with latency.

### Requirement 2: Per-project routing rules

**User Story:** As a project owner, I want to set routing rules like "any
`entity.run.failed` event on `environment:prod` tagged jobs pages on-call
and posts to `#team-ci`", so that the right people hear about the right
events.

**Acceptance Criteria (EARS):**

1. WHEN `POST /api/v1/projects/{slug}/notification-rules` is received
   with a body `{event_pattern, filter_tag_expr?, recipients,
   channels, template_name, rate_limit?}` THEN the system SHALL
   persist a `NotificationRoutingRule` scoped to the project.
2. WHEN an event is published on the message bus matching a rule's
   `event_pattern` AND its entity carries tags satisfying
   `filter_tag_expr` THEN the routing engine SHALL fan-out one
   `DispatchEnvelope` per `(recipient, channel)` tuple.
3. IF the effective routing set is empty for an event THEN the system
   SHALL NOT dispatch and SHALL record a
   `pychestrate_notify_no_route_total` counter increment — silent
   drop is the intended behavior but it is observable.

### Requirement 3: Per-user channel preferences

**User Story:** As an engineer, I want to set my personal preferences —
"email for all my project events, Slack DM for failures, no PagerDuty
outside working hours unless severity is critical" — so that routing
rules never override my personal contact policy.

**Acceptance Criteria (EARS):**

1. WHEN `PUT /api/v1/users/me/notification-preferences` is received
   with a body describing `{per_topic: {channel_kind: enabled}}` plus
   optional `quiet_hours` (timezone + window) THEN the system SHALL
   persist the preference set.
2. IF a recipient's preference disables the channel kind for the
   current topic THEN the system SHALL SKIP dispatch to that
   `(recipient, channel)` tuple and record a
   `pychestrate_notify_skipped_total{reason="user_pref"}` increment.
3. WHERE the event's declared `severity >= critical` THEN the system
   SHALL bypass `quiet_hours` but SHALL still honor explicit
   per-topic disables.

### Requirement 4: Rate limiting per recipient

**User Story:** As an on-call engineer, I want no more than 5 pages per
minute from Pychestrate, so that an alert storm doesn't exhaust my
PagerDuty incidents or drown me in noise.

**Acceptance Criteria (EARS):**

1. WHILE a recipient has been dispatched to more than
   `recipient_rate_limit_per_minute` times in the last 60 seconds
   THEN additional dispatches to that recipient SHALL be deferred to
   a digest envelope and SHALL record
   `pychestrate_notify_rate_limited_total`.
2. WHEN a digest envelope fires THEN it SHALL combine suppressed
   events into a single rendered template and reset the per-recipient
   counter.
3. WHERE the source event has `severity == critical` THEN the rate
   limiter SHALL NOT defer and SHALL still dispatch immediately
   while still recording the override.

### Requirement 5: Dead-letter handling on channel failure

**User Story:** As a platform operator, I want failed dispatches to land
in a dead-letter queue with retry and inspection, so that a Slack outage
doesn't silently lose messages.

**Acceptance Criteria (EARS):**

1. WHEN a channel `send` call raises a recoverable error THEN the
   system SHALL record a `DispatchAttempt(outcome=failed)`, enqueue a
   retry with exponential backoff up to `max_retries`, and emit
   `entity.notification.failed` after the retries are exhausted.
2. WHILE a `DispatchEnvelope` is in the dead-letter queue THEN
   `GET /api/v1/notifications/dead-letter` SHALL list it with the
   last error message and the retry history.
3. WHEN `POST /api/v1/notifications/dead-letter/{id}/replay` is
   received THEN the system SHALL re-enqueue a fresh attempt with
   retry counter reset; IF the caller lacks
   `notification.dlq.replay` THEN `403 Forbidden`.

### Requirement 6: Template extension registration

**User Story:** As an extension author, I want to ship a
`NotificationTemplateExtension` that defines a named template for my
event type, so that notifications have consistent rendering without
inline string literals.

**Acceptance Criteria (EARS):**

1. WHEN the host loads a `NotificationTemplateExtension` subclass
   with `template_name = X` THEN the system SHALL register `X` in
   the template registry.
2. IF two subclasses share `template_name` with equal `PRECEDENCE`
   THEN the service SHALL raise `ConfigurationError` at startup.
3. WHEN a routing rule references an unknown template name THEN
   rule publication SHALL fail with `400 Bad Request` at create
   time rather than at dispatch time.

## Property-Based Test Requirements

### Property 1: Routing fan-out is pure and deterministic

- **Invariant:** For any fixed set of rules, preferences, and an input
  event, `compute_routes(event, rules, preferences)` returns the same
  list of `(recipient, channel, template_name)` tuples in the same
  order regardless of invocation count.
- **Generator:** `hypothesis.strategies.builds` producing random rule
  sets (0–20 rules), random preference maps, and random events with
  tags and severities.
- **Assertion:** Calling `compute_routes` 1000 times on the same input
  produces byte-equal outputs.
- **Sample size:** 1000 generated cases.

### Property 2: Rate limiter preserves total event count via digests

- **Invariant:** For any stream of N dispatches targeting a single
  recipient within a minute, the count of delivered envelopes plus
  deferred-to-digest events plus per-minute limit SHALL equal N —
  i.e., no event is silently dropped.
- **Generator:** `hypothesis.stateful` simulating dispatch arrivals
  at random times in a 60-second window with random severities.
- **Assertion:** `delivered_count + deferred_count == N` across 1000
  runs, confirming conservation.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Routing decision p95 ≤ 20 ms per event with
  100 active rules; end-to-end dispatch-to-delivery-to-channel p95
  ≤ 2 s for non-failing channels.
- **NFR-2 (Security):** Channel write requires `notification.channel.write`;
  routing rule write requires `project.notification.rule.write`;
  preferences are self-only (a user can only edit their own).
  Channel config may include secret references — resolved via
  `1-secrets-vault`; plaintext secrets never appear in REST responses
  or logs.
- **NFR-3 (Observability):** Counters
  `pychestrate_notify_dispatched_total{channel_kind}`,
  `pychestrate_notify_delivered_total{channel_kind}`,
  `pychestrate_notify_failed_total{channel_kind,reason}`,
  `pychestrate_notify_rate_limited_total{recipient_hash}`,
  `pychestrate_notify_skipped_total{reason}`,
  `pychestrate_notify_no_route_total{topic}`,
  `pychestrate_notify_dlq_size`;
  histograms `pychestrate_notify_route_duration_seconds`,
  `pychestrate_notify_send_duration_seconds{channel_kind}`;
  log events `notification.routed`, `notification.dispatched`,
  `notification.delivered`, `notification.failed`,
  `notification.dlq_enqueued`, `notification.dlq_replayed`;
  trace spans `notify.route`, `notify.dispatch`, `notify.send`.
- **NFR-4 (Reliability):** Dead-letter queue persists across restarts.
  Dispatch attempts are idempotent — identical retries for the same
  `DispatchEnvelope` do not double-send (idempotency key scoped to
  `envelope_id`). Channel outages SHALL NOT block the routing
  engine; sends are worker-pool async.

## Out of Scope

- SMS delivery — deferred; add by writing a new
  `notification_channel` impl.
- Rich interactive Slack threads with response handling — deferred
  to a future feature.
- End-user-managed project templates — covered by
  `2-project-templates`.

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`, `1-authentication`,
  `1-rbac`, `1-audit-log`, `1-secrets-vault`, `2-projects`,
  `2-tagging` (for rule filter expressions),
  `2-global-variables` (for channel-config interpolation).
- **Depended on by:** `7-alerts-budgets`, `6-source-integrations`
  (PR / commit-status posts), `8-webhooks-out`.
- **Extension points exposed:**
  `factory: notification_channel`;
  `resource: NotificationTemplateExtension`;
  `event: entity.notification.dispatched|failed`.
