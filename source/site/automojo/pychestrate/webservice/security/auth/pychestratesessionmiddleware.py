"""
.. module:: security.auth.webworks_bridge
    :synopsis: Bridge pychestrate auth_sessions → webworks AuthenticationContext.

.. moduleauthor:: Automation Mojo LLC

The 1-authentication feature persists sessions in the
``auth_sessions`` table and carries the session id in the
``pychestrate_session`` cookie. The webworks ``AccessPolicy`` machinery
enforces role/scope requirements against an
:class:`~automojo.webworks.authentication.core.AuthenticationContext`
attached to the request.

This module exposes :class:`PychestrateSessionMiddleware`, a routing
pipeline middleware (``__call__(request, call_next) -> response``) that:

* reads the ``pychestrate_session`` cookie,
* resolves it via :func:`session_service.resolve_session`,
* looks up the user's canonical role names via the RBAC binding service,
* builds a :class:`~automojo.webworks.authentication.core.Principal`
  carrying the user id and role set, plus an
  :class:`~automojo.webworks.authentication.core.AuthenticationContext`
  with the session id, provider kind, provider name, and a ``user_info``
  attribute mirroring the legacy Flask ``session['user']`` shape, and
* attaches the context to the request as ``request.auth`` (the
  conventional key webworks uses).

When the cookie is missing or its session row has expired, ``request.auth``
is left as ``None`` so downstream policy enforcement sends the request to
the login flow / 401 path instead of treating it as an authenticated
principal.

The user-detail lookup, role resolver, and DB-session factory are all
caller-supplied so the bridge can be wired both in production (against
the real network DB) and in tests (against an in-memory SQLite engine).
This module ships ``default_role_resolver_via_rbac`` and
``default_user_profile_lookup_via_user_service`` for production wiring;
tests typically pass deterministic stubs.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.webworks.authentication.core import (
    AuthenticationContext,
    Principal,
)
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import Response

from automojo.pychestrate.webservice.security.auth import session_service
from automojo.pychestrate.webservice.security.auth.cookies import (
    SESSION_COOKIE_NAME,
)
from automojo.pychestrate.webservice.security.auth.exceptions import (
    SessionExpiredError,
    SessionNotFoundError,
)


SessionFactory = Callable[[], DbSession]
RoleResolver = Callable[[DbSession, str], List[str]]


@dataclass(frozen=True)
class UserProfile:
    """
        Subset of the IdentityUser snapshot the bridge writes
        into the AuthenticationContext attributes ``user_info`` payload.

        :param user_id: Authoritative user id.
        :param username: Login name.
        :param display_name: Human-facing display name.
        :param email: Primary email.
    """
    user_id: str
    username: str
    display_name: str
    email: str


UserProfileLookup = Callable[[DbSession, str], Optional[UserProfile]]


PYCHESTRATE_SESSION_SCHEME = "pychestrate-session"


class PychestrateSessionMiddleware:
    """
        Webworks routing-pipeline middleware that translates a
        ``pychestrate_session`` cookie into a webworks
        :class:`AuthenticationContext` attached to ``request.auth``.

        The middleware mirrors the populating behavior of the legacy
        Flask ``before_request`` hook one-to-one (same cookie, same
        resolution path, same role + user-profile lookups) but emits
        the resolved identity in the webworks idiom so AccessPolicy
        enforcement can read it.

        :param session_factory: Zero-argument callable returning a
                                fresh ``DbSession`` for the resolution
                                + role-lookup round trip.
        :param role_resolver: Callable returning the role names granted
                              to the supplied user id.
        :param user_profile_lookup: Callable returning a
                                    :class:`UserProfile` for the
                                    supplied user id, or ``None`` when
                                    the user can't be loaded.
        :param cookie_name: Override the default ``pychestrate_session``
                            cookie name.
    """

    name: str = "pychestrate_session_bridge"

    def __init__(
            self,
            *,
            session_factory: SessionFactory,
            role_resolver: RoleResolver,
            user_profile_lookup: UserProfileLookup,
            cookie_name: str = SESSION_COOKIE_NAME,
        ):
        """
            Construct a :class:`PychestrateSessionMiddleware`.

            :param session_factory: Callable returning a fresh
                                    ``DbSession``.
            :param role_resolver: Callable returning the role names
                                  for a user id.
            :param user_profile_lookup: Callable returning a
                                        :class:`UserProfile` for a user
                                        id, or ``None``.
            :param cookie_name: Cookie name to read.

            :raises ValueError: If any required dependency is None.
        """
        if session_factory is None:
            err_lines = [
                "PychestrateSessionMiddleware requires a session_factory.",
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        if role_resolver is None:
            err_lines = [
                "PychestrateSessionMiddleware requires a role_resolver.",
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        if user_profile_lookup is None:
            err_lines = [
                "PychestrateSessionMiddleware requires a user_profile_lookup.",
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        self._session_factory: SessionFactory = session_factory
        self._role_resolver: RoleResolver = role_resolver
        self._user_profile_lookup: UserProfileLookup = user_profile_lookup
        self._cookie_name: str = cookie_name
        return

    @property
    def cookie_name(self) -> str:
        """
            The configured cookie name.

            :returns: The cookie name string.
        """
        rtnval = self._cookie_name
        return rtnval

    def __call__(
            self,
            request: Request,
            call_next: Callable[[Request], Response],
        ) -> Response:
        """
            Resolve the cookie (if present) and attach the resulting
            :class:`AuthenticationContext` to ``request.auth`` before
            invoking the next handler.

            :param request: The incoming :class:`Request`.
            :param call_next: The next callable in the pipeline.

            :returns: The :class:`Response` returned by the downstream
                      handler.
        """
        # Respect an existing non-None request.auth so test scaffolds
        # can pre-inject an AuthenticationContext directly without
        # going through the cookie + DB resolution path. Production
        # requests always start without ``request.auth``, so this
        # short-circuit is inert outside tests.
        existing = getattr(request, "auth", None)
        if existing is not None:
            response = call_next(request)
            return response

        cookie_value = request.cookies.get(self._cookie_name, "")
        if cookie_value is None or len(cookie_value) == 0:
            request.auth = None
            response = call_next(request)
            return response

        context = self._resolve_context(cookie_value=cookie_value)
        request.auth = context
        response = call_next(request)
        return response

    def _resolve_context(
            self,
            *,
            cookie_value: str,
        ) -> Optional[AuthenticationContext]:
        """
            Translate a cookie value to an :class:`AuthenticationContext`.

            :param cookie_value: The raw cookie value from the request.

            :returns: A populated :class:`AuthenticationContext` on
                      success, or ``None`` when the session is unknown,
                      expired, or the user profile cannot be loaded.
        """
        db_session = self._session_factory()
        try:
            try:
                principal_record = session_service.resolve_session(
                    db_session=db_session,
                    session_id=cookie_value,
                    now=datetime.now(tz=timezone.utc),
                )
            except (SessionNotFoundError, SessionExpiredError):
                return None
            profile = self._user_profile_lookup(
                db_session, principal_record.user_id,
            )
            roles = self._role_resolver(
                db_session, principal_record.user_id,
            )
        finally:
            db_session.close()

        if profile is None:
            return None

        role_names: List[str] = list(roles) if roles is not None else []

        user_info: Dict[str, Any] = {
            "sub": profile.user_id,
            "username": profile.username,
            "display_name": profile.display_name,
            "email": profile.email,
            "roles": list(role_names),
            "session_id": principal_record.session_id,
            "provider_kind": principal_record.provider_kind.value,
            "provider_name": principal_record.provider_name,
        }

        webworks_principal = Principal(
            identifier=profile.user_id,
            display_name=profile.display_name,
            roles=set(role_names),
            permissions=set(),
            attributes={
                "username": profile.username,
                "email": profile.email,
            },
        )

        context = AuthenticationContext(
            principal=webworks_principal,
            scheme=PYCHESTRATE_SESSION_SCHEME,
            attributes={
                "session_id": principal_record.session_id,
                "provider_kind": principal_record.provider_kind.value,
                "provider_name": principal_record.provider_name,
                "user_info": user_info,
            },
        )
        rtnval = context
        return rtnval


def default_role_resolver_via_rbac(
        db_session: DbSession, user_id: str
    ) -> List[str]:
    """
        Default :class:`RoleResolver` implementation that
        reads the RBAC binding service. Production wires
        this; tests typically pass a deterministic stub.

        :param db_session: SQLAlchemy session to read through.
        :param user_id: User id to resolve roles for.

        :returns: Sorted list of role names granted to the user.
    """
    from automojo.pychestrate.webservice.security.rbac import (
        binding_service,
        models as rbac_models,
    )

    bindings = binding_service.list_bindings(
        db_session=db_session,
        principal_kind=rbac_models.PrincipalKind.USER,
        principal_id=user_id,
    )
    if bindings is None:
        return []
    if len(bindings) == 0:
        return []
    rtnval = sorted({b.role_name for b in bindings})
    return rtnval


def default_user_profile_lookup_via_user_service(
        db_session: DbSession, user_id: str
    ) -> Optional[UserProfile]:
    """
        Default :class:`UserProfileLookup` implementation
        that reads the identity ``user_service``. Production
        wires this; tests typically pass a deterministic
        stub.

        :param db_session: SQLAlchemy session to read through.
        :param user_id: User id to look up.

        :returns: The matching :class:`UserProfile`, or ``None`` when
                  the user cannot be loaded.
    """
    from automojo.pychestrate.webservice.identity.users import (
        user_service,
    )
    from automojo.pychestrate.webservice.identity.users.exceptions import (
        UserNotFoundError,
    )

    try:
        user = user_service.read_user(
            db_session=db_session, user_id=user_id,
        )
    except UserNotFoundError:
        return None
    rtnval = UserProfile(
        user_id=str(user.user_id),
        username=user.login_name,
        display_name=user.display_name,
        email=user.primary_email,
    )
    return rtnval
