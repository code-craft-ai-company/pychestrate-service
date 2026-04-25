"""
.. module:: audit.extensions.unknown_events
    :synopsis: Audit kind for the audit.unknown fallback path.

The fallback kind exists so the chain hash never breaks when
a new feature emits a topic before its dedicated
``AuditEventTypeExtension`` registers. The payload carries the
original kind / source_topic + the offending event payload.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.audit.extensions.event_type import (
    AuditEventTypeExtension,
)


class UnknownAuditKindAuditEvents(AuditEventTypeExtension):
    """
        Catch-all audit kind. Always present in the catalog so
        the writer's fallback path has a registered target.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.unknown"
    source_topic: str = ""
    payload_schema: dict = {
        "type": "object",
        "properties": {
            "unknown_original_kind": {"type": "string"},
            "unknown_source_topic": {"type": "string"},
        },
    }
    description: str = (
        "Catch-all kind used when the writer sees a topic with "
        "no registered AuditEventTypeExtension."
    )
