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


class SecretRotatedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.secret.rotated`` writes.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.secret.rotated"
    source_topic: str = "entity.secret.rotated"
    payload_schema: dict = {
        "type": "object",
        "required": ["secret_ref", "version_id", "version_number"],
        "properties": {
            "secret_ref": {"type": "string"},
            "backend_name": {"type": "string"},
            "version_id": {"type": "string"},
            "version_number": {"type": "integer"},
            "principal_id": {"type": ["string", "null"]},
            "rotated_at": {"type": "string"},
            "grace_seconds": {"type": "integer"},
        },
    }
    description: str = "A secret was rotated to a new version."


