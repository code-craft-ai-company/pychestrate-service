"""
.. module:: test_p31o_adm_password_token_member_field_errors_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The password, API token, service account and project
               member forms show a refused value's error next to its
               field (ADM-11).

.. moduleauthor:: Code Craft AI LLC

The first pass at ADM-11 converted the admin forms that create and edit
things. What was left: the four password pages (they listed their
problems above the form), the API token and service account forms, and
the project member forms. Each now renders the error next to the input
it is about (``<name>-error``, ``aria-invalid``, ``aria-describedby``),
lists it in the error summary at the top, keeps what was typed, and
answers 400. An error about no single input (an inactive account, say)
stays a banner. Sign-in stays generic on purpose.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import re
import uuid

from typing import Any, Dict, Tuple

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    app,
    get,
    merge_cookies,
    open_db_session,
    post_form,
    unique_name,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_seeded_user,
    login_via_post,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
)


START_PASSWORD: str = "Granite-Harbor-47!"
TEMP_PASSWORD: str = "Temporary-Lantern-83!"
NEW_PASSWORD: str = "Copper-Meadow-59#"

#: Long enough and a run of one letter: breaks several policy rules.
WEAK_PASSWORD: str = "aaaaaaaaaaaa"

LINK_PATTERN = re.compile(r'value="([^"]*/password/set/([^"]+))"')


def _tag(page: str, *, element: str, field_id: str) -> str:
    """
        The opening tag of the ``element`` (``input``, ``select``) with
        this id, or an empty string.
    """
    match = re.search(r"<" + element + r'[^>]*\bid="' + re.escape(field_id) + r'"[^>]*>', page, re.S)
    rtnval = match.group(0) if match is not None else ""
    return rtnval


def _error_text(page: str, *, field_id: str) -> str:
    """
        The message shown in ``<field_id>-error``, or an empty string.
    """
    match = re.search(r'id="' + re.escape(field_id) + r'-error"[^>]*>(.*?)</div>', page, re.S)
    rtnval = html.unescape(match.group(1).strip()) if match is not None else ""
    return rtnval


def _flagged(page: str, *, field_id: str, element: str = "input") -> Tuple[bool, bool]:
    """
        ``(aria-invalid, described by its own error)`` for the input.
    """
    tag = _tag(page, element=element, field_id=field_id)
    rtnval = (
        'aria-invalid="true"' in tag,
        (field_id + "-error") in tag and "aria-describedby" in tag,
    )
    return rtnval


def _summary_links_to(page: str, *, field_id: str) -> bool:
    rtnval = 'data-role="error-summary"' in page and ('href="#{}"'.format(field_id)) in page
    return rtnval


def _create_user(*, prefix: str = "fe") -> Tuple[str, str]:
    login_name = unique_name(prefix=prefix)
    response = post_form(
        path="/admin/users/create",
        fields={
            "username": login_name,
            "email": "{}@example.com".format(login_name),
            "password": START_PASSWORD,
            "display_name": "Field Errors",
        },
        cookies=admin_cookies(),
    )
    testbase.assert_equal(response.status_code, 303)
    from ccai.pychestrate.webservice.identity.users.models import IdentityUser  # noqa: E402
    db_session = open_db_session()
    try:
        row = db_session.query(IdentityUser).filter(IdentityUser.login_name == login_name).one()
        user_id = str(row.user_id)
    finally:
        db_session.close()
    rtnval = (login_name, user_id)
    return rtnval


def _signed_in(*, prefix: str = "fe") -> Tuple[str, str, Dict[str, str]]:
    login_name, user_id = _create_user(prefix=prefix)
    _response, cookies = login_via_post(wsgi_app=app(), login=login_name, password=START_PASSWORD)
    rtnval = (login_name, user_id, cookies)
    return rtnval


# ===========================================================================
# Change password (self-service)
# ===========================================================================


def _change_own_password(*, cookies: Dict[str, str], **fields: str) -> Any:
    body = {"current_password": START_PASSWORD, "password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD}
    body.update(fields)
    rtnval = post_form(path="/account/password", fields=body, cookies=cookies)
    return rtnval


def test_a_wrong_current_password_is_shown_next_to_that_input():
    """
    **Feature: password form field errors (ADM-11)**
    **Property: Change password with a wrong current password answers
    400 with the message beside the current-password input, which is
    aria-invalid and described by it, and the summary links to it.**
    """
    _login, _uid, cookies = _signed_in()
    response = _change_own_password(cookies=cookies, current_password="Wrong-Password-11!")

    testbase.assert_equal(
        (response.status_code,
         _error_text(response.text, field_id="current_password"),
         _flagged(response.text, field_id="current_password"),
         _summary_links_to(response.text, field_id="current_password")),
        (400, "The current password is not correct.", (True, True), True),
    )
    return


def test_a_mismatched_confirmation_is_shown_next_to_the_confirmation():
    """
    **Feature: password form field errors (ADM-11)**
    **Property: a confirmation that differs from the new password is
    reported on the confirmation input, not on the new password.**
    """
    _login, _uid, cookies = _signed_in()
    response = _change_own_password(cookies=cookies, password_confirm="Something-Else-77!")

    testbase.assert_equal(
        (response.status_code,
         _error_text(response.text, field_id="password_confirm"),
         _flagged(response.text, field_id="password_confirm"),
         _flagged(response.text, field_id="password")),
        (400, "The new passwords do not match.", (True, True), (False, False)),
    )
    return


def test_a_weak_new_password_is_shown_next_to_the_new_password_with_the_rules_kept():
    """
    **Feature: password form field errors (ADM-11)**
    **Property: a password that breaks the policy is reported beside the
    new-password input, which stays described by the rules list as well
    as by its error.**
    """
    _login, _uid, cookies = _signed_in()
    response = _change_own_password(cookies=cookies, password=WEAK_PASSWORD, password_confirm=WEAK_PASSWORD)
    tag = _tag(response.text, element="input", field_id="password")

    testbase.assert_equal(
        (response.status_code,
         len(_error_text(response.text, field_id="password")) > 0,
         'aria-invalid="true"' in tag,
         "password-rules" in tag and "password-error" in tag),
        (400, True, True, True),
    )
    return


# ===========================================================================
# Admin sets a temporary password
# ===========================================================================


def test_an_admin_password_that_breaks_the_policy_is_shown_next_to_the_input():
    """
    **Feature: password form field errors (ADM-11)**
    **Property: setting a weak temporary password reports the rules on
    the new-password input of the admin's form.**
    """
    _login, user_id = _create_user()
    response = post_form(
        path="/admin/users/{}/password".format(user_id),
        fields={"password": WEAK_PASSWORD, "password_confirm": WEAK_PASSWORD, "must_change": "1"},
        cookies=admin_cookies(),
    )

    testbase.assert_equal(
        (response.status_code,
         len(_error_text(response.text, field_id="password")) > 0,
         _flagged(response.text, field_id="password")[0],
         _summary_links_to(response.text, field_id="password")),
        (400, True, True, True),
    )
    return


def test_an_admin_confirmation_mismatch_is_shown_next_to_the_confirmation():
    """
    **Feature: password form field errors (ADM-11)**
    **Property: a temporary password whose confirmation differs is
    reported on the confirmation input.**
    """
    _login, user_id = _create_user()
    response = post_form(
        path="/admin/users/{}/password".format(user_id),
        fields={"password": TEMP_PASSWORD, "password_confirm": "Not-The-Same-99!"},
        cookies=admin_cookies(),
    )

    testbase.assert_equal(
        (response.status_code,
         _error_text(response.text, field_id="password_confirm"),
         _flagged(response.text, field_id="password_confirm")),
        (400, "The passwords do not match.", (True, True)),
    )
    return


# ===========================================================================
# Password link and forced change (pages without a session)
# ===========================================================================


def _link_page(*, user_id: str) -> Tuple[str, Dict[str, str]]:
    issued = post_form(
        path="/admin/users/{}/password-link".format(user_id), fields={}, cookies=admin_cookies(),
    )
    match = LINK_PATTERN.search(issued.text)
    testbase.assert_true(match is not None, "no link on the page")
    secret = html.unescape(match.group(2))
    form_page = get(path="/password/set/{}".format(secret))
    rtnval = (secret, form_page.collect_set_cookies())
    return rtnval


def test_a_reset_link_password_that_breaks_the_policy_is_shown_next_to_the_input():
    """
    **Feature: password form field errors (ADM-11)**
    **Property: choosing a weak password on the reset-link page reports
    the rules beside the password input.**
    """
    _login, user_id = _create_user()
    secret, cookies = _link_page(user_id=user_id)
    response = post_form(
        path="/password/set/{}".format(secret),
        fields={"password": WEAK_PASSWORD, "password_confirm": WEAK_PASSWORD},
        cookies=cookies,
    )

    testbase.assert_equal(
        (response.status_code,
         len(_error_text(response.text, field_id="password")) > 0,
         _flagged(response.text, field_id="password")[0]),
        (400, True, True),
    )
    return


def test_a_reset_link_confirmation_mismatch_is_shown_next_to_the_confirmation():
    """
    **Feature: password form field errors (ADM-11)**
    **Property: on the reset-link page a differing confirmation is
    reported on the confirmation input.**
    """
    _login, user_id = _create_user()
    secret, cookies = _link_page(user_id=user_id)
    response = post_form(
        path="/password/set/{}".format(secret),
        fields={"password": NEW_PASSWORD, "password_confirm": "Different-Words-31!"},
        cookies=cookies,
    )

    testbase.assert_equal(
        (response.status_code,
         _error_text(response.text, field_id="password_confirm"),
         _flagged(response.text, field_id="password_confirm")),
        (400, "The passwords do not match.", (True, True)),
    )
    return


def test_a_wrong_temporary_password_is_shown_next_to_that_input():
    """
    **Feature: password form field errors (ADM-11)**
    **Property: on the forced-change page a wrong temporary password is
    reported beside the temporary-password input.**
    """
    login_name, user_id = _create_user()
    set_response = post_form(
        path="/admin/users/{}/password".format(user_id),
        fields={"password": TEMP_PASSWORD, "password_confirm": TEMP_PASSWORD, "must_change": "1"},
        cookies=admin_cookies(),
    )
    testbase.assert_equal(set_response.status_code, 303)
    _response, cookies = login_via_post(wsgi_app=app(), login=login_name, password=TEMP_PASSWORD)
    page = get(path="/password/change-required", cookies=cookies)
    response = post_form(
        path="/password/change-required",
        fields={"current_password": "Wrong-Password-11!", "password": NEW_PASSWORD,
                "password_confirm": NEW_PASSWORD},
        cookies=merge_cookies(cookies=cookies, response=page),
    )

    testbase.assert_equal(
        (response.status_code,
         _error_text(response.text, field_id="current_password"),
         _flagged(response.text, field_id="current_password")),
        (400, "The current password is not correct.", (True, True)),
    )
    return


# ===========================================================================
# API tokens and service accounts
# ===========================================================================


def test_a_blank_token_name_is_shown_next_to_the_name_and_keeps_the_other_choices():
    """
    **Feature: token form field errors (ADM-11)**
    **Property: creating a token with a blank name answers 400 with the
    message beside the name input, and the lifetime and access the
    person chose are still selected.**
    """
    _login, _uid, cookies = _signed_in()
    response = post_form(
        path="/account/api-tokens/create",
        fields={"name": "   ", "expires_in_days": "30", "scope": "read-only"},
        cookies=cookies,
    )
    expires = _tag(response.text, element="select", field_id="expires_in_days")
    chosen_days = re.search(r'<option value="30"\s+selected', response.text)
    chosen_scope = re.search(r'<option value="read-only"\s+selected', response.text)

    testbase.assert_equal(
        (response.status_code,
         _error_text(response.text, field_id="name"),
         _flagged(response.text, field_id="name"),
         _summary_links_to(response.text, field_id="name"),
         chosen_days is not None, chosen_scope is not None, len(expires) > 0),
        (400, "A token name is required.", (True, True), True, True, True, True),
    )
    return


def test_a_taken_service_account_name_is_shown_next_to_the_login_name():
    """
    **Feature: token form field errors (ADM-11)**
    **Property: creating a service account whose login name exists
    answers 400 with the message beside the login name input, and the
    display name that was typed is kept.**
    """
    cookies = admin_cookies()
    taken = unique_name(prefix="sa-taken")
    first = post_form(
        path="/admin/service-accounts/create",
        fields={"login_name": taken, "display_name": "First"},
        cookies=cookies,
    )
    testbase.assert_equal(first.status_code, 303)
    response = post_form(
        path="/admin/service-accounts/create",
        fields={"login_name": taken, "display_name": "Kept display name"},
        cookies=cookies,
    )

    testbase.assert_equal(
        (response.status_code,
         taken in _error_text(response.text, field_id="login_name"),
         _flagged(response.text, field_id="login_name"),
         'value="Kept display name"' in _tag(response.text, element="input", field_id="display_name")),
        (400, True, (True, True), True),
    )
    return


def test_a_blank_service_account_token_name_is_shown_in_that_accounts_row():
    """
    **Feature: token form field errors (ADM-11)**
    **Property: issuing a token for a service account with a blank name
    answers 400 with the message beside that account's name input, its
    row open, and the summary linking to it.**
    """
    cookies = admin_cookies()
    login_name = unique_name(prefix="sa-issue")
    created = post_form(
        path="/admin/service-accounts/create",
        fields={"login_name": login_name, "display_name": "Issuer"},
        cookies=cookies,
    )
    testbase.assert_equal(created.status_code, 303)
    listing = get(path="/admin/api-tokens", cookies=cookies)
    row = re.search(
        r'<td class="mono">' + re.escape(login_name) + r"</td>.*?/admin/service-accounts/([0-9a-f-]{36})/api-tokens/create",
        listing.text, re.S,
    )
    testbase.assert_true(row is not None, "no issue form for the new account")
    account_id = row.group(1)

    response = post_form(
        path="/admin/service-accounts/{}/api-tokens/create".format(account_id),
        fields={"name": " ", "expires_in_days": "7", "scope": "read-write"},
        cookies=cookies,
    )
    input_id = "sa-token-name-" + account_id
    row_is_open = re.search(
        r"<details[^>]*\bopen\b[^>]*>(?:(?!</details>).)*?" + re.escape('id="' + input_id + '"'),
        response.text, re.S,
    )

    testbase.assert_equal(
        (response.status_code,
         _error_text(response.text, field_id=input_id),
         _flagged(response.text, field_id=input_id),
         _summary_links_to(response.text, field_id=input_id),
         row_is_open is not None),
        (400, "A token name is required.", (True, True), True, True),
    )
    return


# ===========================================================================
# Project members
# ===========================================================================


def _project_with_member(*, role: str) -> Tuple[int, str, Dict[str, str]]:
    from ccai.pychestrate.core.managers.project_manager import (  # noqa: E402
        ProjectManager,
        ProjectRole,
    )
    cookies = admin_cookies()
    project_id = create_project_via_ui(wsgi_app=app(), cookies=cookies, prefix="fe-members")
    member = ensure_seeded_user(login="fe-member-" + uuid.uuid4().hex[:8])
    db_session = open_db_session()
    try:
        ProjectManager(db_session).add_member(project_id, member.user_id, ProjectRole(role), member.user_id)
    finally:
        db_session.close()
    rtnval = (project_id, member.user_id, cookies)
    return rtnval


def test_an_unknown_role_is_shown_next_to_the_role_when_adding_a_member():
    """
    **Feature: member form field errors (ADM-11)**
    **Property: adding a member with a role that does not exist answers
    400 with the message beside the role select.**
    """
    cookies = admin_cookies()
    project_id = create_project_via_ui(wsgi_app=app(), cookies=cookies, prefix="fe-add")
    member = ensure_seeded_user(login="fe-add-" + uuid.uuid4().hex[:8])
    response = post_form(
        path="/projects/{}/members/add".format(project_id),
        fields={"user_id": member.user_id, "role": "emperor"},
        cookies=cookies,
    )

    testbase.assert_equal(
        (response.status_code,
         _error_text(response.text, field_id="role"),
         _flagged(response.text, field_id="role", element="select"),
         re.search(r'<option value="{}"\s+selected'.format(re.escape(member.user_id)), response.text) is not None),
        (400, "Choose one of the listed roles.", (True, True), True),
    )
    return


def test_no_user_is_shown_next_to_the_user_when_adding_a_member():
    """
    **Feature: member form field errors (ADM-11)**
    **Property: submitting the add-member form without choosing a user
    answers 400 with the message beside the user select.**
    """
    cookies = admin_cookies()
    project_id = create_project_via_ui(wsgi_app=app(), cookies=cookies, prefix="fe-nouser")
    response = post_form(
        path="/projects/{}/members/add".format(project_id),
        fields={"user_id": "", "role": "developer"},
        cookies=cookies,
    )

    testbase.assert_equal(
        (response.status_code,
         _error_text(response.text, field_id="user_id"),
         _flagged(response.text, field_id="user_id", element="select"),
         _summary_links_to(response.text, field_id="user_id")),
        (400, "Choose a user to add to the project.", (True, True), True),
    )
    return


def test_changing_the_owners_role_is_shown_next_to_the_role():
    """
    **Feature: member form field errors (ADM-11)**
    **Property: changing the project owner's role answers 400 with the
    manager's message beside the role select, and the role that was
    picked stays selected.**
    """
    project_id, user_id, cookies = _project_with_member(role="owner")
    response = post_form(
        path="/projects/{}/members/{}/edit".format(project_id, user_id),
        fields={"role": "viewer"},
        cookies=cookies,
    )

    testbase.assert_equal(
        (response.status_code,
         _error_text(response.text, field_id="role"),
         _flagged(response.text, field_id="role", element="select"),
         re.search(r'<option value="viewer"\s+selected', response.text) is not None),
        (400, "Cannot change the project owner's role", (True, True), True),
    )
    return
