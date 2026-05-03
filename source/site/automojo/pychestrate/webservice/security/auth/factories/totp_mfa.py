"""
.. module:: security.auth.factories.totp_mfa
    :synopsis: TotpMfaMethod reference MFA implementation.

The reference implements RFC 6238 (TOTP, SHA-1, 6-digit, 30s
step) with a one-step-back window to absorb client clock skew.
The shared secret bytes are stored in the enrollment row's
``secret_payload`` field by the bootstrap path; the extension
consumes them but never persists.
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

from datetime import datetime, timezone
from typing import Mapping, Optional

from automojo.pychestrate.webservice.security.auth.factories.mfa_method import (
    MFAMethodExtension,
    MfaChallenge,
    MfaEnrollmentRecord,
    MfaResponse,
    MfaVerifyOutcome,
)


TOTP_METHOD_NAME: str = "totp"
TOTP_DIGITS: int = 6
TOTP_PERIOD_SECONDS: int = 30
TOTP_DRIFT_WINDOWS: int = 1
TOTP_SECRET_LENGTH: int = 20


class TotpMfaMethod(MFAMethodExtension):
    """
        RFC 6238 TOTP reference. ``initiate_challenge`` is a
        no-op (the user reads the code off their own
        authenticator); ``verify_response`` recomputes the
        expected code over a +/- one window range.
    """

    resource_extension_name: str = "mfa_method"
    method_name: str = TOTP_METHOD_NAME
    requires_second_factor: bool = True

    @classmethod
    def generate_secret_bytes(cls) -> bytes:
        """
            Produce a fresh 160-bit shared secret. Helper used by
            the enrollment bootstrap path.
        """
        rtnval = secrets.token_bytes(TOTP_SECRET_LENGTH)
        return rtnval

    @classmethod
    def provisioning_uri(
            cls,
            *,
            secret_bytes: bytes,
            account_name: str,
            issuer: str = "Pychestrate"
        ) -> str:
        """
            Build the ``otpauth://`` provisioning URI agents like
            Google Authenticator scan as a QR code. Returned to
            the caller during enroll so it can be rendered as a
            QR code.
        """
        secret_b32 = base64.b32encode(secret_bytes).decode("ascii").rstrip("=")
        encoded_account = account_name.replace(" ", "%20")
        encoded_issuer = issuer.replace(" ", "%20")
        rtnval = (
            "otpauth://totp/"
            + "{}:{}".format(encoded_issuer, encoded_account)
            + "?secret=" + secret_b32
            + "&issuer=" + encoded_issuer
            + "&digits=" + str(TOTP_DIGITS)
            + "&period=" + str(TOTP_PERIOD_SECONDS)
        )
        return rtnval

    @classmethod
    def enroll_payload(cls) -> Mapping[str, object]:
        rtnval: Mapping[str, object] = {
            "digits": TOTP_DIGITS,
            "period_seconds": TOTP_PERIOD_SECONDS,
        }
        return rtnval

    @classmethod
    def initiate_challenge(
            cls,
            *,
            enrollment: MfaEnrollmentRecord,
            issued_at: datetime,
            expires_at: datetime,
            challenge_id: str
        ) -> MfaChallenge:
        rtnval = MfaChallenge(
            challenge_id=challenge_id,
            method_name=cls.method_name,
            user_id=enrollment.user_id,
            issued_at=issued_at,
            expires_at=expires_at,
            payload={
                "digits": TOTP_DIGITS,
                "period_seconds": TOTP_PERIOD_SECONDS,
            },
        )
        return rtnval

    @classmethod
    def verify_response(
            cls,
            *,
            enrollment: MfaEnrollmentRecord,
            challenge: MfaChallenge,
            response: MfaResponse,
            now: datetime
        ) -> MfaVerifyOutcome:
        submitted_code = response.fields.get("code")
        if submitted_code is None:
            rtnval = MfaVerifyOutcome(
                accepted=False, reason="code_missing",
            )
            return rtnval
        if not isinstance(submitted_code, str):
            submitted_code = str(submitted_code)
        if len(submitted_code) != TOTP_DIGITS or not submitted_code.isdigit():
            rtnval = MfaVerifyOutcome(
                accepted=False, reason="code_invalid",
            )
            return rtnval

        # Compute the expected code at the current step and
        # at +/- TOTP_DRIFT_WINDOWS to absorb client skew.
        epoch_seconds = int(now.timestamp())
        center_step = epoch_seconds // TOTP_PERIOD_SECONDS
        for offset in range(
            -TOTP_DRIFT_WINDOWS, TOTP_DRIFT_WINDOWS + 1
        ):
            candidate = _compute_totp(
                secret_bytes=enrollment.secret_payload,
                step=center_step + offset,
            )
            if hmac.compare_digest(candidate, submitted_code):
                if offset == 0:
                    rtnval = MfaVerifyOutcome(accepted=True)
                else:
                    rtnval = MfaVerifyOutcome(
                        accepted=True, reason="window_drift",
                    )
                return rtnval

        rtnval = MfaVerifyOutcome(accepted=False, reason="code_invalid")
        return rtnval


def _compute_totp(*, secret_bytes: bytes, step: int) -> str:
    """
        Compute one TOTP code for the given step using the
        canonical HOTP truncation per RFC 4226 + RFC 6238.
    """
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
