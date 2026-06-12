"""
.. module:: test_p10f_cli_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 8-cli M1 (skeleton).

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import io
import os
import tempfile

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from ccai import testbase

from ccai.pychestrate.cli import (
    credentials,
    entry,
    exit_codes,
    openapi_cache,
    parser,
    transport,
)
from ccai.pychestrate.cli.exceptions import (
    CredentialsFileNotFoundError,
    CredentialsFilePermissionError,
    OpenApiUnavailableError,
    ProfileNotFoundError,
)
from ccai.pychestrate.cli.models import (
    CliProfile,
    RestOperation,
    RestResponse,
)


SAMPLE_OPENAPI_DOCUMENT: Dict = {
    "openapi": "3.0.0",
    "info": {"title": "Pychestrate", "version": "1.2.3"},
    "paths": {
        "/projects": {
            "get": {
                "operationId": "project_list",
                "parameters": [
                    {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer"}},
                    {"name": "include_archived", "in": "query", "required": True, "schema": {"type": "boolean"}},
                ],
            },
            "post": {"operationId": "project_create"},
        },
        "/projects/{slug}": {
            "get": {
                "operationId": "project_get",
                "parameters": [
                    {"name": "slug", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
            }
        },
        "/internal/diag": {"get": {}},
    },
}


# ---------------------------------------------------------------------------
# Credentials loader (T1.4)
# ---------------------------------------------------------------------------

def _write_credentials_file(*, path: Path, body: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    os.chmod(str(path), mode)
    return


def test_credentials_loader_rejects_missing_file():
    """
    **Feature: 8-cli M1 (T1.4)**
    **Property: A missing credentials file raises
    CredentialsFileNotFoundError.**
    """
    with tempfile.TemporaryDirectory() as tmp_str:
        bogus_path = Path(tmp_str) / "does_not_exist"
        os.environ["PYC_CREDENTIALS_PATH"] = str(bogus_path)
        try:
            raised = False
            try:
                credentials.load_profile(profile_name=None)
            except CredentialsFileNotFoundError:
                raised = True
            testbase.assert_equal(raised, True)
        finally:
            del os.environ["PYC_CREDENTIALS_PATH"]
    return


def test_credentials_loader_rejects_too_permissive_file():
    """
    **Feature: 8-cli M1 (T1.4 / NFR-2)**
    **Property: A credentials file wider than 0600 raises
    CredentialsFilePermissionError.**
    """
    with tempfile.TemporaryDirectory() as tmp_str:
        creds_path = Path(tmp_str) / "credentials"
        body = (
            "[default]\n"
            "server_url = https://example.test\n"
            "bearer_token = token-x\n"
        )
        _write_credentials_file(path=creds_path, body=body, mode=0o644)
        os.environ["PYC_CREDENTIALS_PATH"] = str(creds_path)
        try:
            raised = False
            try:
                credentials.load_profile(profile_name=None)
            except CredentialsFilePermissionError:
                raised = True
            testbase.assert_equal(raised, True)
        finally:
            del os.environ["PYC_CREDENTIALS_PATH"]
    return


def test_credentials_loader_returns_default_profile():
    """
    **Feature: 8-cli M1 (T1.4)**
    **Property: A 0600 credentials file with a [default] section
    yields a populated CliProfile.**
    """
    with tempfile.TemporaryDirectory() as tmp_str:
        creds_path = Path(tmp_str) / "credentials"
        body = (
            "[default]\n"
            "server_url = https://example.test\n"
            "bearer_token = token-default\n"
            "bearer_token_expires_at = 2027-01-01T00:00:00Z\n"
            "verify_tls = true\n"
            "\n"
            "[staging]\n"
            "server_url = https://staging.example.test\n"
            "bearer_token = token-staging\n"
            "verify_tls = false\n"
        )
        _write_credentials_file(path=creds_path, body=body, mode=0o600)
        os.environ["PYC_CREDENTIALS_PATH"] = str(creds_path)
        try:
            profile = credentials.load_profile(profile_name=None)
            testbase.assert_equal(profile.profile_name, "default")
            testbase.assert_equal(profile.server_url, "https://example.test")
            testbase.assert_equal(profile.bearer_token, "token-default")
            testbase.assert_equal(profile.verify_tls, True)
        finally:
            del os.environ["PYC_CREDENTIALS_PATH"]
    return


def test_credentials_loader_honors_named_profile():
    """
    **Feature: 8-cli M1 (T1.4)**
    **Property: --profile selects a non-default section.**
    """
    with tempfile.TemporaryDirectory() as tmp_str:
        creds_path = Path(tmp_str) / "credentials"
        body = (
            "[default]\n"
            "server_url = https://example.test\n"
            "\n"
            "[staging]\n"
            "server_url = https://staging.example.test\n"
            "bearer_token = token-staging\n"
            "verify_tls = false\n"
        )
        _write_credentials_file(path=creds_path, body=body, mode=0o600)
        os.environ["PYC_CREDENTIALS_PATH"] = str(creds_path)
        try:
            profile = credentials.load_profile(profile_name="staging")
            testbase.assert_equal(profile.profile_name, "staging")
            testbase.assert_equal(profile.server_url, "https://staging.example.test")
            testbase.assert_equal(profile.verify_tls, False)
        finally:
            del os.environ["PYC_CREDENTIALS_PATH"]
    return


def test_credentials_loader_rejects_unknown_profile():
    """
    **Feature: 8-cli M1 (T1.4)**
    **Property: An unknown profile name raises ProfileNotFoundError.**
    """
    with tempfile.TemporaryDirectory() as tmp_str:
        creds_path = Path(tmp_str) / "credentials"
        body = "[default]\nserver_url = https://example.test\n"
        _write_credentials_file(path=creds_path, body=body, mode=0o600)
        os.environ["PYC_CREDENTIALS_PATH"] = str(creds_path)
        try:
            raised = False
            try:
                credentials.load_profile(profile_name="missing-profile")
            except ProfileNotFoundError:
                raised = True
            testbase.assert_equal(raised, True)
        finally:
            del os.environ["PYC_CREDENTIALS_PATH"]
    return


def test_credentials_store_token_writes_with_strict_mode():
    """
    **Feature: 8-cli M1 (T1.4)**
    **Property: store_token persists the token and keeps mode 0600.**
    """
    with tempfile.TemporaryDirectory() as tmp_str:
        creds_path = Path(tmp_str) / "credentials"
        os.environ["PYC_CREDENTIALS_PATH"] = str(creds_path)
        try:
            credentials.store_token(
                profile_name="default",
                bearer_token="new-token",
                bearer_token_expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
            )
            mode_bits = creds_path.stat().st_mode & 0o777
            testbase.assert_equal(mode_bits, 0o600)
            text = creds_path.read_text(encoding="utf-8")
            testbase.assert_equal("bearer_token = new-token" in text, True)
        finally:
            del os.environ["PYC_CREDENTIALS_PATH"]
    return


# ---------------------------------------------------------------------------
# OpenAPI cache (T1.2)
# ---------------------------------------------------------------------------

def test_openapi_cache_writes_and_returns_fetched_document():
    """
    **Feature: 8-cli M1 (T1.2)**
    **Property: First fetch populates the cache with the fetched doc.**
    """
    with tempfile.TemporaryDirectory() as tmp_str:
        os.environ["PYC_OPENAPI_CACHE_DIR"] = tmp_str
        try:
            calls = {"count": 0}

            def _fetcher() -> Dict:
                calls["count"] += 1
                rtnval = SAMPLE_OPENAPI_DOCUMENT
                return rtnval

            doc = openapi_cache.load_or_fetch(
                server_url="https://example.test",
                fetch_callable=_fetcher,
            )
            testbase.assert_equal(doc.get("info", {}).get("version", ""), "1.2.3")
            cache_dir = Path(tmp_str)
            cached_files = list(cache_dir.iterdir())
            testbase.assert_equal(len(cached_files), 1)
            testbase.assert_equal(calls["count"], 1)
        finally:
            del os.environ["PYC_OPENAPI_CACHE_DIR"]
    return


def test_openapi_cache_falls_back_to_cache_when_fetch_fails():
    """
    **Feature: 8-cli M1 (T1.2)**
    **Property: A failing fetch returns the previously cached doc.**
    """
    with tempfile.TemporaryDirectory() as tmp_str:
        os.environ["PYC_OPENAPI_CACHE_DIR"] = tmp_str
        try:
            def _good_fetcher() -> Dict:
                rtnval = SAMPLE_OPENAPI_DOCUMENT
                return rtnval

            openapi_cache.load_or_fetch(
                server_url="https://example.test",
                fetch_callable=_good_fetcher,
            )

            def _bad_fetcher() -> Dict:
                raise RuntimeError("network down")

            doc = openapi_cache.load_or_fetch(
                server_url="https://example.test",
                fetch_callable=_bad_fetcher,
            )
            testbase.assert_equal(doc.get("info", {}).get("version", ""), "1.2.3")
        finally:
            del os.environ["PYC_OPENAPI_CACHE_DIR"]
    return


def test_openapi_cache_raises_when_no_cache_and_fetch_fails():
    """
    **Feature: 8-cli M1 (T1.2)**
    **Property: A failing fetch with empty cache raises
    OpenApiUnavailableError.**
    """
    with tempfile.TemporaryDirectory() as tmp_str:
        os.environ["PYC_OPENAPI_CACHE_DIR"] = tmp_str
        try:
            def _bad_fetcher() -> Dict:
                raise RuntimeError("network down")

            raised = False
            try:
                openapi_cache.load_or_fetch(
                    server_url="https://example.test",
                    fetch_callable=_bad_fetcher,
                )
            except OpenApiUnavailableError:
                raised = True
            testbase.assert_equal(raised, True)
        finally:
            del os.environ["PYC_OPENAPI_CACHE_DIR"]
    return


# ---------------------------------------------------------------------------
# Parser (T1.3)
# ---------------------------------------------------------------------------

def test_build_command_tree_collects_documented_operations():
    """
    **Feature: 8-cli M1 (T1.3)**
    **Property: build_command_tree returns one entry per
    convention-matching operationId.**
    """
    tree = parser.build_command_tree(openapi_document=SAMPLE_OPENAPI_DOCUMENT)
    testbase.assert_equal(("project", "list") in tree.commands, True)
    testbase.assert_equal(("project", "create") in tree.commands, True)
    testbase.assert_equal(("project", "get") in tree.commands, True)
    return


def test_build_command_tree_skips_operations_without_operation_id():
    """
    **Feature: 8-cli M1 (T1.3)**
    **Property: An operation without operationId does not produce a
    CommandDescriptor.**
    """
    tree = parser.build_command_tree(openapi_document=SAMPLE_OPENAPI_DOCUMENT)
    diag_commands = [(noun, verb) for (noun, verb) in tree.commands.keys() if "diag" in noun]
    testbase.assert_equal(len(diag_commands), 0)
    return


def test_build_command_tree_captures_path_and_query_params():
    """
    **Feature: 8-cli M1 (T1.3)**
    **Property: Path and query params land on the RestOperation.**
    """
    tree = parser.build_command_tree(openapi_document=SAMPLE_OPENAPI_DOCUMENT)
    project_get_descriptor = tree.commands[("project", "get")]
    testbase.assert_equal(project_get_descriptor.operation.path_param_names, ("slug",))
    testbase.assert_equal(project_get_descriptor.operation.required_path_param_names, ("slug",))

    project_list_descriptor = tree.commands[("project", "list")]
    expected_query = ("limit", "include_archived")
    testbase.assert_equal(project_list_descriptor.operation.query_param_names, expected_query)
    testbase.assert_equal(
        project_list_descriptor.operation.required_query_param_names, ("include_archived",)
    )
    return


def test_lookup_command_returns_none_for_unknown_pair():
    """
    **Feature: 8-cli M1 (T1.3)**
    **Property: lookup_command returns None when the (noun, verb) pair
    is not registered.**
    """
    tree = parser.build_command_tree(openapi_document=SAMPLE_OPENAPI_DOCUMENT)
    rtnval = parser.lookup_command(tree=tree, noun="bogus", verb="list")
    testbase.assert_equal(rtnval, None)
    return


# ---------------------------------------------------------------------------
# Transport (T1.5)
# ---------------------------------------------------------------------------

def test_transport_attaches_bearer_header_and_succeeds_on_200():
    """
    **Feature: 8-cli M1 (T1.5)**
    **Property: Bearer token from the profile is sent as
    'Authorization: Bearer ...'; a 200 response body is decoded.**
    """
    captured = {}

    def _fake_opener(*, request, timeout, context):
        captured["url"] = request.full_url
        captured["headers"] = {k.lower(): v for k, v in request.headers.items()}
        captured["method"] = request.get_method()
        rtnval = RestResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=[{"slug": "alpha"}],
            raw_text='[{"slug":"alpha"}]',
        )
        return rtnval

    profile = CliProfile(
        profile_name="default",
        server_url="https://example.test/",
        bearer_token="token-x",
        bearer_token_expires_at=None,
        mtls_cert_path=None,
        mtls_key_path=None,
        verify_tls=True,
    )
    operation = RestOperation(
        operation_id="project_list",
        method="GET",
        path_template="/api/v1/projects",
    )
    response = transport.execute_request(
        profile=profile,
        operation=operation,
        path_params={},
        query_params={},
        body=None,
        idempotency_key=None,
        timeout_seconds=None,
        opener=_fake_opener,
    )
    testbase.assert_equal(response.status_code, 200)
    testbase.assert_equal(captured["url"], "https://example.test/api/v1/projects")
    testbase.assert_equal(captured["headers"].get("authorization"), "Bearer token-x")
    testbase.assert_equal(captured["method"], "GET")
    return


def test_transport_classifies_authentication_failure():
    """
    **Feature: 8-cli M1 (T1.5)**
    **Property: A 401 response raises AuthenticationError.**
    """

    def _fake_opener(*, request, timeout, context):
        rtnval = RestResponse(
            status_code=401,
            headers={},
            body=None,
            raw_text="not authenticated",
        )
        return rtnval

    profile = CliProfile(
        profile_name="default",
        server_url="https://example.test",
        bearer_token=None,
        bearer_token_expires_at=None,
        mtls_cert_path=None,
        mtls_key_path=None,
        verify_tls=True,
    )
    operation = RestOperation(
        operation_id="project_list",
        method="GET",
        path_template="/api/v1/projects",
    )
    raised = False
    try:
        transport.execute_request(
            profile=profile,
            operation=operation,
            path_params={},
            query_params={},
            body=None,
            idempotency_key=None,
            timeout_seconds=None,
            opener=_fake_opener,
        )
    except Exception as xcpt:
        raised = type(xcpt).__name__ == "AuthenticationError"
    testbase.assert_equal(raised, True)
    return


def test_transport_renders_query_string_and_path_params():
    """
    **Feature: 8-cli M1 (T1.5)**
    **Property: Path and query parameters are correctly substituted /
    encoded into the final URL.**
    """
    captured = {}

    def _fake_opener(*, request, timeout, context):
        captured["url"] = request.full_url
        rtnval = RestResponse(
            status_code=200, headers={}, body={}, raw_text="{}"
        )
        return rtnval

    profile = CliProfile(
        profile_name="default",
        server_url="https://example.test",
        bearer_token=None,
        bearer_token_expires_at=None,
        mtls_cert_path=None,
        mtls_key_path=None,
        verify_tls=True,
    )
    operation = RestOperation(
        operation_id="project_get",
        method="GET",
        path_template="/api/v1/projects/{slug}",
        path_param_names=("slug",),
        required_path_param_names=("slug",),
        query_param_names=("limit",),
    )
    transport.execute_request(
        profile=profile,
        operation=operation,
        path_params={"slug": "alpha pack"},
        query_params={"limit": 10},
        body=None,
        idempotency_key=None,
        timeout_seconds=None,
        opener=_fake_opener,
    )
    testbase.assert_equal(
        captured["url"], "https://example.test/api/v1/projects/alpha%20pack?limit=10"
    )
    return


# ---------------------------------------------------------------------------
# Entry point (T1.6 + T1.7)
# ---------------------------------------------------------------------------

def test_entry_version_prints_banner_offline():
    """
    **Feature: 8-cli M1 (T1.6)**
    **Property: pyc --version prints the CLI version with no network.**
    """
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(argv=["--version"], stdout=out, stderr=err)
    testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
    testbase.assert_equal(out.getvalue().startswith("pyc"), True)
    return


def test_entry_top_help_prints_usage():
    """
    **Feature: 8-cli M1 (T1.6)**
    **Property: pyc --help and pyc with no args print the top help.**
    """
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(argv=["--help"], stdout=out, stderr=err)
    testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
    testbase.assert_equal("usage: pyc" in out.getvalue(), True)
    return


def test_entry_unknown_noun_returns_usage_error():
    """
    **Feature: 8-cli M1 (T1.6)**
    **Property: A noun other than 'project' returns EXIT_USAGE_ERROR
    with a stable diagnostic.**
    """
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(argv=["bogus", "list"], stdout=out, stderr=err)
    testbase.assert_equal(rtnval, exit_codes.EXIT_USAGE_ERROR)
    return


def test_entry_project_list_drives_full_path():
    """
    **Feature: 8-cli M1 (T1.7)**
    **Property: pyc project list loads a profile, fetches the OpenAPI,
    drives the request, and emits the JSON body to stdout.**
    """
    profile = CliProfile(
        profile_name="default",
        server_url="https://example.test",
        bearer_token="token-x",
        bearer_token_expires_at=None,
        mtls_cert_path=None,
        mtls_key_path=None,
        verify_tls=True,
    )

    def _profile_loader(name):
        rtnval = profile
        return rtnval

    def _openapi_fetcher() -> Dict:
        rtnval = SAMPLE_OPENAPI_DOCUMENT
        return rtnval

    def _request_opener(*, request, timeout, context):
        rtnval = RestResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=[{"slug": "alpha"}, {"slug": "beta"}],
            raw_text='[{"slug":"alpha"},{"slug":"beta"}]',
        )
        return rtnval

    with tempfile.TemporaryDirectory() as tmp_str:
        os.environ["PYC_OPENAPI_CACHE_DIR"] = tmp_str
        try:
            out = io.StringIO()
            err = io.StringIO()
            rtnval = entry.main(
                argv=["project", "list"],
                stdout=out,
                stderr=err,
                openapi_fetcher=_openapi_fetcher,
                request_opener=_request_opener,
                profile_loader=_profile_loader,
            )
            testbase.assert_equal(rtnval, exit_codes.EXIT_OK)
            testbase.assert_equal('"slug": "alpha"' in out.getvalue(), True)
            testbase.assert_equal('"slug": "beta"' in out.getvalue(), True)
        finally:
            del os.environ["PYC_OPENAPI_CACHE_DIR"]
    return


def test_entry_project_list_returns_credentials_exit_code_on_missing_file():
    """
    **Feature: 8-cli M1 (T1.6)**
    **Property: A missing credentials file maps to EXIT 13.**
    """
    with tempfile.TemporaryDirectory() as tmp_str:
        os.environ["PYC_CREDENTIALS_PATH"] = str(Path(tmp_str) / "missing")
        os.environ["PYC_OPENAPI_CACHE_DIR"] = tmp_str
        try:
            out = io.StringIO()
            err = io.StringIO()
            rtnval = entry.main(
                argv=["project", "list"],
                stdout=out,
                stderr=err,
            )
            testbase.assert_equal(rtnval, exit_codes.EXIT_CREDENTIALS_PERMISSIONS_ERROR)
        finally:
            del os.environ["PYC_CREDENTIALS_PATH"]
            del os.environ["PYC_OPENAPI_CACHE_DIR"]
    return
