"""
.. module:: cli.commands.api
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Commands generated from the server's OpenAPI document.

.. moduleauthor:: Code Craft AI LLC

Every operation in the server's ``/api/v1/_meta/openapi.json`` is a
command (see :mod:`cli.parser` and :mod:`cli.command_names` for how
nouns and verbs are named)::

    pyc <noun> <verb> [PATH_PARAM ...] [--query-param VALUE ...]
                      [--data JSON | --data @FILE | --data - | --from-file PATH]
                      [--set FIELD=VALUE ...] [--wait]

* path parameters are positionals, in URL order;
* query parameters are ``--kebab-case`` flags (``--per-page``; the
  REST spelling ``--per_page`` is accepted too), typed and checked
  against the document's allowed values; ``--help`` shows each one's
  description and server default;
* a JSON body comes from ``--data`` or ``--from-file`` and/or repeated
  ``--set`` (values are parsed as JSON when they can be --
  ``--set count=3`` sends a number -- and dotted keys nest);
  ``--help`` lists the body's fields;
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


import argparse
import json

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ccai.pychestrate.cli import openapi_cache, parser, suggestions, transport
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
    OperationParameter,
    RestOperation,
    RestResponse,
)


OPENAPI_DOCUMENT_PATH: str = "/api/v1/_meta/openapi.json"

#: A cached document younger than this is used without fetching.
OPENAPI_CACHE_MAX_AGE_SECONDS: float = 3600.0

_BODY_METHODS = ("POST", "PUT", "PATCH")

#: Most lines of an operation's description shown in ``--help``.
_HELP_DESCRIPTION_LINE_LIMIT: int = 12

#: Accepted spellings of a boolean query value.
_TRUE_WORDS = ("true", "yes", "on", "1")
_FALSE_WORDS = ("false", "no", "off", "0")


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
        profile: Optional[CliProfile],
        force_refresh: bool = False,
        offline: bool = False
    ) -> Tuple[CommandTree, str]:
    """
        Load the command tree: a fresh cached document, else a fetched
        one (cached for next time), else a stale cached one, else the
        built-in fallback.

        With ``offline`` (``--help``), nothing is fetched: the cached
        document is used whatever its age, else the built-in fallback.

        :param ctx: Invocation context.
        :param profile: Active profile (``None`` when nothing is
                        configured; only valid with ``offline``).
        :param force_refresh: Skip the fresh-cache shortcut.
        :param offline: Never touch the network.

        :returns: ``(tree, source)`` with source ``cache``, ``server``
                  or ``builtin``.
    """
    document: Optional[Dict] = None
    source = "server"
    if offline is True:
        source = "builtin"
        if profile is not None:
            document = openapi_cache.load_cached_any_age(
                server_url=profile.server_url, environ=ctx.environ
            )
            if document is not None:
                source = "cache"
        if document is None:
            document = FALLBACK_OPENAPI_DOCUMENT
    elif force_refresh is False and ctx.openapi_fetcher is None:
        document = openapi_cache.load_cached_if_fresh(
            server_url=profile.server_url, max_age_seconds=OPENAPI_CACHE_MAX_AGE_SECONDS,
            environ=ctx.environ,
        )
        if document is not None:
            source = "cache"

    if document is None:
        fetcher = ctx.openapi_fetcher
        if fetcher is None:
            fetcher = build_default_openapi_fetcher(ctx=ctx, profile=profile)
        try:
            document = openapi_cache.load_or_fetch(
                server_url=profile.server_url, fetch_callable=fetcher, environ=ctx.environ
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
        Help description for one command: the summary, the REST
        endpoint, the operation's own description, and the command's
        other spellings.

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
    if len(operation.description) > 0:
        description_lines = [line.rstrip() for line in operation.description.strip().splitlines()]
        if len(description_lines) > _HELP_DESCRIPTION_LINE_LIMIT:
            description_lines = description_lines[:_HELP_DESCRIPTION_LINE_LIMIT] + ["..."]
        lines.append("")
        lines.extend(description_lines)
    if len(descriptor.aliases) > 0:
        lines.append("")
        spelled = ", ".join("pyc {} {}".format(noun, verb) for noun, verb in descriptor.aliases)
        lines.append("also: {}".format(spelled))
    rtnval = "\n".join(lines)
    return rtnval


def _body_epilog(*, operation: RestOperation) -> Optional[str]:
    """
        The ``--help`` epilog listing the request body's fields.

        :param operation: Operation.

        :returns: Text, or ``None`` when the body has no known fields.
    """
    if len(operation.body_fields) == 0:
        return None
    width = max(len(body_field.name) for body_field in operation.body_fields)
    width = min(max(width, 12), 28)
    lines = ["request body fields (--set FIELD=VALUE, or --data / --from-file):"]
    for body_field in operation.body_fields:
        facts = []
        if len(body_field.value_type) > 0:
            facts.append(body_field.value_type)
        if body_field.required is True:
            facts.append("required")
        text = ", ".join(facts)
        if len(body_field.description) > 0:
            text = "{}{}{}".format(text, " -- " if len(text) > 0 else "", body_field.description)
        lines.append("  {:<{width}}  {}".format(body_field.name, text, width=width))
    rtnval = "\n".join(lines)
    return rtnval


def flag_for(name: str) -> str:
    """
        The command-line flag of a query parameter: ``per_page`` ->
        ``--per-page``.

        :param name: Parameter name.

        :returns: Flag.
    """
    rtnval = "--{}".format(name.replace("_", "-"))
    return rtnval


def _boolean_text(raw: str) -> str:
    """
        argparse ``type`` for boolean query values.

        :param raw: Typed value.

        :returns: ``"true"`` or ``"false"``.
        :raises: argparse.ArgumentTypeError
    """
    lowered = str(raw).strip().lower()
    if lowered in _TRUE_WORDS:
        return "true"
    if lowered in _FALSE_WORDS:
        return "false"
    raise argparse.ArgumentTypeError("expected true or false, got {!r}".format(raw))


class _ChoiceNormalizer:
    """
        argparse ``type`` for an enumerated string parameter: a value
        that matches an allowed value except for case is spelled the
        way the document spells it (the server compares without
        case); anything else is left for argparse's ``choices`` check
        to reject with the list of allowed values.
    """

    def __init__(self, choices: Sequence[str]) -> None:
        self._by_lower: Dict[str, str] = {}
        for choice in choices:
            self._by_lower[str(choice).lower()] = str(choice)
        return

    def __call__(self, raw: str) -> str:
        rtnval = self._by_lower.get(str(raw).lower(), str(raw))
        return rtnval


def _sentence(text: str) -> str:
    """
        ``text`` ending with a period.

        :param text: Text.

        :returns: Text.
    """
    stripped = text.strip()
    if len(stripped) > 0 and stripped[-1] not in ".!?":
        stripped = stripped + "."
    rtnval = stripped
    return rtnval


def _query_argument_options(*, parameter: OperationParameter) -> Dict[str, Any]:
    """
        The argparse options (type, choices, metavar, help) of one
        query parameter.

        :param parameter: Parameter.

        :returns: Keyword arguments for ``add_argument``.
    """
    options: Dict[str, Any] = {"default": None}
    help_parts: List[str] = []
    if len(parameter.description) > 0:
        help_parts.append(_sentence(parameter.description))
    if parameter.value_type == "integer":
        options["type"] = int
        options["metavar"] = "N"
    elif parameter.value_type == "number":
        options["type"] = float
        options["metavar"] = "NUMBER"
    elif parameter.value_type == "boolean":
        options["type"] = _boolean_text
        options["metavar"] = "{true,false}"
    else:
        options["metavar"] = "VALUE"
    if len(parameter.choices) > 0 and parameter.value_type not in ("boolean", "integer", "number"):
        options["type"] = _ChoiceNormalizer(parameter.choices)
        options["choices"] = list(parameter.choices)
        options["metavar"] = "{" + ",".join(parameter.choices) + "}"
    if parameter.value_type == "array":
        options["action"] = "append"
        help_parts.append("Repeatable.")
    if parameter.required is True:
        options["required"] = True
        help_parts.append("Required.")
    if parameter.default is not None:
        help_parts.append("Server default: {}.".format(parameter.default))
    if len(help_parts) == 0:
        help_parts.append("Query parameter {}.".format(parameter.name))
    options["help"] = " ".join(help_parts).replace("%", "%%")
    rtnval = options
    return rtnval


def build_command_parser(*, ctx: CliContext, descriptor: CommandDescriptor) -> CliArgumentParser:
    """
        The argument parser for one generated command.

        :param ctx: Invocation context.
        :param descriptor: Command.

        :returns: Parser whose namespace carries ``p0..`` (path
                  params), ``q0..`` (query params), ``data``,
                  ``from_file``, ``set``, ``wait``, ``wait_timeout``,
                  ``wait_interval``.
    """
    operation = descriptor.operation
    command_parser = CliArgumentParser(
        prog="pyc {} {}".format(descriptor.noun, descriptor.verb),
        description=_describe(descriptor),
        epilog=_body_epilog(operation=operation),
        out_stream=ctx.stdout,
        err_stream=ctx.stderr,
    )
    for index, name in enumerate(operation.path_param_names):
        parameter = operation.find_parameter(name)
        help_text = "path parameter {}".format(name)
        if parameter is not None and len(parameter.description) > 0:
            help_text = parameter.description
        command_parser.add_argument(
            "p{}".format(index), metavar=name.upper(), help=help_text.replace("%", "%%"),
        )
    for index, name in enumerate(operation.query_param_names):
        parameter = operation.find_parameter(name)
        if parameter is None:
            parameter = OperationParameter(name=name, location="query")
        options = _query_argument_options(parameter=parameter)
        flag = flag_for(name)
        command_parser.add_argument(flag, dest="q{}".format(index), **options)
        rest_spelling = "--{}".format(name)
        if rest_spelling != flag:
            # The REST spelling (--per_page) keeps working, unlisted.
            hidden_options = dict(options)
            hidden_options["help"] = argparse.SUPPRESS
            hidden_options.pop("required", None)
            command_parser.add_argument(rest_spelling, dest="q{}".format(index), **hidden_options)
    if operation.has_request_body is True or operation.method in _BODY_METHODS:
        body_group = command_parser.add_argument_group("request body")
        source_group = body_group.add_mutually_exclusive_group()
        source_group.add_argument(
            "--data", default=None, metavar="JSON",
            help="the body as JSON text, @FILE, or - for standard input",
        )
        source_group.add_argument(
            "--from-file", dest="from_file", default=None, metavar="PATH",
            help="read the JSON body from PATH (- for standard input)",
        )
        body_group.add_argument(
            "--set", action="append", default=[], metavar="FIELD=VALUE",
            help="set one body field (repeatable; VALUE is parsed as JSON when it can be,"
                 " dotted fields nest: --set labels.env=ci)",
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


def _read_file_text(*, file_path: str, option: str) -> str:
    """
        Read a body file.

        :param file_path: Path.
        :param option: The option that named it (for the error).

        :returns: Text.
        :raises: CliUsageError
    """
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            rtnval = fh.read()
    except OSError as xcpt:
        raise CliUsageError(
            "{}: cannot read {}: {}".format(option, file_path, xcpt.strerror or xcpt)
        ) from None
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
        text = _read_file_text(file_path=file_path, option="--data")
        source = "--data @{}".format(file_path)
    else:
        text = data_arg
    try:
        rtnval = json.loads(text)
    except ValueError as xcpt:
        raise CliUsageError("{} is not valid JSON: {}".format(source, xcpt)) from None
    return rtnval


def _read_from_file_argument(*, ctx: CliContext, file_arg: str) -> Any:
    """
        Resolve ``--from-file PATH`` (``-`` for standard input).

        :param ctx: Invocation context.
        :param file_arg: Raw value.

        :returns: Parsed JSON.
        :raises: CliUsageError
    """
    if file_arg == "-":
        text = ctx.stdin.read()
        source = "--from-file - (stdin)"
    else:
        text = _read_file_text(file_path=file_arg, option="--from-file")
        source = "--from-file {}".format(file_arg)
    try:
        rtnval = json.loads(text)
    except ValueError as xcpt:
        raise CliUsageError("{} is not valid JSON: {}".format(source, xcpt)) from None
    return rtnval


def build_request_body(
        *,
        ctx: CliContext,
        data_arg: Optional[str],
        set_args: Sequence[str],
        from_file_arg: Optional[str] = None
    ) -> Any:
    """
        Combine ``--data`` / ``--from-file`` and ``--set`` into the
        request body.

        :param ctx: Invocation context.
        :param data_arg: ``--data`` value or ``None``.
        :param set_args: ``--set`` values.
        :param from_file_arg: ``--from-file`` value or ``None``.

        :returns: Body (``None`` when nothing was given).
        :raises: CliUsageError
    """
    body: Any = None
    if data_arg is not None and from_file_arg is not None:
        raise CliUsageError("give the body with --data or --from-file, not both")
    if data_arg is not None:
        body = _read_data_argument(ctx=ctx, data_arg=data_arg)
    if from_file_arg is not None:
        body = _read_from_file_argument(ctx=ctx, file_arg=from_file_arg)
    if len(set_args) > 0:
        if body is None:
            body = {}
        if not isinstance(body, dict):
            raise CliUsageError("--set needs the --data / --from-file body to be a JSON object")
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


def _note_unknown_body_fields(*, ctx: CliContext, descriptor: CommandDescriptor, set_args: Sequence[str]) -> None:
    """
        Warn (on stderr) about ``--set`` fields the body schema does
        not declare -- most often a typo. The request is still sent:
        the server has the last word.

        :param ctx: Invocation context.
        :param descriptor: Command.
        :param set_args: ``--set`` values.

        :returns: None.
    """
    known = [body_field.name for body_field in descriptor.operation.body_fields]
    if len(known) == 0:
        return
    for assignment in set_args:
        key = assignment.partition("=")[0].strip()
        top_level = key.split(".", 1)[0]
        if len(top_level) == 0 or top_level in known:
            continue
        hint = suggestions.did_you_mean(word=top_level, candidates=known)
        ctx.note(
            "unknown-field-{}".format(top_level),
            "note: '{}' is not a field of the {} request body{} (fields: {})".format(
                top_level, descriptor.operation.operation_id,
                "; " + hint if len(hint) > 0 else "", ", ".join(known),
            ),
        )
    return


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
        set_args = values.get("set") or []
        body = build_request_body(
            ctx=ctx, data_arg=values.get("data"), set_args=set_args,
            from_file_arg=values.get("from_file", None),
        )
        _note_unknown_body_fields(ctx=ctx, descriptor=descriptor, set_args=set_args)
        if body is None and operation.has_request_body is True:
            required_fields = [f.name for f in operation.body_fields if f.required is True]
            if operation.body_required is True and len(required_fields) > 0:
                raise CliUsageError(
                    "'pyc {} {}' needs a request body with {}: pass --set FIELD=VALUE for each,"
                    " or the whole body with --data JSON or --from-file PATH"
                    " (see 'pyc {} {} --help')".format(
                        descriptor.noun, descriptor.verb, ", ".join(required_fields),
                        descriptor.noun, descriptor.verb,
                    )
                )
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
    lines = ["usage: pyc {} <verb> [args]".format(noun), ""]
    descriptors = parser.verbs_for(tree=tree, noun=noun)
    if len(descriptors) > 0:
        lines.append("verbs:")
        for descriptor in descriptors:
            summary = descriptor.operation.summary or descriptor.operation.operation_id
            lines.append("  {:<24} {}".format(descriptor.verb, summary))
        lines.append("")
        lines.append("see 'pyc {} <verb> --help' for a verb's arguments.".format(noun))
    else:
        # An alias-only noun (the tag of commands that were renamed).
        lines.append("'{}' commands have their own nouns now:".format(noun))
        for alias_verb, descriptor in parser.alias_verbs_for(tree=tree, noun=noun):
            lines.append("  {:<32} -> pyc {} {}".format(alias_verb, descriptor.noun, descriptor.verb))
        lines.append("")
        lines.append("the old spellings keep working.")
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
