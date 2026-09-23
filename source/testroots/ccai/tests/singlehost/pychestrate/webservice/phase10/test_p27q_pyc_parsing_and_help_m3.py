"""
.. module:: test_p27q_pyc_parsing_and_help_m3
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``pyc`` parsing and help (audit finding CLI-09): help
               never touches the network, unknown commands / verbs /
               flags exit 2 with "did you mean", nothing is silently
               ignored.

.. moduleauthor:: Code Craft AI LLC

The audit found ``--help`` after a global flag ran the command (a
network call), ``ext ... --help`` needed credentials, a typo such as
``pyc frobnicate --help`` exited 0, and ``--limit`` / ``--state`` /
``--output`` were silently ignored by the built-in commands. Every test
here runs in a throw-away HOME with a fake server that records every
request, so "no network" is checked by the absence of requests.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import copy
import gc

from typing import Any, ClassVar, Dict, Tuple

from ccai import testbase

from ccai.pychestrate.cli import exit_codes
from ccai.pychestrate.cli.extensions.cli_subcommand import (
    CLISubcommandDescriptor,
    CLISubcommandExtension,
)
from ccai.pychestrate.cli.models import RestResponse
from ccai.testshared.factories.pyc.pyc_harness import (
    SERVER,
    TOKEN,
    PycFakeServer,
    PycSandbox,
    run_pyc,
)


WIDGETS_DOCUMENT: Dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Pychestrate", "version": "9.9.9"},
    "servers": [{"url": "/api/v1"}],
    "paths": {
        "/widgets": {
            "get": {
                "operationId": "widgets_list", "tags": ["widgets"], "summary": "List widgets.",
                "parameters": [
                    {"name": "state", "in": "query", "schema": {"type": "string"}},
                    {"name": "per_page", "in": "query", "schema": {"type": "integer"}},
                ],
            },
        },
        "/widgets/{widget_id}": {
            "get": {
                "operationId": "widgets_read", "tags": ["widgets"], "summary": "Read a widget.",
                "parameters": [{"name": "widget_id", "in": "path", "required": True}],
            },
        },
    },
}


class _FetchSpy:
    """
        OpenAPI fetch seam that counts how often pyc tried to download
        the document (help must never try).
    """

    def __init__(self) -> None:
        self.calls = 0
        return

    def __call__(self) -> Dict[str, Any]:
        self.calls = self.calls + 1
        rtnval = _widgets_document()
        return rtnval


def _widgets_document() -> Dict[str, Any]:
    rtnval = copy.deepcopy(WIDGETS_DOCUMENT)
    return rtnval


def _cached_sandbox() -> PycSandbox:
    """
        A logged-in sandbox whose command list (WIDGETS_DOCUMENT) is
        cached, as if a command had run before.
    """
    sandbox = PycSandbox()
    sandbox.log_in()
    sandbox.cache_command_list(document=_widgets_document())
    return sandbox


# ===========================================================================
# Help never touches the network
# ===========================================================================


def test_generated_command_help_is_answered_from_the_cache():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: 'pyc widgets list --help' prints the command's help from
    the cached command list and sends no request.**
    """
    sandbox = _cached_sandbox()
    try:
        server = PycFakeServer()
        fetch_spy = _FetchSpy()
        rc, out, _err = run_pyc(sandbox=sandbox, argv=["widgets", "list", "--help"], opener=server,
                                openapi_fetcher=fetch_spy)
        testbase.assert_equal(
            (rc, "usage: pyc widgets list" in out, server.requests, fetch_spy.calls),
            (exit_codes.EXIT_OK, True, [], 0),
        )
    finally:
        sandbox.close()
    return


def test_help_after_a_global_option_does_not_run_the_command():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: '--help' after a global option ('pyc --profile default
    widgets list --timeout 5 --help') prints help and sends no request
    (it used to run the command).**
    """
    sandbox = _cached_sandbox()
    try:
        server = PycFakeServer({("GET", "/api/v1/widgets"): {"items": []}})
        fetch_spy = _FetchSpy()
        rc, out, _err = run_pyc(
            sandbox=sandbox, argv=["--profile", "default", "widgets", "list", "--timeout", "5", "--help"],
            opener=server, openapi_fetcher=fetch_spy,
        )
        testbase.assert_equal(
            (rc, "usage: pyc widgets list" in out, server.requests, fetch_spy.calls),
            (exit_codes.EXIT_OK, True, [], 0),
        )
    finally:
        sandbox.close()
    return


def test_noun_help_is_answered_from_the_cache():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: 'pyc widgets --help' lists the noun's verbs from the
    cache and sends no request.**
    """
    sandbox = _cached_sandbox()
    try:
        server = PycFakeServer()
        fetch_spy = _FetchSpy()
        rc, out, _err = run_pyc(sandbox=sandbox, argv=["widgets", "--help"], opener=server,
                                openapi_fetcher=fetch_spy)
        testbase.assert_equal(
            (rc, "list" in out and "get" in out, server.requests, fetch_spy.calls),
            (exit_codes.EXIT_OK, True, [], 0),
        )
    finally:
        sandbox.close()
    return


def test_help_with_nothing_cached_uses_the_builtin_commands():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: with no cached command list, 'pyc projects list --help'
    still answers (from pyc's built-in commands) without a request.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer()
        fetch_spy = _FetchSpy()
        rc, out, _err = run_pyc(sandbox=sandbox, argv=["projects", "list", "--help"], opener=server,
                                openapi_fetcher=fetch_spy)
        testbase.assert_equal(
            (rc, "usage: pyc projects list" in out, server.requests, fetch_spy.calls),
            (exit_codes.EXIT_OK, True, [], 0),
        )
    finally:
        sandbox.close()
    return


def test_help_for_a_command_that_is_not_cached_says_how_to_get_it():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: help for a command pyc cannot know yet (nothing cached)
    exits 2 pointing at 'pyc commands', without a request.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer()
        fetch_spy = _FetchSpy()
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["widgets", "list", "--help"], opener=server,
                                openapi_fetcher=fetch_spy)
        testbase.assert_equal(
            (rc, "'pyc commands'" in err, "no copy of this server's command list" in err,
             server.requests, fetch_spy.calls),
            (exit_codes.EXIT_USAGE_ERROR, True, True, [], 0),
        )
    finally:
        sandbox.close()
    return


def test_help_needs_no_configuration():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: with no credentials at all, 'pyc runs get --help' prints
    help (exit 0) instead of a configuration error.**
    """
    sandbox = PycSandbox()
    try:
        rc, out, _err = run_pyc(sandbox=sandbox, argv=["runs", "get", "--help"], opener=PycFakeServer())
        testbase.assert_equal((rc, "usage: pyc runs get" in out), (exit_codes.EXIT_OK, True))
    finally:
        sandbox.close()
    return


def test_extension_verb_help_needs_no_credentials():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: 'pyc ext example echo --help' prints the verb's flags
    with no credentials and no request (it used to need credentials).**
    """
    sandbox = PycSandbox()
    try:
        server = PycFakeServer()
        rc, out, _err = run_pyc(sandbox=sandbox, argv=["ext", "example", "echo", "--help"], opener=server)
        testbase.assert_equal(
            (rc, "--message VALUE" in out, server.requests), (exit_codes.EXIT_OK, True, [])
        )
    finally:
        sandbox.close()
    return


def test_extension_help_lists_its_verbs():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: 'pyc ext example --help' lists the extension's verbs
    (it used to fail with "does not declare verb '--help'").**
    """
    sandbox = PycSandbox()
    try:
        rc, out, _err = run_pyc(sandbox=sandbox, argv=["ext", "example", "--help"], opener=PycFakeServer())
        testbase.assert_equal((rc, "echo" in out), (exit_codes.EXIT_OK, True))
    finally:
        sandbox.close()
    return


def test_help_command_prints_the_same_help_as_the_flag():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: 'pyc help widgets list' prints exactly what
    'pyc widgets list --help' prints.**
    """
    sandbox = _cached_sandbox()
    try:
        _rc, by_command, _err = run_pyc(sandbox=sandbox, argv=["help", "widgets", "list"], opener=PycFakeServer())
        _rc, by_flag, _err = run_pyc(sandbox=sandbox, argv=["widgets", "list", "--help"], opener=PycFakeServer())
        testbase.assert_equal((by_command == by_flag, len(by_flag) > 0), (True, True))
    finally:
        sandbox.close()
    return


def test_builtin_command_help_sends_nothing():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: 'pyc --help login' (help before the command) prints the
    login help and sends no request.**
    """
    sandbox = PycSandbox()
    try:
        server = PycFakeServer()
        rc, out, _err = run_pyc(sandbox=sandbox, argv=["--help", "login"], opener=server)
        testbase.assert_equal((rc, "usage: pyc login" in out, server.requests), (exit_codes.EXIT_OK, True, []))
    finally:
        sandbox.close()
    return


def test_login_caches_the_command_list_for_offline_help():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: 'pyc login' downloads the server's command list, so the
    very next --help knows the server's commands.**
    """
    sandbox = PycSandbox()
    try:
        me = {"login_name": "dana", "account_kind": "user",
              "authentication": {"method": "api_token", "token_name": "laptop"}}
        server = PycFakeServer({
            ("GET", "/api/v1/me"): me,
            ("GET", "/api/v1/_meta/openapi.json"): _widgets_document(),
        })
        run_pyc(sandbox=sandbox, argv=["login", "--server-url", SERVER, "--with-token"],
                opener=server, stdin_text=TOKEN + "\n")
        rc, out, _err = run_pyc(sandbox=sandbox, argv=["widgets", "get", "--help"], opener=PycFakeServer())
        testbase.assert_equal((rc, "WIDGET_ID" in out), (exit_codes.EXIT_OK, True))
    finally:
        sandbox.close()
    return


# ===========================================================================
# Typos and unknown input exit 2 with "did you mean"
# ===========================================================================


def test_unknown_command_with_help_exits_two():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: 'pyc frobnicate --help' exits 2 (it used to exit 0).**
    """
    sandbox = _cached_sandbox()
    try:
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["frobnicate", "--help"], opener=PycFakeServer())
        testbase.assert_equal((rc, "'frobnicate' is not a known command" in err), (exit_codes.EXIT_USAGE_ERROR, True))
    finally:
        sandbox.close()
    return


def test_unknown_noun_suggests_the_closest_noun():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: 'pyc widgts list' exits 2 suggesting 'widgets'.**
    """
    sandbox = _cached_sandbox()
    try:
        server = PycFakeServer({("GET", "/api/v1/_meta/openapi.json"): _widgets_document()})
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["widgts", "list"], opener=server)
        testbase.assert_equal((rc, "did you mean 'widgets'?" in err), (exit_codes.EXIT_USAGE_ERROR, True))
    finally:
        sandbox.close()
    return


def test_unknown_verb_suggests_the_closest_verb():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: 'pyc widgets lst' exits 2 suggesting 'list'.**
    """
    sandbox = _cached_sandbox()
    try:
        server = PycFakeServer({("GET", "/api/v1/_meta/openapi.json"): _widgets_document()})
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["widgets", "lst"], opener=server)
        testbase.assert_equal((rc, "did you mean 'list'?" in err), (exit_codes.EXIT_USAGE_ERROR, True))
    finally:
        sandbox.close()
    return


def test_unknown_flag_is_rejected_with_a_suggestion():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: 'pyc widgets list --stat x' exits 2 suggesting '--state'
    and sends no request for the command.**
    """
    sandbox = _cached_sandbox()
    try:
        server = PycFakeServer({("GET", "/api/v1/widgets"): {"items": []}})
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["widgets", "list", "--stat", "x"], opener=server)
        testbase.assert_equal(
            (rc, "did you mean '--state'?" in err, "/api/v1/widgets" in server.paths()),
            (exit_codes.EXIT_USAGE_ERROR, True, False),
        )
    finally:
        sandbox.close()
    return


def test_abbreviated_flag_is_not_guessed():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: '--per 5' is not silently taken as '--per-page 5'; it
    exits 2.**
    """
    sandbox = _cached_sandbox()
    try:
        server = PycFakeServer({("GET", "/api/v1/widgets"): {"items": []}})
        rc, _out, _err = run_pyc(sandbox=sandbox, argv=["widgets", "list", "--per", "5"], opener=server)
        testbase.assert_equal(
            (rc, "/api/v1/widgets" in server.paths()), (exit_codes.EXIT_USAGE_ERROR, False)
        )
    finally:
        sandbox.close()
    return


def test_unknown_leading_option_suggests_a_global_option():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: 'pyc --verison' exits 2 suggesting '--version'.**
    """
    sandbox = PycSandbox()
    try:
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["--verison"])
        testbase.assert_equal((rc, "did you mean '--version'?" in err), (exit_codes.EXIT_USAGE_ERROR, True))
    finally:
        sandbox.close()
    return


def test_plugin_api_catalog_rejects_an_unknown_flag():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: 'pyc plugin-api catalog --limit 5' exits 2 without a
    request (the flag used to be sent as the catalog entry name).**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer()
        rc, _out, _err = run_pyc(sandbox=sandbox, argv=["plugin-api", "catalog", "--limit", "5"], opener=server)
        testbase.assert_equal((rc, server.requests), (exit_codes.EXIT_USAGE_ERROR, []))
    finally:
        sandbox.close()
    return


def test_ext_list_rejects_an_unknown_flag():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: 'pyc ext list --state x' exits 2 without a request (the
    flag used to be ignored).**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer()
        rc, _out, _err = run_pyc(sandbox=sandbox, argv=["ext", "list", "--state", "x"], opener=server)
        testbase.assert_equal((rc, server.requests), (exit_codes.EXIT_USAGE_ERROR, []))
    finally:
        sandbox.close()
    return


def test_commands_rejects_an_unknown_flag():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: 'pyc commands --all' exits 2 (the flag used to be
    ignored).**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer()
        rc, _out, _err = run_pyc(sandbox=sandbox, argv=["commands", "--all"], opener=server)
        testbase.assert_equal((rc, server.requests), (exit_codes.EXIT_USAGE_ERROR, []))
    finally:
        sandbox.close()
    return


def test_noun_without_a_verb_lists_the_verbs():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: 'pyc widgets' exits 2 listing the noun's verbs, without
    a request.**
    """
    sandbox = _cached_sandbox()
    try:
        server = PycFakeServer()
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["widgets"], opener=server)
        testbase.assert_equal(
            (rc, "needs a verb: get, list" in err, server.requests), (exit_codes.EXIT_USAGE_ERROR, True, [])
        )
    finally:
        sandbox.close()
    return


def test_profile_without_a_value_is_a_usage_error():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: '--profile' with no value exits 2 instead of falling
    back to the default profile.**
    """
    sandbox = _cached_sandbox()
    try:
        server = PycFakeServer()
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["widgets", "list", "--profile"], opener=server)
        testbase.assert_equal(
            (rc, "--profile needs a value" in err, server.requests), (exit_codes.EXIT_USAGE_ERROR, True, [])
        )
    finally:
        sandbox.close()
    return


def test_arguments_after_double_dash_are_not_options():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: after '--', '--profile' is a value (here the widget id),
    not the global option.**
    """
    sandbox = _cached_sandbox()
    try:
        server = PycFakeServer({("GET", "/api/v1/widgets/--profile"): {"widget_id": "--profile"}})
        rc, _out, _err = run_pyc(sandbox=sandbox, argv=["widgets", "get", "--", "--profile"], opener=server)
        testbase.assert_equal((rc, server.paths()[-1]), (exit_codes.EXIT_OK, "/api/v1/widgets/--profile"))
    finally:
        sandbox.close()
    return


def test_extension_positional_arguments_are_sent():
    """
    **Feature: pyc parsing and help (CLI-09)**
    **Property: an extension verb's positional argument is sent as the
    query parameter of that name (positionals used to be counted and
    then dropped).**
    """

    class _PositionalProbeSubcommand(CLISubcommandExtension):
        ext_name: ClassVar[str] = "pyc-test-probe"

        @classmethod
        def declare_subcommands(cls) -> Tuple[CLISubcommandDescriptor, ...]:
            rtnval = (CLISubcommandDescriptor(
                verb="look", operation_id="ext_probe_look", positional_arg_names=("target",),
                flag_arg_names=tuple(), description="Look at a target.",
            ),)
            return rtnval

    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        listing = {"items": [{"ext_name": "pyc-test-probe", "method": "GET", "path_suffix": "/look",
                              "full_path": "/api/v1/ext/pyc-test-probe/look"}], "dynamic_mount": "mounted"}
        server = PycFakeServer({
            ("GET", "/api/v1/ext"): listing,
            ("GET", "/api/v1/ext/pyc-test-probe/look"): RestResponse(
                status_code=200, headers={"content-type": "application/json"}, body={}, raw_text="{}"),
        })
        rc, _out, _err = run_pyc(sandbox=sandbox, argv=["ext", "pyc-test-probe", "look", "lab-7"], opener=server)
        testbase.assert_equal((rc, server.requests[-1]["query"]), (exit_codes.EXIT_OK, "target=lab-7"))
    finally:
        sandbox.close()
        del _PositionalProbeSubcommand
        gc.collect()
    return
