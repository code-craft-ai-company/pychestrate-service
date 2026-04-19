# 8-webhooks-in — Requirements

## Introduction

`8-webhooks-in` is Pychestrate's inbound trigger surface — HTTP endpoints
that accept provider-authored POSTs (SCM push/PR events, bug-tracker
state transitions, external schedulers, alerting platforms) and convert
them into normalized Pychestrate events. Each provider type plugs in
through the `inbound_webhook_parser` factory protocol; new providers
are added without forking. It sits downstream of `8-rest-api-v1`
(sharing its dispatch pipeline) and upstream of `0-message-bus`, which
fans the normalized events out to consuming features (e.g.,
`6-source-integrations` listens for SCM events, `6-triage-bug-linking`
listens for bug-tracker events). This feature ships in **Phase 10 —
Public Surface & Extensibility Completion**.

## Requirements

### Requirement 1: Per-Provider Signature Verification

**User Story:** As an operator wiring GitHub/GitLab/Jira webhooks, I want
Pychestrate to verify each provider's native signature, so that forged
traffic cannot trigger jobs.

**Acceptance Criteria (EARS):**

1. WHEN a `POST /api/v1/webhooks/in/<provider>/<hook_name>` arrives
   THEN the system SHALL resolve the configured
   `inbound_webhook_parser` for `provider`, fetch the shared secret
   via `1-secrets-vault` under key
   `webhooks.in.<provider>.<hook_name>.secret`, and verify the
   signature header declared by the parser before invoking any
   handler.
2. IF signature verification fails THEN the system SHALL respond
   `401 Unauthorized`, publish `entity.webhook.failed` with
   `reason="signature_invalid"`, SHALL NOT publish any domain event,
   and SHALL increment
   `pychestrate_webhook_rejections_total{provider,reason}`.
3. WHEN a parser declares multiple accepted signature algorithms
   (e.g., GitHub offers both `X-Hub-Signature-256` and
   `X-Hub-Signature`) THEN the system SHALL require at least one
   strong algorithm (SHA-256 or better) to match; weak-only
   signatures SHALL be rejected with `reason="signature_weak"`.
4. WHERE the configured hook instance is annotated
   `require_mtls=True` the system SHALL additionally require the
   request to arrive over mTLS with a client certificate whose
   `Subject` is in the parser's allow-list.

### Requirement 2: Parser Totality and Structured Rejection

**User Story:** As a reliability-focused engineer, I want the parser
layer to be total — every input either parses or returns a structured
rejection, so that malformed payloads never crash the ingest path.

**Acceptance Criteria (EARS):**

1. WHEN an `inbound_webhook_parser` is invoked THEN it SHALL return
   either `ParsedWebhook` or `StructuredRejection`; any uncaught
   exception SHALL be caught at the framework boundary and
   reclassified as
   `StructuredRejection(reason="parser_crashed", detail=...)`.
2. IF a payload's declared `Content-Type` is not in the parser's
   accepted set THEN the system SHALL respond `415 Unsupported Media
   Type` with a `problem+json` body listing the accepted media
   types.
3. WHEN a `StructuredRejection` is produced THEN the system SHALL
   respond `400 Bad Request` with
   `{reason, detail, recoverable: bool}`, SHALL publish
   `entity.webhook.failed`, and SHALL NOT publish any downstream
   domain event.
4. WHERE the parser returns `recoverable=True` the dispatcher SHALL
   store the raw payload for 7 days under
   `webhooks_in_deadletter/<provider>/<hook_name>/<request_id>` on
   `0-object-store` so operators can replay after fixing the parser.

### Requirement 3: Replay Protection and Idempotent Fan-Out

**User Story:** As an operator, I want duplicate deliveries (which all
providers retry) to be de-duplicated, so that a single upstream event
does not spawn multiple runs.

**Acceptance Criteria (EARS):**

1. WHEN a parser extracts a provider-native delivery id (e.g.,
   GitHub's `X-GitHub-Delivery`) THEN the system SHALL record
   `(provider, hook_name, delivery_id)` in
   `webhooks_in_seen_deliveries` with a 72-hour TTL and SHALL treat
   subsequent deliveries of the same tuple as replays.
2. WHILE a delivery is recognized as a replay the system SHALL
   respond `200 OK` with `{status: "replay_ignored"}` and SHALL NOT
   publish any domain event.
3. IF two concurrent deliveries share the same `(provider,
   hook_name, delivery_id)` THEN the system SHALL serialize them
   via row-level insert contention and exactly one SHALL produce
   the domain event.

### Requirement 4: End-to-End Ingest Latency Budget

**User Story:** As an SRE watching downstream fan-out, I want a tight
ingest-latency bound, so that a GitHub webhook becomes a run dispatch
in under 150 ms p95 end-to-end.

**Acceptance Criteria (EARS):**

1. WHEN a verified, non-replay webhook is received THEN the system
   SHALL acknowledge the provider with a `2xx` response in
   `< 50 ms` p95 measured from request arrival to first response
   byte.
2. WHERE the parser emits more than one domain event from a single
   payload (e.g., a GitHub `pull_request.synchronize` that
   represents multiple commits) the system SHALL publish all events
   within the same message-bus transaction and SHALL NOT partially
   publish if any event fails validation.

### Requirement 5: Provider Registration and Configuration

**User Story:** As an admin, I want to enumerate and configure inbound
webhook endpoints per project, so that each project owns its own SCM
wiring.

**Acceptance Criteria (EARS):**

1. WHEN an admin calls
   `POST /api/v1/projects/{project_id}/webhooks/in` with
   `{provider, hook_name, secret_ref, mtls_required}` THEN the
   system SHALL persist the configuration and publish
   `entity.webhook.configured`.
2. WHEN the inbound URL is fetched with `GET .../webhooks/in/{id}`
   THEN the response SHALL include the exact URL to configure at the
   provider plus the list of headers the parser inspects.
3. IF the named provider has no registered `inbound_webhook_parser`
   factory THEN the configuration call SHALL fail `400 Bad Request`
   code `webhook.unknown_provider`.

## Property-Based Test Requirements

### Property 1: Parser Totality

- **Invariant:** For any byte sequence of size `[0, 1_048_576]` bytes
  with any header map, every registered `inbound_webhook_parser`
  SHALL terminate in either `ParsedWebhook` or `StructuredRejection`;
  no call SHALL raise, hang beyond the parser timeout, or return
  `None`.
- **Generator:** Hypothesis strategy producing `(provider,
  raw_bytes, headers)` triples; raw bytes drawn from a mix of valid
  fixture payloads, corrupted valid payloads (bit-flipped), random
  bytes, and pathologically large bodies.
- **Assertion:** Each invocation returns one of the two types; a
  uniform `StructuredRejection(reason="parser_crashed")` is produced
  by the framework if an exception escapes the parser; total
  parse+reject wall clock stays within the 100 ms parser budget.
- **Sample size:** 1000 generated cases.

### Property 2: Replay De-Duplication

- **Invariant:** For any stream of deliveries with delivery-id
  collisions, the number of published domain events equals the
  number of *distinct* delivery ids observed, regardless of
  ordering or concurrency.
- **Generator:** Strategy producing delivery streams of length
  `[1, 200]` with delivery-id repetition rates drawn from `[0, 0.5]`,
  delivered by `[1, 16]` concurrent workers.
- **Assertion:** `published_events_count == distinct_delivery_ids`;
  duplicate responses carry `{status: "replay_ignored"}`; no race
  produces zero events for a distinct id.
- **Sample size:** 1000 generated cases.

### Property 3: Signature Tamper Resistance

- **Invariant:** For any valid `(payload, signature)` pair, any
  single-bit flip in `payload`, any single-bit flip in the signature
  header, or swapping the signature to the hash of a different
  payload SHALL cause verification to fail and the request to be
  rejected `401`.
- **Generator:** Strategy producing signed payloads for each
  registered parser, then producing a single tampering mutation
  (flip | swap | truncate | extend) at a random byte offset.
- **Assertion:** 100% of tampered requests reject with
  `reason="signature_invalid"`; no tampered request publishes a
  domain event.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Webhook acknowledgement latency SHALL be
  `< 50 ms` p95, measured from TCP accept to first response byte,
  at a steady-state load of 50 req/s per pod. End-to-end
  ack-to-bus-publish latency SHALL be `< 150 ms` p95.
- **NFR-2 (Security):** Signature verification SHALL use constant-time
  comparison. Shared secrets SHALL live only in `1-secrets-vault`
  and SHALL NEVER be written to logs or traces. Raw payloads stored
  in the deadletter bucket SHALL be encrypted at rest via the
  object store driver's default encryption. Rate limit anonymous
  ingest at `100 req/s` per source IP.
- **NFR-3 (Observability):** Emit
  `pychestrate_webhook_received_total{provider,hook_name,outcome}`,
  `pychestrate_webhook_ingest_duration_seconds` (histogram),
  `pychestrate_webhook_rejections_total{provider,reason}`,
  `pychestrate_webhook_replays_total{provider}`,
  `pychestrate_webhook_deadletters_total{provider}`,
  and log events `webhook.received`, `webhook.verified`,
  `webhook.dispatched`, `webhook.failed`, `webhook.replay_ignored`.
  Trace spans: `webhook.ingest`, `webhook.verify`, `webhook.parse`,
  `webhook.publish`.
- **NFR-4 (Reliability):** A provider's parser failure SHALL NOT
  affect any other provider's ingest; parsers run with a 100 ms
  wall-clock budget and are cancelled past it with a
  `StructuredRejection(reason="parser_timeout")`. Deadletter writes
  SHALL not block the response path.

## Out of Scope

- Outbound state-change notifications — owned by `8-webhooks-out`.
- SCM semantic handling (what a GitHub `push` *means*) — owned by
  `6-source-integrations`, which subscribes to the normalized
  events published here.
- Bug-tracker semantic handling — owned by `6-triage-bug-linking`.
- Provider-side configuration (installing the webhook on GitHub)
  — operator responsibility, not automated by Pychestrate.

## Dependencies

- **Depends on:** `8-rest-api-v1` (dispatch pipeline),
  `1-authentication`, `1-secrets-vault` (shared secrets),
  `0-message-bus`, `0-object-store` (deadletter storage),
  `E-extension-host`, `E-factory-protocols`.
- **Depended on by:** `6-source-integrations`,
  `6-triage-bug-linking`, `7-alerts-budgets` (for external alerting
  integrations).
- **Extension points exposed:**
  `factory: inbound_webhook_parser` (per provider); reference
  implementations `GithubWebhookParser`, `GitlabWebhookParser`,
  `BitbucketWebhookParser`, `GenericHmacWebhookParser`. Events:
  `entity.webhook.received`, `entity.webhook.dispatched`,
  `entity.webhook.failed`, `entity.webhook.replay_ignored`. See
  implementation-plan.md Layer 8.
