"""
.. module:: test_p26c_pyc_cli_m2
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the working ``pyc`` CLI (audit findings CLI-01,
               ORG-F16, CLI-02, CLI-03, CLI-04).

.. moduleauthor:: Code Craft AI LLC

Before these changes no ``pyc`` command could succeed against a live
server: the OpenAPI fetch hit a route that did not exist and the
fallback never ran, the only credential it could send was one nothing
accepted, there was no ``login`` or configuration command, network
failures printed tracebacks, and redirects to the sign-in page were
followed and printed as success.

Every test runs hermetically: HOME-independent paths come from an
injected environment (``XDG_CONFIG_HOME`` / ``XDG_CACHE_HOME`` /
``PYC_OPENAPI_CACHE_DIR`` under a temporary directory) and HTTP goes
either through a fake opener or to a throw-away ``http.server`` on
127.0.0.1.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import http.server
import io
import json
import os
import socket
import stat
import sys
import tempfile
import threading
import time

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai import testbase

from ccai.pychestrate.cli import (
    credentials,
    entry,
    exit_codes,
    parser,
    paths,
    transport,
)
from ccai.pychestrate.cli.exceptions import (
    BadRequestError,
    PermissionDeniedError,
    UnexpectedResponseError,
)
from ccai.pychestrate.cli.models import CliProfile, RestResponse


SERVER = "https://pyc.example.test"
TOKEN = "pyc_" + "T" * 43

SPEC_DOCUMENT: Dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Pychestrate", "version": "9.9.9"},
    "servers": [{"url": "https://{host}/api/v1"}],
    "components": {
        "parameters": {
            "SlugParam": {"name": "slug", "in": "path", "required": True, "schema": {"type": "string"}},
        },
    },
    "paths": {
        "/projects": {
            "get": {
                "operationId": "projects_list", "tags": ["projects"], "summary": "List projects.",
                "parameters": [
                    {"name": "per_page", "in": "query", "schema": {"type": "integer"}},
                    {"name": "state", "in": "query", "schema": {"type": "string"}},
                ],
            },
            "post": {
                "operationId": "projects_create", "tags": ["projects"], "summary": "Create a project.",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
            },
        },
        "/projects/{slug}": {
            "parameters": [{"$ref": "#/components/parameters/SlugParam"}],
            "get": {"operationId": "projects_get_by_slug", "tags": ["projects"], "summary": "Read a project."},
        },
        "/resource-pools/{pool_id}/reservations": {
            "post": {
                "operationId": "resource_pools_create_reservation", "tags": ["resource_pools"],
                "parameters": [{"name": "pool_id", "in": "path", "required": True}],
                "requestBody": {"required": True},
            },
        },
        "/projects/{project_id}/test-runs": {
            "post": {
                "operationId": "test_runs_trigger", "tags": ["test_runs"],
                "parameters": [{"name": "project_id", "in": "path", "required": True}],
                "requestBody": {"required": True},
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class _Sandbox:
    """
        A temporary directory holding the XDG config / cache homes and
        the environment that points ``pyc`` at them.
    """

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.environ: Dict[str, str] = {
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_CACHE_HOME": str(self.root / "cache"),
        }
        self._saved_cache_dir = os.environ.get("PYC_OPENAPI_CACHE_DIR", None)
        os.environ["PYC_OPENAPI_CACHE_DIR"] = str(self.root / "cache" / "openapi")
        return

    @property
    def credentials_path(self) -> Path:
        rtnval = self.root / "config" / "pychestrate" / "credentials"
        return rtnval

    def write_credentials(self, text: str, mode: int = 0o600) -> None:
        self.credentials_path.parent.mkdir(parents=True, exist_ok=True)
        self.credentials_path.write_text(text, encoding="utf-8")
        os.chmod(str(self.credentials_path), mode)
        return

    def close(self) -> None:
        if self._saved_cache_dir is None:
            os.environ.pop("PYC_OPENAPI_CACHE_DIR", None)
        else:
            os.environ["PYC_OPENAPI_CACHE_DIR"] = self._saved_cache_dir
        self._tmp.cleanup()
        return


class _FakeServer:
    """
        Fake opener: answers by ``(method, path)`` and records every
        request.
    """

    def __init__(self, routes: Optional[Dict[Tuple[str, str], Any]] = None) -> None:
        self.routes: Dict[Tuple[str, str], Any] = dict(routes or {})
        self.requests: List[Dict[str, Any]] = []
        return

    def __call__(self, *, request, timeout, context) -> RestResponse:
        from urllib.parse import urlsplit  # noqa: E402

        parts = urlsplit(request.full_url)
        body = request.data.decode("utf-8") if request.data else None
        self.requests.append({
            "method": request.get_method(),
            "url": request.full_url,
            "path": parts.path,
            "query": parts.query,
            "headers": {k.lower(): v for k, v in request.header_items()},
            "body": json.loads(body) if body else None,
        })
        answer = self.routes.get((request.get_method(), parts.path), None)
        if callable(answer):
            answer = answer()
        if answer is None:
            return RestResponse(status_code=404, headers={"content-type": "application/problem+json"},
                                body=None, raw_text='{"title": "Not Found", "detail": "no route", "status": 404}')
        if isinstance(answer, RestResponse):
            return answer
        return RestResponse(status_code=200, headers={"content-type": "application/json"},
                            body=answer, raw_text=json.dumps(answer))


def _run(
        *,
        sandbox: _Sandbox,
        argv: List[str],
        opener: Any = None,
        environ: Optional[Dict[str, str]] = None,
        stdin_text: str = "",
        openapi_fetcher: Optional[Callable[[], Dict]] = None,
        sleep: Optional[Callable[[float], None]] = None
    ) -> Tuple[int, str, str]:
    """
        Run ``pyc`` in-process with the sandbox environment.
    """
    env = dict(sandbox.environ)
    env.update(environ or {})
    out = io.StringIO()
    err = io.StringIO()
    rtnval = entry.main(
        argv=argv, stdout=out, stderr=err, stdin=io.StringIO(stdin_text),
        environ=env, request_opener=opener, openapi_fetcher=openapi_fetcher,
        sleep=sleep if sleep is not None else (lambda seconds: None),
    )
    return rtnval, out.getvalue(), err.getvalue()


def _logged_in(sandbox: _Sandbox, *, extra: str = "") -> None:
    sandbox.write_credentials(
        "[default]\nserver_url = {}\nbearer_token = {}\n{}".format(SERVER, TOKEN, extra)
    )
    return


def _spec_fetcher() -> Dict:
    return SPEC_DOCUMENT


def _profile(server_url: str = SERVER) -> CliProfile:
    rtnval = CliProfile(
        profile_name="default", server_url=server_url, bearer_token=TOKEN,
        bearer_token_expires_at=None, mtls_cert_path=None, mtls_key_path=None,
        verify_tls=True,
    )
    return rtnval


class _LocalHttpServer:
    """
        A throw-away HTTP server on 127.0.0.1 answering every request
        with ``status`` / ``headers`` / ``body`` after ``delay``.
    """

    def __init__(self, *, status: int, headers: Dict[str, str], body: bytes, delay: float = 0.0) -> None:
        outer = self
        self.hits: List[str] = []

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                outer.hits.append(self.path)
                time.sleep(delay)
                try:
                    self.send_response(status)
                    for key, value in headers.items():
                        self.send_header(key, value)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):  # noqa: D401
                return

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.daemon_threads = True
        self.url = "http://127.0.0.1:{}".format(self._server.server_address[1])
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        return


def _closed_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


# ===========================================================================
# CLI-01 / ORG-F16: commands work against a live server
# ===========================================================================


def test_project_list_runs_when_the_openapi_document_is_unavailable():
    """
    **Feature: pyc (CLI-01)**
    **Property: when the server cannot provide an OpenAPI document (404)
    and nothing is cached, 'pyc project list' still sends
    GET /api/v1/projects and prints the answer (it used to exit 7
    before sending anything).**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox)
        server = _FakeServer({("GET", "/api/v1/projects"): {"items": [{"slug": "alpha"}]}})
        rc, out, _err = _run(sandbox=sandbox, argv=["project", "list"], opener=server)
        testbase.assert_equal(
            (rc, [r["path"] for r in server.requests], '"slug": "alpha"' in out),
            (exit_codes.EXIT_OK, ["/api/v1/_meta/openapi.json", "/api/v1/projects"], True),
        )
    finally:
        sandbox.close()
    return


def test_requests_carry_the_api_token_as_a_bearer_header():
    """
    **Feature: pyc (CLI-01 / ORG-F02)**
    **Property: every request sends the stored token as
    'Authorization: Bearer pyc_...'.**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox)
        server = _FakeServer({("GET", "/api/v1/projects"): {"items": []}})
        _run(sandbox=sandbox, argv=["projects", "list"], opener=server, openapi_fetcher=_spec_fetcher)
        testbase.assert_equal(server.requests[-1]["headers"].get("authorization"), "Bearer " + TOKEN)
    finally:
        sandbox.close()
    return


def test_generated_command_maps_path_query_and_body_arguments():
    """
    **Feature: pyc (ORG-F16)**
    **Property: a generated command takes path parameters as
    positionals and query parameters as --flags (underscore or hyphen),
    and builds the JSON body from --set with typed, dotted values.**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox)
        server = _FakeServer({("POST", "/api/v1/resource-pools/p-7/reservations"): {"reservation_id": "r-1"}})
        rc, _out, err = _run(
            sandbox=sandbox,
            argv=["resource-pools", "create-reservation", "p-7",
                  "--set", "count=2", "--set", "holder.name=ci", "--set", "exclusive=true"],
            opener=server, openapi_fetcher=_spec_fetcher,
        )
        testbase.assert_equal(
            (rc, server.requests[-1]["body"], err),
            (exit_codes.EXIT_OK, {"count": 2, "holder": {"name": "ci"}, "exclusive": True}, ""),
        )
    finally:
        sandbox.close()
    return


def test_query_flags_accept_hyphen_spelling():
    """
    **Feature: pyc (ORG-F16)**
    **Property: --per-page and --per_page both set the per_page query
    parameter.**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox)
        server = _FakeServer({("GET", "/api/v1/projects"): {"items": []}})
        _run(sandbox=sandbox, argv=["projects", "list", "--per-page", "5"], opener=server,
             openapi_fetcher=_spec_fetcher)
        _run(sandbox=sandbox, argv=["projects", "list", "--per_page", "6"], opener=server,
             openapi_fetcher=_spec_fetcher)
        queries = [r["query"] for r in server.requests if r["path"] == "/api/v1/projects"]
        testbase.assert_equal(queries, ["per_page=5", "per_page=6"])
    finally:
        sandbox.close()
    return


def test_data_argument_reads_a_file():
    """
    **Feature: pyc (ORG-F16)**
    **Property: --data @FILE sends the file's JSON as the body.**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox)
        body_file = sandbox.root / "body.json"
        body_file.write_text('{"slug": "from-file"}', encoding="utf-8")
        server = _FakeServer({("POST", "/api/v1/projects"): {"slug": "from-file"}})
        _run(sandbox=sandbox, argv=["projects", "create", "--data", "@" + str(body_file)],
             opener=server, openapi_fetcher=_spec_fetcher)
        testbase.assert_equal(server.requests[-1]["body"], {"slug": "from-file"})
    finally:
        sandbox.close()
    return


def test_data_argument_reads_stdin():
    """
    **Feature: pyc (ORG-F16)**
    **Property: --data - sends standard input's JSON as the body.**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox)
        server = _FakeServer({("POST", "/api/v1/projects"): {"slug": "piped"}})
        _run(sandbox=sandbox, argv=["projects", "create", "--data", "-"], opener=server,
             openapi_fetcher=_spec_fetcher, stdin_text='{"slug": "piped"}')
        testbase.assert_equal(server.requests[-1]["body"], {"slug": "piped"})
    finally:
        sandbox.close()
    return


def test_invalid_data_is_a_usage_error():
    """
    **Feature: pyc (CLI-03)**
    **Property: --data that is not JSON exits 2 without sending the
    command's request.**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox)
        server = _FakeServer({("POST", "/api/v1/projects"): {}})
        rc, _out, err = _run(sandbox=sandbox, argv=["projects", "create", "--data", "{oops"],
                             opener=server, openapi_fetcher=_spec_fetcher)
        testbase.assert_equal(
            (rc, "not valid JSON" in err, [r["method"] for r in server.requests]),
            (exit_codes.EXIT_USAGE_ERROR, True, []),
        )
    finally:
        sandbox.close()
    return


def test_unknown_verb_lists_the_nouns_verbs():
    """
    **Feature: pyc (ORG-F16)**
    **Property: an unknown verb exits 2 and lists the verbs the noun
    has.**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox)
        rc, _out, err = _run(sandbox=sandbox, argv=["projects", "frobnicate"], opener=_FakeServer(),
                             openapi_fetcher=_spec_fetcher)
        testbase.assert_equal(
            (rc, "create, get, list" in err), (exit_codes.EXIT_USAGE_ERROR, True)
        )
    finally:
        sandbox.close()
    return


def test_commands_lists_every_generated_command():
    """
    **Feature: pyc (ORG-F16)**
    **Property: 'pyc commands' lists the server's commands grouped by
    noun with method and path.**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox)
        rc, out, _err = _run(sandbox=sandbox, argv=["commands"], opener=_FakeServer(),
                             openapi_fetcher=_spec_fetcher)
        testbase.assert_equal(
            (rc, "resource-pools:" in out, "  get " in out, "/api/v1/projects/{slug}" in out),
            (exit_codes.EXIT_OK, True, True, True),
        )
    finally:
        sandbox.close()
    return


def test_fresh_cached_document_needs_no_fetch():
    """
    **Feature: pyc (CLI-01)**
    **Property: after one successful fetch, the next command uses the
    cached document without asking the server for it again.**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox)
        server = _FakeServer({
            ("GET", "/api/v1/_meta/openapi.json"): SPEC_DOCUMENT,
            ("GET", "/api/v1/projects"): {"items": []},
        })
        _run(sandbox=sandbox, argv=["projects", "list"], opener=server)
        _run(sandbox=sandbox, argv=["projects", "list"], opener=server)
        fetches = [r for r in server.requests if r["path"] == "/api/v1/_meta/openapi.json"]
        testbase.assert_equal(len(fetches), 1)
    finally:
        sandbox.close()
    return


def test_console_script_entry_point_exits_with_the_command_code():
    """
    **Feature: pyc (ORG-F16)**
    **Property: console_main (the 'pyc' console script) runs main on
    sys.argv and exits with its code.**
    """
    saved_argv = sys.argv
    sys.argv = ["pyc", "--version"]
    try:
        code = None
        try:
            entry.console_main()
        except SystemExit as xcpt:
            code = xcpt.code
        testbase.assert_equal(code, exit_codes.EXIT_OK)
    finally:
        sys.argv = saved_argv
    return


# ===========================================================================
# Parser
# ===========================================================================


def test_nouns_come_from_tags_and_verbs_drop_the_tag_prefix():
    """
    **Feature: pyc (ORG-F16)**
    **Property: operationId resource_pools_create_reservation tagged
    resource_pools becomes 'resource-pools create-reservation'.**
    """
    tree = parser.build_command_tree(openapi_document=SPEC_DOCUMENT)
    testbase.assert_equal(("resource-pools", "create-reservation") in tree.commands, True)
    return


def test_paths_are_prefixed_with_the_servers_base_path():
    """
    **Feature: pyc (CLI-01)**
    **Property: paths are resolved against the document's servers URL
    (a templated https://{host}/api/v1 yields /api/v1).**
    """
    tree = parser.build_command_tree(openapi_document=SPEC_DOCUMENT)
    testbase.assert_equal(
        tree.commands[("projects", "get")].operation.path_template,
        "/api/v1/projects/{slug}",
    )
    return


def test_shared_path_item_parameters_are_resolved():
    """
    **Feature: pyc (ORG-F16)**
    **Property: parameters declared on the path item (and $ref'd from
    components) become the command's positionals.**
    """
    tree = parser.build_command_tree(openapi_document=SPEC_DOCUMENT)
    testbase.assert_equal(
        tree.commands[("projects", "get")].operation.path_param_names, ("slug",)
    )
    return


def test_singular_noun_and_underscored_verb_resolve():
    """
    **Feature: pyc (ORG-F16)**
    **Property: 'project get_by_slug' (the derived spelling) finds
    'projects get'.**
    """
    tree = parser.build_command_tree(openapi_document=SPEC_DOCUMENT)
    descriptor = parser.lookup_command(tree=tree, noun="project", verb="get_by_slug")
    testbase.assert_equal(descriptor.operation.operation_id, "projects_get_by_slug")
    return


def test_every_operation_of_the_real_contract_becomes_a_distinct_command():
    """
    **Feature: pyc (ORG-F16)**
    **Property: the command tree built from specs/openapi/pychestrate.yaml
    has one command per operation -- no two operations collapse onto
    the same noun/verb.**
    """
    import yaml  # noqa: E402

    here = Path(__file__).resolve()
    root = here
    while not (root / "specs").is_dir() and root.parent != root:
        root = root.parent
    with open(root / "specs" / "openapi" / "pychestrate.yaml", "r", encoding="utf-8") as fh:
        document = yaml.safe_load(fh)
    operation_ids = []
    for path_item in document["paths"].values():
        for method, operation in path_item.items():
            if method in parser.HTTP_METHODS and isinstance(operation, dict) and operation.get("operationId"):
                operation_ids.append(operation["operationId"])
    tree = parser.build_command_tree(openapi_document=document)
    testbase.assert_equal(len(tree.commands), len(operation_ids))
    return


# ===========================================================================
# CLI-02: first run, login, configuration
# ===========================================================================


def test_first_run_without_configuration_explains_how_to_start():
    """
    **Feature: pyc (CLI-02)**
    **Property: with no credentials file and no server URL, a command
    exits 13 and prints the pyc login command and an example
    profile.**
    """
    sandbox = _Sandbox()
    try:
        rc, _out, err = _run(sandbox=sandbox, argv=["project", "list"])
        testbase.assert_equal(
            (rc, "pyc login --server-url" in err, "[default]" in err, "PYC_TOKEN" in err),
            (exit_codes.EXIT_CREDENTIALS_ERROR, True, True, True),
        )
    finally:
        sandbox.close()
    return


def test_environment_alone_configures_pyc():
    """
    **Feature: pyc (CLI-02)**
    **Property: PYC_SERVER_URL and PYC_TOKEN work without any
    credentials file.**
    """
    sandbox = _Sandbox()
    try:
        server = _FakeServer({("GET", "/api/v1/projects"): {"items": []}})
        rc, _out, _err = _run(
            sandbox=sandbox, argv=["projects", "list"], opener=server,
            openapi_fetcher=_spec_fetcher,
            environ={"PYC_SERVER_URL": SERVER, "PYC_TOKEN": TOKEN},
        )
        testbase.assert_equal(
            (rc, server.requests[-1]["url"], server.requests[-1]["headers"].get("authorization")),
            (exit_codes.EXIT_OK, SERVER + "/api/v1/projects", "Bearer " + TOKEN),
        )
    finally:
        sandbox.close()
    return


def test_server_url_flag_works_without_a_credentials_file():
    """
    **Feature: pyc (CLI-02)**
    **Property: --server-url alone (no file) is enough to send a
    request.**
    """
    sandbox = _Sandbox()
    try:
        server = _FakeServer({("GET", "/api/v1/projects"): {"items": []}})
        rc, _out, _err = _run(sandbox=sandbox, argv=["projects", "list", "--server-url", SERVER],
                              opener=server, openapi_fetcher=_spec_fetcher)
        testbase.assert_equal((rc, server.requests[-1]["url"]), (exit_codes.EXIT_OK, SERVER + "/api/v1/projects"))
    finally:
        sandbox.close()
    return


def _me_answer() -> Dict[str, Any]:
    rtnval = {
        "user_id": "u-1", "login_name": "dana", "display_name": "Dana", "account_kind": "user",
        "authentication": {
            "method": "api_token", "token_id": "t-1", "token_name": "laptop",
            "token_scope": "read-write", "token_expires_at": "2026-12-22T00:00:00+00:00",
        },
    }
    return rtnval


def test_login_with_token_on_stdin_writes_a_private_profile():
    """
    **Feature: pyc (CLI-02)**
    **Property: 'pyc login --server-url URL --with-token' verifies the
    token against /api/v1/me and stores server_url, token, and expiry
    in the XDG credentials file with mode 0600.**
    """
    sandbox = _Sandbox()
    try:
        server = _FakeServer({("GET", "/api/v1/me"): _me_answer()})
        rc, out, _err = _run(sandbox=sandbox, argv=["login", "--server-url", SERVER, "--with-token"],
                             opener=server, stdin_text=TOKEN + "\n")
        profile = credentials.load_profile(profile_name=None, environ=sandbox.environ)
        mode = stat.S_IMODE(sandbox.credentials_path.stat().st_mode)
        testbase.assert_equal(
            (rc, profile.server_url, profile.bearer_token, profile.bearer_token_expires_at.year, mode,
             "Logged in to" in out),
            (exit_codes.EXIT_OK, SERVER, TOKEN, 2026, 0o600, True),
        )
    finally:
        sandbox.close()
    return


def test_login_rejects_a_value_that_is_not_an_api_token():
    """
    **Feature: pyc (CLI-02)**
    **Property: pasting something that is not a pyc_ token (a password,
    a session cookie) exits 2 and writes nothing.**
    """
    sandbox = _Sandbox()
    try:
        rc, _out, err = _run(sandbox=sandbox, argv=["login", "--server-url", SERVER, "--with-token"],
                             opener=_FakeServer(), stdin_text="correct-horse-battery\n")
        testbase.assert_equal(
            (rc, "not a Pychestrate API token" in err, sandbox.credentials_path.exists()),
            (exit_codes.EXIT_USAGE_ERROR, True, False),
        )
    finally:
        sandbox.close()
    return


def test_login_with_a_rejected_token_saves_nothing():
    """
    **Feature: pyc (CLI-02)**
    **Property: when /api/v1/me answers 401 the login exits 3 and no
    credentials file is written.**
    """
    sandbox = _Sandbox()
    try:
        server = _FakeServer({("GET", "/api/v1/me"): RestResponse(
            status_code=401, headers={"content-type": "application/problem+json"}, body=None,
            raw_text='{"title": "Unauthenticated", "detail": "The API token is invalid, expired, or revoked.", "status": 401}',
        )})
        rc, _out, err = _run(sandbox=sandbox, argv=["login", "--server-url", SERVER, "--with-token"],
                             opener=server, stdin_text=TOKEN + "\n")
        testbase.assert_equal(
            (rc, "nothing was saved" in err, sandbox.credentials_path.exists()),
            (exit_codes.EXIT_AUTHENTICATION_ERROR, True, False),
        )
    finally:
        sandbox.close()
    return


def test_logout_removes_the_stored_token():
    """
    **Feature: pyc (CLI-02)**
    **Property: 'pyc logout' deletes the token from the profile and
    keeps the server URL.**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox)
        rc, _out, _err = _run(sandbox=sandbox, argv=["logout"])
        profile = credentials.load_profile(profile_name=None, environ=sandbox.environ)
        testbase.assert_equal((rc, profile.bearer_token, profile.server_url), (exit_codes.EXIT_OK, None, SERVER))
    finally:
        sandbox.close()
    return


def test_whoami_reports_the_token_identity():
    """
    **Feature: pyc (CLI-02)**
    **Property: 'pyc whoami' prints the account and the token's name.**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox)
        rc, out, _err = _run(sandbox=sandbox, argv=["whoami"],
                             opener=_FakeServer({("GET", "/api/v1/me"): _me_answer()}))
        testbase.assert_equal((rc, "dana" in out, "API token 'laptop'" in out), (exit_codes.EXIT_OK, True, True))
    finally:
        sandbox.close()
    return


def test_config_set_and_get_round_trip():
    """
    **Feature: pyc (CLI-02)**
    **Property: 'pyc config set server_url' stores a normalized URL
    that 'pyc config get' prints.**
    """
    sandbox = _Sandbox()
    try:
        _run(sandbox=sandbox, argv=["config", "set", "server_url", "https://pyc.example.test/api/v1/"])
        rc, out, _err = _run(sandbox=sandbox, argv=["config", "get", "server_url"])
        testbase.assert_equal((rc, out.strip()), (exit_codes.EXIT_OK, "https://pyc.example.test"))
    finally:
        sandbox.close()
    return


def test_config_get_masks_the_token():
    """
    **Feature: pyc (CLI-02)**
    **Property: 'pyc config get bearer_token' shows only the token's
    first characters.**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox)
        _rc, out, _err = _run(sandbox=sandbox, argv=["config", "get", "bearer_token"])
        testbase.assert_equal((TOKEN in out, out.strip()), (False, TOKEN[:10] + "..."))
    finally:
        sandbox.close()
    return


def test_config_set_refuses_the_token():
    """
    **Feature: pyc (CLI-02)**
    **Property: the token cannot be set with 'pyc config set' (it would
    land in shell history); the command exits 2.**
    """
    sandbox = _Sandbox()
    try:
        rc, _out, _err = _run(sandbox=sandbox, argv=["config", "set", "bearer_token", TOKEN])
        testbase.assert_equal(rc, exit_codes.EXIT_USAGE_ERROR)
    finally:
        sandbox.close()
    return


def test_config_profiles_marks_the_active_profile():
    """
    **Feature: pyc (CLI-02)**
    **Property: 'pyc config profiles' lists every profile and stars
    the active one.**
    """
    sandbox = _Sandbox()
    try:
        sandbox.write_credentials(
            "[default]\nserver_url = {}\n\n[staging]\nserver_url = https://staging.test\n".format(SERVER)
        )
        _rc, out, _err = _run(sandbox=sandbox, argv=["--profile", "staging", "config", "profiles"])
        lines = [line for line in out.splitlines() if "staging.test" in line]
        testbase.assert_equal(lines[0].startswith("* staging"), True)
    finally:
        sandbox.close()
    return


def test_disabled_tls_verification_is_warned_about():
    """
    **Feature: pyc (CLI-02)**
    **Property: a profile with verify_tls = false prints a warning on
    stderr for every command.**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox, extra="verify_tls = false\n")
        _rc, _out, err = _run(sandbox=sandbox, argv=["projects", "list"],
                              opener=_FakeServer({("GET", "/api/v1/projects"): {}}),
                              openapi_fetcher=_spec_fetcher)
        testbase.assert_equal("TLS certificate verification is disabled" in err, True)
    finally:
        sandbox.close()
    return


def test_credentials_are_read_from_the_xdg_config_home():
    """
    **Feature: pyc (CLI-02)**
    **Property: the credentials path is $XDG_CONFIG_HOME/pychestrate/
    credentials, not ~/.pychestrate (which the service shares).**
    """
    environ = {"XDG_CONFIG_HOME": "/xdg/config"}
    testbase.assert_equal(
        str(paths.xdg_credentials_path(environ=environ)), "/xdg/config/pychestrate/credentials"
    )
    return


def test_legacy_credentials_file_is_still_read():
    """
    **Feature: pyc (CLI-02)**
    **Property: when only the pre-XDG ~/.pychestrate/credentials exists,
    it is still used.**
    """
    with tempfile.TemporaryDirectory() as home:
        legacy = Path(home) / ".pychestrate" / "credentials"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("[default]\nserver_url = https://legacy.test\n", encoding="utf-8")
        os.chmod(str(legacy), 0o600)
        saved_home = os.environ.get("HOME", None)
        os.environ["HOME"] = home
        try:
            resolved = paths.resolve_credentials_path(environ={"XDG_CONFIG_HOME": str(Path(home) / "cfg")})
        finally:
            if saved_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = saved_home
        testbase.assert_equal(resolved, legacy)
    return


# ===========================================================================
# CLI-03: errors and exit codes
# ===========================================================================


def test_corrupt_credentials_file_is_a_configuration_error():
    """
    **Feature: pyc (CLI-03)**
    **Property: a credentials file that is not INI exits 13 with a
    message naming the file (it used to be exit 7 "unexpected
    exception").**
    """
    sandbox = _Sandbox()
    try:
        sandbox.write_credentials("this is not ini\n")
        rc, _out, err = _run(sandbox=sandbox, argv=["projects", "list"])
        testbase.assert_equal(
            (rc, "not a valid profile file" in err), (exit_codes.EXIT_CREDENTIALS_ERROR, True)
        )
    finally:
        sandbox.close()
    return


def test_connection_refused_is_reported_without_a_traceback():
    """
    **Feature: pyc (CLI-03)**
    **Property: a closed port exits 8 with one 'cannot reach' line and
    no traceback.**
    """
    sandbox = _Sandbox()
    try:
        url = "http://127.0.0.1:{}".format(_closed_port())
        rc, _out, err = _run(sandbox=sandbox, argv=["projects", "list", "--server-url", url])
        testbase.assert_equal(
            (rc, "cannot reach {}".format(url) in err, "Traceback" in err, "connection refused" in err),
            (exit_codes.EXIT_CONNECTION_ERROR, True, False, True),
        )
    finally:
        sandbox.close()
    return


def test_invalid_server_url_is_reported_without_a_traceback():
    """
    **Feature: pyc (CLI-03)**
    **Property: a server URL that is not http(s)://host exits 8 with an
    'invalid server URL' line.**
    """
    sandbox = _Sandbox()
    try:
        rc, _out, err = _run(sandbox=sandbox, argv=["plugin-api", "catalog", "--server-url", "not-a-url"])
        testbase.assert_equal(
            (rc, "invalid server URL" in err, "Traceback" in err),
            (exit_codes.EXIT_CONNECTION_ERROR, True, False),
        )
    finally:
        sandbox.close()
    return


def test_timeout_flag_bounds_a_slow_server():
    """
    **Feature: pyc (CLI-03)**
    **Property: --timeout makes a request to a server that does not
    answer in time exit 8 ('timed out').**
    """
    sandbox = _Sandbox()
    slow = _LocalHttpServer(status=200, headers={"Content-Type": "application/json"}, body=b"{}", delay=2.0)
    try:
        rc, _out, err = _run(sandbox=sandbox, argv=["--timeout", "0.3", "plugin-api", "catalog",
                                                    "--server-url", slow.url])
        testbase.assert_equal((rc, "timed out" in err), (exit_codes.EXIT_CONNECTION_ERROR, True))
    finally:
        slow.close()
        sandbox.close()
    return


def test_bad_request_answers_are_usage_errors():
    """
    **Feature: pyc (CLI-03)**
    **Property: 400 and 422 map to exit 2 (usage), not 7 (server
    error).**
    """
    outcomes = []
    for status in (400, 422):
        try:
            transport._classify_status(status_code=status, response_text="{}", headers={})
            outcomes.append(None)
        except BadRequestError:
            outcomes.append("BadRequestError")
    testbase.assert_equal(outcomes, ["BadRequestError", "BadRequestError"])
    return


def test_forbidden_is_a_permission_error_naming_the_permission():
    """
    **Feature: pyc (CLI-03)**
    **Property: a 403 problem document renders as 'title: detail
    (requires <permission>) (HTTP 403)'.**
    """
    body = json.dumps({"title": "Forbidden", "detail": "Permission denied: system:projects.read",
                       "status": 403, "required_permission": "system:projects.read"})
    message = None
    try:
        transport._classify_status(status_code=403, response_text=body, headers={})
    except PermissionDeniedError as xcpt:
        message = str(xcpt)
    testbase.assert_equal(
        message,
        "Forbidden: Permission denied: system:projects.read (requires system:projects.read) (HTTP 403)",
    )
    return


def test_trailing_api_prefix_on_the_server_url_is_not_doubled():
    """
    **Feature: pyc (CLI-03)**
    **Property: a server_url ending in /api/v1 is trimmed (with a note)
    instead of requesting /api/v1/api/v1/...**
    """
    sandbox = _Sandbox()
    try:
        server = _FakeServer({("GET", "/api/v1/projects"): {"items": []}})
        rc, _out, err = _run(sandbox=sandbox, argv=["projects", "list", "--server-url", SERVER + "/api/v1"],
                             opener=server, openapi_fetcher=_spec_fetcher)
        testbase.assert_equal(
            (rc, server.requests[-1]["url"], "ends with /api/v1" in err),
            (exit_codes.EXIT_OK, SERVER + "/api/v1/projects", True),
        )
    finally:
        sandbox.close()
    return


def test_unexpected_failure_is_one_line_not_a_traceback():
    """
    **Feature: pyc (CLI-03)**
    **Property: an unexpected exception inside pyc prints one 'internal
    error' line and exits 7.**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox)

        def _explode(*, request, timeout, context):
            raise RuntimeError("boom")

        rc, _out, err = _run(sandbox=sandbox, argv=["plugin-api", "catalog"], opener=_explode)
        testbase.assert_equal(
            (rc, "internal error in pyc: RuntimeError: boom" in err, "Traceback" in err),
            (exit_codes.EXIT_SERVER_ERROR, True, False),
        )
    finally:
        sandbox.close()
    return


def test_global_options_are_accepted_before_version():
    """
    **Feature: pyc (CLI-03)**
    **Property: 'pyc --profile x --version' prints the version (it used
    to be a usage error).**
    """
    sandbox = _Sandbox()
    try:
        rc, out, _err = _run(sandbox=sandbox, argv=["--profile", "x", "--version"])
        testbase.assert_equal((rc, out.startswith("pyc ")), (exit_codes.EXIT_OK, True))
    finally:
        sandbox.close()
    return


def test_unknown_global_option_is_a_usage_error():
    """
    **Feature: pyc (CLI-03)**
    **Property: an unknown leading option exits 2 naming it.**
    """
    sandbox = _Sandbox()
    try:
        rc, _out, err = _run(sandbox=sandbox, argv=["--verbose", "projects", "list"])
        testbase.assert_equal((rc, "--verbose" in err), (exit_codes.EXIT_USAGE_ERROR, True))
    finally:
        sandbox.close()
    return


# ===========================================================================
# CLI-04: redirects and non-API answers
# ===========================================================================


def test_redirect_is_not_followed():
    """
    **Feature: pyc (CLI-04)**
    **Property: the real HTTP opener returns a 302 as-is instead of
    following it to the sign-in page.**
    """
    redirector = _LocalHttpServer(status=302, headers={"Location": "/login?next=/x"}, body=b"")
    try:
        profile = _profile(server_url=redirector.url)
        request = transport.urllib.request.Request(url=redirector.url + "/api/v1/projects", method="GET")
        response = transport._stdlib_open_callable(request=request, timeout=5.0, context=None)
        testbase.assert_equal((response.status_code, redirector.hits), (302, ["/api/v1/projects"]))
    finally:
        redirector.close()
    return


def test_redirect_to_the_sign_in_page_is_an_error_not_success():
    """
    **Feature: pyc (CLI-04)**
    **Property: a command redirected to /login exits 7 and says why,
    printing nothing on stdout (it used to print the login page and
    exit 0).**
    """
    sandbox = _Sandbox()
    redirector = _LocalHttpServer(status=302, headers={"Location": "/login?next=%2Fadmin"}, body=b"")
    try:
        rc, out, err = _run(sandbox=sandbox, argv=["plugin-api", "catalog", "--server-url", redirector.url + "/admin"])
        testbase.assert_equal(
            (rc, out, "redirect to /login" in err, "sign-in page" in err),
            (exit_codes.EXIT_SERVER_ERROR, "", True, True),
        )
    finally:
        redirector.close()
        sandbox.close()
    return


def test_html_success_page_is_an_error_not_success():
    """
    **Feature: pyc (CLI-04)**
    **Property: a 200 text/html answer (a web-UI page) exits 7 naming
    server_url as the likely cause.**
    """
    sandbox = _Sandbox()
    page = _LocalHttpServer(status=200, headers={"Content-Type": "text/html; charset=utf-8"},
                            body=b"<!doctype html><title>Login</title>")
    try:
        rc, out, err = _run(sandbox=sandbox, argv=["plugin-api", "catalog", "--server-url", page.url])
        testbase.assert_equal(
            (rc, out, "HTML page instead of JSON" in err),
            (exit_codes.EXIT_SERVER_ERROR, "", True),
        )
    finally:
        page.close()
        sandbox.close()
    return


def test_redirect_classification_raises_unexpected_response():
    """
    **Feature: pyc (CLI-04)**
    **Property: _classify_status turns any 3xx into
    UnexpectedResponseError.**
    """
    raised = False
    try:
        transport._classify_status(status_code=301, response_text="", headers={"location": "/x"})
    except UnexpectedResponseError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ===========================================================================
# ORG-F16: --wait / runs wait
# ===========================================================================


def _sequence(*answers):
    state = {"index": 0}

    def _next():
        index = min(state["index"], len(answers) - 1)
        state["index"] += 1
        return answers[index]

    return _next


def test_wait_exits_zero_when_the_run_succeeds():
    """
    **Feature: pyc (ORG-F16)**
    **Property: 'test-runs trigger ... --wait' polls the returned
    run_id until it completes and exits 0 on success.**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox)
        server = _FakeServer({
            ("POST", "/api/v1/projects/p-1/test-runs"): {"run_id": "r-9"},
            ("GET", "/api/v1/runs/r-9"): _sequence(
                {"run_id": "r-9", "state": "running"},
                {"run_id": "r-9", "state": "completed", "terminal_outcome": "success"},
            ),
        })
        rc, _out, err = _run(sandbox=sandbox, argv=["test-runs", "trigger", "p-1", "--wait"],
                             opener=server, openapi_fetcher=_spec_fetcher)
        testbase.assert_equal((rc, "run r-9: completed" in err), (exit_codes.EXIT_OK, True))
    finally:
        sandbox.close()
    return


def test_runs_wait_exits_ten_when_the_run_fails():
    """
    **Feature: pyc (ORG-F16)**
    **Property: 'pyc runs wait' exits 10 when the run finishes failed.**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox)
        server = _FakeServer({("GET", "/api/v1/runs/r-9"): {
            "run_id": "r-9", "state": "failed", "terminal_outcome": "failure"}})
        rc, _out, err = _run(sandbox=sandbox, argv=["runs", "wait", "r-9"], opener=server)
        testbase.assert_equal(
            (rc, "finished as failed (failure)" in err), (exit_codes.EXIT_RUN_FAILED, True)
        )
    finally:
        sandbox.close()
    return


def test_runs_wait_exits_eleven_on_timeout():
    """
    **Feature: pyc (ORG-F16)**
    **Property: 'pyc runs wait --wait-timeout 0' on a run that is still
    running exits 11.**
    """
    sandbox = _Sandbox()
    try:
        _logged_in(sandbox)
        server = _FakeServer({("GET", "/api/v1/runs/r-9"): {"run_id": "r-9", "state": "running"}})
        rc, _out, _err = _run(sandbox=sandbox, argv=["runs", "wait", "r-9", "--wait-timeout", "0"],
                              opener=server)
        testbase.assert_equal(rc, exit_codes.EXIT_WAIT_TIMEOUT)
    finally:
        sandbox.close()
    return


class _TerminalInput(io.StringIO):
    """
        A stdin that claims to be a terminal.
    """

    def isatty(self) -> bool:
        return True


def test_interactive_login_prompts_for_the_token_without_echo():
    """
    **Feature: pyc (CLI-02)**
    **Property: on a terminal, 'pyc login' asks for the server URL,
    points at the token page, and reads the token through the no-echo
    prompt (never from the command line).**
    """
    sandbox = _Sandbox()
    try:
        prompts: List[str] = []

        def _prompt(text: str) -> str:
            prompts.append(text)
            return TOKEN

        out = io.StringIO()
        err = io.StringIO()
        rc = entry.main(
            argv=["login"], stdout=out, stderr=err, stdin=_TerminalInput(SERVER + "\n"),
            environ=dict(sandbox.environ),
            request_opener=_FakeServer({("GET", "/api/v1/me"): _me_answer()}),
            prompt_secret=_prompt,
        )
        profile = credentials.load_profile(profile_name=None, environ=sandbox.environ)
        testbase.assert_equal(
            (rc, prompts, "/account/api-tokens" in err.getvalue(), profile.bearer_token),
            (exit_codes.EXIT_OK, ["API token: "], True, TOKEN),
        )
    finally:
        sandbox.close()
    return
