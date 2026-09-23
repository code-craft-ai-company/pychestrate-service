"""
.. module:: cli.entry
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``pyc`` entry-point dispatcher.

.. moduleauthor:: Code Craft AI LLC

The entry point handles four classes of invocation:

1. Help and the version banner. ``--help`` / ``-h`` anywhere on the
   line (or ``pyc help [<noun> [<verb>]]``) prints help for the
   command it follows and never touches the network: the API
   commands' help comes from the cached OpenAPI document (or pyc's
   built-in commands when nothing is cached).
2. Built-in commands: ``login``, ``logout``, ``whoami``, ``config``,
   ``commands``, ``version``, ``runs wait``, ``plugin-api catalog``,
   ``ext``.
3. API commands generated from the server's OpenAPI document
   (``pyc projects list``, ``pyc projects get demo`` ...; see
   :mod:`cli.commands.api`).
4. Failures, each reported as one ``error: ...`` line (no traceback)
   with a documented exit code (see :mod:`cli.exit_codes`). Unknown
   commands, verbs and options exit 2 and name the closest known
   spellings.

Global options (``--profile``, ``--server-url``, ``--timeout``) may
appear anywhere on the command line, before a ``--`` that ends the
options.

The console script is :func:`console_main`
(``pyc = "ccai.pychestrate.cli.entry:console_main"``).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import sys
import traceback

from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ccai.pychestrate.cli import (
    exit_codes,
    parser,
    renderer,
    suggestions,
    version,
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
from ccai.pychestrate.cli.models import CliProfile, CommandTree


CLI_PROG: str = "pyc"
#: The pyc version (defined once, in :mod:`cli.version`).
CLI_VERSION: str = version.PYC_VERSION

PYC_DEBUG_ENV_VAR: str = "PYC_DEBUG"

HELP_FLAGS: Tuple[str, ...] = ("-h", "--help")
HELP_COMMAND: str = "help"
VERSION_FLAG: str = "--version"
END_OF_OPTIONS: str = "--"

#: pyc's own commands, as listed when a command is unknown.
_BUILTIN_COMMANDS: Tuple[str, ...] = (
    "'login'",
    "'logout'",
    "'whoami'",
    "'config ...'",
    "'commands'",
    "'help'",
    "'version'",
    "'project list'",
    "'runs wait <run_id>'",
    "'plugin-api catalog [<entry-name>]'",
    "'ext list'",
    "'ext <ext-name> <verb> [args]'",
)

#: Words that are pyc commands whatever the server offers.
_BUILTIN_NOUNS: Tuple[str, ...] = (
    "login", "logout", "whoami", "config", "commands", "ext", "help", "version",
)

#: Built-in verbs that live under an API noun.
_BUILTIN_VERBS: Dict[Tuple[str, str], str] = {
    ("runs", "wait"): "Wait for a run: exit 0 on success, 10 on failure, 11 on timeout.",
    ("plugin-api", "catalog"): "List the published plugin-api surface, or read one entry.",
}

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
    "  version                      Versions of pyc, the service and its REST API",
    "                               ('pyc --version' prints pyc's alone, offline).",
    "",
    "API commands:",
    "  <noun> <verb> [args]         e.g. 'pyc projects list', 'pyc projects get demo'.",
    "                               Bodies: --data JSON|@FILE|-, --from-file PATH, --set FIELD=VALUE.",
    "  commands [--refresh]         List every API command the server offers.",
    "  project list                 List projects (same as 'projects list').",
    "                               List commands take --all (every page) and --limit N.",
    "  runs wait <run_id>           Wait for a run: exit 0 on success, 10 on failure.",
    "                               POST commands take --wait to do this for their run.",
    "",
    "extensions:",
    "  plugin-api catalog           List the published plugin-api surface.",
    "  plugin-api catalog <n>       Read a single catalog entry by name.",
    "  ext list                     List the extension routes the server mounts.",
    "  ext <name> <verb> [args]     Run a verb of an installed extension.",
    "",
    "help:",
    "  pyc help [<noun> [<verb>]]   Same as 'pyc <noun> <verb> --help'. Help never",
    "                               contacts the server: API commands are described from",
    "                               the command list cached by the last command.",
    "",
    "global options (anywhere on the line):",
    "  --profile NAME               Credentials profile (PYC_PROFILE; default 'default').",
    "  --server-url URL             Server root URL (PYC_SERVER_URL); overrides the profile.",
    "  --timeout SECONDS            Per-request timeout (default 30).",
    "  -o, --output FORMAT          table, json, yaml, tsv or raw (the server's answer as",
    "                               sent). Default: table on a terminal, json otherwise;",
    "                               lists print as arrays.",
    "  --fields A,B,C               Keep these fields, in this order (a.b reaches into objects).",
    "  -q, --quiet                  Print only each item's identifier, one per line.",
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
# Global options
# ---------------------------------------------------------------------------


#: Global options taking a value: spelling -> key in the parsed dict.
_GLOBAL_OPTIONS_WITH_VALUE: Dict[str, str] = {
    "--profile": "profile",
    "--server-url": "server_url",
    "--timeout": "timeout",
    "--output": "output",
    "-o": "output",
    "--fields": "fields",
}

#: Global flags: spelling -> key.
_GLOBAL_FLAGS: Dict[str, str] = {
    "--quiet": "quiet",
    "-q": "quiet",
}

#: Every global option, for "did you mean" on an unknown leading one.
_GLOBAL_OPTION_SPELLINGS: Tuple[str, ...] = (
    tuple(_GLOBAL_OPTIONS_WITH_VALUE.keys()) + tuple(_GLOBAL_FLAGS.keys()) + (VERSION_FLAG,) + HELP_FLAGS
)


def _match_global_option(*, token: str, following: Optional[str]) -> Tuple[Optional[str], Optional[str], int]:
    """
        Recognize one global option token.

        :param token: The token.
        :param following: The next token, or ``None``.

        :returns: ``(key, value, tokens_consumed)``; ``key`` is
                  ``None`` when ``token`` is not a global option.
        :raises: CliUsageError for an option missing its value.
    """
    if token in _GLOBAL_FLAGS:
        rtnval = (_GLOBAL_FLAGS[token], "true", 1)
        return rtnval
    for option, key in _GLOBAL_OPTIONS_WITH_VALUE.items():
        if token == option:
            if following is None or (following.startswith("-") and following != "-"):
                raise CliUsageError("{} needs a value".format(option))
            rtnval = (key, following, 2)
            return rtnval
        if token.startswith(option + "="):
            rtnval = (key, token.split("=", 1)[1], 1)
            return rtnval
        if option == "-o" and token.startswith("-o") and len(token) > 2 and not token.startswith("--"):
            # -ojson
            rtnval = (key, token[2:], 1)
            return rtnval
    rtnval = (None, None, 0)
    return rtnval


def _split_global_args(*, argv: Sequence[str]) -> Tuple[Dict, List[str]]:
    """
        Pull the global options (``--profile``, ``--server-url``,
        ``--timeout``, ``-o/--output``, ``--fields`` -- as
        ``--opt value`` or ``--opt=value`` -- and ``-q/--quiet``) out
        of argv wherever they appear before ``--``. A leading ``--`` is
        dropped; a later one and everything after it are passed through
        untouched.

        :param argv: Tokens after ``pyc``.

        :returns: Tuple of (parsed_globals_dict, remainder_list).
        :raises: CliUsageError for a missing or invalid value.
    """
    parsed: Dict = {
        "profile": None, "server_url": None, "timeout": None,
        "output": None, "fields": None, "quiet": False,
    }
    remainder: List[str] = []
    tokens = list(argv)
    if len(tokens) > 0 and tokens[0] == END_OF_OPTIONS:
        tokens = tokens[1:]
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == END_OF_OPTIONS:
            remainder.extend(tokens[index:])
            break
        following = tokens[index + 1] if index + 1 < len(tokens) else None
        key, value, consumed = _match_global_option(token=token, following=following)
        if key is None:
            remainder.append(token)
            index = index + 1
            continue
        index = index + consumed
        if key == "quiet":
            parsed["quiet"] = True
        else:
            parsed[key] = value

    if parsed["output"] is not None:
        parsed["output"] = renderer.parse_output_format(parsed["output"])
    if parsed["fields"] is not None:
        parsed["fields"] = renderer.parse_fields(parsed["fields"])

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


def _split_help_request(*, tokens: Sequence[str]) -> Tuple[bool, List[str]]:
    """
        Find ``-h`` / ``--help`` before ``--`` and take it out.

        :param tokens: Remaining tokens.

        :returns: ``(help_requested, tokens_without_help_flags)``.
    """
    help_requested = False
    kept: List[str] = []
    after_end = False
    for token in tokens:
        if after_end is False and token == END_OF_OPTIONS:
            after_end = True
        if after_end is False and token in HELP_FLAGS:
            help_requested = True
            continue
        kept.append(token)
    rtnval = (help_requested, kept)
    return rtnval


def _args_after_first_word(*, remainder: Sequence[str]) -> List[str]:
    """
        The tokens after the command word, in their original order
        (help flags included, so the command's own parser answers
        them). A help flag given before the command word is moved
        after it: ``pyc --help login`` is ``pyc login --help``.

        :param remainder: Argv without global options.

        :returns: Arguments of the command.
    """
    leading_help = False
    for index, token in enumerate(remainder):
        if token in HELP_FLAGS:
            leading_help = True
            continue
        args = list(remainder[index + 1:])
        if leading_help is True:
            args.append("--help")
        return args
    return []


def _leading_words(tokens: Sequence[str], count: int) -> List[str]:
    """
        The first ``count`` tokens, stopping at the first option.

        :param tokens: Tokens.
        :param count: Most words wanted.

        :returns: Words.
    """
    words: List[str] = []
    for token in tokens:
        if len(words) >= count or token.startswith("-"):
            break
        words.append(token)
    rtnval = words
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


def _end_sentence(text: str) -> str:
    """
        ``text`` ending with sentence punctuation (a trailing
        "did you mean ...?" keeps its question mark).

        :param text: Text.

        :returns: Text.
    """
    if text.endswith(("?", ".", "!")):
        return text
    rtnval = text + "."
    return rtnval


def _unknown_command_error(
        *,
        noun: str,
        verb: Optional[str],
        known_nouns: Sequence[str],
        detail: Optional[str] = None
    ) -> CliUsageError:
    """
        Build the usage error for an unknown command: the closest
        known nouns, pyc's own commands, and where the API commands
        are listed.

        :param noun: First word.
        :param verb: Second word or ``None``.
        :param known_nouns: Every noun pyc knows right now.
        :param detail: Extra explanation line.

        :returns: :class:`CliUsageError`.
    """
    shown = noun if verb is None else "{} {}".format(noun, verb)
    first_line = "'{}' is not a known command".format(shown)
    hint = suggestions.did_you_mean(word=noun, candidates=known_nouns)
    if len(hint) > 0:
        first_line = "{}; {}".format(first_line, hint)
    lines = [_end_sentence(first_line)]
    if detail is not None:
        lines.append(detail)
    lines.append("built-in: {}".format(", ".join(_BUILTIN_COMMANDS)))
    lines.append("run 'pyc commands' for the API commands the server offers.")
    rtnval = CliUsageError("\n".join(lines))
    return rtnval


def _unknown_verb_error(*, noun: str, verb: str, verbs: Sequence[str]) -> CliUsageError:
    """
        Build the usage error for an unknown verb of a known noun.

        :param noun: Noun (as the tree spells it).
        :param verb: Verb as typed.
        :param verbs: The noun's verbs.

        :returns: :class:`CliUsageError`.
    """
    first_line = "'{}' has no verb '{}'".format(noun, verb)
    hint = suggestions.did_you_mean(word=verb, candidates=verbs)
    if len(hint) > 0:
        first_line = "{}; {}".format(first_line, hint)
    message = "{} verbs: {} (see 'pyc {} --help')".format(
        _end_sentence(first_line), ", ".join(sorted(set(verbs))), noun
    )
    rtnval = CliUsageError(message)
    return rtnval


# ---------------------------------------------------------------------------
# The command tree
# ---------------------------------------------------------------------------


def _offline_tree(*, ctx: CliContext) -> Tuple[CommandTree, str]:
    """
        The command tree help is written from: the cached document of
        the configured server (whatever its age), else the built-in
        commands. Never touches the network.

        :param ctx: Invocation context.

        :returns: ``(tree, source)``.
    """
    from ccai.pychestrate.cli.commands import api as api_commands  # noqa: E402

    profile: Optional[CliProfile] = None
    try:
        profile = resolve_profile(ctx=ctx, quiet=True)
    except (NotConfiguredError, CredentialsFileNotFoundError, ProfileNotFoundError,
            CredentialsFilePermissionError, CredentialsFileInvalidError):
        profile = None
    rtnval = api_commands.load_command_tree(ctx=ctx, profile=profile, offline=True)
    return rtnval


def _known_nouns(*, tree: CommandTree) -> List[str]:
    """
        Every noun pyc knows: its own commands, the builtin verbs'
        nouns, and the tree's canonical and alias nouns.

        :param tree: Command tree.

        :returns: Nouns.
    """
    nouns = list(_BUILTIN_NOUNS)
    nouns.extend(noun for (noun, _verb) in _BUILTIN_VERBS.keys())
    nouns.extend(parser.canonical_nouns(tree=tree))
    nouns.extend(parser.alias_nouns(tree=tree))
    rtnval = sorted(set(nouns))
    return rtnval


def _builtin_verb_keys_for(noun: str) -> List[Tuple[str, str]]:
    """
        The built-in verbs under ``noun`` (``("runs", "wait")`` for
        ``runs`` or ``run``).

        :param noun: Noun as typed or as the tree spells it.

        :returns: Keys of :data:`_BUILTIN_VERBS`, sorted.
    """
    normalized = parser.normalize_word(noun)
    candidates = (normalized, normalized + "s")
    rtnval = sorted(key for key in _BUILTIN_VERBS.keys() if key[0] in candidates)
    return rtnval


def _builtin_verbs_for(noun: str) -> List[str]:
    """
        The built-in verbs under ``noun`` (``wait`` for ``runs``).

        :param noun: Noun as typed or as the tree spells it.

        :returns: Verbs.
    """
    rtnval = [verb for (_noun, verb) in _builtin_verb_keys_for(noun)]
    return rtnval


def _builtin_verb_key(noun: str, verb: str) -> Optional[Tuple[str, str]]:
    """
        The built-in verb ``(noun, verb)`` names, accepting the
        singular noun (``run wait``).

        :param noun: Noun as typed.
        :param verb: Verb as typed.

        :returns: Key of :data:`_BUILTIN_VERBS` or ``None``.
    """
    normalized_noun = parser.normalize_word(noun)
    normalized_verb = parser.normalize_word(verb)
    for candidate in (normalized_noun, normalized_noun + "s"):
        if (candidate, normalized_verb) in _BUILTIN_VERBS:
            rtnval: Optional[Tuple[str, str]] = (candidate, normalized_verb)
            return rtnval
    return None


def _verbs_of(*, tree: CommandTree, noun: str) -> List[str]:
    """
        Every verb of ``noun`` (as the tree spells it): canonical
        verbs, or the alias verbs of an alias-only noun, plus built-in
        verbs.

        :param tree: Command tree.
        :param noun: Noun.

        :returns: Verbs.
    """
    verbs = [descriptor.verb for descriptor in parser.verbs_for(tree=tree, noun=noun)]
    if len(verbs) == 0:
        verbs = [alias for alias, _descriptor in parser.alias_verbs_for(tree=tree, noun=noun)]
    verbs.extend(_builtin_verbs_for(noun))
    rtnval = sorted(set(verbs))
    return rtnval


# ---------------------------------------------------------------------------
# Built-in commands
# ---------------------------------------------------------------------------


def _run_builtin_command(*, ctx: CliContext, noun: str, args: Sequence[str]) -> int:
    """
        Run one of pyc's own top-level commands.

        :param ctx: Invocation context.
        :param noun: Command word.
        :param args: Arguments after it (help flags included; the
                     command's own parser answers them).

        :returns: Exit code.
    """
    if noun == "login":
        from ccai.pychestrate.cli.commands.auth import run_login  # noqa: E402
        return run_login(ctx=ctx, args=args)
    if noun == "logout":
        from ccai.pychestrate.cli.commands.auth import run_logout  # noqa: E402
        return run_logout(ctx=ctx, args=args)
    if noun == "whoami":
        from ccai.pychestrate.cli.commands.auth import run_whoami  # noqa: E402
        return run_whoami(ctx=ctx, args=args)
    if noun == "config":
        from ccai.pychestrate.cli.commands.config import run_config  # noqa: E402
        if len(args) == 0:
            args = ["--help"]
        return run_config(ctx=ctx, args=args)
    if noun == "commands":
        return _run_commands(ctx=ctx, args=args)
    if noun == "ext":
        from ccai.pychestrate.cli.commands.ext import run_ext  # noqa: E402
        return run_ext(ctx=ctx, args=args)
    if noun == "version":
        from ccai.pychestrate.cli.commands.version import run_version  # noqa: E402
        return run_version(ctx=ctx, args=args)
    raise CliUsageError("'{}' is not a pyc command".format(noun))


def _run_builtin_verb(*, ctx: CliContext, key: Tuple[str, str], args: Sequence[str]) -> int:
    """
        Run a built-in verb of an API noun.

        :param ctx: Invocation context.
        :param key: ``(noun, verb)`` of :data:`_BUILTIN_VERBS`.
        :param args: Arguments after the verb.

        :returns: Exit code.
    """
    if key == ("runs", "wait"):
        from ccai.pychestrate.cli.commands.runs import run_runs_wait  # noqa: E402
        return run_runs_wait(ctx=ctx, profile_resolver=lambda: resolve_profile(ctx=ctx), args=args)
    if key == ("plugin-api", "catalog"):
        from ccai.pychestrate.cli.commands.ext import run_plugin_api_catalog  # noqa: E402
        return run_plugin_api_catalog(ctx=ctx, args=args)
    raise CliUsageError("'{} {}' is not a pyc command".format(key[0], key[1]))


def _run_commands(*, ctx: CliContext, args: Sequence[str]) -> int:
    """
        ``pyc commands [--refresh]``.

        :param ctx: Invocation context.
        :param args: Arguments after ``commands``.

        :returns: Exit code.
    """
    from ccai.pychestrate.cli.argparsing import CliArgumentParser  # noqa: E402
    from ccai.pychestrate.cli.commands import api as api_commands  # noqa: E402

    command_parser = CliArgumentParser(
        prog="pyc commands",
        description=(
            "List every API command the server offers (from its OpenAPI document,\n"
            "cached for an hour)."
        ),
        out_stream=ctx.stdout,
        err_stream=ctx.stderr,
    )
    command_parser.add_argument(
        "--refresh", action="store_true", default=False,
        help="download the server's command list again now",
    )
    namespace = command_parser.parse_args(list(args))
    profile = resolve_profile(ctx=ctx)
    tree, source = api_commands.load_command_tree(ctx=ctx, profile=profile, force_refresh=namespace.refresh)
    wants_rows = (
        ctx.output.output_format not in (None, renderer.FORMAT_TABLE)
        or ctx.output.quiet is True
        or len(ctx.output.fields) > 0
    )
    if wants_rows is True:
        rows = []
        for (noun, verb), descriptor in sorted(tree.commands.items()):
            rows.append({
                "command": "{} {}".format(noun, verb),
                "noun": noun,
                "verb": verb,
                "method": descriptor.operation.method,
                "path": descriptor.operation.path_template,
                "operation_id": descriptor.operation.operation_id,
                "summary": descriptor.operation.summary,
            })
        ctx.emit_result(value=rows, identifier_fields=("command",))
    else:
        ctx.stdout.write(api_commands.render_command_list(tree=tree, source=source))
    rtnval = exit_codes.EXIT_OK
    return rtnval


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


def _not_cached_detail(*, source: str) -> Optional[str]:
    """
        The line explaining that help only knows pyc's built-in
        commands because no command list is cached.

        :param source: Where the tree came from.

        :returns: Text or ``None``.
    """
    if source != "builtin":
        return None
    rtnval = (
        "(help works offline and pyc has no copy of this server's command list yet;"
        " run any command, or 'pyc commands', to download it)"
    )
    return rtnval


def _print_noun_help(*, ctx: CliContext, tree: CommandTree, noun: str) -> None:
    """
        ``pyc <noun> --help``: the tree's verbs plus built-in verbs.

        :param ctx: Invocation context.
        :param tree: Command tree.
        :param noun: Noun as the tree (or the built-in verbs) spell it.

        :returns: None.
    """
    from ccai.pychestrate.cli.commands import api as api_commands  # noqa: E402

    has_tree_verbs = (
        len(parser.verbs_for(tree=tree, noun=noun)) > 0
        or len(parser.alias_verbs_for(tree=tree, noun=noun)) > 0
    )
    if has_tree_verbs is True:
        text = api_commands.render_noun_help(tree=tree, noun=noun)
    else:
        text = "usage: pyc {} <verb> [args]\n\nverbs:\n".format(noun)
    builtin_lines = []
    for key in _builtin_verb_keys_for(noun):
        builtin_lines.append("  {:<24} {}".format(key[1], _BUILTIN_VERBS[key]))
    if len(builtin_lines) > 0:
        if has_tree_verbs is True:
            text = text + "\nbuilt-in verbs:\n" + "\n".join(builtin_lines) + "\n"
        else:
            text = text + "\n".join(builtin_lines) + "\n"
    ctx.stdout.write(text)
    return


def _print_help_for(*, ctx: CliContext, words: Sequence[str]) -> int:
    """
        Help for the command named by ``words`` (``[]``, ``[noun]`` or
        ``[noun, verb]``), without touching the network.

        :param ctx: Invocation context.
        :param words: Command words.

        :returns: Exit code (2 for an unknown command).
    """
    from ccai.pychestrate.cli.commands import api as api_commands  # noqa: E402

    if len(words) == 0:
        _print_top_help(stream=ctx.stdout)
        return exit_codes.EXIT_OK

    noun = words[0]
    if noun in _BUILTIN_NOUNS:
        if noun == HELP_COMMAND:
            _print_top_help(stream=ctx.stdout)
            return exit_codes.EXIT_OK
        rtnval = _run_builtin_command(ctx=ctx, noun=noun, args=list(words[1:]) + ["--help"])
        return rtnval

    if len(words) >= 2:
        builtin_key = _builtin_verb_key(noun, words[1])
        if builtin_key is not None:
            rtnval = _run_builtin_verb(ctx=ctx, key=builtin_key, args=["--help"])
            return rtnval

    tree, source = _offline_tree(ctx=ctx)
    resolved_noun = parser.resolve_noun(tree=tree, noun=noun)
    builtin_keys = _builtin_verb_keys_for(noun)
    if resolved_noun is None and len(builtin_keys) == 0:
        raise _unknown_command_error(
            noun=noun, verb=None, known_nouns=_known_nouns(tree=tree),
            detail=_not_cached_detail(source=source),
        )

    if len(words) == 1:
        shown_noun = resolved_noun
        if shown_noun is None:
            shown_noun = builtin_keys[0][0]
        _print_noun_help(ctx=ctx, tree=tree, noun=shown_noun)
        return exit_codes.EXIT_OK

    verb = words[1]
    descriptor = parser.lookup_command(tree=tree, noun=noun, verb=verb)
    if descriptor is None:
        error = _unknown_verb_error(
            noun=resolved_noun or noun, verb=verb, verbs=_verbs_of(tree=tree, noun=resolved_noun or noun),
        )
        detail = _not_cached_detail(source=source)
        if detail is not None:
            error = CliUsageError("{}\n{}".format(error, detail))
        raise error
    api_commands.build_command_parser(ctx=ctx, descriptor=descriptor).print_help()
    return exit_codes.EXIT_OK


# ---------------------------------------------------------------------------
# API commands
# ---------------------------------------------------------------------------


def _handle_api_command(*, ctx: CliContext, noun: str, verb: str, args: Sequence[str]) -> int:
    """
        Run a generated API command, loading the command tree first.

        :param ctx: Invocation context.
        :param noun: Noun as typed.
        :param verb: Verb as typed.
        :param args: Arguments after the verb.

        :returns: Exit code.
    """
    from ccai.pychestrate.cli.commands import api as api_commands  # noqa: E402

    try:
        profile = resolve_profile(ctx=ctx)
    except (NotConfiguredError, CredentialsFileNotFoundError, ProfileNotFoundError) as xcpt:
        # Not configured: a command pyc cannot know is a usage error;
        # a real one reports the configuration problem.
        fallback = api_commands.fallback_command_tree()
        if parser.lookup_command(tree=fallback, noun=noun, verb=verb) is None:
            raise _unknown_command_error(
                noun=noun, verb=verb, known_nouns=_known_nouns(tree=fallback),
                detail=(
                    "pyc could not load the server's command list: {}".format(
                        str(xcpt).splitlines()[0]
                    )
                ),
            ) from None
        raise

    tree, source = api_commands.load_command_tree(ctx=ctx, profile=profile)
    descriptor = parser.lookup_command(tree=tree, noun=noun, verb=verb)
    if descriptor is None and source == "cache":
        tree, source = api_commands.load_command_tree(ctx=ctx, profile=profile, force_refresh=True)
        descriptor = parser.lookup_command(tree=tree, noun=noun, verb=verb)
    if descriptor is None:
        resolved_noun = parser.resolve_noun(tree=tree, noun=noun)
        if resolved_noun is not None:
            raise _unknown_verb_error(noun=resolved_noun, verb=verb, verbs=_verbs_of(tree=tree, noun=resolved_noun))
        detail = None
        if source == "builtin":
            detail = "(the server's OpenAPI document could not be loaded, so only pyc's built-in commands are known)"
        raise _unknown_command_error(noun=noun, verb=verb, known_nouns=_known_nouns(tree=tree), detail=detail)

    rtnval = api_commands.run_api_command(ctx=ctx, profile=profile, descriptor=descriptor, args=args, tree=tree)
    return rtnval


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _dispatch(*, ctx: CliContext, remainder: List[str]) -> int:
    """
        Route one invocation.

        :param ctx: Invocation context.
        :param remainder: Argv without global options.

        :returns: Exit code.
    """
    if len(remainder) > 0 and remainder[0] == VERSION_FLAG:
        ctx.stdout.write("pyc {}\n".format(CLI_VERSION))
        return exit_codes.EXIT_OK

    help_requested, tokens = _split_help_request(tokens=remainder)
    if len(tokens) == 0:
        _print_top_help(stream=ctx.stdout)
        return exit_codes.EXIT_OK

    first = tokens[0]
    if first == HELP_COMMAND:
        rtnval = _print_help_for(ctx=ctx, words=_leading_words(tokens[1:], 2))
        return rtnval
    if first.startswith("-"):
        hint = suggestions.did_you_mean(word=first.split("=", 1)[0], candidates=_GLOBAL_OPTION_SPELLINGS)
        first_line = "unknown option '{}'{}".format(first, "; " + hint if len(hint) > 0 else "")
        raise CliUsageError("{} See 'pyc --help'.".format(_end_sentence(first_line)))

    if first in _BUILTIN_NOUNS:
        # The built-in's own parser answers --help (offline).
        rtnval = _run_builtin_command(ctx=ctx, noun=first, args=_args_after_first_word(remainder=remainder))
        return rtnval

    if help_requested is True:
        rtnval = _print_help_for(ctx=ctx, words=_leading_words(tokens, 2))
        return rtnval

    noun = first
    if len(tokens) == 1 or tokens[1].startswith("-"):
        tree, source = _offline_tree(ctx=ctx)
        resolved_noun = parser.resolve_noun(tree=tree, noun=noun)
        builtin_keys = _builtin_verb_keys_for(noun)
        if resolved_noun is None and len(builtin_keys) == 0:
            raise _unknown_command_error(
                noun=noun, verb=None, known_nouns=_known_nouns(tree=tree),
                detail=_not_cached_detail(source=source),
            )
        shown_noun = resolved_noun if resolved_noun is not None else builtin_keys[0][0]
        raise CliUsageError(
            "'pyc {}' needs a verb: {} (see 'pyc {} --help')".format(
                shown_noun, ", ".join(_verbs_of(tree=tree, noun=shown_noun)), shown_noun
            )
        )

    verb = tokens[1]
    args = tokens[2:]
    builtin_key = _builtin_verb_key(noun, verb)
    if builtin_key is not None:
        rtnval = _run_builtin_verb(ctx=ctx, key=builtin_key, args=args)
        return rtnval

    rtnval = _handle_api_command(ctx=ctx, noun=noun, verb=verb, args=args)
    return rtnval


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
        output=renderer.OutputOptions(
            output_format=parsed_globals.get("output"),
            fields=parsed_globals.get("fields") or tuple(),
            quiet=bool(parsed_globals.get("quiet")),
        ),
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
