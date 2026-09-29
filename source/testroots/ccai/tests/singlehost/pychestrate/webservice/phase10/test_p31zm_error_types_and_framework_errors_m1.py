"""
.. module:: test_p31zm_error_types_and_framework_errors_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Error ``type`` URIs lead to a page, and framework errors are
               problem documents (DOC-14).

.. moduleauthor:: Code Craft AI LLC

Every REST error carries a ``type`` that names its kind. They named
``https://docs.pychestrate.io/errors/...``, a site nothing publishes, and an
unmatched path, a wrong method or an unhandled exception came back in the
webworks dispatcher's own ``{"detail": ..., "status_code": ...}`` shape
instead of as a problem document. The service now serves a public page for
each documented type (``/errors/<slug>``, a service-relative reference unless
``PYCHESTRATE_PUBLIC_BASE_URL`` is set), and the dispatch shim rewrites the
dispatcher's error shape as the problem document for its status.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html as html_lib
import json
import os

from typing import Any, Dict, Optional

from ccai import testbase

from ccai.webworks.routing.response import HTMLResponse, JSONResponse

from ccai.pychestrate.webservice.api import error_catalogue, problem_json
from ccai.pychestrate.webservice.api.problem_json import PROBLEM_TYPES, problem_for_http_status
from ccai.pychestrate.webservice.public_endpoint import ENV_PUBLIC_BASE_URL
from ccai.pychestrate.webservice.wsgi_dispatch import framework_error_as_problem

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
)


class _FakeRequest:
    def __init__(self, *, path: str, accept: str = "text/html", path_params: Optional[Dict[str, str]] = None) -> None:
        self.path = path
        self.method = "GET"
        self.headers = {"Accept": accept}
        self.path_params = path_params if path_params is not None else {}
        return


class _PublicBase:
    """Sets ``PYCHESTRATE_PUBLIC_BASE_URL`` for a block, then restores it."""

    def __init__(self, value: str) -> None:
        self._value = value
        self._saved = None
        return

    def __enter__(self) -> "_PublicBase":
        self._saved = os.environ.get(ENV_PUBLIC_BASE_URL)
        os.environ[ENV_PUBLIC_BASE_URL] = self._value
        return self

    def __exit__(self, *exc_info: Any) -> None:
        if self._saved is None:
            os.environ.pop(ENV_PUBLIC_BASE_URL, None)
        else:
            os.environ[ENV_PUBLIC_BASE_URL] = self._saved
        return


# ---------------------------------------------------------------------------
# The types
# ---------------------------------------------------------------------------


def test_every_type_a_response_can_carry_has_a_catalogue_entry():
    """
    **Feature: error types (DOC-14)**
    **Property: each status the builder maps to a type, and the catch-all,
    has an entry with a meaning and a remedy, so no ``type`` the service
    emits by itself leads to a missing page.**
    """
    slugs = {entry.slug for entry in PROBLEM_TYPES}
    emitted = {problem_for_http_status(status=status, detail="x").body["type"].rsplit("/", 1)[1]
               for status in (400, 401, 403, 404, 405, 409, 422, 429, 500, 503, 418)}

    testbase.assert_equal(
        (sorted(emitted - slugs), all(len(entry.meaning) > 20 and len(entry.remedy) > 10 for entry in PROBLEM_TYPES)),
        ([], True),
    )
    return


def test_a_type_is_a_service_relative_reference_unless_a_public_address_is_configured():
    """
    **Feature: error types (DOC-14)**
    **Property: with no public base URL the type is ``/errors/not-found``;
    with one it is the absolute URL under it; an extension's own type is
    never touched; and no type names docs.pychestrate.io any more.**
    """
    plain = problem_for_http_status(status=404, detail="x").body["type"]
    with _PublicBase("https://pyc.example.com/"):
        absolute = problem_for_http_status(status=404, detail="x").body["type"]
        custom = problem_json.build_problem_response(
            problem_type="https://example.com/problems/quota", title="Quota", status=429, detail="x",
        ).body["type"]

    testbase.assert_equal(
        (plain, absolute, custom, "docs.pychestrate.io" in plain + absolute),
        ("/errors/not-found", "https://pyc.example.com/errors/not-found", "https://example.com/problems/quota", False),
    )
    return


# ---------------------------------------------------------------------------
# The pages
# ---------------------------------------------------------------------------


def _page(*, slug: Optional[str] = None, accept: str = "text/html") -> Any:
    ensure_app()  # installs the templates the pages render with
    if slug is None:
        return error_catalogue.handle_error_index(_FakeRequest(path="/errors", accept=accept))
    return error_catalogue.handle_error_type(
        _FakeRequest(path="/errors/" + slug, accept=accept, path_params={"slug": slug})
    )


def test_the_pages_render_in_the_strict_environment_production_uses():
    """
    **Feature: error types (DOC-14)**
    **Property: the index (with and without an unknown slug) and a type page
    render from the contexts the handlers build, in the strict Jinja
    environment the service runs with -- the lenient test environment once
    let an undefined variable through and staging answered 500.**
    """
    from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import strict_environment

    environment = strict_environment()
    rendered = [
        environment.get_template(error_catalogue.INDEX_TEMPLATE).render(error_catalogue.index_context()),
        environment.get_template(error_catalogue.INDEX_TEMPLATE).render(error_catalogue.index_context(unknown_slug="nope")),
        environment.get_template(error_catalogue.TYPE_TEMPLATE).render(error_catalogue.type_context(entry=PROBLEM_TYPES[0])),
    ]

    testbase.assert_equal(
        ("nope" in rendered[1], "nope" in rendered[0], PROBLEM_TYPES[0].title in rendered[2]),
        (True, False, True),
    )
    return


def test_the_json_entry_names_its_type_the_way_a_response_does():
    """
    **Feature: error types (DOC-14)**
    **Property: with a public base URL configured, the ``type`` in the JSON
    of an entry is the same absolute URL a response of that type carries.**
    """
    with _PublicBase("https://pyc.example.com"):
        entry = json.loads(_page(slug="conflict", accept="application/json").body)
        response_type = problem_for_http_status(status=409, detail="x").body["type"]

    testbase.assert_equal((entry["type"], response_type), ("https://pyc.example.com/errors/conflict",) * 2)
    return


def test_each_type_has_a_page_that_says_what_it_means_and_what_to_do():
    """
    **Feature: error types (DOC-14)**
    **Property: every documented type's page answers 200 HTML with its
    title, its type reference, what it means and what to do.**
    """
    problems = []
    for entry in PROBLEM_TYPES:
        response = _page(slug=entry.slug)
        html = html_lib.unescape(response.body.decode("utf-8"))
        for expected in (entry.title, "/errors/" + entry.slug, entry.meaning, entry.remedy):
            if response.status_code != 200 or expected not in html:
                problems.append((entry.slug, response.status_code, expected[:30]))

    testbase.assert_equal(problems, [])
    return


def test_the_index_lists_every_type_and_an_unknown_one_is_a_404_that_still_lists_them():
    """
    **Feature: error types (DOC-14)**
    **Property: /errors links every type; /errors/no-such-type answers 404
    and shows the list, and to a JSON caller a problem document.**
    """
    index = _page().body.decode("utf-8")
    unknown = _page(slug="no-such-type")
    unknown_json = _page(slug="no-such-type", accept="application/json")

    testbase.assert_equal(
        (all('href="/errors/{}"'.format(entry.slug) in index for entry in PROBLEM_TYPES),
         unknown.status_code, "no-such-type" in unknown.body.decode("utf-8"), 'href="/errors/not-found"' in unknown.body.decode("utf-8"),
         unknown_json.status_code, unknown_json.headers.get("Content-Type"), json.loads(unknown_json.body)["type"]),
        (True, 404, True, True, 404, "application/problem+json", "/errors/not-found"),
    )
    return


def test_a_caller_that_asks_for_json_gets_the_entry_as_json():
    """
    **Feature: error types (DOC-14)**
    **Property: with ``Accept: application/json`` the page of a type is the
    entry as JSON (slug, status, title, meaning, remedy, type) and the index
    is ``{"types": [...]}``; a browser's Accept (which lists text/html)
    still gets HTML.**
    """
    entry = json.loads(_page(slug="conflict", accept="application/json").body)
    index = json.loads(_page(accept="application/json").body)
    browser = _page(slug="conflict", accept="text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8")

    testbase.assert_equal(
        (entry["slug"], entry["status"], entry["type"], len(index["types"]) == len(PROBLEM_TYPES),
         browser.headers.get("Content-Type", "").startswith("text/html")),
        ("conflict", 409, "/errors/conflict", True, True),
    )
    return


def test_the_pages_are_registered_before_the_catch_all_and_need_no_sign_in():
    """
    **Feature: error types (DOC-14)**
    **Property: the application registers the catalogue routes ahead of the
    shell catch-all (which would send an anonymous caller to the login
    page), and the handlers never look at a session.**
    """
    ensure_app()  # the application module is imported through the harness
    import app_pychestrate_main

    with open(app_pychestrate_main.__file__, encoding="utf-8") as handle:
        main_source = handle.read()
    with open(error_catalogue.__file__, encoding="utf-8") as handle:
        handler_source = handle.read()

    registered = main_source.index("register_error_catalogue_routes(app=app)")
    catch_all = main_source.index("register_shell_catchall(app=app)")

    testbase.assert_equal(
        (registered < catch_all, "session" in handler_source.lower() or "principal" in handler_source.lower()),
        (True, False),
    )
    return


# ---------------------------------------------------------------------------
# Framework errors
# ---------------------------------------------------------------------------


def _framework(status: int, detail: str, **headers: str) -> JSONResponse:
    return JSONResponse({"detail": detail, "status_code": status}, status_code=status, headers=dict(headers) or None)


def test_the_dispatchers_own_error_shape_becomes_a_problem_document_and_keeps_its_headers():
    """
    **Feature: framework errors (DOC-14)**
    **Property: a 405 in the dispatcher's ``{detail, status_code}`` shape is
    answered as ``application/problem+json`` of type method-not-allowed
    with the request path as ``instance``, and the ``Allow`` header it set
    survives; 404 and 500 likewise.**
    """
    request = _FakeRequest(path="/api/v1/projects")
    converted = framework_error_as_problem(request=request, response=_framework(405, "Method Not Allowed", Allow="GET, POST"))
    body = json.loads(converted.body)
    statuses = [
        (status, json.loads(framework_error_as_problem(request=request, response=_framework(status, phrase)).body)["type"])
        for status, phrase in ((404, "Not Found"), (500, "Internal Server Error"))
    ]

    testbase.assert_equal(
        (converted.status_code, converted.headers["Content-Type"], converted.headers.get("Allow"), body,
         statuses),
        (405, "application/problem+json", "GET, POST",
         {"type": "/errors/method-not-allowed", "title": "Method Not Allowed", "status": 405,
          "detail": "Method Not Allowed", "instance": "/api/v1/projects"},
         [(404, "/errors/not-found"), (500, "/errors/internal-server-error")]),
    )
    return


def test_only_the_dispatchers_shape_is_replaced():
    """
    **Feature: framework errors (DOC-14)**
    **Property: a success, a handler's own JSON error, a problem document,
    an HTML error page, and a JSON error whose ``status_code`` disagrees
    with the response status all pass through as the same object.**
    """
    request = _FakeRequest(path="/api/v1/projects")
    problem = problem_json.build_problem_response(problem_type="/errors/conflict", title="Conflict", status=409, detail="x")
    from ccai.webworks.routing.response import Response

    untouched = [
        JSONResponse({"detail": "fine", "status_code": 200}, status_code=200),
        JSONResponse({"error": "name taken"}, status_code=409),
        JSONResponse({"detail": "x", "status_code": 409, "extra": 1}, status_code=409),
        JSONResponse({"detail": "x", "status_code": 500}, status_code=404),
        HTMLResponse("<h1>Not found</h1>", status_code=404),
        Response(404, {"Content-Type": "text/plain"}, b"Not Found"),
        Response(409, {"Content-Type": "application/problem+json"}, json.dumps(problem.body).encode("utf-8")),
        Response(500, {"Content-Type": "application/json"}, b"not json"),
    ]

    testbase.assert_equal(
        [framework_error_as_problem(request=request, response=response) is response for response in untouched],
        [True] * len(untouched),
    )
    return


def test_through_the_whole_application_an_unknown_api_path_is_a_problem_document():
    """
    **Feature: framework errors (DOC-14)**
    **Property: a request the router cannot match, sent through the WSGI
    application, is answered 404 as ``application/problem+json`` of type
    not-found with the path as ``instance``, not as the dispatcher's own
    shape.**
    """
    handle = ensure_app()
    response = drive_request(wsgi_app=handle.wsgi_app, method="GET", path="/api/v1/no-such-thing")
    body = json.loads(response.body)

    testbase.assert_equal(
        (response.status_code, response.header("Content-Type"), body.get("type"), body.get("instance"), "status_code" in body),
        (404, "application/problem+json", "/errors/not-found", "/api/v1/no-such-thing", False),
    )
    return
