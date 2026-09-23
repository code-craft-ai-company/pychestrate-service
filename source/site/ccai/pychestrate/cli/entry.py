"""
.. module:: cli.entry
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``pyc`` entry-point dispatcher.

.. moduleauthor:: Code Craft AI LLC

The entry point handles four classes of invocation:

1. Static metadata commands (``--version``, ``--help``, and the help of
   built-in commands) that never touch the network.
2. Built-in commands: ``login``, ``logout``, ``whoami``, ``config``,
   ``commands``, ``runs wait``, ``plugin-api catalog``, ``ext``.
3. API commands generated from the server's OpenAPI document
   (``pyc projects list``, ``pyc projects get-by-slug demo`` ...; see
   :mod:`cli.commands.api`).
4. Failures, each reported as one ``error: ...`` line (no traceback)
   with a documented exit code (see :mod:`cli.exit_codes`).

Global options (``--profile``, ``--server-url``, ``--timeout``) may
appear anywhere on the command line.

The console script is :func:`console_main`
(``pyc = "ccai.pychestrate.cli.entry:console_main"``).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import sys
import traceback

from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ccai.pychestrate.cli import (
    exit_codes,
    parser,
    transport,
)
from ccai.pychestrate.cli.argparsing import ParserExit
from ccai.pychestrate.cli.context import CliContext, resolve_profile
from ccai.pychestrate.cli.exceptions import (
    AuthenticationError,
    BadRequestError,
    CliUsageError,
    CommandTreeBuildError,
    ConflictError,
    CredentialsFileInvalidError,
    CredentialsFileNotFoundError,
    CredentialsFilePermissionError,
    NotConfiguredError,
    NotFoundError,
    OpenApiUnavailableError,
    PermissionDeniedError,
    ProfileNotFoundError,
    RateLimitedError,
    RunFailedError,
    ServerError,
    ServerUnreachableError,
    WaitTimeoutError,
)
from ccai.pychestrate.cli.extensions.discovery import (
    find_descriptor,
    find_listed_route,
    find_subcommand_class,
    parse_ext_listing,
)
from ccai.pychestrate.cli.models import CliProfile, RestOperation


CLI_PROG: str = "pyc"
CLI_VERSION: str = "0.2.0"

PYC_DEBUG_ENV_VAR: str = "PYC_DEBUG"

_PLUGIN_API_CATALOG_VERB: str = "catalog"
_EXT_LIST_VERB: str = "list"

#: Built-in commands, as listed when a command is unknown.
_BUILTIN_COMMANDS: Tuple[str, ...] = (
    "'login'",
    "'logout'",
    "'whoami'",
    "'config ...'",
    "'commands'",
    "'project list'",
    "'runs wait <run_id>'",
    "'plugin-api catalog [<entry-name>]'",
    "'ext list'",
    "'ext <ext-name> <verb> [args]'",
)

_TOP_HELP_LINES: Tuple[str, ...] = (
    "usage: pyc [--profile NAME] [--server-url URL] [--timeout SECONDS] <command> [args]",
    "",
    "The Pychestrate command line. API commands are generated from the server's",
    "OpenAPI document; 'pyc commands' lists them.",
    "",
    "getting started:",
    "  login [--with-token]         Store a server URL and an API token (mode 0600).",
    "                               Create the token in the web UI: Account > API tokens.",
    "  whoami [--json]              Show who the stored token authenticates as.",
    "  logout [--revoke]            Forget (and optionally revoke) the stored token.",
    "  config init|set|get|unset|profiles|path",
    "                               Manage the credentials file.",
    "",
    "API commands:",
    "  <noun> <verb> [args]         e.g. 'pyc projects list', 'pyc projects get-by-slug demo'.",
    "                               Bodies: --data JSON|@FILE|- and --set KEY=VALUE.",
    "  commands                     List every API command the server offers.",
    "  project list                 List projects (same as 'projects list').",
    "  runs wait <run_id>           Wait for a run: exit 0 on success, 10 on failure.",
    "                               POST commands take --wait to do this for their run.",
    "",
    "extensions:",
    "  plugin-api catalog           List the published plugin-api surface.",
    "  plugin-api catalog <n>       Read a single catalog entry by name.",
    "  ext list                     List concrete extension mounts.",
    "  ext <name> <verb> [args]     Invoke a CLISubcommandExtension verb.",
    "",
    "global options (anywhere on the line):",
    "  --profile NAME               Credentials profile (PYC_PROFILE; default 'default').",
    "  --server-url URL             Server root URL (PYC_SERVER_URL); overrides the profile.",
    "  --timeout SECONDS            Per-request timeout (default 30).",
    "  --version, --help",
    "",
    "environment: PYC_SERVER_URL, PYC_TOKEN, PYC_PROFILE, PYC_CREDENTIALS_PATH,",
    "  PYC_OPENAPI_CACHE_DIR, XDG_CONFIG_HOME, XDG_CACHE_HOME, PYC_DEBUG.",
    "",
    "exit codes: 0 ok; 2 usage (or server 400/422); 3 authentication/permission;",
    "  4 not found; 5 conflict; 6 rate limited; 7 server error or a non-API answer;",
    "  8 cannot reach the server; 10 run failed (--wait); 11 wait timed out;",
    "  13 configuration / credentials file.",
    "",
    "see 'pyc <noun> --help' or 'pyc <noun> <verb> --help'.",
    "",
)


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


def _print_top_help(*, stream) -> None:
    """
        Print the static top-level help summary.

        :param stream: Stream to write to.

        :returns: None.
    """
    stream.write("\n".join(_TOP_HELP_LINES))
    return


def _is_help_flag(arg: str) -> bool:
    """
        Return True when ``arg`` requests help output.

        :param arg: Single argv token.

        :returns: Boolean.
    """
    rtnval = arg in ("-h", "--help", "help")
    return rtnval


def _is_version_flag(arg: str) -> bool:
    """
        Return True when ``arg`` requests the version banner.

        :param arg: Single argv token.

        :returns: Boolean.
    """
    rtnval = arg in ("--version", "version")
    return rtnval


_STATIC_NOUN_HELP: Dict[str, str] = {
    "plugin-api": (
        "usage: pyc plugin-api <verb> [args]\n\n"
        "verbs:\n"
        "  catalog              List every published plugin-api entry.\n"
        "  catalog <entry>      Read a single entry by name.\n"
    ),
    "ext": (
        "usage: pyc ext <verb> [args]\n\n"
        "verbs:\n"
        "  list                       List the concrete extension mounts the host discovered.\n"
        "  <ext-name> <verb> [args]   Invoke a CLISubcommandExtension subcommand; the route\n"
        "                             comes from the server's /api/v1/ext listing.\n"
    ),
    "project": (
        "usage: pyc project <verb> [args]\n\n"
        "verbs:\n"
        "  list   List projects (the server's full set: 'pyc projects --help').\n"
    ),
}

_STATIC_VERB_HELP: Dict[Tuple[str, str], str] = {
    ("plugin-api", _PLUGIN_API_CATALOG_VERB): (
        "usage: pyc plugin-api catalog [<entry-name>]\n\n"
        "Read the published plugin-api surface.\n"
        "With no argument, lists every entry.\n"
        "With an argument, reads the named entry's metadata.\n"
    ),
    ("ext", _EXT_LIST_VERB): (
        "usage: pyc ext list\n\n"
        "List every concrete extension route the host has discovered.\n"
        "Each line names ext_name, method, full path, and the\n"
        "handler class.\n"
    ),
}


# ---------------------------------------------------------------------------
# Global options
# ---------------------------------------------------------------------------


_GLOBAL_OPTIONS_WITH_VALUE: Tuple[str, ...] = ("--profile", "--server-url", "--timeout")


def _split_global_args(*, argv: Sequence[str]) -> Tuple[Dict, List[str]]:
    """
        Pull ``--profile``, ``--server-url`` and ``--timeout`` (either
        ``--opt value`` or ``--opt=value``) out of argv wherever they
        appear. A leading ``--`` is dropped.

        :param argv: Tokens after ``pyc``.

        :returns: Tuple of (parsed_globals_dict, remainder_list).
        :raises: CliUsageError for a missing or invalid value.
    """
    parsed: Dict = {"profile": None, "server_url": None, "timeout": None}
    remainder: List[str] = []
    tokens = list(argv)
    if len(tokens) > 0 and tokens[0] == "--":
        tokens = tokens[1:]
    index = 0
    while index < len(tokens):
        token = tokens[index]
        matched = None
        value = None
        for option in _GLOBAL_OPTIONS_WITH_VALUE:
            if token == option:
                matched = option
                if index + 1 >= len(tokens) or tokens[index + 1].startswith("--"):
                    raise CliUsageError("{} needs a value".format(option))
                value = tokens[index + 1]
                index = index + 2
                break
            if token.startswith(option + "="):
                matched = option
                value = token.split("=", 1)[1]
                index = index + 1
                break
        if matched is None:
            remainder.append(token)
            index = index + 1
            continue
        key = matched[2:].replace("-", "_")
        parsed[key] = value

    if parsed["timeout"] is not None:
        try:
            seconds = float(parsed["timeout"])
        except ValueError:
            seconds = -1.0
        if seconds <= 0:
            raise CliUsageError("--timeout must be a number of seconds greater than 0")
        parsed["timeout"] = seconds
    for key, option in (("profile", "--profile"), ("server_url", "--server-url")):
        if parsed[key] is not None and len(parsed[key].strip()) == 0:
            raise CliUsageError("{} needs a value".format(option))

    rtnval = (parsed, remainder)
    return rtnval


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def _map_exception_to_exit_code(*, xcpt: Exception, stderr) -> int:
    """
        Translate a CLI exception into the documented exit code and one
        ``error: ...`` report on stderr.

        :param xcpt: Captured exception.
        :param stderr: Stream for diagnostics.

        :returns: Process exit code.
    """
    table = (
        (NotConfiguredError, exit_codes.EXIT_CREDENTIALS_ERROR),
        (CredentialsFileNotFoundError, exit_codes.EXIT_CREDENTIALS_ERROR),
        (CredentialsFilePermissionError, exit_codes.EXIT_CREDENTIALS_ERROR),
        (CredentialsFileInvalidError, exit_codes.EXIT_CREDENTIALS_ERROR),
        (ProfileNotFoundError, exit_codes.EXIT_USAGE_ERROR),
        (CliUsageError, exit_codes.EXIT_USAGE_ERROR),
        (BadRequestError, exit_codes.EXIT_USAGE_ERROR),
        (AuthenticationError, exit_codes.EXIT_AUTHENTICATION_ERROR),
        (NotFoundError, exit_codes.EXIT_NOT_FOUND),
        (ConflictError, exit_codes.EXIT_CONFLICT),
        (RateLimitedError, exit_codes.EXIT_RATE_LIMITED),
        (ServerUnreachableError, exit_codes.EXIT_CONNECTION_ERROR),
        (RunFailedError, exit_codes.EXIT_RUN_FAILED),
        (WaitTimeoutError, exit_codes.EXIT_WAIT_TIMEOUT),
        (ServerError, exit_codes.EXIT_SERVER_ERROR),
        (OpenApiUnavailableError, exit_codes.EXIT_SERVER_ERROR),
        (CommandTreeBuildError, exit_codes.EXIT_SERVER_ERROR),
    )
    for exception_type, code in table:
        if isinstance(xcpt, exception_type):
            message = str(xcpt)
            if isinstance(xcpt, AuthenticationError) and not isinstance(xcpt, PermissionDeniedError):
                if "pyc login" not in message:
                    message = (
                        "{}\nhint: store an API token with 'pyc login' (or set PYC_TOKEN);"
                        " 'pyc config profiles' shows what is configured.".format(message)
                    )
            stderr.write("error: {}\n".format(message))
            return code

    stderr.write(
        "error: internal error in pyc: {}: {} (set {}=1 for a traceback)\n".format(
            type(xcpt).__name__, xcpt, PYC_DEBUG_ENV_VAR
        )
    )
    return exit_codes.EXIT_SERVER_ERROR


def _unknown_command_error(*, noun: str, verb: Optional[str], detail: Optional[str] = None) -> CliUsageError:
    """
        Build the usage error for an unknown command, listing the
        built-in commands.

        :param noun: First word.
        :param verb: Second word or ``None``.
        :param detail: Extra explanation line.

        :returns: :class:`CliUsageError`.
    """
    shown = noun if verb is None else "{} {}".format(noun, verb)
    lines = ["'{}' is not a known command.".format(shown)]
    if detail is not None:
        lines.append(detail)
    lines.append("built-in: {}".format(", ".join(_BUILTIN_COMMANDS)))
    lines.append("run 'pyc commands' for the API commands the server offers.")
    rtnval = CliUsageError("\n".join(lines))
    return rtnval


# ---------------------------------------------------------------------------
# plugin-api / ext
# ---------------------------------------------------------------------------


def _plugin_api_catalog_operation() -> RestOperation:
    """
        Operation backing ``pyc plugin-api catalog``.

        :returns: :class:`RestOperation`.
    """
    rtnval = RestOperation(
        operation_id="plugin_api_catalog",
        method="GET",
        path_template="/api/v1/plugin-api/_meta/catalog",
    )
    return rtnval


def _plugin_api_catalog_entry_operation() -> RestOperation:
    """
        Operation backing ``pyc plugin-api catalog <entry-name>``.

        :returns: :class:`RestOperation`.
    """
    rtnval = RestOperation(
        operation_id="plugin_api_catalog_entry",
        method="GET",
        path_template="/api/v1/plugin-api/_meta/catalog/{name}",
        path_param_names=("name",),
        required_path_param_names=("name",),
    )
    return rtnval


def _plugin_api_mounts_operation() -> RestOperation:
    """
        Operation backing ``pyc ext list``.

        :returns: :class:`RestOperation`.
    """
    rtnval = RestOperation(
        operation_id="plugin_api_mounts",
        method="GET",
        path_template="/api/v1/plugin-api/_meta/mounts",
    )
    return rtnval


def _ext_listing_operation() -> RestOperation:
    """
        ``GET /api/v1/ext``: the server's own list of extension routes.

        :returns: :class:`RestOperation`.
    """
    rtnval = RestOperation(
        operation_id="plugin_api_list_ext",
        method="GET",
        path_template="/api/v1/ext",
    )
    return rtnval


def _send(*, ctx: CliContext, profile: CliProfile, operation: RestOperation,
          path_params: Optional[Dict[str, str]] = None,
          query_params: Optional[Dict[str, str]] = None):
    """
        Send one request with the invocation's opener seam.

        :returns: :class:`RestResponse`.
    """
    rtnval = transport.execute_request(
        profile=profile,
        operation=operation,
        path_params=path_params or {},
        query_params=query_params or {},
        body=None,
        idempotency_key=None,
        timeout_seconds=None,
        opener=ctx.request_opener,
    )
    return rtnval


def _emit_json(*, ctx: CliContext, body, empty_text: str) -> None:
    """
        Print a response body the way the M1 commands did.

        :returns: None.
    """
    if body is None:
        ctx.stdout.write(empty_text + "\n")
    elif isinstance(body, (dict, list)):
        ctx.stdout.write(json.dumps(body, indent=2))
        ctx.stdout.write("\n")
    else:
        ctx.stdout.write("{}\n".format(body))
    return


def _handle_plugin_api_catalog(*, ctx: CliContext, entry_name: Optional[str]) -> int:
    """
        ``pyc plugin-api catalog [<entry-name>]``.

        :returns: Exit code.
    """
    profile = resolve_profile(ctx=ctx)
    if entry_name is None:
        response = _send(ctx=ctx, profile=profile, operation=_plugin_api_catalog_operation())
        _emit_json(ctx=ctx, body=response.body, empty_text="{}")
    else:
        response = _send(
            ctx=ctx, profile=profile, operation=_plugin_api_catalog_entry_operation(),
            path_params={"name": entry_name},
        )
        _emit_json(ctx=ctx, body=response.body, empty_text="{}")
    return exit_codes.EXIT_OK


def _handle_ext_list(*, ctx: CliContext) -> int:
    """
        ``pyc ext list``.

        :returns: Exit code.
    """
    profile = resolve_profile(ctx=ctx)
    response = _send(ctx=ctx, profile=profile, operation=_plugin_api_mounts_operation())
    _emit_json(ctx=ctx, body=response.body, empty_text="[]")
    return exit_codes.EXIT_OK


def _parse_ext_invocation_args(
        *,
        argv_tokens: Sequence[str]
    ) -> Tuple[List[str], Dict[str, str]]:
    """
        Split the trailing tokens of a ``pyc ext`` invocation into
        positional + flag halves. ``--flag=value`` and
        ``--flag value`` are both accepted.

        :param argv_tokens: Tokens after ``pyc ext <ext_name> <verb>``.

        :returns: ``(positional, flags)`` tuple.
    """
    positional: List[str] = []
    flags: Dict[str, str] = {}
    iterator = iter(argv_tokens)
    for token in iterator:
        if token.startswith("--") and "=" in token:
            flag_name, _, flag_value = token[2:].partition("=")
            flags[flag_name] = flag_value
            continue
        if token.startswith("--"):
            flag_name = token[2:]
            flag_value = next(iterator, "")
            flags[flag_name] = flag_value
            continue
        positional.append(token)
    rtnval = (positional, flags)
    return rtnval


def _handle_ext_invocation(*, ctx: CliContext, ext_name: str, verb: str, tokens: Sequence[str]) -> int:
    """
        ``pyc ext <ext_name> <verb> [positional...] [--flag=value...]``.

        The verb's argument layout comes from the locally installed
        :class:`CLISubcommandExtension`; the route (method and URL)
        comes from the server's ``/api/v1/ext`` listing, so the command
        runs exactly what the server mounts.

        :returns: Exit code.
    """
    subcommand_class = find_subcommand_class(ext_name=ext_name)
    if subcommand_class is None:
        raise CliUsageError("no extension is registered under '{}'.".format(ext_name))
    descriptor = find_descriptor(subcommand_class=subcommand_class, verb=verb)
    if descriptor is None:
        raise CliUsageError("extension '{}' does not declare verb '{}'.".format(ext_name, verb))

    if any(_is_help_flag(token) for token in tokens if token.startswith("-")):
        flags_text = " ".join("[--{} VALUE]".format(flag) for flag in descriptor.flag_arg_names)
        positional_text = " ".join("<{}>".format(name) for name in descriptor.positional_arg_names)
        ctx.stdout.write(
            "usage: pyc ext {} {} {} {}\n\n{}\n".format(
                ext_name, verb, positional_text, flags_text, descriptor.description
            ).replace("  ", " ")
        )
        return exit_codes.EXIT_OK

    positional_args, flag_args = _parse_ext_invocation_args(argv_tokens=tokens)
    if len(positional_args) != len(descriptor.positional_arg_names):
        raise CliUsageError(
            "'{} {}' expects {} positional argument(s); got {}.".format(
                ext_name, verb, len(descriptor.positional_arg_names), len(positional_args)
            )
        )
    for flag_name in flag_args.keys():
        if flag_name not in descriptor.flag_arg_names:
            raise CliUsageError(
                "'{} {}' does not declare flag '--{}'.".format(ext_name, verb, flag_name)
            )

    profile = resolve_profile(ctx=ctx)
    listing = _send(ctx=ctx, profile=profile, operation=_ext_listing_operation())
    routes, dynamic_mount = parse_ext_listing(body=listing.body)
    route = find_listed_route(routes=routes, ext_name=ext_name, verb=verb)
    if route is None:
        raise NotFoundError(
            "the server at {} does not mount /api/v1/ext/{}/{} (its /api/v1/ext listing"
            " names {} extension route(s)); the '{}' extension is not installed there.".format(
                profile.server_url, ext_name, verb, len(routes), ext_name
            )
        )

    query_params: Dict[str, str] = {}
    for flag_name in descriptor.flag_arg_names:
        if flag_name in flag_args:
            query_params[flag_name] = flag_args[flag_name]

    operation = RestOperation(
        operation_id=descriptor.operation_id,
        method=route.method,
        path_template=route.full_path,
    )
    try:
        response = _send(ctx=ctx, profile=profile, operation=operation, query_params=query_params)
    except NotFoundError as xcpt:
        if dynamic_mount is not None and dynamic_mount != "mounted":
            raise NotFoundError(
                "{} -- the server lists {} but reports dynamic_mount={!r}: it does not"
                " serve extension routes yet.".format(xcpt, route.full_path, dynamic_mount)
            ) from None
        raise
    _emit_json(ctx=ctx, body=response.body, empty_text="{}")
    return exit_codes.EXIT_OK


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _handle_commands(*, ctx: CliContext, args: Sequence[str]) -> int:
    """
        ``pyc commands [--refresh]``.

        :returns: Exit code.
    """
    from ccai.pychestrate.cli.commands import api as api_commands  # noqa: E402

    refresh = "--refresh" in args
    profile = resolve_profile(ctx=ctx)
    tree, source = api_commands.load_command_tree(ctx=ctx, profile=profile, force_refresh=refresh)
    ctx.stdout.write(api_commands.render_command_list(tree=tree, source=source))
    return exit_codes.EXIT_OK


def _handle_api_noun_help(*, ctx: CliContext, noun: str) -> int:
    """
        ``pyc <noun> --help`` for a noun of the generated tree.

        :returns: Exit code.
    """
    from ccai.pychestrate.cli.commands import api as api_commands  # noqa: E402

    try:
        profile = resolve_profile(ctx=ctx)
        tree, _source = api_commands.load_command_tree(ctx=ctx, profile=profile)
    except (NotConfiguredError, CredentialsFileNotFoundError, ProfileNotFoundError):
        tree = api_commands.fallback_command_tree()

    canonical = parser.resolve_noun(tree=tree, noun=noun)
    if canonical is None:
        ctx.stdout.write(
            "noun '{}' is not known here. Run 'pyc commands' for the server's API commands,"
            " or 'pyc --help'.\n".format(noun)
        )
        return exit_codes.EXIT_OK
    ctx.stdout.write(api_commands.render_noun_help(tree=tree, noun=canonical))
    return exit_codes.EXIT_OK


def _handle_api_command(*, ctx: CliContext, noun: str, verb: str, args: Sequence[str]) -> int:
    """
        Run a generated API command, loading the command tree first.

        :returns: Exit code.
    """
    from ccai.pychestrate.cli.commands import api as api_commands  # noqa: E402

    wants_help = any(_is_help_flag(token) for token in args if token.startswith("-"))
    try:
        profile = resolve_profile(ctx=ctx)
    except (NotConfiguredError, CredentialsFileNotFoundError, ProfileNotFoundError) as xcpt:
        fallback = api_commands.fallback_command_tree()
        fallback_descriptor = parser.lookup_command(tree=fallback, noun=noun, verb=verb)
        if fallback_descriptor is None:
            raise _unknown_command_error(
                noun=noun, verb=verb,
                detail=(
                    "pyc could not load the server's command list: {}".format(
                        str(xcpt).splitlines()[0]
                    )
                ),
            ) from None
        if wants_help is True:
            api_commands.build_command_parser(ctx=ctx, descriptor=fallback_descriptor).print_help()
            return exit_codes.EXIT_OK
        raise

    tree, source = api_commands.load_command_tree(ctx=ctx, profile=profile)
    descriptor = parser.lookup_command(tree=tree, noun=noun, verb=verb)
    if descriptor is None and source == "cache":
        tree, source = api_commands.load_command_tree(ctx=ctx, profile=profile, force_refresh=True)
        descriptor = parser.lookup_command(tree=tree, noun=noun, verb=verb)
    if descriptor is None:
        canonical = parser.resolve_noun(tree=tree, noun=noun)
        if canonical is not None:
            verbs = ", ".join(entry.verb for entry in parser.verbs_for(tree=tree, noun=canonical))
            raise CliUsageError(
                "'{}' has no verb '{}'. verbs: {}".format(canonical, verb, verbs)
            )
        detail = None
        if source == "builtin":
            detail = "(the server's OpenAPI document could not be loaded, so only pyc's built-in commands are known)"
        raise _unknown_command_error(noun=noun, verb=verb, detail=detail)

    if wants_help is True:
        command_parser = api_commands.build_command_parser(ctx=ctx, descriptor=descriptor)
        command_parser.print_help()
        return exit_codes.EXIT_OK

    rtnval = api_commands.run_api_command(ctx=ctx, profile=profile, descriptor=descriptor, args=args)
    return rtnval


def _dispatch(*, ctx: CliContext, remainder: List[str]) -> int:
    """
        Route one invocation.

        :param ctx: Invocation context.
        :param remainder: Argv without global options.

        :returns: Exit code.
    """
    if len(remainder) == 0 or _is_help_flag(remainder[0]):
        _print_top_help(stream=ctx.stdout)
        return exit_codes.EXIT_OK
    if _is_version_flag(remainder[0]):
        ctx.stdout.write("pyc {}\n".format(CLI_VERSION))
        return exit_codes.EXIT_OK

    noun = remainder[0]
    if noun.startswith("-"):
        raise CliUsageError("unknown option '{}'. See 'pyc --help'.".format(noun))
    rest = remainder[1:]

    if noun == "login":
        from ccai.pychestrate.cli.commands.auth import run_login  # noqa: E402
        return run_login(ctx=ctx, args=rest)
    if noun == "logout":
        from ccai.pychestrate.cli.commands.auth import run_logout  # noqa: E402
        return run_logout(ctx=ctx, args=rest)
    if noun == "whoami":
        from ccai.pychestrate.cli.commands.auth import run_whoami  # noqa: E402
        return run_whoami(ctx=ctx, args=rest)
    if noun == "config":
        from ccai.pychestrate.cli.commands.config import run_config  # noqa: E402
        if len(rest) == 0:
            rest = ["--help"]
        return run_config(ctx=ctx, args=rest)
    if noun == "commands":
        if len(rest) > 0 and _is_help_flag(rest[0]):
            ctx.stdout.write("usage: pyc commands [--refresh]\n\nList every API command the server offers.\n")
            return exit_codes.EXIT_OK
        return _handle_commands(ctx=ctx, args=rest)

    if len(rest) > 0 and _is_help_flag(rest[0]):
        if noun in _STATIC_NOUN_HELP:
            ctx.stdout.write(_STATIC_NOUN_HELP[noun])
            return exit_codes.EXIT_OK
        return _handle_api_noun_help(ctx=ctx, noun=noun)

    if len(rest) == 0:
        raise CliUsageError(
            "usage: pyc <noun> <verb> [args] -- '{}' needs a verb; see 'pyc {} --help'.".format(noun, noun)
        )
    verb = rest[0]
    args = rest[1:]

    if len(args) > 0 and _is_help_flag(args[0]) and (noun, verb) in _STATIC_VERB_HELP:
        ctx.stdout.write(_STATIC_VERB_HELP[(noun, verb)])
        return exit_codes.EXIT_OK

    if noun == "plugin-api":
        if verb != _PLUGIN_API_CATALOG_VERB:
            raise _unknown_command_error(noun=noun, verb=verb)
        entry_name = args[0] if len(args) > 0 else None
        return _handle_plugin_api_catalog(ctx=ctx, entry_name=entry_name)

    if noun == "ext":
        if verb == _EXT_LIST_VERB:
            return _handle_ext_list(ctx=ctx)
        if len(args) == 0:
            raise CliUsageError("usage: pyc ext <ext-name> <verb> [args]")
        return _handle_ext_invocation(ctx=ctx, ext_name=verb, verb=args[0], tokens=args[1:])

    if parser.normalize_word(noun) in ("runs", "run") and verb == "wait":
        from ccai.pychestrate.cli.commands.runs import run_runs_wait  # noqa: E402
        return run_runs_wait(ctx=ctx, profile_resolver=lambda: resolve_profile(ctx=ctx), args=args)

    return _handle_api_command(ctx=ctx, noun=noun, verb=verb, args=args)


def main(
        *,
        argv: Optional[Sequence[str]],
        stdout=None,
        stderr=None,
        openapi_fetcher: Optional[Callable[[], Dict]] = None,
        request_opener=None,
        profile_loader: Optional[Callable[[Optional[str]], CliProfile]] = None,
        stdin=None,
        environ: Optional[Mapping[str, str]] = None,
        prompt_secret: Optional[Callable[[str], str]] = None,
        sleep: Optional[Callable[[float], None]] = None
    ) -> int:
    """
        CLI entry point.

        :param argv: Override argv (mainly for tests). ``None`` defaults
                     to :data:`sys.argv` slicing.
        :param stdout: Output stream. Defaults to :data:`sys.stdout`.
        :param stderr: Diagnostic stream. Defaults to :data:`sys.stderr`.
        :param openapi_fetcher: Test seam replacing the live HTTP fetch.
        :param request_opener: Test seam replacing the live urllib
                               opener.
        :param profile_loader: Test seam replacing
                               :func:`credentials.load_profile`.
        :param stdin: Input stream. Defaults to :data:`sys.stdin`.
        :param environ: Environment. Defaults to :data:`os.environ`.
        :param prompt_secret: Test seam replacing ``getpass``.
        :param sleep: Test seam replacing ``time.sleep`` (``--wait``).

        :returns: Process exit code.
    """
    if argv is None:
        argv_list: Sequence[str] = sys.argv[1:]
    else:
        argv_list = list(argv)

    out_stream = stdout if stdout is not None else sys.stdout
    err_stream = stderr if stderr is not None else sys.stderr
    in_stream = stdin if stdin is not None else sys.stdin
    env = environ if environ is not None else os.environ

    try:
        parsed_globals, remainder = _split_global_args(argv=argv_list)
    except CliUsageError as xcpt:
        rtnval = _map_exception_to_exit_code(xcpt=xcpt, stderr=err_stream)
        return rtnval

    ctx = CliContext(
        stdout=out_stream,
        stderr=err_stream,
        stdin=in_stream,
        environ=env,
        profile_name=parsed_globals.get("profile"),
        server_url=parsed_globals.get("server_url"),
        timeout_seconds=parsed_globals.get("timeout"),
        openapi_fetcher=openapi_fetcher,
        request_opener=request_opener,
        profile_loader=profile_loader,
        prompt_secret=prompt_secret,
        sleep=sleep,
    )

    try:
        rtnval = _dispatch(ctx=ctx, remainder=list(remainder))
    except ParserExit as xcpt:
        rtnval = xcpt.status
    except KeyboardInterrupt:
        err_stream.write("error: interrupted\n")
        rtnval = 130
    except Exception as xcpt:  # noqa: BLE001 — every failure becomes one error line
        if len(str(env.get(PYC_DEBUG_ENV_VAR, ""))) > 0:
            traceback.print_exc(file=err_stream)
        rtnval = _map_exception_to_exit_code(xcpt=xcpt, stderr=err_stream)
    return rtnval


def console_main() -> None:
    """
        Console-script entry point (``pyc``): run :func:`main` on
        :data:`sys.argv` and exit with its code.

        :returns: Never returns.
    """
    try:
        code = main(argv=None)
    except BrokenPipeError:
        # ``pyc ... | head`` closed the pipe; that is not an error.
        code = exit_codes.EXIT_OK
    sys.exit(code)


if __name__ == "__main__":
    console_main()
