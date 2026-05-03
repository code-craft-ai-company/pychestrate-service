"""
.. module:: security.auth.oidc.id_token
    :synopsis: OIDC id_token validation.

The id_token is a signed JWT carrying the IdP's claims
about the authenticated user. Pychestrate validates it
end-to-end before opening a session:

1. Decode the compact JWS (header + payload + signature).
2. Look up the signing key from the configured JWKS via
   ``kid``. The lookup is pluggable through
   :class:`JwksKeyResolver` so production wires it to the
   ``oidc.discovery`` fetcher and tests hand in a
   deterministic mapping.
3. Verify the signature against the resolved key. RS256 +
   ES256 are supported (the OIDC core mandate).
4. Validate the claim set: iss matches the configured
   issuer, aud contains the configured client_id, exp >
   now, iat <= now + skew, nonce matches the state-row
   nonce.

The validator is *total*: every failure surfaces as
:class:`IdTokenValidationError` carrying a stable reason
token so the controller can log without leaking detail to
the client.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import hashlib
import hmac
import json
import os

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, List, Mapping, Optional, Tuple


DEFAULT_CLOCK_SKEW = timedelta(minutes=2)


SUPPORTED_ALGORITHMS: Tuple[str, ...] = ("RS256", "ES256", "HS256")


class IdTokenValidationError(Exception):
    """
        Raised when an id_token fails any decode / signature
        / claim check. The first argument is a stable reason
        token so callers can log + branch.

        :param reason: Stable token (
                       ``id_token_malformed`` /
                       ``alg_unsupported`` /
                       ``signing_key_unknown`` /
                       ``signature_invalid`` /
                       ``iss_mismatch`` /
                       ``aud_missing`` /
                       ``token_expired`` /
                       ``iat_in_future`` /
                       ``nonce_mismatch``).
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason if len(detail) == 0 else "{}: {}".format(reason, detail))
        self.reason: str = reason
        self.detail: str = detail
        return


@dataclass(frozen=True)
class DecodedIdToken:
    """
        Result of decoding (not validating) an id_token.

        :param header: Parsed JWS header (contains ``alg`` /
                       ``kid`` / ``typ``).
        :param payload: Parsed JWT claim set.
        :param signing_input: ``header.payload`` bytes the
                              signature was computed over.
        :param signature: Raw signature bytes.
    """
    header: Mapping[str, Any]
    payload: Mapping[str, Any]
    signing_input: bytes
    signature: bytes


@dataclass(frozen=True)
class JwksKey:
    """
        One entry in the IdP's JWKS document.

        :param kid: Key id matching the JWS header ``kid``.
        :param alg: Signing algorithm (``RS256`` /
                    ``ES256`` / ``HS256``).
        :param key: Algorithm-specific key material —
                    ``cryptography`` public key for RS256/ES256,
                    raw bytes for HS256 (test surface).
    """
    kid: str
    alg: str
    key: Any


JwksKeyResolver = Callable[[str], Optional[JwksKey]]


@dataclass(frozen=True)
class ValidationParams:
    """
        Per-call validation parameters.

        :param expected_issuer: ``iss`` claim must equal this
                                exactly.
        :param expected_audience: ``aud`` claim (string or
                                  list) must contain this.
        :param expected_nonce: ``nonce`` claim must equal
                               this exactly. ``None`` skips
                               the nonce check (refresh
                               flows that don't issue a
                               nonce).
        :param clock_skew: Absolute tolerance applied to
                           ``exp`` / ``iat`` checks.
        :param now: Optional clock override.
    """
    expected_issuer: str
    expected_audience: str
    expected_nonce: Optional[str] = None
    clock_skew: timedelta = DEFAULT_CLOCK_SKEW
    now: Optional[datetime] = None


def decode_id_token(*, token: str) -> DecodedIdToken:
    """
        Parse a compact JWS into header / payload / signing
        input / signature without verifying anything.

        :raises: IdTokenValidationError(reason="id_token_malformed").
    """
    if token is None or len(token) == 0:
        raise IdTokenValidationError(
            "id_token_malformed", "empty token",
        ) from None
    parts = token.split(".")
    if len(parts) != 3:
        raise IdTokenValidationError(
            "id_token_malformed",
            "expected three dot-separated segments, got {}".format(len(parts)),
        ) from None
    header_segment, payload_segment, signature_segment = parts
    try:
        header = json.loads(_b64url_decode(segment=header_segment))
    except (ValueError, json.JSONDecodeError) as decode_err:
        raise IdTokenValidationError(
            "id_token_malformed",
            "header parse: {}".format(decode_err),
        ) from None
    try:
        payload = json.loads(_b64url_decode(segment=payload_segment))
    except (ValueError, json.JSONDecodeError) as decode_err:
        raise IdTokenValidationError(
            "id_token_malformed",
            "payload parse: {}".format(decode_err),
        ) from None
    if not isinstance(header, dict):
        raise IdTokenValidationError(
            "id_token_malformed", "header is not an object",
        ) from None
    if not isinstance(payload, dict):
        raise IdTokenValidationError(
            "id_token_malformed", "payload is not an object",
        ) from None
    try:
        signature = _b64url_decode(segment=signature_segment)
    except ValueError as decode_err:
        raise IdTokenValidationError(
            "id_token_malformed",
            "signature parse: {}".format(decode_err),
        ) from None
    signing_input = "{}.{}".format(
        header_segment, payload_segment,
    ).encode("ascii")
    rtnval = DecodedIdToken(
        header=header,
        payload=payload,
        signing_input=signing_input,
        signature=signature,
    )
    return rtnval


def validate_id_token(
        *,
        token: str,
        params: ValidationParams,
        key_resolver: JwksKeyResolver
    ) -> DecodedIdToken:
    """
        Decode + verify signature + validate claims.

        :param token: The JWT id_token string.
        :param params: Per-call validation parameters.
        :param key_resolver: Callable mapping a ``kid`` to a
                             :class:`JwksKey` (or ``None`` on
                             miss).

        :returns: The decoded token bundle on success.
        :raises: IdTokenValidationError on any failure.
    """
    decoded = decode_id_token(token=token)

    alg = decoded.header.get("alg")
    if alg not in SUPPORTED_ALGORITHMS:
        raise IdTokenValidationError(
            "alg_unsupported",
            "alg={!r}".format(alg),
        ) from None

    kid = decoded.header.get("kid")
    if kid is None or len(kid) == 0:
        raise IdTokenValidationError(
            "id_token_malformed", "header missing kid",
        ) from None
    key = key_resolver(kid)
    if key is None:
        raise IdTokenValidationError(
            "signing_key_unknown",
            "no JWKS entry for kid={!r}".format(kid),
        ) from None
    if key.alg != alg:
        raise IdTokenValidationError(
            "alg_unsupported",
            "header alg={} disagrees with key alg={}".format(alg, key.alg),
        ) from None

    if alg == "HS256":
        _verify_hs256(
            signing_input=decoded.signing_input,
            signature=decoded.signature,
            key=key.key,
        )
    elif alg == "RS256":
        _verify_rs256(
            signing_input=decoded.signing_input,
            signature=decoded.signature,
            key=key.key,
        )
    elif alg == "ES256":
        _verify_es256(
            signing_input=decoded.signing_input,
            signature=decoded.signature,
            key=key.key,
        )

    _validate_claims(payload=decoded.payload, params=params)
    rtnval = decoded
    return rtnval


def _validate_claims(
        *,
        payload: Mapping[str, Any],
        params: ValidationParams
    ) -> None:
    issuer_claim = payload.get("iss")
    if issuer_claim != params.expected_issuer:
        raise IdTokenValidationError(
            "iss_mismatch",
            "expected={!r} actual={!r}".format(
                params.expected_issuer, issuer_claim,
            ),
        ) from None

    aud_claim = payload.get("aud")
    aud_list: List[str] = []
    if isinstance(aud_claim, list):
        aud_list = [str(value) for value in aud_claim]
    elif isinstance(aud_claim, str):
        aud_list = [aud_claim]
    if params.expected_audience not in aud_list:
        raise IdTokenValidationError(
            "aud_missing",
            "expected={!r} actual={!r}".format(
                params.expected_audience, aud_claim,
            ),
        ) from None

    materialized_now = (
        params.now if params.now is not None
        else datetime.now(tz=timezone.utc)
    )
    skew = params.clock_skew

    exp_claim = payload.get("exp")
    if exp_claim is None:
        raise IdTokenValidationError(
            "token_expired", "exp claim missing",
        ) from None
    try:
        exp_at = datetime.fromtimestamp(int(exp_claim), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        raise IdTokenValidationError(
            "token_expired",
            "exp claim invalid: {!r}".format(exp_claim),
        ) from None
    if materialized_now > (exp_at + skew):
        raise IdTokenValidationError(
            "token_expired",
            "exp={} now={}".format(exp_at.isoformat(), materialized_now.isoformat()),
        ) from None

    iat_claim = payload.get("iat")
    if iat_claim is not None:
        try:
            iat_at = datetime.fromtimestamp(int(iat_claim), tz=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            raise IdTokenValidationError(
                "iat_in_future",
                "iat claim invalid: {!r}".format(iat_claim),
            ) from None
        if iat_at > (materialized_now + skew):
            raise IdTokenValidationError(
                "iat_in_future",
                "iat={} now={}".format(
                    iat_at.isoformat(), materialized_now.isoformat(),
                ),
            ) from None

    if params.expected_nonce is not None:
        nonce_claim = payload.get("nonce")
        if nonce_claim != params.expected_nonce:
            raise IdTokenValidationError(
                "nonce_mismatch",
                "expected={!r} actual={!r}".format(
                    params.expected_nonce, nonce_claim,
                ),
            ) from None
    return


def _verify_hs256(
        *, signing_input: bytes, signature: bytes, key: Any
    ) -> None:
    if not isinstance(key, (bytes, bytearray)):
        raise IdTokenValidationError(
            "signature_invalid",
            "HS256 key must be raw bytes",
        ) from None
    expected = hmac.new(
        bytes(key), signing_input, hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected, signature):
        raise IdTokenValidationError(
            "signature_invalid", "HS256 compare failed",
        ) from None
    return


def _verify_rs256(
        *, signing_input: bytes, signature: bytes, key: Any
    ) -> None:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    try:
        key.verify(
            signature,
            signing_input,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except InvalidSignature:
        raise IdTokenValidationError(
            "signature_invalid", "RS256 verify rejected",
        ) from None
    except Exception as verify_err:
        raise IdTokenValidationError(
            "signature_invalid",
            "RS256 verify raised: {}".format(verify_err),
        ) from None
    return


def _verify_es256(
        *, signing_input: bytes, signature: bytes, key: Any
    ) -> None:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import (
        ec, utils as asym_utils,
    )

    if len(signature) != 64:
        raise IdTokenValidationError(
            "signature_invalid",
            "ES256 raw signature must be 64 bytes",
        ) from None
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    der_signature = asym_utils.encode_dss_signature(r, s)
    try:
        key.verify(
            der_signature,
            signing_input,
            ec.ECDSA(hashes.SHA256()),
        )
    except InvalidSignature:
        raise IdTokenValidationError(
            "signature_invalid", "ES256 verify rejected",
        ) from None
    except Exception as verify_err:
        raise IdTokenValidationError(
            "signature_invalid",
            "ES256 verify raised: {}".format(verify_err),
        ) from None
    return


def _b64url_decode(*, segment: str) -> bytes:
    if segment is None:
        raise ValueError("segment is None")
    padding = "=" * (-len(segment) % 4)
    rtnval = base64.urlsafe_b64decode(segment + padding)
    return rtnval


def encode_test_token(
        *,
        header: Mapping[str, Any],
        payload: Mapping[str, Any],
        hs256_key: bytes
    ) -> str:
    """
        Helper used by tests to assemble a deterministic
        HS256-signed id_token. Production code never calls
        this — production tokens come from the IdP.
    """
    header_segment = _b64url_encode(
        data=json.dumps(
            header, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8"),
    )
    payload_segment = _b64url_encode(
        data=json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8"),
    )
    signing_input = "{}.{}".format(
        header_segment, payload_segment,
    ).encode("ascii")
    signature = hmac.new(
        hs256_key, signing_input, hashlib.sha256,
    ).digest()
    rtnval = "{}.{}.{}".format(
        header_segment, payload_segment,
        _b64url_encode(data=signature),
    )
    return rtnval


def _b64url_encode(*, data: bytes) -> str:
    rtnval = base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
    return rtnval
