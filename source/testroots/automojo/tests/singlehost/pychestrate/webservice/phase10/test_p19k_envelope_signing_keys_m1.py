"""
.. module:: test_p19k_envelope_signing_keys_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the /api/v1/envelope-signing-keys JWKS endpoint.

.. moduleauthor:: Automation Mojo LLC

Covers the p19k envelope-signing-key distribution surface:

* route registration (one GET pair),
* 401 for an anonymous request,
* 503 when no signing key is provisioned,
* 200 with the JWKS-style key set,
* the exposed PEM parses as a valid Ed25519 public key,
* round-trip: a signature produced by the in-process signer
  verifies against the exposed public key,
* the cookie / API-key principal path AND the mTLS path both
  satisfy the auth gate,
* bootstrap source-smoke.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os

from typing import Any, Callable, Dict, List, Optional, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)

from automojo import testbase

from automojo.pychestrate.webservice.api.problem_json import (
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_UNAUTHENTICATED,
)
from automojo.pychestrate.webservice.jobs.envelope import signer
from automojo.pychestrate.webservice.jobs.envelope import startup as envelope_startup
from automojo.pychestrate.webservice.jobs.envelope.restapi.v1 import (
    signing_keys_routes,
)


# ---------------------------------------------------------------------------
# Test stubs
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(
        self,
        *,
        path: str = "/api/v1/envelope-signing-keys",
        auth_principal: Optional[Any] = None,
        mtls_client_cn: Optional[str] = None,
    ) -> None:
        self.path: str = path
        self.auth_principal: Optional[Any] = auth_principal
        self.mtls_client_cn: Optional[str] = mtls_client_cn
        return


class _FakeApp:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, Tuple[str, ...], Callable]] = []
        return

    def attach_route(
        self, path: str, methods: Optional[List[str]] = None
    ) -> Callable:
        resolved_methods = tuple(methods if methods is not None else ["GET"])

        def decorator(func: Callable) -> Callable:
            self.calls.append((path, resolved_methods, func))
            rtnval = func
            return rtnval

        rtnval = decorator
        return rtnval


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_signing_keys_routes_attaches_one_get_route():
    """
    **Feature: p19k expose-envelope-signing-key**
    **Property: register_signing_keys_routes attaches a single
    ``GET /api/v1/envelope-signing-keys`` route.**
    """
    app = _FakeApp()
    signing_keys_routes.register_signing_keys_routes(
        app=app, version_prefix="/api/v1"
    )

    expected = (("/api/v1/envelope-signing-keys", ("GET",)),)
    actual = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual, expected)
    return


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------


def test_handle_returns_401_for_anonymous_request():
    """
    **Feature: p19k expose-envelope-signing-key**
    **Property: An unauthenticated request (no cookie / API-key
    principal and no mTLS cert) returns 401 problem+json.**
    """
    signer.reset_for_testing()
    request = _FakeRequest()
    response = signing_keys_routes.handle_list_envelope_signing_keys(request)
    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_handle_accepts_cookie_or_api_key_principal():
    """
    **Feature: p19k expose-envelope-signing-key**
    **Property: A request carrying an auth_principal (resolved from
    the cookie session or API key) satisfies the auth gate.**
    """
    signer.reset_for_testing()
    handle = signer.generate_dev_signing_key(key_id="p19k-cookie-key")
    signer.set_active_signing_key(handle=handle)
    try:
        request = _FakeRequest(auth_principal=object())
        response = signing_keys_routes.handle_list_envelope_signing_keys(
            request
        )
    finally:
        signer.reset_for_testing()

    testbase.assert_equal(response.status_code, 200)
    return


def test_handle_accepts_mtls_client_principal():
    """
    **Feature: p19k expose-envelope-signing-key**
    **Property: A request carrying a verified mTLS client common-name
    satisfies the auth gate -- this is the freshly-enrolled client's
    access path.**
    """
    signer.reset_for_testing()
    handle = signer.generate_dev_signing_key(key_id="p19k-mtls-key")
    signer.set_active_signing_key(handle=handle)
    try:
        request = _FakeRequest(mtls_client_cn="client-abc")
        response = signing_keys_routes.handle_list_envelope_signing_keys(
            request
        )
    finally:
        signer.reset_for_testing()

    testbase.assert_equal(response.status_code, 200)
    return


# ---------------------------------------------------------------------------
# 503 sweep
# ---------------------------------------------------------------------------


def test_handle_returns_503_when_signer_absent():
    """
    **Feature: p19k expose-envelope-signing-key**
    **Property: With an authenticated principal but no signing key
    provisioned the handler returns 503 problem+json so callers can
    distinguish "not configured" from "auth failure".**
    """
    signer.reset_for_testing()
    request = _FakeRequest(auth_principal=object())
    response = signing_keys_routes.handle_list_envelope_signing_keys(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_handle_returns_200_with_jwks_style_key_set():
    """
    **Feature: p19k expose-envelope-signing-key**
    **Property: With a signing key installed the handler returns 200
    with a ``{"keys": [...]}`` body; the single entry carries the
    signer's key_id, Ed25519 algorithm, a PEM public key, and the
    ``active`` status.**
    """
    signer.reset_for_testing()
    handle = signer.generate_dev_signing_key(key_id="p19k-active-key")
    signer.set_active_signing_key(handle=handle)
    try:
        request = _FakeRequest(auth_principal=object())
        response = signing_keys_routes.handle_list_envelope_signing_keys(
            request
        )
    finally:
        signer.reset_for_testing()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    keys = body["keys"]
    testbase.assert_equal(len(keys), 1)
    entry = keys[0]
    testbase.assert_equal(entry["key_id"], "p19k-active-key")
    testbase.assert_equal(entry["algorithm"], "Ed25519")
    testbase.assert_equal(entry["status"], "active")
    pem_ok = entry["public_key_pem"].startswith("-----BEGIN PUBLIC KEY-----")
    testbase.assert_equal(pem_ok, True)
    return


def test_exposed_pem_parses_as_valid_ed25519_public_key():
    """
    **Feature: p19k expose-envelope-signing-key**
    **Property: The ``public_key_pem`` in the response is a
    well-formed Ed25519 SubjectPublicKeyInfo key.**
    """
    signer.reset_for_testing()
    handle = signer.generate_dev_signing_key(key_id="p19k-parse-key")
    signer.set_active_signing_key(handle=handle)
    try:
        request = _FakeRequest(auth_principal=object())
        response = signing_keys_routes.handle_list_envelope_signing_keys(
            request
        )
    finally:
        signer.reset_for_testing()

    body = _decode_body(response)
    pem_text = body["keys"][0]["public_key_pem"]
    loaded = serialization.load_pem_public_key(pem_text.encode("ascii"))
    is_ed25519 = isinstance(loaded, Ed25519PublicKey)
    testbase.assert_equal(is_ed25519, True)
    return


def test_exposed_public_key_verifies_signature_from_the_signer():
    """
    **Feature: p19k expose-envelope-signing-key**
    **Property: ROUND TRIP -- a detached signature produced by the
    in-process signer verifies against the public key the endpoint
    exposes. This is the security property the pod-client relies
    on.**
    """
    signer.reset_for_testing()
    handle = signer.generate_dev_signing_key(key_id="p19k-roundtrip-key")
    signer.set_active_signing_key(handle=handle)
    try:
        request = _FakeRequest(auth_principal=object())
        response = signing_keys_routes.handle_list_envelope_signing_keys(
            request
        )
        body = _decode_body(response)
        pem_text = body["keys"][0]["public_key_pem"]

        payload = b"p19k canonical envelope bytes round-trip"
        signature = signer.sign(payload=payload)
    finally:
        signer.reset_for_testing()

    exposed_public_key = serialization.load_pem_public_key(
        pem_text.encode("ascii")
    )
    # Raises InvalidSignature on mismatch -- a clean return proves
    # the exposed key verifies the signer's signature.
    exposed_public_key.verify(signature, payload)
    return


def test_retiring_key_marked_when_extra_verify_key_registered():
    """
    **Feature: p19k expose-envelope-signing-key**
    **Property: A verify key that is not the active signing key is
    reported with ``status == "retiring"`` so the schema supports
    rotation.**
    """
    signer.reset_for_testing()
    active_handle = signer.generate_dev_signing_key(key_id="p19k-active")
    signer.set_active_signing_key(handle=active_handle)
    retiring_handle = signer.generate_dev_signing_key(key_id="p19k-old")
    signer.register_verify_key(
        key_id=retiring_handle.key_id,
        public_key=retiring_handle.public_key,
    )
    try:
        request = _FakeRequest(auth_principal=object())
        response = signing_keys_routes.handle_list_envelope_signing_keys(
            request
        )
    finally:
        signer.reset_for_testing()

    body = _decode_body(response)
    statuses = {entry["key_id"]: entry["status"] for entry in body["keys"]}
    testbase.assert_equal(statuses["p19k-active"], "active")
    testbase.assert_equal(statuses["p19k-old"], "retiring")
    return


# ---------------------------------------------------------------------------
# Environment-driven signer install
# ---------------------------------------------------------------------------


def _clear_signing_env() -> None:
    """
        Remove every ``PYCHESTRATE_ENVELOPE_SIGNING_KEY_*`` env var
        plus the dev-mode toggle so a test starts from a known state.
    """
    for name in (
        envelope_startup.ENV_SIGNING_KEY_SOURCE,
        envelope_startup.ENV_SIGNING_KEY_ID,
        envelope_startup.ENV_SIGNING_KEY_FILE_PATH,
        envelope_startup.ENV_SIGNING_KEY_ENV_VAR,
        envelope_startup.DEV_MODE_ENV_VAR,
    ):
        if name in os.environ:
            del os.environ[name]
    return


def test_install_from_environment_uses_dev_mode_when_source_unset():
    """
    **Feature: p19k expose-envelope-signing-key**
    **Property: With no SOURCE env var and PYCHESTRATE_DEV_MODE=1 the
    environment-driven install generates an ephemeral signing key.**
    """
    signer.reset_for_testing()
    _clear_signing_env()
    os.environ[envelope_startup.DEV_MODE_ENV_VAR] = "1"
    try:
        installed = envelope_startup.install_envelope_signer_from_environment()
    finally:
        _clear_signing_env()
        installed_handle = signer._ACTIVE_SIGNING_KEY  # noqa: SLF001
        signer.reset_for_testing()

    testbase.assert_equal(installed, True)
    testbase.assert_true(installed_handle is not None)
    return


def test_install_from_environment_returns_false_on_misconfiguration():
    """
    **Feature: p19k expose-envelope-signing-key**
    **Property: A bad config (source=dev without PYCHESTRATE_DEV_MODE)
    is swallowed -- the install returns False rather than crashing the
    service bootstrap, and no key is installed.**
    """
    signer.reset_for_testing()
    _clear_signing_env()
    os.environ[envelope_startup.ENV_SIGNING_KEY_SOURCE] = "dev"
    try:
        installed = envelope_startup.install_envelope_signer_from_environment()
    finally:
        _clear_signing_env()
        signer.reset_for_testing()

    testbase.assert_equal(installed, False)
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_signing_keys_routes_and_calls_it():
    """
    **Feature: p19k expose-envelope-signing-key**
    **Property: app_pychestrate_main.py wires
    register_signing_keys_routes into the service bootstrap.**
    """
    here = os.path.dirname(os.path.abspath(__file__))
    repo_source_root = os.path.normpath(
        os.path.join(
            here, "..", "..", "..", "..", "..", "..", "..", "..",
            "source", "site",
        )
    )
    bootstrap_path = os.path.join(repo_source_root, "app_pychestrate_main.py")
    with open(bootstrap_path, "r", encoding="utf-8") as fh:
        text = fh.read()

    has_import = (
        "signing_keys_routes import" in text
    )
    has_call = (
        "register_signing_keys_routes(app=app, version_prefix=\"/api/v1\")"
        in text
    )
    has_signer_install = (
        "install_envelope_signer_from_environment()" in text
    )
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    testbase.assert_equal(has_signer_install, True)
    return
