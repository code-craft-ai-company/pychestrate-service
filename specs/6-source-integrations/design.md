# 6-source-integrations — Design

## Architecture

`6-source-integrations` is a thin integration layer: it accepts webhooks,
verifies signatures, dedups deliveries, loads pipeline files from the
SCM at the target commit, hands off to `PipelineService.trigger_run`,
and posts commit statuses back when pipeline runs change state.
Providers are plug-in `scm_provider` factories; per-provider payload
shapes are contributed via `WebhookPayloadParserExtension` resource
extensions so that a site-specific GitHub Enterprise quirk can be
handled without patching the core provider. Ships in Phase 6 alongside
`6-pipeline-definition`. Authoritative source of truth for repo data is
the SCM; this feature caches only dedup keys and `last_seen_heads` for
polling.

## Data Model

Tables in `0-persistence`:

- `scm_project_config`:
  - `project_id: UUID` PK
  - `provider_name: str`
  - `repo_key: str` — e.g., `owner/repo`
  - `pipeline_file_path: str` — default `.pychestrate/pipeline.yaml`
  - `use_polling: bool`
  - `polling_ref_glob: str`
  - `last_poll_at: datetime | None`
- `scm_webhook_delivery`:
  - `delivery_id: str`
  - `project_id: UUID`
  - `provider_name: str`
  - `received_at: datetime`
  - `first_seen_at: datetime`
  - PK `(project_id, delivery_id)` — enables dedup lookup.
- `scm_last_seen_head`:
  - `project_id: UUID`
  - `ref: str`
  - `commit_sha: str`
  - `observed_at: datetime`
  - PK `(project_id, ref)`.
- `scm_status_dedup`:
  - In-memory LRU (size 8192) keyed by `(project_id, commit_sha, context, state)`.

Value types:

- `PushEvent`, `PullRequestEvent` — parsed dataclasses.
- `CommitStatusRequest` — `{commit_sha, context, state, description, target_url}`.

## Interfaces

### Public API

REST under `8-rest-api-v1`:

- `POST /api/v1/webhooks/scm/{project_id}` — raw webhook endpoint.
- `POST /api/v1/projects/{project_id}/scm/config` body `{provider_name, repo_key, pipeline_file_path, use_polling}` → config.
- `GET /api/v1/projects/{project_id}/scm/deliveries?limit=&cursor=` → paginated delivery history.

Inbound webhook: `Content-Type` and `X-Pychestrate-Provider: <name>` header-driven routing; body verified via provider's signature classmethod.

### Internal API

```python
class SourceIntegrations:
    def __init__(
        self,
        repo: ScmRepository,
        provider_registry: ScmProviderRegistry,
        secrets: SecretsAccessor,
        pipelines: PipelineService,
        rbac: RbacService,
        audit: AuditLog,
        bus: MessageBus,
        clock: Clock,
        config: SourceIntegrationsConfig
    ) -> None:
        self._repo = repo
        self._provider_registry = provider_registry
        self._secrets = secrets
        self._pipelines = pipelines
        self._rbac = rbac
        self._audit = audit
        self._bus = bus
        self._clock = clock
        self._config = config
        return

    def handle_webhook(
        self,
        project_id: UUID,
        headers: dict[str, str],
        raw_body: bytes
    ) -> WebhookAckResult:
        """
            Verify and route an inbound webhook.

            :returns: WebhookAckResult with state (accepted|deduped|rejected).
            :raises: ConfigurationError
        """
        ...

    def set_project_config(
        self,
        actor_id: UUID,
        project_id: UUID,
        provider_name: str,
        repo_key: str,
        pipeline_file_path: str,
        use_polling: bool,
        polling_ref_glob: str | None
    ) -> None:
        """
            Persist per-project SCM config.

            :returns: None.
            :raises: AuthorizationError, ConfigurationError
        """
        ...

    def post_pipeline_status(
        self,
        pipeline_run: PipelineRunView,
        aspects: PostStatusAspects | None = None
    ) -> None:
        """
            Post a commit status reflecting a pipeline state transition.

            :returns: None.
            :raises: ProviderTransientError
        """
        ...

    def poll_project(
        self,
        project_id: UUID
    ) -> PollResult:
        """
            Run one polling sweep for a project.

            :returns: PollResult with observed new heads.
            :raises: ConfigurationError, ProviderTransientError
        """
        ...
```

### Extension Surface

Factory protocol declared here:

```python
class ScmProviderProtocol(FactoryProtocolBase):
    """
        Contract for scm_provider implementations.
    """
    factory_protocol_name: str = "scm_provider"

    @classmethod
    def provider_name(cls) -> str:
        ...

    @classmethod
    def verify_webhook_signature(
        cls,
        headers: dict[str, str],
        raw_body: bytes,
        shared_secret: bytes
    ) -> bool:
        ...

    @classmethod
    def parse_push_event(
        cls,
        headers: dict[str, str],
        body_json: dict
    ) -> PushEvent | None:
        ...

    @classmethod
    def parse_pull_request_event(
        cls,
        headers: dict[str, str],
        body_json: dict
    ) -> PullRequestEvent | None:
        ...

    @classmethod
    def read_file_at_ref(
        cls,
        driver: ScmProviderDriver,
        repo_key: str,
        ref_or_sha: str,
        path: str
    ) -> bytes:
        ...

    @classmethod
    def post_commit_status(
        cls,
        driver: ScmProviderDriver,
        repo_key: str,
        request: CommitStatusRequest
    ) -> None:
        ...

    @classmethod
    def list_refs(
        cls,
        driver: ScmProviderDriver,
        repo_key: str
    ) -> dict[str, str]:
        ...

    @classmethod
    def capabilities(cls) -> ScmCapabilities:
        ...
```

Resource extension:

```python
class WebhookPayloadParserExtension(ResourceExtension):
    """
        Pluggable payload parser for a specific provider + event quirk.
    """
    provider_name: str
    event_kinds: set[str]

    @classmethod
    def matches(cls, headers: dict[str, str], body_json: dict) -> bool:
        ...

    @classmethod
    def parse(cls, headers: dict[str, str], body_json: dict) -> PushEvent | PullRequestEvent | None:
        ...
```

Reference implementations under
`source/site/automojo/factories/pychestrate/scm_provider/`:

- `GithubScmProvider` — `PRECEDENCE = 500`.
- `GitlabScmProvider` — `PRECEDENCE = 500`.
- `BitbucketScmProvider` — `PRECEDENCE = 500`.
- `GiteaScmProvider` — `PRECEDENCE = 500`.

### Events Emitted

- `entity.source.webhook.received` — `{project_id, provider_name, event_kind, delivery_id}`
- `entity.source.pipeline_triggered_by_webhook` — `{project_id, pipeline_run_id, commit_sha, ref}`
- `entity.source.commit_status_posted` — `{project_id, provider, commit_sha, state}`

### Events Consumed

- `entity.pipeline.run_started`, `entity.pipeline.run_completed` — trigger status posting.
- `extension.reloaded` — refresh provider registry.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/orchestration/source/`:

- `__init__.py`
- `service.py` — `SourceIntegrations`.
- `repository.py` — `ScmRepository`.
- `provider_protocol.py` — `ScmProviderProtocol`.
- `provider_registry.py` — extension-host accessor.
- `parser_extension.py` — `WebhookPayloadParserExtension`.
- `dedup.py` — delivery + status dedup stores.
- `poll_worker.py` — scheduler for polling sweeps.
- `status_poster.py` — pipeline-event subscriber posting statuses.
- `aspects.py` — `PostStatusAspects`, `PollAspects`.
- `errors.py` — `ProviderTransientError`.
- `rest/v1_routes.py` — REST endpoints.

Factories under `source/site/automojo/factories/pychestrate/scm_provider/`.
Parser extensions under `source/site/automojo/extensions/pychestrate/webhook_parser/`.

## Key Flows

### Flow 1 — Webhook path

1. `POST /api/v1/webhooks/scm/{project_id}` with raw body.
2. `SourceIntegrations.handle_webhook` resolves `ScmProject_Config`.
3. Shared secret fetched from `1-secrets-vault`; `provider.verify_webhook_signature(...)` — failure → 401.
4. `delivery_id` extracted from headers; dedup lookup → if seen, 200.
5. Event parsed via provider + matching `WebhookPayloadParserExtension` (if any).
6. Pipeline file bytes read via `provider.read_file_at_ref(...)`.
7. `PipelineService.trigger_run(...)` called with `TriggerCause(kind="webhook", reference=delivery_id)`.
8. Delivery recorded; `entity.source.webhook.received` emitted.

### Flow 2 — Status post after pipeline event

1. `status_poster` subscribes to `entity.pipeline.run_started|completed|failed|cancelled`.
2. For each, `CommitStatusRequest` built with `context = "pychestrate/<filename>"`.
3. Dedup against `scm_status_dedup`; if within `status_dedup_seconds`, skip.
4. `provider.post_commit_status(...)` invoked; transient errors retried per `PostStatusAspects`.

### Flow 3 — Polling

1. `poll_worker` iterates projects with `use_polling == True`.
2. `provider.list_refs(...)` returns map `ref → sha`.
3. Compared against `scm_last_seen_head`; new heads matching `polling_ref_glob` trigger file read + pipeline dispatch with `TriggerCause(kind="polling", reference=ref)`.
4. `last_seen_head` updated.

## Error Handling

- `ConfigurationError`: unknown provider, bad signature secret, missing capability when invoked → bubble.
- `ProviderTransientError`: caught at driver boundary and reclassified with multiline context; retried per Aspects.
- 401 on signature failure (never 500).
- 413 on oversize payload (`max_webhook_payload_bytes`).
- Missing pipeline file at ref: 200, INFO log.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- Webhook shared secrets stored per-project in `1-secrets-vault` at `secrets/project/<id>/scm/webhook_secret`.
- Status-post credentials stored at `secrets/project/<id>/scm/api_token`.
- RBAC `scm.config.write` gates `set_project_config`; `scm.config.read` gates view.
- Webhook handler rate-limited per project: `max_webhooks_per_minute_per_project` (default 600).
- No outbound followups fire on webhook replay (dedup).
- Full body not logged by default; `delivery_id`, event kind, and size only.

## Observability

Metrics:

- `pychestrate_source_webhooks_received_total{project,provider,event_kind}` — counter
- `pychestrate_source_webhook_signature_failures_total{project,provider}` — counter
- `pychestrate_source_status_posts_total{project,provider,state}` — counter
- `pychestrate_source_status_post_errors_total{project,provider,error_kind}` — counter
- `pychestrate_source_poll_duration_seconds{project,provider}` — histogram
- `pychestrate_source_dedup_hits_total{project,kind}` — counter

Log events: `pychestrate.source.webhook.received`, `pychestrate.source.webhook.signature_failed`, `pychestrate.source.pipeline_file_missing`, `pychestrate.source.status_posted`, `pychestrate.source.poll.swept`, `pychestrate.source.provider_unavailable`.

Trace spans: `pychestrate.source.webhook`, `pychestrate.source.post_status`, `pychestrate.source.poll`, `pychestrate.source.read_file`.

## Open Questions

- App-token vs PAT vs GitHub App for status posting — choose per-provider defaults. Timebox: Phase 6 midpoint.
- Delivery-id dedup TTL — 1 h vs 24 h. Timebox: Phase 6 exit.
- Webhook-retry acceptance: should the service proactively return 202 and defer file read to a worker? Timebox: Phase 6 exit.
