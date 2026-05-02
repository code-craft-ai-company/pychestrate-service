"""
.. module:: test_p10r_pyc_ext_invoke_e2e
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: End-to-end test for ``pyc ext <ext-name> <verb>`` dispatch.

.. moduleauthor:: Automation Mojo LLC

The slice closes the loop between two previously-orthogonal pieces:

* ``CLISubcommandExtension`` (p10n) — declares
  ``pyc ext <ext-name> <verb>`` descriptors plus the wrapped
  ``operation_id``.
* ``RestEndpointExtension`` + ``ext_router`` (p10i / p10j) — emit
  the live :class:`MountManifest` carrying every concrete
  ``/api/v1/ext/<ext-name><suffix>`` route.

Discovery walks both subclass trees, the dispatcher resolves the
matching descriptor + mounted-route pair, and the existing transport
seam drives the call. The reference pair shipped in-tree is
``PycExtExampleSubcommand`` ↔ ``ExampleEchoEndpoints`` —
``pyc ext example echo --message=hello`` round-trips through to
``GET /api/v1/ext/example/echo?message=hello``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import io
import json

from automojo import testbase

from automojo.pychestrate.cli import entry, exit_codes
from automojo.pychestrate.cli.extensions.discovery import (
    find_descriptor,
    find_mounted_route_for_verb,
    find_subcommand_class,
    resolve_ext_command,
)
from automojo.pychestrate.cli.extensions.example_subcommand import (
    PycExtExampleSubcommand,
)
from automojo.pychestrate.cli.models import CliProfile, RestResponse

# Side-effect imports — load every half of the example pair so
# ``__subclasses__`` enumerations cover them deterministically.
from automojo.pychestrate.webservice.extensions.rest_endpoint_example import (  # noqa: F401
    ExampleEchoEndpoints,
)
from automojo.pychestrate.webservice.extensions.rest_endpoint_protocol import (  # noqa: F401
    RestEndpointExtension,
)


def _build_profile():
    rtnval = CliProfile(
        profile_name="default",
        server_url="https://example.test",
        bearer_token="token-x",
        bearer_token_expires_at=None,
        mtls_cert_path=None,
        mtls_key_path=None,
        verify_tls=True,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def test_find_subcommand_class_returns_example_for_known_ext_name():
    """
    **Feature: 8-cli M2 (ext invocation)**
    **Property: find_subcommand_class returns the loaded
    PycExtExampleSubcommand for ext_name='example'.**
    """
    found = find_subcommand_class(ext_name="example")
    testbase.assert_equal(found is PycExtExampleSubcommand, True)
    return


def test_find_subcommand_class_returns_none_for_unknown_ext_name():
    """
    **Feature: 8-cli M2 (ext invocation)**
    **Property: find_subcommand_class returns None when no extension
    claims the ext_name.**
    """
    found = find_subcommand_class(ext_name="bogus-no-extension")
    testbase.assert_equal(found, None)
    return


def test_find_descriptor_returns_echo_descriptor():
    descriptor = find_descriptor(
        subcommand_class=PycExtExampleSubcommand, verb="echo"
    )
    testbase.assert_equal(descriptor is not None, True)
    testbase.assert_equal(descriptor.verb, "echo")
    testbase.assert_equal(descriptor.operation_id, "ext_example_echo")
    return


def test_find_descriptor_returns_none_for_unknown_verb():
    descriptor = find_descriptor(
        subcommand_class=PycExtExampleSubcommand, verb="bogus-verb"
    )
    testbase.assert_equal(descriptor, None)
    return


def test_find_mounted_route_resolves_example_echo():
    """
    **Feature: 8-cli M2 (ext invocation)**
    **Property: find_mounted_route_for_verb returns the matching
    /api/v1/ext/example/echo route from the live ext-router manifest.**
    """
    route = find_mounted_route_for_verb(ext_name="example", verb="echo")
    testbase.assert_equal(route is not None, True)
    testbase.assert_equal(route.full_path, "/api/v1/ext/example/echo")
    testbase.assert_equal(route.method, "GET")
    return


def test_resolve_ext_command_returns_full_bundle():
    """
    **Feature: 8-cli M2 (ext invocation)**
    **Property: resolve_ext_command returns a populated
    ResolvedExtCommand with descriptor, mounted_route, and the
    declaring subcommand_class for a known (ext_name, verb) pair.**
    """
    resolved = resolve_ext_command(ext_name="example", verb="echo")
    testbase.assert_equal(resolved is not None, True)
    testbase.assert_equal(resolved.subcommand_class is PycExtExampleSubcommand, True)
    testbase.assert_equal(resolved.descriptor.verb, "echo")
    testbase.assert_equal(resolved.mounted_route.full_path, "/api/v1/ext/example/echo")
    return


def test_resolve_ext_command_returns_none_on_unknown_ext_name():
    rtnval = resolve_ext_command(ext_name="bogus-no-extension", verb="echo")
    testbase.assert_equal(rtnval, None)
    return


def test_resolve_ext_command_returns_none_on_unknown_verb():
    rtnval = resolve_ext_command(ext_name="example", verb="bogus-verb")
    testbase.assert_equal(rtnval, None)
    return


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------

def test_pyc_ext_example_echo_round_trips_through_transport():
    """
    **Feature: 8-cli M2 (ext invocation)**
    **Property: pyc ext example echo --message=hello hits
    GET /api/v1/ext/example/echo?message=hello with the bearer
    header attached and emits the JSON response.**
    """
    captured = {}

    def _fake_opener(*, request, timeout, context):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["authorization"] = (
            request.headers.get("Authorization", "")
        )
        rtnval = RestResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body={"message": "hello"},
            raw_text='{"message":"hello"}',
        )
        return rtnval

    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["ext", "example", "echo", "--message=hello"],
        stdout=out,
        stderr=err,
        request_opener=_fake_opener,
        profile_loader=lambda name: _build_profile(),
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
    testbase.assert_equal(
        captured["url"],
        "https://example.test/api/v1/ext/example/echo?message=hello",
    )
    testbase.assert_equal(captured["method"], "GET")
    testbase.assert_equal(captured["authorization"], "Bearer token-x")
    testbase.assert_equal('"message": "hello"' in out.getvalue(), True)
    return


def test_pyc_ext_accepts_separated_flag_form():
    """
    **Feature: 8-cli M2 (ext invocation)**
    **Property: --message hello (space-separated) is accepted in
    addition to --message=hello.**
    """
    captured = {}

    def _fake_opener(*, request, timeout, context):
        captured["url"] = request.full_url
        rtnval = RestResponse(
            status_code=200, headers={}, body={}, raw_text="{}"
        )
        return rtnval

    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["ext", "example", "echo", "--message", "hi there"],
        stdout=out,
        stderr=err,
        request_opener=_fake_opener,
        profile_loader=lambda name: _build_profile(),
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
    testbase.assert_equal("message=hi+there" in captured["url"], True)
    return


def test_pyc_ext_unknown_ext_name_returns_usage_error():
    """
    **Feature: 8-cli M2 (ext invocation)**
    **Property: pyc ext bogus-ext echo returns EXIT_USAGE_ERROR
    with a stderr diagnostic naming the unknown ext_name.**
    """
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["ext", "bogus-ext", "echo"],
        stdout=out,
        stderr=err,
        profile_loader=lambda name: _build_profile(),
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_USAGE_ERROR)
    testbase.assert_equal("bogus-ext" in err.getvalue(), True)
    return


def test_pyc_ext_unknown_verb_returns_usage_error():
    """
    **Feature: 8-cli M2 (ext invocation)**
    **Property: pyc ext example bogus-verb returns
    EXIT_USAGE_ERROR with a stderr diagnostic naming the verb.**
    """
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["ext", "example", "bogus-verb"],
        stdout=out,
        stderr=err,
        profile_loader=lambda name: _build_profile(),
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_USAGE_ERROR)
    err_text = err.getvalue()
    testbase.assert_equal("example" in err_text, True)
    testbase.assert_equal("bogus-verb" in err_text, True)
    return


def test_pyc_ext_undeclared_flag_rejected():
    """
    **Feature: 8-cli M2 (ext invocation)**
    **Property: A flag not declared on the descriptor is rejected
    rather than silently passed.**
    """
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["ext", "example", "echo", "--undeclared-flag=x"],
        stdout=out,
        stderr=err,
        profile_loader=lambda name: _build_profile(),
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_USAGE_ERROR)
    testbase.assert_equal("undeclared-flag" in err.getvalue(), True)
    return


def test_pyc_ext_with_no_subverb_returns_usage_error():
    """
    **Feature: 8-cli M2 (ext invocation)**
    **Property: pyc ext example (without a verb) returns
    EXIT_USAGE_ERROR.**
    """
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["ext", "example"],
        stdout=out,
        stderr=err,
        profile_loader=lambda name: _build_profile(),
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_USAGE_ERROR)
    return


def test_pyc_ext_propagates_authentication_error():
    """
    **Feature: 8-cli M2 (ext invocation)**
    **Property: A 401 from the wrapped REST endpoint maps to
    EXIT_AUTHENTICATION_ERROR.**
    """

    def _fake_opener(*, request, timeout, context):
        rtnval = RestResponse(
            status_code=401, headers={}, body=None, raw_text="not authenticated"
        )
        return rtnval

    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["ext", "example", "echo", "--message=x"],
        stdout=out,
        stderr=err,
        request_opener=_fake_opener,
        profile_loader=lambda name: _build_profile(),
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_AUTHENTICATION_ERROR)
    return


def test_pyc_ext_list_still_works_alongside_invocation_path():
    """
    **Feature: 8-cli M2 (ext invocation)**
    **Property: ``pyc ext list`` still routes to the manifest list
    even though the ext-namespace is shared with the new
    descriptor-driven dispatch.**
    """

    def _fake_opener(*, request, timeout, context):
        rtnval = RestResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=[],
            raw_text="[]",
        )
        return rtnval

    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["ext", "list"],
        stdout=out,
        stderr=err,
        request_opener=_fake_opener,
        profile_loader=lambda name: _build_profile(),
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
    return


# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------

def test_top_help_advertises_ext_invocation_form():
    """
    **Feature: 8-cli M2 (ext invocation)**
    **Property: pyc --help mentions the new ext invocation form.**
    """
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(argv=["--help"], stdout=out, stderr=err)
    testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
    text = out.getvalue()
    testbase.assert_equal("ext <name> <verb>" in text, True)
    return


def test_ext_noun_help_lists_invocation_form():
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(argv=["ext", "--help"], stdout=out, stderr=err)
    testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
    testbase.assert_equal("<ext-name> <verb>" in out.getvalue(), True)
    return


def test_unknown_noun_diagnostic_lists_ext_invocation_form():
    """
    **Feature: 8-cli M2 (ext invocation)**
    **Property: An unknown noun's stderr diagnostic now includes
    'ext <ext-name> <verb> [args]' in the supported list.**
    """
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["bogus-noun", "list"], stdout=out, stderr=err
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_USAGE_ERROR)
    testbase.assert_equal(
        "'ext <ext-name> <verb> [args]'" in err.getvalue(), True
    )
    return
