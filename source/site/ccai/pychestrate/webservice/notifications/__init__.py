"""
.. module:: notifications
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 2-notification-hub feature — channel + template dispatch.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
    register_resource_extension,
)
from ccai.pychestrate.webservice.notifications.extensions.template import (
    NotificationTemplateExtension,
)
from ccai.pychestrate.webservice.notifications.extensions.channel_test_template import (
    ChannelTestTemplate,
)
from ccai.pychestrate.webservice.notifications.extensions.run_failed_template import (
    RunFailedTemplate,
)
from ccai.pychestrate.webservice.notifications.extensions.run_succeeded_template import (
    RunSucceededTemplate,
)
from ccai.pychestrate.webservice.notifications.factories.smtp_email import (
    SmtpEmailChannel,
)
from ccai.pychestrate.webservice.notifications.factories.webhook_channels import (
    GenericWebhookChannel,
    MsTeamsWebhookChannel,
    PagerDutyEventsV2Channel,
    SlackWebhookChannel,
)


def register_builtin_extensions() -> None:
    """
        Register the in-tree ``notification_channel`` implementations and
        :class:`NotificationTemplateExtension` packs for M2.

        :returns: None.
    """
    register_factory_implementation(implementation=SmtpEmailChannel)
    register_factory_implementation(implementation=SlackWebhookChannel)
    register_factory_implementation(implementation=MsTeamsWebhookChannel)
    register_factory_implementation(implementation=PagerDutyEventsV2Channel)
    register_factory_implementation(implementation=GenericWebhookChannel)
    register_resource_extension(
        base_class=NotificationTemplateExtension,
        extension=RunFailedTemplate,
    )
    register_resource_extension(
        base_class=NotificationTemplateExtension,
        extension=RunSucceededTemplate,
    )
    register_resource_extension(
        base_class=NotificationTemplateExtension,
        extension=ChannelTestTemplate,
    )
    return
