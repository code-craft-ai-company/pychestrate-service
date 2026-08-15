"""
.. module:: test_p19m_envelope_jwks_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the /api/v1/envelope-signing-keys/jwks.json endpoint.

.. moduleauthor:: Code Craft AI LLC

Covers the p19m envelope-signing JWK Set surface -- the standards
shaped sibling of the p19k PEM key-set endpoint:

* route registration (one GET pair),
* 401 for an anonymous request, 503 when no key is provisioned,
* the RFC 7517 / RFC 8037 OKP member set on each JWK,
* base64url ``x`` encoding with no padding,
* round-trip: a signature produced by the in-process signer verifies
  against the public key rebuilt from the published ``x``,
* active-key-first ordering across a rotation grace window,
* the registered ``application/jwk-set+json`` media type,
* the ``Cache-Control`` / ``ETag`` caching contract, including the
  ``If-None-Match`` 304 revalidation path,
* bootstrap source-smoke.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import hashlib
import json
import os

from typing import Any, Callable, Dict, List, Optional, Tuple

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)

from ccai import testbase

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_UNAUTHENTICATED,
)
from ccai.pychestrate.webservice.jobs.envelope import signer
from ccai.pychestrate.webservice.jobs.envelope.restapi.v1 import jwks_routes


# ---------------------------------------------------------------------------
# Test stubs / helpers
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(
        self,
        *,
        path: str = "/api/v1/envelope-signing-keys/jwks.json",
        auth_principal: Optional[Any] = None,
        mtls_client_cn: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.path: str = path
        self.auth_principal: Optional[Any] = auth_principal
        self.mtls_client_cn: Optional[str] = mtls_client_cn
        self.headers: Dict[str, str] = {}
        if headers is not None:
            for name, value in headers.items():
                self.headers[name] = value
        return

    def get_header(self, name: str, default: str = "") -> str:
        rtnval = self.headers.get(name, default)
        return rtnval


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


def _read_header(*, response: Any, name: str) -> str:
    """
        Read a response header case-insensitively.

        HTTP field names are case-insensitive (RFC 9110 section 5.1),
        so asserting on the exact key casing webworks happens to store
        would test the framework rather than the handler.
    """
    wanted = name.lower()
    for key, value in response.headers.items():
        if str(key).lower() == wanted:
            rtnval = str(value)
            return rtnval

    rtnval = ""
    return rtnval


def _install_dev_key(*, key_id: str) -> signer.SigningKeyHandle:
    """
        Reset the signer registry and install one freshly generated
        dev key as the active signing key.
    """
    signer.reset_for_testing()
    handle = signer.generate_dev_signing_key(key_id=key_id)
    signer.set_active_signing_key(handle=handle)
    rtnval = handle
    return rtnval


def _get_jwks(*, request: _FakeRequest) -> Any:
    """
        Invoke the handler and return the response, always clearing
        the module-level signer registry afterwards.
    """
    try:
        response = jwks_routes.handle_get_envelope_jwks(request)
    finally:
        signer.reset_for_testing()
    rtnval = response
    return rtnval


def _decode_base64url_no_padding(*, value: str) -> bytes:
    """
        Re-pad a base64url string and decode it back to raw bytes.
    """
    padding_needed = (-len(value)) % 4
    padded = value + ("=" * padding_needed)
    rtnval = base64.urlsafe_b64decode(padded.encode("ascii"))
    return rtnval


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_envelope_jwks_routes_attaches_one_get_route():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: register_envelope_jwks_routes attaches a single
    ``GET /api/v1/envelope-signing-keys/jwks.json`` route.**
    """
    app = _FakeApp()
    jwks_routes.register_envelope_jwks_routes(
        app=app, version_prefix="/api/v1"
    )

    expected = (("/api/v1/envelope-signing-keys/jwks.json", ("GET",)),)
    actual = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual, expected)
    return


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------


def test_handle_returns_401_for_anonymous_request():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: An unauthenticated request (no cookie / API-key
    principal and no mTLS cert) returns 401 problem+json.**
    """
    signer.reset_for_testing()
    response = _get_jwks(request=_FakeRequest())

    testbase.assert_equal(response.status_code, 401)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_handle_accepts_cookie_or_api_key_principal():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: A request carrying an auth_principal (resolved from
    the cookie session or API key) satisfies the auth gate.**
    """
    _install_dev_key(key_id="p19m-cookie-key")
    response = _get_jwks(request=_FakeRequest(auth_principal=object()))

    testbase.assert_equal(response.status_code, 200)
    return


def test_handle_accepts_mtls_client_principal():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: A request carrying a verified mTLS client common-name
    satisfies the auth gate -- this is the freshly-enrolled client's
    access path.**
    """
    _install_dev_key(key_id="p19m-mtls-key")
    response = _get_jwks(request=_FakeRequest(mtls_client_cn="client-abc"))

    testbase.assert_equal(response.status_code, 200)
    return


# ---------------------------------------------------------------------------
# Not-provisioned sweep
# ---------------------------------------------------------------------------


def test_handle_returns_503_when_signer_absent():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: With an authenticated principal but no signing key
    provisioned the handler returns 503 problem+json rather than an
    empty JWK Set, so callers can distinguish "not configured" from
    "this service signs nothing".**
    """
    signer.reset_for_testing()
    response = _get_jwks(request=_FakeRequest(auth_principal=object()))

    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


# ---------------------------------------------------------------------------
# RFC 7517 / RFC 8037 document shape
# ---------------------------------------------------------------------------


def test_response_body_is_a_jwk_set_with_one_key():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: The 200 body is an RFC 7517 JWK Set -- a ``keys``
    array -- carrying exactly one entry when a single signing key is
    installed.**
    """
    _install_dev_key(key_id="p19m-shape-key")
    response = _get_jwks(request=_FakeRequest(auth_principal=object()))

    body = _decode_body(response)
    testbase.assert_equal(list(body.keys()), ["keys"])
    testbase.assert_equal(len(body["keys"]), 1)
    return


def test_published_jwk_carries_the_okp_ed25519_member_set():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: Each JWK declares the RFC 8037 OKP/Ed25519 member set
    -- kty=OKP, crv=Ed25519, alg=EdDSA, use=sig -- plus the signer's
    kid.**
    """
    _install_dev_key(key_id="p19m-members-key")
    response = _get_jwks(request=_FakeRequest(auth_principal=object()))

    body = _decode_body(response)
    jwk = body["keys"][0]
    testbase.assert_equal(jwk["kty"], "OKP")
    testbase.assert_equal(jwk["crv"], "Ed25519")
    testbase.assert_equal(jwk["alg"], "EdDSA")
    testbase.assert_equal(jwk["use"], "sig")
    testbase.assert_equal(jwk["kid"], "p19m-members-key")
    return


def test_published_jwk_never_carries_private_key_material():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: The published JWK omits the RFC 8037 ``d`` member --
    the private signing key never leaves the service process.**
    """
    _install_dev_key(key_id="p19m-nopriv-key")
    response = _get_jwks(request=_FakeRequest(auth_principal=object()))

    body = _decode_body(response)
    jwk = body["keys"][0]
    has_private_member = "d" in jwk
    testbase.assert_equal(has_private_member, False)
    return


def test_published_x_is_unpadded_base64url_of_the_raw_public_key():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: The ``x`` member is the raw 32-byte Ed25519 public key
    in base64url with the trailing '=' padding stripped, per RFC 7515
    section 2.**
    """
    _install_dev_key(key_id="p19m-encoding-key")
    response = _get_jwks(request=_FakeRequest(auth_principal=object()))

    body = _decode_body(response)
    x_value = body["keys"][0]["x"]
    has_padding = "=" in x_value
    testbase.assert_equal(has_padding, False)

    raw_bytes = _decode_base64url_no_padding(value=x_value)
    testbase.assert_equal(len(raw_bytes), 32)
    return


def test_published_x_rebuilds_a_valid_ed25519_public_key():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: The decoded ``x`` member loads as a well-formed
    Ed25519 public key.**
    """
    _install_dev_key(key_id="p19m-rebuild-key")
    response = _get_jwks(request=_FakeRequest(auth_principal=object()))

    body = _decode_body(response)
    raw_bytes = _decode_base64url_no_padding(value=body["keys"][0]["x"])
    loaded = Ed25519PublicKey.from_public_bytes(raw_bytes)

    is_ed25519 = isinstance(loaded, Ed25519PublicKey)
    testbase.assert_equal(is_ed25519, True)
    return


def test_published_key_verifies_a_signature_from_the_signer():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: ROUND TRIP -- a detached signature produced by the
    in-process signer verifies against the public key rebuilt from the
    published JWK. This is the security property the pod-client relies
    on when it refuses to run an unverifiable envelope.**
    """
    _install_dev_key(key_id="p19m-roundtrip-key")
    payload = b"p19m canonical envelope bytes round-trip"
    try:
        request = _FakeRequest(auth_principal=object())
        response = jwks_routes.handle_get_envelope_jwks(request)
        body = _decode_body(response)
        x_value = body["keys"][0]["x"]
        signature = signer.sign(payload=payload)
    finally:
        signer.reset_for_testing()

    raw_bytes = _decode_base64url_no_padding(value=x_value)
    published_public_key = Ed25519PublicKey.from_public_bytes(raw_bytes)

    # Raises InvalidSignature on mismatch -- a clean return proves the
    # published key verifies the signer's signature.
    published_public_key.verify(signature, payload)
    return


def test_published_kid_matches_the_active_signing_key_id():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: The published ``kid`` is the same identifier the
    signer stamps onto signed envelopes, so a client can resolve an
    envelope's key_id against this document.**
    """
    handle = _install_dev_key(key_id="p19m-kid-match")
    expected_key_id = handle.key_id
    response = _get_jwks(request=_FakeRequest(auth_principal=object()))

    body = _decode_body(response)
    testbase.assert_equal(body["keys"][0]["kid"], expected_key_id)
    return


# ---------------------------------------------------------------------------
# Rotation ordering
# ---------------------------------------------------------------------------


def test_rotation_grace_window_key_is_published_alongside_the_active_key():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: A verify key registered for the rotation grace window
    is published in the same JWK Set, so a client can still verify
    envelopes signed by the previous generation.**
    """
    signer.reset_for_testing()
    active_handle = signer.generate_dev_signing_key(key_id="p19m-b-active")
    signer.set_active_signing_key(handle=active_handle)
    retiring_handle = signer.generate_dev_signing_key(key_id="p19m-a-old")
    signer.register_verify_key(
        key_id=retiring_handle.key_id,
        public_key=retiring_handle.public_key,
    )
    response = _get_jwks(request=_FakeRequest(auth_principal=object()))

    body = _decode_body(response)
    published_kids = sorted(entry["kid"] for entry in body["keys"])
    testbase.assert_equal(published_kids, ["p19m-a-old", "p19m-b-active"])
    return


def test_active_key_is_published_first_even_when_kid_sorts_last():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: The active signing key is element zero regardless of
    kid ordering (RFC 7517 section 5 lets key order signal
    preference), so a client can take keys[0] as "the key envelopes
    are being signed with right now".**
    """
    signer.reset_for_testing()
    active_handle = signer.generate_dev_signing_key(key_id="p19m-z-active")
    signer.set_active_signing_key(handle=active_handle)
    retiring_handle = signer.generate_dev_signing_key(key_id="p19m-a-old")
    signer.register_verify_key(
        key_id=retiring_handle.key_id,
        public_key=retiring_handle.public_key,
    )
    response = _get_jwks(request=_FakeRequest(auth_principal=object()))

    body = _decode_body(response)
    testbase.assert_equal(body["keys"][0]["kid"], "p19m-z-active")
    return


# ---------------------------------------------------------------------------
# Media type
# ---------------------------------------------------------------------------


def test_response_declares_the_registered_jwk_set_media_type():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: The 200 response carries the RFC 7517 section 8.5.1
    registered media type ``application/jwk-set+json``.**
    """
    _install_dev_key(key_id="p19m-media-key")
    response = _get_jwks(request=_FakeRequest(auth_principal=object()))

    content_type = _read_header(response=response, name="Content-Type")
    testbase.assert_equal(content_type, "application/jwk-set+json")
    return


# ---------------------------------------------------------------------------
# Caching contract
# ---------------------------------------------------------------------------


def test_response_declares_private_five_minute_revalidating_cache():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: The 200 response is cacheable ``private`` for 300
    seconds and must revalidate afterwards -- private because the
    endpoint is auth-gated, 300 s to match the ``max_envelope_age``
    default so a cached key set never outlives the envelopes it
    verifies.**
    """
    _install_dev_key(key_id="p19m-cache-key")
    response = _get_jwks(request=_FakeRequest(auth_principal=object()))

    cache_control = _read_header(response=response, name="Cache-Control")
    testbase.assert_equal(cache_control, "private, max-age=300, must-revalidate")
    return


def test_response_etag_is_the_sha256_of_the_canonical_document():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: The ``ETag`` is a quoted strong validator holding the
    SHA-256 of the canonical JSON rendering of the served document, so
    every gunicorn worker holding the same key set emits the same
    validator.**
    """
    _install_dev_key(key_id="p19m-etag-key")
    response = _get_jwks(request=_FakeRequest(auth_principal=object()))

    body = _decode_body(response)
    canonical_text = json.dumps(body, sort_keys=True, separators=(",", ":"))
    expected_digest = hashlib.sha256(
        canonical_text.encode("utf-8")
    ).hexdigest()

    etag = _read_header(response=response, name="ETag")
    testbase.assert_equal(etag, '"{}"'.format(expected_digest))
    return


def test_etag_changes_when_the_key_set_changes():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: Registering another verify key changes the ``ETag``,
    so a rotation invalidates every client's cached copy.**
    """
    signer.reset_for_testing()
    active_handle = signer.generate_dev_signing_key(key_id="p19m-drift-active")
    signer.set_active_signing_key(handle=active_handle)
    try:
        request = _FakeRequest(auth_principal=object())
        before_response = jwks_routes.handle_get_envelope_jwks(request)
        before_etag = _read_header(response=before_response, name="ETag")

        rotated_handle = signer.generate_dev_signing_key(
            key_id="p19m-drift-new"
        )
        signer.register_verify_key(
            key_id=rotated_handle.key_id,
            public_key=rotated_handle.public_key,
        )
        after_response = jwks_routes.handle_get_envelope_jwks(request)
        after_etag = _read_header(response=after_response, name="ETag")
    finally:
        signer.reset_for_testing()

    etags_differ = before_etag != after_etag
    testbase.assert_equal(etags_differ, True)
    return


def test_matching_if_none_match_returns_304_with_no_body():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: A revalidation request whose ``If-None-Match`` matches
    the current ``ETag`` gets ``304 Not Modified`` with an empty body,
    so the once-per-60 s unknown-key refresh costs a header exchange
    rather than a full document.**
    """
    signer.reset_for_testing()
    handle = signer.generate_dev_signing_key(key_id="p19m-inm-key")
    signer.set_active_signing_key(handle=handle)
    try:
        first = jwks_routes.handle_get_envelope_jwks(
            _FakeRequest(auth_principal=object())
        )
        etag = _read_header(response=first, name="ETag")
        revalidation = _FakeRequest(
            auth_principal=object(),
            headers={"If-None-Match": etag},
        )
        second = jwks_routes.handle_get_envelope_jwks(revalidation)
    finally:
        signer.reset_for_testing()

    testbase.assert_equal(second.status_code, 304)
    testbase.assert_equal(second.body, b"")
    return


def test_matching_if_none_match_repeats_the_validator_headers():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: The 304 answer repeats ``ETag`` and ``Cache-Control``
    so the client can extend its cache entry without a full fetch.**
    """
    signer.reset_for_testing()
    handle = signer.generate_dev_signing_key(key_id="p19m-inm-headers-key")
    signer.set_active_signing_key(handle=handle)
    try:
        first = jwks_routes.handle_get_envelope_jwks(
            _FakeRequest(auth_principal=object())
        )
        etag = _read_header(response=first, name="ETag")
        revalidation = _FakeRequest(
            auth_principal=object(),
            headers={"If-None-Match": etag},
        )
        second = jwks_routes.handle_get_envelope_jwks(revalidation)
    finally:
        signer.reset_for_testing()

    repeated_etag = _read_header(response=second, name="ETag")
    repeated_cache = _read_header(response=second, name="Cache-Control")
    testbase.assert_equal(repeated_etag, etag)
    testbase.assert_equal(
        repeated_cache, "private, max-age=300, must-revalidate"
    )
    return


def test_weak_if_none_match_prefix_still_matches():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: ``If-None-Match`` uses the weak comparison function
    (RFC 9110 section 13.1.2), so a ``W/``-prefixed candidate emitted
    by an intermediary still revalidates to 304.**
    """
    signer.reset_for_testing()
    handle = signer.generate_dev_signing_key(key_id="p19m-weak-key")
    signer.set_active_signing_key(handle=handle)
    try:
        first = jwks_routes.handle_get_envelope_jwks(
            _FakeRequest(auth_principal=object())
        )
        etag = _read_header(response=first, name="ETag")
        revalidation = _FakeRequest(
            auth_principal=object(),
            headers={"If-None-Match": "W/" + etag},
        )
        second = jwks_routes.handle_get_envelope_jwks(revalidation)
    finally:
        signer.reset_for_testing()

    testbase.assert_equal(second.status_code, 304)
    return


def test_lowercased_if_none_match_header_still_matches():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: The ``If-None-Match`` lookup is case-insensitive
    (RFC 9110 section 5.1), so the lowercased field name HTTP/2 puts
    on the wire still revalidates to 304 rather than silently
    re-sending the whole document.**
    """
    signer.reset_for_testing()
    handle = signer.generate_dev_signing_key(key_id="p19m-lowercase-key")
    signer.set_active_signing_key(handle=handle)
    try:
        first = jwks_routes.handle_get_envelope_jwks(
            _FakeRequest(auth_principal=object())
        )
        etag = _read_header(response=first, name="ETag")
        revalidation = _FakeRequest(
            auth_principal=object(),
            headers={"if-none-match": etag},
        )
        second = jwks_routes.handle_get_envelope_jwks(revalidation)
    finally:
        signer.reset_for_testing()

    testbase.assert_equal(second.status_code, 304)
    return


def test_stale_if_none_match_returns_the_full_document():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: An ``If-None-Match`` that does not match the current
    ``ETag`` returns 200 with the full JWK Set -- a client holding a
    pre-rotation copy gets the new keys.**
    """
    _install_dev_key(key_id="p19m-stale-key")
    request = _FakeRequest(
        auth_principal=object(),
        headers={"If-None-Match": '"not-the-current-digest"'},
    )
    response = _get_jwks(request=request)

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["keys"]), 1)
    return


def test_wildcard_if_none_match_returns_304():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: The ``*`` wildcard in ``If-None-Match`` matches any
    current representation and revalidates to 304, per RFC 9110
    section 13.1.2.**
    """
    _install_dev_key(key_id="p19m-wildcard-key")
    request = _FakeRequest(
        auth_principal=object(),
        headers={"If-None-Match": "*"},
    )
    response = _get_jwks(request=request)

    testbase.assert_equal(response.status_code, 304)
    return


def test_if_none_match_is_ignored_on_an_anonymous_request():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: The auth gate runs before the cache validator -- an
    anonymous request carrying a matching ``If-None-Match`` still gets
    401, never a 304 that would confirm the document exists.**
    """
    signer.reset_for_testing()
    handle = signer.generate_dev_signing_key(key_id="p19m-anon-inm-key")
    signer.set_active_signing_key(handle=handle)
    try:
        first = jwks_routes.handle_get_envelope_jwks(
            _FakeRequest(auth_principal=object())
        )
        etag = _read_header(response=first, name="ETag")
        anonymous = _FakeRequest(headers={"If-None-Match": etag})
        second = jwks_routes.handle_get_envelope_jwks(anonymous)
    finally:
        signer.reset_for_testing()

    testbase.assert_equal(second.status_code, 401)
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_envelope_jwks_routes_and_calls_it():
    """
    **Feature: p19m envelope-signing-jwks**
    **Property: app_pychestrate_main.py wires
    register_envelope_jwks_routes into the service bootstrap.**
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

    has_import = "jwks_routes import" in text
    has_call = (
        "register_envelope_jwks_routes(app=app, version_prefix=\"/api/v1\")"
        in text
    )
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return
