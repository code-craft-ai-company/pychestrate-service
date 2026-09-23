"""
.. module:: cli.context
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Per-invocation state of ``pyc``: streams, environment,
               global options, test seams, and profile resolution.

.. moduleauthor:: Code Craft AI LLC

Where the server URL and token come from, highest precedence first:

* server URL: ``--server-url``, ``PYC_SERVER_URL``, the profile's
  ``server_url``;
* token: ``PYC_TOKEN``, the profile's ``bearer_token``.

So a CI job needs no file at all
(``PYC_SERVER_URL=... PYC_TOKEN=... pyc projects list``), and a person
runs ``pyc login`` once. With neither, :func:`resolve_profile` raises
:class:`NotConfiguredError` whose message says exactly how to get
started.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import urllib.parse

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Mapping, Optional, TextIO, Tuple

from ccai.pychestrate.cli import credentials, renderer
from ccai.pychestrate.cli.exceptions import (
    CredentialsFileNotFoundError,
    NotConfiguredError,
    ProfileNotFoundError,
)
from ccai.pychestrate.cli.models import CliProfile
from ccai.pychestrate.cli.renderer import OutputOptions


PYC_SERVER_URL_ENV_VAR: str = "PYC_SERVER_URL"
PYC_TOKEN_ENV_VAR: str = "PYC_TOKEN"

#: The REST prefix ``pyc`` adds itself; a server URL ending in it is
#: trimmed (with a note) instead of producing ``/api/v1/api/v1/...``.
API_PREFIX: str = "/api/v1"

EXAMPLE_SERVER_URL: str = "https://pychestrate.example.com"

#: A stored token expiring within this many days is warned about.
TOKEN_EXPIRY_WARNING_DAYS: int = 7


class _NullStream:
    """
        A text stream that discards everything written to it.
    """

    def write(self, text: str) -> int:
        rtnval = len(text)
        return rtnval

    def flush(self) -> None:
        return


@dataclass
class CliContext:
    """
        Everything one ``pyc`` invocation needs besides its arguments.

        :param stdout: Output stream.
        :param stderr: Diagnostics stream.
        :param stdin: Input stream (``pyc login --with-token``).
        :param environ: Environment mapping.
        :param profile_name: ``--profile`` value.
        :param server_url: ``--server-url`` value.
        :param timeout_seconds: ``--timeout`` value.
        :param openapi_fetcher: Test seam replacing the OpenAPI fetch.
        :param request_opener: Test seam replacing the HTTP opener.
        :param profile_loader: Test seam replacing
                               :func:`credentials.load_profile`.
        :param prompt_secret: Callable reading a secret from the
                              terminal (``getpass`` by default).
        :param sleep: Callable used by ``--wait`` polling.
        :param clock: Callable returning "now" (UTC).
        :param output: ``-o/--output``, ``--fields``, ``-q/--quiet``.
    """
    stdout: TextIO
    stderr: TextIO
    stdin: TextIO
    environ: Mapping[str, str]
    profile_name: Optional[str] = None
    server_url: Optional[str] = None
    timeout_seconds: Optional[float] = None
    openapi_fetcher: Optional[Callable[[], Dict]] = None
    request_opener: Optional[Callable[..., Any]] = None
    profile_loader: Optional[Callable[[Optional[str]], CliProfile]] = None
    prompt_secret: Optional[Callable[[str], str]] = None
    sleep: Optional[Callable[[float], None]] = None
    clock: Optional[Callable[[], datetime]] = None
    output: OutputOptions = field(default_factory=OutputOptions)
    _notes_written: set = field(default_factory=set)

    def note(self, key: str, message: str) -> None:
        """
            Write a one-line note / warning to stderr once per
            invocation.

            :param key: De-duplication key.
            :param message: Line to write.

            :returns: None.
        """
        if key in self._notes_written:
            return
        self._notes_written.add(key)
        self.stderr.write(message.rstrip("\n") + "\n")
        return

    def now(self) -> datetime:
        """
            Current UTC time (test seam).

            :returns: Aware datetime.
        """
        if self.clock is not None:
            return self.clock()
        rtnval = datetime.now(timezone.utc)
        return rtnval

    def emit_result(
            self,
            *,
            value: Any,
            raw_text: Optional[str] = None,
            identifier_fields: Tuple[str, ...] = tuple(),
            default_format: Optional[str] = None
        ) -> None:
        """
            Print a command's result in the ``--output`` format (see
            :mod:`cli.renderer`).

            :param value: Decoded body, or data pyc built.
            :param raw_text: The body as the server sent it (``-o raw``).
            :param identifier_fields: Fields ``--quiet`` prints.
            :param default_format: The command's own default format;
                                   ``None`` for table on a terminal /
                                   JSON elsewhere.

            :returns: None.
        """
        renderer.render(
            request=renderer.RenderRequest(
                value=value,
                raw_text=raw_text,
                identifier_fields=identifier_fields,
                default_format=default_format,
            ),
            options=self.output,
            stream=self.stdout,
            notes=self.stderr,
            environ=dict(self.environ),
        )
        return


def not_configured_message(*, ctx: CliContext, reason: str) -> str:
    """
        The first-run guidance printed when no server is configured.

        :param ctx: Invocation context.
        :param reason: What is missing.

        :returns: Multi-line message.
    """
    profile_name = credentials.resolve_profile_name(requested=ctx.profile_name, environ=ctx.environ)
    path = credentials.credentials_path(environ=ctx.environ)
    lines = [
        "pyc is not configured: {}.".format(reason),
        "",
        "Sign in once (you will be asked for an API token; create one in the web UI",
        "under Account > API tokens):",
        "",
        "    pyc login --server-url {}".format(EXAMPLE_SERVER_URL),
        "",
        "or, for a single command or a CI job, set {} and {}.".format(
            PYC_SERVER_URL_ENV_VAR, PYC_TOKEN_ENV_VAR
        ),
        "",
        "'pyc login' writes {} (mode 0600), for example:".format(path),
        "",
    ]
    for example_line in credentials.example_profile(
            profile_name=profile_name, server_url=EXAMPLE_SERVER_URL).splitlines():
        lines.append("    " + example_line)
    rtnval = "\n".join(lines)
    return rtnval


def normalize_server_url(*, ctx: CliContext, server_url: str) -> str:
    """
        Trim whitespace, a trailing ``/``, and a trailing ``/api/v1``
        (``pyc`` adds that itself), noting the latter on stderr.

        :param ctx: Invocation context.
        :param server_url: Configured URL.

        :returns: The service root URL.
    """
    candidate = (server_url or "").strip().rstrip("/")
    parsed = urllib.parse.urlsplit(candidate)
    path = parsed.path.rstrip("/")
    if path.endswith(API_PREFIX):
        trimmed_path = path[:-len(API_PREFIX)]
        trimmed = urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, trimmed_path, parsed.query, parsed.fragment)
        ).rstrip("/")
        ctx.note(
            "api-prefix",
            "note: server_url {} ends with {}; using {} (pyc adds {} itself).".format(
                candidate, API_PREFIX, trimmed, API_PREFIX
            ),
        )
        return trimmed
    return candidate


def _ephemeral_profile(*, ctx: CliContext, server_url: str, token: Optional[str]) -> CliProfile:
    """
        A profile built from ``--server-url`` / environment variables
        alone (no credentials file needed).

        :param ctx: Invocation context.
        :param server_url: Server URL.
        :param token: Token or ``None``.

        :returns: :class:`CliProfile`.
    """
    profile_name = credentials.resolve_profile_name(requested=ctx.profile_name, environ=ctx.environ)
    rtnval = CliProfile(
        profile_name=profile_name,
        server_url=server_url,
        bearer_token=token,
        bearer_token_expires_at=None,
        mtls_cert_path=None,
        mtls_key_path=None,
        verify_tls=True,
        timeout_seconds=None,
    )
    return rtnval


def _load_stored_profile(ctx: CliContext) -> CliProfile:
    """
        Load the active profile through the seam or the credentials
        file.

        :param ctx: Invocation context.

        :returns: :class:`CliProfile`.
    """
    if ctx.profile_loader is not None:
        rtnval = ctx.profile_loader(ctx.profile_name)
        return rtnval
    rtnval = credentials.load_profile(profile_name=ctx.profile_name, environ=ctx.environ)
    return rtnval


def resolve_profile(*, ctx: CliContext, quiet: bool = False) -> CliProfile:
    """
        Resolve the effective profile for this invocation (see module
        docs for precedence), warn about disabled TLS verification and
        an expired stored token, and normalize the server URL.

        :param ctx: Invocation context.
        :param quiet: Print no notes or warnings (``--help`` only
                      needs the server URL to find the cached command
                      list).

        :returns: :class:`CliProfile`.
        :raises: NotConfiguredError, ProfileNotFoundError,
                 CredentialsFilePermissionError,
                 CredentialsFileInvalidError
    """
    if quiet is True:
        silent_ctx = replace(ctx, stderr=_NullStream())
        rtnval = resolve_profile(ctx=silent_ctx, quiet=False)
        return rtnval

    url_override = ctx.server_url
    if url_override is None or len(url_override.strip()) == 0:
        url_override = ctx.environ.get(PYC_SERVER_URL_ENV_VAR, "") or None
    token_override = ctx.environ.get(PYC_TOKEN_ENV_VAR, "") or None

    try:
        profile = _load_stored_profile(ctx)
    except CredentialsFileNotFoundError:
        if url_override is None:
            path = credentials.credentials_path(environ=ctx.environ)
            raise NotConfiguredError(
                not_configured_message(ctx=ctx, reason="no credentials file at {}".format(path))
            ) from None
        profile = _ephemeral_profile(ctx=ctx, server_url=url_override, token=token_override)
    except ProfileNotFoundError:
        if url_override is None:
            raise
        profile = _ephemeral_profile(ctx=ctx, server_url=url_override, token=token_override)

    if url_override is not None:
        profile = replace(profile, server_url=url_override)
    if token_override is not None:
        profile = replace(profile, bearer_token=token_override, bearer_token_expires_at=None)
    if ctx.timeout_seconds is not None:
        profile = replace(profile, timeout_seconds=ctx.timeout_seconds)

    if len((profile.server_url or "").strip()) == 0:
        raise NotConfiguredError(
            not_configured_message(
                ctx=ctx,
                reason="profile '{}' has no server_url".format(profile.profile_name),
            )
        ) from None

    profile = replace(profile, server_url=normalize_server_url(ctx=ctx, server_url=profile.server_url))

    if profile.verify_tls is False:
        ctx.note(
            "tls",
            "warning: TLS certificate verification is disabled for profile '{}'"
            " (verify_tls = false); anyone on the network path can read or"
            " alter this traffic.".format(profile.profile_name),
        )

    expires_at = profile.bearer_token_expires_at
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        now = ctx.now()
        if expires_at <= now:
            ctx.note(
                "expired",
                "warning: the API token stored in profile '{}' expired on {};"
                " run 'pyc login' with a new token.".format(
                    profile.profile_name, expires_at.date().isoformat()
                ),
            )
        elif expires_at - now <= timedelta(days=TOKEN_EXPIRY_WARNING_DAYS):
            remaining_days = max((expires_at - now).days, 0)
            ctx.note(
                "expiring",
                "warning: the API token stored in profile '{}' expires {} ({}); create a new one"
                " under Account > API tokens and run 'pyc login'.".format(
                    profile.profile_name,
                    "within a day" if remaining_days == 0 else "in {} day(s)".format(remaining_days),
                    expires_at.date().isoformat(),
                ),
            )
    rtnval = profile
    return rtnval


__all__ = [
    "API_PREFIX",
    "CliContext",
    "EXAMPLE_SERVER_URL",
    "PYC_SERVER_URL_ENV_VAR",
    "PYC_TOKEN_ENV_VAR",
    "normalize_server_url",
    "not_configured_message",
    "resolve_profile",
]
