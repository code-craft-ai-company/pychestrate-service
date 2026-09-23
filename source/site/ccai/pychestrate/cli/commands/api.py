"""
.. module:: cli.commands.api
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Commands generated from the server's OpenAPI document.

.. moduleauthor:: Code Craft AI LLC

Every operation in the server's ``/api/v1/_meta/openapi.json`` is a
command (see :mod:`cli.parser` for how nouns and verbs are named)::

    pyc <noun> <verb> [PATH_PARAM ...] [--QUERY_PARAM VALUE ...]
                      [--data JSON | --data @FILE | --data -]
                      [--set KEY=VALUE ...] [--wait]

* path parameters are positionals, in URL order;
* query parameters are ``--name value`` (``--per-page`` or
  ``--per_page``);
* a JSON body comes from ``--data`` and/or repeated ``--set`` (values
  are parsed as JSON when they can be -- ``--set count=3`` sends a
  number -- and dotted keys nest);
* ``--wait`` (on POST commands) waits for the ``run_id`` the response
  names and exits with the run's result (see :mod:`cli.commands.runs`).

The response body is printed as JSON on stdout. The document is cached
(:mod:`cli.openapi_cache`) and re-fetched when it is older than an
hour or does not know the command; when it cannot be fetched at all
the built-in :data:`builtin_operations.FALLBACK_OPENAPI_DOCUMENT`
keeps the everyday commands working.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ccai.pychestrate.cli import openapi_cache, parser, transport
from ccai.pychestrate.cli.argparsing import CliArgumentParser
from ccai.pychestrate.cli.builtin_operations import FALLBACK_OPENAPI_DOCUMENT
from ccai.pychestrate.cli.context import CliContext
from ccai.pychestrate.cli.exceptions import (
    CliUsageError,
    CommandTreeBuildError,
    OpenApiUnavailableError,
)
from ccai.pychestrate.cli.models import (
    CliProfile,
    CommandDescriptor,
    CommandTree,
    RestOperation,
    RestResponse,
)


OPENAPI_DOCUMENT_PATH: str = "/api/v1/_meta/openapi.json"

#: A cached document younger than this is used without fetching.
OPENAPI_CACHE_MAX_AGE_SECONDS: float = 3600.0

_BODY_METHODS = ("POST", "PUT", "PATCH")


# ---------------------------------------------------------------------------
# Loading the command tree
# ---------------------------------------------------------------------------


def build_default_openapi_fetcher(*, ctx: CliContext, profile: CliProfile):
    """
        Build the fetcher for ``/api/v1/_meta/openapi.json``.

        :param ctx: Invocation context.
        :param profile: Active profile.

        :returns: No-arg callable returning the document; raises when
                  the answer is not an OpenAPI document.
    """

    def _fetch() -> Dict:
        operation = RestOperation(
            operation_id="_meta_openapi",
            method="GET",
            path_template=OPENAPI_DOCUMENT_PATH,
        )
        response = transport.execute_request(
            profile=profile,
            operation=operation,
            path_params={},
            query_params={},
            body=None,
            idempotency_key=None,
            timeout_seconds=None,
            opener=ctx.request_opener,
        )
        if not isinstance(response.body, dict) or not isinstance(response.body.get("paths", None), dict):
            raise OpenApiUnavailableError(
                "{} did not return an OpenAPI document".format(OPENAPI_DOCUMENT_PATH)
            )
        rtnval = response.body
        return rtnval

    rtnval = _fetch
    return rtnval


def load_command_tree(
        *,
        ctx: CliContext,
        profile: CliProfile,
        force_refresh: bool = False
    ) -> Tuple[CommandTree, str]:
    """
        Load the command tree: a fresh cached document, else a fetched
        one (cached for next time), else a stale cached one, else the
        built-in fallback.

        :param ctx: Invocation context.
        :param profile: Active profile.
        :param force_refresh: Skip the fresh-cache shortcut.

        :returns: ``(tree, source)`` with source ``cache``, ``server``
                  or ``builtin``.
    """
    document: Optional[Dict] = None
    source = "server"
    if force_refresh is False and ctx.openapi_fetcher is None:
        document = openapi_cache.load_cached_if_fresh(
            server_url=profile.server_url, max_age_seconds=OPENAPI_CACHE_MAX_AGE_SECONDS
        )
        if document is not None:
            source = "cache"

    if document is None:
        fetcher = ctx.openapi_fetcher
        if fetcher is None:
            fetcher = build_default_openapi_fetcher(ctx=ctx, profile=profile)
        try:
            document = openapi_cache.load_or_fetch(
                server_url=profile.server_url, fetch_callable=fetcher
            )
        except OpenApiUnavailableError:
            document = FALLBACK_OPENAPI_DOCUMENT
            source = "builtin"

    try:
        tree = parser.build_command_tree(openapi_document=document)
    except CommandTreeBuildError:
        tree = parser.build_command_tree(openapi_document=FALLBACK_OPENAPI_DOCUMENT)
        source = "builtin"
    rtnval = (tree, source)
    return rtnval


def fallback_command_tree() -> CommandTree:
    """
        The command tree of the built-in fallback document.

        :returns: :class:`CommandTree`.
    """
    rtnval = parser.build_command_tree(openapi_document=FALLBACK_OPENAPI_DOCUMENT)
    return rtnval


# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------


def _describe(descriptor: CommandDescriptor) -> str:
    """
        Help description for one command.

        :param descriptor: Command.

        :returns: Text.
    """
    operation = descriptor.operation
    lines = []
    if len(operation.summary) > 0:
        lines.append(operation.summary)
        lines.append("")
    lines.append("{} {}  (operationId {})".format(
        operation.method, operation.path_template, operation.operation_id
    ))
    rtnval = "\n".join(lines)
    return rtnval


def build_command_parser(*, ctx: CliContext, descriptor: CommandDescriptor) -> CliArgumentParser:
    """
        The argument parser for one generated command.

        :param ctx: Invocation context.
        :param descriptor: Command.

        :returns: Parser whose namespace carries ``p0..`` (path
                  params), ``q0..`` (query params), ``data``, ``set``,
                  ``wait``, ``wait_timeout``, ``wait_interval``.
    """
    operation = descriptor.operation
    command_parser = CliArgumentParser(
        prog="pyc {} {}".format(descriptor.noun, descriptor.verb),
        description=_describe(descriptor),
        out_stream=ctx.stdout,
        err_stream=ctx.stderr,
    )
    for index, name in enumerate(operation.path_param_names):
        command_parser.add_argument("p{}".format(index), metavar=name, help="path parameter {}".format(name))
    for index, name in enumerate(operation.query_param_names):
        flags = ["--{}".format(name)]
        hyphenated = "--{}".format(name.replace("_", "-"))
        if hyphenated not in flags:
            flags.append(hyphenated)
        is_required = name in operation.required_query_param_names
        command_parser.add_argument(
            *flags, dest="q{}".format(index), default=None, metavar="VALUE",
            help="query parameter {}{}".format(name, " (the server requires it)" if is_required else ""),
        )
    if operation.has_request_body is True or operation.method in _BODY_METHODS:
        command_parser.add_argument(
            "--data", default=None, metavar="JSON",
            help="request body: JSON text, @FILE, or - for stdin",
        )
        command_parser.add_argument(
            "--set", action="append", default=[], metavar="KEY=VALUE",
            help="set one body field (repeatable; VALUE parsed as JSON when possible,"
                 " dotted keys nest)",
        )
    if operation.method == "POST":
        command_parser.add_argument(
            "--wait", action="store_true", default=False,
            help="wait for the run_id in the response to finish; exit 0 on success,"
                 " 10 on failure, 11 on timeout",
        )
        command_parser.add_argument(
            "--wait-timeout", type=float, default=3600.0, metavar="SECONDS",
            help="give up waiting after this long (default 3600)",
        )
        command_parser.add_argument(
            "--wait-interval", type=float, default=5.0, metavar="SECONDS",
            help="poll interval while waiting (default 5)",
        )
    rtnval = command_parser
    return rtnval


def _parse_value(raw: str) -> Any:
    """
        Parse a ``--set`` value: JSON when it parses, else the string.

        :param raw: Raw text.

        :returns: Parsed value.
    """
    try:
        rtnval = json.loads(raw)
    except ValueError:
        rtnval = raw
    return rtnval


def _read_data_argument(*, ctx: CliContext, data_arg: str) -> Any:
    """
        Resolve ``--data``: inline JSON, ``@file``, or ``-`` for stdin.

        :param ctx: Invocation context.
        :param data_arg: Raw ``--data`` value.

        :returns: Parsed JSON.
        :raises: CliUsageError
    """
    source = "--data"
    if data_arg == "-":
        text = ctx.stdin.read()
        source = "--data - (stdin)"
    elif data_arg.startswith("@"):
        file_path = data_arg[1:]
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError as xcpt:
            raise CliUsageError("cannot read {}: {}".format(file_path, xcpt.strerror or xcpt)) from None
        source = "--data @{}".format(file_path)
    else:
        text = data_arg
    try:
        rtnval = json.loads(text)
    except ValueError as xcpt:
        raise CliUsageError("{} is not valid JSON: {}".format(source, xcpt)) from None
    return rtnval


def build_request_body(*, ctx: CliContext, data_arg: Optional[str], set_args: Sequence[str]) -> Any:
    """
        Combine ``--data`` and ``--set`` into the request body.

        :param ctx: Invocation context.
        :param data_arg: ``--data`` value or ``None``.
        :param set_args: ``--set`` values.

        :returns: Body (``None`` when neither was given).
        :raises: CliUsageError
    """
    body: Any = None
    if data_arg is not None:
        body = _read_data_argument(ctx=ctx, data_arg=data_arg)
    if len(set_args) > 0:
        if body is None:
            body = {}
        if not isinstance(body, dict):
            raise CliUsageError("--set needs --data to be a JSON object (or no --data)")
        for assignment in set_args:
            key, separator, raw_value = assignment.partition("=")
            if separator != "=" or len(key.strip()) == 0:
                raise CliUsageError("--set expects KEY=VALUE, got {!r}".format(assignment))
            target = body
            parts = key.strip().split(".")
            for part in parts[:-1]:
                existing = target.get(part, None)
                if not isinstance(existing, dict):
                    existing = {}
                    target[part] = existing
                target = existing
            target[parts[-1]] = _parse_value(raw_value)
    rtnval = body
    return rtnval


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def emit_response(*, ctx: CliContext, response: RestResponse) -> None:
    """
        Print a response body: JSON pretty-printed, text verbatim,
        nothing for an empty body.

        :param ctx: Invocation context.
        :param response: The response.

        :returns: None.
    """
    body = response.body
    if body is None:
        return
    if isinstance(body, (dict, list)):
        ctx.stdout.write(json.dumps(body, indent=2))
        ctx.stdout.write("\n")
        return
    text = str(body)
    ctx.stdout.write(text)
    if not text.endswith("\n"):
        ctx.stdout.write("\n")
    return


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def run_api_command(
        *,
        ctx: CliContext,
        profile: CliProfile,
        descriptor: CommandDescriptor,
        args: Sequence[str]
    ) -> int:
    """
        Parse the arguments of one generated command, send the request,
        and print the response.

        :param ctx: Invocation context.
        :param profile: Active profile.
        :param descriptor: Command.
        :param args: Arguments after ``pyc <noun> <verb>``.

        :returns: Exit code (0; errors raise).
    """
    from ccai.pychestrate.cli import exit_codes  # noqa: E402

    operation = descriptor.operation
    command_parser = build_command_parser(ctx=ctx, descriptor=descriptor)
    namespace = command_parser.parse_args(list(args))
    values = vars(namespace)

    path_params: Dict[str, str] = {}
    for index, name in enumerate(operation.path_param_names):
        path_params[name] = values["p{}".format(index)]
    query_params: Dict[str, str] = {}
    for index, name in enumerate(operation.query_param_names):
        value = values.get("q{}".format(index), None)
        if value is not None:
            query_params[name] = value

    body = None
    if "data" in values:
        body = build_request_body(ctx=ctx, data_arg=values.get("data"), set_args=values.get("set") or [])
        if body is None and operation.has_request_body is True:
            body = {}

    response = transport.execute_request(
        profile=profile,
        operation=operation,
        path_params=path_params,
        query_params=query_params,
        body=body,
        idempotency_key=None,
        timeout_seconds=None,
        opener=ctx.request_opener,
    )
    emit_response(ctx=ctx, response=response)

    if values.get("wait", False) is True:
        from ccai.pychestrate.cli.commands.runs import wait_for_run  # noqa: E402
        run_id = None
        if isinstance(response.body, dict):
            run_id = response.body.get("run_id", None)
        if run_id is None or len(str(run_id)) == 0:
            raise CliUsageError(
                "--wait: the response carries no run_id, so there is nothing to wait for"
            )
        rtnval = wait_for_run(
            ctx=ctx, profile=profile, run_id=str(run_id),
            timeout_seconds=values.get("wait_timeout", 3600.0),
            interval_seconds=values.get("wait_interval", 5.0),
        )
        return rtnval

    rtnval = exit_codes.EXIT_OK
    return rtnval


def render_noun_help(*, tree: CommandTree, noun: str) -> str:
    """
        ``pyc <noun> --help`` for a generated noun.

        :param tree: Command tree.
        :param noun: Canonical noun.

        :returns: Help text.
    """
    lines = ["usage: pyc {} <verb> [args]".format(noun), "", "verbs:"]
    for descriptor in parser.verbs_for(tree=tree, noun=noun):
        summary = descriptor.operation.summary or descriptor.operation.operation_id
        lines.append("  {:<32} {}".format(descriptor.verb, summary))
    lines.append("")
    lines.append("see 'pyc {} <verb> --help' for a verb's arguments.".format(noun))
    rtnval = "\n".join(lines) + "\n"
    return rtnval


def render_command_list(*, tree: CommandTree, source: str) -> str:
    """
        ``pyc commands``: every generated command, grouped by noun.

        :param tree: Command tree.
        :param source: Where the document came from.

        :returns: Text.
    """
    lines: List[str] = []
    if source == "builtin":
        lines.append(
            "note: the server's OpenAPI document is unavailable; showing pyc's built-in commands."
        )
    current_noun = None
    for (noun, verb), descriptor in sorted(tree.commands.items()):
        if noun != current_noun:
            if current_noun is not None:
                lines.append("")
            lines.append("{}:".format(noun))
            current_noun = noun
        operation = descriptor.operation
        lines.append("  {:<34} {:<6} {}".format(verb, operation.method, operation.path_template))
    rtnval = "\n".join(lines) + "\n"
    return rtnval


__all__ = [
    "OPENAPI_CACHE_MAX_AGE_SECONDS",
    "OPENAPI_DOCUMENT_PATH",
    "build_command_parser",
    "build_default_openapi_fetcher",
    "build_request_body",
    "emit_response",
    "fallback_command_tree",
    "load_command_tree",
    "render_command_list",
    "render_noun_help",
    "run_api_command",
]
