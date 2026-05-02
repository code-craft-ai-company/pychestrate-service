"""
.. module:: security.auth.extensions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``MFAMethodExtension`` resource base + reference packs.

.. moduleauthor:: Automation Mojo LLC

External ``pychestrate-ext-<name>`` packs subclass
:class:`MFAMethodExtension` to register a multi-factor authentication
method (TOTP, WebAuthn, push, custom). The base lives next to the
1-authentication feature so it ships with the auth subsystem.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.security.auth.extensions.mfa_method import (
    MFAEnrollmentChallenge,
    MFAMethodExtension,
    MFAVerificationResult,
)
from automojo.pychestrate.webservice.security.auth.extensions.totp_method import (
    TotpMfaMethod,
)


__all__ = [
    "MFAEnrollmentChallenge",
    "MFAMethodExtension",
    "MFAVerificationResult",
    "TotpMfaMethod",
]
