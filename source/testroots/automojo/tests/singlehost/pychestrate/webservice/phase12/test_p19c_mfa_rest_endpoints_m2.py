"""
.. module:: test_p19c_mfa_rest_endpoints_m2
    :synopsis: Tests for P19c — 1-authentication M2 MFA REST endpoints.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import hmac
import struct

from datetime import datetime, timezone
from typing import Any, Mapping

from flask import Flask, g
from flask_restx import Api
from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.security.auth import mfa_service
from automojo.pychestrate.webservice.security.auth.factories.totp_mfa import (
    TOTP_DIGITS,
    TOTP_PERIOD_SECONDS,
    TotpMfaMethod,
)
from automojo.pychestrate.webservice.security.auth.restapi.v1 import (
    auth_controller,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
    session_for,
)


def _build_app(*, engine) -> Flask:
    """
        Build a minimal Flask app that wires the auth namespace
        and a per-request g.db_session attached from the
        in-memory SQLite engine.
    """
    session_factory = sessionmaker(bind=engine)

    app = Flask("p19c-mfa-test")
    app.config["TESTING"] = True
    app.config["RESTX_MASK_SWAGGER"] = False

    @app.before_request
    def _attach_session():
        g.db_session = session_factory()
        return None

    @app.teardown_request
    def _close_session(_exc):
        db_session = getattr(g, "db_session", None)
        if db_session is not None:
            db_session.close()
        return None

    api = Api(app)
    for ns, path in auth_controller.publish_namespaces(version_prefix="/1"):
        api.add_namespace(ns, path=path)
    return app


def _enroll_and_confirm(
        *, session, user_id: str
    ) -> bytes:
    """
        Drive enrollment + confirmation through the
        mfa_service so the (user, totp) row is verified and
        ready to challenge against. Returns the raw secret
        bytes for the test to mint live TOTP codes against.
    """
    bootstrap = mfa_service.enroll_method(
        db_session=session,
        user_id=user_id,
        method_name=TotpMfaMethod.method_name,
        account_name="alice@example.com",
    )
    code = _live_totp(secret_bytes=bootstrap.secret_payload)
    mfa_service.confirm_enrollment(
        db_session=session,
        enrollment_id=bootstrap.enrollment_id,
        response_fields={"code": code},
    )
    rtnval = bootstrap.secret_payload
    return rtnval


def _live_totp(*, secret_bytes: bytes) -> str:
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


def _setup() -> tuple:
    reset_phase1_runtime()
    mfa_service.reset_for_testing()
    engine, session = build_in_memory_session()
    user_id = new_uuid()
    secret = _enroll_and_confirm(session=session, user_id=user_id)
    session.close()
    app = _build_app(engine=engine)
    rtnval = (app, engine, user_id, secret)
    return rtnval


# -------------------------------------
# /auth/mfa/challenge happy path
# -------------------------------------

def test_post_mfa_challenge_returns_201_with_challenge_bundle():
    """
    **Feature: 1-authentication (M2)**
    **Property: POST /api/v1/auth/mfa/challenge issues a
    challenge for the (user, method) row and returns 201
    with challenge_id / issued_at / expires_at / payload.**
    """
    app, _engine, user_id, _secret = _setup()
    client = app.test_client()
    response = client.post(
        "/1/auth/mfa/challenge",
        json={"user_id": user_id, "method_name": "totp"},
    )
    testbase.assert_equal(response.status_code, 201)
    body = response.get_json()
    testbase.assert_equal(body["user_id"], user_id)
    testbase.assert_equal(body["method_name"], "totp")
    testbase.assert_equal(len(body["challenge_id"]) > 0, True)
    testbase.assert_equal(
        body["payload"]["digits"], TOTP_DIGITS,
    )
    testbase.assert_equal(
        body["payload"]["period_seconds"], TOTP_PERIOD_SECONDS,
    )
    return


def test_post_mfa_challenge_404_when_method_unknown():
    """
    **Feature: 1-authentication (M2)**
    **Property: POST /auth/mfa/challenge returns 404 when
    no MFAMethodExtension is registered for method_name.**
    """
    app, _engine, user_id, _secret = _setup()
    client = app.test_client()
    response = client.post(
        "/1/auth/mfa/challenge",
        json={"user_id": user_id, "method_name": "made-up-method"},
    )
    testbase.assert_equal(response.status_code, 404)
    return


def test_post_mfa_challenge_404_when_enrollment_missing():
    """
    **Feature: 1-authentication (M2)**
    **Property: POST /auth/mfa/challenge returns 404 when
    the user has no enrollment for the requested method.**
    """
    app, _engine, _user_id, _secret = _setup()
    client = app.test_client()
    other_user = new_uuid()
    response = client.post(
        "/1/auth/mfa/challenge",
        json={"user_id": other_user, "method_name": "totp"},
    )
    testbase.assert_equal(response.status_code, 404)
    return


def test_post_mfa_challenge_400_when_user_id_empty():
    """
    **Feature: 1-authentication (M2)**
    **Property: POST /auth/mfa/challenge returns 400 when
    user_id is empty so the controller refuses to look up
    a half-shaped row.**
    """
    app, _engine, _user_id, _secret = _setup()
    client = app.test_client()
    response = client.post(
        "/1/auth/mfa/challenge",
        json={"user_id": "", "method_name": "totp"},
    )
    testbase.assert_equal(response.status_code, 400)
    return


# -------------------------------------
# /auth/mfa/verify happy path
# -------------------------------------

def test_post_mfa_verify_accepts_correct_code_and_returns_200():
    """
    **Feature: 1-authentication (M2)**
    **Property: POST /api/v1/auth/mfa/verify with the right
    TOTP code returns 200 and accepted=True.**
    """
    app, _engine, user_id, secret = _setup()
    client = app.test_client()
    challenge_response = client.post(
        "/1/auth/mfa/challenge",
        json={"user_id": user_id, "method_name": "totp"},
    )
    challenge_id = challenge_response.get_json()["challenge_id"]
    code = _live_totp(secret_bytes=secret)
    verify_response = client.post(
        "/1/auth/mfa/verify",
        json={"challenge_id": challenge_id, "response": {"code": code}},
    )
    testbase.assert_equal(verify_response.status_code, 200)
    body = verify_response.get_json()
    testbase.assert_equal(body["accepted"], True)
    testbase.assert_equal(body["challenge_id"], challenge_id)
    return


def test_post_mfa_verify_401_on_bad_code():
    """
    **Feature: 1-authentication (M2)**
    **Property: POST /auth/mfa/verify with a wrong code
    returns 401 with reason=challenge_rejected.**
    """
    app, _engine, user_id, _secret = _setup()
    client = app.test_client()
    challenge_response = client.post(
        "/1/auth/mfa/challenge",
        json={"user_id": user_id, "method_name": "totp"},
    )
    challenge_id = challenge_response.get_json()["challenge_id"]
    verify_response = client.post(
        "/1/auth/mfa/verify",
        json={"challenge_id": challenge_id, "response": {"code": "000000"}},
    )
    testbase.assert_equal(verify_response.status_code, 401)
    return


def test_post_mfa_verify_404_on_unknown_challenge_id():
    """
    **Feature: 1-authentication (M2)**
    **Property: POST /auth/mfa/verify against an unknown
    challenge_id returns 404 (the active-challenge store
    pop is single-use; a forged or already-consumed id
    misses).**
    """
    app, _engine, _user_id, _secret = _setup()
    client = app.test_client()
    verify_response = client.post(
        "/1/auth/mfa/verify",
        json={
            "challenge_id": "not-a-real-id",
            "response": {"code": "123456"},
        },
    )
    testbase.assert_equal(verify_response.status_code, 404)
    return


def test_post_mfa_verify_consumes_challenge_so_replay_misses():
    """
    **Feature: 1-authentication (M2)**
    **Property: a successful verify consumes the challenge,
    so a follow-up verify with the same id returns 404.**
    """
    app, _engine, user_id, secret = _setup()
    client = app.test_client()
    challenge_response = client.post(
        "/1/auth/mfa/challenge",
        json={"user_id": user_id, "method_name": "totp"},
    )
    challenge_id = challenge_response.get_json()["challenge_id"]
    code = _live_totp(secret_bytes=secret)
    first = client.post(
        "/1/auth/mfa/verify",
        json={"challenge_id": challenge_id, "response": {"code": code}},
    )
    second = client.post(
        "/1/auth/mfa/verify",
        json={"challenge_id": challenge_id, "response": {"code": code}},
    )
    testbase.assert_equal(first.status_code, 200)
    testbase.assert_equal(second.status_code, 404)
    return


def test_post_mfa_verify_400_when_response_is_not_object():
    """
    **Feature: 1-authentication (M2)**
    **Property: POST /auth/mfa/verify returns 400 when the
    response field isn't a JSON object.**
    """
    app, _engine, user_id, _secret = _setup()
    client = app.test_client()
    challenge_response = client.post(
        "/1/auth/mfa/challenge",
        json={"user_id": user_id, "method_name": "totp"},
    )
    challenge_id = challenge_response.get_json()["challenge_id"]
    verify_response = client.post(
        "/1/auth/mfa/verify",
        json={"challenge_id": challenge_id, "response": "not-an-object"},
    )
    testbase.assert_equal(verify_response.status_code, 400)
    return


# -------------------------------------
# Namespace publication
# -------------------------------------

def test_publish_namespaces_returns_versioned_path():
    """
    **Feature: 1-authentication (M2)**
    **Property: publish_namespaces returns the auth
    namespace mapped to the given version prefix so the
    main API wiring can hand it to flask_restx.Api.**
    """
    pairs = auth_controller.publish_namespaces(version_prefix="/1")
    testbase.assert_equal(len(pairs), 1)
    namespace, path = pairs[0]
    testbase.assert_equal(path, "/1/auth")
    testbase.assert_equal(namespace is auth_controller.auth_ns, True)
    return
