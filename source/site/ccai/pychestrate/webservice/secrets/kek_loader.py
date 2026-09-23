"""
.. module:: secrets.kek_loader
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: KEK bootstrap loader at service startup.

.. moduleauthor:: Code Craft AI LLC

The KEK (Key Encryption Key) is loaded once at service startup from an
operator-owned source and used by the local backend to wrap per-version
DEKs. The M1 skeleton supports the ``file`` and ``env`` sources; the
``kms`` source lands when the KMS shim protocol is declared.

A KEK file must be accessible to its owner only (mode ``0600`` or
``0400``). On POSIX hosts the loader refuses a file that grants any
permission to its group or to other users, so a key that another
local account could read (or replace) stops startup instead of
protecting secrets it cannot keep private.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import stat

from dataclasses import dataclass
from typing import Optional

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes


#: Permission bits a KEK file must not carry: every group and other
#: bit (read, write, execute).
KEK_FILE_FORBIDDEN_MODE_BITS: int = stat.S_IRWXG | stat.S_IRWXO


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


def check_kek_file_permissions(*, file_path: str) -> None:
    """
        Refuse a KEK file that its group or other users can access.

        The check runs on POSIX hosts only; Windows does not express
        file access through POSIX mode bits. Symlinks are followed, so
        the mode checked is the mode of the file that holds the key.

        :param file_path: Path to the KEK file.

        :returns: None.
        :raises: ConfigurationError when the file mode grants any group
                 or other permission. The message names the path, the
                 mode found, and the command that fixes it.
    """
    if os.name != "posix":
        return

    file_mode = stat.S_IMODE(os.stat(file_path).st_mode)
    if (file_mode & KEK_FILE_FORBIDDEN_MODE_BITS) != 0:
        err_msg_lines = ["KEK file permissions are too open."]
        err_msg_lines.append("PATH: {}".format(file_path))
        err_msg_lines.append("MODE: {:04o}".format(file_mode))
        err_msg_lines.append(
            "REQUIRED: readable by the service user only (0600 or 0400)."
        )
        err_msg_lines.append("FIX: chmod 0600 {}".format(file_path))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg)

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
                          The file must be at least 32 bytes and, on
                          POSIX hosts, accessible to its owner only
                          (see :func:`check_kek_file_permissions`).
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
        check_kek_file_permissions(file_path=file_path)
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
