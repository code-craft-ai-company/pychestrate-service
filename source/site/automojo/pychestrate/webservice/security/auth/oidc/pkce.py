"""
.. module:: security.auth.oidc.pkce
    :synopsis: PKCE S256 verifier + challenge generation.

Implements RFC 7636 PKCE for the OIDC authorization-code
flow. The verifier is a high-entropy random URL-safe string
(43-128 chars per the RFC); the challenge is the base64url
encoding of ``SHA-256(verifier)`` with no padding. This
module is pure: no I/O, no DB.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import hashlib
import os
import secrets

from dataclasses import dataclass


PKCE_VERIFIER_BYTES: int = 32
PKCE_CHALLENGE_METHOD: str = "S256"


@dataclass(frozen=True)
class PkcePair:
    """
        PKCE verifier + challenge bundle.

        :param verifier: URL-safe verifier string the M2
                         dispatcher sends back to the IdP at
                         the token-exchange step.
        :param challenge: base64url-encoded SHA-256 of the
                          verifier, no padding.
        :param method: Always ``"S256"``.
    """
    verifier: str
    challenge: str
    method: str


def generate_pkce_pair(*, verifier_bytes: int = PKCE_VERIFIER_BYTES) -> PkcePair:
    """
        Build a fresh PKCE pair.

        :param verifier_bytes: Bytes of entropy for the
                               verifier (default 32 — yields
                               a ~43-character base64url
                               string, the RFC's lower
                               bound).

        :returns: A frozen :class:`PkcePair`.
    """
    if verifier_bytes < 32:
        err_lines = ["PKCE verifier must use >= 32 bytes of entropy."]
        err_lines.append("VALUE: {}".format(verifier_bytes))
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    raw = secrets.token_bytes(verifier_bytes)
    verifier = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    challenge = compute_challenge(verifier=verifier)
    rtnval = PkcePair(
        verifier=verifier,
        challenge=challenge,
        method=PKCE_CHALLENGE_METHOD,
    )
    return rtnval


def compute_challenge(*, verifier: str) -> str:
    """
        Re-derive the PKCE challenge for an arbitrary
        verifier — used by the M3 callback path to confirm
        the IdP returned a matching pair.
    """
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    rtnval = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return rtnval


def verify_challenge(*, verifier: str, challenge: str) -> bool:
    """
        Constant-time check that ``challenge`` matches
        ``SHA-256(verifier)`` under the S256 method.
    """
    import hmac
    expected = compute_challenge(verifier=verifier)
    rtnval = hmac.compare_digest(expected, challenge)
    return rtnval
