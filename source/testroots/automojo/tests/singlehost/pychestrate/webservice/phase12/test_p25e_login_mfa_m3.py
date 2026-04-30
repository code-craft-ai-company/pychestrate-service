"""
.. module:: test_p25e_login_mfa_m3
    :synopsis: Tests for the MFA second-factor flow on POST /api/v1/auth/login.

When the user has any verified MFA enrollment the login endpoint
runs in two stages:

1. POST /auth/login with ``{login_name, password}`` — credentials
   verify but no Set-Cookie is emitted; the response carries
   ``mfa_required=true`` plus a fresh ``challenge_id``.
2. POST /auth/login with ``{login_name, password, challenge_id,
   mfa_code}`` — both factors are checked; the session is opened
   and the Set-Cookie header is emitted.

This test seeds a TOTP enrollment for an admin user via
:mod:`mfa_service`, drives the two-stage flow against the running
:class:`PychestrateApplication`, and asserts each stage's response
shape.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import hmac
import importlib.util
import json
import os
import struct
import tempfile

from datetime import datetime, timezone
from typing import Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.webworks.routing.request import Request

from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (
    PychestrateApplication,
)
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.security.auth import mfa_service
from automojo.pychestrate.webservice.security.auth.cookies import (
    SESSION_COOKIE_NAME,
)
from automojo.pychestrate.webservice.security.auth.factories.totp_mfa import (
    TOTP_DIGITS,
    TOTP_PERIOD_SECONDS,
    TotpMfaMethod,
)
from automojo.pychestrate.webservice.security.auth.local_flow import (
    reset_backoff_for_testing,
)
from automojo.pychestrate.webservice.security.auth.pepper_loader import (
    reset_active_pepper_for_testing,
    set_active_pepper,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


_LOGIN_NAME = "alice-mfa"
_LOGIN_PASSWORD = "MfaSecret!42"
_LOGIN_EMAIL = "alice-mfa@example.com"


def _live_totp(*, secret_bytes: bytes) -> str:
    """
        Compute the current TOTP code for ``secret_bytes`` (RFC 6238).
    """
    epoch_seconds = int(datetime.now(timezone.utc).timestamp())
    step = epoch_seconds // TOTP_PERIOD_SECONDS
    counter_bytes = struct.pack(">Q", step)
    digest = hmac.new(
        key=secret_bytes, msg=counter_bytes, digestmod=hashlib.sha1,
    ).digest()
    offset = digest[-1] & 0x0F
    truncated = (
        ((digest[offset] & 0x7F) << 24)
        | ((digest[offset + 1] & 0xFF) << 16)
        | ((digest[offset + 2] & 0xFF) << 8)
        | (digest[offset + 3] & 0xFF)
    )
    code = truncated % (10 ** TOTP_DIGITS)
    rtnval = str(code).zfill(TOTP_DIGITS)
    return rtnval


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


def _build_app_with_mfa_user() -> Tuple[PychestrateApplication, str, str, bytes]:
    """
        Boot a fresh app, seed a user with local credentials, enroll
        TOTP, and confirm the enrollment so it counts as 'verified'.

        :returns: ``(app, db_path, user_id, totp_secret_bytes)``.
    """
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p25e-test-pepper"))
    reset_backoff_for_testing()
    mfa_service.reset_for_testing()

    fd, db_path = tempfile.mkstemp(prefix="pych_p25e_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(db_path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
    )

    bootstrap = _import_bootstrap_module()
    db_session = factory()
    try:
        bootstrap._sync_role_catalog(db_session=db_session)
        user_id = bootstrap._ensure_user(
            db_session=db_session,
            login_name=_LOGIN_NAME,
            primary_email=_LOGIN_EMAIL,
            display_name="Alice MFA",
            timezone_name="UTC",
        )
        bootstrap._ensure_admin_binding(
            db_session=db_session, user_id=user_id,
        )
        bootstrap._ensure_local_password(
            db_session=db_session,
            user_id=user_id,
            password=_LOGIN_PASSWORD,
        )

        # Enroll + confirm TOTP so the user has a verified MFA method.
        enrollment = mfa_service.enroll_method(
            db_session=db_session,
            user_id=user_id,
            method_name=TotpMfaMethod.method_name,
            account_name=_LOGIN_NAME,
            actor_user_id=user_id,
        )
        secret_bytes = enrollment.secret_payload
        confirmation_code = _live_totp(secret_bytes=secret_bytes)
        mfa_service.confirm_enrollment(
            db_session=db_session,
            enrollment_id=enrollment.enrollment_id,
            response_fields={"code": confirmation_code},
        )
        db_session.commit()
    finally:
        db_session.close()

    return app, db_path, user_id, secret_bytes


def test_login_first_stage_returns_mfa_required_with_challenge():
    """
    **Feature: P25e MFA login flow (M3)**
    **Property: For a user with a verified TOTP enrollment, the
    first /auth/login call (creds only) returns 200 with
    mfa_required=true, a challenge_id, the method_name, and an
    expires_at timestamp. No Set-Cookie header is emitted.**
    """
    app, db_path, user_id, _secret = _build_app_with_mfa_user()
    try:
        request = Request(
            method="POST",
            path="/api/v1/auth/login",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "login_name": _LOGIN_NAME,
                "password": _LOGIN_PASSWORD,
            }).encode("utf-8"),
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 200)

        body = json.loads(response.body.decode("utf-8"))
        testbase.assert_equal(body.get("mfa_required"), True)
        testbase.assert_equal(body.get("user_id"), user_id)
        testbase.assert_equal(
            body.get("method_name"), TotpMfaMethod.method_name,
        )
        testbase.assert_equal(
            isinstance(body.get("challenge_id"), str), True,
        )
        testbase.assert_equal(len(body["challenge_id"]) > 0, True)
        testbase.assert_equal(
            isinstance(body.get("expires_at"), str), True,
        )

        # No Set-Cookie until the second factor is verified.
        for header_name in response.headers.keys():
            testbase.assert_equal(
                header_name.lower() != "set-cookie", True,
            )
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(db_path)
    return


def test_login_second_stage_with_valid_totp_emits_set_cookie():
    """
    **Feature: P25e MFA login flow (M3)**
    **Property: After receiving the first-stage response, posting
    creds + challenge_id + the live TOTP code returns 200 with a
    Set-Cookie header carrying the session id.**
    """
    app, db_path, user_id, secret_bytes = _build_app_with_mfa_user()
    try:
        first = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/auth/login",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "login_name": _LOGIN_NAME,
                "password": _LOGIN_PASSWORD,
            }).encode("utf-8"),
        ))
        challenge_id = json.loads(first.body.decode("utf-8"))["challenge_id"]

        code = _live_totp(secret_bytes=secret_bytes)
        second = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/auth/login",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "login_name": _LOGIN_NAME,
                "password": _LOGIN_PASSWORD,
                "challenge_id": challenge_id,
                "mfa_code": code,
            }).encode("utf-8"),
        ))
        testbase.assert_equal(second.status_code, 200)

        body = json.loads(second.body.decode("utf-8"))
        testbase.assert_equal(body.get("user_id"), user_id)
        testbase.assert_equal(
            isinstance(body.get("session_id"), str), True,
        )

        set_cookie = None
        for header_name, header_value in second.headers.items():
            if header_name.lower() == "set-cookie":
                set_cookie = header_value
                break
        testbase.assert_equal(set_cookie is not None, True)
        testbase.assert_equal(
            set_cookie.startswith("{0}=".format(SESSION_COOKIE_NAME)),
            True,
        )
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(db_path)
    return


def test_login_second_stage_with_wrong_totp_returns_401():
    """
    **Feature: P25e MFA login flow (M3)**
    **Property: A wrong mfa_code on the second stage returns 401.**
    """
    app, db_path, _user_id, _secret = _build_app_with_mfa_user()
    try:
        first = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/auth/login",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "login_name": _LOGIN_NAME,
                "password": _LOGIN_PASSWORD,
            }).encode("utf-8"),
        ))
        challenge_id = json.loads(first.body.decode("utf-8"))["challenge_id"]

        second = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/auth/login",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "login_name": _LOGIN_NAME,
                "password": _LOGIN_PASSWORD,
                "challenge_id": challenge_id,
                "mfa_code": "000000",
            }).encode("utf-8"),
        ))
        testbase.assert_equal(second.status_code, 401)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(db_path)
    return
