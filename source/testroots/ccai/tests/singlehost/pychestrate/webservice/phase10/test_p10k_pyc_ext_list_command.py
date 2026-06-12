"""
.. module:: test_p10k_pyc_ext_list_command
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ``pyc ext list`` (8-cli M2 partial).

.. moduleauthor:: Code Craft AI LLC

The CLI consumes the new ``GET /api/v1/plugin-api/_meta/mounts``
endpoint, which mirrors the in-process :class:`MountManifest` produced
by ``extensions.ext_router.mount_extension_routes``. Tests stub the
transport opener so the dispatcher path is exercised without a live
HTTP server.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import io
import json

from ccai import testbase

from ccai.pychestrate.cli import entry, exit_codes
from ccai.pychestrate.cli.models import CliProfile, RestResponse


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


def test_ext_list_hits_documented_mounts_endpoint():
    """
    **Feature: 8-cli M2 (ext list)**
    **Property: pyc ext list issues a GET against
    /api/v1/plugin-api/_meta/mounts and prints the JSON body.**
    """
    captured = {}

    body = [
        {
            "ext_name": "example",
            "method": "GET",
            "path_suffix": "/echo",
            "full_path": "/api/v1/ext/example/echo",
            "handler_class": "ExampleEchoEndpoints",
            "required_permissions": [],
            "required_capabilities": [],
            "description": "Echo back",
        }
    ]

    def _fake_opener(*, request, timeout, context):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        rtnval = RestResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=body,
            raw_text=json.dumps(body),
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
    testbase.assert_equal(
        captured["url"], "https://example.test/api/v1/plugin-api/_meta/mounts"
    )
    testbase.assert_equal(captured["method"], "GET")
    testbase.assert_equal('"ext_name": "example"' in out.getvalue(), True)
    testbase.assert_equal('"full_path": "/api/v1/ext/example/echo"' in out.getvalue(), True)
    return


def test_ext_list_handles_empty_manifest():
    """
    **Feature: 8-cli M2 (ext list)**
    **Property: An empty manifest renders as ``[]`` (matching
    project list's empty case).**
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
    testbase.assert_equal(out.getvalue().strip(), "[]")
    return


def test_ext_list_propagates_authentication_error():
    """
    **Feature: 8-cli M2 (ext list)**
    **Property: A 401 maps to EXIT_AUTHENTICATION_ERROR.**
    """

    def _fake_opener(*, request, timeout, context):
        rtnval = RestResponse(
            status_code=401,
            headers={},
            body=None,
            raw_text="not authenticated",
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
    testbase.assert_equal(rtnval, exit_codes.EXIT_AUTHENTICATION_ERROR)
    return


def test_ext_list_propagates_server_error():
    """
    **Feature: 8-cli M2 (ext list)**
    **Property: A 500 from the server maps to EXIT_SERVER_ERROR.**
    """

    def _fake_opener(*, request, timeout, context):
        rtnval = RestResponse(
            status_code=500,
            headers={},
            body=None,
            raw_text="upstream broke",
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
    testbase.assert_equal(rtnval, exit_codes.EXIT_SERVER_ERROR)
    return


def test_ext_list_does_not_fetch_openapi_document():
    """
    **Feature: 8-cli M2 (ext list)**
    **Property: ext list bypasses the OpenAPI fetch since the mounts
    endpoint is a stable metadata path.**
    """

    def _failing_openapi_fetcher():
        raise RuntimeError(
            "OpenAPI fetcher must not be invoked for ext list"
        )

    def _fake_opener(*, request, timeout, context):
        rtnval = RestResponse(
            status_code=200,
            headers={},
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
        openapi_fetcher=_failing_openapi_fetcher,
        request_opener=_fake_opener,
        profile_loader=lambda name: _build_profile(),
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
    return


def test_ext_noun_help_lists_list_verb():
    """
    **Feature: 8-cli M2 (ext help)**
    **Property: pyc ext --help describes the list verb.**
    """
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["ext", "--help"], stdout=out, stderr=err
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
    testbase.assert_equal("list" in out.getvalue(), True)
    return


def test_ext_list_verb_help_describes_command():
    """
    **Feature: 8-cli M2 (ext help)**
    **Property: pyc ext list --help describes what it returns.**
    """
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["ext", "list", "--help"], stdout=out, stderr=err
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
    testbase.assert_equal("ext_name" in out.getvalue(), True)
    return


def test_top_help_advertises_ext_list():
    """
    **Feature: 8-cli M2 (top help)**
    **Property: pyc --help lists ``ext list`` alongside the other
    M2 commands.**
    """
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(argv=["--help"], stdout=out, stderr=err)
    testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
    testbase.assert_equal("ext list" in out.getvalue(), True)
    return


def test_unknown_noun_lists_ext_in_supported_commands():
    """
    **Feature: 8-cli M2 (top dispatch)**
    **Property: An unknown noun's stderr diagnostic includes
    ``'ext list'`` in the supported list.**
    """
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["bogus-noun", "list"], stdout=out, stderr=err
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_USAGE_ERROR)
    testbase.assert_equal("'ext list'" in err.getvalue(), True)
    return
