"""
.. module:: audit.extensions.notification_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Audit kinds produced from 2-notification-hub entity topics (audit ORG-F08).

.. moduleauthor:: Code Craft AI LLC

Who added, changed or deleted a notification channel or rule is recorded here. A channel's secrets are never in these records: they carry the names of the
settings that are secret and the names of the settings that changed, not values. (The secrets vault records its own ``audit.secret.*`` entries when the
channel's secret is stored, replaced or removed.)
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, Tuple

from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension


def _audit_pack(*, class_name: str, topic: str, kind: str, description: str, required: Tuple[str, ...], properties: Dict[str, Any]) -> type:
    """
        Build one :class:`AuditEventTypeExtension` for a notification topic.
    """
    schema_properties = dict(properties)
    schema_properties["actor_user_id"] = {"type": ["string", "null"]}
    schema_properties["client_address"] = {"type": ["string", "null"]}
    rtnval = type(class_name, (AuditEventTypeExtension,), {
        "__doc__": "Canonical audit kind for ``{}``.".format(topic),
        "resource_extension_name": "audit_event_type",
        "kind": kind,
        "source_topic": topic,
        "payload_schema": {"type": "object", "required": list(required), "properties": schema_properties},
        "description": description,
    })
    return rtnval


_TEXT = {"type": "string"}
_TEXT_LIST = {"type": "array", "items": {"type": "string"}}

ChannelCreatedAuditEvents = _audit_pack(
    class_name="ChannelCreatedAuditEvents", topic="entity.notification.channel_created", kind="audit.notification.channel_created",
    description="A notification channel was added.", required=("channel_id", "name", "kind"),
    properties={"channel_id": _TEXT, "name": _TEXT, "kind": _TEXT, "secret_settings": _TEXT_LIST},
)
ChannelUpdatedAuditEvents = _audit_pack(
    class_name="ChannelUpdatedAuditEvents", topic="entity.notification.channel_updated", kind="audit.notification.channel_updated",
    description="A notification channel was switched on or off, changed, or had a secret replaced.", required=("channel_id", "name", "changed"),
    properties={"channel_id": _TEXT, "name": _TEXT, "changed": _TEXT_LIST},
)
ChannelDeletedAuditEvents = _audit_pack(
    class_name="ChannelDeletedAuditEvents", topic="entity.notification.channel_deleted", kind="audit.notification.channel_deleted",
    description="A notification channel was deleted.", required=("channel_id", "name"),
    properties={"channel_id": _TEXT, "name": _TEXT, "kind": _TEXT},
)
RuleCreatedAuditEvents = _audit_pack(
    class_name="RuleCreatedAuditEvents", topic="entity.notification.rule_created", kind="audit.notification.rule_created",
    description="A notification routing rule was added.", required=("rule_id", "event_pattern"),
    properties={"rule_id": _TEXT, "event_pattern": _TEXT, "template_name": _TEXT, "channel_ids": _TEXT_LIST, "recipients": _TEXT_LIST, "project_id": {"type": ["string", "null"]}},
)
RuleUpdatedAuditEvents = _audit_pack(
    class_name="RuleUpdatedAuditEvents", topic="entity.notification.rule_updated", kind="audit.notification.rule_updated",
    description="A notification routing rule was switched on or off.", required=("rule_id", "event_pattern"),
    properties={"rule_id": _TEXT, "event_pattern": _TEXT, "disabled": {"type": "boolean"}},
)
RuleDeletedAuditEvents = _audit_pack(
    class_name="RuleDeletedAuditEvents", topic="entity.notification.rule_deleted", kind="audit.notification.rule_deleted",
    description="A notification routing rule was deleted.", required=("rule_id", "event_pattern"),
    properties={"rule_id": _TEXT, "event_pattern": _TEXT},
)

NOTIFICATION_AUDIT_EVENT_TYPES = (
    ChannelCreatedAuditEvents, ChannelUpdatedAuditEvents, ChannelDeletedAuditEvents,
    RuleCreatedAuditEvents, RuleUpdatedAuditEvents, RuleDeletedAuditEvents,
)
