"""
.. module:: audit.extensions.session_events
    :synopsis: Audit kinds produced from 1-authentication entity topics.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.audit.extensions.event_type import (
    AuditEventTypeExtension,
)


class SessionOpenedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.session.opened``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.session.opened"
    source_topic: str = "entity.session.opened"
    payload_schema: dict = {
        "type": "object",
        "required": ["session_id", "user_id"],
        "properties": {
            "session_id": {"type": "string"},
            "user_id": {"type": "string"},
            "provider_kind": {"type": "string"},
            "provider_name": {"type": "string"},
            "mfa_method_name": {"type": ["string", "null"]},
            "opened_at": {"type": "string"},
        },
    }
    description: str = "An authenticated session was opened."


class SessionClosedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.session.closed``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.session.closed"
    source_topic: str = "entity.session.closed"
    payload_schema: dict = {
        "type": "object",
        "required": ["session_id", "user_id"],
        "properties": {
            "session_id": {"type": "string"},
            "user_id": {"type": "string"},
            "reason": {"type": "string"},
            "closed_at": {"type": "string"},
        },
    }
    description: str = "An authenticated session was closed."


class SessionsRevokedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.session.revoked`` (bulk) — issued by
        the M2 revoke_sessions_for_user path.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.session.revoked"
    source_topic: str = "entity.session.revoked"
    payload_schema: dict = {
        "type": "object",
        "required": ["user_id", "count"],
        "properties": {
            "user_id": {"type": "string"},
            "count": {"type": "integer"},
            "session_ids": {"type": "array"},
            "reason": {"type": "string"},
            "revoked_at": {"type": "string"},
        },
    }
    description: str = "Every active session for a user was revoked."


class LoginRejectedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.auth.login.rejected``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.auth.login.rejected"
    source_topic: str = "entity.auth.login.rejected"
    payload_schema: dict = {
        "type": "object",
        "properties": {
            "provider_kind": {"type": "string"},
            "provider_name": {"type": "string"},
            "reason": {"type": "string"},
            "remote_ip_hash": {"type": "string"},
            "attempted_login_name_hash": {"type": "string"},
            "at": {"type": "string"},
        },
    }
    description: str = "A login attempt was rejected."


class MfaEnrollmentAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.mfa.enrollment.created``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.mfa.enrollment.created"
    source_topic: str = "entity.mfa.enrollment.created"
    payload_schema: dict = {
        "type": "object",
        "required": ["user_id", "method_name"],
        "properties": {
            "user_id": {"type": "string"},
            "method_name": {"type": "string"},
            "enrollment_id": {"type": "string"},
            "actor_user_id": {"type": ["string", "null"]},
        },
    }
    description: str = "An MFA enrollment was created."


class MfaChallengeVerifiedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.mfa.challenge.verified``.
    """
    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.mfa.challenge.verified"
    source_topic: str = "entity.mfa.challenge.verified"
    payload_schema: dict = {
        "type": "object",
        "required": ["user_id", "method_name"],
        "properties": {
            "user_id": {"type": "string"},
            "method_name": {"type": "string"},
            "challenge_id": {"type": "string"},
            "verified_at": {"type": "string"},
        },
    }
    description: str = "An MFA challenge was successfully verified."
