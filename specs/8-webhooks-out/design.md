# 8-webhooks-out — Design

## Architecture

`8-webhooks-out` lives under
`source/site/ccai/pychestrate/webservice/webhooks/outbound/`. It
is the *surface* for outbound URL targets — configuration CRUD,
topic filtering, payload signing, and the `WebhookNotificationChannel`
implementation of `2-notification-hub`'s `notification_channel`
factory. The dispatch engine itself (retry scheduler, per-target
queue, connection pool) belongs to `2-notification-hub`; this feature
merely plugs in as a channel kind. The authoritative state of
targets lives in `webhooks_out_targets` in `0-persistence`; per-event
delivery history lives in `webhooks_out_deliveries`. Signing is a
pure function over `(timestamp, canonical_body, secret)` and is
invoked by the channel just before handing bytes to the HTTP
transport. This feature ships in **Phase 10 — Public Surface &
Extensibility Completion**.

## Data Model

`webhooks_out_targets` table:

- `target_id: UUID` — PK.
- `project_id: UUID` — FK → `projects.project_id`.
- `target_name: str` — human label, unique per project.
- `target_url: str` — `https://...` (or `http://` with
  `allow_plaintext=True`).
- `topics: list[str]` — topic prefixes to forward.
- `filter_expression: Optional[str]` — narrow boolean DSL.
- `current_secret_ref: str`, `previous_secret_ref: Optional[str]`.
- `previous_secret_valid_until: Optional[datetime]`.
- `allow_plaintext: bool`, `project_scope: bool`.
- `channel_kind: str` — default `http_webhook`; overridden by
  extensions.
- `enabled: bool`, `consecutive_abandoned: int`.
- `created_at: datetime`, `created_by: UUID`,
  `last_modified_at: datetime`.
- Unique on `(project_id, target_name)`.
- Index: `(project_id, enabled)`.

`webhooks_out_deliveries` table:

- `delivery_id: UUID` — PK.
- `target_id: UUID` — FK.
- `event_topic: str`, `event_id: UUID`, `event_payload_ref: str`
  (points to the in-message-bus persistence).
- `timestamp_seconds: int` — the timestamp signed into the
  delivery.
- `attempt_count: int`, `status: DeliveryStatus`
  (`pending | delivered | retrying | abandoned | permanent_4xx`),
  `last_status_code: Optional[int]`,
  `last_duration_seconds: Optional[float]`,
  `truncated_response_body: Optional[bytes]`,
  `finalized_at: Optional[datetime]`.
- Index: `(target_id, finalized_at)`, `(status, finalized_at)`.

`webhooks_out_secret_rotations` table:

- `target_id: UUID`, `rotation_id: UUID` — composite PK.
- `rotated_at: datetime`, `rotated_by: UUID`,
  `old_secret_ref: str`, `new_secret_ref: str`,
  `old_secret_valid_until: datetime`.

## Interfaces

### Public API

- `GET /api/v1/projects/{project_id}/webhooks/out` — list targets.
- `POST /api/v1/projects/{project_id}/webhooks/out` — create target
  `{target_name, target_url, topics[], filter_expression?,
  allow_plaintext?, project_scope?, channel_kind?}`.
- `GET /api/v1/projects/{project_id}/webhooks/out/{target_id}` —
  detail.
- `PATCH /api/v1/projects/{project_id}/webhooks/out/{target_id}` —
  update.
- `DELETE /api/v1/projects/{project_id}/webhooks/out/{target_id}` —
  remove.
- `POST /api/v1/projects/{project_id}/webhooks/out/{target_id}:rotate_secret` —
  issue a new signing secret; previous secret remains valid for 48 h.
- `POST /api/v1/projects/{project_id}/webhooks/out/{target_id}:test` —
  deliver a synthetic `entity.webhook.test` event.
- `GET /api/v1/projects/{project_id}/webhooks/out/{target_id}/deliveries` —
  paginated history.
- `POST /api/v1/projects/{project_id}/webhooks/out/{target_id}/deliveries/{delivery_id}:redrive` —
  re-enqueue a delivery unchanged.

### Internal API

Module `ccai.pychestrate.webservice.webhooks.outbound.signing`:

```python
def sign_payload(
        *,
        canonical_body: bytes,
        timestamp_seconds: int,
        current_secret: SecretBytes,
        previous_secret: Optional[SecretBytes]
    ) -> str:
    """
        Return the `X-Pychestrate-Signature` header value.

        :returns: Header value string
            `"t=<ts>,v1=<hex>[,v1-previous=<hex>]"`.
    """
    ...
```

Module
`ccai.pychestrate.webservice.webhooks.outbound.target_service`:

```python
def create_target(
        *,
        project_id: UUID,
        target_name: str,
        target_url: str,
        topics: list[str],
        filter_expression: Optional[str],
        allow_plaintext: bool,
        project_scope: bool,
        channel_kind: str,
        created_by: UUID
    ) -> WebhookOutTarget:
    """
        Persist a new webhook target and issue its first signing secret.

        :raises: ConfigurationError, ValidationError
    """
    ...


def rotate_secret(*, target_id: UUID, rotated_by: UUID) -> WebhookOutTarget:
    """
        Mint a new signing secret, move the current secret into
        `previous_secret` with a 48-hour validity window, and
        publish `entity.webhook.secret_rotated`.
    """
    ...


def disable_target(*, target_id: UUID, reason: str) -> None:
    """Mark a target disabled; publish `entity.webhook.target_disabled`."""
    rtnval = None
    return rtnval
```

Module
`ccai.pychestrate.webservice.webhooks.outbound.filter_engine`:

```python
def decide_delivery(
        *,
        target_topics: list[str],
        filter_expression: Optional[str],
        event_topic: str,
        event_payload: dict
    ) -> DeliveryDecision:
    """
        Apply topic prefix match + optional filter expression.

        :returns: `DeliveryDecision(deliver: bool, skip_reason: Optional[str])`
    """
    ...
```

Module
`ccai.pychestrate.webservice.webhooks.outbound.channel`:

```python
class WebhookNotificationChannel:
    channel_kind: str = "http_webhook"

    @classmethod
    def deliver(
            cls,
            *,
            target: WebhookOutTarget,
            event_topic: str,
            event_payload: dict,
            attempt_number: int
    ) -> DeliveryAttemptResult:
        """
            Sign and POST the payload to the target URL.

            :raises: TransientDeliveryError, PermanentDeliveryError
        """
        ...
```

Module
`ccai.pychestrate.webservice.webhooks.outbound.delivery_recorder`:

```python
def record_attempt(
        *,
        target_id: UUID,
        event_topic: str,
        event_id: UUID,
        attempt: DeliveryAttemptResult
    ) -> DeliveryRow:
    """Persist the attempt and update consecutive-abandoned counters."""
    ...
```

### Extension Surface

This feature does **not** declare a new factory protocol or resource
base. It registers `WebhookNotificationChannel` through the
`notification_channel` factory owned by `2-notification-hub`. The
registration body is a minimal adapter declared in
`ccai.pychestrate.webservice.webhooks.outbound.factories.http_webhook_channel`:

```python
class HttpWebhookChannel(NotificationChannelProtocol):
    factory_protocol_name: str = "notification_channel"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def channel_kind(cls) -> str:
        """Return 'http_webhook'."""
        ...

    @classmethod
    def deliver(cls, *, channel_config: dict, payload: dict) -> None:
        """Delegate to `WebhookNotificationChannel.deliver`."""
        ...
```

An extension can ship an alternative HTTP channel (e.g., mTLS-only)
at `PRECEDENCE = 500` to replace the default, without touching
`8-webhooks-out` internals.

### Events Emitted

- `entity.webhook.dispatched` —
  `{target_id, project_id, event_topic, event_id, status_code,
  attempt_count, duration_seconds, delivered_at}`.
- `entity.webhook.failed` —
  `{target_id, event_topic, event_id, attempt_count, reason,
  failed_at}`.
- `entity.webhook.retry_scheduled` —
  `{target_id, event_id, next_attempt_at, attempt_count}`.
- `entity.webhook.target_disabled` —
  `{target_id, project_id, reason, disabled_at}`.
- `entity.webhook.secret_rotated` —
  `{target_id, rotated_by, rotated_at, old_secret_valid_until}`.
- `entity.webhook.test` — synthetic event for target test.

### Events Consumed

- **Every** `entity.*` topic is a subscription candidate; the
  dispatcher subscribes lazily to exactly the topics listed by any
  enabled target (union across targets).
- `entity.project.deleted` — disables and deletes all targets for
  that project.
- `entity.secret.rotated` — evicts cached `SecretBytes`.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/webhooks/outbound/
    __init__.py
    signing.py                      # sign_payload
    target_service.py               # CRUD + rotate_secret + disable_target
    filter_engine.py                # decide_delivery
    channel.py                      # WebhookNotificationChannel
    delivery_recorder.py
    factories/
        http_webhook_channel.py     # notification_channel factory adapter
    restapi/
        v1/
            targets_controller.py
            deliveries_controller.py
    models.py                       # WebhookOutTarget, DeliveryAttemptResult, ...
    exceptions.py
```

## Key Flows

**Deliver an Event:**

1. `0-message-bus` yields `entity.run.completed` to the outbound
   dispatcher worker.
2. Worker queries enabled targets whose topic list prefix-matches the
   event (in-memory cached table refreshed on
   `entity.webhook.target_disabled` etc.).
3. For each matching target, `filter_engine.decide_delivery`
   evaluates the filter expression.
4. `signing.sign_payload` builds the header
   `"t=<ts>,v1=<hex>[,v1-previous=<hex>]"`.
5. `WebhookNotificationChannel.deliver` POSTs the canonical body.
6. `delivery_recorder.record_attempt` persists the result and
   publishes `entity.webhook.dispatched` or
   `entity.webhook.retry_scheduled`.

**Secret Rotation:**

1. Admin calls
   `POST .../webhooks/out/{target_id}:rotate_secret`.
2. `target_service.rotate_secret` mints a new secret via
   `1-secrets-vault`, moves the existing one to `previous_secret`
   with `previous_secret_valid_until = now + 48 h`.
3. For 48 h, every dispatch includes both `v1` and `v1-previous`
   header segments.
4. A scheduled sweep clears `previous_secret_ref` after the window.

**Auto-Disable on Sustained Failure:**

1. A target reaches its 24-attempt abandoned status for the third
   time in a row.
2. `delivery_recorder` increments `consecutive_abandoned` and,
   when it hits 3, calls `target_service.disable_target`.
3. `entity.webhook.target_disabled` publishes; a notification to
   `system:webhook.admin` holders goes out through the hub.

## Error Handling

- `TransientDeliveryError` — 5xx, timeout, DNS failure, TLS
  failure; caught by the hub's retry scheduler; NOT swallowed.
- `PermanentDeliveryError` — non-408/non-429 4xx; no retry.
- `SignatureSecretMissingError` — raised when
  `current_secret_ref` resolves to nothing; reclassified as
  `ConfigurationError` at the controller; delivery is skipped and
  the target auto-disabled with reason `"missing_secret"`.
- `ConfigurationError` — raised when a target's `channel_kind`
  resolves to no registered channel; at creation time it rejects
  the API call; at dispatch time it disables the target.
- `SemanticError` — raised for internal misuse (e.g., signing a
  non-canonical body); never caught.
- Error messages assembled with `os.linesep.join([...])` including
  `target_id`, `event_id`, and `attempt_count`.

## Security Considerations

- Signing secrets stored in `1-secrets-vault` only; caches are
  `SecretBytes` evicted on rotation.
- Signature uses HMAC-SHA-256; receivers are documented to use
  constant-time comparison.
- Plaintext `http://` is refused unless the target sets
  `allow_plaintext=True`, which is explicitly dev-only and emits
  `pychestrate_webhook_plaintext_targets_total` so operators can
  audit.
- Target URLs are filtered against an allow/deny list (no
  `localhost`, no RFC 1918 in production) configurable via
  `2-global-variables` key `webhooks.out.url_policy`.
- Every target mutation appears in `1-audit-log` with the actor's
  `user_id`.
- Outbound HTTP client honors a 30-second request timeout and
  rejects redirects to plaintext URLs.
- `system:webhook.admin` permission gates target CRUD and redrive;
  `system:webhook.read` gates list/detail.

## Observability

Metrics:

- `pychestrate_webhook_dispatched_total{target,status}`
- `pychestrate_webhook_dispatch_duration_seconds` (histogram)
- `pychestrate_webhook_retry_total{target}`
- `pychestrate_webhook_abandoned_total{target}`
- `pychestrate_webhook_targets_enabled` (gauge)
- `pychestrate_webhook_signing_duration_seconds`
- `pychestrate_webhook_plaintext_targets_total` (gauge)

Log events: `webhook.dispatched`, `webhook.failed`,
`webhook.retry_scheduled`, `webhook.target_disabled`,
`webhook.secret_rotated`, `webhook.target_created`,
`webhook.target_updated`, `webhook.target_deleted`.

Trace spans: `webhook.sign`, `webhook.filter`, `webhook.dispatch`,
`webhook.receive_response`, `webhook.record_attempt`.

## Open Questions

- Do we let receivers self-service secret rotation via a special
  endpoint (e.g., challenge-response), or keep rotation admin-only?
  Close before Phase 10 GA.
- Should `FilterExpression` be a custom DSL or reuse the PromQL-ish
  language used by `7-alerts-budgets`? Proposed: reuse if it covers
  the needed predicates, otherwise ship a narrow dedicated DSL.
- Batching — is "one HTTP POST per entity event" the final contract,
  or do we offer opt-in batching (group up to N events in a single
  envelope)? Defer; gather demand from the first five receivers.
