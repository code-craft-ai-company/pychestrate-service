# 8-webhooks-in — Design

## Architecture

`8-webhooks-in` lives under
`source/site/automojo/pychestrate/webservice/webhooks/inbound/` and
mounts its routes under `/api/v1/webhooks/in/<provider>/<hook_name>`
through the `8-rest-api-v1` dispatcher, reusing that feature's
authentication, rate-limit, and problem-json machinery. The core of
the feature is a *parser dispatch*: incoming requests are routed to an
`inbound_webhook_parser` implementation selected by the URL's
`<provider>` segment via `E-extension-host`. Every parser is
contracted to be *total* — it returns a `ParsedWebhook` or a
`StructuredRejection`, and the framework wraps its invocation in a
100 ms budget plus a catch-and-reclassify boundary so uncaught
exceptions surface as a structured rejection, never a 500. Verified
payloads are normalized into domain events published on
`0-message-bus`. Replays are de-duplicated via a `webhooks_in_seen_deliveries`
table. This feature ships in **Phase 10 — Public Surface &
Extensibility Completion**.

## Data Model

`webhooks_in_configurations` table:

- `webhook_id: UUID` — PK.
- `project_id: UUID` — FK → `projects.project_id`.
- `provider: str` — parser factory name (e.g., `github`, `gitlab`).
- `hook_name: str` — per-project nickname.
- `secret_ref: str` — pointer into `1-secrets-vault`
  (`webhooks.in.<provider>.<hook_name>.secret`).
- `mtls_required: bool`.
- `created_at: datetime`, `created_by: UUID`.
- `disabled_at: Optional[datetime]`.
- Unique on `(project_id, provider, hook_name)`.
- Index: `(provider, hook_name)`.

`webhooks_in_seen_deliveries` table:

- `provider: str` — PK component.
- `hook_name: str` — PK component.
- `delivery_id: str` — PK component.
- `first_seen_at: datetime`, `expires_at: datetime` (72 h).
- Index: `(expires_at)` for sweeper.

`webhooks_in_deadletter_index` table (pointers into the object store):

- `request_id: UUID` — PK.
- `webhook_id: UUID`, `provider: str`, `hook_name: str`.
- `object_store_path: str`, `content_type: str`, `byte_size: int`.
- `reason: str`, `recoverable: bool`.
- `stored_at: datetime`, `expires_at: datetime` (7 d).

Dataclass:

```python
@dataclass(frozen=True)
class ParsedWebhook:
    provider: str
    hook_name: str
    delivery_id: Optional[str]
    domain_events: list[NormalizedEvent]


@dataclass(frozen=True)
class StructuredRejection:
    reason: str
    detail: str
    recoverable: bool
    status_code: int
```

## Interfaces

### Public API

- `POST /api/v1/webhooks/in/<provider>/<hook_name>` — inbound
  dispatch endpoint.
- `POST /api/v1/projects/{project_id}/webhooks/in` — create
  configuration.
- `GET /api/v1/projects/{project_id}/webhooks/in` — list configured
  webhooks.
- `GET /api/v1/projects/{project_id}/webhooks/in/{webhook_id}` —
  detail (includes the URL to paste at the provider).
- `PATCH /api/v1/projects/{project_id}/webhooks/in/{webhook_id}` —
  rotate secret, toggle mTLS, disable.
- `DELETE /api/v1/projects/{project_id}/webhooks/in/{webhook_id}` —
  remove configuration.
- `POST /api/v1/projects/{project_id}/webhooks/in/{webhook_id}:replay`
  — replay a deadlettered payload by `request_id`.

### Internal API

Module `automojo.pychestrate.webservice.webhooks.inbound.dispatcher`:

```python
def dispatch_inbound_webhook(
        *,
        provider: str,
        hook_name: str,
        raw_bytes: bytes,
        headers: Mapping[str, str],
        remote_ip: str,
        request_id: UUID,
        mtls_subject: Optional[str]
    ) -> WebhookDispatchResult:
    """
        Verify, parse, de-duplicate, and publish normalized events.

        :param provider: Parser factory name.
        :param hook_name: Per-project nickname of the configured hook.
        :param raw_bytes: Raw request body.
        :param headers: Request headers.
        :param remote_ip: Source IP for rate-limit and audit.
        :param request_id: Server-assigned id for tracing and deadletter.
        :param mtls_subject: Subject DN if the request arrived over mTLS.

        :returns: WebhookDispatchResult carrying status and published events.
        :raises: ConfigurationError
    """
    ...
```

Module `automojo.pychestrate.webservice.webhooks.inbound.verification`:

```python
def verify_signature(
        *,
        parser: InboundWebhookParserProtocol,
        raw_bytes: bytes,
        headers: Mapping[str, str],
        shared_secret: SecretBytes
    ) -> VerificationOutcome:
    """
        Run the parser's declared signature algorithm in constant time.

        :raises: AuthenticationError
    """
    ...
```

Module `automojo.pychestrate.webservice.webhooks.inbound.replay_cache`:

```python
def record_delivery_or_replay(
        *,
        provider: str,
        hook_name: str,
        delivery_id: str,
        now: datetime
    ) -> DeliveryOutcome:
    """
        Return `recorded` or `replay_ignored` atomically.
    """
    ...
```

Module `automojo.pychestrate.webservice.webhooks.inbound.deadletter`:

```python
def store_deadletter(
        *,
        webhook_id: UUID,
        provider: str,
        hook_name: str,
        request_id: UUID,
        raw_bytes: bytes,
        content_type: str,
        rejection: StructuredRejection
    ) -> None:
    """Write the raw payload to the object store under a 7-day TTL."""
    rtnval = None
    return rtnval


def replay_deadletter(*, request_id: UUID) -> WebhookDispatchResult:
    """Replay a stored deadlettered payload through the dispatcher."""
    ...
```

Module `automojo.pychestrate.webservice.webhooks.inbound.normalization`:

```python
def publish_domain_events(
        *,
        parsed: ParsedWebhook,
        webhook_id: UUID,
        request_id: UUID
    ) -> int:
    """
        Publish every domain event from a parsed webhook atomically.

        :returns: Number of events published.
    """
    ...
```

### Extension Surface

Factory protocol `inbound_webhook_parser` declared in
`automojo.pychestrate.webservice.webhooks.inbound.factories.inbound_webhook_parser`:

```python
class InboundWebhookParserProtocol(FactoryProtocolBase):
    factory_protocol_name: str = "inbound_webhook_parser"
    protocol_schema_version: int = 1

    @classmethod
    def provider_name(cls) -> str:
        """Return the URL segment (e.g., 'github')."""
        ...

    @classmethod
    def accepted_content_types(cls) -> list[str]:
        """Media types the parser consumes."""
        ...

    @classmethod
    def signature_headers(cls) -> list[SignatureHeaderSpec]:
        """Header name + algorithm + encoding for each accepted algorithm."""
        ...

    @classmethod
    def delivery_id_header(cls) -> Optional[str]:
        """Header carrying the provider-native delivery id, if any."""
        ...

    @classmethod
    def parse(
            cls,
            *,
            raw_bytes: bytes,
            headers: Mapping[str, str],
            shared_secret: SecretBytes
        ) -> Union[ParsedWebhook, StructuredRejection]:
        """Parse a verified payload into normalized domain events."""
        ...
```

Reference implementations (in-tree):

- `GithubWebhookParser` (`PRECEDENCE = 1000`) — verifies
  `X-Hub-Signature-256` (strong) and `X-Hub-Signature` (weak),
  reads `X-GitHub-Delivery` for replay keys, emits
  `entity.scm.push|pull_request|issue_comment|...`.
- `GitlabWebhookParser` (`PRECEDENCE = 1000`) — header
  `X-Gitlab-Token` (opaque match), delivery `X-Gitlab-Event-UUID`.
- `BitbucketWebhookParser` (`PRECEDENCE = 1000`).
- `GenericHmacWebhookParser` (`PRECEDENCE = 1500`) — fallback
  HMAC-SHA-256 implementation for generic providers.

### Events Emitted

- `entity.webhook.received` —
  `{provider, hook_name, request_id, received_at, remote_ip_hash}`.
- `entity.webhook.verified` —
  `{provider, hook_name, request_id, delivery_id}`.
- `entity.webhook.dispatched` —
  `{provider, hook_name, request_id, domain_event_count,
  dispatched_at}`.
- `entity.webhook.failed` —
  `{provider, hook_name, request_id, reason, detail, recoverable}`.
- `entity.webhook.replay_ignored` —
  `{provider, hook_name, delivery_id, observed_at}`.
- `entity.webhook.configured` —
  `{webhook_id, project_id, provider, hook_name, created_by,
  created_at}`.

Plus the normalized domain events each parser emits (e.g.,
`entity.scm.push`, `entity.bugtracker.state_changed`) — those are
owned by the downstream features but are *published by* this
feature.

### Events Consumed

- `entity.extension.loaded` — re-index parser registry.
- `entity.extension.unloaded` — drop parser from registry.
- `entity.secret.rotated` — invalidate in-process cache of shared
  secret bytes.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/webhooks/inbound/
    __init__.py
    dispatcher.py                 # top-level dispatch pipeline
    verification.py               # signature verification
    replay_cache.py               # seen-deliveries table
    deadletter.py                 # deadletter store + replay
    normalization.py              # publish_domain_events
    configuration_service.py      # CRUD for webhooks_in_configurations
    factories/
        inbound_webhook_parser.py # FactoryProtocolBase
        github_parser.py          # reference
        gitlab_parser.py          # reference
        bitbucket_parser.py       # reference
        generic_hmac_parser.py    # reference
    restapi/
        v1/
            inbound_controller.py # /api/v1/webhooks/in/...
            configuration_controller.py
    models.py                     # ParsedWebhook, StructuredRejection,
                                  # NormalizedEvent, SignatureHeaderSpec
    exceptions.py
```

## Key Flows

**Verified Delivery:**

1. `inbound_controller` receives `POST /api/v1/webhooks/in/github/main`.
2. `configuration_service.lookup` resolves the webhook row; its
   `secret_ref` is resolved through `1-secrets-vault`.
3. `dispatcher.dispatch_inbound_webhook` reads headers, calls
   `verification.verify_signature` in constant time.
4. `replay_cache.record_delivery_or_replay` inserts the delivery id;
   if already present, returns `replay_ignored` and the controller
   responds `200 {status: "replay_ignored"}`.
5. `GithubWebhookParser.parse` returns `ParsedWebhook` within the
   100 ms parser budget.
6. `normalization.publish_domain_events` publishes each normalized
   event atomically through `0-message-bus`.
7. `dispatcher` responds `204 No Content` and publishes
   `entity.webhook.dispatched`.

**Parser Crash Reclassified:**

1. A malformed payload causes `ParserX.parse` to raise a
   `KeyError`.
2. `dispatcher` catches at the framework boundary and reclassifies
   as `StructuredRejection(reason="parser_crashed",
   detail="KeyError: 'action'", recoverable=True)`.
3. `deadletter.store_deadletter` writes the raw payload under a
   7-day TTL.
4. `entity.webhook.failed` publishes; response is `400 problem+json`.
5. An operator fixes the parser, calls the replay endpoint, and
   `replay_deadletter` re-enters the dispatcher.

**Configuration:**

1. Admin calls `POST /api/v1/projects/{id}/webhooks/in` with
   `{provider, hook_name, secret_ref, mtls_required}`.
2. `configuration_service.create_webhook` validates that `provider`
   has a registered parser; persists the row.
3. `GET .../webhooks/in/{webhook_id}` returns the exact URL to paste
   at the provider plus the list of headers the parser inspects.

## Error Handling

- `AuthenticationError` — surfaces as 401; reason logged server-side.
- `ParserTimeoutError` — reclassified as
  `StructuredRejection(reason="parser_timeout")` at the framework
  boundary.
- `ParserCrashedError` — reclassified similarly.
- `ConfigurationError` — raised when an unknown provider is
  requested at configuration time; when an expected parser fails to
  load at startup; when a stored `secret_ref` cannot be resolved.
- `SemanticError` — never caught; e.g., a parser returning the
  wrong union type.
- Multiline error messages built with `os.linesep.join([...])`
  including request id and provider for traceability.

## Security Considerations

- Shared secrets live only in `1-secrets-vault`; cached in-process
  as `SecretBytes`; evicted on `entity.secret.rotated`.
- Signature comparison is constant-time (`hmac.compare_digest`).
- Weak signature-only acceptances (MD5, SHA-1 without SHA-256
  companion) are rejected at the verification stage with
  `reason="signature_weak"`.
- mTLS enforcement is per-hook via `mtls_required`.
- Deadlettered payloads are stored encrypted at rest and access
  requires `system:webhook.admin`.
- Anonymous rate-limit keyed on source IP at 100 req/s.
- Audit log records every configuration mutation.
- `system:webhook.admin` permission gates configuration CRUD;
  `system:webhook.replay` gates the deadletter replay endpoint.

## Observability

Metrics:

- `pychestrate_webhook_received_total{provider,hook_name,outcome}`
- `pychestrate_webhook_ingest_duration_seconds` (histogram)
- `pychestrate_webhook_rejections_total{provider,reason}`
- `pychestrate_webhook_replays_total{provider}`
- `pychestrate_webhook_deadletters_total{provider}`
- `pychestrate_webhook_parser_timeout_total{provider}`
- `pychestrate_webhook_parser_crashed_total{provider}`

Log events: `webhook.received`, `webhook.verified`,
`webhook.dispatched`, `webhook.failed`, `webhook.replay_ignored`,
`webhook.deadlettered`, `webhook.configured`.

Trace spans: `webhook.ingest`, `webhook.verify`, `webhook.parse`,
`webhook.dedup`, `webhook.publish`, `webhook.deadletter_write`.

## Open Questions

- Should the deadletter retention window be per-hook configurable or
  a global 7 days? Close during Phase 10 operator review.
- Do we offer a provider-agnostic "JSON passthrough" mode for fully
  custom parsers, or require every provider to register? Leaning
  require — the generic HMAC parser covers the long tail. Revisit
  after the first three external extensions land.
- Replay-cache sharding — is the `webhooks_in_seen_deliveries`
  table sufficient at scale, or do we front it with Redis? Measure
  in Phase 10 load tests.
