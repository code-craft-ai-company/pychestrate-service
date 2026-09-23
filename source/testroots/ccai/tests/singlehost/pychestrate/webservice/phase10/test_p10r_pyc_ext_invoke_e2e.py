"""
.. module:: test_p10r_pyc_ext_invoke_e2e
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: End-to-end test for ``pyc ext <ext-name> <verb>`` dispatch.

.. moduleauthor:: Code Craft AI LLC

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

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import io
import json

from ccai import testbase

from ccai.pychestrate.cli import entry, exit_codes
from ccai.pychestrate.cli.extensions.discovery import (
    find_descriptor,
    find_subcommand_class,
)
from ccai.pychestrate.cli.extensions.example_subcommand import (
    PycExtExampleSubcommand,
)
from ccai.pychestrate.cli.models import CliProfile, RestResponse

# The in-process pairing of the two halves lives with the service
# (the CLI package imports no service code).
from ccai.pychestrate.webservice.extensions.cli_ext_pairing import (
    find_mounted_route_for_verb,
    resolve_ext_command,
)

# Side-effect imports — load every half of the example pair so
# ``__subclasses__`` enumerations cover them deterministically.
from ccai.pychestrate.webservice.extensions.rest_endpoint_example import (  # noqa: F401
    ExampleEchoEndpoints,
)
from ccai.pychestrate.webservice.extensions.rest_endpoint_protocol import (  # noqa: F401
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


#: The server's ``GET /api/v1/ext`` answer for the in-tree example: the
#: dispatcher resolves the route (method + URL) from this listing.
_EXAMPLE_EXT_LISTING = {
    "items": [
        {
            "ext_name": "example",
            "method": "GET",
            "path_suffix": "/echo",
            "full_path": "/api/v1/ext/example/echo",
        }
    ],
    "total": 1,
    "dynamic_mount": "mounted",
}


def _is_ext_listing_request(request) -> bool:
    rtnval = request.full_url.endswith("/api/v1/ext")
    return rtnval


def _listing_response() -> RestResponse:
    rtnval = RestResponse(
        status_code=200,
        headers={"content-type": "application/json"},
        body=_EXAMPLE_EXT_LISTING,
        raw_text="",
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
        if _is_ext_listing_request(request):
            return _listing_response()
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
        if _is_ext_listing_request(request):
            return _listing_response()
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
        if _is_ext_listing_request(request):
            return _listing_response()
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


# ---------------------------------------------------------------------------
# Server-side route resolution (CLI-01)
# ---------------------------------------------------------------------------


def test_pyc_ext_resolves_the_route_from_the_server_listing():
    """
    **Feature: 8-cli (ext invocation, CLI-01)**
    **Property: the dispatcher asks the server's GET /api/v1/ext for
    the route before calling it, so the call targets what the server
    mounts rather than what the CLI process happens to import.**
    """
    urls = []

    def _fake_opener(*, request, timeout, context):
        urls.append(request.full_url)
        if _is_ext_listing_request(request):
            return _listing_response()
        rtnval = RestResponse(status_code=200, headers={}, body={}, raw_text="{}")
        return rtnval

    rtnval = entry.main(
        argv=["ext", "example", "echo", "--message=x"],
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        request_opener=_fake_opener,
        profile_loader=lambda name: _build_profile(),
    )
    testbase.assert_equal(
        (rtnval, urls),
        (exit_codes.EXIT_OK, [
            "https://example.test/api/v1/ext",
            "https://example.test/api/v1/ext/example/echo?message=x",
        ]),
    )
    return


def test_pyc_ext_route_missing_from_the_server_is_not_found():
    """
    **Feature: 8-cli (ext invocation, CLI-01)**
    **Property: when the server's listing does not name the route, the
    CLI exits 4 saying the server does not mount it (instead of the old
    false "does not declare verb").**
    """

    def _fake_opener(*, request, timeout, context):
        rtnval = RestResponse(
            status_code=200, headers={"content-type": "application/json"},
            body={"items": [], "total": 0, "dynamic_mount": "deferred"}, raw_text="",
        )
        return rtnval

    err = io.StringIO()
    rtnval = entry.main(
        argv=["ext", "example", "echo", "--message=x"],
        stdout=io.StringIO(),
        stderr=err,
        request_opener=_fake_opener,
        profile_loader=lambda name: _build_profile(),
    )
    testbase.assert_equal(
        (rtnval, "does not mount /api/v1/ext/example/echo" in err.getvalue(),
         "does not declare verb" in err.getvalue()),
        (exit_codes.EXIT_NOT_FOUND, True, False),
    )
    return


def test_pyc_ext_unserved_listed_route_explains_the_deferred_mount():
    """
    **Feature: 8-cli (ext invocation, CLI-01)**
    **Property: a route the server lists but answers 404 for (its
    listing says dynamic_mount is deferred) exits 4 and says the server
    does not serve extension routes yet.**
    """

    def _fake_opener(*, request, timeout, context):
        if _is_ext_listing_request(request):
            listing = dict(_EXAMPLE_EXT_LISTING)
            listing["dynamic_mount"] = "deferred"
            return RestResponse(
                status_code=200, headers={"content-type": "application/json"},
                body=listing, raw_text="",
            )
        rtnval = RestResponse(status_code=404, headers={}, body=None, raw_text="Not Found")
        return rtnval

    err = io.StringIO()
    rtnval = entry.main(
        argv=["ext", "example", "echo", "--message=x"],
        stdout=io.StringIO(),
        stderr=err,
        request_opener=_fake_opener,
        profile_loader=lambda name: _build_profile(),
    )
    testbase.assert_equal(
        (rtnval, "does not serve extension routes yet" in err.getvalue()),
        (exit_codes.EXIT_NOT_FOUND, True),
    )
    return
