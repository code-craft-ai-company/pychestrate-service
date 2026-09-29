"""
.. module:: audit.extensions.ip_allocation_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Audit kind for a lab manager releasing an IP address that
               someone else holds.

.. moduleauthor:: Code Craft AI LLC

An IP address is checked in by the person who checked it out. A person
holding the resource-management permission may release it for them,
giving a reason. The row change reaches the audit log through the
data-change bridge (``audit.data.updated``); this kind adds what the
bridge cannot know: that it was released for someone else, whose it was,
and why.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension


IP_FORCE_RELEASED_TOPIC: str = "entity.ip_allocation.force_released"


class IpAllocationForceReleasedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.ip_allocation.force_released``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.ip_allocation.force_released"
    actor_payload_keys: tuple = ("actor_user_id",)
    source_topic: str = IP_FORCE_RELEASED_TOPIC
    payload_schema: dict = {
        "type": "object",
        "required": ["allocation_id", "ip_address", "reason"],
        "properties": {
            "allocation_id": {"type": "integer"},
            "pool_id": {"type": ["integer", "null"]},
            "ip_address": {"type": "string"},
            "holder_user_id": {"type": ["string", "null"]},
            "reason": {"type": "string"},
            "actor_user_id": {"type": ["string", "null"]},
        },
    }
    description: str = "A lab manager released an IP address someone else held, and why."
