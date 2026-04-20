"""
.. module:: secrets.kek_loader
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: KEK bootstrap loader at service startup.

.. moduleauthor:: Automation Mojo LLC

The KEK (Key Encryption Key) is loaded once at service startup from an
operator-owned source and used by the local backend to wrap per-version
DEKs. The M1 skeleton supports the ``file`` and ``env`` sources; the
``kms`` source lands when the KMS shim protocol is declared.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from typing import Optional

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes


@dataclass(frozen=True)
class KekHandle:
    """
        A loaded KEK reference.

        :param kek_id: Operator-assigned identifier for the loaded KEK.
        :param key_material: Opaque byte material wrapped in :class:`SecretBytes`.
        :param source: Short string describing where the KEK was loaded from.
    """
    kek_id: str
    key_material: SecretBytes
    source: str


_ACTIVE_KEK: Optional[KekHandle] = None


def set_active_kek(*, kek: KekHandle) -> None:
    """
        Register the active KEK handle for the process. The local
        secrets backend reads the active KEK via :func:`get_active_kek`.

        :param kek: The :class:`KekHandle` returned by
                    :func:`load_kek_at_startup`.

        :returns: None.
    """
    global _ACTIVE_KEK
    _ACTIVE_KEK = kek
    return


def get_active_kek() -> KekHandle:
    """
        Return the active KEK handle for the process.

        :returns: The :class:`KekHandle` installed via :func:`set_active_kek`.
        :raises: ConfigurationError when no KEK has been loaded.
    """
    if _ACTIVE_KEK is None:
        raise ConfigurationError(
            "No active KEK is loaded. Call set_active_kek(kek=load_kek_at_startup(...)) "
            "during service bootstrap before the secrets backend is used."
        )
    rtnval = _ACTIVE_KEK
    return rtnval


def reset_active_kek_for_testing() -> None:
    """
        Clear the active KEK. Test-only helper used to isolate tests.

        :returns: None.
    """
    global _ACTIVE_KEK
    _ACTIVE_KEK = None
    return


def load_kek_at_startup(
        *,
        source: str,
        file_path: Optional[str],
        env_var: Optional[str],
        kek_id: str
    ) -> KekHandle:
    """
        Load the KEK from the configured source and wrap it in a
        :class:`KekHandle`. Raises :class:`ConfigurationError` on any
        failure so service startup bails rather than silently falling
        back to a weaker path.

        :param source: ``"file"`` | ``"env"`` | ``"kms"``.
        :param file_path: Path to the KEK file when ``source == "file"``.
        :param env_var: Environment variable name when ``source == "env"``.
        :param kek_id: Operator-assigned identifier for logging.

        :returns: The loaded :class:`KekHandle`.
        :raises: ConfigurationError
    """
    if source == "file":
        if file_path is None or len(file_path) == 0:
            raise ConfigurationError("KEK source 'file' requires a non-empty file_path")
        if os.path.exists(file_path) is False:
            err_msg_lines = ["KEK file not found."]
            err_msg_lines.append("PATH: {}".format(file_path))
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg)
        with open(file_path, "rb") as handle:
            material = handle.read()
        if len(material) < 32:
            raise ConfigurationError("KEK material must be >= 32 bytes (AES-256)")
        rtnval = KekHandle(
            kek_id=kek_id,
            key_material=SecretBytes(material),
            source="file",
        )
        return rtnval

    if source == "env":
        if env_var is None or len(env_var) == 0:
            raise ConfigurationError("KEK source 'env' requires a non-empty env_var name")
        raw = os.environ.get(env_var, None)
        if raw is None:
            err_msg_lines = ["KEK environment variable not set."]
            err_msg_lines.append("ENV_VAR: {}".format(env_var))
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg)
        material = raw.encode("utf-8")
        if len(material) < 32:
            raise ConfigurationError("KEK material must be >= 32 bytes (AES-256)")
        rtnval = KekHandle(
            kek_id=kek_id,
            key_material=SecretBytes(material),
            source="env",
        )
        return rtnval

    err_msg_lines = ["Unsupported KEK source."]
    err_msg_lines.append("SOURCE: {}".format(source))
    err_msg_lines.append("SUPPORTED: file, env")
    err_msg = os.linesep.join(err_msg_lines)
    raise ConfigurationError(err_msg)
