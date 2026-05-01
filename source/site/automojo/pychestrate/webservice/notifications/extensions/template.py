"""
.. module:: notifications.extensions.template
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: NotificationTemplateExtension base class.

.. moduleauthor:: Automation Mojo LLC

Concrete templates override :meth:`render` to produce a
(subject, body) pair from an event payload. The template name is
immutable and used as the key in the routing rules table.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from automojo.pychestrate.webservice.extensions.resource_extension import ResourceExtension


@dataclass(frozen=True)
class RenderedMessage:
    """
        Rendered output from :meth:`NotificationTemplateExtension.render`.

        :param subject: Subject line (plain text).
        :param body: Body text (plain / markdown / HTML per template).
        :param severity: One of ``DEBUG | INFO | WARN | ERROR | CRITICAL``.
    """
    subject: str
    body: str
    severity: str


class NotificationTemplateExtension(ResourceExtension):
    """
        Base class for a named notification template.
    """

    resource_extension_name: ClassVar[str] = "notification_template"
    template_name: ClassVar[str] = ""
    default_severity: ClassVar[str] = "INFO"
    description: ClassVar[str] = ""

    is_published: ClassVar[bool] = True
    published_docs_url: ClassVar[str] = (
        "https://docs.pychestrate.io/plugin-api/NotificationTemplateExtension"
    )
    published_reference: ClassVar[str] = (
        "automojo.pychestrate.webservice.notifications.extensions.run_failed_template"
        ".RunFailedTemplate"
    )

    @classmethod
    def render(cls, *, payload: Mapping[str, Any]) -> RenderedMessage:
        """
            Render a message from an event payload.

            :param payload: Opaque mapping from the source bus event.

            :returns: The :class:`RenderedMessage`.
        """
        raise NotImplementedError("Subclasses must implement render()")
