"""
.. module:: notifications.extensions.run_succeeded_template
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference RunSucceededTemplate (2-notification-hub T2.6).

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


class RunSucceededTemplate(NotificationTemplateExtension):
    """
        Reference template for ``entity.run.completed`` events: a run that
        finished without a failure. The subject names the run and the project;
        the body is a three-line summary, like the run-failed template's.
    """

    resource_extension_name: ClassVar[str] = "notification_template"
    template_name: ClassVar[str] = "run_succeeded"
    default_severity: ClassVar[str] = "INFO"
    description: ClassVar[str] = "Reference template emitted when a run completes."
    event_topics: ClassVar[Tuple[str, ...]] = (RunStateEventTopics.COMPLETED,)

    @classmethod
    def render(cls, *, payload: Mapping[str, Any]) -> RenderedMessage:
        """
            Render the subject and body for a run-completed notification.

            :param payload: Opaque event mapping (``run_id``, ``project_slug``, ``reason``).

            :returns: The :class:`RenderedMessage`.
        """
        run_id = payload.get("run_id", "<unknown>")
        project_slug = payload.get("project_slug", "<unknown>")
        reason = payload.get("reason", "")
        job_name = payload.get("job_name", None)
        if job_name:
            subject = "[Pychestrate] {} ({}) completed in {}".format(job_name, str(run_id)[:8], project_slug)
        else:
            subject = "[Pychestrate] Run {} completed in {}".format(run_id, project_slug)
        body_lines = []
        if job_name:
            body_lines.append("Job: {}".format(job_name))
        body_lines.extend(["Run id: {}".format(run_id), "Project: {}".format(project_slug)])
        if payload.get("triggered_by", None):
            body_lines.append("Triggered by: {}".format(payload["triggered_by"]))
        if reason:
            body_lines.append("Note: {}".format(reason))
        if payload.get("run_url", None):
            body_lines.append("Open: {}".format(payload["run_url"]))
        rtnval = RenderedMessage(subject=subject, body="\n".join(body_lines), severity=cls.default_severity)
        return rtnval
