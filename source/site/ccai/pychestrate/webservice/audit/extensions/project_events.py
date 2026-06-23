"""
.. module:: audit.extensions.project_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Audit kinds produced from 2-projects entity topics.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension


_PROJECT_LIFECYCLE_SCHEMA = {
    "type": "object",
    "required": ["project_id", "slug"],
    "properties": {
        "project_id": {"type": "string"},
        "slug": {"type": "string"},
        "state": {"type": ["string", "null"]},
        "actor_user_id": {"type": ["string", "null"]},
    },
}

_PROJECT_MEMBER_SCHEMA = {
    "type": "object",
    "required": ["project_id", "slug", "user_id", "role_name"],
    "properties": {
        "project_id": {"type": "string"},
        "slug": {"type": "string"},
        "user_id": {"type": "string"},
        "role_name": {"type": "string"},
        "actor_user_id": {"type": ["string", "null"]},
    },
}


class ProjectCreatedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.project.created``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.project.created"
    source_topic: str = "entity.project.created"
    payload_schema: dict = {
        "type": "object",
        "required": ["project_id", "slug"],
        "properties": {
            "project_id": {"type": "string"},
            "slug": {"type": "string"},
            "display_name": {"type": "string"},
            "owning_group_id": {"type": ["string", "null"]},
            "template_id": {"type": ["string", "null"]},
            "template_version": {"type": ["string", "null"]},
            "actor_user_id": {"type": ["string", "null"]},
            "created_at": {"type": "string"},
        },
    }
    description: str = "A new project aggregate was created."


class ProjectArchivedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.project.archived``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.project.archived"
    source_topic: str = "entity.project.archived"
    payload_schema: dict = _PROJECT_LIFECYCLE_SCHEMA
    description: str = "A project was moved into ARCHIVED state."


class ProjectUnarchivedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.project.unarchived``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.project.unarchived"
    source_topic: str = "entity.project.unarchived"
    payload_schema: dict = _PROJECT_LIFECYCLE_SCHEMA
    description: str = "A project was moved back to ACTIVE."


class ProjectDeletedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.project.deleted``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.project.deleted"
    source_topic: str = "entity.project.deleted"
    payload_schema: dict = _PROJECT_LIFECYCLE_SCHEMA
    description: str = "A project aggregate was hard-deleted."


class ProjectMemberAddedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.project.member_added``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.project.member_added"
    source_topic: str = "entity.project.member_added"
    payload_schema: dict = _PROJECT_MEMBER_SCHEMA
    description: str = "A user was attached to a project with a role."


class ProjectMemberRemovedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.project.member_removed``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.project.member_removed"
    source_topic: str = "entity.project.member_removed"
    payload_schema: dict = _PROJECT_MEMBER_SCHEMA
    description: str = "A user binding was removed from a project."
