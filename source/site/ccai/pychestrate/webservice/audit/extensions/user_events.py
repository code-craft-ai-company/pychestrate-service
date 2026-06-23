"""
.. module:: audit.extensions.user_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Audit kinds produced from 1-user-management entity topics.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension


class UserLifecycleAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.user.created``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.user.created"
    source_topic: str = "entity.user.created"
    payload_schema: dict = {
        "type": "object",
        "required": ["user_id", "login_name", "provisioning_source"],
        "properties": {
            "user_id": {"type": "string"},
            "login_name": {"type": "string"},
            "provisioning_source": {"type": "string"},
            "actor_user_id": {"type": ["string", "null"]},
            "created_at": {"type": "string"},
        },
    }
    description: str = "A new identity user record was created."
