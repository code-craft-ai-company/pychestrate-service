"""
.. module:: security.auth.api_tokens.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy model for API tokens (personal access tokens
               and service-account tokens).

.. moduleauthor:: Code Craft AI LLC

One row per issued token. The token secret itself is never stored:
``token_sha256`` holds the SHA-256 digest of the full token string,
which is enough to look a presented token up and compare it. The
secret carries 256 bits of randomness, so a fast digest is the
right tool here (a slow password hash buys nothing for a value that
cannot be guessed).

A token always acts as exactly one identity user (``user_id``): the
person who owns a personal access token, or the service account a
machine token was minted for. Authorization is that user's RBAC --
the token carries no permissions of its own, so it can never grant
more than its principal holds.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class AuthApiToken(PychestratePhase1Base, SerializableModel):
    """
        An API token that authenticates machine callers (the ``pyc``
        CLI, CI jobs, MCP agents) as ``Authorization: Bearer <token>``.

        :ivar token_id: Server-generated id; safe to show and log.
        :ivar user_id: The identity user the token acts as.
        :ivar name: Operator-chosen label ("laptop CLI", "nightly CI").
        :ivar token_sha256: Hex SHA-256 digest of the full token.
        :ivar token_hint: Non-secret leading characters of the token so
                          a user can tell their tokens apart.
        :ivar scope: ``read-write`` or ``read-only``.
        :ivar created_at: When the token was issued.
        :ivar created_by_user_id: Who issued it (the owner for personal
                                  tokens, an administrator for
                                  service-account tokens).
        :ivar expires_at: Hard expiry; every token expires.
        :ivar last_used_at: Last successful authentication (updated at
                            most once a minute).
        :ivar revoked_at: When the token was revoked, or ``None``.
        :ivar revoked_by_user_id: Who revoked it.
    """

    __tablename__ = "auth_api_tokens"

    token_id = Column(UUIDType(binary=False), primary_key=True)
    user_id = Column(
        UUIDType(binary=False),
        ForeignKey("identity_users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(128), nullable=False)
    token_sha256 = Column(String(64), nullable=False, unique=True)
    token_hint = Column(String(16), nullable=False)
    scope = Column(String(16), nullable=False, default="read-write")
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    created_by_user_id = Column(
        UUIDType(binary=False),
        ForeignKey("identity_users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at = Column(UtcDateTime(timezone=True), nullable=False)
    last_used_at = Column(UtcDateTime(timezone=True), nullable=True)
    revoked_at = Column(UtcDateTime(timezone=True), nullable=True)
    revoked_by_user_id = Column(
        UUIDType(binary=False),
        ForeignKey("identity_users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_auth_api_tokens_user_id", "user_id"),
    )


__all__ = [
    "AuthApiToken",
]
