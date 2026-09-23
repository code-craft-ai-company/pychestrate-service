"""
.. module:: audit.extensions.user_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Audit kinds produced from 1-user-management entity topics.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension


class UserLifecycleAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.user.created``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.user.created"
    source_topic: str = "entity.user.created"
    payload_schema: dict = {
        "type": "object",
        "required": ["user_id", "login_name", "provisioning_source"],
        "properties": {
            "user_id": {"type": "string"},
            "login_name": {"type": "string"},
            "provisioning_source": {"type": "string"},
            "actor_user_id": {"type": ["string", "null"]},
            "created_at": {"type": "string"},
        },
    }
    description: str = "A new identity user record was created."


_USER_CHANGE_SCHEMA = {
    "type": "object",
    "required": ["user_id", "login_name"],
    "properties": {
        "user_id": {"type": "string"},
        "login_name": {"type": "string"},
        "changed_fields": {"type": "array", "items": {"type": "string"}},
        "actor_user_id": {"type": ["string", "null"]},
        "client_address": {"type": ["string", "null"]},
    },
}


class UserUpdatedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.user.updated`` (profile fields changed).
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.user.updated"
    source_topic: str = "entity.user.updated"
    payload_schema: dict = _USER_CHANGE_SCHEMA
    description: str = "A user's profile was changed."


class UserDeactivatedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.user.deactivated``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.user.deactivated"
    source_topic: str = "entity.user.deactivated"
    payload_schema: dict = _USER_CHANGE_SCHEMA
    description: str = "A user was deactivated and signed out everywhere."


class UserReactivatedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.user.reactivated``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.user.reactivated"
    source_topic: str = "entity.user.reactivated"
    payload_schema: dict = _USER_CHANGE_SCHEMA
    description: str = "A deactivated user was reactivated."


_PASSWORD_EVENT_SCHEMA = {
    "type": "object",
    "required": ["user_id", "login_name"],
    "properties": {
        "user_id": {"type": "string"},
        "login_name": {"type": "string"},
        "purpose": {"type": "string"},
        "expires_at": {"type": "string"},
        "must_change": {"type": "boolean"},
        "forced": {"type": "boolean"},
        "actor_user_id": {"type": ["string", "null"]},
        "client_address": {"type": ["string", "null"]},
    },
}


class UserPasswordChangedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.user.password_changed`` (a user changed
        their own password).
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.user.password_changed"
    source_topic: str = "entity.user.password_changed"
    payload_schema: dict = _PASSWORD_EVENT_SCHEMA
    description: str = "A user changed their own password."


class UserPasswordResetAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.user.password_reset`` (an administrator
        set a user's password).
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.user.password_reset"
    source_topic: str = "entity.user.password_reset"
    payload_schema: dict = _PASSWORD_EVENT_SCHEMA
    description: str = "An administrator set a user's password."


class UserPasswordLinkIssuedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.user.password_link_issued`` (an invite
        or reset link was created).
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.user.password_link_issued"
    source_topic: str = "entity.user.password_link_issued"
    payload_schema: dict = _PASSWORD_EVENT_SCHEMA
    description: str = "An invite or password-reset link was created."


class UserPasswordLinkRedeemedAuditEvents(AuditEventTypeExtension):
    """
        Audit kind for ``entity.user.password_link_redeemed`` (a user
        set their password from a link).
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.user.password_link_redeemed"
    source_topic: str = "entity.user.password_link_redeemed"
    payload_schema: dict = _PASSWORD_EVENT_SCHEMA
    description: str = "A user set their password from an invite or reset link."


USER_AUDIT_EVENT_TYPES = (
    UserLifecycleAuditEvents,
    UserUpdatedAuditEvents,
    UserDeactivatedAuditEvents,
    UserReactivatedAuditEvents,
    UserPasswordChangedAuditEvents,
    UserPasswordResetAuditEvents,
    UserPasswordLinkIssuedAuditEvents,
    UserPasswordLinkRedeemedAuditEvents,
)
