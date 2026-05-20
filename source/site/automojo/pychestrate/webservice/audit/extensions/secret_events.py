"""
.. module:: audit.extensions.secret_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Audit kinds produced from 1-secrets-vault entity topics.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension


class SecretAccessedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.secret.accessed`` reads.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.secret.accessed"
    source_topic: str = "entity.secret.accessed"
    payload_schema: dict = {
        "type": "object",
        "required": ["secret_ref", "backend_name", "principal_id"],
        "properties": {
            "secret_ref": {"type": "string"},
            "backend_name": {"type": "string"},
            "version_id": {"type": ["string", "null"]},
            "principal_id": {"type": "string"},
            "accessed_at": {"type": "string"},
        },
    }
    description: str = "A secret was read by a principal."


class SecretCreatedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.secret.created`` writes.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.secret.created"
    source_topic: str = "entity.secret.created"
    payload_schema: dict = {
        "type": "object",
        "required": ["secret_ref", "backend_name", "version_id"],
        "properties": {
            "secret_ref": {"type": "string"},
            "backend_name": {"type": "string"},
            "version_id": {"type": "string"},
            "principal_id": {"type": ["string", "null"]},
            "created_at": {"type": "string"},
        },
    }
    description: str = "A secret was created."


class SecretUpdatedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.secret.rotated`` updates.

        Introduced by PR p20g for the scope-aware ``PUT`` (rotate /
        update value) REST operation.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.secret.updated"
    source_topic: str = "entity.secret.rotated"
    payload_schema: dict = {
        "type": "object",
        "required": ["secret_ref", "backend_name", "version_id"],
        "properties": {
            "secret_ref": {"type": "string"},
            "backend_name": {"type": "string"},
            "version_id": {"type": "string"},
            "principal_id": {"type": ["string", "null"]},
            "updated_at": {"type": "string"},
        },
    }
    description: str = "A secret value was updated / rotated."


class SecretDeletedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.secret.force_expired`` deletes.

        Introduced by PR p20g for the scope-aware ``DELETE`` REST
        operation.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.secret.deleted"
    source_topic: str = "entity.secret.force_expired"
    payload_schema: dict = {
        "type": "object",
        "required": ["secret_ref"],
        "properties": {
            "secret_ref": {"type": "string"},
            "backend_name": {"type": ["string", "null"]},
            "principal_id": {"type": ["string", "null"]},
            "deleted_at": {"type": "string"},
        },
    }
    description: str = "A secret was deleted."


