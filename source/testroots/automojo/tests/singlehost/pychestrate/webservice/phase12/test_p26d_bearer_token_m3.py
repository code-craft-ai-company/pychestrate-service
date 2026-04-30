"""
.. module:: test_p26d_bearer_token_m3
    :synopsis: Tests for the BearerTokenMiddleware.

Drives a redeem → bearer-call round trip end-to-end:

1. Bootstrap admin + open the service.
2. Mint an enrollment token.
3. POST /api/v1/enrollment-tokens/redeem (public) and read back
   the bearer_token.
4. With the bearer attached as ``Authorization: Bearer <token>``,
   call a public endpoint and confirm ``request.auth`` is populated
   with an agent principal carrying the client's identity.
5. With a bogus bearer, confirm ``request.auth`` stays None (the
   middleware is silent on miss).
6. Confirm that when a cookie is also present, the cookie identity
   wins and the bearer is ignored.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import importlib.util
import json
import os
import tempfile

from typing import Optional, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.webworks.authentication.core import (
    AuthenticationContext,
    Principal,
)
from automojo.webworks.endpoints.descriptor import EndpointDescriptor
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse

from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (
    PychestrateApplication,
)
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.security.auth.pepper_loader import (
    reset_active_pepper_for_testing,
    set_active_pepper,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def _build_app() -> Tuple[PychestrateApplication, str]:
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p26d-test-pepper"))
    fd, path = tempfile.mkstemp(prefix="pych_p26d_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
    )
    return app, path


def _import_bootstrap_module():
    repo_root = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", "..", "..", "..", "..", "..",
        ),
    )
    spec = importlib.util.spec_from_file_location(
        "scripts_bootstrapadmin",
        os.path.join(repo_root, "scripts", "bootstrapadmin.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CAPTURE_KEY = "captured_auth"


def _install_capture_endpoint(*, app, captured) -> None:
    """
        Register a one-off endpoint at /probe that stashes
        request.auth into ``captured`` so the test can assert on it
        without reaching for handler internals.
    """
    def _probe(request: Request) -> JSONResponse:
        captured[_CAPTURE_KEY] = getattr(request, "auth", None)
        return JSONResponse(content={"ok": True}, status_code=200)

    descriptor = EndpointDescriptor(
        handler=_probe,
        module=__name__,
        leaf=None,
        path="/probe",
        methods=["GET"],
    )
    app.router.add_endpoint(descriptor=descriptor)
    return


def _seed_admin_and_redeem_bearer(*, app, db_path) -> Tuple[str, str]:
    """
        Run bootstrapadmin against the engine to register an admin +
        cookie, then mint an enrollment token via the cookie path
        and redeem it to obtain a bearer. Returns
        ``(admin_cookie, bearer_token)``.
    """
    bootstrap = _import_bootstrap_module()
    factory = app.flow_runtime._session_factory

    db_session = factory()
    try:
        bootstrap._sync_role_catalog(db_session=db_session)
        user_id = bootstrap._ensure_user(
            db_session=db_session,
            login_name="admin-26d",
            primary_email="admin-26d@example.com",
            display_name="Admin",
            timezone_name="UTC",
        )
        bootstrap._ensure_admin_binding(
            db_session=db_session, user_id=user_id,
        )
        bootstrap._ensure_local_password(
            db_session=db_session,
            user_id=user_id,
            password="ChangeMe!",
        )
        admin_cookie = bootstrap._open_admin_session(
            db_session=db_session, user_id=user_id,
        )
        db_session.commit()

        # Build a project to anchor the enrollment token.
        from automojo.pychestrate.webservice.projects import service as ps
        project = ps.create_project(
            db_session=db_session,
            slug="lab",
            display_name="Lab",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=user_id,
        )
        project_id = str(project.project_id)

        from automojo.pychestrate.webservice.clients.enrollment.service import (
            issue_enrollment_token,
        )
        issued = issue_enrollment_token(
            db_session=db_session,
            project_id=project_id,
            pod_name="raspi-01",
            ttl_seconds=600,
            one_shot=False,
            issued_by=user_id,
        )
        db_session.commit()
        secret = issued.secret
    finally:
        db_session.close()

    # Redeem via the public endpoint to mint a bearer.
    redeem_request = Request(
        method="POST",
        path="/api/v1/enrollment-tokens/redeem",
        headers={"Content-Type": "application/json"},
        body=json.dumps({
            "secret": secret,
            "pod_name": "raspi-01",
            "agent_version": "1.0.0",
            "transport_name": "http",
        }).encode("utf-8"),
    )
    redeem_response = app.dispatcher.dispatch(request=redeem_request)
    testbase.assert_equal(redeem_response.status_code, 200)
    bearer_token = json.loads(redeem_response.body.decode())["bearer_token"]
    return admin_cookie, bearer_token


def test_valid_bearer_populates_agent_principal_on_request_auth():
    """
    **Feature: P26d bearer-token middleware (M3)**
    **Property: With Authorization: Bearer <token>, the middleware
    resolves the token to a Client row and attaches an
    AuthenticationContext whose principal carries the agent role
    and the client's pod_name + project_id.**
    """
    app, db_path = _build_app()
    captured = {}
    _install_capture_endpoint(app=app, captured=captured)
    try:
        _admin_cookie, bearer = _seed_admin_and_redeem_bearer(
            app=app, db_path=db_path,
        )
        request = Request(
            method="GET",
            path="/probe",
            headers={"Authorization": "Bearer {0}".format(bearer)},
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 200)

        context = captured[_CAPTURE_KEY]
        testbase.assert_equal(context is None, False)
        testbase.assert_equal(context.scheme, "bearer-client")
        testbase.assert_equal("agent" in context.principal.roles, True)
        testbase.assert_equal(
            context.principal.display_name, "agent:raspi-01",
        )
        testbase.assert_equal(
            context.attributes.get("pod_name"), "raspi-01",
        )
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(db_path)
    return


def test_unknown_bearer_leaves_request_auth_anonymous():
    """
    **Feature: P26d bearer-token middleware (M3)**
    **Property: A bogus bearer token leaves request.auth as None
    (the middleware is silent on miss; AccessPolicy still applies).**
    """
    app, db_path = _build_app()
    captured = {}
    _install_capture_endpoint(app=app, captured=captured)
    try:
        request = Request(
            method="GET",
            path="/probe",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(captured[_CAPTURE_KEY] is None, True)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(db_path)
    return


def test_cookie_identity_wins_over_bearer_when_both_present():
    """
    **Feature: P26d bearer-token middleware (M3)**
    **Property: A request that carries both a session cookie AND
    an Authorization: Bearer header keeps the cookie identity. The
    BearerTokenMiddleware respects the existing request.auth set
    upstream by PychestrateSessionMiddleware.**
    """
    app, db_path = _build_app()
    captured = {}
    _install_capture_endpoint(app=app, captured=captured)
    # Pre-inject a synthetic cookie context (skip the cookie-resolve
    # round trip; we just want to verify the bearer middleware
    # respects the existing value).
    pre_set_context = AuthenticationContext(
        principal=Principal(
            identifier="00000000-0000-4000-8000-000000d000",
            display_name="cookie-user",
            roles={"system-admin"},
        ),
        scheme="pychestrate-session",
    )
    original = app.dispatcher.dispatch

    def _wrapped(*, request):
        request.auth = pre_set_context
        rtnval = original(request=request)
        return rtnval

    app.dispatcher.dispatch = _wrapped

    try:
        _admin_cookie, bearer = _seed_admin_and_redeem_bearer(
            app=app, db_path=db_path,
        )
        # Reset the pre-injected hook so the bearer call gets the
        # cookie-context applied.
        request = Request(
            method="GET",
            path="/probe",
            headers={"Authorization": "Bearer {0}".format(bearer)},
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 200)

        context = captured[_CAPTURE_KEY]
        testbase.assert_equal(context is None, False)
        testbase.assert_equal(context.scheme, "pychestrate-session")
        testbase.assert_equal(
            context.principal.display_name, "cookie-user",
        )
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(db_path)
    return
