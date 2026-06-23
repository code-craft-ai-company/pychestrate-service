"""
.. module:: test_p10j_pyc_plugin_api_command
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ``pyc plugin-api catalog`` (8-cli M2 partial).

.. moduleauthor:: Code Craft AI LLC

The CLI consumes the catalog endpoint shipped by ``8-plugin-api`` M1.
``pyc plugin-api catalog`` lists every published entry; ``pyc
plugin-api catalog <name>`` reads a single entry. Both fly through
the existing transport seam so the tests stub the opener.
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


def test_plugin_api_catalog_lists_every_entry():
    """
    **Feature: 8-cli M2 (plugin-api catalog list)**
    **Property: pyc plugin-api catalog hits
    /api/v1/plugin-api/_meta/catalog and emits the JSON body.**
    """
    captured_url = {}

    catalog_body = {
        "factory_protocols": [
            {"name": "auth_provider", "kind": "factory_protocol"},
            {"name": "secrets_backend", "kind": "factory_protocol"},
        ],
        "resource_extensions": [
            {"name": "RestEndpointExtension", "kind": "resource_extension"},
        ],
    }

    def _fake_opener(*, request, timeout, context):
        captured_url["url"] = request.full_url
        captured_url["method"] = request.get_method()
        rtnval = RestResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=catalog_body,
            raw_text=json.dumps(catalog_body),
        )
        return rtnval

    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["plugin-api", "catalog"],
        stdout=out,
        stderr=err,
        request_opener=_fake_opener,
        profile_loader=lambda name: _build_profile(),
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
    testbase.assert_equal(
        captured_url["url"], "https://example.test/api/v1/plugin-api/_meta/catalog"
    )
    testbase.assert_equal(captured_url["method"], "GET")
    testbase.assert_equal('"name": "auth_provider"' in out.getvalue(), True)
    testbase.assert_equal('"RestEndpointExtension"' in out.getvalue(), True)
    return


def test_plugin_api_catalog_reads_single_entry_by_name():
    """
    **Feature: 8-cli M2 (plugin-api catalog detail)**
    **Property: pyc plugin-api catalog auth_provider hits the
    per-entry endpoint with the name path-encoded.**
    """
    captured_url = {}

    detail_body = {
        "name": "auth_provider",
        "kind": "factory_protocol",
        "status": "supported",
    }

    def _fake_opener(*, request, timeout, context):
        captured_url["url"] = request.full_url
        rtnval = RestResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=detail_body,
            raw_text=json.dumps(detail_body),
        )
        return rtnval

    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["plugin-api", "catalog", "auth_provider"],
        stdout=out,
        stderr=err,
        request_opener=_fake_opener,
        profile_loader=lambda name: _build_profile(),
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
    testbase.assert_equal(
        captured_url["url"],
        "https://example.test/api/v1/plugin-api/_meta/catalog/auth_provider",
    )
    testbase.assert_equal('"name": "auth_provider"' in out.getvalue(), True)
    return


def test_plugin_api_catalog_detail_propagates_404():
    """
    **Feature: 8-cli M2 (plugin-api catalog detail)**
    **Property: A 404 from the server maps to EXIT_NOT_FOUND.**
    """

    def _fake_opener(*, request, timeout, context):
        rtnval = RestResponse(
            status_code=404,
            headers={},
            body=None,
            raw_text="not found",
        )
        return rtnval

    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["plugin-api", "catalog", "missing-entry"],
        stdout=out,
        stderr=err,
        request_opener=_fake_opener,
        profile_loader=lambda name: _build_profile(),
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_NOT_FOUND)
    return


def test_plugin_api_catalog_detail_propagates_authentication_error():
    """
    **Feature: 8-cli M2 (plugin-api catalog detail)**
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
        argv=["plugin-api", "catalog"],
        stdout=out,
        stderr=err,
        request_opener=_fake_opener,
        profile_loader=lambda name: _build_profile(),
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_AUTHENTICATION_ERROR)
    return


def test_plugin_api_catalog_does_not_fetch_openapi_document():
    """
    **Feature: 8-cli M2 (plugin-api catalog)**
    **Property: The catalog command bypasses OpenAPI fetch since the
    endpoint is a stable metadata path. The openapi_fetcher seam must
    not be invoked.**
    """

    def _failing_openapi_fetcher():
        raise RuntimeError(
            "OpenAPI fetcher must not be invoked for plugin-api catalog"
        )

    def _fake_opener(*, request, timeout, context):
        rtnval = RestResponse(
            status_code=200,
            headers={},
            body={"factory_protocols": [], "resource_extensions": []},
            raw_text="",
        )
        return rtnval

    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["plugin-api", "catalog"],
        stdout=out,
        stderr=err,
        openapi_fetcher=_failing_openapi_fetcher,
        request_opener=_fake_opener,
        profile_loader=lambda name: _build_profile(),
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
    return


def test_plugin_api_noun_help_lists_catalog_verb():
    """
    **Feature: 8-cli M2 (plugin-api help)**
    **Property: pyc plugin-api --help describes the catalog verbs.**
    """
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["plugin-api", "--help"], stdout=out, stderr=err
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
    testbase.assert_equal("catalog" in out.getvalue(), True)
    return


def test_plugin_api_catalog_verb_help_describes_optional_argument():
    """
    **Feature: 8-cli M2 (plugin-api help)**
    **Property: pyc plugin-api catalog --help calls out the optional
    entry-name argument.**
    """
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["plugin-api", "catalog", "--help"], stdout=out, stderr=err
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
    testbase.assert_equal("[<entry-name>]" in out.getvalue(), True)
    return


def test_top_help_advertises_plugin_api():
    """
    **Feature: 8-cli M2 (top help)**
    **Property: pyc --help mentions the new plugin-api commands.**
    """
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(argv=["--help"], stdout=out, stderr=err)
    testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
    testbase.assert_equal("plugin-api catalog" in out.getvalue(), True)
    return


def test_unknown_noun_still_produces_supported_command_list():
    """
    **Feature: 8-cli M2 (top dispatch)**
    **Property: An unknown noun returns EXIT_USAGE_ERROR with a stderr
    diagnostic that lists every supported (noun, verb) pair.**
    """
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=["bogus-noun", "list"], stdout=out, stderr=err
    )
    testbase.assert_equal(rtnval, exit_codes.EXIT_USAGE_ERROR)
    err_text = err.getvalue()
    testbase.assert_equal("'project list'" in err_text, True)
    testbase.assert_equal("'plugin-api catalog" in err_text, True)
    return
