"""
.. module:: test_p40h_setup_wizard_forms_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the first-run setup pages' field errors and the
               unlock page's token path.

.. moduleauthor:: Code Craft AI LLC

Audit findings LD-06 and LD-05. The create-administrator form listed
every problem at the top of the page, and no field carried an error
state. Each message now sits under its field, which is marked
``aria-invalid`` and described by it, and the first invalid field takes
focus. The unlock page hid long token paths in a scroll box that
keyboards could not reach, with no way to copy them. The paths now wrap
and each has a Copy button.

**Feature: first-run setup (LD-05/LD-06)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from typing import Any, Dict, Optional

from ccai import testbase

from ccai.pychestrate.webservice.security.auth.password_policy import (
    password_policy_template_context,
)
from ccai.pychestrate.webservice.webinterface.blueprints.setup import routes as setup_routes

from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    strict_environment,
)


def _render_admin(*, field_errors: Dict[str, str], first_invalid: Optional[str]) -> str:
    context = {
        "form_values": {"login_name": "ops-admin", "email": "not-an-email", "display_name": ""},
        "min_password_length": setup_routes.MIN_PASSWORD_LENGTH,
        "error": " ".join(field_errors.values()) or None,
        "errors": list(field_errors.values()),
        "field_errors": field_errors,
        "first_invalid": first_invalid,
    }
    # The handler merges the password policy's rule text, bounds and
    # pattern into every render (ADM-17).
    context.update(password_policy_template_context())
    rtnval = strict_environment().get_template("setup/admin.html").render(**context)
    return rtnval


def _input_tag(html: str, field_id: str) -> str:
    match = re.search(r'<input[^>]*\bid="{}"[^>]*>'.format(re.escape(field_id)), html)
    rtnval = match.group(0) if match is not None else ""
    return rtnval


def _form_group(html: str, field_id: str) -> str:
    """
        The ``form-group`` block that holds the field ``field_id``.
    """
    for block in html.split('<div class="form-group">')[1:]:
        if 'id="{}"'.format(field_id) in block:
            rtnval = block
            return rtnval
    return ""


def test_each_setup_problem_is_keyed_to_its_field_in_form_order():
    """
    **Feature: first-run setup (LD-06)**
    **Property: validating the create-administrator form names the field
    each problem belongs to, in the order the fields appear.**
    """
    # A password the policy accepts (ADM-17), so only the three
    # problems under test are reported.
    field_errors = setup_routes._collect_admin_field_errors(
        login_name="ok-admin",
        email="not-an-email",
        password="Granite-Harbor-47!",
        password_confirm="Granite-Harbor-47?",
        display_name="",
    )
    testbase.assert_equal(list(field_errors), ["email", "display_name", "password_confirm"])
    return


def test_an_invalid_field_is_marked_and_described_by_its_own_message():
    """
    **Feature: first-run setup (LD-06)**
    **Property: a field with a problem carries aria-invalid and
    aria-describedby pointing at a message shown in the same form group,
    under the field.**
    """
    html = _render_admin(field_errors={"email": "Email address looks invalid."}, first_invalid="email")
    tag = _input_tag(html, "email")
    group = _form_group(html, "email")
    testbase.assert_equal(
        ('aria-invalid="true"' in tag, 'aria-describedby="email-error"' in tag,
         'id="email-error"' in group and "Email address looks invalid." in group),
        (True, True, True),
    )
    return


def test_a_valid_field_carries_no_error_state():
    """
    **Feature: first-run setup (LD-06)**
    **Property: fields without a problem are not marked invalid, while a
    field with one is.**
    """
    html = _render_admin(field_errors={"email": "Email address looks invalid."}, first_invalid="email")
    testbase.assert_equal(
        [field for field in ("login_name", "email", "display_name", "password", "password_confirm")
         if 'aria-invalid="true"' in _input_tag(html, field)],
        ["email"],
    )
    return


def test_the_first_invalid_field_takes_focus():
    """
    **Feature: first-run setup (LD-06)**
    **Property: after a failed submission the first field with a problem
    is the only one with autofocus.**
    """
    html = _render_admin(
        field_errors={"display_name": "Display name is required.",
                      "password_confirm": "Password and confirmation do not match."},
        first_invalid="display_name",
    )
    testbase.assert_equal(
        [field for field in ("login_name", "email", "display_name", "password", "password_confirm")
         if "autofocus" in _input_tag(html, field)],
        ["display_name"],
    )
    return


def test_the_error_summary_links_each_problem_to_its_field():
    """
    **Feature: first-run setup (LD-06)**
    **Property: the summary at the top counts the problems and links each
    one to its field.**
    """
    html = _render_admin(
        field_errors={"email": "Email address looks invalid.",
                      "password_confirm": "Password and confirmation do not match."},
        first_invalid="email",
    )
    testbase.assert_equal(
        ("Fix the 2 fields marked below" in html, '<a href="#email">' in html,
         '<a href="#password_confirm">' in html),
        (True, True, True),
    )
    return


def test_the_unlock_page_offers_to_copy_the_path_and_the_command():
    """
    **Feature: first-run setup (LD-05)**
    **Property: the token path and the command that prints it each have a
    Copy button wired to the element holding the text.**
    """
    path = "/var/lib/pychestrate/presence/instances/production-east-1/runtime/initial-admin-token.txt"
    html = strict_environment().get_template("setup/unlock.html").render(token_path=path, error=None)
    testbase.assert_equal(
        ('<pre class="path" id="token-path">{}</pre>'.format(path) in html,
         '<pre class="path" id="token-command">sudo cat {}</pre>'.format(path) in html,
         'data-copy-from="token-path"' in html, 'data-copy-from="token-command"' in html),
        (True, True, True, True),
    )
    return


def test_long_token_paths_wrap_instead_of_scrolling():
    """
    **Feature: first-run setup (LD-05)**
    **Property: the token path blocks wrap long paths rather than hiding
    them in a horizontal scroll box keyboards cannot reach.**
    """
    html = strict_environment().get_template("setup/unlock.html").render(token_path="/x", error=None)
    rule = re.search(r"\.setup-card pre\.path \{(.*?)\}", html, re.S)
    body = rule.group(1) if rule is not None else ""
    testbase.assert_equal(
        ("overflow-wrap: anywhere" in body, "white-space: pre-wrap" in body, "overflow-x" in body),
        (True, True, False),
    )
    return
