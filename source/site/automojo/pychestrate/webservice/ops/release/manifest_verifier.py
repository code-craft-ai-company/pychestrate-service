"""
.. module:: ops.release.manifest_verifier
    :synopsis: Manifest + signature verification against ``trusted_issuer_keys``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)
from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.ops.release.errors import (
    ManifestVerificationError,
)
from automojo.pychestrate.webservice.ops.release.models import (
    TrustedIssuerKey,
)


@dataclass(frozen=True)
class ManifestVerificationResult:
    """
        Verifier verdict.

        :param verified: ``True`` when the signature checks
                         out against a still-valid trusted
                         key.
        :param issuer_key_id: Key id that produced the
                              successful verify (or ``None``
                              on failure).
        :param reason: Stable token when not verified —
                       ``"unknown_issuer"``,
                       ``"key_expired"``,
                       ``"signature_invalid"``.
    """
    verified: bool
    issuer_key_id: Optional[str] = None
    reason: Optional[str] = None


def verify_manifest(
        *,
        db_session: DbSession,
        manifest_bytes: bytes,
        signature: bytes,
        issuer_key_id: str,
        now=None
    ) -> ManifestVerificationResult:
    """
        Verify a manifest + signature against the persisted
        ``release_trusted_issuer_keys`` row identified by
        ``issuer_key_id``.

        :raises: ManifestVerificationError when the lookup
                 returns no row at all (vs. a failed compare,
                 which is a normal verdict).
    """
    row = (
        db_session.query(TrustedIssuerKey)
        .filter(TrustedIssuerKey.issuer_key_id == issuer_key_id)
        .first()
    )
    if row is None:
        err_lines = ["No trusted issuer key registered for the supplied id."]
        err_lines.append("ISSUER_KEY_ID: {}".format(issuer_key_id))
        err_msg = os.linesep.join(err_lines)
        raise ManifestVerificationError(err_msg) from None
    if row.valid_until is not None and now is not None and now > row.valid_until:
        rtnval = ManifestVerificationResult(
            verified=False,
            issuer_key_id=issuer_key_id,
            reason="key_expired",
        )
        return rtnval
    public = Ed25519PublicKey.from_public_bytes(row.public_key_bytes)
    try:
        public.verify(signature, manifest_bytes)
    except InvalidSignature:
        rtnval = ManifestVerificationResult(
            verified=False,
            issuer_key_id=issuer_key_id,
            reason="signature_invalid",
        )
        return rtnval
    rtnval = ManifestVerificationResult(
        verified=True, issuer_key_id=issuer_key_id,
    )
    return rtnval


def register_trusted_issuer_key(
        *,
        db_session: DbSession,
        issuer_key_id: str,
        public_key_bytes: bytes,
        valid_from=None,
        valid_until=None,
        replaced_by: Optional[str] = None
    ) -> TrustedIssuerKey:
    """
        Insert (or update) a row in
        ``release_trusted_issuer_keys``. Idempotent on
        ``issuer_key_id`` — the public key is replaced when an
        existing row is found, allowing the bootstrap and the
        rotation paths to share an entry point.
    """
    row = (
        db_session.query(TrustedIssuerKey)
        .filter(TrustedIssuerKey.issuer_key_id == issuer_key_id)
        .first()
    )
    if row is None:
        row = TrustedIssuerKey(
            issuer_key_id=issuer_key_id,
            public_key_bytes=public_key_bytes,
            valid_from=valid_from,
            valid_until=valid_until,
            replaced_by=replaced_by,
        )
        db_session.add(row)
    else:
        row.public_key_bytes = public_key_bytes
        if valid_from is not None:
            row.valid_from = valid_from
        row.valid_until = valid_until
        row.replaced_by = replaced_by
    db_session.flush()
    return row
