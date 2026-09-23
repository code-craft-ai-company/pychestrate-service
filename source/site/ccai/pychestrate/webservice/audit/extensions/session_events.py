"""
.. module:: audit.extensions.session_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Audit kinds for sign-ins, sign-outs, terminated sessions,
               and rejected sign-in attempts (1-authentication topics).

.. moduleauthor:: Code Craft AI LLC

``session_service`` publishes ``entity.session.opened`` for every
sign-in and ``entity.session.closed`` for every sign-out, termination,
or forced close; nothing recorded them, so the audit log had no
sign-ins at all. A sign-in's actor is the user who signed in; a close
names an ``actor_user_id`` when someone other than the session's owner
ended it (an administrator terminating a session, a deactivation), and
falls back to the owner for an ordinary sign-out.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension


class SessionOpenedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.session.opened`` (a sign-in).
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.session.opened"
    source_topic: str = "entity.session.opened"
    actor_payload_keys: tuple = ("actor_user_id", "user_id")
    payload_schema: dict = {
        "type": "object",
        "required": ["session_id", "user_id"],
        "properties": {
            "session_id": {"type": "string"},
            "user_id": {"type": "string"},
            "provider_kind": {"type": "string"},
            "provider_name": {"type": "string"},
            "client_address": {"type": ["string", "null"]},
            "user_agent": {"type": ["string", "null"]},
            "opened_at": {"type": "string"},
        },
    }
    description: str = "A user signed in."


class SessionClosedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.session.closed`` (sign-out, termination,
        or a forced close such as deactivation).
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.session.closed"
    source_topic: str = "entity.session.closed"
    actor_payload_keys: tuple = ("actor_user_id", "user_id")
    payload_schema: dict = {
        "type": "object",
        "required": ["session_id", "user_id", "reason"],
        "properties": {
            "session_id": {"type": "string"},
            "user_id": {"type": "string"},
            "reason": {"type": "string"},
            "actor_user_id": {"type": ["string", "null"]},
            "closed_at": {"type": "string"},
        },
    }
    description: str = "A session ended (sign-out or termination)."


class LoginRejectedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.auth.login.rejected`` (a failed sign-in
        attempt). The claimed login name is recorded as typed; there is
        no actor.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.auth.login_rejected"
    source_topic: str = "entity.auth.login.rejected"
    actor_payload_keys: tuple = ()
    payload_schema: dict = {
        "type": "object",
        "required": ["login_name", "reason"],
        "properties": {
            "login_name": {"type": "string"},
            "reason": {"type": "string"},
            "client_address": {"type": ["string", "null"]},
            "rejected_at": {"type": "string"},
        },
    }
    description: str = "A sign-in attempt was rejected."


SESSION_AUDIT_EVENT_TYPES = (
    SessionOpenedAuditEvents,
    SessionClosedAuditEvents,
    LoginRejectedAuditEvents,
)
