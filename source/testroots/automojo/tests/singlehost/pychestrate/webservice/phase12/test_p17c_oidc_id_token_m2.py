"""
.. module:: test_p17c_oidc_id_token_m2
    :synopsis: Tests for P17c — 1-authentication M2 OIDC id_token validator.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from automojo import testbase

from automojo.pychestrate.webservice.security.auth.oidc.id_token import (
    DEFAULT_CLOCK_SKEW,
    DecodedIdToken,
    IdTokenValidationError,
    JwksKey,
    SUPPORTED_ALGORITHMS,
    ValidationParams,
    decode_id_token,
    encode_test_token,
    validate_id_token,
)


HS256_KEY: bytes = b"\xab" * 32


def _build_payload(
        *,
        issuer: str = "https://idp.example.com",
        audience: str = "client-pychestrate",
        nonce: Optional[str] = "fixed-nonce",
        exp_offset: int = 600,
        iat_offset: int = -10,
        anchor: Optional[datetime] = None
    ) -> Mapping[str, Any]:
    materialized_anchor = (
        anchor if anchor is not None else
        datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    )
    payload = {
        "iss": issuer,
        "aud": audience,
        "sub": "user-123",
        "exp": int((materialized_anchor + timedelta(seconds=exp_offset)).timestamp()),
        "iat": int((materialized_anchor + timedelta(seconds=iat_offset)).timestamp()),
    }
    if nonce is not None:
        payload["nonce"] = nonce
    return payload


def _build_token(
        *,
        header_kid: str = "kid-1",
        header_alg: str = "HS256",
        payload_overrides: Optional[Mapping[str, Any]] = None,
        anchor: Optional[datetime] = None,
        exp_offset: int = 600,
        iat_offset: int = -10
    ) -> str:
    header = {"alg": header_alg, "typ": "JWT", "kid": header_kid}
    payload = dict(_build_payload(
        anchor=anchor, exp_offset=exp_offset, iat_offset=iat_offset,
    ))
    if payload_overrides is not None:
        payload.update(payload_overrides)
    rtnval = encode_test_token(
        header=header, payload=payload, hs256_key=HS256_KEY,
    )
    return rtnval


def _resolver(*, kid: str = "kid-1", alg: str = "HS256", key=HS256_KEY):
    def _inner(lookup_kid: str):
        if lookup_kid != kid:
            return None
        return JwksKey(kid=kid, alg=alg, key=key)
    return _inner


# -------------------------------------
# decode_id_token
# -------------------------------------

def test_decode_id_token_returns_header_payload_signature():
    """
    **Feature: 1-authentication (M2)**
    **Property: decode_id_token parses the three compact JWS
    segments into header + payload + signature without
    verifying anything.**
    """
    token = _build_token()
    decoded = decode_id_token(token=token)
    testbase.assert_equal(decoded.header.get("alg"), "HS256")
    testbase.assert_equal(decoded.header.get("kid"), "kid-1")
    testbase.assert_equal(
        decoded.payload.get("iss"),
        "https://idp.example.com",
    )
    testbase.assert_equal(len(decoded.signature) > 0, True)
    return


def test_decode_id_token_rejects_empty_token():
    """
    **Feature: 1-authentication (M2)**
    **Property: an empty token raises IdTokenValidationError
    with reason='id_token_malformed'.**
    """
    raised = False
    captured_reason = ""
    try:
        decode_id_token(token="")
    except IdTokenValidationError as err:
        raised = True
        captured_reason = err.reason
    testbase.assert_equal(raised, True)
    testbase.assert_equal(captured_reason, "id_token_malformed")
    return


def test_decode_id_token_rejects_wrong_segment_count():
    """
    **Feature: 1-authentication (M2)**
    **Property: a token without exactly three dot-separated
    segments is malformed.**
    """
    raised_count = 0
    for token in ("only-one", "two.parts", "four.parts.go.here"):
        try:
            decode_id_token(token=token)
        except IdTokenValidationError as err:
            if err.reason == "id_token_malformed":
                raised_count = raised_count + 1
    testbase.assert_equal(raised_count, 3)
    return


def test_decode_id_token_rejects_non_object_header():
    """
    **Feature: 1-authentication (M2)**
    **Property: a header that decodes to a non-object value
    is malformed.**
    """
    import base64
    import json
    bad_header = base64.urlsafe_b64encode(
        json.dumps([1, 2, 3]).encode("utf-8"),
    ).decode("ascii").rstrip("=")
    body = base64.urlsafe_b64encode(
        json.dumps({}).encode("utf-8"),
    ).decode("ascii").rstrip("=")
    sig = base64.urlsafe_b64encode(b"sig").decode("ascii").rstrip("=")
    token = "{}.{}.{}".format(bad_header, body, sig)
    raised = False
    try:
        decode_id_token(token=token)
    except IdTokenValidationError as err:
        if err.reason == "id_token_malformed":
            raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# validate_id_token — happy path
# -------------------------------------

def test_validate_id_token_accepts_valid_token():
    """
    **Feature: 1-authentication (M2)**
    **Property: a fresh, properly-signed id_token validates
    cleanly under the canonical iss/aud/exp/nonce checks.**
    """
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    token = _build_token(anchor=anchor)
    params = ValidationParams(
        expected_issuer="https://idp.example.com",
        expected_audience="client-pychestrate",
        expected_nonce="fixed-nonce",
        now=anchor,
    )
    decoded = validate_id_token(
        token=token, params=params, key_resolver=_resolver(),
    )
    testbase.assert_equal(decoded.payload.get("sub"), "user-123")
    return


def test_validate_id_token_accepts_audience_list():
    """
    **Feature: 1-authentication (M2)**
    **Property: aud may be a list — validation passes when
    the configured audience is in the list.**
    """
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    token = _build_token(
        anchor=anchor,
        payload_overrides={
            "aud": ["other-client", "client-pychestrate"],
        },
    )
    params = ValidationParams(
        expected_issuer="https://idp.example.com",
        expected_audience="client-pychestrate",
        expected_nonce="fixed-nonce",
        now=anchor,
    )
    decoded = validate_id_token(
        token=token, params=params, key_resolver=_resolver(),
    )
    testbase.assert_equal(decoded.payload.get("sub"), "user-123")
    return


def test_validate_id_token_skips_nonce_when_expected_is_none():
    """
    **Feature: 1-authentication (M2)**
    **Property: a refresh-flow token without a nonce passes
    when expected_nonce is None.**
    """
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    token = _build_token(
        anchor=anchor,
        payload_overrides={"nonce": None},
    )
    # Strip the nonce by re-encoding without it.
    import json
    decoded = decode_id_token(token=token)
    payload_no_nonce = dict(decoded.payload)
    payload_no_nonce.pop("nonce", None)
    fresh = encode_test_token(
        header=decoded.header,
        payload=payload_no_nonce,
        hs256_key=HS256_KEY,
    )
    params = ValidationParams(
        expected_issuer="https://idp.example.com",
        expected_audience="client-pychestrate",
        expected_nonce=None,
        now=anchor,
    )
    validated = validate_id_token(
        token=fresh, params=params, key_resolver=_resolver(),
    )
    testbase.assert_equal(validated.payload.get("sub"), "user-123")
    return


# -------------------------------------
# validate_id_token — failure modes
# -------------------------------------

def test_validate_id_token_rejects_unknown_alg():
    """
    **Feature: 1-authentication (M2)**
    **Property: an unsupported alg surfaces with
    reason='alg_unsupported'.**
    """
    token = _build_token(header_alg="none")
    params = ValidationParams(
        expected_issuer="https://idp.example.com",
        expected_audience="client-pychestrate",
        expected_nonce="fixed-nonce",
    )
    raised_reason = ""
    try:
        validate_id_token(
            token=token, params=params, key_resolver=_resolver(),
        )
    except IdTokenValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "alg_unsupported")
    return


def test_validate_id_token_rejects_unknown_kid():
    """
    **Feature: 1-authentication (M2)**
    **Property: a kid that the resolver doesn't know
    surfaces as signing_key_unknown.**
    """
    token = _build_token(header_kid="ghost-kid")
    params = ValidationParams(
        expected_issuer="https://idp.example.com",
        expected_audience="client-pychestrate",
        expected_nonce="fixed-nonce",
    )
    raised_reason = ""
    try:
        validate_id_token(
            token=token, params=params, key_resolver=_resolver(),
        )
    except IdTokenValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "signing_key_unknown")
    return


def test_validate_id_token_rejects_alg_mismatch_with_key():
    """
    **Feature: 1-authentication (M2)**
    **Property: a header alg that disagrees with the
    resolved key's alg surfaces as alg_unsupported.**
    """
    token = _build_token()
    params = ValidationParams(
        expected_issuer="https://idp.example.com",
        expected_audience="client-pychestrate",
        expected_nonce="fixed-nonce",
    )
    raised_reason = ""
    try:
        validate_id_token(
            token=token, params=params,
            key_resolver=_resolver(alg="RS256"),
        )
    except IdTokenValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "alg_unsupported")
    return


def test_validate_id_token_rejects_forged_signature():
    """
    **Feature: 1-authentication (M2)**
    **Property: a token signed with a different HS256 key
    surfaces with reason='signature_invalid'.**
    """
    token = _build_token()
    params = ValidationParams(
        expected_issuer="https://idp.example.com",
        expected_audience="client-pychestrate",
        expected_nonce="fixed-nonce",
    )
    raised_reason = ""
    try:
        validate_id_token(
            token=token, params=params,
            key_resolver=_resolver(key=b"\x99" * 32),
        )
    except IdTokenValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "signature_invalid")
    return


def test_validate_id_token_rejects_iss_mismatch():
    """
    **Feature: 1-authentication (M2)**
    **Property: an iss claim that doesn't match
    expected_issuer surfaces with reason='iss_mismatch'.**
    """
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    token = _build_token(
        anchor=anchor,
        payload_overrides={"iss": "https://attacker.example.com"},
    )
    params = ValidationParams(
        expected_issuer="https://idp.example.com",
        expected_audience="client-pychestrate",
        expected_nonce="fixed-nonce",
        now=anchor,
    )
    raised_reason = ""
    try:
        validate_id_token(
            token=token, params=params, key_resolver=_resolver(),
        )
    except IdTokenValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "iss_mismatch")
    return


def test_validate_id_token_rejects_aud_missing():
    """
    **Feature: 1-authentication (M2)**
    **Property: an aud claim that does not contain the
    configured audience surfaces with reason='aud_missing'.**
    """
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    token = _build_token(
        anchor=anchor,
        payload_overrides={"aud": ["someone-else"]},
    )
    params = ValidationParams(
        expected_issuer="https://idp.example.com",
        expected_audience="client-pychestrate",
        expected_nonce="fixed-nonce",
        now=anchor,
    )
    raised_reason = ""
    try:
        validate_id_token(
            token=token, params=params, key_resolver=_resolver(),
        )
    except IdTokenValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "aud_missing")
    return


def test_validate_id_token_rejects_expired_token():
    """
    **Feature: 1-authentication (M2)**
    **Property: a token whose exp claim is in the past
    surfaces with reason='token_expired'.**
    """
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    token = _build_token(anchor=anchor, exp_offset=-3600)
    params = ValidationParams(
        expected_issuer="https://idp.example.com",
        expected_audience="client-pychestrate",
        expected_nonce="fixed-nonce",
        now=anchor,
    )
    raised_reason = ""
    try:
        validate_id_token(
            token=token, params=params, key_resolver=_resolver(),
        )
    except IdTokenValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "token_expired")
    return


def test_validate_id_token_rejects_iat_in_future():
    """
    **Feature: 1-authentication (M2)**
    **Property: an iat claim further in the future than the
    clock_skew window surfaces with reason='iat_in_future'.**
    """
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    token = _build_token(anchor=anchor, iat_offset=3600)
    params = ValidationParams(
        expected_issuer="https://idp.example.com",
        expected_audience="client-pychestrate",
        expected_nonce="fixed-nonce",
        now=anchor,
    )
    raised_reason = ""
    try:
        validate_id_token(
            token=token, params=params, key_resolver=_resolver(),
        )
    except IdTokenValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "iat_in_future")
    return


def test_validate_id_token_rejects_nonce_mismatch():
    """
    **Feature: 1-authentication (M2)**
    **Property: a nonce claim that doesn't equal
    expected_nonce surfaces with reason='nonce_mismatch'.**
    """
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    token = _build_token(
        anchor=anchor,
        payload_overrides={"nonce": "wrong-nonce"},
    )
    params = ValidationParams(
        expected_issuer="https://idp.example.com",
        expected_audience="client-pychestrate",
        expected_nonce="expected-nonce",
        now=anchor,
    )
    raised_reason = ""
    try:
        validate_id_token(
            token=token, params=params, key_resolver=_resolver(),
        )
    except IdTokenValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "nonce_mismatch")
    return


def test_validate_id_token_clock_skew_tolerance():
    """
    **Feature: 1-authentication (M2)**
    **Property: an exp claim slightly in the past but
    within the clock_skew window passes; just past the
    window fails.**
    """
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    token = _build_token(anchor=anchor, exp_offset=-60)
    params = ValidationParams(
        expected_issuer="https://idp.example.com",
        expected_audience="client-pychestrate",
        expected_nonce="fixed-nonce",
        clock_skew=timedelta(minutes=2),
        now=anchor,
    )
    decoded = validate_id_token(
        token=token, params=params, key_resolver=_resolver(),
    )
    testbase.assert_equal(decoded.payload.get("sub"), "user-123")

    raised_reason = ""
    params_strict = ValidationParams(
        expected_issuer="https://idp.example.com",
        expected_audience="client-pychestrate",
        expected_nonce="fixed-nonce",
        clock_skew=timedelta(seconds=10),
        now=anchor,
    )
    try:
        validate_id_token(
            token=token, params=params_strict,
            key_resolver=_resolver(),
        )
    except IdTokenValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "token_expired")
    return


def test_supported_algorithms_contains_canonical_set():
    """
    **Feature: 1-authentication (M2)**
    **Property: SUPPORTED_ALGORITHMS includes RS256 + ES256
    (the OIDC core mandate) plus HS256 (test surface).**
    """
    testbase.assert_equal("RS256" in SUPPORTED_ALGORITHMS, True)
    testbase.assert_equal("ES256" in SUPPORTED_ALGORITHMS, True)
    testbase.assert_equal("HS256" in SUPPORTED_ALGORITHMS, True)
    testbase.assert_equal("none" in SUPPORTED_ALGORITHMS, False)
    return
