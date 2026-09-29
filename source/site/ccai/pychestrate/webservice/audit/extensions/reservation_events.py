"""
.. module:: audit.extensions.reservation_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Audit kind for a lab manager acting on someone else's
               reservation.

.. moduleauthor:: Code Craft AI LLC

A reservation is changed or cancelled by its owner. A person holding the
resource-management permission may also do it for the owner, giving a
reason. The row change itself reaches the audit log through the
data-change bridge (``audit.data.updated``, with the acting user); this
kind adds what the bridge cannot know: that it was done for someone
else, whose reservation it was, and why.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension


RESERVATION_OVERRIDDEN_TOPIC: str = "entity.reservation.overridden"


class ReservationOverriddenAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.reservation.overridden``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.reservation.overridden"
    actor_payload_keys: tuple = ("actor_user_id",)
    source_topic: str = RESERVATION_OVERRIDDEN_TOPIC
    payload_schema: dict = {
        "type": "object",
        "required": ["reservation_id", "action", "reason"],
        "properties": {
            "reservation_id": {"type": "integer"},
            "resource_id": {"type": ["integer", "null"]},
            "action": {"type": "string", "enum": ["cancelled", "changed"]},
            "owner_user_id": {"type": ["string", "null"]},
            "reason": {"type": "string"},
            "actor_user_id": {"type": ["string", "null"]},
        },
    }
    description: str = (
        "A lab manager changed or cancelled another person's reservation, and why."
    )
