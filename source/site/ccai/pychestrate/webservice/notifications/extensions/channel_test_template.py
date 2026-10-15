"""
.. module:: notifications.extensions.channel_test_template
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The message the Notifications page's "Send test message" button sends.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, ClassVar, Mapping, Tuple

from ccai.pychestrate.webservice.notifications.extensions.template import (
    NotificationTemplateExtension,
    RenderedMessage,
)


class ChannelTestTemplate(NotificationTemplateExtension):
    """
        The text of a test message. It describes no event and a routing rule may not use it, so it can only ever be sent by
        an administrator pressing the button.
    """

    resource_extension_name: ClassVar[str] = "notification_template"
    template_name: ClassVar[str] = "channel_test"
    default_severity: ClassVar[str] = "INFO"
    description: ClassVar[str] = "The test message sent from the Notifications page."
    event_topics: ClassVar[Tuple[str, ...]] = ()
    is_test_message: ClassVar[bool] = True

    @classmethod
    def render(cls, *, payload: Mapping[str, Any]) -> RenderedMessage:
        """
            Render the test message.

            :param payload: ``channel_name`` and ``sent_by`` (both optional).

            :returns: The :class:`RenderedMessage`.
        """
        channel_name = payload.get("channel_name", "this channel")
        sent_by = payload.get("sent_by", "an administrator")
        subject = "[Pychestrate] Test message"
        body = "This is a test message for the notification channel {}, sent by {}. If you can read it, the channel works.".format(channel_name, sent_by)
        rtnval = RenderedMessage(subject=subject, body=body, severity=cls.default_severity)
        return rtnval
