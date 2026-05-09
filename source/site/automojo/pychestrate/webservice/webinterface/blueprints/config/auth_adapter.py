"""
.. module:: webinterface.blueprints.config.auth_adapter
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Drop-in replacement for the legacy ``SecurityManager``
               backed by the modern ``security.auth.local_flow`` +
               ``session_service`` stack.

.. moduleauthor:: Automation Mojo LLC

The consumer-UI port (PRs F1..F5) preserved 1:1 the legacy
flask-era handler shape that built a ``SecurityManager`` from
``automojo.pychestrate.core.managers.security_manager`` and
called ``authenticate(AuthRequest)`` /
``validate_token(token)`` / ``logout(token)`` /
``check_permission(user_id, permission)`` on it. That stack
queries the legacy ``user`` / ``password_history`` /
``sessions`` tables on
:class:`PychestrateModelBase`; see
``userguide/12-00-consumer-ui-auth-stack.rst`` for the full
context.

This adapter exposes the same four-method interface but
wires each method to the modern Phase-1+ stack:

* :meth:`authenticate` -> :func:`local_flow.verify_local_credentials`
  + :func:`session_service.open_session` against
  ``identity_users`` + ``auth_local_credentials`` +
  ``auth_sessions``.
* :meth:`validate_token` ->
  :func:`session_service.resolve_session`.
* :meth:`logout` -> :func:`session_service.close_session`.
* :meth:`check_permission` -> :func:`rbac_evaluator.check_permission`
  against the modern ``rbac_*`` tables on
  :class:`PychestratePhase1Base`. The legacy
  ``user.roles`` -> ``system_roles`` -> ``permissions``
  chain is no longer consulted; consumer-UI permission
  strings are now canonical ``system:<action>`` keys
  matched against the catalog produced by the in-tree
  ``CorePermissionExtension`` / ``SystemAdminRole`` packs.

The adapter holds the same shape as the legacy
:class:`SecurityManager` so :func:`_build_security_manager` is
a drop-in swap and consumer-UI handlers don't change.

CSRF token handling
-------------------

The legacy ``SecurityManager`` stored a per-session CSRF token
on the ``sessions`` row alongside the session token. The
modern :class:`AuthSession` does not carry a CSRF column;
CSRF lives entirely on the cookie session payload (the same
``csrf.SESSION_KEY`` slot the consumer UI's ``csrf`` module
manages).

The adapter therefore generates a fresh CSRF token at
:meth:`authenticate` time and returns it on the
:class:`AuthResponse`. The handler stores it on the cookie.
:meth:`validate_token` does NOT return a CSRF token (the
shimmed value is empty); the caller is expected to read the
CSRF from its cookie session, not from a server-of-record
re-fetch.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import secrets

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from automojo.pychestrate.webservice.security.auth import (
    local_flow,
)
from automojo.pychestrate.webservice.security.auth.exceptions import (
    AuthenticationError as ModernAuthenticationError,
    SessionExpiredError,
    SessionNotFoundError,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthLocalCredentials,
    AuthProviderKind,
    AuthSession,
)
from automojo.pychestrate.webservice.security.auth.session_service import (
    RequestFingerprint,
    close_session,
    open_session,
    resolve_session,
)
from automojo.pychestrate.webservice.identity.users.models import (
    IdentityUser,
)


# ---------------------------------------------------------------------------
# Shimmed dataclasses (same names + shapes the legacy SecurityManager used)
# ---------------------------------------------------------------------------


_DEFAULT_SESSION_IDLE_TIMEOUT_SECONDS: int = 30 * 60
_DEFAULT_SESSION_MAX_LIFETIME_SECONDS: int = 24 * 60 * 60


@dataclass
class AuthRequest:
    """
        Login form payload. Same shape as the legacy
        :class:`automojo.pychestrate.core.managers.security_manager.AuthRequest`
        so the consumer-UI handler's call shape doesn't change.
    """
    username: str
    password: str
    client_ip: str = ""
    user_agent: str = ""


@dataclass
class AuthResponse:
    """
        Successful authentication result.

        :param token: The session id the cookie will carry.
        :param expires_at: When the session expires.
        :param user_id: Authenticated user id.
        :param username: User's login name.
        :param csrf_token: Freshly-generated CSRF token to bind
                           to the cookie session.
    """
    token: str
    expires_at: datetime
    user_id: str
    username: str
    csrf_token: str


@dataclass
class SessionInfo:
    """
        Validated-session readout. Mirrors the legacy
        ``SessionInfo`` shape consumer-UI handlers consume.

        :param session_id: The session id (= token).
        :param token: Same as ``session_id``.
        :param user_id: Authenticated user id.
        :param username: User's login name.
        :param csrf_token: Empty under the modern stack -- the
                           cookie session is the CSRF source of
                           truth, see module docstring.
        :param created_at: Session open time.
        :param last_activity: Most-recent observed activity.
        :param expires_at: Session expiry.
        :param client_ip: IP-fingerprint hash (not raw IP).
        :param user_agent: User-Agent fingerprint hash.
    """
    session_id: str
    token: str
    user_id: str
    username: str
    csrf_token: str = ""
    created_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    client_ip: str = ""
    user_agent: str = ""


class AuthenticationError(Exception):
    """
        Raised by :meth:`ConsumerUISecurityAdapter.authenticate`
        on any failed login. Mirrors the legacy
        ``security_manager.AuthenticationError`` so handler
        ``except`` blocks don't change.
    """

    def __init__(self, message: str = "Invalid credentials") -> None:
        self.message: str = message
        super().__init__(message)
        return


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


def _fingerprint_value(*, raw: str) -> str:
    """
        Hash a raw IP / User-Agent string for storage on
        :class:`AuthSession`. Production uses the same shape;
        the test stub uses a tag so logs stay readable.
    """
    if raw is None:
        raw = ""
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    rtnval = digest[:64]
    return rtnval


class ConsumerUISecurityAdapter:
    """
        Thin facade over :mod:`security.auth.local_flow` +
        :mod:`security.auth.session_service` that mimics the
        legacy :class:`SecurityManager` interface.

        Constructed once per request by
        :func:`webinterface.blueprints.config.routes._build_security_manager`.
    """

    def __init__(self, db_session: Any) -> None:
        """
            :param db_session: Active per-request SQLAlchemy
                               session.
        """
        self._db_session: Any = db_session
        return

    # ------------------------------------------------------------------
    # authenticate
    # ------------------------------------------------------------------

    def authenticate(self, request: AuthRequest) -> AuthResponse:
        """
            Verify local credentials and open a modern
            :class:`AuthSession`. Returns an
            :class:`AuthResponse` whose ``token`` slot carries
            the new ``session_id`` (the same value the cookie
            stores under ``session_token``).

            :param request: Login form payload.

            :returns: Populated :class:`AuthResponse`.
            :raises: :class:`AuthenticationError` on any
                     verification failure.
        """
        try:
            credentials_result = local_flow.verify_local_credentials(
                login_name=request.username,
                password=request.password,
                mfa_code=None,
                source_ip=request.client_ip or "",
                db_session=self._db_session,
            )
        except ModernAuthenticationError as exc:
            raise AuthenticationError(str(exc)) from None
        except Exception as exc:
            # Backoff state-machine raises ``AuthenticationError``
            # when a caller is still rate-limited; flatten to the
            # adapter's exception type so handler ``except``
            # blocks don't have to know about modern exception
            # classes.
            raise AuthenticationError(str(exc)) from None

        user_row = (
            self._db_session.query(IdentityUser)
            .filter(IdentityUser.user_id == credentials_result.user_id)
            .first()
        )
        if user_row is None:
            raise AuthenticationError("Invalid credentials")

        fingerprint = RequestFingerprint(
            ip_fingerprint=_fingerprint_value(raw=request.client_ip),
            user_agent_fingerprint=_fingerprint_value(
                raw=request.user_agent
            ),
        )

        session = open_session(
            db_session=self._db_session,
            user_id=str(user_row.user_id),
            provider_kind=AuthProviderKind.LOCAL,
            provider_name="local",
            mfa_method_name=None,
            access_token_payload=None,
            refresh_token_payload=None,
            request_fingerprint=fingerprint,
            idle_timeout_seconds=_DEFAULT_SESSION_IDLE_TIMEOUT_SECONDS,
            max_lifetime_seconds=_DEFAULT_SESSION_MAX_LIFETIME_SECONDS,
        )

        # CSRF token lives on the cookie session payload, not on
        # the AuthSession row -- the modern schema does not carry
        # a CSRF column. Generate a fresh one per login; the
        # handler will write it onto the cookie under
        # ``csrf.SESSION_KEY``.
        csrf_token = secrets.token_urlsafe(32)

        rtnval = AuthResponse(
            token=str(session.session_id),
            expires_at=session.expires_at,
            user_id=str(user_row.user_id),
            username=user_row.login_name,
            csrf_token=csrf_token,
        )
        return rtnval

    # ------------------------------------------------------------------
    # validate_token
    # ------------------------------------------------------------------

    def validate_token(self, token: str) -> Optional[SessionInfo]:
        """
            Validate the cookie's ``session_token`` against the
            ``auth_sessions`` table. Returns a
            :class:`SessionInfo` on success; ``None`` on any
            failure (matches the legacy
            :meth:`SecurityManager.validate_token` contract).

            The ``csrf_token`` slot on the result is empty --
            the consumer-UI handler is expected to read CSRF
            from the cookie session, not from this readout. See
            module docstring.

            :param token: Session id to validate.

            :returns: :class:`SessionInfo` on a live session;
                      ``None`` otherwise.
        """
        if token is None or len(token) == 0:
            return None

        now = datetime.now(timezone.utc)
        try:
            principal = resolve_session(
                db_session=self._db_session,
                session_id=token,
                now=now,
            )
        except SessionExpiredError:
            return None
        except SessionNotFoundError:
            return None
        except Exception:
            return None

        # ``resolve_session`` returns an :class:`AuthPrincipal`
        # but we need the AuthSession itself for timestamps +
        # the IdentityUser for the username. Both live behind
        # one extra query each.
        session_row = (
            self._db_session.query(AuthSession)
            .filter(AuthSession.session_id == principal.session_id)
            .first()
        )
        if session_row is None:
            return None

        user_row = (
            self._db_session.query(IdentityUser)
            .filter(IdentityUser.user_id == session_row.user_id)
            .first()
        )
        if user_row is None:
            return None

        rtnval = SessionInfo(
            session_id=str(session_row.session_id),
            token=str(session_row.session_id),
            user_id=str(session_row.user_id),
            username=user_row.login_name,
            csrf_token="",
            created_at=session_row.opened_at,
            last_activity=session_row.last_seen_at,
            expires_at=session_row.expires_at,
            client_ip=session_row.ip_fingerprint or "",
            user_agent=session_row.user_agent_fingerprint or "",
        )
        return rtnval

    # ------------------------------------------------------------------
    # logout
    # ------------------------------------------------------------------

    def logout(self, token: str) -> None:
        """
            Close the session via
            :func:`session_service.close_session`. Idempotent --
            unknown tokens are silently ignored to match the
            legacy ``SecurityManager.logout`` contract.

            :param token: Session id to close.

            :returns: None.
        """
        if token is None or len(token) == 0:
            return
        try:
            close_session(
                db_session=self._db_session, session_id=token
            )
        except Exception:
            # The legacy SecurityManager ate exceptions on logout
            # too; the consumer-UI handler doesn't surface any
            # information from this call.
            pass
        return

    # ------------------------------------------------------------------
    # check_permission (modern rbac_evaluator)
    # ------------------------------------------------------------------

    def check_permission(
            self, user_id: str, permission: str
        ) -> bool:
        """
            Evaluate a permission for ``user_id`` against the modern
            :mod:`rbac_evaluator` on the ``rbac_*`` tables.

            The consumer-UI's permission gates pass canonical
            ``system:<action>`` keys (e.g.
            ``"system:resources.manage"``); the evaluator walks
            the principal's direct + group + organization
            bindings and returns an :class:`AuthzDecision`. We
            collapse that to a simple ``bool`` to preserve the
            legacy ``SecurityManager.check_permission`` contract
            consumer-UI handlers were written against.

            On any unexpected internal failure (malformed key,
            schema problem, etc.) the helper treats the request
            as denied -- the call site already swallows the
            exception and routes through the deny-redirect
            branch, so a permissive default would mask real
            bugs.

            :param user_id: User id (UUID string from the auth
                            flow's :class:`AuthSession`).
            :param permission: Canonical permission key (e.g.
                               ``"system:resources.manage"``).

            :returns: ``True`` if the principal holds the
                      permission, ``False`` otherwise.
        """
        from datetime import datetime, timezone  # noqa: E402

        from automojo.pychestrate.webservice.security.auth.session_service import (  # noqa: E402
            AuthPrincipal,
        )
        from automojo.pychestrate.webservice.security.auth.models import (  # noqa: E402
            AuthProviderKind,
        )
        from automojo.pychestrate.webservice.security.rbac import (  # noqa: E402
            rbac_evaluator,
        )

        # The evaluator's permission_key contract requires a
        # namespace; reject bare keys early so the caller gets
        # a deny rather than a ``SemanticError`` bubble.
        if permission is None or len(permission.strip()) == 0:
            return False
        if ":" not in permission:
            return False

        # Build a minimal AuthPrincipal. The evaluator only reads
        # ``user_id`` off it for its own group-membership lookup;
        # ``session_id`` / ``provider_kind`` / ``provider_name``
        # are not used in the binding-lookup path. We supply the
        # caller's user_id and benign defaults for the rest.
        principal = AuthPrincipal(
            user_id=user_id,
            session_id="",
            provider_kind=AuthProviderKind.LOCAL,
            provider_name="local",
        )
        now = datetime.now(timezone.utc)

        try:
            decision = rbac_evaluator.check_permission(
                db_session=self._db_session,
                principal=principal,
                permission_key=permission,
                now=now,
            )
        except Exception:
            return False

        rtnval = decision.allowed
        return rtnval


__all__ = [
    "AuthRequest",
    "AuthResponse",
    "SessionInfo",
    "AuthenticationError",
    "ConsumerUISecurityAdapter",
]
