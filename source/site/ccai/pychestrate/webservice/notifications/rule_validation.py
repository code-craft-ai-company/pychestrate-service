"""
.. module:: notifications.rule_validation
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Check a routing rule's fields, so a rule that could never send is refused with the reason (REST and the Notifications page).

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from typing import Any, Dict, List, Mapping, Optional

from ccai.pychestrate.webservice.notifications import service as notification_service
from ccai.pychestrate.webservice.notifications.exceptions import (
    ChannelNotFoundError,
    RoutingRuleInvalidError,
    TemplateNotFoundError,
)
from ccai.pychestrate.webservice.notifications.router import pattern_matches
from ccai.pychestrate.webservice.notifications.run_notifier import NOTIFIED_TOPICS
from ccai.pychestrate.webservice.projects.models import Project


#: Deliveries one rule may ask for (channels times recipients), so a typo cannot fan out to hundreds.
MAX_CHANNELS: int = 5
MAX_RECIPIENTS: int = 20


def is_uuid(value: Any) -> bool:
    """
        Whether a value is a UUID.

        :param value: Anything.

        :returns: True for a UUID in any text form.
    """
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def validate_rule_fields(*, db_session: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
    """
        Check a rule's fields and return them cleaned.

        :param db_session: Active SQLAlchemy session.
        :param payload: ``event_pattern``, ``template_name``, ``channel_ids``, ``recipients``, optional ``project_id`` and
                        ``rate_limit_per_minute``.

        :returns: The cleaned fields, ready for :func:`notification_service.create_routing_rule`.
        :raises: RoutingRuleInvalidError saying what is wrong.
    """
    if payload.get("filter_tag_expression", None) not in (None, ""):
        raise RoutingRuleInvalidError("filter_tag_expression is not supported yet; a rule matches on event_pattern and project_id only.")

    pattern = str(payload.get("event_pattern", "") or "").strip()
    if len(pattern) == 0:
        raise RoutingRuleInvalidError("event_pattern is required (for example 'entity.run.failed').")
    if not any(pattern_matches(pattern=pattern, topic=topic) for topic in NOTIFIED_TOPICS):
        raise RoutingRuleInvalidError(
            "event_pattern '{}' matches none of the events that can be notified: {}.".format(pattern, ", ".join(NOTIFIED_TOPICS)),
            {"event_pattern": pattern},
        )

    template_name = str(payload.get("template_name", "") or "").strip()
    if len(template_name) == 0:
        raise RoutingRuleInvalidError("template_name is required (for example 'run_failed').")
    try:
        template = notification_service._resolve_template(template_name=template_name)
    except TemplateNotFoundError:
        raise RoutingRuleInvalidError("No notification template is named '{}'.".format(template_name), {"template_name": template_name}) from None
    if template.is_test_message is True:
        raise RoutingRuleInvalidError(
            "Template '{}' is the text of the test message sent from the Notifications page; a routing rule cannot use it.".format(template_name),
            {"template_name": template_name},
        )
    fitting = [topic for topic in NOTIFIED_TOPICS if pattern_matches(pattern=pattern, topic=topic) and (len(template.event_topics) == 0 or topic in template.event_topics)]
    if len(fitting) == 0:
        raise RoutingRuleInvalidError(
            "Template '{}' describes {}, and event_pattern '{}' matches none of them, so this rule would never send.".format(
                template_name, ", ".join(template.event_topics), pattern),
            {"template_name": template_name, "event_pattern": pattern},
        )

    channel_ids = payload.get("channel_ids", None)
    if not isinstance(channel_ids, list) or len(channel_ids) == 0 or len(channel_ids) > MAX_CHANNELS:
        raise RoutingRuleInvalidError("channel_ids must list between 1 and {} channel ids.".format(MAX_CHANNELS))
    for channel_id in channel_ids:
        if not is_uuid(channel_id):
            raise RoutingRuleInvalidError("channel_ids holds a value that is not a channel id: {!r}.".format(channel_id))
        try:
            notification_service.read_channel(db_session=db_session, channel_id=str(channel_id))
        except ChannelNotFoundError:
            raise RoutingRuleInvalidError("No notification channel has the id {}.".format(channel_id), {"channel_id": str(channel_id)}) from None

    recipients = payload.get("recipients", None)
    if not isinstance(recipients, list) or len(recipients) == 0 or len(recipients) > MAX_RECIPIENTS:
        raise RoutingRuleInvalidError("recipients must list between 1 and {} addresses.".format(MAX_RECIPIENTS))
    cleaned_recipients: List[str] = []
    for recipient in recipients:
        if not isinstance(recipient, str) or len(recipient.strip()) == 0 or len(recipient) > 320:
            raise RoutingRuleInvalidError("recipients holds a value that is not an address: {!r}.".format(recipient))
        cleaned_recipients.append(recipient.strip())

    project_id: Optional[str] = None
    if payload.get("project_id", None) not in (None, ""):
        project_id = str(payload["project_id"])
        if not is_uuid(project_id) or db_session.query(Project.project_id).filter(Project.project_id == project_id).first() is None:
            raise RoutingRuleInvalidError("No project has the id {}.".format(project_id), {"project_id": project_id})

    rate_limit = payload.get("rate_limit_per_minute", None)
    if rate_limit is not None and (isinstance(rate_limit, bool) or not isinstance(rate_limit, int) or rate_limit < 1 or rate_limit > 10000):
        raise RoutingRuleInvalidError("rate_limit_per_minute must be a whole number from 1 to 10000, or left out for no limit.")

    rtnval = {
        "project_id": project_id, "event_pattern": pattern, "template_name": template_name,
        "channel_ids": [str(channel_id) for channel_id in channel_ids], "recipients": cleaned_recipients,
        "rate_limit_per_minute": rate_limit,
    }
    return rtnval
