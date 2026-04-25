"""
.. module:: security.auth.factories.mfa_method
    :synopsis: MFAMethodExtension resource base + IO shapes.

The base class is a :class:`ResourceExtension` per the M2
spec — concrete methods (TOTP, WebAuthn, push) are
*kinds*, not chains of overrides, so the consumer iterates
the registered set rather than picking one.

Each implementation owns the secret-shape it expects to live
in :class:`AuthMfaEnrollment.secret_ref`, the form of the
challenge payload it returns from
:meth:`initiate_challenge`, and the constant-time compare
inside :meth:`verify_response`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Optional

from automojo.pychestrate.webservice.extensions.resource_extension import (
    ResourceExtension,
)


@dataclass(frozen=True)
class MfaEnrollmentRecord:
    """
        Caller-facing snapshot of an enrollment row passed
        across the extension boundary so the method does not
        need a DB session of its own.
    """
    enrollment_id: str
    user_id: str
    method_name: str
    secret_payload: bytes
    verified_at: Optional[datetime]


@dataclass(frozen=True)
class MfaChallenge:
    """
        Issued challenge bundle the orchestration layer holds
        in the active-challenge store while the user produces
        their response.
    """
    challenge_id: str
    method_name: str
    user_id: str
    issued_at: datetime
    expires_at: datetime
    payload: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MfaResponse:
    """
        User-supplied response submitted to
        :meth:`MFAMethodExtension.verify_response`.
    """
    fields: Mapping[str, object]


@dataclass(frozen=True)
class MfaVerifyOutcome:
    """
        Result of a verify_response invocation.

        :param accepted: ``True`` when the response satisfies
                         the method.
        :param reason: Stable token when not accepted —
                       ``"code_invalid"``, ``"window_drift"``.
    """
    accepted: bool
    reason: Optional[str] = None


class MFAMethodExtension(ResourceExtension):
    """
        Resource base for MFA methods. Subclasses set
        :attr:`method_name`, :attr:`requires_second_factor`,
        and override :meth:`initiate_challenge` +
        :meth:`verify_response`.
    """

    resource_extension_name: str = "mfa_method"

    method_name: str = ""
    requires_second_factor: bool = True

    @classmethod
    def enroll_payload(
            cls
        ) -> Mapping[str, object]:
        """
            Return the per-method enrollment metadata produced
            during the enroll-time handshake. The default
            implementation returns an empty mapping; the TOTP
            reference returns the provisioning URI.
        """
        rtnval: Mapping[str, object] = {}
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
        """
            Produce a fresh challenge for ``enrollment``.
        """
        raise NotImplementedError(
            "Subclasses must implement initiate_challenge",
        )

    @classmethod
    def verify_response(
            cls,
            *,
            enrollment: MfaEnrollmentRecord,
            challenge: MfaChallenge,
            response: MfaResponse,
            now: datetime
        ) -> MfaVerifyOutcome:
        """
            Compare ``response`` against ``challenge``.
        """
        raise NotImplementedError(
            "Subclasses must implement verify_response",
        )
