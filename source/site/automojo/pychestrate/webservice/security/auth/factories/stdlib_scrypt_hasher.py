"""
.. module:: security.auth.factories.stdlib_scrypt_hasher
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Stdlib-only scrypt password hasher reference implementation.

.. moduleauthor:: Automation Mojo LLC

This reference implementation is intentionally stdlib-only so the
service ships with a working password hasher out of the box without a
third-party dependency. For production deployments, operators install a
``pychestrate-ext-auth-argon2id`` extension pack that registers at a
lower ``PRECEDENCE`` than this class; the registry resolves the
Argon2id hasher first for new hashes while old stdlib-scrypt hashes
continue to verify through the algorithm-name lookup path.

Parameters:

- ``n = 16384`` (cost factor — power of two)
- ``r = 8`` (block size)
- ``p = 1`` (parallelism)
- ``salt`` = 16 random bytes per hash
- ``dklen = 32`` bytes derived

Encoded storage format:

    ``phase1-scrypt$n=<N>,r=<R>,p=<P>$<base64 salt>$<base64 digest>``

The format is self-describing so a rotation to different cost
parameters can still verify older rows.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import hashlib
import hmac
import os
import secrets as _py_secrets

from typing import Dict

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.security.auth.factories.password_hasher import (
    EncodedHash,
    PasswordHasherProtocol,
)


SCRYPT_ALGORITHM_NAME: str = "phase1-scrypt"
SCRYPT_N: int = 16384
SCRYPT_R: int = 8
SCRYPT_P: int = 1
SCRYPT_DKLEN: int = 32
SCRYPT_SALT_LEN_BYTES: int = 16
SCRYPT_MAXMEM_BYTES: int = 128 * SCRYPT_N * SCRYPT_R * 4


def _encode_hash(*, salt: bytes, digest: bytes, n: int, r: int, p: int) -> bytes:
    """
        Build the canonical encoded-hash bytes for the stdlib-scrypt hasher.

        :param salt: Random salt bytes.
        :param digest: KDF digest bytes.
        :param n: scrypt cost factor.
        :param r: scrypt block size.
        :param p: scrypt parallelism.

        :returns: Encoded bytes ready for persistence.
    """
    salt_b64 = base64.b64encode(salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    encoded = "{alg}$n={n},r={r},p={p}${salt}${digest}".format(
        alg=SCRYPT_ALGORITHM_NAME,
        n=n, r=r, p=p,
        salt=salt_b64,
        digest=digest_b64,
    )
    rtnval = encoded.encode("utf-8")
    return rtnval


def _decode_hash(*, encoded: bytes) -> Dict[str, object]:
    """
        Parse an encoded stdlib-scrypt hash into its component fields.

        :param encoded: Encoded bytes written by :func:`_encode_hash`.

        :returns: Dict with keys ``n``, ``r``, ``p``, ``salt``, ``digest``.
        :raises: ConfigurationError when the encoded value is malformed.
    """
    text = encoded.decode("utf-8")
    parts = text.split("$")
    if len(parts) != 4:
        err_msg_lines = ["Malformed stdlib-scrypt encoded hash."]
        err_msg_lines.append("PARTS: {}".format(len(parts)))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    algorithm, params_str, salt_b64, digest_b64 = parts
    if algorithm != SCRYPT_ALGORITHM_NAME:
        err_msg_lines = ["Encoded hash algorithm tag does not match stdlib-scrypt."]
        err_msg_lines.append("TAG: {}".format(algorithm))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    params: Dict[str, int] = {}
    for chunk in params_str.split(","):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        params[key.strip()] = int(value.strip())

    if "n" not in params or "r" not in params or "p" not in params:
        err_msg_lines = ["Stdlib-scrypt parameters missing from encoded hash."]
        err_msg_lines.append("PARAMS: {}".format(params_str))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    salt = base64.b64decode(salt_b64)
    digest = base64.b64decode(digest_b64)
    rtnval = {
        "n": params["n"],
        "r": params["r"],
        "p": params["p"],
        "salt": salt,
        "digest": digest,
    }
    return rtnval


def _scrypt_digest(*, peppered: bytes, salt: bytes, n: int, r: int, p: int) -> bytes:
    """
        Run ``hashlib.scrypt`` with the supplied parameters.

        :param peppered: ``password_bytes + pepper_bytes``.
        :param salt: Random salt bytes.
        :param n: Cost factor.
        :param r: Block size.
        :param p: Parallelism.

        :returns: Derived key bytes of length :data:`SCRYPT_DKLEN`.
    """
    maxmem = 128 * n * r * 4
    if maxmem < SCRYPT_MAXMEM_BYTES:
        maxmem = SCRYPT_MAXMEM_BYTES

    digest = hashlib.scrypt(
        password=peppered,
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=SCRYPT_DKLEN,
        maxmem=maxmem,
    )
    return digest


class StdlibScryptPasswordHasher(PasswordHasherProtocol):
    """
        Stdlib ``hashlib.scrypt``-backed password hasher.

        Serves as the default in-tree ``password_hasher`` so Pychestrate
        boots with a working local login path without pulling any
        third-party crypto dependency. Production deployments install a
        stronger hasher (Argon2id, HSM-backed, …) via an extension pack.
    """

    factory_protocol_name: str = "password_hasher"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 2000

    @classmethod
    def algorithm_name(cls) -> str:
        rtnval = SCRYPT_ALGORITHM_NAME
        return rtnval

    @classmethod
    def hash_password(
            cls,
            *,
            password: str,
            pepper: SecretBytes
        ) -> EncodedHash:
        salt = _py_secrets.token_bytes(SCRYPT_SALT_LEN_BYTES)
        peppered = password.encode("utf-8") + pepper.reveal()
        digest = _scrypt_digest(
            peppered=peppered,
            salt=salt,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
        )
        encoded_bytes = _encode_hash(
            salt=salt,
            digest=digest,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
        )
        rtnval = EncodedHash(
            encoded_bytes=encoded_bytes,
            algorithm_name=SCRYPT_ALGORITHM_NAME,
            algo_params={
                "algorithm": SCRYPT_ALGORITHM_NAME,
                "n": SCRYPT_N,
                "r": SCRYPT_R,
                "p": SCRYPT_P,
                "dklen": SCRYPT_DKLEN,
                "salt_len": SCRYPT_SALT_LEN_BYTES,
            },
        )
        return rtnval

    @classmethod
    def verify_password(
            cls,
            *,
            encoded_hash: bytes,
            password: str,
            pepper: SecretBytes
        ) -> bool:
        try:
            parsed = _decode_hash(encoded=encoded_hash)
        except ConfigurationError:
            return False

        peppered = password.encode("utf-8") + pepper.reveal()
        candidate = _scrypt_digest(
            peppered=peppered,
            salt=bytes(parsed["salt"]),
            n=int(parsed["n"]),
            r=int(parsed["r"]),
            p=int(parsed["p"]),
        )
        expected = bytes(parsed["digest"])
        rtnval = hmac.compare_digest(candidate, expected)
        return rtnval
