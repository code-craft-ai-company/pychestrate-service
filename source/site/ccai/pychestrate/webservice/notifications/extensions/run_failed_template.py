"""
.. module:: notifications.extensions.run_failed_template
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference RunFailedTemplate for 2-notification-hub M1.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, ClassVar, Mapping, Tuple

from ccai.pychestrate.webservice.jobs.run.state.events import RunStateEventTopics
from ccai.pychestrate.webservice.notifications.extensions.template import (
    NotificationTemplateExtension,
    RenderedMessage,
)


class RunFailedTemplate(NotificationTemplateExtension):
    """
        Reference template for ``entity.run.failed`` events. The subject
        line includes the run id and the project slug; the body is a
        three-line summary.
    """

    resource_extension_name: ClassVar[str] = "notification_template"
    template_name: ClassVar[str] = "run_failed"
    default_severity: ClassVar[str] = "ERROR"
    description: ClassVar[str] = "Reference template emitted when a run fails."
    event_topics: ClassVar[Tuple[str, ...]] = (RunStateEventTopics.FAILED,)

    @classmethod
    def render(cls, *, payload: Mapping[str, Any]) -> RenderedMessage:
        """
            Render the subject and body for a run-failed notification.

            :param payload: Opaque event mapping.

            :returns: The :class:`RenderedMessage`.
        """
        run_id = payload.get("run_id", "<unknown>")
        project_slug = payload.get("project_slug", "<unknown>")
        reason = payload.get("reason", "")

        subject = "[Pychestrate] Run {} failed in {}".format(run_id, project_slug)

        body_lines = []
        body_lines.append("Run id: {}".format(run_id))
        body_lines.append("Project: {}".format(project_slug))
        body_lines.append("Reason: {}".format(reason))
        body = "\n".join(body_lines)

        rtnval = RenderedMessage(
            subject=subject,
            body=body,
            severity=cls.default_severity,
        )
        return rtnval
