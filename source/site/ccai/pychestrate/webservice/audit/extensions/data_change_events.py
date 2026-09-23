"""
.. module:: audit.extensions.data_change_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Audit kinds for row changes the data-change bridge
               records on the web UI's own stores.

.. moduleauthor:: Code Craft AI LLC

The web UI's projects, resources, variables and legacy secrets pages
write the ``core.orm`` tables through the legacy managers, which were
never given an audit logger, so none of those actions reached the audit
log. :mod:`audit.data_change_bridge` turns each row a signed-in user's
request inserts, updates or deletes into one of these events (see that
module for which tables and fields are covered).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension


_DATA_CHANGE_SCHEMA = {
    "type": "object",
    "required": ["table", "entity", "entity_id"],
    "properties": {
        "table": {"type": "string"},
        "entity": {"type": "string"},
        "entity_id": {"type": "string"},
        "label": {"type": ["string", "null"]},
        "changed_fields": {"type": "array", "items": {"type": "string"}},
        "changes": {"type": "object"},
        "actor_user_id": {"type": ["string", "null"]},
        "client_address": {"type": ["string", "null"]},
    },
}


class DataCreatedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.data.created``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.data.created"
    source_topic: str = "entity.data.created"
    payload_schema: dict = _DATA_CHANGE_SCHEMA
    description: str = "A record was created."


class DataUpdatedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.data.updated``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.data.updated"
    source_topic: str = "entity.data.updated"
    payload_schema: dict = _DATA_CHANGE_SCHEMA
    description: str = "A record was changed."


class DataDeletedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.data.deleted``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.data.deleted"
    source_topic: str = "entity.data.deleted"
    payload_schema: dict = _DATA_CHANGE_SCHEMA
    description: str = "A record was deleted."


DATA_CHANGE_AUDIT_EVENT_TYPES = (
    DataCreatedAuditEvents,
    DataUpdatedAuditEvents,
    DataDeletedAuditEvents,
)
