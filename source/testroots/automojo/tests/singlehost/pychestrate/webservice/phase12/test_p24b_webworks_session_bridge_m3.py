"""
.. module:: test_p24b_webworks_session_bridge_m3
    :synopsis: Tests for P24b — pychestrate session bridge as a webworks middleware.

This module exercises :class:`PychestrateSessionMiddleware` end-to-end.
The bridge replaces the legacy Flask ``before_request`` hook and
populates ``request.auth`` with a webworks
:class:`~automojo.webworks.authentication.core.AuthenticationContext`
so AccessPolicy enforcement reads the resolved identity in the webworks
idiom.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Dict, List, Optional, Tuple

from automojo import testbase

from automojo.webworks.authentication.core import AuthenticationContext
from automojo.webworks.routing.dispatcher import Dispatcher
from automojo.webworks.routing.middleware import MiddlewarePipeline
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response
from automojo.webworks.routing.router import Router

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.security.auth import session_service
from automojo.pychestrate.webservice.security.auth.cookies import (
    SESSION_COOKIE_NAME,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
)
from automojo.pychestrate.webservice.security.auth.session_service import (
    RequestFingerprint,
)
from automojo.pychestrate.webservice.security.auth.pychestratesessionmiddleware import (
    PYCHESTRATE_SESSION_SCHEME,
    PychestrateSessionMiddleware,
    UserProfile,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


_CAPTURED_AUTH_KEY = "captured_auth"


def _seed_session_for_user(*, session, user_id: str) -> str:
    """
        Open an auth_session row for ``user_id``.

        :param session: SQLAlchemy session to write through.
        :param user_id: User id to seat.

        :returns: The new session id (string).
    """
    seated = session_service.open_session(
        db_session=session,
        user_id=user_id,
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
        mfa_method_name=None,
        access_token_payload=None,
        refresh_token_payload=None,
        request_fingerprint=RequestFingerprint(
            ip_fingerprint="ip", user_agent_fingerprint="ua",
        ),
        idle_timeout_seconds=1800,
        max_lifetime_seconds=8 * 3600,
    )
    rtnval = str(seated.session_id)
    return rtnval


def _make_app_callable(
        *,
        engine,
        roles: List[str],
        profile: Optional[UserProfile],
        captured: Dict[str, Optional[AuthenticationContext]],
    ):
    """
        Build the callable :class:`TestClient` consumes. Installs the
        bridge middleware, registers a single capture endpoint at
        ``/probe`` that reads ``request.auth`` and stashes it in
        ``captured`` so the test can assert on it.

        :param engine: In-memory SQLAlchemy engine.
        :param roles: Role names the resolver should return.
        :param profile: User profile the lookup should return (or
                        ``None`` to simulate a missing user record).
        :param captured: Dict the probe handler writes
                         ``request.auth`` into under
                         ``_CAPTURED_AUTH_KEY``.

        :returns: A ``(method, path, headers, body) -> (status,
                  headers, body)`` callable.
    """
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=engine)

    def _role_resolver(_db_session, _user_id):
        rtnval = list(roles)
        return rtnval

    def _profile_lookup(_db_session, _user_id):
        rtnval = profile
        return rtnval

    middleware = PychestrateSessionMiddleware(
        session_factory=session_factory,
        role_resolver=_role_resolver,
        user_profile_lookup=_profile_lookup,
    )

    def _probe_handler(request: Request) -> Response:
        captured[_CAPTURED_AUTH_KEY] = getattr(request, "auth", None)
        rtnval = JSONResponse(content={"ok": True}, status_code=200)
        return rtnval

    from automojo.webworks.endpoints.descriptor import EndpointDescriptor
    descriptor = EndpointDescriptor(
        handler=_probe_handler,
        module=__name__,
        leaf=None,
        path="/probe",
        methods=["GET"],
    )

    router = Router()
    router.add_endpoint(descriptor=descriptor)

    pipeline = MiddlewarePipeline()
    pipeline.add(middleware=middleware, name=middleware.name)

    dispatcher = Dispatcher(router=router, pipeline=pipeline)

    def _app_callable(
            method: str,
            path: str,
            headers: Dict[str, str],
            body: bytes,
        ) -> Tuple[int, Dict[str, str], bytes]:
        request = Request(
            method=method,
            path=path,
            headers=headers,
            body=body,
        )
        response = dispatcher.dispatch(request=request)
        rtnval = (response.status_code, dict(response.headers), response.body)
        return rtnval

    return _app_callable


def _setup() -> Tuple[object, object]:
    """
        Reset phase-1 runtime and build a fresh in-memory engine +
        session.

        :returns: Tuple of ``(engine, session)``.
    """
    reset_phase1_runtime()
    engine, session = build_in_memory_session()
    rtnval = (engine, session)
    return rtnval


def _make_profile(*, user_id: str) -> UserProfile:
    """
        Build a deterministic :class:`UserProfile` for ``user_id``.

        :param user_id: User id the profile belongs to.

        :returns: A populated :class:`UserProfile`.
    """
    rtnval = UserProfile(
        user_id=str(user_id),
        username="alice",
        display_name="Alice",
        email="alice@example.com",
    )
    return rtnval


# -------------------------------------
# happy path: cookie → AuthenticationContext on request.auth
# -------------------------------------

def test_valid_session_cookie_populates_authentication_context_on_request():
    """
    **Feature: P24b webworks session bridge (M3)**
    **Property: A valid pychestrate_session cookie causes the bridge
    to attach an AuthenticationContext to request.auth, with the
    resolved Principal carrying the user id, display name, and the
    role set returned by the resolver.**
    """
    engine, session = _setup()
    try:
        user_id = new_uuid()
        session_id = _seed_session_for_user(session=session, user_id=user_id)
        session.commit()

        captured: Dict[str, Optional[AuthenticationContext]] = {}
        app_callable = _make_app_callable(
            engine=engine,
            roles=["admin", "operator"],
            profile=_make_profile(user_id=str(user_id)),
            captured=captured,
        )
        cookie_header = "{}={}".format(SESSION_COOKIE_NAME, session_id)

        status_code, _, _ = app_callable(
            "GET", "/probe", {"Cookie": cookie_header}, b"",
        )

        testbase.assert_equal(status_code, 200)
        context = captured[_CAPTURED_AUTH_KEY]
        testbase.assert_equal(context is None, False)
        testbase.assert_equal(context.scheme, PYCHESTRATE_SESSION_SCHEME)
        testbase.assert_equal(context.principal.identifier, str(user_id))
        testbase.assert_equal(context.principal.display_name, "Alice")
        testbase.assert_equal(context.principal.has_role("admin"), True)
        testbase.assert_equal(context.principal.has_role("operator"), True)
        testbase.assert_equal(context.attributes["session_id"], session_id)
        testbase.assert_equal(context.attributes["provider_kind"], "LOCAL")
        testbase.assert_equal(context.attributes["provider_name"], "local")
        user_info = context.attributes["user_info"]
        testbase.assert_equal(user_info["username"], "alice")
        testbase.assert_equal(user_info["email"], "alice@example.com")
        testbase.assert_equal(user_info["roles"], ["admin", "operator"])
    finally:
        session.close()
    return


# -------------------------------------
# missing cookie → request.auth is None
# -------------------------------------

def test_missing_cookie_leaves_request_auth_none():
    """
    **Feature: P24b webworks session bridge (M3)**
    **Property: When the pychestrate_session cookie is absent the
    bridge does not call the role resolver or profile lookup and
    leaves request.auth as None so downstream policy enforcement
    treats the request as anonymous.**
    """
    engine, session = _setup()
    try:
        captured: Dict[str, Optional[AuthenticationContext]] = {}
        app_callable = _make_app_callable(
            engine=engine,
            roles=["admin"],
            profile=_make_profile(user_id="never-looked-up"),
            captured=captured,
        )

        status_code, _, _ = app_callable(
            "GET", "/probe", {}, b"",
        )

        testbase.assert_equal(status_code, 200)
        testbase.assert_equal(captured[_CAPTURED_AUTH_KEY] is None, True)
    finally:
        session.close()
    return


# -------------------------------------
# unknown cookie → request.auth is None
# -------------------------------------

def test_unknown_session_cookie_leaves_request_auth_none():
    """
    **Feature: P24b webworks session bridge (M3)**
    **Property: When the cookie value does not match any session row
    the bridge swallows SessionNotFoundError and leaves request.auth
    as None.**
    """
    engine, session = _setup()
    try:
        captured: Dict[str, Optional[AuthenticationContext]] = {}
        app_callable = _make_app_callable(
            engine=engine,
            roles=["admin"],
            profile=_make_profile(user_id="never-looked-up"),
            captured=captured,
        )
        cookie_header = "{}={}".format(SESSION_COOKIE_NAME, str(new_uuid()))

        status_code, _, _ = app_callable(
            "GET", "/probe", {"Cookie": cookie_header}, b"",
        )

        testbase.assert_equal(status_code, 200)
        testbase.assert_equal(captured[_CAPTURED_AUTH_KEY] is None, True)
    finally:
        session.close()
    return


# -------------------------------------
# user-profile lookup miss → request.auth is None
# -------------------------------------

def test_unknown_user_profile_leaves_request_auth_none():
    """
    **Feature: P24b webworks session bridge (M3)**
    **Property: When the session resolves but the user_profile_lookup
    returns None (e.g. user row was deleted post-login) the bridge
    treats the request as anonymous rather than constructing a
    Principal with missing fields.**
    """
    engine, session = _setup()
    try:
        user_id = new_uuid()
        session_id = _seed_session_for_user(session=session, user_id=user_id)
        session.commit()

        captured: Dict[str, Optional[AuthenticationContext]] = {}
        app_callable = _make_app_callable(
            engine=engine,
            roles=["admin"],
            profile=None,
            captured=captured,
        )
        cookie_header = "{}={}".format(SESSION_COOKIE_NAME, session_id)

        status_code, _, _ = app_callable(
            "GET", "/probe", {"Cookie": cookie_header}, b"",
        )

        testbase.assert_equal(status_code, 200)
        testbase.assert_equal(captured[_CAPTURED_AUTH_KEY] is None, True)
    finally:
        session.close()
    return


# -------------------------------------
# constructor validation
# -------------------------------------

def test_middleware_construction_rejects_missing_dependencies():
    """
    **Feature: P24b webworks session bridge (M3)**
    **Property: The middleware constructor refuses to build with a
    missing session_factory, role_resolver, or user_profile_lookup.**
    """
    raised_session = False
    try:
        PychestrateSessionMiddleware(
            session_factory=None,
            role_resolver=lambda *args: [],
            user_profile_lookup=lambda *args: None,
        )
    except ValueError:
        raised_session = True
    testbase.assert_equal(raised_session, True)

    raised_resolver = False
    try:
        PychestrateSessionMiddleware(
            session_factory=lambda: None,
            role_resolver=None,
            user_profile_lookup=lambda *args: None,
        )
    except ValueError:
        raised_resolver = True
    testbase.assert_equal(raised_resolver, True)

    raised_lookup = False
    try:
        PychestrateSessionMiddleware(
            session_factory=lambda: None,
            role_resolver=lambda *args: [],
            user_profile_lookup=None,
        )
    except ValueError:
        raised_lookup = True
    testbase.assert_equal(raised_lookup, True)
    return
