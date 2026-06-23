# 2-notification-hub — Design

## Architecture

`2-notification-hub` lives under
`ccai.pychestrate.webservice.notifications`. It consumes every topic on
`0-message-bus` via a wildcard subscriber, runs each event through a
three-stage pipeline (match → render → send), and persists per-dispatch
audit trail in `0-persistence`. The channel registry and template registry
are loaded at startup through `E-factory-protocols` and
`E-resource-extensions`. A worker pool (sized via service config) handles
async sends; failures flow into a persistent dead-letter queue with
exponential-backoff retry. The rate limiter is a per-recipient sliding
window (token bucket with 60 s refill) backed by Postgres
advisory-increment-and-check. Ships in **Phase 1**.

## Data Model

```python
class Severity(str, enum.Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class NotificationChannel:
    channel_id: UUID
    name: str                    # UNIQUE within project or system
    kind: str                    # registered notification_channel name
    scope_level: Literal["system", "project"]
    scope_id: UUID | None
    config: dict[str, Any]       # validated against channel schema
    secret_refs: dict[str, str]  # { "api_token": "${secret:...}" }
    max_send_seconds: int
    disabled: bool

@dataclass
class NotificationRoutingRule:
    rule_id: UUID
    project_id: UUID
    event_pattern: str           # glob, e.g., "entity.run.failed",
                                 # "entity.run.*", "entity.*.failed"
    filter_tag_expression: str | None
    recipients: list[Recipient]  # user_id | group_id | external_email
    channel_ids: list[UUID]
    template_name: str           # must be registered
    rate_limit_per_minute: int | None

@dataclass
class UserNotificationPreferences:
    user_id: UUID                # PK
    per_topic: dict[str, dict[str, bool]]  # { topic_glob: { channel_kind: enabled } }
    quiet_hours_timezone: str | None
    quiet_hours_start: str | None  # "HH:MM"
    quiet_hours_end: str | None

@dataclass
class DispatchEnvelope:
    envelope_id: UUID            # idempotency key
    event_topic: str
    event_payload: dict[str, Any]
    recipient: Recipient
    channel_id: UUID
    template_name: str
    severity: Severity
    rendered_subject: str
    rendered_body: str
    created_at: datetime

@dataclass
class DispatchAttempt:
    attempt_id: UUID
    envelope_id: UUID
    attempt_number: int
    outcome: Literal["delivered", "failed", "deferred"]
    error_message: str | None
    latency_ms: int | None
    attempted_at: datetime

@dataclass
class DeadLetter:
    envelope_id: UUID            # PK (same as envelope)
    last_error: str
    attempt_count: int
    enqueued_at: datetime
    replayable: bool
```

Indexes: `notification_channels UNIQUE (scope_level, scope_id, name)`;
`notification_routing_rules (project_id)`, `(event_pattern)`;
`dispatch_envelopes (event_topic, created_at)`;
`dispatch_attempts (envelope_id)`;
`dead_letters (enqueued_at)`.

## Interfaces

### Public API

- `POST/GET/PATCH/DELETE /api/v1/notifications/channels/{id?}` —
  channel CRUD.
- `POST/GET/PATCH/DELETE /api/v1/projects/{slug}/notification-rules/{id?}` —
  routing rule CRUD.
- `GET/PUT /api/v1/users/me/notification-preferences` —
  preferences CRUD (self-only).
- `GET /api/v1/notifications/dead-letter?limit=&offset=` — list.
- `POST /api/v1/notifications/dead-letter/{envelope_id}/replay` —
  replay.
- `DELETE /api/v1/notifications/dead-letter/{envelope_id}` — drop.
- `GET /api/v1/notifications/dispatch-log?project_slug=&since=` —
  audit viewer.

### Internal API

```python
# source/site/ccai/pychestrate/webservice/notifications/service.py

def register_channel(
    *,
    name: str,
    kind: str,
    scope_level: Literal["system", "project"],
    scope_id: UUID | None,
    config: dict[str, Any],
    secret_refs: dict[str, str] | None = None,
    max_send_seconds: int = 15,
    actor_user_id: UUID,
) -> NotificationChannel:
    ...


def create_routing_rule(
    *,
    project_id: UUID,
    event_pattern: str,
    filter_tag_expression: str | None,
    recipients: list[Recipient],
    channel_ids: list[UUID],
    template_name: str,
    rate_limit_per_minute: int | None,
    actor_user_id: UUID,
) -> NotificationRoutingRule:
    ...


def update_user_preferences(
    *,
    user_id: UUID,
    per_topic: dict[str, dict[str, bool]],
    quiet_hours_timezone: str | None,
    quiet_hours_start: str | None,
    quiet_hours_end: str | None,
) -> UserNotificationPreferences:
    ...


# source/site/ccai/pychestrate/webservice/notifications/router.py

def compute_routes(
    *,
    event_topic: str,
    event_payload: dict[str, Any],
    entity_tags: list[str],
    severity: Severity,
    project_id: UUID | None,
) -> list[DispatchEnvelope]:
    """
        Pure function: rules + preferences + rate-limit snapshot →
        dispatch envelope list. Makes Property 1 testable.

        :param event_topic: Bus topic string
        :param event_payload: Decoded event payload
        :param entity_tags: Tags attached to the subject entity
        :param severity: Severity derived from payload
        :param project_id: Project scope (None for system events)

        :returns: List of DispatchEnvelope (possibly empty)
    """
    ...


# source/site/ccai/pychestrate/webservice/notifications/dispatcher.py

def dispatch(
    *,
    envelope: DispatchEnvelope,
) -> DispatchAttempt:
    """
        Synchronous send with per-channel timeout.

        :param envelope: The prepared envelope

        :returns: DispatchAttempt with outcome recorded
    """
    ...


def replay_from_dlq(
    *,
    envelope_id: UUID,
    actor_user_id: UUID,
) -> DispatchAttempt:
    ...
```

### Extension Surface

- `factory: notification_channel`
  (`source/site/ccai/pychestrate/webservice/notifications/factories.py`)

```python
class NotificationChannelProtocol(FactoryProtocolBase):
    factory_protocol_name = "notification_channel"

    kind_name: ClassVar[str]
    config_schema: ClassVar[dict[str, Any]]

    @classmethod
    def validate_config(cls, *, config: dict[str, Any]) -> None:
        ...

    @classmethod
    def send(
        cls,
        *,
        config: dict[str, Any],
        envelope: DispatchEnvelope,
        timeout_seconds: int,
    ) -> None:
        """Raise on failure; return on success."""
        ...
```

Reference impls shipped in-tree under
`ccai/factories/pychestrate/notifications/`:
`SmtpEmailChannel`, `SlackWebhookChannel`, `MsTeamsWebhookChannel`,
`PagerDutyEventsV2Channel`, `GenericWebhookChannel`.

- `resource: NotificationTemplateExtension`

```python
class NotificationTemplateExtension(ResourceExtension):
    template_name: ClassVar[str]
    subject_template: ClassVar[str]   # Jinja2 string
    body_template: ClassVar[str]
    content_type: ClassVar[Literal["text/plain", "text/html", "text/markdown"]]
    PRECEDENCE: ClassVar[int] = 1000

    @classmethod
    def render(
        cls,
        *,
        event_payload: dict[str, Any],
    ) -> tuple[str, str]:
        ...
```

Reference impls: `RunFailedTemplate`, `RunSucceededTemplate`,
`ProjectMemberAddedTemplate`.

### Events Emitted

```python
@dataclass
class NotificationDispatchedEvent:
    envelope_id: UUID
    event_topic: str
    channel_kind: str
    recipient_hash: str
    occurred_at: datetime

@dataclass
class NotificationFailedEvent:
    envelope_id: UUID
    event_topic: str
    channel_kind: str
    recipient_hash: str
    attempt_count: int
    last_error: str
    occurred_at: datetime
```

Topics: `entity.notification.dispatched`,
`entity.notification.failed`.

### Events Consumed

- `*` — wildcard subscriber, the hub is the terminal consumer for
  routing purposes.
- `entity.project.deleted` — delete routing rules and channels scoped
  to the project.
- `entity.user.deleted` — remove user preferences and scrub
  recipients.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/notifications/
    __init__.py
    entities.py         # NotificationChannel, NotificationRoutingRule,
                        # UserNotificationPreferences, DispatchEnvelope,
                        # DispatchAttempt, DeadLetter, Severity
    repository.py       # DB access
    service.py          # channel / rule / prefs CRUD
    router.py           # compute_routes (pure)
    dispatcher.py       # dispatch + retry + DLQ
    rate_limiter.py     # per-recipient sliding window
    digest.py           # digest envelope rendering
    factories.py        # NotificationChannelProtocol + reference impls
    templates.py        # NotificationTemplateExtension + reference impls
    subscriber.py       # wildcard bus subscriber -> router -> dispatcher
    errors.py
source/site/ccai/pychestrate/webservice/restapi/versions/v1/notifications.py
```

## Key Flows

**Route and dispatch**
1. Bus subscriber receives event; extracts entity_id/entity_kind from
   payload.
2. Looks up tags for the entity via `2-tagging`.
3. Calls `compute_routes`; returns zero-or-more `DispatchEnvelope`s.
4. For each envelope, the rate limiter either admits or defers to a
   per-recipient digest window.
5. Admitted envelopes go to the dispatcher worker pool; `send` is
   called with `timeout_seconds`. Success → `DispatchAttempt(outcome=delivered)`
   and `entity.notification.dispatched`. Failure → retry with backoff
   (1s, 5s, 30s, 5m); after `max_retries` → DLQ and
   `entity.notification.failed`.

**Dead-letter replay**
1. Operator hits the DLQ endpoint, reviews last errors.
2. `POST /dead-letter/{id}/replay` enqueues a fresh attempt with
   `attempt_number = 1`; DLQ row is marked `replayed` once the
   attempt succeeds (and removed).

**Digest flush**
1. Rate limiter maintains a 60-second window; on arrival exceeding
   `recipient_rate_limit_per_minute`, events accumulate in a digest
   buffer keyed by `(recipient, channel_id)`.
2. A timer flushes the digest every 60 s, rendering
   `DigestTemplate` with the accumulated events and dispatching a
   single envelope.

## Error Handling

- Channel `send` is expected to raise on failure. Recoverable errors
  (`TimeoutError`, `IOError`, HTTP 5xx, rate-limit 429) are caught,
  reclassified to `ChannelDispatchError` with channel kind and URL
  redacted in the message, counter incremented, retry scheduled.
- Non-recoverable errors (4xx except 429, template render errors) go
  straight to DLQ.
- `SemanticError` (misuse of the dispatcher API) is never caught.
- `ConfigurationError` raised when channel config fails
  `validate_config`, when the template name is unknown at rule-create
  time, or when two `NotificationTemplateExtension`s collide on
  `template_name` with equal `PRECEDENCE`.
- Multiline error messages use `os.linesep.join([...])`.

## Security Considerations

- Channel config secrets: only `${secret:…}` references are stored;
  resolution happens at send time through `2-global-variables`'
  `secret_ref_dereferencer`. Plaintext never hits REST responses or
  logs.
- Recipients validate against `1-user-management` or, for external
  emails, against a configured `external_recipient_allowlist`.
- `notification.channel.write` gates system channels;
  `project.notification.channel.write` gates project channels.
- `notification.dlq.replay` is a distinct permission (high privilege)
  because replay can repeat an alert storm.
- Rate limiting protects external services and engineers.
- Audit-log entries for every channel create/update/delete, rule
  create/update/delete, and DLQ replay.

## Observability

- Counters: `pychestrate_notify_dispatched_total{channel_kind}`,
  `pychestrate_notify_delivered_total{channel_kind}`,
  `pychestrate_notify_failed_total{channel_kind,reason}`,
  `pychestrate_notify_rate_limited_total{recipient_hash}`,
  `pychestrate_notify_skipped_total{reason}`,
  `pychestrate_notify_no_route_total{topic}`,
  `pychestrate_notify_dlq_size` (gauge).
- Histograms: `pychestrate_notify_route_duration_seconds`,
  `pychestrate_notify_send_duration_seconds{channel_kind}`.
- Structured logs: `notification.routed`, `notification.dispatched`,
  `notification.delivered`, `notification.failed`,
  `notification.deferred_to_digest`,
  `notification.dlq_enqueued`, `notification.dlq_replayed`.
- Trace spans: `notify.route`, `notify.dispatch`, `notify.send`,
  `notify.render_template`, `notify.rate_check`.

## Open Questions

- Phase-1 blocker: which specific Slack scopes are required for the
  webhook vs OAuth channel impl? Close before shipping
  `SlackWebhookChannel`.
- Phase-10 blocker: should the digest template be extensible per
  project, or is a single system template sufficient? Revisit with UX
  after first quarter of production traffic.
