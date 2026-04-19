# 6-source-integrations — Requirements

## Introduction

The `6-source-integrations` feature connects Pychestrate to source
control management systems (GitHub, GitLab, Bitbucket, Gitea, custom).
It ingests webhook events, falls back to polling when webhooks are
unavailable, posts commit/PR status updates for completed pipeline
runs, and maintains the cached repo metadata needed to read a
pipeline document at a given commit. The feature ships in **Phase 6**
with `6-pipeline-definition`, `6-build-orchestration`, and
`6-build-artifacts`. It sits between the external SCM and
`6-pipeline-definition`: on a push/PR event it loads the project's
pipeline file at that commit and calls
`PipelineService.trigger_run(...)`. Authoritative source of truth for
repo state is the SCM; this feature owns only routing, dedup, and
status mirroring.

## Requirements

### Requirement 1: SCM Provider Factory Protocol

**User Story:** As an operator running our own Gitea instance, I want
to register a Gitea provider so that Pychestrate speaks Gitea's
webhook + status API without code changes in-tree.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers a `ScmProviderProtocol` implementation THEN the system SHALL verify `provider_name`, `verify_webhook_signature`, `parse_push_event`, `parse_pull_request_event`, `read_file_at_ref`, `post_commit_status`, `list_refs` classmethods AND raise `ConfigurationError` naming missing members.
2. IF two providers share `provider_name` and `PRECEDENCE` THEN the system SHALL raise `ConfigurationError` at load time.
3. WHEN a project is configured with `scm_provider = "<name>"` THEN the system SHALL resolve the provider through the registry on every API call — hot-replacement is allowed without restart.
4. WHERE a provider declares `supports_polling: True` THEN the system SHALL schedule a polling sweep every `poll_interval_seconds` (default 120) for projects with `use_polling: True`.

### Requirement 2: Webhook Ingest With Signature Verification And Dedup

**User Story:** As a security engineer, I want every inbound webhook
verified and deduplicated, so that unsigned or replayed events cannot
trigger a pipeline.

**Acceptance Criteria (EARS):**

1. WHEN a request arrives at `POST /api/v1/webhooks/scm/{project_id}` AND the configured provider's `verify_webhook_signature(...)` returns `False` THEN the system SHALL respond 401 AND SHALL NOT dispatch anything AND SHALL emit `pychestrate.source.webhook.signature_failed` at WARNING.
2. WHEN signature verification succeeds AND the webhook's `delivery_id` has been seen within `dedup_window_seconds` (default 3600) THEN the system SHALL respond 200 and skip dispatch.
3. WHEN a `push` event parses successfully THEN the system SHALL read the pipeline file at the pushed commit via `provider.read_file_at_ref(...)` AND call `PipelineService.trigger_run(...)` with `trigger_cause = TriggerCause(kind="webhook", reference=delivery_id)`.
4. IF the pipeline file does not exist at the commit THEN the system SHALL respond 200, log at INFO `pychestrate.source.pipeline_file_missing`, AND NOT create a pipeline run.
5. WHERE the event is a `pull_request.opened` or `pull_request.synchronize` THEN the system SHALL use the PR's head SHA as the target commit AND SHALL include `ref = refs/pull/<number>/merge` in the `PipelineRun`.

### Requirement 3: Commit-Status Posting

**User Story:** As a developer opening a PR, I want to see Pychestrate's
build status on the PR, so that I know whether to merge.

**Acceptance Criteria (EARS):**

1. WHEN `PipelineRun` transitions to `running`, `completed`, `failed`, or `cancelled` THEN the system SHALL post a commit status to the target commit via the provider's `post_commit_status(...)` with `context = "pychestrate/<filename>"`, `description` from the run summary, and a `target_url` to the run detail page.
2. IF `post_commit_status` returns `ProviderTransientError` THEN the system SHALL honor the Aspects retry policy (default 3 attempts, exponential backoff 500 ms → 10 s) before surfacing the failure.
3. WHEN the provider does not support status posting (capability `post_commit_status: False`) THEN the system SHALL log at INFO and skip the post without failing the pipeline run.
4. WHERE the event loop has posted the same `(context, commit_sha, state)` tuple within `status_dedup_seconds` (default 5) THEN the system SHALL skip the redundant post.

### Requirement 4: Polling Fallback

**User Story:** As an operator behind an egress firewall that blocks
inbound webhooks, I want Pychestrate to poll for new commits so that
pipelines can still run automatically.

**Acceptance Criteria (EARS):**

1. WHEN `use_polling: True` is configured for a project AND the provider supports polling THEN the system SHALL call `provider.list_refs(...)` every `poll_interval_seconds` (default 120) and compare observed HEAD SHAs against the per-project `last_seen_heads: dict[ref, sha]`.
2. IF a new head SHA is observed on a ref matched by `polling_ref_glob` (default `refs/heads/*`) THEN the system SHALL read the pipeline file at that commit AND trigger a run with `trigger_cause = TriggerCause(kind="polling", reference=ref)`.
3. WHEN polling runs AND the last sweep recorded an error for this project THEN the system SHALL refresh credentials through `1-secrets-vault` before issuing the next call.

## Property-Based Test Requirements

### Property 1: Dedup Is Idempotent Over Replayed Webhooks

- **Invariant:** For any set of webhook delivery ids, replaying the same id N times within the dedup window results in exactly one pipeline-run dispatch; replaying across the window boundary results in one dispatch per fresh window.
- **Generator:** `hypothesis.strategies.lists(text(alphabet=ascii_letters + digits, min_size=1, max_size=40), min_size=1, max_size=50)` for delivery ids and a time-travel fixture sampling times within and outside the window.
- **Assertion:** `dispatch_count == len(unique_within_window(deliveries))`.
- **Sample size:** 1000 generated cases

### Property 2: Status Post Dedup Collapses Bursts

- **Invariant:** For any burst of identical `(context, commit_sha, state)` tuples within `status_dedup_seconds`, exactly one post reaches the provider.
- **Generator:** `hypothesis.strategies.tuples(integers(min_value=1, max_value=50), floats(min_value=0.0, max_value=10.0))` as `(burst_size, interval_seconds)`.
- **Assertion:** `post_count == 1 if interval_seconds <= status_dedup_seconds else burst_size`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Webhook handler (accept + verify + enqueue) p99 < 150 ms. `post_commit_status` p99 < 800 ms excluding provider latency. Polling sweep p99 < 3 s per project at 100 refs. Dedup lookup p99 < 5 ms.
- **NFR-2 (Security):** All webhooks require HMAC verification via the provider; shared secret from `1-secrets-vault`. HTTPS-only endpoints. Incoming payload capped at `max_webhook_payload_bytes` (default 1 MiB) — oversized requests rejected 413. Commit-status credentials scoped per project.
- **NFR-3 (Observability):** Metrics `pychestrate_source_webhooks_received_total{project,provider,event_kind}` (counter), `pychestrate_source_webhook_signature_failures_total{project,provider}` (counter), `pychestrate_source_status_posts_total{project,provider,state}` (counter), `pychestrate_source_status_post_errors_total{project,provider,error_kind}` (counter), `pychestrate_source_poll_duration_seconds{project,provider}` (histogram). Log events `pychestrate.source.webhook.received`, `pychestrate.source.webhook.signature_failed`, `pychestrate.source.pipeline_file_missing`, `pychestrate.source.status_posted`, `pychestrate.source.poll.swept`. Trace spans `pychestrate.source.webhook`, `pychestrate.source.post_status`, `pychestrate.source.poll`.
- **NFR-4 (Reliability):** A provider outage SHALL NOT block webhook acceptance — the webhook handler enqueues into a durable queue; status posts retry with bounded backoff. Polling catches up missed commits after an outage (HEAD comparison is idempotent).

## Out of Scope

- Pipeline execution (see `6-pipeline-definition`).
- OAuth user sign-in from the SCM (see `1-authentication`).
- Mirroring whole-repo content locally (only pipeline files are read).

## Dependencies

- **Depends on:** `6-pipeline-definition`, `1-secrets-vault`, `1-rbac`, `1-audit-log`, `2-projects`, `0-persistence`, `0-message-bus`, `0-web-app-host`, `E-extension-host`.
- **Depended on by:** `6-pipeline-definition` (commit-status posting callbacks), `7-orchestration-metrics`.
- **Extension points exposed:** `factory: scm_provider` — GitHub, GitLab, Bitbucket, Gitea, custom; `resource: WebhookPayloadParserExtension` — per-provider payload parsers.
