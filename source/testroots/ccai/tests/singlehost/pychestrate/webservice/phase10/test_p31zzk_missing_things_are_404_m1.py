"""
.. module:: test_p31zzk_missing_things_are_404_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A missing thing or an unknown admin path is a real 404 (ADM-22).

.. moduleauthor:: Code Craft AI LLC

``/projects/999`` answered 303 to the projects list with a "Project not found."
flash, and ``/admin/nope`` answered 200 with the shell and an empty page. Both
now answer 404 with the site's error page inside the shell: it names what was
not found, keeps the address, and links back to the list ("Back to All Projects").
Handlers say "not found" through one helper (``_not_found_redirect``); a static
check keeps them from building their own flash redirect again.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import glob
import html
import os
import re

from typing import Any, Dict, Optional

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.blueprints.config import routes as config_routes
from ccai.pychestrate.webservice.webinterface.foundation import flash
from ccai.pychestrate.webservice.webinterface.site_shell import bundle_registry, catchall_route

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    logged_in_cookies,
)


BLUEPRINTS_DIR = os.path.join(
    os.path.dirname(config_routes.__file__), os.pardir
)
ADMIN_BUNDLE_ENTRY = os.path.join(
    os.path.dirname(bundle_registry.__file__), os.pardir,
    "static", "javascript", "pyc-admin-bundle", "index.entry.js",
)


def _setup() -> Dict[str, Any]:
    handle = ensure_app()
    rtnval = {"wsgi_app": handle.wsgi_app, "cookies": logged_in_cookies(wsgi_app=handle.wsgi_app)}
    return rtnval


def _get(setup: Dict[str, Any], path: str, *, signed_in: bool = True) -> Any:
    cookies = setup["cookies"] if signed_in else None
    response = drive_request(wsgi_app=setup["wsgi_app"], method="GET", path=path, cookies=cookies)
    if signed_in:
        setup["cookies"].update(response.collect_set_cookies())
    return response


def _back_link(text: str) -> Optional[Any]:
    match = re.search(r'<a href="([^"]*)"[^>]*data-role="back-to-list">([^<]*)</a>', text)
    rtnval = (html.unescape(match.group(2)), match.group(1)) if match else None
    return rtnval


def test_a_missing_project_is_a_404_page_that_links_back_to_the_projects():
    """
    **Feature: real 404s (ADM-22)**
    **Property: ``/projects/99999999`` answers 404 in the shell, says "Project
    not found", and offers "Back to All Projects" (the list's own name in the navigation); the next page shows
    no leftover "not found" flash.**
    """
    setup = _setup()
    response = _get(setup, "/projects/99999999")
    text = response.text
    following = _get(setup, "/projects/list").text

    testbase.assert_equal(
        (
            response.status_code,
            "Project not found" in text,
            "pyc-site-shell" in text,
            _back_link(text),
            "Project not found" in following,
        ),
        (404, True, True, ("Back to All Projects", "/projects/list"), False),
    )
    return


def test_a_missing_user_and_a_missing_resource_are_404_pages_too():
    """
    **Feature: real 404s (ADM-22)**
    **Property: the same holds for the admin and resources pages: a missing
    user gives 404 "User not found" with "Back to Users"; a missing
    resource gives 404 with "Back to Resources".**
    """
    setup = _setup()
    user = _get(setup, "/admin/users/no-such-user")
    resource = _get(setup, "/resources/99999999")

    testbase.assert_equal(
        (
            user.status_code, "User not found" in user.text, _back_link(user.text),
            resource.status_code, "not found" in resource.text, _back_link(resource.text),
        ),
        (404, True, ("Back to Users", "/admin/users"), 404, True, ("Back to Resources", "/resources/list")),
    )
    return


def test_an_unknown_admin_path_is_a_404_and_the_real_ones_still_open():
    """
    **Feature: real 404s (ADM-22)**
    **Property: ``/admin/nope`` answers 404 (also when signed out, since a
    mistyped address is not a reason to ask for a sign-in); the admin pages the
    bundle serves and the ones the blueprints serve still answer 200.**
    """
    setup = _setup()
    unknown = _get(setup, "/admin/nope")
    unknown_signed_out = _get(setup, "/admin/nope", signed_in=False)
    deeper = _get(setup, "/admin/feature-flags/nope")
    served = {path: _get(setup, path).status_code for path in (
        "/admin", "/admin/overview", "/admin/feature-flags", "/admin/extensions",
        "/admin/system-health", "/admin/dashboard", "/admin/users",
    )}

    testbase.assert_equal(
        (unknown.status_code, unknown_signed_out.status_code, deeper.status_code, sorted(set(served.values()))),
        (404, 404, 404, [200]),
    )
    return


def test_the_shell_owns_only_the_admin_paths_its_bundle_serves():
    """
    **Feature: real 404s (ADM-22)**
    **Property: the shell catch-all treats ``/admin``, ``/admin/overview``,
    ``/admin/feature-flags``, ``/admin/extensions`` and ``/admin/system-health``
    (with or without a trailing slash) as its own and no other path under
    ``/admin``; every path under the other bundle prefixes (an id under
    ``/runs``) stays the bundle's to report.**
    """
    bundle_registry.install_default_bundles()
    owned = {
        path: catchall_route._is_known_shell_route(path=path)
        for path in (
            "/admin", "/admin/", "/admin/overview", "/admin/feature-flags", "/admin/extensions",
            "/admin/system-health/", "/admin/nope", "/admin/feature-flags/nope", "/admin/users/x",
            "/runs", "/runs/some-id", "/pipelines/abc/edit", "/nope",
        )
    }

    testbase.assert_equal(
        sorted(path for path, known in owned.items() if known is True),
        sorted([
            "/admin", "/admin/", "/admin/overview", "/admin/feature-flags", "/admin/extensions",
            "/admin/system-health/", "/runs", "/runs/some-id", "/pipelines/abc/edit",
        ]),
    )
    return


def test_the_admin_bundle_route_list_matches_the_bundle():
    """
    **Feature: real 404s (ADM-22)**
    **Property: the paths the server treats as the admin bundle's are exactly
    the ones ``pyc-admin-bundle/index.entry.js`` classifies, so a route added
    to one is not forgotten in the other.**
    """
    with open(ADMIN_BUNDLE_ENTRY, encoding="utf-8") as handle:
        source = handle.read()
    in_bundle = sorted(set(re.findall(r'^const [A-Z_]+_ROUTE = "(/admin[^"]*)";', source, re.M)))

    testbase.assert_equal(sorted(bundle_registry.EXACT_BUNDLE_ROUTES["/admin"]), in_bundle)
    return


def test_a_handler_that_is_not_wrapped_still_redirects_with_the_message():
    """
    **Feature: real 404s (ADM-22)**
    **Property: outside the shell wrapper (a direct call), the not-found answer
    is still a 303 to the list with the message flashed, so nothing that calls
    a handler directly loses the message.**
    """
    ensure_app()
    session: Dict[str, Any] = {}
    response = config_routes._not_found_redirect(session=session, url="/projects/list", message="Project not found.")

    testbase.assert_equal(
        (
            response.status_code,
            response.header("Location") if hasattr(response, "header") else response._headers.get("Location"),
            isinstance(response, config_routes.EntityNotFoundResponse),
            [message for _category, message in flash.consume_flashes(session=session)],
        ),
        (303, "/projects/list", True, ["Project not found."]),
    )
    return


def test_no_handler_builds_its_own_not_found_flash_redirect():
    """
    **Feature: real 404s (ADM-22)**
    **Property: no blueprint module calls ``_redirect_with_flash`` with a
    "... not found" message; they use ``_not_found_redirect``.**
    """
    offenders = []
    for path in sorted(glob.glob(os.path.join(BLUEPRINTS_DIR, "**", "*.py"), recursive=True)):
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        for match in re.finditer(r"_redirect_with_flash\((?:(?!category=).){0,500}?message=(?:not_found_message|\"[^\"]* not found[^\"]*\")", text, re.S):
            offenders.append("{}:{}".format(os.path.relpath(path, BLUEPRINTS_DIR), text.count("\n", 0, match.start()) + 1))

    testbase.assert_equal(offenders, [])
    return
