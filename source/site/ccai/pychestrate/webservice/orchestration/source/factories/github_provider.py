"""
.. module:: orchestration.source.factories.github_provider
    :synopsis: GithubScmProvider — reference SCM provider.

Verifies inbound webhook signatures using the
``X-Hub-Signature-256`` HMAC-SHA-256 scheme that GitHub
publishes. Parses ``push`` and ``pull_request`` payloads into
the typed :class:`PushEvent` / :class:`PullRequestEvent`
shapes.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hmac
import hashlib

from typing import Any, Mapping

from ccai.pychestrate.webservice.orchestration.source.factories.provider_protocol import (
    ParsedWebhook,
    PullRequestEvent,
    PushEvent,
    ScmEventKind,
    ScmProviderProtocol,
    WebhookHeaders,
)


GITHUB_PROVIDER_NAME: str = "github"
SIGNATURE_PREFIX: str = "sha256="
GITHUB_DELIVERY_HEADER: str = "x-github-delivery"
GITHUB_EVENT_HEADER: str = "x-github-event"
GITHUB_SIGNATURE_HEADER: str = "x-hub-signature-256"


class GithubScmProvider(ScmProviderProtocol):
    """
        Reference GitHub webhook provider.
    """

    factory_protocol_name: str = "scm_provider"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 500

    @classmethod
    def provider_name(cls) -> str:
        rtnval = GITHUB_PROVIDER_NAME
        return rtnval

    @classmethod
    def normalize_headers(
            cls,
            *,
            raw_headers: Mapping[str, str]
        ) -> WebhookHeaders:
        folded: dict = {
            key.lower(): value for key, value in raw_headers.items()
        }
        rtnval = WebhookHeaders(
            delivery_id=folded.get(GITHUB_DELIVERY_HEADER, ""),
            event_kind=folded.get(GITHUB_EVENT_HEADER, ""),
            signature=folded.get(GITHUB_SIGNATURE_HEADER, ""),
            raw_headers=folded,
        )
        return rtnval

    @classmethod
    def verify_signature(
            cls,
            *,
            secret: bytes,
            raw_body: bytes,
            headers: WebhookHeaders
        ) -> bool:
        signature = headers.signature
        if signature is None or len(signature) == 0:
            return False
        if not signature.startswith(SIGNATURE_PREFIX):
            return False
        provided = signature[len(SIGNATURE_PREFIX):]
        computed = hmac.new(
            key=secret, msg=raw_body, digestmod=hashlib.sha256,
        ).hexdigest()
        rtnval = hmac.compare_digest(provided, computed)
        return rtnval

    @classmethod
    def parse_event(
            cls,
            *,
            headers: WebhookHeaders,
            payload: Mapping[str, Any]
        ) -> ParsedWebhook:
        event_kind_raw = (headers.event_kind or "").lower()
        if event_kind_raw == "ping":
            rtnval = ParsedWebhook(event_kind=ScmEventKind.PING)
            return rtnval
        if event_kind_raw == "push":
            push = _parse_push(payload=payload)
            rtnval = ParsedWebhook(
                event_kind=ScmEventKind.PUSH, push=push,
            )
            return rtnval
        if event_kind_raw == "pull_request":
            pull = _parse_pull_request(payload=payload)
            rtnval = ParsedWebhook(
                event_kind=ScmEventKind.PULL_REQUEST, pull_request=pull,
            )
            return rtnval

        rtnval = ParsedWebhook(event_kind=ScmEventKind.UNKNOWN)
        return rtnval


def _parse_push(*, payload: Mapping[str, Any]) -> PushEvent:
    repository = payload.get("repository", {}) or {}
    repo_key = repository.get("full_name", "") or ""
    pusher = payload.get("pusher", {}) or {}
    pusher_actor = pusher.get("name", "") or ""
    rtnval = PushEvent(
        repo_key=repo_key,
        ref=payload.get("ref", "") or "",
        commit_sha=payload.get("after", "") or "",
        pusher_actor=pusher_actor,
        is_force_push=bool(payload.get("forced", False)),
    )
    return rtnval


def _parse_pull_request(*, payload: Mapping[str, Any]) -> PullRequestEvent:
    pull = payload.get("pull_request", {}) or {}
    head = pull.get("head", {}) or {}
    base = pull.get("base", {}) or {}
    repository = payload.get("repository", {}) or {}
    rtnval = PullRequestEvent(
        repo_key=repository.get("full_name", "") or "",
        pr_number=int(payload.get("number", pull.get("number", 0)) or 0),
        head_ref=head.get("ref", "") or "",
        head_commit_sha=head.get("sha", "") or "",
        base_ref=base.get("ref", "") or "",
        title=pull.get("title", "") or "",
        action=payload.get("action", "") or "",
    )
    return rtnval
