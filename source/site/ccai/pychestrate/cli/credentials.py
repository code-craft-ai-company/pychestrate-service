"""
.. module:: cli.credentials
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The ``pyc`` credentials file: profiles holding a server
               URL and an API token.

.. moduleauthor:: Code Craft AI LLC

The file lives at ``$XDG_CONFIG_HOME/pychestrate/credentials``
(``~/.config/pychestrate/credentials``; see :mod:`cli.paths`), is INI
with one section per profile, and is written with mode ``0600``. The
loader is intentionally strict: a wider mode aborts with
:class:`CredentialsFilePermissionError` so a misconfigured file does
not become a credential leak. Profile selection follows
``--profile`` > ``PYC_PROFILE`` > ``default``.

``pyc login`` writes a profile; nobody has to hand-write the file.
The format, for reference::

    [default]
    server_url = https://pychestrate.example.com
    bearer_token = pyc_...
    bearer_token_expires_at = 2026-12-22T05:59:43+00:00
    verify_tls = true
    ; optional: timeout = 30, mtls_cert_path = ..., mtls_key_path = ...
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import configparser
import datetime
import os
import stat
import tempfile

from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

from ccai.pychestrate.cli import paths
from ccai.pychestrate.cli.exceptions import (
    CredentialsFileInvalidError,
    CredentialsFileNotFoundError,
    CredentialsFilePermissionError,
    ProfileNotFoundError,
)
from ccai.pychestrate.cli.models import DEFAULT_PROFILE_NAME, CliProfile


CREDENTIALS_RELATIVE_PATH: str = ".config/pychestrate/credentials"
PYC_PROFILE_ENV_VAR: str = "PYC_PROFILE"
PYC_CREDENTIALS_PATH_ENV_VAR: str = paths.PYC_CREDENTIALS_PATH_ENV_VAR

REQUIRED_FILE_MODE_MASK: int = 0o077

#: Keys ``pyc config set`` may change. The token is written only by
#: ``pyc login`` so it never passes through the command line.
SETTABLE_KEYS: Tuple[str, ...] = (
    "server_url",
    "verify_tls",
    "timeout",
    "mtls_cert_path",
    "mtls_key_path",
)

#: Every key a profile may carry.
KNOWN_KEYS: Tuple[str, ...] = SETTABLE_KEYS + ("bearer_token", "bearer_token_expires_at")

EXAMPLE_PROFILE_TEMPLATE: str = (
    "[{profile}]\n"
    "server_url = {server_url}\n"
    "; bearer_token is written by 'pyc login'\n"
    "bearer_token = pyc_...\n"
    "verify_tls = true\n"
)


def _resolve_credentials_path(environ: Optional[Mapping[str, str]] = None) -> Path:
    """
        Return the credentials file path (see
        :func:`paths.resolve_credentials_path`).

        :param environ: Environment mapping (tests).

        :returns: Absolute path to the credentials file.
    """
    rtnval = paths.resolve_credentials_path(environ=environ)
    return rtnval


def credentials_path(*, environ: Optional[Mapping[str, str]] = None) -> Path:
    """
        The credentials file ``pyc`` reads and writes.

        :param environ: Environment mapping (tests).

        :returns: Absolute :class:`Path`.
    """
    rtnval = _resolve_credentials_path(environ)
    return rtnval


def resolve_profile_name(
        *,
        requested: Optional[str],
        environ: Optional[Mapping[str, str]] = None
    ) -> str:
    """
        Resolve the active profile name: ``--profile``, then
        ``PYC_PROFILE``, then ``default``.

        :param requested: ``--profile`` argument value or ``None``.
        :param environ: Environment mapping (tests).

        :returns: Active profile name.
    """
    if requested is not None and len(requested) > 0:
        rtnval = requested
        return rtnval

    env = os.environ if environ is None else environ
    env_value = env.get(PYC_PROFILE_ENV_VAR, "")
    if len(env_value) > 0:
        rtnval = env_value
        return rtnval

    rtnval = DEFAULT_PROFILE_NAME
    return rtnval


def _resolve_profile_name(*, requested: Optional[str]) -> str:
    """
        Backwards-compatible alias of :func:`resolve_profile_name`.

        :param requested: ``--profile`` argument value or ``None``.

        :returns: Active profile name.
    """
    rtnval = resolve_profile_name(requested=requested)
    return rtnval


def example_profile(*, profile_name: str, server_url: str) -> str:
    """
        An example profile, printed with first-run errors.

        :param profile_name: Section name.
        :param server_url: Server URL to show.

        :returns: INI text.
    """
    rtnval = EXAMPLE_PROFILE_TEMPLATE.format(profile=profile_name, server_url=server_url)
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
        err_msg_lines.append("FIX: chmod 600 {}".format(credentials_path))
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


def parse_bool(*, raw: Optional[str], default: bool) -> bool:
    """
        Parse an INI boolean.

        :param raw: Raw value or ``None``.
        :param default: Value for ``None`` / empty.

        :returns: Boolean.
    """
    if raw is None or len(raw.strip()) == 0:
        return default
    rtnval = raw.strip().lower() not in ("0", "false", "no", "off")
    return rtnval


def _parse_timeout(*, raw: str, credentials_path: Path, profile_name: str) -> Optional[float]:
    """
        Parse the optional ``timeout`` key (seconds).

        :param raw: Raw value.
        :param credentials_path: File path, for the error message.
        :param profile_name: Profile name, for the error message.

        :returns: Seconds or ``None``.
        :raises: CredentialsFileInvalidError
    """
    if raw is None or len(raw.strip()) == 0:
        return None
    try:
        rtnval = float(raw.strip())
    except ValueError:
        rtnval = -1.0
    if rtnval <= 0:
        err_msg_lines = ["Invalid timeout in the credentials file (want seconds > 0)."]
        err_msg_lines.append("PATH: {}".format(credentials_path))
        err_msg_lines.append("PROFILE: {}".format(profile_name))
        err_msg_lines.append("VALUE: {}".format(raw))
        raise CredentialsFileInvalidError(os.linesep.join(err_msg_lines)) from None
    return rtnval


def read_credentials_file(
        *,
        environ: Optional[Mapping[str, str]] = None
    ) -> Tuple[Path, configparser.ConfigParser]:
    """
        Read and parse the credentials file, enforcing mode ``0600``.

        :param environ: Environment mapping (tests).

        :returns: ``(path, parser)``.
        :raises: CredentialsFileNotFoundError,
                 CredentialsFilePermissionError,
                 CredentialsFileInvalidError
    """
    credentials_path = _resolve_credentials_path(environ)
    if not credentials_path.is_file():
        err_msg_lines = ["Credentials file not found."]
        err_msg_lines.append("PATH: {}".format(credentials_path))
        err_msg = os.linesep.join(err_msg_lines)
        raise CredentialsFileNotFoundError(err_msg) from None

    _enforce_strict_mode(credentials_path=credentials_path)

    parser = configparser.ConfigParser(interpolation=None)
    try:
        with open(credentials_path, "r", encoding="utf-8") as fh:
            parser.read_file(fh)
    except (configparser.Error, UnicodeDecodeError, OSError) as xcpt:
        first_line = str(xcpt).splitlines()[0] if len(str(xcpt)) > 0 else type(xcpt).__name__
        err_msg_lines = ["Cannot read the credentials file; it is not a valid profile file."]
        err_msg_lines.append("PATH: {}".format(credentials_path))
        err_msg_lines.append("PROBLEM: {}".format(first_line))
        err_msg_lines.append("FIX: repair it, or move it aside and run 'pyc login'.")
        err_msg = os.linesep.join(err_msg_lines)
        raise CredentialsFileInvalidError(err_msg) from None

    rtnval = (credentials_path, parser)
    return rtnval


def load_profile(
        *,
        profile_name: Optional[str],
        environ: Optional[Mapping[str, str]] = None
    ) -> CliProfile:
    """
        Load a single profile, enforcing mode ``0600``.

        :param profile_name: ``--profile`` argument value or ``None``.
        :param environ: Environment mapping (tests).

        :returns: Resolved :class:`CliProfile`.
        :raises: CredentialsFileNotFoundError,
                 CredentialsFilePermissionError,
                 CredentialsFileInvalidError,
                 ProfileNotFoundError
    """
    credentials_path, parser = read_credentials_file(environ=environ)

    active_profile_name = resolve_profile_name(requested=profile_name, environ=environ)
    if active_profile_name not in parser:
        err_msg_lines = ["Profile not found in credentials file."]
        err_msg_lines.append("PATH: {}".format(credentials_path))
        err_msg_lines.append("PROFILE: {}".format(active_profile_name))
        err_msg_lines.append("AVAILABLE: {}".format(", ".join(sorted(parser.sections())) or "(none)"))
        err_msg_lines.append(
            "FIX: pyc login --profile {} --server-url <url>".format(active_profile_name)
        )
        err_msg = os.linesep.join(err_msg_lines)
        raise ProfileNotFoundError(err_msg) from None

    section = parser[active_profile_name]
    server_url = section.get("server_url", "").strip()
    bearer_token_raw = section.get("bearer_token", "").strip()
    bearer_token_expires_raw = section.get("bearer_token_expires_at", "").strip()
    mtls_cert_path = section.get("mtls_cert_path", "").strip()
    mtls_key_path = section.get("mtls_key_path", "").strip()
    verify_tls_value = parse_bool(raw=section.get("verify_tls", "true"), default=True)
    timeout_value = _parse_timeout(
        raw=section.get("timeout", ""), credentials_path=credentials_path,
        profile_name=active_profile_name,
    )

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
        timeout_seconds=timeout_value,
    )
    return rtnval


def list_profiles(
        *,
        environ: Optional[Mapping[str, str]] = None
    ) -> Tuple[Path, List[Tuple[str, Dict[str, str]]]]:
    """
        List every profile with its keys.

        :param environ: Environment mapping (tests).

        :returns: ``(path, [(profile_name, {key: value}), ...])``; an
                  empty list when the file does not exist.
        :raises: CredentialsFilePermissionError,
                 CredentialsFileInvalidError
    """
    try:
        credentials_path, parser = read_credentials_file(environ=environ)
    except CredentialsFileNotFoundError:
        rtnval = (_resolve_credentials_path(environ), [])
        return rtnval
    profiles: List[Tuple[str, Dict[str, str]]] = []
    for section_name in parser.sections():
        profiles.append((section_name, dict(parser[section_name])))
    rtnval = (credentials_path, profiles)
    return rtnval


def _write_private_file(*, target: Path, text: str) -> None:
    """
        Atomically replace ``target`` with ``text``, mode ``0600``; the
        parent directory is created ``0700`` when missing.

        :param target: Destination path.
        :param text: File content.

        :returns: None.
    """
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".credentials-", dir=str(target.parent))
    try:
        os.chmod(tmp_name, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, str(target))
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    os.chmod(str(target), 0o600)
    return


def write_profile_values(
        *,
        profile_name: str,
        values: Mapping[str, Optional[str]],
        environ: Optional[Mapping[str, str]] = None
    ) -> Path:
    """
        Set (or, for ``None`` values, remove) keys in a profile,
        creating the profile and the file as needed. The file keeps
        mode ``0600``.

        :param profile_name: Section name.
        :param values: ``{key: value}``; ``None`` deletes the key.
        :param environ: Environment mapping (tests).

        :returns: The path written.
        :raises: CredentialsFilePermissionError,
                 CredentialsFileInvalidError
    """
    target = paths.resolve_writable_credentials_path(environ=environ)
    parser = configparser.ConfigParser(interpolation=None)
    if target.is_file():
        _path, parser = read_credentials_file(environ=environ)

    if profile_name not in parser:
        parser[profile_name] = {}
    for key, value in values.items():
        if value is None:
            if key in parser[profile_name]:
                del parser[profile_name][key]
            continue
        parser[profile_name][key] = str(value)

    lines: List[str] = []
    for section_name in parser.sections():
        lines.append("[{}]".format(section_name))
        for key, value in parser[section_name].items():
            lines.append("{} = {}".format(key, value))
        lines.append("")
    _write_private_file(target=target, text="\n".join(lines))
    rtnval = target
    return rtnval


def store_token(
        *,
        profile_name: str,
        bearer_token: str,
        bearer_token_expires_at: Optional[datetime.datetime],
        environ: Optional[Mapping[str, str]] = None
    ) -> Path:
    """
        Write a bearer token + expiry into the named profile, creating
        the file (mode ``0600``) when it does not exist yet.

        :param profile_name: Section name to update.
        :param bearer_token: The API token.
        :param bearer_token_expires_at: Expiry timestamp, or ``None``.
        :param environ: Environment mapping (tests).

        :returns: The path written.
    """
    expires_value: Optional[str] = None
    if bearer_token_expires_at is not None:
        expires_value = bearer_token_expires_at.isoformat()
    rtnval = write_profile_values(
        profile_name=profile_name,
        values={"bearer_token": bearer_token, "bearer_token_expires_at": expires_value},
        environ=environ,
    )
    return rtnval


__all__ = [
    "EXAMPLE_PROFILE_TEMPLATE",
    "KNOWN_KEYS",
    "PYC_CREDENTIALS_PATH_ENV_VAR",
    "PYC_PROFILE_ENV_VAR",
    "SETTABLE_KEYS",
    "credentials_path",
    "example_profile",
    "list_profiles",
    "load_profile",
    "parse_bool",
    "read_credentials_file",
    "resolve_profile_name",
    "store_token",
    "write_profile_values",
]
