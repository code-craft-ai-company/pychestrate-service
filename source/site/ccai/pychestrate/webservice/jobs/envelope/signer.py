"""
.. module:: jobs.envelope.signer
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Ed25519 signing + verification helpers for JobEnvelope.

.. moduleauthor:: Code Craft AI LLC

Wraps ``cryptography.hazmat.primitives.asymmetric.ed25519`` with a
module-level active-key / JWKS registry so the codec's ``sign`` and
``verify`` stay simple. The signing key is installed at service
startup via :func:`set_active_signing_key`; the JWKS-style verify set
is populated via :func:`register_verify_key` (multiple public keys can
be registered to support rotation).

M1 scope: the signing key is loaded from an env var
(``PYCHESTRATE_ENVELOPE_SIGNING_KEY``) in dev mode or supplied as raw
bytes via :func:`set_active_signing_key`. M2 replaces the dev-mode
loader with a ``1-secrets-vault`` fetch + rotation subscriber.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import os

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.jobs.envelope.errors import (
    EnvelopeSigningKeyMissingError,
)


@dataclass(frozen=True)
class SigningKeyHandle:
    """
        A loaded Ed25519 signing key with its JWKS-style ``key_id``.

        :param key_id: Operator-assigned identifier for the key
                       pair; surfaces on every signed envelope.
        :param private_key: Ed25519 private key used by :func:`sign`.
        :param public_key: Matching public key; also auto-registered
                           for verification.
    """
    key_id: str
    private_key: Ed25519PrivateKey
    public_key: Ed25519PublicKey


@dataclass(frozen=True)
class VerificationResult:
    """
        Outcome returned by :func:`verify`.

        :param valid: Whether the signature verified.
        :param reason: Short code (empty on success) describing the
                       failure:
                       ``"signature_mismatch"``,
                       ``"unknown_key"``,
                       ``"expired"`` (checked by the codec, not here).
    """
    valid: bool
    reason: str


_ACTIVE_SIGNING_KEY: Optional[SigningKeyHandle] = None
_VERIFY_KEYS: Dict[str, Ed25519PublicKey] = {}


def set_active_signing_key(*, handle: SigningKeyHandle) -> None:
    """
        Install the currently-active signing key. Also auto-registers
        the matching public key in the verify set so a process can
        verify its own signed envelopes without extra wiring.

        :param handle: The :class:`SigningKeyHandle` returned by
                       :func:`load_signing_key_at_startup` or built
                       directly by a deployer.

        :returns: None.
    """
    global _ACTIVE_SIGNING_KEY
    _ACTIVE_SIGNING_KEY = handle
    _VERIFY_KEYS[handle.key_id] = handle.public_key
    return


def get_active_signing_key() -> SigningKeyHandle:
    """
        Return the currently-installed signing key handle or raise.

        :returns: The active signing key.
        :raises: EnvelopeSigningKeyMissingError when none is installed.
    """
    handle = _ACTIVE_SIGNING_KEY
    if handle is None:
        err_lines = ["No envelope signing key is installed."]
        err_lines.append(
            "HINT: call load_signing_key_at_startup() + set_active_signing_key() "
            "from the service bootstrap."
        )
        err_msg = os.linesep.join(err_lines)
        raise EnvelopeSigningKeyMissingError(err_msg) from None
    return handle


def register_verify_key(
        *,
        key_id: str,
        public_key: Ed25519PublicKey
    ) -> None:
    """
        Register an additional public key in the JWKS-style verify
        set. Used by rotation to keep the previous generation's
        signatures verifiable through the grace window.

        :param key_id: JWKS key id the signed envelope references.
        :param public_key: :class:`Ed25519PublicKey` to verify with.

        :returns: None.
    """
    _VERIFY_KEYS[key_id] = public_key
    return


def reset_for_testing() -> None:
    """
        Clear the active signing key and every registered verify key.
        Intended for the test suite only.

        :returns: None.
    """
    global _ACTIVE_SIGNING_KEY
    _ACTIVE_SIGNING_KEY = None
    _VERIFY_KEYS.clear()
    return


def load_signing_key_at_startup(
        *,
        source: str,
        file_path: Optional[str] = None,
        env_var: Optional[str] = None,
        key_id: str
    ) -> SigningKeyHandle:
    """
        Load the Ed25519 signing key from an operator-supplied source.
        Mirrors the :func:`secrets.kek_loader.load_kek_at_startup`
        shape so deployment wiring is uniform across KEK / CA /
        envelope-signing material.

        The M1 loader accepts raw 32-byte seeds (produced by
        :func:`generate_dev_signing_key`). It does NOT yet support
        PKCS#8 PEM — that lands when the ``1-secrets-vault`` fetch
        path wires up in M2.

        :param source: ``"file"`` or ``"env"``.
        :param file_path: Path to a file whose content is a base64-
                          encoded Ed25519 seed when
                          ``source="file"``.
        :param env_var: Environment variable holding the same base64
                        content when ``source="env"``.
        :param key_id: Operator-assigned identifier published in
                       signed envelopes.

        :returns: Populated :class:`SigningKeyHandle`.
        :raises: ConfigurationError when the source cannot be read or
                 the seed is malformed.
    """
    if source == "file":
        if file_path is None or len(file_path) == 0:
            err_lines = ["Signing key source 'file' requires file_path."]
            err_msg = os.linesep.join(err_lines)
            raise ConfigurationError(err_msg) from None
        try:
            with open(file_path, "rb") as handle:
                raw = handle.read()
        except OSError as xcpt:
            err_lines = ["Cannot load signing key — file read failed."]
            err_lines.append("PATH: {}".format(file_path))
            err_lines.append("REASON: {}".format(str(xcpt)))
            err_msg = os.linesep.join(err_lines)
            raise ConfigurationError(err_msg) from xcpt
    elif source == "env":
        if env_var is None or len(env_var) == 0:
            err_lines = ["Signing key source 'env' requires env_var."]
            err_msg = os.linesep.join(err_lines)
            raise ConfigurationError(err_msg) from None
        value = os.environ.get(env_var, None)
        if value is None or len(value) == 0:
            err_lines = ["Cannot load signing key — env var is empty."]
            err_lines.append("ENV_VAR: {}".format(env_var))
            err_msg = os.linesep.join(err_lines)
            raise ConfigurationError(err_msg) from None
        raw = value.encode("ascii")
    else:
        err_lines = ["Unsupported signing key source."]
        err_lines.append("SOURCE: {}".format(source))
        err_lines.append("SUPPORTED: (file, env)")
        err_msg = os.linesep.join(err_lines)
        raise ConfigurationError(err_msg) from None

    try:
        seed = base64.b64decode(raw.strip(), validate=True)
    except Exception as xcpt:
        err_lines = ["Cannot load signing key — base64 decode failed."]
        err_lines.append("REASON: {}".format(str(xcpt)))
        err_msg = os.linesep.join(err_lines)
        raise ConfigurationError(err_msg) from xcpt

    if len(seed) != 32:
        err_lines = ["Cannot load signing key — Ed25519 seed must be exactly 32 bytes."]
        err_lines.append("RECEIVED_BYTES: {}".format(len(seed)))
        err_msg = os.linesep.join(err_lines)
        raise ConfigurationError(err_msg) from None

    private_key = Ed25519PrivateKey.from_private_bytes(seed)
    public_key = private_key.public_key()

    rtnval = SigningKeyHandle(
        key_id=key_id,
        private_key=private_key,
        public_key=public_key,
    )
    return rtnval


def generate_dev_signing_key(*, key_id: str) -> SigningKeyHandle:
    """
        Produce a fresh Ed25519 handle for tests and local dev. Real
        deployments source material through ``1-secrets-vault``.

        :param key_id: Operator-assigned identifier.

        :returns: Populated :class:`SigningKeyHandle`.
    """
    private_key = Ed25519PrivateKey.generate()
    rtnval = SigningKeyHandle(
        key_id=key_id,
        private_key=private_key,
        public_key=private_key.public_key(),
    )
    return rtnval


#: JWKS-style algorithm label published for every Ed25519 key.
ED25519_ALGORITHM_NAME: str = "Ed25519"


def public_key_to_pem(*, public_key: Ed25519PublicKey) -> str:
    """
        Serialize an Ed25519 public key to a SubjectPublicKeyInfo PEM
        string. Only the public half is serialized — this function
        never touches private key material.

        :param public_key: The :class:`Ed25519PublicKey` to encode.

        :returns: PEM-encoded public key text (``-----BEGIN PUBLIC
                  KEY-----`` block, trailing newline included).
    """
    pem_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    rtnval = pem_bytes.decode("ascii")
    return rtnval


def active_signing_key_set() -> List[Dict[str, Any]]:
    """
        Build the JWKS-style public-key set for distribution to job-
        envelope-verifying clients. The list carries one entry per
        registered verify key; the entry matching the active signing
        key is marked ``"active"`` and every other entry is marked
        ``"retiring"`` (rotation grace-window keys).

        Only public key material is serialized — the private signing
        key never leaves this process.

        :returns: List of dicts, each with ``key_id``, ``algorithm``,
                  ``public_key_pem``, and ``status`` members. Empty
                  when no signing key is installed.
    """
    handle = _ACTIVE_SIGNING_KEY
    if handle is None:
        rtnval: List[Dict[str, Any]] = []
        return rtnval

    active_key_id = handle.key_id

    rtnval = []
    for key_id in sorted(_VERIFY_KEYS.keys()):
        public_key = _VERIFY_KEYS[key_id]
        if key_id == active_key_id:
            status = "active"
        else:
            status = "retiring"
        entry = {
            "key_id": key_id,
            "algorithm": ED25519_ALGORITHM_NAME,
            "public_key_pem": public_key_to_pem(public_key=public_key),
            "status": status,
        }
        rtnval.append(entry)
    return rtnval


def sign(*, payload: bytes) -> bytes:
    """
        Sign the supplied canonical bytes with the active signing
        key.

        :param payload: Canonical envelope bytes.

        :returns: Detached Ed25519 signature (64 bytes).
        :raises: EnvelopeSigningKeyMissingError when no key is
                 installed.
    """
    handle = get_active_signing_key()
    rtnval = handle.private_key.sign(payload)
    return rtnval


def verify(
        *,
        payload: bytes,
        signature: bytes,
        key_id: str
    ) -> VerificationResult:
    """
        Verify a detached Ed25519 signature against the public key
        registered under ``key_id``. Returns a structured result
        rather than raising so transport-layer callers can log the
        rejection reason without catching an exception.

        :param payload: Canonical envelope bytes.
        :param signature: Detached signature bytes.
        :param key_id: The signed envelope's ``key_id`` claim.

        :returns: :class:`VerificationResult`.
    """
    public_key = _VERIFY_KEYS.get(key_id, None)
    if public_key is None:
        rtnval = VerificationResult(valid=False, reason="unknown_key")
        return rtnval
    try:
        public_key.verify(signature, payload)
    except InvalidSignature:
        rtnval = VerificationResult(valid=False, reason="signature_mismatch")
        return rtnval
    rtnval = VerificationResult(valid=True, reason="")
    return rtnval
