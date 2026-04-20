"""
.. module:: security.auth.factories.password_hasher
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: FactoryProtocolBase for pluggable password-hashing backends.

.. moduleauthor:: Automation Mojo LLC

The password hasher is a Layer E factory protocol so the service can
ship a stdlib-only fallback in-tree while letting operators install
stronger hashing (Argon2id, scrypt-on-GPU, HSM-backed) through an
extension pack without modifying the service source. The protocol is
keyed on ``algorithm_name`` — every persisted credential row carries
``algo_params['algorithm']`` so verification always selects the hasher
that produced the stored hash, even after an operator registers a
newer one at higher priority.

A production deployment installs an out-of-tree ``pychestrate-ext-auth-argon2id``
extension pack that registers at a lower PRECEDENCE than the in-tree
fallback; the registry resolves the Argon2id hasher first for new
hashes. Old stdlib-scrypt hashes continue to verify via lookup by
algorithm name.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, Type

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase
from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
    resolve_factory_implementation,
)
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes


@dataclass(frozen=True)
class EncodedHash:
    """
        The full result of hashing a password.

        :param encoded_bytes: Opaque bytes that carry everything the verifier
                              needs (salt + digest + params in whatever
                              encoding the concrete hasher chose).
        :param algorithm_name: Canonical algorithm identifier the hasher
                               declares via
                               :meth:`PasswordHasherProtocol.algorithm_name`.
        :param algo_params: Algorithm-specific parameters for auditability
                            and rehash-on-policy-change decisions. Must be
                            JSON-serializable.
    """
    encoded_bytes: bytes
    algorithm_name: str
    algo_params: Dict[str, Any] = field(default_factory=dict)


class PasswordHasherProtocol(FactoryProtocolBase):
    """
        Contract for any password-hashing implementation the auth flow
        will call. Implementations set :attr:`PRECEDENCE` to influence
        which hasher is chosen for fresh hashes; verification always
        targets the hasher whose ``algorithm_name`` matches the stored
        ``algo_params``.
    """

    factory_protocol_name: str = "password_hasher"
    protocol_schema_version: int = 1

    @classmethod
    def algorithm_name(cls) -> str:
        """
            Canonical algorithm identifier stored in ``algo_params``.

            :returns: The identifier string (e.g., ``"argon2id-64mib-3t"``).
        """
        raise NotImplementedError("Subclasses must implement algorithm_name")

    @classmethod
    def hash_password(
            cls,
            *,
            password: str,
            pepper: SecretBytes
        ) -> EncodedHash:
        """
            Hash ``password`` concatenated with the active pepper and
            return the :class:`EncodedHash` ready for persistence.

            :param password: Submitted plaintext password.
            :param pepper: Pre-loaded :class:`SecretBytes` from the pepper
                           loader. Implementations concatenate the pepper
                           with the password before calling the underlying
                           KDF; no hasher generates a pepper itself.

            :returns: Populated :class:`EncodedHash`.
        """
        raise NotImplementedError("Subclasses must implement hash_password")

    @classmethod
    def verify_password(
            cls,
            *,
            encoded_hash: bytes,
            password: str,
            pepper: SecretBytes
        ) -> bool:
        """
            Verify ``password`` against the stored encoded hash.

            :param encoded_hash: The bytes persisted in
                                 ``auth_local_credentials.argon2id_hash`` at
                                 hash time. (The column name is retained for
                                 schema compatibility; it holds whatever the
                                 registered hasher wrote.)
            :param password: Submitted plaintext password.
            :param pepper: Pre-loaded :class:`SecretBytes`.

            :returns: True on match, False on mismatch.
        """
        raise NotImplementedError("Subclasses must implement verify_password")


def resolve_hasher_for_hashing() -> Type[PasswordHasherProtocol]:
    """
        Return the highest-priority registered password hasher.

        :returns: The :class:`PasswordHasherProtocol` subclass to use for
                  new hashes.
        :raises: ConfigurationError when no hasher is registered.
    """
    rtnval = resolve_factory_implementation(
        factory_protocol_name="password_hasher",
        predicate=None,
    )
    return rtnval


def resolve_hasher_for_verifying(*, algorithm_name: str) -> Type[PasswordHasherProtocol]:
    """
        Return the registered hasher whose ``algorithm_name`` matches the
        supplied value. Falls back to the highest-priority hasher when
        ``algorithm_name`` is empty so callers on legacy rows without an
        algorithm tag still verify.

        :param algorithm_name: Algorithm tag from the stored ``algo_params``.

        :returns: The :class:`PasswordHasherProtocol` subclass to use.
        :raises: ConfigurationError when no matching hasher is registered.
    """
    if algorithm_name is None or len(algorithm_name) == 0:
        rtnval = resolve_hasher_for_hashing()
        return rtnval

    candidates = list_factory_implementations(factory_protocol_name="password_hasher")
    matched: Optional[Type[PasswordHasherProtocol]] = None
    for impl in candidates:
        if impl.algorithm_name() == algorithm_name:
            matched = impl
            break

    if matched is None:
        err_msg_lines = ["No registered password_hasher matches the stored algorithm."]
        err_msg_lines.append("ALGORITHM: {}".format(algorithm_name))
        err_msg_lines.append("REGISTERED: ({})".format(len(candidates)))
        for impl in candidates:
            err_msg_lines.append("    {} (PRECEDENCE={})".format(
                impl.algorithm_name(),
                getattr(impl, "PRECEDENCE", 1000),
            ))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    rtnval = matched
    return rtnval
