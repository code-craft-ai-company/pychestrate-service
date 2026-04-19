# 8-webhooks-out — Requirements

## Introduction

`8-webhooks-out` is the configuration and signing surface for outbound
state-change notifications delivered as HTTP POSTs to customer-owned
URLs. It is *not* a separate delivery engine — it reuses
`2-notification-hub` as the underlying channel, registering a
`WebhookNotificationChannel` implementation of the
`notification_channel` factory. This feature owns: configuring URL
targets per project, selecting which entity events to forward,
generating and rotating signing secrets, signing each outbound
payload (HMAC-SHA-256 over a canonicalized body plus timestamp), and
surfacing delivery metrics. It sits downstream of `0-message-bus`
(source of entity events) and upstream of any external automation
(CI systems, ChatOps bots, custom dashboards) that consumes
Pychestrate events. This feature ships in **Phase 10 — Public Surface
& Extensibility Completion**.

## Requirements

### Requirement 1: Per-Target Signed Delivery

**User Story:** As a receiver, I want every outbound webhook from
Pychestrate to carry a verifiable signature over the body and a
timestamp, so that I can reject forgeries and replays.

**Acceptance Criteria (EARS):**

1. WHEN the hub dispatches a payload to a configured target THEN the
   HTTP request SHALL include
   `X-Pychestrate-Signature: t=<unix_ts>,v1=<hmac_sha256_hex>`
   where the signed string is
   `"<unix_ts>.<canonical_json_body>"` and the key is the target's
   current signing secret.
2. WHEN a target has both a `current_secret` and a `previous_secret`
   (mid-rotation) THEN the request SHALL include an additional
   `v1-previous=<hmac_sha256_hex>` segment computed with the
   previous secret, enabling zero-downtime secret rotation for
   receivers.
3. IF a signing secret is rotated THEN the system SHALL keep the
   previous secret valid for a grace window of **48 hours** before
   discarding it.
4. WHERE the target URL is `https://` the system SHALL validate the
   TLS certificate chain against the configured trust store and
   SHALL refuse plaintext `http://` targets unless the target is
   explicitly annotated `allow_plaintext=True` (dev-only flag).

### Requirement 2: Event Subscription and Filtering

**User Story:** As a project admin, I want to pick which entity events
get forwarded to each URL target, so that I do not flood receivers
with irrelevant traffic.

**Acceptance Criteria (EARS):**

1. WHEN an admin creates a target with
   `topics=["entity.run.completed", "entity.pod.state_changed"]`
   THEN the system SHALL deliver *only* those topics (plus sub-topics
   via prefix match) to that URL.
2. IF a target's topic list is empty THEN the system SHALL reject the
   create call with `400 Bad Request` code `webhook_out.no_topics`
   (no "all" wildcard — fan-out must be explicit).
3. WHEN a `FilterExpression` (a narrow boolean DSL) is supplied
   alongside the topic list THEN the system SHALL evaluate it
   against the event payload and SHALL deliver only events for
   which it returns `True`; evaluation errors SHALL log and SHALL
   default to *skip* (safer than double-delivery).
4. WHERE a target declares `project_scope=True` the system SHALL
   only forward events tagged with the owning `project_id`.

### Requirement 3: Delivery Reliability and Backoff

**User Story:** As a receiver operator, I want sensible retry
behavior, so that transient 5xx failures do not drop events.

**Acceptance Criteria (EARS):**

1. WHEN a delivery receives `2xx` THEN the attempt SHALL be recorded
   as `status="delivered"` with the observed status code and
   duration.
2. WHEN a delivery receives `5xx`, connection timeout, DNS failure,
   or TLS failure THEN the system SHALL retry with exponential
   backoff starting at 30 s and doubling up to 1 hour, capping at
   **24 attempts**; after the cap the delivery SHALL be marked
   `status="abandoned"`.
3. IF a delivery receives `4xx` (other than `408` or `429`) THEN the
   system SHALL record the failure and SHALL NOT retry — the
   receiver is telling us the payload is permanently unacceptable.
4. WHEN a receiver returns `429 Too Many Requests` with
   `Retry-After` THEN the system SHALL honor the value (capped at
   1 hour) before the next attempt.
5. WHILE a target has three consecutive `abandoned` deliveries the
   system SHALL auto-disable the target, publish
   `entity.webhook.target_disabled`, and notify
   `system:webhook.admin` holders via `2-notification-hub`.

### Requirement 4: Extension Reuse via `notification_channel`

**User Story:** As an implementer, I want outbound webhooks to reuse
the existing channel dispatch machinery, so that there is one path
for email, Slack, PagerDuty, and HTTP targets.

**Acceptance Criteria (EARS):**

1. WHEN `2-notification-hub` initializes THEN a
   `WebhookNotificationChannel` (channel_kind=`http_webhook`) SHALL
   be registered via the `notification_channel` factory protocol at
   `PRECEDENCE = 1000`.
2. IF an alternative HTTP channel (e.g., an mTLS-only variant) is
   registered at a lower `PRECEDENCE` THEN it SHALL replace the
   default per the extension host's last-match-wins semantics.
3. WHEN a target is configured with an extension-supplied channel
   kind THEN the extension's channel SHALL receive the signed
   payload unchanged; signing is an invariant of `8-webhooks-out`,
   not of the channel.

### Requirement 5: Delivery Observability

**User Story:** As a support engineer, I want per-target delivery
history and a way to redrive failed events, so that I can diagnose
why a receiver is missing data.

**Acceptance Criteria (EARS):**

1. WHEN a delivery finalizes (delivered, permanent-4xx, or
   abandoned) THEN the system SHALL persist an entry in
   `webhooks_out_deliveries` with status, status code, attempt
   count, duration, and a truncated response body (first 2 KiB).
2. WHEN an operator calls
   `GET /api/v1/projects/{id}/webhooks/out/{target_id}/deliveries`
   THEN the system SHALL return a paginated list ordered by
   `finalized_at DESC`.
3. WHERE an operator calls
   `POST .../deliveries/{delivery_id}:redrive` the system SHALL
   re-enqueue the original payload to the target unchanged (same
   signature timestamp validity window rules apply receiver-side).

## Property-Based Test Requirements

### Property 1: Signature Determinism and Tamper Sensitivity

- **Invariant:** For any (payload, timestamp, secret) triple, the
  computed signature is deterministic byte-for-byte; for any
  single-bit flip in the payload *or* the timestamp, the signature
  SHALL differ.
- **Generator:** Hypothesis strategy producing random JSON bodies
  up to 64 KiB, random unix timestamps, random 32-byte secrets,
  then a random single-bit mutation position.
- **Assertion:** `sign(p, t, s) == sign(p, t, s)` across two
  computations; `sign(p', t, s) != sign(p, t, s)` and
  `sign(p, t', s) != sign(p, t, s)` for every mutation; hex output
  is lower-case and 64 characters.
- **Sample size:** 1000 generated cases.

### Property 2: Backoff Schedule Monotonicity

- **Invariant:** For any delivery that retries up to 24 times, the
  sequence of next-attempt delays is non-decreasing, starts at
  `>= 30 s`, never exceeds 1 hour, and the total elapsed time
  across the schedule is bounded by the sum of capped delays.
- **Generator:** Strategy producing failure traces of length 1–24
  (mix of 5xx, timeouts, 429-with-Retry-After, 429-without).
- **Assertion:** Every computed next-attempt delay is in
  `[30 s, 3600 s]`, strictly non-decreasing until the 1-hour cap,
  and a `Retry-After` directive overrides only upward (never
  shortens below 30 s).
- **Sample size:** 1000 generated cases.

### Property 3: Topic Filter Totality

- **Invariant:** For any target with topic list
  `T = [t1, t2, ...]` and any entity event with topic `e`, the
  decision to deliver equals "there exists `ti` in `T` such that
  `e` starts with `ti`" — never a crash, never a partial match
  depending on order.
- **Generator:** Strategy producing random topic prefixes and
  random event topics (mix of registered names, random strings,
  empty strings).
- **Assertion:** Decision matches a reference implementation
  `any(e == ti or e.startswith(ti + ".") for ti in T)`; no call
  raises; every decision terminates in bounded time.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Signing a 64 KiB payload SHALL complete
  in `< 1 ms`; dispatching to a target (TLS handshake amortized via
  connection reuse) SHALL complete in `< 500 ms` p95 for an
  external URL. Queue drain rate SHALL sustain `200 events/s` per
  pod.
- **NFR-2 (Security):** Signing secrets SHALL live only in
  `1-secrets-vault`. Signatures SHALL use HMAC-SHA-256 with
  constant-time comparison documented for receivers. Plaintext
  targets SHALL be refused by default. Outbound sockets SHALL
  honor a 30-second request timeout so misbehaving receivers
  cannot starve the dispatcher. Audit log records every target
  mutation and every secret rotation.
- **NFR-3 (Observability):** Emit
  `pychestrate_webhook_dispatched_total{target,status}`,
  `pychestrate_webhook_dispatch_duration_seconds` (histogram),
  `pychestrate_webhook_retry_total{target}`,
  `pychestrate_webhook_abandoned_total{target}`,
  `pychestrate_webhook_targets_enabled` (gauge),
  `pychestrate_webhook_signing_duration_seconds`, and log events
  `webhook.dispatched`, `webhook.failed`, `webhook.retry_scheduled`,
  `webhook.target_disabled`, `webhook.secret_rotated`. Trace spans:
  `webhook.sign`, `webhook.dispatch`, `webhook.receive_response`.
- **NFR-4 (Reliability):** A receiver's downtime SHALL NOT block
  other receivers — dispatch is per-target concurrent with a
  per-target queue. Process restart SHALL resume in-flight
  deliveries from their persisted state; no duplicates beyond the
  retry semantics.

## Out of Scope

- Inbound trigger endpoints — owned by `8-webhooks-in`.
- Email / Slack / PagerDuty channels — owned by
  `2-notification-hub`.
- Notification *templates* (rendering) — `2-notification-hub`
  resource surface; this feature delivers raw canonical JSON.
- Kafka / SQS / other non-HTTP channels — scope for future
  `8-webhooks-out-extensions`.

## Dependencies

- **Depends on:** `2-notification-hub`, `0-message-bus`,
  `1-secrets-vault` (signing secrets), `1-audit-log`,
  `8-rest-api-v1` (target CRUD endpoints).
- **Depended on by:** external automation consumers; no internal
  features depend on this.
- **Extension points exposed:** Reuses
  `factory: notification_channel` from `2-notification-hub` —
  ships `WebhookNotificationChannel` at `PRECEDENCE = 1000`.
  Events: `entity.webhook.dispatched`, `entity.webhook.failed`,
  `entity.webhook.retry_scheduled`,
  `entity.webhook.target_disabled`, `entity.webhook.secret_rotated`.
  See implementation-plan.md Layer 8.
