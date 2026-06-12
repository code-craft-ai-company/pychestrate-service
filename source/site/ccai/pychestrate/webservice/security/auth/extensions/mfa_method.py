"""
.. module:: security.auth.extensions.mfa_method
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``MFAMethodExtension`` resource base for ``1-authentication``.

.. moduleauthor:: Code Craft AI LLC

Layer 1 publishes ``MFAMethodExtension`` (per ``8-plugin-api``
Requirement 2) so external packs can ship MFA methods (TOTP,
WebAuthn, push notification, recovery code, custom) without forking
the auth subsystem. Each subclass declares a stable
:attr:`method_name` plus the two flow halves —
:meth:`begin_enrollment` returns a challenge bundle, and
:meth:`verify_challenge` returns the verification outcome.

The base intentionally avoids prescribing a wire format for
challenges or proofs; subclasses encode whatever shape their method
needs in the opaque ``payload`` mappings on
:class:`MFAEnrollmentChallenge` and
:class:`MFAVerificationResult`. The auth runtime owns lookup,
storage, and rate-limit enforcement; the extension owns the
cryptographic check.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping

from ccai.pychestrate.webservice.extensions.resource_extension import ResourceExtension


@dataclass(frozen=True)
class MFAEnrollmentChallenge:
    """
        Returned by :meth:`MFAMethodExtension.begin_enrollment`.

        :param method_name: Echoes the producing extension's method
                            name for diagnostic correlation.
        :param challenge_id: Caller-correlation id the auth runtime
                             persists alongside the user's enrollment
                             record.
        :param payload: Opaque mapping the extension renders to the
                        client (e.g., TOTP secret + QR URI, WebAuthn
                        creation options).
    """
    method_name: str
    challenge_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MFAVerificationResult:
    """
        Returned by :meth:`MFAMethodExtension.verify_challenge`.

        :param verified: True iff the supplied proof passes the
                         method's check.
        :param method_name: Echoes the producing extension's method
                            name.
        :param failure_reason: Short stable token (machine-readable)
                               when ``verified`` is False; empty
                               string otherwise.
    """
    verified: bool
    method_name: str
    failure_reason: str


class MFAMethodExtension(ResourceExtension):
    """
        Base class for an MFA method contributed to ``1-authentication``.

        Subclasses set :attr:`method_name`, :attr:`display_label`, and
        :attr:`requires_enrollment`, then implement
        :meth:`begin_enrollment` and :meth:`verify_challenge`. The
        auth runtime gates every call by RBAC + rate limit before
        dispatching, so subclasses focus purely on the cryptographic
        contract.
    """

    resource_extension_name: ClassVar[str] = "mfa_method"
    method_name: ClassVar[str] = ""
    display_label: ClassVar[str] = ""
    requires_enrollment: ClassVar[bool] = True

    is_published: ClassVar[bool] = True
    published_docs_url: ClassVar[str] = (
        "https://docs.pychestrate.io/plugin-api/MFAMethodExtension"
    )
    published_reference: ClassVar[str] = (
        "ccai.pychestrate.webservice.security.auth.extensions.totp_method"
        ".TotpMfaMethod"
    )

    @classmethod
    def begin_enrollment(
            cls,
            *,
            user_id: str
        ) -> MFAEnrollmentChallenge:
        """
            Produce an enrollment challenge for ``user_id``.

            Subclasses generate the method-specific secret material
            and return :class:`MFAEnrollmentChallenge` for the auth
            runtime to persist and surface to the client.

            :param user_id: Acting user id (UUID string).

            :returns: :class:`MFAEnrollmentChallenge`.
        """
        raise NotImplementedError("Subclasses must implement begin_enrollment")

    @classmethod
    def verify_challenge(
            cls,
            *,
            user_id: str,
            challenge_id: str,
            proof: Mapping[str, Any]
        ) -> MFAVerificationResult:
        """
            Verify a method-specific proof against an enrollment
            persisted under ``challenge_id``.

            :param user_id: Acting user id.
            :param challenge_id: Id returned from a prior
                                 :meth:`begin_enrollment` call.
            :param proof: Method-specific verification payload.

            :returns: :class:`MFAVerificationResult`.
        """
        raise NotImplementedError("Subclasses must implement verify_challenge")
