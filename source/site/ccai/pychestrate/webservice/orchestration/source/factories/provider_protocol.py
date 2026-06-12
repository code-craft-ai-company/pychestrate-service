"""
.. module:: orchestration.source.factories.provider_protocol
    :synopsis: ``scm_provider`` factory contract + parsed-event types.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


class ScmEventKind(str, enum.Enum):
    """
        Subset of webhook event kinds an SCM provider may emit.
        M1 covers the push + pull-request paths; later kinds
        (``release``, ``check_suite``, etc.) graduate as
        feature owners need them.
    """
    PUSH = "push"
    PULL_REQUEST = "pull_request"
    PING = "ping"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PushEvent:
    """
        Parsed view of a push event.
    """
    repo_key: str
    ref: str
    commit_sha: str
    pusher_actor: str
    is_force_push: bool = False


@dataclass(frozen=True)
class PullRequestEvent:
    """
        Parsed view of a pull-request event.

        :param action: Provider-side action label
                       (``opened``, ``synchronize``, ``closed``,
                       ``reopened``).
    """
    repo_key: str
    pr_number: int
    head_ref: str
    head_commit_sha: str
    base_ref: str
    title: str
    action: str


@dataclass(frozen=True)
class WebhookHeaders:
    """
        Frozen header view passed to the provider's signature
        verifier. Keys are case-folded so providers don't have
        to.
    """
    delivery_id: str
    event_kind: str
    signature: str
    raw_headers: Mapping[str, str]


@dataclass(frozen=True)
class ParsedWebhook:
    """
        Aggregated provider parse result.

        :param event_kind: Resolved :class:`ScmEventKind`.
        :param push: Populated when ``event_kind == PUSH``.
        :param pull_request: Populated when ``event_kind ==
                             PULL_REQUEST``.
    """
    event_kind: ScmEventKind
    push: Optional[PushEvent] = None
    pull_request: Optional[PullRequestEvent] = None


class ScmProviderProtocol(FactoryProtocolBase):
    """
        Contract for ``scm_provider`` extensions. M1 in-tree
        cover GitHub; M2 widens to GitLab, Bitbucket, Gitea via
        new factory implementations.
    """

    factory_protocol_name: str = "scm_provider"
    protocol_schema_version: int = 1

    is_published: bool = True
    published_docs_url: str = "https://docs.pychestrate.io/plugin-api/scm_provider"
    published_reference: str = (
        "ccai.pychestrate.webservice.orchestration.source.factories.github_provider"
        ".GithubScmProvider"
    )

    @classmethod
    def provider_name(cls) -> str:
        """
            Stable identifier the
            :func:`set_project_config` service uses to bind a
            provider to a project.
        """
        raise NotImplementedError("Subclasses must implement provider_name")

    @classmethod
    def normalize_headers(cls, *, raw_headers: Mapping[str, str]) -> WebhookHeaders:
        """
            Extract delivery id / event kind / signature header
            values from the inbound request.
        """
        raise NotImplementedError("Subclasses must implement normalize_headers")

    @classmethod
    def verify_signature(
            cls,
            *,
            secret: bytes,
            raw_body: bytes,
            headers: WebhookHeaders
        ) -> bool:
        """
            Return True when the supplied signature matches the
            expected HMAC over ``raw_body`` using ``secret``.
        """
        raise NotImplementedError("Subclasses must implement verify_signature")

    @classmethod
    def parse_event(
            cls,
            *,
            headers: WebhookHeaders,
            payload: Mapping[str, Any]
        ) -> ParsedWebhook:
        """
            Translate a verified webhook payload into a typed
            :class:`ParsedWebhook`.
        """
        raise NotImplementedError("Subclasses must implement parse_event")
