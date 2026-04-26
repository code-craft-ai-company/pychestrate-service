"""
.. module:: security.auth.webworks_bridge
    :synopsis: Bridge pychestrate auth_sessions → automojo-webworks session['user'].

The 1-authentication feature persists sessions in the
``auth_sessions`` table and carries the session id in the
``pychestrate_session`` cookie. The shipped
``automojo.webservice.xflask.baseauthentication.check_authentication_with_roles``
hook expects to read a populated Flask ``session['user']``
dict (with at least ``roles``) before it'll let a request
through to a protected endpoint.

This module installs a ``before_request`` hook that runs
*before* webworks' enforcement: it reads the
``pychestrate_session`` cookie, resolves it via
:func:`session_service.resolve_session`, looks up the user's
canonical role names via the RBAC binding service, and
populates Flask ``session['user']`` in the shape
:func:`automojo.webservice.xflask.basestate.establish_session`
produces. Webworks then enforces against that populated
session unmodified.

When the cookie is missing or its session row has expired,
the bridge clears any stale ``session['user']`` so webworks
sends the request to its login redirect / 401 path instead
of letting it through on a previous principal.

The user-detail lookup, role resolver, and DB-session
factory are all caller-supplied so the bridge can be wired
both in production (against the real network DB) and in
tests (against an in-memory SQLite engine).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from flask import Flask, g, request, session
from sqlalchemy.orm import Session as DbSession

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
        into Flask ``session['user']``.

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


def install_pychestrate_session_bridge(
        *,
        app: Flask,
        session_factory: SessionFactory,
        role_resolver: RoleResolver,
        user_profile_lookup: UserProfileLookup,
        cookie_name: str = SESSION_COOKIE_NAME
    ) -> None:
    """
        Install the ``before_request`` hook that translates
        a ``pychestrate_session`` cookie into a populated
        Flask ``session['user']`` so webworks'
        ``check_authentication_with_roles`` enforces the
        right principal.

        :param app: Flask application to install on.
        :param session_factory: Callable returning a fresh
                                ``DbSession`` for the
                                resolution + role-lookup
                                round trip.
        :param role_resolver: Callable returning the role
                              names granted to the supplied
                              user id.
        :param user_profile_lookup: Callable returning a
                                    :class:`UserProfile` for
                                    the supplied user id, or
                                    ``None`` when the user
                                    can't be loaded.
        :param cookie_name: Override the default
                            ``pychestrate_session`` cookie
                            name.

        :returns: None. The hook is registered on ``app``.
    """
    if app is None:
        err_lines = [
            "install_pychestrate_session_bridge requires a Flask app.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if session_factory is None:
        err_lines = [
            "install_pychestrate_session_bridge requires a session_factory.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if role_resolver is None:
        err_lines = [
            "install_pychestrate_session_bridge requires a role_resolver.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if user_profile_lookup is None:
        err_lines = [
            "install_pychestrate_session_bridge requires a user_profile_lookup.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if getattr(app, "_pychestrate_webworks_bridge_installed", False) is True:
        # Idempotent — installing twice on the same app shouldn't
        # double-register the hook.
        return

    def _bridge_before_request():
        cookie_value = request.cookies.get(cookie_name, "")
        if cookie_value is None or len(cookie_value) == 0:
            _clear_session_user()
            return None
        rtnval = _populate_session_from_cookie(
            cookie_value=cookie_value,
            session_factory=session_factory,
            role_resolver=role_resolver,
            user_profile_lookup=user_profile_lookup,
        )
        return rtnval

    app.before_request(_bridge_before_request)
    setattr(app, "_pychestrate_webworks_bridge_installed", True)
    return


def _populate_session_from_cookie(
        *,
        cookie_value: str,
        session_factory: SessionFactory,
        role_resolver: RoleResolver,
        user_profile_lookup: UserProfileLookup
    ):
    db_session = session_factory()
    try:
        try:
            principal = session_service.resolve_session(
                db_session=db_session,
                session_id=cookie_value,
                now=datetime.now(tz=timezone.utc),
            )
        except (SessionNotFoundError, SessionExpiredError):
            _clear_session_user()
            return None
        profile = user_profile_lookup(db_session, principal.user_id)
        roles = role_resolver(db_session, principal.user_id)
    finally:
        db_session.close()

    if profile is None:
        _clear_session_user()
        return None

    user_info: Dict[str, Any] = {
        "sub": profile.user_id,
        "username": profile.username,
        "display_name": profile.display_name,
        "email": profile.email,
        "roles": list(roles) if roles is not None else [],
        "session_id": principal.session_id,
        "provider_kind": principal.provider_kind.value,
        "provider_name": principal.provider_name,
    }
    session["user"] = user_info
    g.current_user = user_info
    g.pychestrate_session_id = principal.session_id
    return None


def _clear_session_user() -> None:
    if "user" in session:
        session.pop("user", None)
    return


def default_role_resolver_via_rbac(
        db_session: DbSession, user_id: str
    ) -> List[str]:
    """
        Default :class:`RoleResolver` implementation that
        reads the RBAC binding service. Production wires
        this; tests typically pass a deterministic stub.
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
    if bindings is None or len(bindings) == 0:
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
