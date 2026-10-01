"""
.. module:: audit.extensions.resource_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Audit kinds produced from resource-inventory entity topics (RES-22).

.. moduleauthor:: Code Craft AI LLC

A lab manager asking "who renamed this device, who put it in maintenance, who retired it" found nothing:
the inventory published ``entity.resource.*`` events and no audit kind listened. These kinds record a
resource being registered, its name, description or tags being changed, and its state changing (which covers
retirement and quarantine). The record's target is ``resource:<id>`` and its actor is the user who acted.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension


_RESOURCE_SCHEMA = {
    "type": "object",
    "required": ["resource_id", "project_id"],
    "properties": {
        "resource_id": {"type": "string"},
        "project_id": {"type": "string"},
        "kind": {"type": "string"},
        "display_name": {"type": "string"},
        "changed": {"type": "array", "items": {"type": "string"}},
        "from_state": {"type": "string"},
        "to_state": {"type": "string"},
        "reason": {"type": "string"},
        "actor": {"type": "string"},
        "actor_user_id": {"type": ["string", "null"]},
        "target_ref": {"type": "string"},
    },
}


class ResourceRegisteredAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.resource.registered``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.resource.registered"
    source_topic: str = "entity.resource.registered"
    payload_schema: dict = _RESOURCE_SCHEMA
    description: str = "A resource (a device, for example) was registered."


class ResourceUpdatedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.resource.updated``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.resource.updated"
    source_topic: str = "entity.resource.updated"
    payload_schema: dict = _RESOURCE_SCHEMA
    description: str = "A resource's name, description or tags were changed."


class ResourceStateChangedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.resource.state_changed`` (maintenance, quarantine, retirement ...).
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.resource.state_changed"
    source_topic: str = "entity.resource.state_changed"
    payload_schema: dict = _RESOURCE_SCHEMA
    description: str = "A resource's state changed (for example to maintenance, quarantined or retired)."


RESOURCE_AUDIT_EVENT_TYPES = (
    ResourceRegisteredAuditEvents,
    ResourceUpdatedAuditEvents,
    ResourceStateChangedAuditEvents,
)
