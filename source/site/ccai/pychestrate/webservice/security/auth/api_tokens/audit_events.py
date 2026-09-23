"""
.. module:: security.auth.api_tokens.audit_events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Audit kinds for API-token creation, revocation, and use.

.. moduleauthor:: Code Craft AI LLC

Registered by :func:`security.auth.api_tokens.register_builtin_extensions`
so the audit bus subscriber captures every
:class:`ApiTokenEventTopics` event into the audit store. The creation
of a service account needs no kind of its own: it publishes the
ordinary ``entity.user.created`` event (``audit.user.created``) with
``provisioning_source = "service_account"``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension
from ccai.pychestrate.webservice.security.auth.api_tokens.events import ApiTokenEventTopics


class ApiTokenCreatedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.api_token.created``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.api_token.created"
    source_topic: str = ApiTokenEventTopics.TOKEN_CREATED
    payload_schema: dict = {
        "type": "object",
        "required": ["token_id", "user_id", "name", "scope", "expires_at"],
        "properties": {
            "token_id": {"type": "string"},
            "user_id": {"type": "string"},
            "login_name": {"type": ["string", "null"]},
            "is_service_account": {"type": "boolean"},
            "name": {"type": "string"},
            "scope": {"type": "string"},
            "expires_at": {"type": "string"},
            "created_at": {"type": "string"},
            "actor_user_id": {"type": ["string", "null"]},
            "target_ref": {"type": "string"},
        },
    }
    description: str = "An API token was issued (the secret is never recorded)."


class ApiTokenRevokedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.api_token.revoked``.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.api_token.revoked"
    source_topic: str = ApiTokenEventTopics.TOKEN_REVOKED
    payload_schema: dict = {
        "type": "object",
        "required": ["token_id", "user_id", "revoked_at"],
        "properties": {
            "token_id": {"type": "string"},
            "user_id": {"type": "string"},
            "login_name": {"type": ["string", "null"]},
            "name": {"type": "string"},
            "revoked_at": {"type": "string"},
            "actor_user_id": {"type": ["string", "null"]},
            "target_ref": {"type": "string"},
        },
    }
    description: str = "An API token was revoked."


class ApiTokenUsedAuditEvents(AuditEventTypeExtension):
    """
        Canonical audit kind for ``entity.api_token.used``: a token's
        first use, then at most one record per token per hour.
    """

    resource_extension_name: str = "audit_event_type"
    kind: str = "audit.api_token.used"
    source_topic: str = ApiTokenEventTopics.TOKEN_USED
    payload_schema: dict = {
        "type": "object",
        "required": ["token_id", "user_id", "method", "path", "used_at"],
        "properties": {
            "token_id": {"type": "string"},
            "user_id": {"type": "string"},
            "login_name": {"type": ["string", "null"]},
            "name": {"type": "string"},
            "method": {"type": "string"},
            "path": {"type": "string"},
            "used_at": {"type": "string"},
            "actor_user_id": {"type": ["string", "null"]},
            "target_ref": {"type": "string"},
        },
    }
    description: str = "An API token authenticated a request."


API_TOKEN_AUDIT_EVENT_TYPES = (
    ApiTokenCreatedAuditEvents,
    ApiTokenRevokedAuditEvents,
    ApiTokenUsedAuditEvents,
)


__all__ = [
    "API_TOKEN_AUDIT_EVENT_TYPES",
    "ApiTokenCreatedAuditEvents",
    "ApiTokenRevokedAuditEvents",
    "ApiTokenUsedAuditEvents",
]
