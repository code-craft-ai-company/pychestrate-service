"""
.. module:: test_p26b_auth_admin_gates_m3
    :synopsis: Confirms /auth/providers/.../{enable,disable} are gated.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


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
from automojo.webworks.routing.request import Request

from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (
    PychestrateApplication,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def _build_app() -> Tuple[PychestrateApplication, str]:
    reset_phase1_runtime()
    fd, path = tempfile.mkstemp(prefix="pych_p26b_", suffix=".db")
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


def _wrap_with_auth(
        *,
        app: PychestrateApplication,
        context: Optional[AuthenticationContext],
    ) -> None:
    original = app.dispatcher.dispatch

    def _wrapped(*, request):
        request.auth = context
        rtnval = original(request=request)
        return rtnval

    app.dispatcher.dispatch = _wrapped
    return


def test_anonymous_provider_enable_returns_401():
    """
    **Feature: P26b auth admin gates (M3)**
    **Property: POST /api/v1/auth/providers/{kind}/{name}/enable
    rejects anonymous requests with HTTP 401.**
    """
    app, path = _build_app()
    _wrap_with_auth(app=app, context=None)
    try:
        request = Request(
            method="POST",
            path="/api/v1/auth/providers/local/local/enable",
            headers={"Content-Type": "application/json"},
            body=b"",
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 401)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_anonymous_provider_disable_returns_401():
    """
    **Feature: P26b auth admin gates (M3)**
    **Property: POST /api/v1/auth/providers/{kind}/{name}/disable
    rejects anonymous requests with HTTP 401.**
    """
    app, path = _build_app()
    _wrap_with_auth(app=app, context=None)
    try:
        request = Request(
            method="POST",
            path="/api/v1/auth/providers/local/local/disable",
            headers={"Content-Type": "application/json"},
            body=b"",
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 401)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_admin_provider_enable_clears_the_gate():
    """
    **Feature: P26b auth admin gates (M3)**
    **Property: With a system-admin context attached, POST
    /api/v1/auth/providers/.../enable dispatches PAST the gate
    (response is 4xx for 'kind_unknown' / 'mode_not_registered'
    rather than 401/403).**
    """
    admin = AuthenticationContext(
        principal=Principal(
            identifier="00000000-0000-4000-8000-00000000a900",
            display_name="Test Admin",
            roles={"system-admin"},
        ),
        scheme="test-injection",
    )
    app, path = _build_app()
    _wrap_with_auth(app=app, context=admin)
    try:
        request = Request(
            method="POST",
            path="/api/v1/auth/providers/local/local/enable",
            headers={"Content-Type": "application/json"},
            body=b"",
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code != 401, True)
        testbase.assert_equal(response.status_code != 403, True)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return
