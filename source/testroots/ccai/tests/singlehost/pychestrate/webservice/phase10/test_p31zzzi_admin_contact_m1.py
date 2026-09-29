"""
.. module:: test_p31zzzi_admin_contact_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A refused person is told whom to ask for access (XC-21).

.. moduleauthor:: Code Craft AI LLC

"Ask an administrator" never said who that is. The installation names a contact
in ``PYCHESTRATE_ADMIN_CONTACT``; the 403 page adds "To ask for access, contact
<contact>." and the shell document carries it for the no-access screen. Nothing
is added when no contact is configured. These tests read the contact's
normalisation, the real 403 page a user with no role receives, and the shell
document rendered in the strict template environment with a hostile value.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import os

from contextlib import contextmanager
from typing import Iterator, Optional

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.site_shell.admin_contact import (
    ENV_ADMIN_CONTACT,
    MAX_CONTACT_LENGTH,
    access_request_sentence,
    admin_contact,
)

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    app,
    get,
    post_form,
    unique_name,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    login_via_post,
)
from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import strict_environment


_PASSWORD: str = "Granite-Harbor-47!"

_NO_ROLE_COOKIES = {}


@contextmanager
def _contact(value: Optional[str]) -> Iterator[None]:
    """Sets (or clears, with ``None``) the contact variable for a block, then restores it."""
    previous = os.environ.get(ENV_ADMIN_CONTACT)
    if value is None:
        os.environ.pop(ENV_ADMIN_CONTACT, None)
    else:
        os.environ[ENV_ADMIN_CONTACT] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(ENV_ADMIN_CONTACT, None)
        else:
            os.environ[ENV_ADMIN_CONTACT] = previous


def _no_role_cookies():
    if len(_NO_ROLE_COOKIES) == 0:
        login_name = unique_name(prefix="norole")
        response = post_form(
            path="/admin/users/create",
            fields={"username": login_name, "email": "{}@example.com".format(login_name),
                    "password": _PASSWORD, "display_name": "No Role"},
            cookies=admin_cookies(),
        )
        testbase.assert_equal(response.status_code, 303)
        login_response, cookies = login_via_post(wsgi_app=app(), login=login_name, password=_PASSWORD)
        testbase.assert_equal(login_response.status_code, 303)
        _NO_ROLE_COOKIES.update(cookies)
    return dict(_NO_ROLE_COOKIES)


def test_the_contact_is_one_short_line_or_nothing():
    """
    **Feature: whom to ask for access (XC-21)**
    **Property: no variable (or a blank one) gives no contact and no sentence;
    line breaks and runs of spaces collapse to single spaces; a value longer
    than the limit is cut.**
    """
    with _contact(None):
        unset = (admin_contact(), access_request_sentence())
    with _contact("   \n "):
        blank = (admin_contact(), access_request_sentence())
    with _contact("  Platform team\r\n  (#help-pychestrate) "):
        tidy = (admin_contact(), access_request_sentence())
    with _contact("x" * (MAX_CONTACT_LENGTH + 50)):
        cut = len(admin_contact())

    testbase.assert_equal(
        (unset, blank, tidy, cut),
        (
            ("", ""), ("", ""),
            ("Platform team (#help-pychestrate)", "To ask for access, contact Platform team (#help-pychestrate)."),
            MAX_CONTACT_LENGTH,
        ),
    )
    return


def test_the_403_page_names_whom_to_ask_only_when_someone_is_configured():
    """
    **Feature: whom to ask for access (XC-21)**
    **Property: a user with no role who opens an admin page gets the 403 page,
    which ends with the contact sentence when a contact is configured and says
    nothing extra when it is not.**
    """
    with _contact("ops@lab.example"):
        refused = get(path="/admin/users", cookies=_no_role_cookies())
    status, with_contact = refused.status_code, html.unescape(refused.text)
    with _contact(None):
        without = html.unescape(get(path="/admin/users", cookies=_no_role_cookies()).text)

    testbase.assert_equal(
        (status, "To ask for access, contact ops@lab.example." in with_contact, "To ask for access" in without, "Ask an administrator" in without),
        (403, True, False, True),
    )
    return


def test_the_shell_document_carries_the_contact_escaped_and_only_when_set():
    """
    **Feature: whom to ask for access (XC-21)**
    **Property: the shell element has an ``admin-contact`` attribute when a
    contact is given and none otherwise, and a value that tries to close the
    attribute and start a script is escaped.**
    """
    template = strict_environment().get_template("site_shell/shell_document.html")
    base = dict(
        page_title="P", initial_route="/", bundle_names=["pyc-site-shell"], bundle_stylesheets=[], content_html="",
        csrf_token="", user_display_name="", user_login_name="", service_version="", user_guide_url="",
    )
    plain = template.render(admin_contact="ops@lab.example", **base)
    none = template.render(admin_contact="", **base)
    hostile = template.render(admin_contact='x"><script>alert(1)</script>', **base)

    testbase.assert_equal(
        ('admin-contact="ops@lab.example"' in plain, "admin-contact" in none, "<script>alert(1)" in hostile, "&lt;script&gt;" in hostile),
        (True, False, False, True),
    )
    return
