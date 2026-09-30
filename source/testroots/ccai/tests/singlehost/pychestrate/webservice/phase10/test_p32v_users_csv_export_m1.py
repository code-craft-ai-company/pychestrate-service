"""
.. module:: test_p32v_users_csv_export_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The users list downloads as a spreadsheet for an access review (ORG-F22).

.. moduleauthor:: Code Craft AI LLC

An auditor asking "who has an account, can they sign in, and what may they do" could only read the
Users page a page at a time. ``GET /admin/users?format=csv`` returns every user the page's search
matches (not one page) as a CSV attachment: username, email, display name, status, the roles held
everywhere, and when the account was created. Every cell is written so a spreadsheet cannot read it as
a formula (a display name is typed by whoever made the account). It needs the same permission as the
page; the page links to it with its current search.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import csv
import io
import re
import uuid

from typing import Any, Dict, List

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_app,
    ensure_seeded_viewer,
    grant_role_to_user,
    login_as,
)


GOOD_PASSWORD: str = "Correct-Horse-Battery-9"


def _unique(prefix: str) -> str:
    return "{}-{}".format(prefix, uuid.uuid4().hex[:8])


def _make_user(cookies: Dict[str, str], *, username: str, display_name: str = "CSV Person") -> str:
    response = adm.post_form(
        path="/admin/users/create", cookies=cookies,
        fields={
            "username": username, "email": "{}@example.com".format(username), "password_setup": "password",
            "password": GOOD_PASSWORD, "display_name": display_name, "firstname": "", "lastname": "",
        },
    )
    testbase.assert_equal(response.status_code in (302, 303), True, response.text[:200])
    page = adm.get(path="/admin/users", cookies=cookies, query={"search": username}).text
    match = re.search(r'href="/admin/users/([0-9a-f-]{36})"[^>]*>\s*' + re.escape(username), page)
    testbase.assert_true(match is not None, "user not listed")
    return match.group(1)


def _rows(body: str) -> List[Dict[str, str]]:
    return list(csv.DictReader(io.StringIO(body)))


def test_the_export_is_every_matching_user_with_their_roles_as_an_attachment():
    """
    **Feature: users export (ORG-F22)**
    **Property: ``format=csv`` answers 200 ``text/csv`` as an attachment named for users, with the
    documented header and a row per user; ``search`` narrows it; a user's system roles are listed and a
    user with none has an empty cell; page size does not apply.**
    """
    cookies = adm.admin_cookies()
    tag = _unique("csvx")
    plain = _make_user(cookies, username=tag + "-plain")
    audited = _make_user(cookies, username=tag + "-audit")
    grant_role_to_user(user_id=audited, role_name="auditor")

    everything = adm.get(path="/admin/users", cookies=cookies, query={"format": "csv", "per_page": "1"})
    narrowed = adm.get(path="/admin/users", cookies=cookies, query={"format": "csv", "search": tag})
    by_name = {row["username"]: row for row in _rows(narrowed.text)}

    testbase.assert_equal(
        (
            everything.status_code, (everything.header("Content-Type") or "").split(";")[0],
            (everything.header("Content-Disposition") or "").startswith('attachment; filename="pychestrate-users-'),
            list(_rows(everything.text)[0].keys()), len(_rows(everything.text)) >= 3,
            sorted(by_name), by_name[tag + "-plain"]["system_roles"], by_name[tag + "-audit"]["system_roles"],
            by_name[tag + "-plain"]["status"], by_name[tag + "-plain"]["email"], bool(by_name[tag + "-plain"]["created_at"]),
        ),
        (
            200, "text/csv", True, ["username", "email", "display_name", "status", "system_roles", "created_at"], True,
            [tag + "-audit", tag + "-plain"], "", "auditor", "active", tag + "-plain@example.com", True,
        ),
    )
    return


def test_a_display_name_that_would_be_a_formula_is_written_as_text():
    """
    **Feature: users export (ORG-F22)**
    **Property: a display name of ``=HYPERLINK(...)`` comes back from a CSV parser with an apostrophe in
    front, so a spreadsheet shows it and does not run it.**
    """
    cookies = adm.admin_cookies()
    name = _unique("csvf")
    _make_user(cookies, username=name, display_name='=HYPERLINK("http://x","y")')
    rows = _rows(adm.get(path="/admin/users", cookies=cookies, query={"format": "csv", "search": name}).text)

    testbase.assert_equal([row["display_name"] for row in rows], ["'=HYPERLINK(\"http://x\",\"y\")"])
    return


def test_a_person_who_may_not_read_users_gets_no_export_and_the_page_links_to_it_with_its_search():
    """
    **Feature: users export (ORG-F22)**
    **Property: a signed-in user without the users permission is refused the export like the page
    (403, no CSV); the Users page has a Download CSV link that carries the current search.**
    """
    cookies = adm.admin_cookies()
    viewer = login_as(wsgi_app=ensure_app().wsgi_app, user=ensure_seeded_viewer())
    refused = adm.get(path="/admin/users", cookies=viewer, query={"format": "csv"})
    page = adm.get(path="/admin/users", cookies=cookies, query={"search": "ada lovelace"}).text
    bare = adm.get(path="/admin/users", cookies=cookies).text

    testbase.assert_equal(
        (
            refused.status_code, "text/csv" in (refused.header("Content-Type") or ""),
            'data-role="download-csv"' in page, "?format=csv&amp;search=ada%20lovelace" in page or "?format=csv&search=ada%20lovelace" in page,
            "?format=csv" in bare and "search=" not in re.search(r'<a[^>]*data-role="download-csv"[^>]*>', bare).group(0),
        ),
        (403, False, True, True, True),
    )
    return
