"""
.. module:: webhooks_out
    :synopsis: 8-webhooks-out — outbound webhook delivery.

Public surface:

* :class:`WebhookTarget`, :class:`WebhookDelivery` —
  persistence rows.
* :class:`DeliveryOutcome`, :class:`SignatureScheme` —
  enums.
* :class:`WebhookTargetView`, :class:`WebhookDeliveryView`,
  :class:`SignedRequest` — IO shapes.
* :func:`register_target`, :func:`get_target`,
  :func:`list_targets_for_project`,
  :func:`disable_target`,
  :func:`build_signed_request`,
  :func:`record_delivery_attempt`,
  :func:`list_recent_deliveries_for_target`,
  :func:`compute_signature`.
* :class:`NotificationChannelProtocol` factory contract +
  reference :class:`WebhookNotificationChannel`.
* :class:`WebhookOutEventTopics`.
* Errors: :class:`WebhookOutError`,
  :class:`WebhookTargetNotFoundError`,
  :class:`WebhookTargetConflictError`,
  :class:`WebhookTargetInvalidError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.webhooks_out.errors import (
    WebhookOutError,
    WebhookTargetConflictError,
    WebhookTargetInvalidError,
    WebhookTargetNotFoundError,
)
from automojo.pychestrate.webservice.webhooks_out.events import (
    WebhookOutEventTopics,
)
from automojo.pychestrate.webservice.webhooks_out.factories.notification_channel_protocol import (
    NotificationChannelProtocol,
)
from automojo.pychestrate.webservice.webhooks_out.factories.webhook_channel import (
    WebhookNotificationChannel,
)
from automojo.pychestrate.webservice.webhooks_out.models import (
    DeliveryOutcome,
    SignatureScheme,
    WebhookDelivery,
    WebhookTarget,
)
from automojo.pychestrate.webservice.webhooks_out.service import (
    SignedRequest,
    WebhookDeliveryView,
    WebhookTargetView,
    build_signed_request,
    compute_signature,
    disable_target,
    get_target,
    list_recent_deliveries_for_target,
    list_targets_for_project,
    record_delivery_attempt,
    register_target,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`WebhookNotificationChannel`
        reference under the ``notification_channel`` factory
        protocol.
    """
    register_factory_implementation(implementation=WebhookNotificationChannel)
    return
