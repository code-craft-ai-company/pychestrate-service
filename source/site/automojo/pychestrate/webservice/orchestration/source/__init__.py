"""
.. module:: orchestration.source
    :synopsis: 6-source-integrations — SCM webhook ingest + commit-status posting.

Public surface:

* :class:`ScmProjectConfig`, :class:`ScmWebhookDelivery`,
  :class:`ScmLastSeenHead` — persistence rows.
* :class:`PushEvent`, :class:`PullRequestEvent`,
  :class:`WebhookAckResult`, :class:`WebhookAckState`,
  :class:`ScmEventKind`, :class:`ScmProjectConfigView`,
  :class:`SourceIntegrationsAspects` — IO shapes.
* :func:`set_project_config`, :func:`get_project_config`,
  :func:`handle_webhook`, :func:`record_last_seen_head`,
  :func:`get_last_seen_head`,
  :func:`list_recent_deliveries`.
* :class:`ScmProviderProtocol` factory contract +
  reference :class:`GithubScmProvider`.
* :class:`SourceEventTopics`.
* Errors: :class:`SourceIntegrationsError`,
  :class:`ScmConfigNotFoundError`,
  :class:`ScmProviderNotFoundError`,
  :class:`ScmSignatureInvalidError`,
  :class:`ScmPayloadInvalidError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.orchestration.source.errors import (
    ScmConfigNotFoundError,
    ScmPayloadInvalidError,
    ScmProviderNotFoundError,
    ScmSignatureInvalidError,
    SourceIntegrationsError,
)
from automojo.pychestrate.webservice.orchestration.source.events import (
    SourceEventTopics,
)
from automojo.pychestrate.webservice.orchestration.source.factories.github_provider import (
    GithubScmProvider,
)
from automojo.pychestrate.webservice.orchestration.source.factories.provider_protocol import (
    PullRequestEvent,
    PushEvent,
    ScmEventKind,
    ScmProviderProtocol,
)
from automojo.pychestrate.webservice.orchestration.source.models import (
    ScmLastSeenHead,
    ScmProjectConfig,
    ScmWebhookDelivery,
)
from automojo.pychestrate.webservice.orchestration.source.service import (
    ScmLastSeenHeadView,
    ScmProjectConfigView,
    ScmWebhookDeliveryView,
    SourceIntegrationsAspects,
    WebhookAckResult,
    WebhookAckState,
    get_last_seen_head,
    get_project_config,
    handle_webhook,
    list_recent_deliveries,
    record_last_seen_head,
    set_project_config,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`GithubScmProvider` reference
        implementation.
    """
    register_factory_implementation(implementation=GithubScmProvider)
    return
