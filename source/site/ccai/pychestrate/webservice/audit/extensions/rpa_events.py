"""
.. module:: audit.extensions.rpa_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Audit kinds produced from 6-rpa-orchestration entity topics.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension


class RpaJobTypeRegisteredAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.rpa.job_type_registered``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.rpa.job_type_registered"
    source_topic: str = "entity.rpa.job_type_registered"
    payload_schema: dict = {
        "type": "object",
        "required": ["type_id", "execution_mode"],
        "properties": {
            "type_id": {"type": "string"},
            "execution_mode": {"type": "string"},
            "actor_id": {"type": ["string", "null"]},
        },
    }
    description: str = "An RPA job type was registered."


class RpaJobTypePublishedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.rpa.job_type_published``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.rpa.job_type_published"
    source_topic: str = "entity.rpa.job_type_published"
    payload_schema: dict = {
        "type": "object",
        "required": ["type_id", "version"],
        "properties": {
            "type_id": {"type": "string"},
            "version": {"type": "string"},
            "actor_id": {"type": ["string", "null"]},
        },
    }
    description: str = "A version of an RPA job type was published."


class RpaJobTypeRetiredAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.rpa.job_type_retired``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.rpa.job_type_retired"
    source_topic: str = "entity.rpa.job_type_retired"
    payload_schema: dict = {
        "type": "object",
        "required": ["type_id"],
        "properties": {
            "type_id": {"type": "string"},
            "actor_id": {"type": ["string", "null"]},
        },
    }
    description: str = "An RPA job type was retired."


class RpaJobStartedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.rpa.job_started`` (a trigger).
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.rpa.job_started"
    source_topic: str = "entity.rpa.job_started"
    payload_schema: dict = {
        "type": "object",
        "required": ["job_id", "project_id", "type_id", "version"],
        "properties": {
            "job_id": {"type": "string"},
            "project_id": {"type": "string"},
            "spec_id": {"type": ["string", "null"]},
            "type_id": {"type": "string"},
            "version": {"type": "string"},
            "execution_mode": {"type": "string"},
            "trigger_cause": {"type": "object"},
        },
    }
    description: str = "An RPA job was triggered."


class RpaJobCompletedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.rpa.job_completed``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.rpa.job_completed"
    source_topic: str = "entity.rpa.job_completed"
    payload_schema: dict = {
        "type": "object",
        "required": ["job_id", "final_status"],
        "properties": {
            "job_id": {"type": "string"},
            "project_id": {"type": "string"},
            "final_status": {"type": "string"},
            "exit_code": {"type": ["integer", "null"]},
            "result_root_key": {"type": ["string", "null"]},
        },
    }
    description: str = "An RPA job reached a successful terminal state."


class RpaJobFailedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.rpa.job_failed``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.rpa.job_failed"
    source_topic: str = "entity.rpa.job_failed"
    payload_schema: dict = {
        "type": "object",
        "required": ["job_id"],
        "properties": {
            "job_id": {"type": "string"},
            "project_id": {"type": "string"},
            "final_status": {"type": "string"},
            "status": {"type": "string"},
            "reason": {"type": ["string", "null"]},
        },
    }
    description: str = "An RPA job failed or timed out."


class RpaJobCancelledAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.rpa.job_cancelled``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.rpa.job_cancelled"
    source_topic: str = "entity.rpa.job_cancelled"
    payload_schema: dict = {
        "type": "object",
        "required": ["job_id"],
        "properties": {
            "job_id": {"type": "string"},
            "project_id": {"type": "string"},
            "reason": {"type": ["string", "null"]},
        },
    }
    description: str = "An RPA job was cancelled."


class RpaSpecChangedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.rpa.spec_updated``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.rpa.spec_updated"
    source_topic: str = "entity.rpa.spec_updated"
    payload_schema: dict = {
        "type": "object",
        "required": ["spec_id", "project_id"],
        "properties": {
            "spec_id": {"type": "string"},
            "project_id": {"type": "string"},
            "revision": {"type": "integer"},
            "actor_id": {"type": ["string", "null"]},
        },
    }
    description: str = "An RPA specification was edited."


RPA_AUDIT_EVENT_TYPES = (
    RpaJobTypeRegisteredAuditEvents,
    RpaJobTypePublishedAuditEvents,
    RpaJobTypeRetiredAuditEvents,
    RpaJobStartedAuditEvents,
    RpaJobCompletedAuditEvents,
    RpaJobFailedAuditEvents,
    RpaJobCancelledAuditEvents,
    RpaSpecChangedAuditEvents,
)
