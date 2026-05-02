"""
.. module:: security.auth.extensions.totp_method
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference :class:`MFAMethodExtension` — RFC 6238 TOTP.

.. moduleauthor:: Automation Mojo LLC

Reference TOTP implementation per RFC 6238 used as the catalog's
``published_reference`` for ``MFAMethodExtension``. The runtime
storage / lookup live in the auth service; this module is just the
cryptographic surface — secret generation for enrollment and
HMAC-SHA-1-based code verification.

Tests in p10n_mfa_method_extension_m1 exercise the verification
math against fixed RFC 6238 test vectors so the reference cannot
silently regress.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import hashlib
import hmac
import os
import secrets
import struct
import time

from typing import Any, ClassVar, Mapping

from automojo.pychestrate.webservice.security.auth.extensions.mfa_method import (
    MFAEnrollmentChallenge,
    MFAMethodExtension,
    MFAVerificationResult,
)


TOTP_DEFAULT_PERIOD_SECONDS: int = 30
TOTP_DEFAULT_DIGITS: int = 6
TOTP_DEFAULT_ALGORITHM: str = "SHA1"


def _base32_secret(*, byte_length: int) -> str:
    """
        Generate a fresh URL-safe base-32-encoded secret.

        :param byte_length: Raw secret length in bytes.

        :returns: Base-32-encoded string with no padding.
    """
    raw = secrets.token_bytes(byte_length)
    encoded_padded = base64.b32encode(raw).decode("ascii")
    rtnval = encoded_padded.rstrip("=")
    return rtnval


def _decode_base32(*, encoded: str) -> bytes:
    """
        Decode a base-32 secret, restoring padding when it was
        stripped during issuance.

        :param encoded: Base-32 string (with or without padding).

        :returns: Decoded raw bytes.
    """
    padding_needed = (-len(encoded)) % 8
    padded = encoded + ("=" * padding_needed)
    rtnval = base64.b32decode(padded.upper(), casefold=True)
    return rtnval


def compute_totp_code(
        *,
        secret_base32: str,
        timestamp_seconds: int,
        period_seconds: int = TOTP_DEFAULT_PERIOD_SECONDS,
        digits: int = TOTP_DEFAULT_DIGITS
    ) -> str:
    """
        Compute the RFC 6238 TOTP value for a given secret + timestamp.

        :param secret_base32: Shared secret in base-32 encoding.
        :param timestamp_seconds: Unix timestamp.
        :param period_seconds: Step size (default 30s per RFC 6238).
        :param digits: Code length (default 6).

        :returns: Zero-padded numeric code of length ``digits``.
    """
    counter = int(timestamp_seconds // period_seconds)
    counter_bytes = struct.pack(">Q", counter)
    raw_key = _decode_base32(encoded=secret_base32)
    digest = hmac.new(raw_key, counter_bytes, hashlib.sha1).digest()

    offset = digest[-1] & 0x0F
    truncated = (
        ((digest[offset] & 0x7F) << 24)
        | ((digest[offset + 1] & 0xFF) << 16)
        | ((digest[offset + 2] & 0xFF) << 8)
        | (digest[offset + 3] & 0xFF)
    )
    code_int = truncated % (10 ** digits)
    rtnval = "{:0{}d}".format(code_int, digits)
    return rtnval


def _new_challenge_id() -> str:
    """
        Mint a fresh url-safe random challenge id for the runtime.

        :returns: 22-character url-safe base64 token.
    """
    rtnval = base64.urlsafe_b64encode(os.urandom(16)).decode("ascii").rstrip("=")
    return rtnval


class TotpMfaMethod(MFAMethodExtension):
    """
        Reference TOTP MFA method.

        Enrollment generates a 20-byte base-32 secret and returns it
        in the challenge payload along with the period / digits /
        algorithm parameters. Verification recomputes the TOTP for
        the current period and accepts a small +/- 1 step skew to
        absorb clock drift.
    """

    method_name: ClassVar[str] = "totp"
    display_label: ClassVar[str] = "Time-based One-Time Password"
    requires_enrollment: ClassVar[bool] = True

    _DEFAULT_SECRET_BYTES: ClassVar[int] = 20
    _SKEW_STEPS: ClassVar[int] = 1

    @classmethod
    def begin_enrollment(
            cls,
            *,
            user_id: str
        ) -> MFAEnrollmentChallenge:
        secret = _base32_secret(byte_length=cls._DEFAULT_SECRET_BYTES)
        payload = {
            "secret_base32": secret,
            "period_seconds": TOTP_DEFAULT_PERIOD_SECONDS,
            "digits": TOTP_DEFAULT_DIGITS,
            "algorithm": TOTP_DEFAULT_ALGORITHM,
        }
        rtnval = MFAEnrollmentChallenge(
            method_name=cls.method_name,
            challenge_id=_new_challenge_id(),
            payload=payload,
        )
        return rtnval

    @classmethod
    def verify_challenge(
            cls,
            *,
            user_id: str,
            challenge_id: str,
            proof: Mapping[str, Any]
        ) -> MFAVerificationResult:
        candidate_code = proof.get("code", "")
        secret = proof.get("secret_base32", "")
        if not isinstance(candidate_code, str) or len(candidate_code) == 0:
            rtnval = MFAVerificationResult(
                verified=False,
                method_name=cls.method_name,
                failure_reason="missing_code",
            )
            return rtnval
        if not isinstance(secret, str) or len(secret) == 0:
            rtnval = MFAVerificationResult(
                verified=False,
                method_name=cls.method_name,
                failure_reason="missing_secret",
            )
            return rtnval

        timestamp_override = proof.get("timestamp_seconds", None)
        if timestamp_override is None:
            now_seconds = int(time.time())
        else:
            now_seconds = int(timestamp_override)

        for skew in range(-cls._SKEW_STEPS, cls._SKEW_STEPS + 1):
            offset_seconds = now_seconds + (skew * TOTP_DEFAULT_PERIOD_SECONDS)
            expected = compute_totp_code(
                secret_base32=secret,
                timestamp_seconds=offset_seconds,
            )
            if hmac.compare_digest(candidate_code, expected):
                rtnval = MFAVerificationResult(
                    verified=True,
                    method_name=cls.method_name,
                    failure_reason="",
                )
                return rtnval

        rtnval = MFAVerificationResult(
            verified=False,
            method_name=cls.method_name,
            failure_reason="code_mismatch",
        )
        return rtnval
