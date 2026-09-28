"""
.. module:: test_p31l_adm_form_field_errors_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Admin forms show a refused value's error next to its
               field and keep what was typed (ADM-11).

.. moduleauthor:: Code Craft AI LLC

Every admin form used to flash ``str(exc)`` above the page, never set
``aria-invalid``, and several edit forms threw away what was typed.
A validation error that names a field now renders next to that field
(``<name>-error``, ``aria-invalid``, ``aria-describedby``), is listed
in the error summary at the top of the form, and the form comes back
with the submitted values and a 400.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re
import uuid

from typing import Any, Dict

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    post_form,
)


GOOD_PASSWORD: str = "Correct-Horse-Battery-9"


def _setup() -> Dict[str, Any]:
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    rtnval = {"wsgi_app": handle.wsgi_app, "cookies": cookies}
    return rtnval


def _unique(prefix: str) -> str:
    rtnval = "{}-{}".format(prefix, uuid.uuid4().hex[:8])
    return rtnval


def _create_user(setup: Dict[str, Any], **overrides: str) -> Any:
    fields = {
        "username": _unique("fe"),
        "email": "{}@example.com".format(_unique("fe")),
        "password_setup": "password",
        "password": GOOD_PASSWORD,
        "display_name": "Field Errors",
        "firstname": "",
        "lastname": "",
    }
    fields.update(overrides)
    rtnval = post_form(
        wsgi_app=setup["wsgi_app"], path="/admin/users/create", cookies=setup["cookies"], fields=fields,
    )
    return rtnval


def _user_id_for(setup: Dict[str, Any], *, username: str) -> str:
    page = drive_request(
        wsgi_app=setup["wsgi_app"], method="GET", path="/admin/users",
        query_string="search=" + username, cookies=setup["cookies"],
    ).text
    match = re.search(r'href="/admin/users/([0-9a-f-]{36})"[^>]*>\s*' + re.escape(username), page)
    testbase.assert_true(match is not None, "user {} not listed".format(username))
    rtnval = match.group(1)
    return rtnval


def _input_tag(html: str, *, field_id: str) -> str:
    match = re.search(r'<input[^>]*\bid="' + re.escape(field_id) + r'"[^>]*>', html, re.S)
    rtnval = match.group(0) if match is not None else ""
    return rtnval


def test_create_user_bad_email_is_shown_next_to_the_email_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: creating a user with email "not-an-email@x" is refused
    with a 400 whose email input is aria-invalid and described by the
    email-error message.**
    """
    setup = _setup()
    response = _create_user(setup, email="not-an-email@x")
    email_input = _input_tag(response.text, field_id="email")

    testbase.assert_equal(
        (response.status_code, 'id="email-error"' in response.text,
         'aria-invalid="true"' in email_input, 'aria-describedby="email-error"' in email_input),
        (400, True, True, True),
    )
    return


def test_create_user_error_is_listed_in_the_summary_with_a_link_to_its_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: the refused create page opens with an error summary
    that links to the email input.**
    """
    setup = _setup()
    response = _create_user(setup, email="not-an-email@x")

    testbase.assert_equal(
        ('data-role="error-summary"' in response.text, 'href="#email"' in response.text),
        (True, True),
    )
    return


def test_create_user_refusal_keeps_the_typed_values():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: after a refused create the username and first name the
    admin typed are still in the form.**
    """
    setup = _setup()
    username = _unique("keep")
    response = _create_user(setup, username=username, firstname="Grace", email="broken@")

    testbase.assert_equal(
        ('value="{}"'.format(username) in _input_tag(response.text, field_id="username"),
         'value="Grace"' in _input_tag(response.text, field_id="firstname")),
        (True, True),
    )
    return


def test_create_user_duplicate_username_is_shown_next_to_the_username_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: a second user with an existing username is refused with
    the error next to the username input.**
    """
    setup = _setup()
    username = _unique("dup")
    _create_user(setup, username=username)
    response = _create_user(setup, username=username)

    testbase.assert_equal(
        (response.status_code, 'id="username-error"' in response.text),
        (400, True),
    )
    return


def test_password_error_keeps_the_rules_description_on_the_input():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: a refused password leaves the password input described
    by both the password rules and the error (one aria-describedby).**
    """
    setup = _setup()
    response = _create_user(setup, password="short")
    password_input = _input_tag(response.text, field_id="password")

    testbase.assert_equal(
        (response.status_code, password_input.count("aria-describedby="),
         'aria-describedby="password-rules password-error"' in password_input),
        (400, 1, True),
    )
    return


def test_edit_user_bad_email_keeps_the_typed_values_and_marks_the_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: saving a user's edit form with email "broken@" answers
    400, marks the email input, and keeps the display name that was
    typed rather than the stored one.**
    """
    setup = _setup()
    username = _unique("edit")
    _create_user(setup, username=username)
    user_id = _user_id_for(setup, username=username)
    response = post_form(
        wsgi_app=setup["wsgi_app"],
        path="/admin/users/{}/edit".format(user_id),
        cookies=setup["cookies"],
        fields={"email": "broken@", "display_name": "Typed Name", "firstname": "", "lastname": "", "is_active": "on"},
    )

    testbase.assert_equal(
        (response.status_code, 'id="email-error"' in response.text,
         'value="Typed Name"' in _input_tag(response.text, field_id="display_name"),
         'value="broken@"' in _input_tag(response.text, field_id="email")),
        (400, True, True, True),
    )
    return
