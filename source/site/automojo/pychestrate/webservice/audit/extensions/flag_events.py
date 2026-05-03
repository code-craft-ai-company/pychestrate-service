"""
.. module:: audit.extensions.flag_events
    :synopsis: Audit kinds produced from 1-feature-flags entity topics.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.audit.extensions.event_type import (
    AuditEventTypeExtension,
)


class FlagCreatedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.flag.created``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.flag.created"
    source_topic: str = "entity.flag.created"
    payload_schema: dict = {
        "type": "object",
        "required": ["flag_key"],
        "properties": {
            "flag_key": {"type": "string"},
            "default_value": {"type": "boolean"},
            "actor_user_id": {"type": ["string", "null"]},
        },
    }
    description: str = "A feature flag was created."


class FlagUpdatedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.flag.updated``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.flag.updated"
    source_topic: str = "entity.flag.updated"
    payload_schema: dict = {
        "type": "object",
        "required": ["flag_key"],
        "properties": {
            "flag_key": {"type": "string"},
            "actor_user_id": {"type": ["string", "null"]},
        },
    }
    description: str = "A feature flag's rules / default were updated."


class FlagRetiredAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.flag.retired``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.flag.retired"
    source_topic: str = "entity.flag.retired"
    payload_schema: dict = {
        "type": "object",
        "required": ["flag_key"],
        "properties": {
            "flag_key": {"type": "string"},
            "actor_user_id": {"type": ["string", "null"]},
        },
    }
    description: str = "A feature flag was retired."


class FlagRemovedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.flag.removed``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.flag.removed"
    source_topic: str = "entity.flag.removed"
    payload_schema: dict = {
        "type": "object",
        "required": ["flag_key"],
        "properties": {
            "flag_key": {"type": "string"},
            "actor_user_id": {"type": ["string", "null"]},
        },
    }
    description: str = "A feature flag was permanently removed."
