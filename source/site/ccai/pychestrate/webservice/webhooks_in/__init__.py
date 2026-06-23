"""
.. module:: webhooks_in
    :synopsis: 8-webhooks-in — inbound webhook dispatch.

Public surface:

* :class:`WebhookConfiguration`,
  :class:`WebhookSeenDelivery`,
  :class:`WebhookDeadletter` — persistence rows.
* :class:`SignatureAlgorithm`, :class:`SignatureEncoding`,
  :class:`SignatureHeaderSpec` — parser declaration helpers.
* :class:`NormalizedEvent`, :class:`ParsedWebhook`,
  :class:`StructuredRejection` — IO shapes.
* :func:`create_webhook`, :func:`get_webhook`,
  :func:`list_webhooks`, :func:`disable_webhook`.
* :class:`WebhookConfigurationView`.
* :func:`dispatch_inbound_webhook` +
  :class:`WebhookDispatchResult`.
* :func:`verify_signature` + :class:`VerificationOutcome`.
* :func:`record_delivery_or_replay` + :class:`ReplayOutcome`.
* :func:`publish_domain_events`.
* :class:`InboundWebhookParserProtocol` factory contract +
  reference :class:`GenericHmacWebhookParser`.
* :class:`WebhookInEventTopics`.
* Errors: :class:`WebhookInError`,
  :class:`WebhookConfigurationConflictError`,
  :class:`WebhookConfigurationInvalidError`,
  :class:`WebhookConfigurationNotFoundError`,
  :class:`WebhookProviderUnknownError`,
  :class:`WebhookSignatureInvalidError`,
  :class:`WebhookReplayDetectedError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from ccai.pychestrate.webservice.webhooks_in.configuration_service import (
    WebhookConfigurationView,
    create_webhook,
    disable_webhook,
    get_webhook,
    list_webhooks,
)
from ccai.pychestrate.webservice.webhooks_in.dispatcher import (
    WebhookDispatchResult,
    dispatch_inbound_webhook,
)
from ccai.pychestrate.webservice.webhooks_in.errors import (
    WebhookConfigurationConflictError,
    WebhookConfigurationInvalidError,
    WebhookConfigurationNotFoundError,
    WebhookInError,
    WebhookProviderUnknownError,
    WebhookReplayDetectedError,
    WebhookSignatureInvalidError,
)
from ccai.pychestrate.webservice.webhooks_in.events import (
    WebhookInEventTopics,
)
from ccai.pychestrate.webservice.webhooks_in.factories.generic_hmac_parser import (
    GenericHmacWebhookParser,
)
from ccai.pychestrate.webservice.webhooks_in.factories.inbound_webhook_parser import (
    InboundWebhookParserProtocol,
)
from ccai.pychestrate.webservice.webhooks_in.models import (
    NormalizedEvent,
    ParsedWebhook,
    SignatureAlgorithm,
    SignatureEncoding,
    SignatureHeaderSpec,
    StructuredRejection,
    WebhookConfiguration,
    WebhookDeadletter,
    WebhookSeenDelivery,
)
from ccai.pychestrate.webservice.webhooks_in.normalization import (
    publish_domain_events,
)
from ccai.pychestrate.webservice.webhooks_in.replay_cache import (
    ReplayOutcome,
    record_delivery_or_replay,
)
from ccai.pychestrate.webservice.webhooks_in.verification import (
    VerificationOutcome,
    verify_signature,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`GenericHmacWebhookParser`
        reference under the ``inbound_webhook_parser``
        factory protocol.
    """
    register_factory_implementation(implementation=GenericHmacWebhookParser)
    return
