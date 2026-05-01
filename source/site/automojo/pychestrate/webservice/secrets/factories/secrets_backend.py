"""
.. module:: secrets.factories.secrets_backend
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: FactoryProtocolBase for pluggable secrets backends.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Optional

from automojo.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.secrets.secrets_aspects import SecretsAspects


@dataclass(frozen=True)
class BackendCapabilities:
    """
        Capability flags declared by a ``secrets_backend`` implementation.

        :param supports_native_rotation: True if the backend rotates atomically.
        :param supports_audit_tap: True if the backend emits its own audit trail.
        :param stores_ciphertext: True if the backend holds bytes itself.
    """
    supports_native_rotation: bool
    supports_audit_tap: bool
    stores_ciphertext: bool


@dataclass(frozen=True)
class BackendWriteResult:
    """
        Result returned by a backend write.

        :param ciphertext_ref: Opaque backend id (None for backends that store nothing).
        :param wrapped_dek: AES-wrapped DEK (None for delegated backends).
        :param kek_id: KEK id used when the backend is local.
    """
    ciphertext_ref: Optional[str]
    wrapped_dek: Optional[bytes]
    kek_id: Optional[str]


@dataclass(frozen=True)
class BackendReadResult:
    """
        Result returned by a backend read.

        :param plaintext: The resolved plaintext wrapped in :class:`SecretBytes`.
        :param version_number: Monotonic version number that served the read.
    """
    plaintext: SecretBytes
    version_number: int


class SecretsBackendProtocol(FactoryProtocolBase):
    """
        Contract for a ``secrets_backend`` implementation.
    """

    factory_protocol_name: str = "secrets_backend"
    protocol_schema_version: int = 1

    is_published: bool = True
    published_docs_url: str = "https://docs.pychestrate.io/plugin-api/secrets_backend"
    published_reference: str = (
        "automojo.pychestrate.webservice.secrets.factories.local_backend"
        ".LocalEncryptedSecretsBackend"
    )

    @classmethod
    def namespace_pattern(cls) -> str:
        """
            Glob pattern matched against ``secret_ref`` to claim a namespace.

            :returns: The pattern string.
        """
        raise NotImplementedError("Subclasses must implement namespace_pattern")

    @classmethod
    def capabilities(cls) -> BackendCapabilities:
        """
            Return the declared capability flags for this backend.

            :returns: The :class:`BackendCapabilities`.
        """
        raise NotImplementedError("Subclasses must implement capabilities")

    @classmethod
    def write_secret(
            cls,
            *,
            secret_ref: str,
            plaintext: SecretBytes,
            aspects: SecretsAspects
        ) -> BackendWriteResult:
        """
            Persist a new secret version.

            :param secret_ref: Canonical ref.
            :param plaintext: Wrapped plaintext bytes.
            :param aspects: Behavior knobs from the caller.

            :returns: The :class:`BackendWriteResult`.
        """
        raise NotImplementedError("Subclasses must implement write_secret")

    @classmethod
    def read_secret(
            cls,
            *,
            secret_ref: str,
            version_id: Optional[str],
            aspects: SecretsAspects
        ) -> BackendReadResult:
        """
            Resolve a secret ref to plaintext.

            :param secret_ref: Canonical ref.
            :param version_id: Specific version id; None means active.
            :param aspects: Behavior knobs from the caller.

            :returns: The :class:`BackendReadResult`.
        """
        raise NotImplementedError("Subclasses must implement read_secret")

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
            Rotate a secret in place.

            :returns: The :class:`BackendWriteResult`.
        """
        raise NotImplementedError("Subclasses must implement rotate_secret")

    @classmethod
    def delete_secret(
            cls,
            *,
            secret_ref: str,
            aspects: SecretsAspects
        ) -> None:
        """
            Delete a secret and all versions.

            :returns: None.
        """
        raise NotImplementedError("Subclasses must implement delete_secret")
