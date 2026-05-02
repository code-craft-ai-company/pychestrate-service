"""
.. module:: cli.credentials
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``~/.pychestrate/credentials`` profile loader.

.. moduleauthor:: Automation Mojo LLC

The loader is intentionally strict: a wider mode than ``0600`` aborts
with :class:`CredentialsFilePermissionError` so a misconfigured file
does not become a credential leak. Profile selection follows
``--profile`` > ``PYC_PROFILE`` > ``default``. Disk format is INI per
design.md: one section per profile with the documented keys.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import configparser
import datetime
import os
import stat

from pathlib import Path
from typing import Optional

from automojo.pychestrate.cli.exceptions import (
    CredentialsFileNotFoundError,
    CredentialsFilePermissionError,
    ProfileNotFoundError,
)
from automojo.pychestrate.cli.models import DEFAULT_PROFILE_NAME, CliProfile


CREDENTIALS_RELATIVE_PATH: str = ".pychestrate/credentials"
PYC_PROFILE_ENV_VAR: str = "PYC_PROFILE"
PYC_CREDENTIALS_PATH_ENV_VAR: str = "PYC_CREDENTIALS_PATH"

REQUIRED_FILE_MODE_MASK: int = 0o077


def _resolve_credentials_path() -> Path:
    """
        Return the credentials file path, honoring the test-friendly
        :data:`PYC_CREDENTIALS_PATH_ENV_VAR` override.

        :returns: Absolute path to the credentials file.
    """
    override = os.environ.get(PYC_CREDENTIALS_PATH_ENV_VAR, None)
    if override is not None and len(override) > 0:
        rtnval = Path(override).expanduser().resolve()
        return rtnval
    rtnval = Path.home() / CREDENTIALS_RELATIVE_PATH
    return rtnval


def _resolve_profile_name(*, requested: Optional[str]) -> str:
    """
        Resolve the active profile name.

        :param requested: ``--profile`` argument value or ``None``.

        :returns: Active profile name.
    """
    if requested is not None and len(requested) > 0:
        rtnval = requested
        return rtnval

    env_value = os.environ.get(PYC_PROFILE_ENV_VAR, "")
    if len(env_value) > 0:
        rtnval = env_value
        return rtnval

    rtnval = DEFAULT_PROFILE_NAME
    return rtnval


def _enforce_strict_mode(*, credentials_path: Path) -> None:
    """
        Refuse to read a credentials file whose mode bits include any
        non-owner read/write/execute access.

        :param credentials_path: Resolved path to the credentials file.

        :returns: None.
        :raises: CredentialsFilePermissionError on any group/other bit set.
    """
    mode_bits = credentials_path.stat().st_mode
    sensitive_bits = mode_bits & REQUIRED_FILE_MODE_MASK
    if sensitive_bits != 0:
        err_msg_lines = ["Credentials file mode is too permissive."]
        err_msg_lines.append("PATH: {}".format(credentials_path))
        err_msg_lines.append("MODE: {:o}".format(stat.S_IMODE(mode_bits)))
        err_msg_lines.append("REQUIRED: 600 (owner only)")
        err_msg = os.linesep.join(err_msg_lines)
        raise CredentialsFilePermissionError(err_msg) from None
    return


def _parse_iso_datetime(*, raw: str) -> Optional[datetime.datetime]:
    """
        Parse an ISO-8601 string with a permissive ``Z`` suffix.

        :param raw: String value from the credentials file.

        :returns: Parsed :class:`datetime.datetime` or ``None`` when
                  empty / unparseable.
    """
    if raw is None or len(raw) == 0:
        rtnval: Optional[datetime.datetime] = None
        return rtnval

    candidate = raw.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"

    try:
        rtnval = datetime.datetime.fromisoformat(candidate)
    except ValueError:
        rtnval = None
    return rtnval


def load_profile(*, profile_name: Optional[str]) -> CliProfile:
    """
        Load a single profile, enforcing mode ``0600``.

        :param profile_name: ``--profile`` argument value or ``None``.

        :returns: Resolved :class:`CliProfile`.
        :raises: CredentialsFileNotFoundError,
                 CredentialsFilePermissionError,
                 ProfileNotFoundError
    """
    credentials_path = _resolve_credentials_path()
    if not credentials_path.is_file():
        err_msg_lines = ["Credentials file not found."]
        err_msg_lines.append("PATH: {}".format(credentials_path))
        err_msg = os.linesep.join(err_msg_lines)
        raise CredentialsFileNotFoundError(err_msg) from None

    _enforce_strict_mode(credentials_path=credentials_path)

    parser = configparser.ConfigParser()
    parser.read(credentials_path, encoding="utf-8")

    active_profile_name = _resolve_profile_name(requested=profile_name)
    if active_profile_name not in parser:
        err_msg_lines = ["Profile not found in credentials file."]
        err_msg_lines.append("PATH: {}".format(credentials_path))
        err_msg_lines.append("PROFILE: {}".format(active_profile_name))
        err_msg_lines.append("AVAILABLE: {}".format(", ".join(sorted(parser.sections()))))
        err_msg = os.linesep.join(err_msg_lines)
        raise ProfileNotFoundError(err_msg) from None

    section = parser[active_profile_name]
    server_url = section.get("server_url", "").strip()
    bearer_token_raw = section.get("bearer_token", "").strip()
    bearer_token_expires_raw = section.get("bearer_token_expires_at", "").strip()
    mtls_cert_path = section.get("mtls_cert_path", "").strip()
    mtls_key_path = section.get("mtls_key_path", "").strip()
    verify_tls_raw = section.get("verify_tls", "true").strip().lower()

    if verify_tls_raw in ("0", "false", "no", "off"):
        verify_tls_value = False
    else:
        verify_tls_value = True

    bearer_token_value: Optional[str] = bearer_token_raw if len(bearer_token_raw) > 0 else None
    bearer_token_expires_value = _parse_iso_datetime(raw=bearer_token_expires_raw)
    mtls_cert_value: Optional[str] = mtls_cert_path if len(mtls_cert_path) > 0 else None
    mtls_key_value: Optional[str] = mtls_key_path if len(mtls_key_path) > 0 else None

    rtnval = CliProfile(
        profile_name=active_profile_name,
        server_url=server_url,
        bearer_token=bearer_token_value,
        bearer_token_expires_at=bearer_token_expires_value,
        mtls_cert_path=mtls_cert_value,
        mtls_key_path=mtls_key_value,
        verify_tls=verify_tls_value,
    )
    return rtnval


def store_token(
        *,
        profile_name: str,
        bearer_token: str,
        bearer_token_expires_at: datetime.datetime
    ) -> None:
    """
        Write a bearer token + expiry into the named profile.

        Preserves mode ``0600`` on the credentials file. Creates the
        file if it does not yet exist.

        :param profile_name: Section name to update.
        :param bearer_token: Token bytes (base64-encoded JWT etc.).
        :param bearer_token_expires_at: Expiry timestamp.

        :returns: None.
    """
    credentials_path = _resolve_credentials_path()
    credentials_path.parent.mkdir(parents=True, exist_ok=True)

    parser = configparser.ConfigParser()
    if credentials_path.is_file():
        parser.read(credentials_path, encoding="utf-8")

    if profile_name not in parser:
        parser[profile_name] = {}

    parser[profile_name]["bearer_token"] = bearer_token
    parser[profile_name]["bearer_token_expires_at"] = bearer_token_expires_at.isoformat()

    fd = os.open(
        str(credentials_path),
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            parser.write(fh)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise

    os.chmod(str(credentials_path), 0o600)
    return
