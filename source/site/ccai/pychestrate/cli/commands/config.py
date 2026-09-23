"""
.. module:: cli.commands.config
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``pyc config init|set|get|unset|profiles|path``.

.. moduleauthor:: Code Craft AI LLC

Manage the credentials file without editing it by hand. Every write
keeps mode ``0600``. The token itself is written only by
``pyc login`` (so it never appears on a command line); ``config get
bearer_token`` shows only its first characters.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Dict, List, Optional, Sequence

from ccai.pychestrate.cli import credentials, exit_codes, transport
from ccai.pychestrate.cli.argparsing import CliArgumentParser
from ccai.pychestrate.cli.context import CliContext, normalize_server_url
from ccai.pychestrate.cli.exceptions import (
    CliUsageError,
    CredentialsFileNotFoundError,
    ProfileNotFoundError,
)


CONFIG_VERBS = ("init", "set", "get", "unset", "profiles", "path")

_TOKEN_SHOWN_CHARS: int = 10


def _mask_token(value: str) -> str:
    """
        Show a token's first characters only.

        :param value: Token.

        :returns: Masked text.
    """
    if len(value) <= _TOKEN_SHOWN_CHARS:
        return "***"
    rtnval = value[:_TOKEN_SHOWN_CHARS] + "..."
    return rtnval


def _validate_value(*, ctx: CliContext, key: str, value: str) -> str:
    """
        Validate and normalize a ``config set`` value.

        :param ctx: Invocation context.
        :param key: Key.
        :param value: Raw value.

        :returns: Value to store.
        :raises: CliUsageError
    """
    if key == "server_url":
        normalized = normalize_server_url(ctx=ctx, server_url=value)
        try:
            rtnval = transport.validate_server_url(server_url=normalized)
        except Exception as xcpt:
            raise CliUsageError(str(xcpt).replace("cannot reach", "invalid server_url")) from None
        return rtnval
    if key == "verify_tls":
        lowered = value.strip().lower()
        if lowered not in ("true", "false", "yes", "no", "on", "off", "1", "0"):
            raise CliUsageError("verify_tls must be true or false")
        rtnval = "true" if credentials.parse_bool(raw=lowered, default=True) else "false"
        if rtnval == "false":
            ctx.note(
                "tls-set",
                "warning: with verify_tls = false anyone on the network path can read"
                " or alter pyc's traffic, including the API token.",
            )
        return rtnval
    if key == "timeout":
        try:
            seconds = float(value)
        except ValueError:
            seconds = -1.0
        if seconds <= 0:
            raise CliUsageError("timeout must be a number of seconds greater than 0")
        rtnval = "{:g}".format(seconds)
        return rtnval
    rtnval = value.strip()
    return rtnval


def _profile_values(*, ctx: CliContext, profile_name: str) -> Dict[str, str]:
    """
        The stored keys of one profile.

        :param ctx: Invocation context.
        :param profile_name: Profile.

        :returns: ``{key: value}``.
        :raises: CredentialsFileNotFoundError, ProfileNotFoundError
    """
    path, profiles = credentials.list_profiles(environ=ctx.environ)
    for name, values in profiles:
        if name == profile_name:
            return values
    if len(profiles) == 0:
        raise CredentialsFileNotFoundError(
            "No credentials file at {}; run 'pyc login' or 'pyc config init'.".format(path)
        )
    raise ProfileNotFoundError(
        "No profile '{}' in {} (have: {}).".format(
            profile_name, path, ", ".join(name for name, _values in profiles)
        )
    )


def run_config(*, ctx: CliContext, args: Sequence[str]) -> int:
    """
        Dispatch ``pyc config <verb>``.

        :param ctx: Invocation context.
        :param args: Arguments after ``config``.

        :returns: Exit code.
    """
    command_parser = CliArgumentParser(
        prog="pyc config",
        description=(
            "Manage the pyc credentials file ({}).\n\n"
            "  init [--server-url URL]  create the file / profile (mode 0600)\n"
            "  set KEY VALUE            set server_url, verify_tls, timeout,\n"
            "                           mtls_cert_path or mtls_key_path\n"
            "  get KEY                  print one value (tokens are masked)\n"
            "  unset KEY                remove one key\n"
            "  profiles                 list profiles\n"
            "  path                     print the file's path\n\n"
            "The API token is stored by 'pyc login'.".format(
                credentials.credentials_path(environ=ctx.environ)
            )
        ),
        out_stream=ctx.stdout,
        err_stream=ctx.stderr,
    )
    command_parser.add_argument("verb", choices=CONFIG_VERBS)
    command_parser.add_argument("key", nargs="?", default=None)
    command_parser.add_argument("value", nargs="?", default=None)
    namespace = command_parser.parse_args(list(args))

    profile_name = credentials.resolve_profile_name(requested=ctx.profile_name, environ=ctx.environ)
    verb = namespace.verb

    if verb == "path":
        ctx.stdout.write("{}\n".format(credentials.credentials_path(environ=ctx.environ)))
        return exit_codes.EXIT_OK

    if verb == "profiles":
        path, profiles = credentials.list_profiles(environ=ctx.environ)
        if len(profiles) == 0:
            ctx.stdout.write("no profiles ({} does not exist); run 'pyc login'.\n".format(path))
            return exit_codes.EXIT_OK
        lines: List[str] = ["profiles in {}:".format(path)]
        for name, values in profiles:
            marker = "*" if name == profile_name else " "
            token = values.get("bearer_token", "")
            token_text = "no token"
            if len(token) > 0:
                token_text = "token {}".format(_mask_token(token))
                expires = values.get("bearer_token_expires_at", "")
                if len(expires) > 0:
                    token_text = "{} (expires {})".format(token_text, expires[:10])
            lines.append("{} {:<16} {:<40} {}".format(
                marker, name, values.get("server_url", "(no server_url)"), token_text
            ))
        ctx.stdout.write("\n".join(lines) + "\n")
        return exit_codes.EXIT_OK

    if verb == "init":
        server_url = ctx.server_url
        try:
            existing = _profile_values(ctx=ctx, profile_name=profile_name)
        except (CredentialsFileNotFoundError, ProfileNotFoundError):
            existing = None
        if existing is not None and server_url is None:
            ctx.stdout.write(
                "profile '{}' already exists in {}.\n".format(
                    profile_name, credentials.credentials_path(environ=ctx.environ)
                )
            )
            return exit_codes.EXIT_OK
        values: Dict[str, Optional[str]] = {"verify_tls": (existing or {}).get("verify_tls", "true")}
        if server_url is not None:
            values["server_url"] = _validate_value(ctx=ctx, key="server_url", value=server_url)
        path = credentials.write_profile_values(profile_name=profile_name, values=values, environ=ctx.environ)
        ctx.stdout.write("wrote profile '{}' to {} (mode 0600).\n".format(profile_name, path))
        ctx.stdout.write("next: pyc login{}\n".format(
            "" if server_url is not None else " --server-url https://your-server"
        ))
        return exit_codes.EXIT_OK

    key = namespace.key
    if key is None:
        raise CliUsageError("pyc config {} needs a KEY".format(verb))
    if key not in credentials.KNOWN_KEYS:
        raise CliUsageError(
            "unknown key '{}'; keys: {}".format(key, ", ".join(credentials.KNOWN_KEYS))
        )

    if verb == "get":
        values = _profile_values(ctx=ctx, profile_name=profile_name)
        value = values.get(key, None)
        if value is None:
            ctx.stderr.write("'{}' is not set in profile '{}'.\n".format(key, profile_name))
            return exit_codes.EXIT_NOT_FOUND
        if key == "bearer_token":
            value = _mask_token(value)
        ctx.stdout.write("{}\n".format(value))
        return exit_codes.EXIT_OK

    if verb == "unset":
        path = credentials.write_profile_values(
            profile_name=profile_name, values={key: None}, environ=ctx.environ,
        )
        ctx.stdout.write("removed '{}' from profile '{}' ({}).\n".format(key, profile_name, path))
        return exit_codes.EXIT_OK

    # verb == "set"
    if key not in credentials.SETTABLE_KEYS:
        raise CliUsageError(
            "'{}' is written by 'pyc login', not 'pyc config set'".format(key)
        )
    if namespace.value is None:
        raise CliUsageError("pyc config set {} needs a VALUE".format(key))
    value = _validate_value(ctx=ctx, key=key, value=namespace.value)
    path = credentials.write_profile_values(
        profile_name=profile_name, values={key: value}, environ=ctx.environ,
    )
    ctx.stdout.write("set {} = {} in profile '{}' ({}).\n".format(key, value, profile_name, path))
    rtnval = exit_codes.EXIT_OK
    return rtnval


__all__ = [
    "CONFIG_VERBS",
    "run_config",
]
