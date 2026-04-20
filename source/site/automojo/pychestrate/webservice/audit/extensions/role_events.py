"""
.. module:: audit.extensions.role_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Audit kinds produced from 1-rbac entity topics.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension


class RoleBindingAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.role.assigned``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.role.assigned"
    source_topic: str = "entity.role.assigned"
    payload_schema: dict = {
        "type": "object",
        "required": ["binding_id", "role_name", "principal_kind", "principal_id"],
        "properties": {
            "binding_id": {"type": "string"},
            "role_name": {"type": "string"},
            "principal_kind": {"type": "string"},
            "principal_id": {"type": "string"},
            "scope_kind": {"type": "string"},
            "scope_id": {"type": ["string", "null"]},
            "actor_user_id": {"type": ["string", "null"]},
            "created_at": {"type": "string"},
        },
    }
    description: str = "A role binding was assigned to a principal."
