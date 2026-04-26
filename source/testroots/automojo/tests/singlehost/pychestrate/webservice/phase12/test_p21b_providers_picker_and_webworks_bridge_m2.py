"""
.. module:: test_p21b_providers_picker_and_webworks_bridge_m2
    :synopsis: Tests for P21b — providers picker REST + webworks bridge.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timezone
from typing import List, Optional

from flask import Flask, jsonify, session as flask_session
from flask_restx import Api
from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.pychestrate.webservice.security.auth import (
    provider_directory,
    session_service,
)
from automojo.pychestrate.webservice.security.auth.cookies import (
    SESSION_COOKIE_NAME,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
)
from automojo.pychestrate.webservice.security.auth.oidc.provider_registry import (
    OidcProviderConfig,
    register_oidc_provider,
    reset_for_testing as reset_oidc_registry,
)
from automojo.pychestrate.webservice.security.auth.restapi.v1 import (
    auth_controller,
)
from automojo.pychestrate.webservice.security.auth.session_service import (
    RequestFingerprint,
    open_session,
)
from automojo.pychestrate.webservice.security.auth.webworks_bridge import (
    UserProfile,
    install_pychestrate_session_bridge,
)

# Webworks pieces under validation.
from automojo.webservice.xflask.baseauthentication import (
    check_authentication_with_roles,
)
from automojo.webservice.xflask.basesecurity import RouteSecurityManager
from automojo.webservice.xflask.basestate import BASE_SITE_SERVICE_STATE

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


def _stub_oidc_token_fetcher(_request):
    return None


def _stub_oidc_key_resolver(_kid):
    return None


def _register_oidc(*, provider_name: str = "okta") -> None:
    register_oidc_provider(
        config=OidcProviderConfig(
            provider_name=provider_name,
            authorization_endpoint="https://idp.example.com/authorize",
            token_endpoint="https://idp.example.com/token",
            expected_issuer="https://idp.example.com",
            client_id="client-pychestrate",
            redirect_uri="https://app.example.com/cb",
            token_fetcher=_stub_oidc_token_fetcher,
            key_resolver=_stub_oidc_key_resolver,
            session_factory=lambda: None,
        ),
    )
    return


def _setup_picker() -> Flask:
    provider_directory.reset_for_testing()
    reset_oidc_registry()
    _register_oidc()
    provider_directory.register_credential_mode(
        kind=AuthProviderKind.OIDC,
        provider_name="okta",
        display_label="Sign in with Okta",
    )
    provider_directory.register_credential_mode(
        kind=AuthProviderKind.LOCAL,
        provider_name="local",
        display_label="Local password",
    )
    provider_directory.register_credential_mode(
        kind=AuthProviderKind.LOCAL,
        provider_name="staged-local",
        display_label="Staged local",
        enabled=False,
    )
    app = Flask("p21b-picker")
    app.config["TESTING"] = True
    api = Api(app)
    for ns, path in auth_controller.publish_namespaces(
        version_prefix="/1",
    ):
        api.add_namespace(ns, path=path)
    return app


# -------------------------------------
# Picker endpoint
# -------------------------------------

def test_get_providers_returns_only_enabled_modes_sorted():
    """
    **Feature: 1-authentication (M2)**
    **Property: GET /api/v1/auth/providers returns 200 with
    every enabled credential mode, filtered against the
    backing config registries and sorted by (kind,
    provider_name).**
    """
    app = _setup_picker()
    client = app.test_client()
    response = client.get("/1/auth/providers")
    testbase.assert_equal(response.status_code, 200)
    body = response.get_json()
    pairs = [
        (p["kind"], p["provider_name"]) for p in body["providers"]
    ]
    testbase.assert_equal(pairs, [("LOCAL", "local"), ("OIDC", "okta")])
    return


def test_get_providers_emits_canonical_login_paths():
    """
    **Feature: 1-authentication (M2)**
    **Property: each picker entry's login_path defaults to
    the canonical /auth/{kind}/{name}/login URL the
    controller routes recognize.**
    """
    app = _setup_picker()
    client = app.test_client()
    body = client.get("/1/auth/providers").get_json()
    by_name = {p["provider_name"]: p for p in body["providers"]}
    testbase.assert_equal(
        by_name["okta"]["login_path"], "/auth/oidc/okta/login",
    )
    testbase.assert_equal(
        by_name["local"]["login_path"], "/api/v1/auth/local/login",
    )
    return


def test_get_providers_carries_display_labels_for_ui():
    """
    **Feature: 1-authentication (M2)**
    **Property: each picker entry carries display_label so
    the UI can render the button text without a second
    lookup.**
    """
    app = _setup_picker()
    client = app.test_client()
    body = client.get("/1/auth/providers").get_json()
    by_name = {p["provider_name"]: p for p in body["providers"]}
    testbase.assert_equal(
        by_name["okta"]["display_label"], "Sign in with Okta",
    )
    testbase.assert_equal(
        by_name["local"]["display_label"], "Local password",
    )
    return


def test_get_providers_returns_empty_list_when_directory_is_empty():
    """
    **Feature: 1-authentication (M2)**
    **Property: with no registered credential modes the
    endpoint returns 200 with an empty providers list.**
    """
    provider_directory.reset_for_testing()
    reset_oidc_registry()
    app = Flask("p21b-empty")
    app.config["TESTING"] = True
    api = Api(app)
    for ns, path in auth_controller.publish_namespaces(
        version_prefix="/1",
    ):
        api.add_namespace(ns, path=path)
    response = app.test_client().get("/1/auth/providers")
    testbase.assert_equal(response.status_code, 200)
    testbase.assert_equal(response.get_json()["providers"], [])
    return


# -------------------------------------
# Webworks bridge — integration with check_authentication_with_roles
# -------------------------------------

def _build_app_with_bridge_and_webworks(
        *,
        engine,
        seated_session_id: str,
        seated_user_id: str,
        seated_roles: List[str]
    ) -> Flask:
    session_factory = sessionmaker(bind=engine)

    app = Flask("p21b-bridge")
    app.config["TESTING"] = True
    app.secret_key = "test-secret-key-p21b"

    # Set up webworks state — required by check_authentication_with_roles.
    route_security = RouteSecurityManager(app)
    route_security.add_api_prefix("/api/")
    route_security.add_public_endpoint("public_probe")
    route_security.add_public_endpoint("login")
    route_security.update_single_endpoints(
        "protected_probe", roles=["pychestrate.admin"],
    )
    BASE_SITE_SERVICE_STATE.ROUTE_SECURITY = route_security

    def _role_resolver(_db, user_id: str) -> List[str]:
        if user_id == seated_user_id:
            return list(seated_roles)
        return []

    def _user_profile_lookup(_db, user_id: str):
        if user_id != seated_user_id:
            return None
        rtnval = UserProfile(
            user_id=user_id,
            username="alice",
            display_name="Alice",
            email="alice@example.com",
        )
        return rtnval

    install_pychestrate_session_bridge(
        app=app,
        session_factory=session_factory,
        role_resolver=_role_resolver,
        user_profile_lookup=_user_profile_lookup,
    )
    # Webworks runs AFTER the bridge; the bridge populates
    # session['user'] so the enforcement hook decides on the
    # principal the cookie names.
    app.before_request(check_authentication_with_roles)

    @app.route("/api/probe/protected", endpoint="protected_probe")
    def _probe_protected():
        principal = flask_session.get("user", {})
        rtnval = jsonify({
            "user_id": principal.get("sub"),
            "roles": principal.get("roles", []),
            "session_id": principal.get("session_id"),
        })
        return rtnval

    @app.route("/api/probe/public", endpoint="public_probe")
    def _probe_public():
        principal = flask_session.get("user", None)
        rtnval = jsonify({
            "principal_present": principal is not None,
        })
        return rtnval

    @app.route("/login", endpoint="login")
    def _login():
        return "login-page"

    return app


def _seat_local_session(*, session, user_id: str) -> str:
    fingerprint = RequestFingerprint(
        ip_fingerprint="ip", user_agent_fingerprint="ua",
    )
    seated = open_session(
        db_session=session,
        user_id=user_id,
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
        mfa_method_name=None,
        access_token_payload=None,
        refresh_token_payload=None,
        request_fingerprint=fingerprint,
        idle_timeout_seconds=1800,
        max_lifetime_seconds=8 * 3600,
    )
    rtnval = str(seated.session_id)
    return rtnval


def test_webworks_bridge_lets_authenticated_request_through_to_protected_route():
    """
    **Feature: 1-authentication (M2)**
    **Property: with a seated auth_sessions row and the
    webworks bridge installed, a cookie-bearing request
    reaches a protected endpoint and webworks'
    check_authentication_with_roles authorizes it against
    the bridge-populated session['user'] roles.**
    """
    engine, db_session = build_in_memory_session()
    user_id = "11111111-1111-1111-1111-111111111111"
    cookie_value = _seat_local_session(
        session=db_session, user_id=user_id,
    )
    db_session.close()
    app = _build_app_with_bridge_and_webworks(
        engine=engine,
        seated_session_id=cookie_value,
        seated_user_id=user_id,
        seated_roles=["pychestrate.admin"],
    )
    client = app.test_client()
    client.set_cookie(
        SESSION_COOKIE_NAME, cookie_value, domain="localhost",
    )
    response = client.get("/api/probe/protected")
    testbase.assert_equal(response.status_code, 200)
    body = response.get_json()
    testbase.assert_equal(body["user_id"], user_id)
    testbase.assert_equal(body["session_id"], cookie_value)
    testbase.assert_equal(body["roles"], ["pychestrate.admin"])
    return


def test_webworks_bridge_returns_401_for_api_route_when_cookie_missing():
    """
    **Feature: 1-authentication (M2)**
    **Property: without the pychestrate_session cookie an
    API route returns 401 (webworks' API path) — the
    bridge clears any stale session['user'] so webworks
    enforces on the empty principal.**
    """
    engine, _db_session = build_in_memory_session()
    app = _build_app_with_bridge_and_webworks(
        engine=engine,
        seated_session_id="ignored",
        seated_user_id="ignored",
        seated_roles=[],
    )
    response = app.test_client().get("/api/probe/protected")
    testbase.assert_equal(response.status_code, 401)
    return


def test_webworks_bridge_returns_403_when_user_lacks_required_role():
    """
    **Feature: 1-authentication (M2)**
    **Property: with a seated session whose roles don't
    intersect the endpoint's allowed roles, webworks
    returns 403 — the bridge populated session['user']
    correctly but the principal is unauthorized.**
    """
    engine, db_session = build_in_memory_session()
    user_id = "22222222-2222-2222-2222-222222222222"
    cookie_value = _seat_local_session(
        session=db_session, user_id=user_id,
    )
    db_session.close()
    app = _build_app_with_bridge_and_webworks(
        engine=engine,
        seated_session_id=cookie_value,
        seated_user_id=user_id,
        seated_roles=["pychestrate.viewer"],  # NOT admin
    )
    client = app.test_client()
    client.set_cookie(
        SESSION_COOKIE_NAME, cookie_value, domain="localhost",
    )
    response = client.get("/api/probe/protected")
    testbase.assert_equal(response.status_code, 403)
    return


def test_webworks_bridge_lets_public_endpoint_through_without_cookie():
    """
    **Feature: 1-authentication (M2)**
    **Property: a public endpoint reachable without
    authentication still resolves through webworks because
    the bridge doesn't fail when the cookie is absent.**
    """
    engine, _db_session = build_in_memory_session()
    app = _build_app_with_bridge_and_webworks(
        engine=engine,
        seated_session_id="ignored",
        seated_user_id="ignored",
        seated_roles=[],
    )
    response = app.test_client().get("/api/probe/public")
    testbase.assert_equal(response.status_code, 200)
    testbase.assert_equal(
        response.get_json()["principal_present"], False,
    )
    return


def test_webworks_bridge_clears_stale_session_user_when_cookie_unrecognized():
    """
    **Feature: 1-authentication (M2)**
    **Property: a cookie carrying a session id that
    doesn't match any auth_sessions row results in
    session['user'] being cleared, so webworks treats the
    request as anonymous and returns 401 on protected API
    routes.**
    """
    engine, _db_session = build_in_memory_session()
    app = _build_app_with_bridge_and_webworks(
        engine=engine,
        seated_session_id="not-used",
        seated_user_id="not-used",
        seated_roles=["pychestrate.admin"],
    )
    client = app.test_client()
    client.set_cookie(
        SESSION_COOKIE_NAME,
        "00000000-0000-0000-0000-000000000000",
        domain="localhost",
    )
    response = client.get("/api/probe/protected")
    testbase.assert_equal(response.status_code, 401)
    return


def test_install_pychestrate_session_bridge_is_idempotent():
    """
    **Feature: 1-authentication (M2)**
    **Property: installing the bridge twice on the same
    Flask app doesn't double-register the before_request
    hook.**
    """
    engine, _ = build_in_memory_session()
    session_factory = sessionmaker(bind=engine)
    app = Flask("p21b-idempotent")
    app.secret_key = "x"
    install_pychestrate_session_bridge(
        app=app,
        session_factory=session_factory,
        role_resolver=lambda _db, _uid: [],
        user_profile_lookup=lambda _db, _uid: None,
    )
    install_pychestrate_session_bridge(
        app=app,
        session_factory=session_factory,
        role_resolver=lambda _db, _uid: [],
        user_profile_lookup=lambda _db, _uid: None,
    )
    testbase.assert_equal(
        getattr(app, "_pychestrate_webworks_bridge_installed"), True,
    )
    return
