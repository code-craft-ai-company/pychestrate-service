"""
.. module:: cli.commands.ext
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``pyc ext ...`` and ``pyc plugin-api catalog``.

.. moduleauthor:: Code Craft AI LLC

* ``pyc ext list`` -- the extension routes the server mounts
  (``GET /api/v1/plugin-api/_meta/mounts``).
* ``pyc ext <ext-name> <verb> [args]`` -- a verb of a
  :class:`CLISubcommandExtension` installed next to ``pyc``. The verb's
  arguments come from its :class:`CLISubcommandDescriptor`; the route
  (method and URL) from the server's ``GET /api/v1/ext`` listing, so
  the command runs exactly what the server mounts. Positional
  arguments and ``--flags`` are sent as query parameters named after
  them.
* ``pyc plugin-api catalog [<entry-name>]`` -- the published
  plugin-api surface (``GET /api/v1/plugin-api/_meta/catalog``).

Every ``--help`` here is answered from local information only.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List, Optional, Sequence

from ccai.pychestrate.cli import exit_codes, renderer, suggestions, transport
from ccai.pychestrate.cli.argparsing import CliArgumentParser
from ccai.pychestrate.cli.context import CliContext, resolve_profile
from ccai.pychestrate.cli.exceptions import CliUsageError, NotFoundError
from ccai.pychestrate.cli.extensions.cli_subcommand import (
    CLISubcommandDescriptor,
    CLISubcommandExtension,
)
from ccai.pychestrate.cli.extensions.discovery import (
    find_descriptor,
    find_listed_route,
    find_subcommand_class,
    parse_ext_listing,
)
from ccai.pychestrate.cli.models import CliProfile, RestOperation, RestResponse


EXT_LIST_VERB: str = "list"
PLUGIN_API_CATALOG_VERB: str = "catalog"

EXT_HELP_TEXT: str = (
    "usage: pyc ext <verb> [args]\n"
    "\n"
    "Commands contributed by extensions (CLISubcommandExtension).\n"
    "\n"
    "verbs:\n"
    "  list                       List the extension routes the server mounts.\n"
    "  <ext-name> <verb> [args]   Run a verb of an installed extension; the route\n"
    "                             comes from the server's /api/v1/ext listing.\n"
    "\n"
    "see 'pyc ext <ext-name> --help' for an extension's verbs.\n"
)

_HELP_FLAGS = ("-h", "--help")


def _is_help_token(token: str) -> bool:
    """
        Whether ``token`` asks for help.

        :param token: One argument.

        :returns: Boolean.
    """
    rtnval = token in _HELP_FLAGS
    return rtnval


def _send(
        *,
        ctx: CliContext,
        profile: CliProfile,
        operation: RestOperation,
        path_params: Optional[Dict[str, str]] = None,
        query_params: Optional[Dict[str, str]] = None
    ) -> RestResponse:
    """
        Send one request with the invocation's opener seam.

        :param ctx: Invocation context.
        :param profile: Active profile.
        :param operation: Operation.
        :param path_params: Path parameters.
        :param query_params: Query parameters.

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


def _emit_catalog(*, ctx: CliContext, response: RestResponse) -> None:
    """
        Print the plugin-api catalog: as one table of entries (both
        kinds) for ``table`` / ``tsv`` / ``--quiet``, as the server's
        object otherwise.

        :param ctx: Invocation context.
        :param response: The catalog answer.

        :returns: None.
    """
    body = response.body
    output_format = renderer.effective_format(options=ctx.output, stream=ctx.stdout)
    is_catalog = isinstance(body, dict) and ("factory_protocols" in body or "resource_extensions" in body)
    tabular = output_format in (renderer.FORMAT_TABLE, renderer.FORMAT_TSV) or ctx.output.quiet is True
    if is_catalog is True and tabular is True:
        rows: List[Any] = list(body.get("factory_protocols", None) or [])
        rows.extend(body.get("resource_extensions", None) or [])
        ctx.emit_result(value=rows, identifier_fields=("name",))
        return
    ctx.emit_result(value=body, raw_text=response.raw_text, identifier_fields=("name",))
    return


# ---------------------------------------------------------------------------
# plugin-api catalog
# ---------------------------------------------------------------------------


def run_plugin_api_catalog(*, ctx: CliContext, args: Sequence[str]) -> int:
    """
        ``pyc plugin-api catalog [<entry-name>]``.

        :param ctx: Invocation context.
        :param args: Arguments after ``catalog``.

        :returns: Exit code.
    """
    command_parser = CliArgumentParser(
        prog="pyc plugin-api catalog",
        description=(
            "Read the published plugin-api surface: every factory protocol and\n"
            "resource extension a pack can implement. With an entry name, read that\n"
            "entry's metadata.\n\n"
            "GET /api/v1/plugin-api/_meta/catalog[/<entry-name>]"
        ),
        out_stream=ctx.stdout,
        err_stream=ctx.stderr,
    )
    command_parser.add_argument(
        "entry_name", nargs="?", default=None, metavar="<entry-name>",
        help="one catalog entry (for example CLISubcommandExtension)",
    )
    namespace = command_parser.parse_args(list(args))

    profile = resolve_profile(ctx=ctx)
    if namespace.entry_name is None:
        operation = RestOperation(
            operation_id="plugin_api_list_catalog",
            method="GET",
            path_template="/api/v1/plugin-api/_meta/catalog",
        )
        response = _send(ctx=ctx, profile=profile, operation=operation)
    else:
        operation = RestOperation(
            operation_id="plugin_api_get_protocol",
            method="GET",
            path_template="/api/v1/plugin-api/_meta/catalog/{name}",
            path_param_names=("name",),
            required_path_param_names=("name",),
        )
        response = _send(
            ctx=ctx, profile=profile, operation=operation, path_params={"name": namespace.entry_name},
        )
    _emit_catalog(ctx=ctx, response=response)
    rtnval = exit_codes.EXIT_OK
    return rtnval


# ---------------------------------------------------------------------------
# ext list
# ---------------------------------------------------------------------------


def run_ext_list(*, ctx: CliContext, args: Sequence[str]) -> int:
    """
        ``pyc ext list``.

        :param ctx: Invocation context.
        :param args: Arguments after ``list``.

        :returns: Exit code.
    """
    command_parser = CliArgumentParser(
        prog="pyc ext list",
        description=(
            "List every extension route the server mounts: ext_name, method,\n"
            "path_suffix, full_path and the handler class.\n\n"
            "GET /api/v1/plugin-api/_meta/mounts"
        ),
        out_stream=ctx.stdout,
        err_stream=ctx.stderr,
    )
    command_parser.parse_args(list(args))

    profile = resolve_profile(ctx=ctx)
    operation = RestOperation(
        operation_id="plugin_api_list_mounts",
        method="GET",
        path_template="/api/v1/plugin-api/_meta/mounts",
    )
    response = _send(ctx=ctx, profile=profile, operation=operation)
    ctx.emit_result(value=response.body, raw_text=response.raw_text, identifier_fields=("full_path",))
    rtnval = exit_codes.EXIT_OK
    return rtnval


# ---------------------------------------------------------------------------
# ext <ext-name> <verb>
# ---------------------------------------------------------------------------


def installed_extension_names() -> List[str]:
    """
        The ``ext_name`` of every :class:`CLISubcommandExtension`
        loaded in this process.

        :returns: Sorted names.
    """
    names: List[str] = []
    for subclass in CLISubcommandExtension.__subclasses__():
        name = getattr(subclass, "ext_name", "")
        if len(name) > 0:
            names.append(name)
    rtnval = sorted(set(names))
    return rtnval


def _extension_help(*, ext_name: str, descriptors: Sequence[CLISubcommandDescriptor]) -> str:
    """
        ``pyc ext <ext-name> --help``.

        :param ext_name: Extension.
        :param descriptors: Its verbs.

        :returns: Text.
    """
    lines = ["usage: pyc ext {} <verb> [args]".format(ext_name), "", "verbs:"]
    for descriptor in descriptors:
        lines.append("  {:<16} {}".format(descriptor.verb, descriptor.description))
    lines.append("")
    lines.append("see 'pyc ext {} <verb> --help' for a verb's arguments.".format(ext_name))
    rtnval = "\n".join(lines) + "\n"
    return rtnval


def build_ext_verb_parser(
        *,
        ctx: CliContext,
        ext_name: str,
        descriptor: CLISubcommandDescriptor
    ) -> CliArgumentParser:
    """
        The argument parser of one extension verb, built from its
        descriptor: positionals in declaration order, ``--flag VALUE``
        options (``--flag=value`` works too).

        :param ctx: Invocation context.
        :param ext_name: Extension.
        :param descriptor: Verb descriptor.

        :returns: Parser; its namespace carries ``positional_<name>``
                  and ``flag_<name>`` values.
    """
    command_parser = CliArgumentParser(
        prog="pyc ext {} {}".format(ext_name, descriptor.verb),
        description=(
            "{}\n\n"
            "Runs the /api/v1/ext/{}/{} route the server lists (operationId {});\n"
            "arguments are sent as query parameters.".format(
                descriptor.description, ext_name, descriptor.verb, descriptor.operation_id
            )
        ),
        out_stream=ctx.stdout,
        err_stream=ctx.stderr,
    )
    for name in descriptor.positional_arg_names:
        command_parser.add_argument(
            "positional_{}".format(name), metavar=name.upper(), help="sent as the {} parameter".format(name),
        )
    for name in descriptor.flag_arg_names:
        spellings = ["--{}".format(name)]
        kebab = "--{}".format(name.replace("_", "-"))
        if kebab not in spellings:
            spellings.insert(0, kebab)
        command_parser.add_argument(
            *spellings, dest="flag_{}".format(name), default=None, metavar="VALUE",
            help="sent as the {} parameter".format(name),
        )
    rtnval = command_parser
    return rtnval


def run_ext_invocation(*, ctx: CliContext, ext_name: str, args: Sequence[str]) -> int:
    """
        ``pyc ext <ext-name> <verb> [positional...] [--flag value...]``.

        :param ctx: Invocation context.
        :param ext_name: Extension.
        :param args: Arguments after the extension name.

        :returns: Exit code.
    """
    subcommand_class = find_subcommand_class(ext_name=ext_name)
    if subcommand_class is None:
        known = installed_extension_names()
        hint = suggestions.did_you_mean(word=ext_name, candidates=known)
        raise CliUsageError(
            "no extension is registered under '{}'{}; installed: {}. See 'pyc ext --help'.".format(
                ext_name, "; " + hint if len(hint) > 0 else "", ", ".join(known) or "(none)"
            )
        )
    descriptors = list(subcommand_class.declare_subcommands())
    verbs = [descriptor.verb for descriptor in descriptors]

    if len(args) > 0 and _is_help_token(args[0]):
        ctx.stdout.write(_extension_help(ext_name=ext_name, descriptors=descriptors))
        return exit_codes.EXIT_OK
    if len(args) == 0:
        raise CliUsageError(
            "'pyc ext {}' needs a verb: {} (see 'pyc ext {} --help')".format(
                ext_name, ", ".join(verbs), ext_name
            )
        )

    verb = args[0]
    descriptor = find_descriptor(subcommand_class=subcommand_class, verb=verb)
    if descriptor is None:
        hint = suggestions.did_you_mean(word=verb, candidates=verbs)
        raise CliUsageError(
            "extension '{}' does not declare verb '{}'{}; verbs: {}".format(
                ext_name, verb, "; " + hint if len(hint) > 0 else "", ", ".join(verbs)
            )
        )

    command_parser = build_ext_verb_parser(ctx=ctx, ext_name=ext_name, descriptor=descriptor)
    namespace = command_parser.parse_args(list(args[1:]))
    values = vars(namespace)

    query_params: Dict[str, str] = {}
    for name in descriptor.positional_arg_names:
        query_params[name] = values["positional_{}".format(name)]
    for name in descriptor.flag_arg_names:
        value = values.get("flag_{}".format(name), None)
        if value is not None:
            query_params[name] = value

    profile = resolve_profile(ctx=ctx)
    listing_operation = RestOperation(
        operation_id="plugin_api_list_ext",
        method="GET",
        path_template="/api/v1/ext",
    )
    listing = _send(ctx=ctx, profile=profile, operation=listing_operation)
    routes, dynamic_mount = parse_ext_listing(body=listing.body)
    route = find_listed_route(routes=routes, ext_name=ext_name, verb=verb)
    if route is None:
        raise NotFoundError(
            "the server at {} does not mount /api/v1/ext/{}/{} (its /api/v1/ext listing"
            " names {} extension route(s)); the '{}' extension is not installed there.".format(
                profile.server_url, ext_name, verb, len(routes), ext_name
            )
        )

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
    ctx.emit_result(value=response.body, raw_text=response.raw_text)
    rtnval = exit_codes.EXIT_OK
    return rtnval


def run_ext(*, ctx: CliContext, args: Sequence[str]) -> int:
    """
        Dispatch ``pyc ext ...``.

        :param ctx: Invocation context.
        :param args: Arguments after ``ext``.

        :returns: Exit code.
    """
    if len(args) > 0 and _is_help_token(args[0]):
        ctx.stdout.write(EXT_HELP_TEXT)
        return exit_codes.EXIT_OK
    if len(args) == 0:
        raise CliUsageError("'pyc ext' needs a verb: list, or <ext-name> <verb> (see 'pyc ext --help')")
    first = args[0]
    if first == EXT_LIST_VERB:
        rtnval = run_ext_list(ctx=ctx, args=args[1:])
        return rtnval
    if first.startswith("-"):
        raise CliUsageError("unknown option '{}' for 'pyc ext' (see 'pyc ext --help')".format(first))
    rtnval = run_ext_invocation(ctx=ctx, ext_name=first, args=args[1:])
    return rtnval


__all__ = [
    "EXT_HELP_TEXT",
    "EXT_LIST_VERB",
    "PLUGIN_API_CATALOG_VERB",
    "build_ext_verb_parser",
    "installed_extension_names",
    "run_ext",
    "run_ext_invocation",
    "run_ext_list",
    "run_plugin_api_catalog",
]
