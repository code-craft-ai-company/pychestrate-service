"""
.. module:: test_p24a_authblueprint_webworks_m3
    :synopsis: Tests for P24a — authblueprint migrated to webworks.

This module is the **worked-example test** for the P24a Flask →
automojo-webworks migration. It exercises the migrated
:class:`AuthBlueprint` end-to-end through the webworks dispatcher and
the :class:`DbSessionMiddleware`, and demonstrates the in-process
``TestClient`` substitute for the legacy Flask ``app.test_client()``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timezone
from typing import Dict, Tuple

from automojo import testbase

from automojo.webworks.devexp.testing.testclient import TestClient
from automojo.webworks.routing.dispatcher import Dispatcher
from automojo.webworks.routing.middleware import MiddlewarePipeline
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import Response
from automojo.webworks.routing.router import Router

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.middleware_webworks import (
    DbSessionMiddleware,
)
from automojo.pychestrate.webservice.security.auth import session_service
from automojo.pychestrate.webservice.security.auth.exceptions import (
    SessionNotFoundError,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
)
from automojo.pychestrate.webservice.security.auth.restapi.v1 import (
    authblueprint,
)
from automojo.pychestrate.webservice.security.auth.session_service import (
    RequestFingerprint,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


def _build_app_callable(
        *,
        engine,
        install_db_session_middleware: bool = True,
    ):
    """
        Build the ``(method, path, headers, body) -> (status, headers,
        body)`` callable that :class:`TestClient` consumes.

        Each call constructs a fresh :class:`Request`, dispatches it
        through a :class:`MiddlewarePipeline` that — by default —
        installs :class:`DbSessionMiddleware` bound to the supplied
        in-memory engine, and serializes the resulting
        :class:`Response`.

        :param engine: The SQLAlchemy engine the session factory binds
                       against.
        :param install_db_session_middleware: When True (default) the
                       db-session middleware is installed in the
                       pipeline. Pass False to validate the controller's
                       503 fallback when the middleware is absent.

        :returns: A callable matching the
                  :class:`automojo.webworks.devexp.testing.testclient.TestClient`
                  protocol.
    """
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=engine)

    router = Router()
    authblueprint.AuthBlueprint.register(router=router)

    pipeline = MiddlewarePipeline()
    if install_db_session_middleware is True:
        middleware = DbSessionMiddleware(session_factory=session_factory)
        pipeline.add(middleware=middleware, name=middleware.name)

    dispatcher = Dispatcher(router=router, pipeline=pipeline)

    def _app_callable(
            method: str,
            path: str,
            headers: Dict[str, str],
            body: bytes,
        ) -> Tuple[int, Dict[str, str], bytes]:
        if "?" in path:
            path_only, _, query_string_str = path.partition("?")
        else:
            path_only = path
            query_string_str = ""
        request = Request(
            method=method,
            path=path_only,
            query_string=query_string_str.encode("utf-8"),
            headers=headers,
            body=body,
        )
        response = dispatcher.dispatch(request=request)
        rtnval = (response.status_code, dict(response.headers), response.body)
        return rtnval

    return _app_callable


def _seed_session(*, session) -> str:
    """
        Open a session row via :func:`session_service.open_session` so
        the logout endpoint has something to close.

        :param session: The SQLAlchemy session to write through.

        :returns: The new session id.
    """
    seated = session_service.open_session(
        db_session=session,
        user_id=new_uuid(),
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


def _setup() -> Tuple[object, object]:
    """
        Reset phase-1 runtime singletons and build a fresh in-memory
        engine + session.

        :returns: Tuple of ``(engine, session)``.
    """
    reset_phase1_runtime()
    engine, session = build_in_memory_session()
    rtnval = (engine, session)
    return rtnval


# -------------------------------------
# logout — happy path through the pipeline
# -------------------------------------

def test_logout_endpoint_closes_session_via_db_session_middleware():
    """
    **Feature: P24a webworks migration (M3)**
    **Property: POST /api/v1/auth/logout dispatched through the
    webworks pipeline closes the session row, with the request-scoped
    db_session supplied by DbSessionMiddleware.**
    """
    engine, session = _setup()
    try:
        session_id = _seed_session(session=session)
        session.commit()

        app_callable = _build_app_callable(engine=engine)
        client = TestClient(app=app_callable)

        response = client.post(
            path="/api/v1/auth/logout",
            json={"session_id": session_id},
        )

        testbase.assert_equal(response.status_code, 200)
        body = json.loads(response.body.decode("utf-8"))
        testbase.assert_equal(body["session_id"], session_id)
        testbase.assert_equal(body["status"], "closed")

        raised = False
        try:
            session_service.resolve_session(
                db_session=session,
                session_id=session_id,
                now=datetime.now(tz=timezone.utc),
            )
        except SessionNotFoundError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        session.close()
    return


# -------------------------------------
# logout — 503 when middleware is absent
# -------------------------------------

def test_logout_endpoint_returns_503_when_db_session_missing():
    """
    **Feature: P24a webworks migration (M3)**
    **Property: When DbSessionMiddleware is not installed, the
    controller raises HTTPException(503) which the dispatcher renders
    as a JSON body with detail and status_code fields.**
    """
    engine, session = _setup()
    try:
        app_callable = _build_app_callable(
            engine=engine, install_db_session_middleware=False,
        )
        client = TestClient(app=app_callable)

        response = client.post(
            path="/api/v1/auth/logout",
            json={"session_id": "anything"},
        )

        testbase.assert_equal(response.status_code, 503)
        body = json.loads(response.body.decode("utf-8"))
        testbase.assert_equal(body["status_code"], 503)
        detail = body["detail"]
        testbase.assert_equal(
            "db_session" in detail.lower(), True,
        )
    finally:
        session.close()
    return


# -------------------------------------
# logout — body validation
# -------------------------------------

def test_logout_endpoint_rejects_empty_body_with_400():
    """
    **Feature: P24a webworks migration (M3)**
    **Property: A logout request with an empty body returns 400, not
    a 500, so the JSON validation in the controller is preserved
    across the migration.**
    """
    engine, session = _setup()
    try:
        app_callable = _build_app_callable(engine=engine)
        client = TestClient(app=app_callable)

        response = client.post(path="/api/v1/auth/logout")

        testbase.assert_equal(response.status_code, 400)
    finally:
        session.close()
    return


# -------------------------------------
# routing — path parameters
# -------------------------------------

def test_unknown_provider_kind_path_param_returns_404():
    """
    **Feature: P24a webworks migration (M3)**
    **Property: Path parameters are routed correctly through the
    webworks Router; an unknown ``kind`` segment surfaces the
    controller's 404 (not a router 404), confirming the route
    matched and ``request.path_params`` was populated.**
    """
    engine, session = _setup()
    try:
        app_callable = _build_app_callable(engine=engine)
        client = TestClient(app=app_callable)

        response = client.post(
            path="/api/v1/auth/providers/notakind/somename/enable",
        )

        testbase.assert_equal(response.status_code, 404)
        body = json.loads(response.body.decode("utf-8"))
        testbase.assert_equal(body["detail"], "kind_unknown")
    finally:
        session.close()
    return
