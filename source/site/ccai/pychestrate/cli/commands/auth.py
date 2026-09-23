"""
.. module:: cli.commands.auth
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``pyc login``, ``pyc logout``, ``pyc whoami``.

.. moduleauthor:: Code Craft AI LLC

``pyc login`` is the first-run path. It needs a server URL and an API
token (create one in the web UI under Account > API tokens):

* server URL: ``--server-url``, ``PYC_SERVER_URL``, the profile's
  current ``server_url``, or a prompt when interactive;
* token: ``--with-token`` (read from stdin, for scripts),
  ``PYC_TOKEN``, or a hidden prompt when interactive. The token never
  has to appear on the command line.

It verifies the token against ``GET /api/v1/me`` before saving the
server URL, token, and expiry into the profile (file mode ``0600``).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import getpass
import json

from dataclasses import replace
from typing import Any, Dict, Optional, Sequence

from ccai.pychestrate.cli import credentials, exit_codes, transport
from ccai.pychestrate.cli.argparsing import CliArgumentParser
from ccai.pychestrate.cli.context import (
    PYC_SERVER_URL_ENV_VAR,
    PYC_TOKEN_ENV_VAR,
    CliContext,
    normalize_server_url,
    resolve_profile,
)
from ccai.pychestrate.cli.exceptions import (
    AuthenticationError,
    CliUsageError,
    CredentialsFileNotFoundError,
    ProfileNotFoundError,
)
from ccai.pychestrate.cli.models import CliProfile, RestOperation


ME_PATH: str = "/api/v1/me"
TOKEN_PREFIX: str = "pyc_"
TOKEN_PAGE_PATH: str = "/account/api-tokens"


def _me_operation() -> RestOperation:
    rtnval = RestOperation(operation_id="me_get_identity", method="GET", path_template=ME_PATH)
    return rtnval


def fetch_identity(*, ctx: CliContext, profile: CliProfile) -> Dict[str, Any]:
    """
        ``GET /api/v1/me`` with the profile's credentials.

        :param ctx: Invocation context.
        :param profile: Profile to authenticate with.

        :returns: The identity document.
    """
    response = transport.execute_request(
        profile=profile,
        operation=_me_operation(),
        path_params={},
        query_params={},
        body=None,
        idempotency_key=None,
        timeout_seconds=None,
        opener=ctx.request_opener,
    )
    rtnval = response.body if isinstance(response.body, dict) else {}
    return rtnval


def _is_interactive(stream: Any) -> bool:
    try:
        rtnval = bool(stream.isatty())
    except Exception:
        rtnval = False
    return rtnval


def _stored_profile(ctx: CliContext) -> Optional[CliProfile]:
    """
        The stored profile, or ``None`` when there is no file / profile.

        :param ctx: Invocation context.

        :returns: Profile or ``None``.
    """
    try:
        rtnval = credentials.load_profile(profile_name=ctx.profile_name, environ=ctx.environ)
    except (CredentialsFileNotFoundError, ProfileNotFoundError):
        rtnval = None
    return rtnval


def _read_secret(ctx: CliContext, prompt: str) -> str:
    if ctx.prompt_secret is not None:
        rtnval = ctx.prompt_secret(prompt)
        return rtnval
    rtnval = getpass.getpass(prompt, stream=ctx.stderr)
    return rtnval


def _describe_expiry(value: Optional[str]) -> str:
    if value is None or len(value) == 0:
        return "no recorded expiry"
    rtnval = "expires {}".format(value[:10])
    return rtnval


def run_login(*, ctx: CliContext, args: Sequence[str]) -> int:
    """
        ``pyc login [--server-url URL] [--with-token] [--profile NAME]``.

        :param ctx: Invocation context (``--server-url`` / ``--profile``
                    were parsed as global options).
        :param args: Arguments after ``login``.

        :returns: Exit code.
    """
    command_parser = CliArgumentParser(
        prog="pyc login",
        description=(
            "Store a server URL and an API token in a credentials profile.\n\n"
            "Create the token in the web UI under Account > API tokens, then run\n"
            "    pyc login --server-url https://pychestrate.example.com\n"
            "and paste it when asked, or pipe it in with --with-token."
        ),
        out_stream=ctx.stdout,
        err_stream=ctx.stderr,
    )
    command_parser.add_argument(
        "--with-token", action="store_true", default=False,
        help="read the token from standard input (first line)",
    )
    namespace = command_parser.parse_args(list(args))

    profile_name = credentials.resolve_profile_name(requested=ctx.profile_name, environ=ctx.environ)
    stored = _stored_profile(ctx)

    server_url = ctx.server_url or ctx.environ.get(PYC_SERVER_URL_ENV_VAR, "") or None
    if server_url is None and stored is not None and len(stored.server_url) > 0:
        server_url = stored.server_url
    if server_url is None:
        if _is_interactive(ctx.stdin) is True and namespace.with_token is False:
            ctx.stderr.write("Pychestrate server URL: ")
            ctx.stderr.flush()
            server_url = ctx.stdin.readline().strip()
        if server_url is None or len(server_url) == 0:
            raise CliUsageError(
                "pyc login needs the server URL: pass --server-url https://host"
                " (or set {})".format(PYC_SERVER_URL_ENV_VAR)
            )
    server_url = normalize_server_url(ctx=ctx, server_url=server_url)
    try:
        server_url = transport.validate_server_url(server_url=server_url)
    except Exception as xcpt:
        raise CliUsageError(str(xcpt).replace("cannot reach", "invalid --server-url")) from None

    if namespace.with_token is True:
        token = ctx.stdin.readline().strip()
    else:
        token = ctx.environ.get(PYC_TOKEN_ENV_VAR, "").strip()
        if len(token) == 0:
            if _is_interactive(ctx.stdin) is False:
                raise CliUsageError(
                    "no API token: pipe it in with 'pyc login --with-token' or set {}."
                    " Create one at {}{}".format(PYC_TOKEN_ENV_VAR, server_url, TOKEN_PAGE_PATH)
                )
            ctx.stderr.write(
                "Create an API token at {}{} and paste it here.\n".format(server_url, TOKEN_PAGE_PATH)
            )
            token = _read_secret(ctx, "API token: ").strip()
    if len(token) == 0:
        raise CliUsageError("no API token was given")
    if token.startswith(TOKEN_PREFIX) is False:
        raise CliUsageError(
            "that is not a Pychestrate API token (they start with '{}');"
            " create one at {}{}".format(TOKEN_PREFIX, server_url, TOKEN_PAGE_PATH)
        )

    verify_profile = CliProfile(
        profile_name=profile_name,
        server_url=server_url,
        bearer_token=token,
        bearer_token_expires_at=None,
        mtls_cert_path=stored.mtls_cert_path if stored is not None else None,
        mtls_key_path=stored.mtls_key_path if stored is not None else None,
        verify_tls=stored.verify_tls if stored is not None else True,
        timeout_seconds=ctx.timeout_seconds if ctx.timeout_seconds is not None else (
            stored.timeout_seconds if stored is not None else None
        ),
    )
    try:
        identity = fetch_identity(ctx=ctx, profile=verify_profile)
    except AuthenticationError as xcpt:
        raise AuthenticationError(
            "the server rejected the token, nothing was saved: {}".format(xcpt)
        ) from None

    authentication = identity.get("authentication", {}) or {}
    expires_at = authentication.get("token_expires_at", None)
    path = credentials.write_profile_values(
        profile_name=profile_name,
        values={
            "server_url": server_url,
            "bearer_token": token,
            "bearer_token_expires_at": expires_at,
        },
        environ=ctx.environ,
    )
    ctx.stdout.write(
        "Logged in to {} as {} ({}); token '{}' ({}, {}).\n".format(
            server_url,
            identity.get("login_name", "?"),
            identity.get("account_kind", "user"),
            authentication.get("token_name", "?"),
            authentication.get("token_scope", "?"),
            _describe_expiry(expires_at),
        )
    )
    ctx.stdout.write("Saved profile '{}' in {} (mode 0600).\n".format(profile_name, path))
    rtnval = exit_codes.EXIT_OK
    return rtnval


def run_logout(*, ctx: CliContext, args: Sequence[str]) -> int:
    """
        ``pyc logout [--revoke]``: remove the token from the profile,
        optionally revoking it on the server first.

        :param ctx: Invocation context.
        :param args: Arguments after ``logout``.

        :returns: Exit code.
    """
    command_parser = CliArgumentParser(
        prog="pyc logout",
        description="Remove the stored API token from the profile.",
        out_stream=ctx.stdout,
        err_stream=ctx.stderr,
    )
    command_parser.add_argument(
        "--revoke", action="store_true", default=False,
        help="also revoke the token on the server so it stops working everywhere",
    )
    namespace = command_parser.parse_args(list(args))

    stored = credentials.load_profile(profile_name=ctx.profile_name, environ=ctx.environ)
    revoked = False
    if namespace.revoke is True and stored.bearer_token is not None:
        profile = resolve_profile(ctx=ctx)
        profile = replace(profile, bearer_token=stored.bearer_token)
        identity = fetch_identity(ctx=ctx, profile=profile)
        token_id = (identity.get("authentication", {}) or {}).get("token_id", None)
        if token_id is not None:
            transport.execute_request(
                profile=profile,
                operation=RestOperation(
                    operation_id="api_tokens_revoke_mine",
                    method="DELETE",
                    path_template="/api/v1/me/api-tokens/{token_id}",
                    path_param_names=("token_id",),
                    required_path_param_names=("token_id",),
                ),
                path_params={"token_id": token_id},
                query_params={},
                body=None,
                idempotency_key=None,
                timeout_seconds=None,
                opener=ctx.request_opener,
            )
            revoked = True

    path = credentials.write_profile_values(
        profile_name=stored.profile_name,
        values={"bearer_token": None, "bearer_token_expires_at": None},
        environ=ctx.environ,
    )
    message = "Removed the API token from profile '{}' ({})".format(stored.profile_name, path)
    if revoked is True:
        message = message + " and revoked it on the server"
    ctx.stdout.write(message + ".\n")
    rtnval = exit_codes.EXIT_OK
    return rtnval


def run_whoami(*, ctx: CliContext, args: Sequence[str]) -> int:
    """
        ``pyc whoami [--json]``.

        :param ctx: Invocation context.
        :param args: Arguments after ``whoami``.

        :returns: Exit code.
    """
    command_parser = CliArgumentParser(
        prog="pyc whoami",
        description="Show who the configured credentials authenticate as.",
        out_stream=ctx.stdout,
        err_stream=ctx.stderr,
    )
    command_parser.add_argument("--json", action="store_true", default=False, help="print the raw JSON")
    namespace = command_parser.parse_args(list(args))

    profile = resolve_profile(ctx=ctx)
    if profile.bearer_token is None and profile.mtls_cert_path is None:
        ctx.note("no-token", "note: no API token is configured; run 'pyc login'.")
    identity = fetch_identity(ctx=ctx, profile=profile)
    if namespace.json is True:
        ctx.stdout.write(json.dumps(identity, indent=2) + "\n")
        return exit_codes.EXIT_OK

    authentication = identity.get("authentication", {}) or {}
    if authentication.get("method", "") == "api_token":
        auth_line = "API token '{}' ({}, {})".format(
            authentication.get("token_name", "?"),
            authentication.get("token_scope", "?"),
            _describe_expiry(authentication.get("token_expires_at", None)),
        )
    else:
        auth_line = str(authentication.get("method", "unknown"))
    lines = [
        "server:   {}".format(profile.server_url),
        "account:  {} ({}){}".format(
            identity.get("login_name", "?"),
            identity.get("display_name", ""),
            " [service account]" if identity.get("account_kind") == "service_account" else "",
        ),
        "auth:     {}".format(auth_line),
        "profile:  {}".format(profile.profile_name),
    ]
    ctx.stdout.write("\n".join(lines) + "\n")
    rtnval = exit_codes.EXIT_OK
    return rtnval


__all__ = [
    "fetch_identity",
    "run_login",
    "run_logout",
    "run_whoami",
]
