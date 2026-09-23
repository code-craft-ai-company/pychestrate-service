"""
.. module:: audit.extensions.role_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Audit kinds produced from 1-rbac entity topics.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension


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


class RoleRevokedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.role.revoked`` (a binding was removed).
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.role.revoked"
    source_topic: str = "entity.role.revoked"
    payload_schema: dict = {
        "type": "object",
        "required": ["role_name", "principal_kind", "principal_id"],
        "properties": {
            "binding_id": {"type": ["string", "null"]},
            "role_name": {"type": "string"},
            "principal_kind": {"type": "string"},
            "principal_id": {"type": "string"},
            "scope_kind": {"type": "string"},
            "scope_id": {"type": ["string", "null"]},
            "actor_user_id": {"type": ["string", "null"]},
            "revoked_at": {"type": "string"},
        },
    }
    description: str = "A role binding was removed from a principal."


_ROLE_DEFINITION_SCHEMA = {
    "type": "object",
    "required": ["role_id", "role_name"],
    "properties": {
        "role_id": {"type": "string"},
        "role_name": {"type": "string"},
        "permission_keys": {"type": "array", "items": {"type": "string"}},
        "removed_binding_count": {"type": "integer"},
        "actor_user_id": {"type": ["string", "null"]},
        "client_address": {"type": ["string", "null"]},
    },
}


class RoleCreatedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.role.created`` (a custom role).
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.role.created"
    source_topic: str = "entity.role.created"
    payload_schema: dict = _ROLE_DEFINITION_SCHEMA
    description: str = "A custom role was created."


class RoleUpdatedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.role.updated`` (a custom role's grants).
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.role.updated"
    source_topic: str = "entity.role.updated"
    payload_schema: dict = _ROLE_DEFINITION_SCHEMA
    description: str = "A custom role's description or permissions changed."


class RoleDeletedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.role.deleted`` (a custom role).
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.role.deleted"
    source_topic: str = "entity.role.deleted"
    payload_schema: dict = _ROLE_DEFINITION_SCHEMA
    description: str = "A custom role was deleted with its bindings."


ROLE_AUDIT_EVENT_TYPES = (
    RoleBindingAuditEvents,
    RoleRevokedAuditEvents,
    RoleCreatedAuditEvents,
    RoleUpdatedAuditEvents,
    RoleDeletedAuditEvents,
)
