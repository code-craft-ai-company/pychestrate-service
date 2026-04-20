"""
.. module:: secrets.factories.local_backend
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference local AES-GCM + DEK wrap backend.

.. moduleauthor:: Automation Mojo LLC

The local backend generates a fresh 256-bit DEK per encrypt, AES-GCM
encrypts the plaintext under a random 96-bit nonce, then wraps the DEK
with the process-wide KEK via NIST AES Key Wrap (RFC 3394). The wrapped
DEK, the ciphertext+tag with its prepended nonce, and the KEK id are
returned to ``secrets_service.put_secret`` which persists them on the
:class:`SecretVersion` row.

The backend is stateless by design: the only I/O is the persistent row
the caller materializes and the KEK looked up through
:func:`get_active_kek`. That makes the backend easy to exercise from
tests and lets ``secrets_service`` remain the single place that owns
transactional semantics and audit emission.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import secrets as _py_secrets

from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.keywrap import aes_key_unwrap, aes_key_wrap

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.webservice.secrets.factories.secrets_backend import (
    BackendCapabilities,
    BackendReadResult,
    BackendWriteResult,
    SecretsBackendProtocol,
)
from automojo.pychestrate.webservice.secrets.kek_loader import get_active_kek
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.secrets.secrets_aspects import SecretsAspects


DEK_LENGTH_BYTES: int = 32
NONCE_LENGTH_BYTES: int = 12
KEK_WRAP_KEY_LENGTH_BYTES: int = 32


@dataclass(frozen=True)
class LocalCipherPayload:
    """
        The bytes the local backend returns to the service layer for
        persistence on a :class:`SecretVersion` row.

        :param ciphertext_bytes: ``nonce(12) || ciphertext_and_tag``.
        :param wrapped_dek: DEK wrapped under the active KEK.
        :param kek_id: Identifier of the KEK that wrapped the DEK.
    """
    ciphertext_bytes: bytes
    wrapped_dek: bytes
    kek_id: str


def _active_kek_bytes() -> bytes:
    """
        Return the raw active KEK bytes, validating the length required by
        AES Key Wrap. Bails with :class:`ConfigurationError` when the KEK
        is not exactly 32 bytes.

        :returns: The KEK bytes.
        :raises: ConfigurationError
    """
    handle = get_active_kek()
    material = handle.key_material.reveal()
    if len(material) != KEK_WRAP_KEY_LENGTH_BYTES:
        err_msg_lines = ["Active KEK material is not the required length for AES Key Wrap."]
        err_msg_lines.append("KEK_ID: {}".format(handle.kek_id))
        err_msg_lines.append("REQUIRED_BYTES: {}".format(KEK_WRAP_KEY_LENGTH_BYTES))
        err_msg_lines.append("ACTUAL_BYTES: {}".format(len(material)))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None
    return material


def encrypt_plaintext(*, plaintext: SecretBytes, secret_ref: str) -> LocalCipherPayload:
    """
        Encrypt ``plaintext`` under a fresh DEK and wrap the DEK with the
        active KEK. ``secret_ref`` is bound into the AEAD associated data
        so ciphertext from one secret cannot be substituted for another.

        :param plaintext: The :class:`SecretBytes` wrapping the payload.
        :param secret_ref: Canonical secret reference used as AEAD AD.

        :returns: :class:`LocalCipherPayload` carrying the bytes the
                  persistence layer should store on the version row.
    """
    dek = _py_secrets.token_bytes(DEK_LENGTH_BYTES)
    nonce = _py_secrets.token_bytes(NONCE_LENGTH_BYTES)

    aead = AESGCM(dek)
    raw = plaintext.reveal()
    associated = secret_ref.encode("utf-8")
    ciphertext_and_tag = aead.encrypt(nonce, raw, associated)

    kek_bytes = _active_kek_bytes()
    wrapped_dek = aes_key_wrap(kek_bytes, dek)

    rtnval = LocalCipherPayload(
        ciphertext_bytes=nonce + ciphertext_and_tag,
        wrapped_dek=wrapped_dek,
        kek_id=get_active_kek().kek_id,
    )
    return rtnval


def decrypt_ciphertext(
        *,
        ciphertext_bytes: bytes,
        wrapped_dek: bytes,
        secret_ref: str
    ) -> SecretBytes:
    """
        Decrypt the local-backend ciphertext written by
        :func:`encrypt_plaintext` back into a :class:`SecretBytes`.

        :param ciphertext_bytes: ``nonce || ciphertext_and_tag``.
        :param wrapped_dek: DEK wrapped under the active KEK.
        :param secret_ref: Canonical secret reference used as AEAD AD.

        :returns: The decrypted plaintext wrapped in :class:`SecretBytes`.
    """
    if len(ciphertext_bytes) < NONCE_LENGTH_BYTES + 1:
        err_msg_lines = ["Local ciphertext payload is too short to contain nonce + tag."]
        err_msg_lines.append("SECRET_REF: {}".format(secret_ref))
        err_msg_lines.append("ACTUAL_BYTES: {}".format(len(ciphertext_bytes)))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    nonce = ciphertext_bytes[:NONCE_LENGTH_BYTES]
    ciphertext_and_tag = ciphertext_bytes[NONCE_LENGTH_BYTES:]

    kek_bytes = _active_kek_bytes()
    dek = aes_key_unwrap(kek_bytes, wrapped_dek)

    aead = AESGCM(dek)
    associated = secret_ref.encode("utf-8")
    plaintext = aead.decrypt(nonce, ciphertext_and_tag, associated)

    rtnval = SecretBytes(plaintext)
    return rtnval


class LocalEncryptedSecretsBackend(SecretsBackendProtocol):
    """
        Reference ``secrets_backend`` implementation targeting the local
        ``phase1_secrets`` / ``phase1_secret_versions`` tables. Claims
        ``namespace_pattern = "*"`` so it serves any ref that is not
        taken by a higher-priority backend.

        The backend's ``write`` / ``read`` / ``rotate`` calls are pure
        crypto helpers: they produce / consume :class:`LocalCipherPayload`
        objects. Transaction and audit semantics live in the paired
        :mod:`secrets_service` module which coordinates the version row
        insert, the ACL check, and the audit capture inside a single DB
        transaction.
    """

    factory_protocol_name: str = "secrets_backend"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def namespace_pattern(cls) -> str:
        rtnval = "*"
        return rtnval

    @classmethod
    def capabilities(cls) -> BackendCapabilities:
        rtnval = BackendCapabilities(
            supports_native_rotation=False,
            supports_audit_tap=False,
            stores_ciphertext=True,
        )
        return rtnval

    @classmethod
    def write_secret(
            cls,
            *,
            secret_ref: str,
            plaintext: SecretBytes,
            aspects: SecretsAspects
        ) -> BackendWriteResult:
        """
            Produce the crypto payload that ``secrets_service`` will
            persist on a new version row. The backend never touches the
            session; persistence lives in the service layer.

            :param secret_ref: Canonical secret reference.
            :param plaintext: Wrapped plaintext bytes.
            :param aspects: Behavior knobs from the caller (unused here
                            beyond propagating the opaque aspects object).

            :returns: :class:`BackendWriteResult` carrying the ciphertext
                      ref format string, the wrapped DEK, and the KEK id.
        """
        payload = encrypt_plaintext(plaintext=plaintext, secret_ref=secret_ref)
        rtnval = BackendWriteResult(
            ciphertext_ref=None,
            wrapped_dek=payload.wrapped_dek,
            kek_id=payload.kek_id,
        )
        # The caller persists ``payload.ciphertext_bytes`` onto the version
        # row's ``ciphertext_bytes`` column. The backend write result does
        # not carry the bytes to keep the protocol surface the same for
        # external backends which don't hold ciphertext in-service.
        # Callers use :func:`encrypt_plaintext` directly when they need
        # both halves — see ``secrets_service.put_secret``.
        return rtnval

    @classmethod
    def read_secret(
            cls,
            *,
            secret_ref: str,
            version_id: Optional[str],
            aspects: SecretsAspects
        ) -> BackendReadResult:
        """
            The local backend's read path is exercised by the service
            layer calling :func:`decrypt_ciphertext` directly using the
            bytes already loaded from the version row. This method is
            provided for protocol-surface completeness but returns an
            empty plaintext wrapper — the service layer never calls it.

            :param secret_ref: Canonical secret reference.
            :param version_id: Specific version id; None means active.
            :param aspects: Behavior knobs from the caller.

            :returns: A :class:`BackendReadResult` with an empty wrapper.
        """
        rtnval = BackendReadResult(
            plaintext=SecretBytes(b""),
            version_number=0,
        )
        return rtnval

    @classmethod
    def rotate_secret(
            cls,
            *,
            secret_ref: str,
            new_plaintext: SecretBytes,
            grace_seconds: int,
            aspects: SecretsAspects
        ) -> BackendWriteResult:
        """
            Rotation is a new encrypt with a fresh DEK.

            :param secret_ref: Canonical secret reference.
            :param new_plaintext: New plaintext to encrypt.
            :param grace_seconds: Grace window in seconds; the caller
                                  writes ``grace_expires_at`` on the
                                  previous version row.
            :param aspects: Behavior knobs from the caller.

            :returns: :class:`BackendWriteResult`.
        """
        rtnval = cls.write_secret(
            secret_ref=secret_ref,
            plaintext=new_plaintext,
            aspects=aspects,
        )
        return rtnval

    @classmethod
    def delete_secret(
            cls,
            *,
            secret_ref: str,
            aspects: SecretsAspects
        ) -> None:
        """
            Deletion is a DB-only operation handled by the service layer;
            the local backend has no external storage to clean up.

            :returns: None.
        """
        return
