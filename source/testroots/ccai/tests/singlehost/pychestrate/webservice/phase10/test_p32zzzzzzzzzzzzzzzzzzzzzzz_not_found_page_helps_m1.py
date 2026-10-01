"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzz_not_found_page_helps_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The not-found page offers more than the home page (DOC-20).

.. moduleauthor:: Code Craft AI LLC

A signed-in person who followed a stale link got "Page not found" and one button, "Go to the home page". The page now also says
where to look next: search (Ctrl+K), the projects, and the user guide. Other errors (403, 500) are unchanged.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm


def test_the_not_found_page_says_where_to_look_next():
    """
    **Feature: not-found page (DOC-20)**
    **Property: a project page for an id that does not exist answers 404 and, besides the home button, says to search with Ctrl+K, links
    the projects and links the user guide at /docs/.**
    """
    cookies = adm.admin_cookies()
    response = adm.get(path="/projects/00000000-0000-4000-8000-000000000000", cookies=cookies)
    html = response.text

    testbase.assert_equal(
        (response.status_code, 'data-role="not-found-help"' in html, "<kbd>Ctrl</kbd>+<kbd>K</kbd>" in html, 'href="/projects"' in html, 'href="/docs/"' in html, "Go to the home page" in html),
        (404, True, True, True, True, True),
    )
    return
