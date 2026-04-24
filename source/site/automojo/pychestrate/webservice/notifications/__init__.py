"""
.. module:: notifications
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 2-notification-hub feature — channel + template dispatch.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
    register_resource_extension,
)
from automojo.pychestrate.webservice.notifications.extensions.template import (
    NotificationTemplateExtension,
)
from automojo.pychestrate.webservice.notifications.extensions.run_failed_template import (
    RunFailedTemplate,
)
from automojo.pychestrate.webservice.notifications.factories.smtp_email import (
    SmtpEmailChannel,
)
from automojo.pychestrate.webservice.notifications.factories.webhook_channels import (
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
    return
