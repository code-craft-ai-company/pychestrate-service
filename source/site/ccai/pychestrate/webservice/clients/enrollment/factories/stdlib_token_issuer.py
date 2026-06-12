"""
.. module:: clients.enrollment.factories.stdlib_token_issuer
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Stdlib-only HMAC-SHA256 enrollment token issuer reference.

.. moduleauthor:: Code Craft AI LLC

Secret generation: 32 bytes of ``secrets.token_urlsafe``.
Stored digest: ``hmac.new(pepper, secret_bytes, sha256).digest()`` using
the active pepper loaded via :mod:`auth.pepper_loader`.
Verification: ``hmac.compare_digest`` over the recomputed digest.

The pepper is shared with the password hasher on purpose — a server-side
secret an attacker cannot derive from a database dump alone. Operators
register an out-of-tree issuer at a lower ``PRECEDENCE`` to swap the
algorithm (e.g. to Argon2id-backed HMAC, or an HSM-backed signer).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import hmac
import secrets as _py_secrets

from ccai.pychestrate.webservice.clients.enrollment.factories.token_issuer import (
    EnrollmentTokenIssuerProtocol,
    IssuedSecret,
)
from ccai.pychestrate.webservice.security.auth.pepper_loader import get_active_pepper


STDLIB_TOKEN_ISSUER_ALGORITHM: str = "phase2-stdlib-hmac-sha256"
STDLIB_TOKEN_SECRET_BYTES: int = 32


def _pepper_bytes() -> bytes:
    """
        Return the active pepper bytes. Raises :class:`ConfigurationError`
        through :func:`get_active_pepper` when no pepper has been loaded.

        :returns: Pepper bytes.
    """
    rtnval = get_active_pepper().reveal()
    return rtnval


def _digest(*, secret: str) -> bytes:
    """
        Compute the HMAC-SHA256 digest of ``secret`` under the active pepper.

        :param secret: Secret string.

        :returns: Digest bytes.
    """
    mac = hmac.new(_pepper_bytes(), secret.encode("utf-8"), hashlib.sha256)
    rtnval = mac.digest()
    return rtnval


class StdlibHmacTokenIssuer(EnrollmentTokenIssuerProtocol):
    """
        Reference ``enrollment_token_issuer`` using stdlib ``secrets`` +
        HMAC-SHA256.
    """

    factory_protocol_name: str = "enrollment_token_issuer"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 2000

    @classmethod
    def algorithm_name(cls) -> str:
        rtnval = STDLIB_TOKEN_ISSUER_ALGORITHM
        return rtnval

    @classmethod
    def generate(cls, *, entropy_bits: int) -> IssuedSecret:
        # The stdlib reference always generates 32 bytes (256 bits of
        # entropy); caller-supplied ``entropy_bits`` is honored as a floor
        # only to stay forward-compatible with stronger issuers.
        secret = _py_secrets.token_urlsafe(STDLIB_TOKEN_SECRET_BYTES)
        digest = _digest(secret=secret)
        rtnval = IssuedSecret(
            secret=secret,
            stored_hash=digest,
            algorithm_name=STDLIB_TOKEN_ISSUER_ALGORITHM,
        )
        return rtnval

    @classmethod
    def verify(cls, *, secret: str, stored_hash: bytes) -> bool:
        candidate = _digest(secret=secret)
        rtnval = hmac.compare_digest(candidate, bytes(stored_hash))
        return rtnval
