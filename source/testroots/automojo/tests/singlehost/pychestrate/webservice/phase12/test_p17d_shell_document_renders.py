"""
.. module:: test_p17d_shell_document_renders
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase-12 smoke -- the deployed pychestrate root
               serves the unified site-shell document.

.. moduleauthor:: Automation Mojo LLC

Hits ``GET /`` against the deploy and asserts that:

* The response is HTML.
* The response body contains the ``<pyc-site-shell>`` Custom
  Element open tag.
* The response body references the prebuilt shell bundle at
  ``/static/javascript/dist/pyc-site-shell.js``.

That's enough to confirm PR3's mount path works end-to-end (the
catch-all handler runs, the Jinja template renders, the static
file path is correctly emitted). Sidebar / palette / metrics
behavior arrives with M2/M3.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import httpx

from automojo import testbase

from automojo.testshared.test_config import BASE_URL


REQUEST_TIMEOUT_SECONDS: float = 10.0


def test_root_path_serves_site_shell_document():
    """
    **Feature: site-shell**
    **Property: GET / on a deployed pychestrate instance
    returns an HTML document that mounts the
    ``<pyc-site-shell>`` Custom Element and imports the
    prebuilt ``/static/javascript/dist/pyc-site-shell.js``
    bundle.**
    """
    with httpx.Client(
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
        response = client.get("/")

    testbase.assert_equal(response.status_code, 200)
    content_type = response.headers.get("content-type", "")
    testbase.assert_true("text/html" in content_type)

    body = response.text
    testbase.assert_true("<pyc-site-shell" in body)
    testbase.assert_true(
        "/static/javascript/dist/pyc-site-shell.js" in body
    )
    return


def test_shell_bundle_is_served_as_javascript():
    """
    **Feature: site-shell**
    **Property: The prebuilt shell bundle at
    ``/static/javascript/dist/pyc-site-shell.js`` is reachable
    over the static-files surface and is served with a
    JavaScript-flavored Content-Type.**
    """
    with httpx.Client(
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
        response = client.get("/static/javascript/dist/pyc-site-shell.js")

    testbase.assert_equal(response.status_code, 200)
    content_type = response.headers.get("content-type", "")
    # mimetypes resolves ".js" to either "application/javascript"
    # or "text/javascript" depending on platform; accept either.
    js_content_types = ("javascript",)
    matched = False
    for token in js_content_types:
        if token in content_type:
            matched = True
            break
    testbase.assert_true(matched)
    return
