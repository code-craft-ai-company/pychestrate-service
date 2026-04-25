"""
.. module:: ops.release.manifest_signer
    :synopsis: Ed25519 release-manifest signer.

The signer holds the active private key in process memory for
the M1 reference path. The dedicated subprocess isolation
called out in design.md (with seccomp, redacted stderr, and
fd hygiene) lands in M3 hardening; the M1 surface is shaped
so the subprocess swap-in is a behind-the-call replacement.

Module-level singletons:

* ``_ACTIVE_KEY`` — the loaded :class:`SigningKey` produced by
  :func:`load_signing_key`. ``set_active_signing_key`` is the
  canonical write entry point used by the bootstrap path and
  the test reset helper.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import threading

from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from automojo.pychestrate.webservice.ops.release.errors import (
    ReleaseSigningKeyUnavailableError,
)


@dataclass(frozen=True)
class SigningKey:
    """
        Active signing key bundle. The private key is held in
        memory for the M1 reference path; M3 promotes this
        bundle to a handle that proxies into the dedicated
        signer subprocess.
    """
    issuer_key_id: str
    private_key_bytes: bytes
    public_key_bytes: bytes


_LOCK = threading.RLock()
_ACTIVE_KEY: Optional[SigningKey] = None


def generate_signing_key(*, issuer_key_id: str) -> SigningKey:
    """
        Generate a fresh Ed25519 keypair bundled into a
        :class:`SigningKey`. Useful for tests and the
        bootstrap path's "first run" key install.

        :param issuer_key_id: Operator-assigned key id.

        :returns: :class:`SigningKey`.
    """
    private = Ed25519PrivateKey.generate()
    private_bytes = _serialize_private(key=private)
    public = private.public_key()
    public_bytes = _serialize_public(key=public)
    rtnval = SigningKey(
        issuer_key_id=issuer_key_id,
        private_key_bytes=private_bytes,
        public_key_bytes=public_bytes,
    )
    return rtnval


def load_signing_key(
        *,
        issuer_key_id: str,
        private_key_bytes: bytes
    ) -> SigningKey:
    """
        Wrap caller-supplied raw private key bytes into a
        :class:`SigningKey` bundle. Raises
        :class:`ReleaseSigningKeyUnavailableError` on a
        malformed payload.
    """
    if private_key_bytes is None or len(private_key_bytes) == 0:
        err_lines = ["Cannot load signing key from empty private bytes."]
        err_lines.append("ISSUER_KEY_ID: {}".format(issuer_key_id))
        err_msg = os.linesep.join(err_lines)
        raise ReleaseSigningKeyUnavailableError(err_msg) from None
    try:
        private = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    except Exception as load_err:
        err_lines = ["Failed to load Ed25519 private key bytes."]
        err_lines.append("ISSUER_KEY_ID: {}".format(issuer_key_id))
        err_lines.append("DETAIL: {}".format(load_err))
        err_msg = os.linesep.join(err_lines)
        raise ReleaseSigningKeyUnavailableError(err_msg) from None
    public_bytes = _serialize_public(key=private.public_key())
    rtnval = SigningKey(
        issuer_key_id=issuer_key_id,
        private_key_bytes=private_key_bytes,
        public_key_bytes=public_bytes,
    )
    return rtnval


def set_active_signing_key(*, key: SigningKey) -> None:
    """
        Install ``key`` as the active signing bundle. Called
        by the bootstrap once at startup; tests use the
        :func:`reset_for_testing` helper.
    """
    global _ACTIVE_KEY
    with _LOCK:
        _ACTIVE_KEY = key
    return


def get_active_signing_key() -> SigningKey:
    """
        Return the active signing key.

        :raises: ReleaseSigningKeyUnavailableError when no key
                 has been installed.
    """
    with _LOCK:
        active = _ACTIVE_KEY
    if active is None:
        err_lines = ["No active release signing key has been installed."]
        err_msg = os.linesep.join(err_lines)
        raise ReleaseSigningKeyUnavailableError(err_msg) from None
    return active


def reset_for_testing() -> None:
    """
        Drop the active signing key. Used by tests to keep the
        module-level singleton from leaking across cases.
    """
    global _ACTIVE_KEY
    with _LOCK:
        _ACTIVE_KEY = None
    return


def sign_manifest(
        *,
        manifest_bytes: bytes,
        issuer_key_id: Optional[str] = None
    ) -> bytes:
    """
        Produce a detached Ed25519 signature over
        ``manifest_bytes`` using the active signing key.

        :param manifest_bytes: Canonical serialized manifest
                               bytes; the caller owns the
                               canonicalization.
        :param issuer_key_id: Optional explicit key id; when
                              ``None`` the active key's id is
                              used. The function raises
                              :class:`ReleaseSigningKeyUnavailableError`
                              when ``issuer_key_id`` is set
                              but does not match the active
                              key — preventing an accidental
                              cross-key signature.

        :returns: Detached signature bytes.
        :raises: ReleaseSigningKeyUnavailableError.
    """
    active = get_active_signing_key()
    if issuer_key_id is not None and issuer_key_id != active.issuer_key_id:
        err_lines = ["Active signing key does not match requested issuer."]
        err_lines.append("REQUESTED: {}".format(issuer_key_id))
        err_lines.append("ACTIVE: {}".format(active.issuer_key_id))
        err_msg = os.linesep.join(err_lines)
        raise ReleaseSigningKeyUnavailableError(err_msg) from None
    private = Ed25519PrivateKey.from_private_bytes(
        active.private_key_bytes,
    )
    signature = private.sign(manifest_bytes)
    rtnval = signature
    return rtnval


def _serialize_private(*, key: Ed25519PrivateKey) -> bytes:
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
    )
    rtnval = key.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )
    return rtnval


def _serialize_public(*, key: Ed25519PublicKey) -> bytes:
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
    )
    rtnval = key.public_bytes(
        encoding=Encoding.Raw, format=PublicFormat.Raw,
    )
    return rtnval
