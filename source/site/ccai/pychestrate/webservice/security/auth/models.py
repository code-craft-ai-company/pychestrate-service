"""
.. module:: security.auth.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for the 1-authentication feature.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class AuthProviderKind(enum.Enum):
    """
        Kind of authentication provider used to open a session.
    """
    OIDC = "OIDC"
    SAML = "SAML"
    LOCAL = "LOCAL"


class AuthSession(PychestratePhase1Base, SerializableModel):
    """
        Authoritative session state. The session_id is what the cookie
        carries; all other fields are server-owned.
    """

    __tablename__ = "auth_sessions"

    session_id = Column(UUIDType(binary=False), primary_key=True)
    user_id = Column(
        UUIDType(binary=False),
        ForeignKey("identity_users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_kind = Column(
        Enum(AuthProviderKind, name="auth_provider_kind"),
        nullable=False,
    )
    provider_name = Column(String(128), nullable=False)
    opened_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    expires_at = Column(UtcDateTime(timezone=True), nullable=False)
    last_seen_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    idle_timeout_seconds = Column(Integer, nullable=False, default=1800)
    access_token_enc = Column(LargeBinary, nullable=True)
    refresh_token_enc = Column(LargeBinary, nullable=True)
    mfa_method_name = Column(String(64), nullable=True)
    ip_fingerprint = Column(String(128), nullable=False, default="")
    user_agent_fingerprint = Column(String(128), nullable=False, default="")

    # Where the session was opened from (see AuthSessionClient); the
    # row is deleted with the session.
    client = relationship(
        "AuthSessionClient",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="select",
    )

    __table_args__ = (
        Index("ix_auth_sessions_user_expires", "user_id", "expires_at"),
        Index("ix_auth_sessions_last_seen", "last_seen_at"),
    )


class AuthSessionClient(PychestratePhase1Base, SerializableModel):
    """
        Where a session was opened from: the client's real address
        (resolved behind trusted proxies, see
        :mod:`security.auth.client_address`) and its User-Agent, which
        the admin sessions page shows. A separate table (rather than
        columns on ``auth_sessions``) so databases created by the
        development auto-create path gain it without a migration.
    """

    __tablename__ = "auth_session_clients"

    session_id = Column(
        UUIDType(binary=False),
        ForeignKey("auth_sessions.session_id", ondelete="CASCADE"),
        primary_key=True,
    )
    client_address = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)


class AuthLocalCredentials(PychestratePhase1Base, SerializableModel):
    """
        Local fallback credential hash per user. Argon2id parameters carried
        in ``algo_params`` so rotation can be done without schema changes.
    """

    __tablename__ = "auth_local_credentials"

    user_id = Column(
        UUIDType(binary=False),
        ForeignKey("identity_users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    argon2id_hash = Column(LargeBinary, nullable=False)
    algo_params = Column(JSON, nullable=False, default=dict)
    must_rotate_after = Column(UtcDateTime(timezone=True), nullable=True)
    last_changed_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)


class PasswordTokenPurpose(enum.Enum):
    """
        What a single-use password link is for.
    """
    INVITE = "INVITE"
    RESET = "RESET"


class AuthPasswordToken(PychestratePhase1Base, SerializableModel):
    """
        Single-use link that lets a user set their own password: an
        invite for a new account or a reset an administrator issued.
        Only the SHA-256 digest of the link secret is stored; the
        secret itself is shown once to the administrator who created
        it. A token is usable while ``used_at`` and ``revoked_at`` are
        empty and ``expires_at`` is in the future.
    """

    __tablename__ = "auth_password_tokens"

    token_id = Column(UUIDType(binary=False), primary_key=True)
    user_id = Column(
        UUIDType(binary=False),
        ForeignKey("identity_users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    purpose = Column(
        Enum(PasswordTokenPurpose, name="auth_password_token_purpose"),
        nullable=False,
    )
    token_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    created_by = Column(UUIDType(binary=False), nullable=True)
    expires_at = Column(UtcDateTime(timezone=True), nullable=False)
    used_at = Column(UtcDateTime(timezone=True), nullable=True)
    revoked_at = Column(UtcDateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_auth_password_tokens_user", "user_id"),
    )


class AuthSamlReplayCache(PychestratePhase1Base, SerializableModel):
    """
        Replay cache keyed on ``Response/@ID`` to block SAML replay.
    """

    __tablename__ = "auth_saml_replay_cache"

    response_id = Column(String(128), primary_key=True)
    not_on_or_after = Column(UtcDateTime(timezone=True), nullable=False)


class AuthMfaEnrollment(PychestratePhase1Base, SerializableModel):
    """
        Enrollment row per (user, method). ``secret_ref`` points into
        ``1-secrets-vault`` for the method-specific material.
    """

    __tablename__ = "auth_mfa_enrollments"

    enrollment_id = Column(UUIDType(binary=False), primary_key=True)
    user_id = Column(
        UUIDType(binary=False),
        ForeignKey("identity_users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    method_name = Column(String(64), nullable=False)
    secret_ref = Column(String(256), nullable=False)
    verified_at = Column(UtcDateTime(timezone=True), nullable=True)
    last_used_at = Column(UtcDateTime(timezone=True), nullable=True)


class AuthOidcState(PychestratePhase1Base, SerializableModel):
    """
        One-shot state/nonce/PKCE row for an OIDC authorization code flow.
    """

    __tablename__ = "auth_oidc_state"

    state = Column(String(128), primary_key=True)
    nonce = Column(String(128), nullable=False)
    pkce_verifier_enc = Column(LargeBinary, nullable=False)
    provider_name = Column(String(128), nullable=False)
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    expires_at = Column(UtcDateTime(timezone=True), nullable=False)
    redirect_target = Column(String(1024), nullable=False, default="")
