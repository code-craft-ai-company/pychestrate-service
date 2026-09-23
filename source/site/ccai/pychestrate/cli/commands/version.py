"""
.. module:: cli.commands.version
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``pyc version``: the versions of pyc, the service it
               talks to, and the service's REST API.

.. moduleauthor:: Code Craft AI LLC

``pyc --version`` prints pyc's own version and never touches the
network. ``pyc version`` also asks the configured server for its
OpenAPI document (``GET /api/v1/_meta/openapi.json``) and reports:

* ``pyc`` -- :data:`cli.version.PYC_VERSION` (and the Python running it);
* ``server`` -- the server URL;
* ``service`` -- the service's own version (``info.x-service-version``);
* ``api`` -- the REST contract's version (``info.version``).

With no server configured it prints pyc's version and says so (exit
0); when the server cannot be asked it prints pyc's version and exits
with the error's code.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import platform

from typing import Any, Dict, Optional, Sequence

from ccai.pychestrate.cli import exit_codes, openapi_cache, renderer, version
from ccai.pychestrate.cli.argparsing import CliArgumentParser
from ccai.pychestrate.cli.context import CliContext, resolve_profile
from ccai.pychestrate.cli.exceptions import (
    CredentialsFileNotFoundError,
    NotConfiguredError,
    ProfileNotFoundError,
)


#: The OpenAPI ``info`` member naming the service's own version.
SERVICE_VERSION_MEMBER: str = "x-service-version"

UNKNOWN_TEXT: str = "unknown"


def _print_versions(*, ctx: CliContext, report: Dict[str, Any]) -> None:
    """
        Print the version report: ``field  value`` lines by default,
        the ``--output`` format when one is asked for.

        :param ctx: Invocation context.
        :param report: Versions.

        :returns: None.
    """
    wants_document = (
        ctx.output.output_format not in (None, renderer.FORMAT_TABLE)
        or ctx.output.quiet is True
        or len(ctx.output.fields) > 0
    )
    if wants_document is True:
        ctx.emit_result(value=report, identifier_fields=("pyc",))
        return
    lines = ["pyc      {} (python {})".format(report["pyc"], report["python"])]
    if report.get("server_url", None) is not None:
        lines.append("server   {}".format(report["server_url"]))
        lines.append("service  {}".format(report.get("service_version", None) or UNKNOWN_TEXT))
        lines.append("api      {}".format(report.get("api_version", None) or UNKNOWN_TEXT))
    ctx.stdout.write("\n".join(lines) + "\n")
    return


def run_version(*, ctx: CliContext, args: Sequence[str]) -> int:
    """
        ``pyc version``.

        :param ctx: Invocation context.
        :param args: Arguments after ``version``.

        :returns: Exit code.
    """
    from ccai.pychestrate.cli.commands import api as api_commands  # noqa: E402

    command_parser = CliArgumentParser(
        prog="pyc version",
        description=(
            "Show the versions of pyc, of the service the active profile points at,\n"
            "and of that service's REST API (read from its OpenAPI document).\n"
            "'pyc --version' prints only pyc's version, without contacting the server."
        ),
        out_stream=ctx.stdout,
        err_stream=ctx.stderr,
    )
    command_parser.parse_args(list(args))

    report: Dict[str, Any] = {
        "pyc": version.PYC_VERSION,
        "python": platform.python_version(),
        "server_url": None,
        "service_version": None,
        "api_version": None,
    }
    try:
        profile = resolve_profile(ctx=ctx)
    except (NotConfiguredError, CredentialsFileNotFoundError, ProfileNotFoundError):
        _print_versions(ctx=ctx, report=report)
        ctx.note("version-no-server", "note: no server is configured, so only pyc's version is known; run 'pyc login'.")
        return exit_codes.EXIT_OK

    report["server_url"] = profile.server_url
    fetcher = ctx.openapi_fetcher
    if fetcher is None:
        fetcher = api_commands.build_default_openapi_fetcher(ctx=ctx, profile=profile)
    try:
        document = fetcher()
    except Exception:
        _print_versions(ctx=ctx, report=report)
        raise
    openapi_cache.store(server_url=profile.server_url, document=document, environ=ctx.environ)

    info: Optional[Dict[str, Any]] = document.get("info", None) if isinstance(document, dict) else None
    if isinstance(info, dict):
        report["service_version"] = info.get(SERVICE_VERSION_MEMBER, None)
        report["api_version"] = info.get("version", None)
    _print_versions(ctx=ctx, report=report)
    rtnval = exit_codes.EXIT_OK
    return rtnval


__all__ = [
    "SERVICE_VERSION_MEMBER",
    "run_version",
]
