"""
.. module:: audit.extensions.ui_profile_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Audit kind for 9-ui-profiles deployment changes.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension


class UiProfileDeploymentChangedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.ui_profile.deployment_changed``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.ui_profile.deployment_changed"
    source_topic: str = "entity.ui_profile.deployment_changed"
    payload_schema: dict = {
        "type": "object",
        "required": ["surfaces"],
        "properties": {
            "surfaces": {"type": "array", "items": {"type": "string"}},
            "actor_id": {"type": ["string", "null"]},
        },
    }
    description: str = "The deployment-wide UI profile (visible automation surfaces) changed."
