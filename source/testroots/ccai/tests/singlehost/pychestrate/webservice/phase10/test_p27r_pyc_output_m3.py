"""
.. module:: test_p27r_pyc_output_m3
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``pyc`` output (audit finding CLI-10): table / json /
               yaml / tsv / raw with a terminal-aware default, lists as
               arrays, ``--fields``, ``--quiet``, ``--all`` /
               ``--limit``, request ids in errors, token-expiry
               warnings.

.. moduleauthor:: Code Craft AI LLC

The audit found pyc printed the raw ``{items, meta}`` envelope, had no
table, ``--output``, ``--fields`` or ``--quiet``, never followed
pagination, named no request id in errors, and printed two JSON
documents for ``--wait``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import copy
import json

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlsplit

from ccai import testbase

from ccai.pychestrate.cli import exit_codes
from ccai.pychestrate.cli.models import RestResponse
from ccai.testshared.factories.pyc.pyc_harness import (
    PycFakeServer,
    PycSandbox,
    TerminalStream,
    run_pyc,
)


GADGET_ROWS: List[Dict[str, Any]] = [
    {"gadget_id": "g-1", "slug": "alpha", "state": "ACTIVE", "labels": {"env": "ci"}, "note": "tab\there"},
    {"gadget_id": "g-2", "slug": "beta", "state": "RETIRED", "labels": {"env": "lab"}, "note": "two\nlines"},
    {"gadget_id": "g-3", "slug": "gamma", "state": "ACTIVE", "labels": {}, "note": None},
    {"gadget_id": "g-4", "slug": "delta", "state": "ACTIVE", "labels": {}, "note": "true"},
    {"gadget_id": "g-5", "slug": "epsilon", "state": "ACTIVE", "labels": {}, "note": "12:30"},
]

DOCUMENT: Dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Pychestrate", "version": "9.9.9"},
    "servers": [{"url": "/api/v1"}],
    "paths": {
        "/gadgets": {
            "get": {
                "operationId": "gadgets_list", "tags": ["gadgets"],
                "parameters": [
                    {"name": "page", "in": "query", "schema": {"type": "integer"}},
                    {"name": "per_page", "in": "query", "schema": {"type": "integer"}},
                ],
            },
        },
        "/gadgets/{slug}": {
            "get": {
                "operationId": "gadgets_get_by_slug", "tags": ["gadgets"],
                "parameters": [{"name": "slug", "in": "path", "required": True}],
            },
        },
        "/gadgets/{slug}:trigger": {
            "post": {
                "operationId": "gadgets_trigger", "tags": ["gadgets"],
                "parameters": [{"name": "slug", "in": "path", "required": True}],
            },
        },
        "/sprockets": {
            "get": {
                "operationId": "sprockets_list", "tags": ["sprockets"],
                "parameters": [
                    {"name": "offset", "in": "query", "schema": {"type": "integer"}},
                    {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                ],
            },
        },
        "/mounts": {"get": {"operationId": "mounts_list", "tags": ["mounts"]}},
        "/logs": {"get": {"operationId": "logs_read", "tags": ["logs"]}},
        "/runs/{run_id}": {
            "get": {
                "operationId": "runs_get_by_id", "tags": ["runs"],
                "parameters": [{"name": "run_id", "in": "path", "required": True}],
            },
        },
    },
}


class _PagedGadgets:
    """
        Fake server paging GADGET_ROWS by ``page`` / ``per_page`` (and
        SPROCKET rows by ``offset`` / ``limit``); records every URL.
    """

    def __init__(self) -> None:
        self.urls: List[str] = []
        return

    def __call__(self, *, request, timeout, context) -> RestResponse:
        self.urls.append(request.full_url)
        parts = urlsplit(request.full_url)
        query = {key: values[-1] for key, values in parse_qs(parts.query).items()}
        if parts.path == "/api/v1/gadgets":
            page = int(query.get("page", "1"))
            per_page = int(query.get("per_page", "2"))
            start = (page - 1) * per_page
            body: Any = {
                "items": GADGET_ROWS[start:start + per_page],
                "meta": {"page": page, "per_page": per_page, "total": len(GADGET_ROWS), "next_cursor": None},
            }
        elif parts.path == "/api/v1/sprockets":
            offset = int(query.get("offset", "0"))
            limit = int(query.get("limit", "2"))
            body = {"sprockets": GADGET_ROWS[offset:offset + limit], "total": len(GADGET_ROWS),
                    "offset": offset, "limit": limit}
        else:
            body = {"title": "Not Found", "detail": "no route", "status": 404}
            return RestResponse(status_code=404, headers={"content-type": "application/problem+json"},
                                body=None, raw_text=json.dumps(body))
        rtnval = RestResponse(status_code=200, headers={"content-type": "application/json"},
                              body=body, raw_text=json.dumps(body))
        return rtnval


def _sandbox() -> PycSandbox:
    sandbox = PycSandbox()
    sandbox.log_in()
    sandbox.cache_command_list(document=copy.deepcopy(DOCUMENT))
    return sandbox


def _gadget_server() -> PycFakeServer:
    rtnval = PycFakeServer({
        ("GET", "/api/v1/_meta/openapi.json"): copy.deepcopy(DOCUMENT),
        ("GET", "/api/v1/gadgets"): {
            "items": copy.deepcopy(GADGET_ROWS[:2]),
            "meta": {"page": 1, "per_page": 2, "total": 5, "next_cursor": None},
        },
        ("GET", "/api/v1/gadgets/alpha"): copy.deepcopy(GADGET_ROWS[0]),
        ("GET", "/api/v1/mounts"): {"items": [{"ext_name": "example"}], "dynamic_mount": "mounted"},
        ("GET", "/api/v1/logs"): RestResponse(status_code=200, headers={"content-type": "text/plain"},
                                              body="line one\nline two\n", raw_text="line one\nline two\n"),
    })
    return rtnval


# ===========================================================================
# Formats
# ===========================================================================


def test_list_prints_a_json_array_when_piped():
    """
    **Feature: pyc output (CLI-10)**
    **Property: a list answer ({items, meta}) prints as a JSON array when
    stdout is not a terminal (it used to print the raw envelope).**
    """
    sandbox = _sandbox()
    try:
        rc, out, _err = run_pyc(sandbox=sandbox, argv=["gadgets", "list"], opener=_gadget_server())
        testbase.assert_equal((rc, json.loads(out)), (exit_codes.EXIT_OK, GADGET_ROWS[:2]))
    finally:
        sandbox.close()
    return


def test_default_format_on_a_terminal_is_a_table():
    """
    **Feature: pyc output (CLI-10)**
    **Property: on a terminal a list prints as aligned columns with a
    header row.**
    """
    sandbox = _sandbox()
    try:
        rc, out, _err = run_pyc(sandbox=sandbox, argv=["gadgets", "list"], opener=_gadget_server(),
                                stdout=TerminalStream())
        first_line = out.splitlines()[0]
        testbase.assert_equal(
            (rc, first_line.split()), (exit_codes.EXIT_OK, ["gadget_id", "slug", "state", "note"])
        )
    finally:
        sandbox.close()
    return


def test_table_leaves_out_columns_that_do_not_fit_the_terminal():
    """
    **Feature: pyc output (CLI-10)**
    **Property: a table wider than the terminal (COLUMNS=24) drops the
    trailing columns and says which on stderr.**
    """
    sandbox = _sandbox()
    try:
        _rc, out, err = run_pyc(sandbox=sandbox, argv=["gadgets", "list"], opener=_gadget_server(),
                                stdout=TerminalStream(), environ={"COLUMNS": "24"})
        testbase.assert_equal(
            (out.splitlines()[0].split(), "did not fit: state, note" in err),
            (["gadget_id", "slug"], True),
        )
    finally:
        sandbox.close()
    return


def test_yaml_output_reads_back_as_the_same_document():
    """
    **Feature: pyc output (CLI-10)**
    **Property: -o yaml prints YAML that parses back to exactly the JSON
    document (strings that look like booleans, times or numbers stay
    strings).**
    """
    import yaml  # noqa: E402 -- test-only dependency

    server = _gadget_server()
    server.routes[("GET", "/api/v1/gadgets")] = {"items": copy.deepcopy(GADGET_ROWS), "meta": {}}
    sandbox = _sandbox()
    try:
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["gadgets", "list", "-o", "yaml"], opener=server)
        testbase.assert_equal(yaml.safe_load(out), GADGET_ROWS)
    finally:
        sandbox.close()
    return


def test_tsv_output_escapes_tabs_and_newlines():
    """
    **Feature: pyc output (CLI-10)**
    **Property: -o tsv prints a header row and one row per item, with
    tabs and newlines inside values escaped.**
    """
    sandbox = _sandbox()
    try:
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["gadgets", "list", "-o", "tsv", "--fields", "slug,note"],
                                 opener=_gadget_server())
        testbase.assert_equal(out, "slug\tnote\nalpha\ttab\\there\nbeta\ttwo\\nlines\n")
    finally:
        sandbox.close()
    return


def test_raw_prints_the_answer_as_the_server_sent_it():
    """
    **Feature: pyc output (CLI-10)**
    **Property: -o raw prints the response body unchanged (envelope
    included).**
    """
    server = _gadget_server()
    sandbox = _sandbox()
    try:
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["gadgets", "list", "-o", "raw"], opener=server)
        testbase.assert_equal(json.loads(out)["meta"]["total"], 5)
    finally:
        sandbox.close()
    return


def test_output_option_works_before_or_after_the_command():
    """
    **Feature: pyc output (CLI-10)**
    **Property: 'pyc -o tsv gadgets list' prints what 'pyc gadgets list
    --output tsv' prints.**
    """
    sandbox = _sandbox()
    try:
        _rc, before, _err = run_pyc(sandbox=sandbox, argv=["-o", "tsv", "gadgets", "list"], opener=_gadget_server())
        _rc, after, _err = run_pyc(sandbox=sandbox, argv=["gadgets", "list", "--output", "tsv"],
                                   opener=_gadget_server())
        testbase.assert_equal((before == after, before.startswith("gadget_id\t")), (True, True))
    finally:
        sandbox.close()
    return


def test_unknown_output_format_is_a_usage_error():
    """
    **Feature: pyc output (CLI-10)**
    **Property: -o jsn exits 2 suggesting 'json', before any request.**
    """
    sandbox = _sandbox()
    try:
        server = _gadget_server()
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["gadgets", "list", "-o", "jsn"], opener=server)
        testbase.assert_equal(
            (rc, "did you mean 'json'?" in err, server.requests), (exit_codes.EXIT_USAGE_ERROR, True, [])
        )
    finally:
        sandbox.close()
    return


def test_envelope_with_more_than_paging_data_stays_an_object():
    """
    **Feature: pyc output (CLI-10)**
    **Property: a list answer that also carries other data
    ({items, dynamic_mount}) prints as the object in JSON, so nothing is
    lost.**
    """
    sandbox = _sandbox()
    try:
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["mounts", "list"], opener=_gadget_server())
        testbase.assert_equal(json.loads(out)["dynamic_mount"], "mounted")
    finally:
        sandbox.close()
    return


def test_offset_list_answer_prints_its_items():
    """
    **Feature: pyc output (CLI-10)**
    **Property: an offset list answer ({sprockets, total, offset, limit})
    prints as the array of sprockets.**
    """
    sandbox = _sandbox()
    try:
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["sprockets", "list"], opener=_PagedGadgets())
        testbase.assert_equal(json.loads(out), GADGET_ROWS[:2])
    finally:
        sandbox.close()
    return


def test_text_answer_prints_as_text():
    """
    **Feature: pyc output (CLI-10)**
    **Property: a text/plain answer (logs) prints verbatim.**
    """
    sandbox = _sandbox()
    try:
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["logs", "read"], opener=_gadget_server())
        testbase.assert_equal(out, "line one\nline two\n")
    finally:
        sandbox.close()
    return


# ===========================================================================
# --fields and --quiet
# ===========================================================================


def test_fields_select_and_order_the_fields():
    """
    **Feature: pyc output (CLI-10)**
    **Property: --fields state,slug keeps those fields in that order.**
    """
    sandbox = _sandbox()
    try:
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["gadgets", "list", "--fields", "state,slug"],
                                 opener=_gadget_server())
        testbase.assert_equal(
            [list(item.items()) for item in json.loads(out)],
            [[("state", "ACTIVE"), ("slug", "alpha")], [("state", "RETIRED"), ("slug", "beta")]],
        )
    finally:
        sandbox.close()
    return


def test_fields_reach_into_nested_objects():
    """
    **Feature: pyc output (CLI-10)**
    **Property: --fields labels.env reads a field inside an object.**
    """
    sandbox = _sandbox()
    try:
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["gadgets", "list", "-o", "tsv", "--fields", "slug,labels.env"],
                                 opener=_gadget_server())
        testbase.assert_equal(out, "slug\tlabels.env\nalpha\tci\nbeta\tlab\n")
    finally:
        sandbox.close()
    return


def test_unknown_field_is_a_usage_error_with_a_suggestion():
    """
    **Feature: pyc output (CLI-10)**
    **Property: --fields naming a field no item has exits 2 suggesting
    the closest field.**
    """
    sandbox = _sandbox()
    try:
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["gadgets", "list", "--fields", "slgu"], opener=_gadget_server())
        testbase.assert_equal((rc, "did you mean 'slug'?" in err), (exit_codes.EXIT_USAGE_ERROR, True))
    finally:
        sandbox.close()
    return


def test_quiet_prints_what_the_get_command_takes():
    """
    **Feature: pyc output (CLI-10)**
    **Property: -q prints one identifier per line -- the slug, because
    'gadgets get' takes a SLUG -- so the output feeds the next command.**
    """
    sandbox = _sandbox()
    try:
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["gadgets", "list", "-q"], opener=_gadget_server())
        testbase.assert_equal(out, "alpha\nbeta\n")
    finally:
        sandbox.close()
    return


# ===========================================================================
# Pagination
# ===========================================================================


def test_single_page_notes_that_more_items_exist():
    """
    **Feature: pyc output (CLI-10)**
    **Property: a list with more items than the page notes on stderr how
    many there are and how to get them.**
    """
    sandbox = _sandbox()
    try:
        _rc, _out, err = run_pyc(sandbox=sandbox, argv=["gadgets", "list"], opener=_gadget_server())
        testbase.assert_equal("showing items 1-2 of 5; add --all" in err, True)
    finally:
        sandbox.close()
    return


def test_all_follows_every_page():
    """
    **Feature: pyc output (CLI-10)**
    **Property: --all requests page after page and prints every item as
    one array (pagination used to be ignored).**
    """
    sandbox = _sandbox()
    try:
        server = _PagedGadgets()
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["gadgets", "list", "--all"], opener=server)
        testbase.assert_equal((json.loads(out), len(server.urls)), (GADGET_ROWS, 3))
    finally:
        sandbox.close()
    return


def test_limit_stops_after_that_many_items():
    """
    **Feature: pyc output (CLI-10)**
    **Property: --limit 3 prints three items, requesting only the pages
    it needs.**
    """
    sandbox = _sandbox()
    try:
        server = _PagedGadgets()
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["gadgets", "list", "--limit", "3"], opener=server)
        testbase.assert_equal(
            ([item["slug"] for item in json.loads(out)], len(server.urls)), (["alpha", "beta", "gamma"], 2)
        )
    finally:
        sandbox.close()
    return


def test_all_follows_offset_pages():
    """
    **Feature: pyc output (CLI-10)**
    **Property: --all on an offset / limit list keeps asking until the
    last item.**
    """
    sandbox = _sandbox()
    try:
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["sprockets", "list", "--limit", "2", "--all"],
                                 opener=_PagedGadgets())
        testbase.assert_equal(json.loads(out), GADGET_ROWS)
    finally:
        sandbox.close()
    return


def test_raw_output_cannot_follow_pages():
    """
    **Feature: pyc output (CLI-10)**
    **Property: -o raw with --all exits 2 (raw is one answer as sent).**
    """
    sandbox = _sandbox()
    try:
        rc, _out, _err = run_pyc(sandbox=sandbox, argv=["gadgets", "list", "--all", "-o", "raw"],
                                 opener=_PagedGadgets())
        testbase.assert_equal(rc, exit_codes.EXIT_USAGE_ERROR)
    finally:
        sandbox.close()
    return


# ===========================================================================
# Errors, request ids, token expiry, --wait
# ===========================================================================


def test_every_request_carries_a_request_id():
    """
    **Feature: pyc output (CLI-10)**
    **Property: requests carry an X-Request-Id header.**
    """
    sandbox = _sandbox()
    try:
        server = _gadget_server()
        run_pyc(sandbox=sandbox, argv=["gadgets", "get", "alpha"], opener=server)
        testbase.assert_equal(len(server.requests[-1]["headers"].get("x-request-id", "")), 32)
    finally:
        sandbox.close()
    return


def test_error_names_the_request_id_pyc_sent():
    """
    **Feature: pyc output (CLI-10)**
    **Property: a failed request's error line is 'title: detail (HTTP
    404, request id <the X-Request-Id sent>)'.**
    """
    sandbox = _sandbox()
    try:
        server = _gadget_server()
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["gadgets", "get", "nope"], opener=server)
        sent = server.requests[-1]["headers"]["x-request-id"]
        testbase.assert_equal(
            (rc, err.strip()),
            (exit_codes.EXIT_NOT_FOUND, "error: Not Found: no route (HTTP 404, request id {})".format(sent)),
        )
    finally:
        sandbox.close()
    return


def test_error_prefers_the_request_id_the_server_names():
    """
    **Feature: pyc output (CLI-10)**
    **Property: when the server answers with its own X-Request-Id, the
    error names that id.**
    """
    sandbox = _sandbox()
    try:
        server = _gadget_server()
        server.routes[("GET", "/api/v1/gadgets/broken")] = RestResponse(
            status_code=500, headers={"content-type": "application/problem+json", "x-request-id": "srv-77"},
            body=None, raw_text='{"title": "Internal Server Error", "detail": "boom", "status": 500}',
        )
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["gadgets", "get", "broken"], opener=server)
        testbase.assert_equal(
            (rc, "(HTTP 500, request id srv-77)" in err), (exit_codes.EXIT_SERVER_ERROR, True)
        )
    finally:
        sandbox.close()
    return


def test_token_expiring_within_a_week_is_warned_about():
    """
    **Feature: pyc output (CLI-10)**
    **Property: a stored token that expires in three days prints a
    warning naming the date on every command.**
    """
    expires = datetime.now(timezone.utc) + timedelta(days=3, hours=1)
    sandbox = PycSandbox()
    try:
        sandbox.log_in(extra="bearer_token_expires_at = {}\n".format(expires.isoformat()))
        sandbox.cache_command_list(document=copy.deepcopy(DOCUMENT))
        _rc, _out, err = run_pyc(sandbox=sandbox, argv=["gadgets", "get", "alpha"], opener=_gadget_server())
        testbase.assert_equal(
            "expires in 3 day(s) ({})".format(expires.date().isoformat()) in err, True
        )
    finally:
        sandbox.close()
    return


def test_expired_token_is_warned_about():
    """
    **Feature: pyc output (CLI-10)**
    **Property: a stored token past its expiry prints "expired on
    <date>".**
    """
    expired = datetime.now(timezone.utc) - timedelta(days=2)
    sandbox = PycSandbox()
    try:
        sandbox.log_in(extra="bearer_token_expires_at = {}\n".format(expired.isoformat()))
        sandbox.cache_command_list(document=copy.deepcopy(DOCUMENT))
        _rc, _out, err = run_pyc(sandbox=sandbox, argv=["gadgets", "get", "alpha"], opener=_gadget_server())
        testbase.assert_equal("expired on {}".format(expired.date().isoformat()) in err, True)
    finally:
        sandbox.close()
    return


def test_wait_prints_only_the_finished_run():
    """
    **Feature: pyc output (CLI-10)**
    **Property: '--wait -o json' prints one JSON document -- the finished
    run -- instead of the trigger answer followed by the run.**
    """
    sandbox = _sandbox()
    try:
        final_run = {"run_id": "r-9", "state": "completed", "terminal_outcome": "success"}
        server = _gadget_server()
        server.routes[("POST", "/api/v1/gadgets/alpha:trigger")] = {"run_id": "r-9"}
        server.routes[("GET", "/api/v1/runs/r-9")] = final_run
        rc, out, _err = run_pyc(sandbox=sandbox, argv=["gadgets", "trigger", "alpha", "--wait", "-o", "json"],
                                opener=server)
        testbase.assert_equal((rc, json.loads(out)), (exit_codes.EXIT_OK, final_run))
    finally:
        sandbox.close()
    return


# ===========================================================================
# Built-in commands
# ===========================================================================


def test_ext_list_prints_a_table_on_a_terminal():
    """
    **Feature: pyc output (CLI-10)**
    **Property: 'pyc ext list' on a terminal prints one line per route
    under a header (its help promised lines; it printed JSON).**
    """
    sandbox = _sandbox()
    try:
        server = PycFakeServer({("GET", "/api/v1/plugin-api/_meta/mounts"): [
            {"ext_name": "example", "method": "GET", "path_suffix": "/echo",
             "full_path": "/api/v1/ext/example/echo", "handler_class": "ExampleEchoEndpoints"},
        ]})
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["ext", "list"], opener=server, stdout=TerminalStream())
        lines = out.splitlines()
        testbase.assert_equal(
            (lines[0].split()[:2], lines[1].split()[:2]), (["ext_name", "method"], ["example", "GET"])
        )
    finally:
        sandbox.close()
    return


def test_whoami_prints_yaml_on_request():
    """
    **Feature: pyc output (CLI-10)**
    **Property: 'pyc whoami -o yaml' prints the identity as YAML.**
    """
    import yaml  # noqa: E402 -- test-only dependency

    sandbox = _sandbox()
    try:
        identity = {"login_name": "dana", "account_kind": "user", "authentication": {"method": "api_token"}}
        server = PycFakeServer({("GET", "/api/v1/me"): identity})
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["whoami", "-o", "yaml"], opener=server)
        testbase.assert_equal(yaml.safe_load(out), identity)
    finally:
        sandbox.close()
    return


def test_commands_prints_json_rows_on_request():
    """
    **Feature: pyc output (CLI-10)**
    **Property: 'pyc commands -o json' prints one object per command
    with its method and path.**
    """
    sandbox = _sandbox()
    try:
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["commands", "-o", "json", "--fields", "command,method,path"],
                                 opener=_gadget_server())
        rows = json.loads(out)
        testbase.assert_equal(
            {"command": "gadgets get", "method": "GET", "path": "/api/v1/gadgets/{slug}"} in rows, True
        )
    finally:
        sandbox.close()
    return
