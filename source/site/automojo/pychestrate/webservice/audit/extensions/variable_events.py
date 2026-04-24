"""
.. module:: audit.extensions.variable_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Audit kinds produced from 2-global-variables entity topics.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension


_VARIABLE_PAYLOAD_SCHEMA = {
    "type": "object",
    "required": ["scope", "name"],
    "properties": {
        "binding_id": {"type": ["string", "null"]},
        "scope": {"type": "string"},
        "scope_id": {"type": "string"},
        "name": {"type": "string"},
        "value_type": {"type": ["string", "null"]},
        "actor_user_id": {"type": ["string", "null"]},
        "set_at": {"type": ["string", "null"]},
    },
}


class VariableSetAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.variable.set``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.variable.set"
    source_topic: str = "entity.variable.set"
    payload_schema: dict = _VARIABLE_PAYLOAD_SCHEMA
    description: str = "A variable binding was created or replaced."


class VariableUnsetAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.variable.unset``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.variable.unset"
    source_topic: str = "entity.variable.unset"
    payload_schema: dict = _VARIABLE_PAYLOAD_SCHEMA
    description: str = "A variable binding was removed."
