"""
.. module:: test_p31f_adm_password_lifecycle_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Password lifecycle: admin reset with forced change,
               single-use reset / invite links, and self-service change
               (audit ADM-04).

.. moduleauthor:: Code Craft AI LLC

A user who forgot their password was locked out for good (an
administrator could not set a new one), and nobody could change the
password they were given. These tests drive the real routes: the admin
"Reset password" page (temporary password, reset link), the invite
option on the create form, the sign-in-free link and forced-change
pages, and Account > Change password.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import html
import re

from datetime import datetime, timedelta, timezone

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    cookie_session,
)

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    app,
    audit_records_for,
    ensure_audit_wiring,
    get,
    latest_audit_sequence,
    merge_cookies,
    open_db_session,
    post_form,
    unique_name,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    decode_session_cookie,
    ensure_seeded_admin,
    login_via_post,
)


_START_PASSWORD: str = "Granite-Harbor-47!"
_TEMP_PASSWORD: str = "Temporary-Lantern-83!"
_NEW_PASSWORD: str = "Copper-Meadow-59#"

_LINK_PATTERN = re.compile(r'value="([^"]*/password/set/([^"]+))"')


def _create_user(*, prefix: str = "pwuser") -> tuple:
    login_name = unique_name(prefix=prefix)
    response = post_form(
        path="/admin/users/create",
        fields={
            "username": login_name,
            "email": "{}@example.com".format(login_name),
            "password": _START_PASSWORD,
            "display_name": "Password Probe",
        },
        cookies=admin_cookies(),
    )
    testbase.assert_equal(response.status_code, 303)
    rtnval = (login_name, _user_id(login_name=login_name))
    return rtnval


def _user_id(*, login_name: str) -> str:
    from ccai.pychestrate.webservice.identity.users.models import IdentityUser  # noqa: E402
    db_session = open_db_session()
    try:
        row = db_session.query(IdentityUser).filter(IdentityUser.login_name == login_name).one()
        rtnval = str(row.user_id)
    finally:
        db_session.close()
    return rtnval


def _user_status(*, login_name: str) -> str:
    from ccai.pychestrate.webservice.identity.users.models import IdentityUser  # noqa: E402
    db_session = open_db_session()
    try:
        row = db_session.query(IdentityUser).filter(IdentityUser.login_name == login_name).one()
        rtnval = row.status.value
    finally:
        db_session.close()
    return rtnval


def _session_token(*, cookies) -> str:
    payload = decode_session_cookie(cookie_value=cookies.get(cookie_session.COOKIE_NAME, ""))
    if payload is None:
        return ""
    rtnval = str(payload.get(auth_guard.SESSION_TOKEN_KEY, "") or "")
    return rtnval


def _set_temporary_password(*, user_id: str, password: str = _TEMP_PASSWORD, must_change: bool = True):
    fields = {"password": password, "password_confirm": password}
    if must_change is True:
        fields["must_change"] = "1"
    response = post_form(
        path="/admin/users/{}/password".format(user_id), fields=fields, cookies=admin_cookies()
    )
    return response


def _issue_link(*, user_id: str) -> tuple:
    response = post_form(
        path="/admin/users/{}/password-link".format(user_id), fields={}, cookies=admin_cookies()
    )
    match = _LINK_PATTERN.search(response.text)
    testbase.assert_true(match is not None, "no link on the page")
    rtnval = (response, html.unescape(match.group(2)))
    return rtnval


def _redeem(*, secret: str, password: str = _NEW_PASSWORD):
    form_page = get(path="/password/set/{}".format(secret))
    cookies = form_page.collect_set_cookies()
    response = post_form(
        path="/password/set/{}".format(secret),
        fields={"password": password, "password_confirm": password},
        cookies=cookies,
    )
    return response


# ===========================================================================
# Admin reset with a forced change
# ===========================================================================


def test_admin_sets_a_temporary_password():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: an administrator can set a new password for a user
    (redirect back to the user with a success message).**
    """
    _login, user_id = _create_user()
    response = _set_temporary_password(user_id=user_id)
    testbase.assert_equal(response.status_code, 303)
    testbase.assert_equal(response.header("Location"), "/admin/users/{}".format(user_id))
    return


def test_temporary_password_sends_sign_in_to_the_change_page():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: signing in with a temporary password leads to the
    change page and opens no session.**
    """
    login_name, user_id = _create_user()
    _set_temporary_password(user_id=user_id)
    response, cookies = login_via_post(wsgi_app=app(), login=login_name, password=_TEMP_PASSWORD)
    testbase.assert_equal(response.header("Location"), "/password/change-required")
    testbase.assert_equal(_session_token(cookies=cookies), "")
    return


def test_forced_change_signs_the_user_in_with_the_new_password():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: after proving the temporary password and choosing a
    new one, the user is signed in, and the new password works for
    later sign-ins.**
    """
    login_name, user_id = _create_user()
    _set_temporary_password(user_id=user_id)
    _response, cookies = login_via_post(wsgi_app=app(), login=login_name, password=_TEMP_PASSWORD)
    page = get(path="/password/change-required", cookies=cookies)
    testbase.assert_equal(page.status_code, 200)
    change = post_form(
        path="/password/change-required",
        fields={"current_password": _TEMP_PASSWORD, "password": _NEW_PASSWORD,
                "password_confirm": _NEW_PASSWORD},
        cookies=merge_cookies(cookies=cookies, response=page),
    )
    testbase.assert_equal(change.status_code, 303)
    signed_in = merge_cookies(cookies=cookies, response=change)
    testbase.assert_true(len(_session_token(cookies=signed_in)) > 0, "not signed in")
    again, _cookies = login_via_post(wsgi_app=app(), login=login_name, password=_NEW_PASSWORD)
    testbase.assert_equal(again.header("Location"), "/")
    return


def test_admin_reset_enforces_the_password_policy():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: the admin reset refuses a password that breaks the
    shared policy and names the broken rules.**
    """
    _login, user_id = _create_user()
    response = _set_temporary_password(user_id=user_id, password="a" * 12)
    testbase.assert_equal(response.status_code, 400)
    testbase.assert_true("Password must contain a digit." in response.text)
    return


def test_admin_reset_signs_the_user_out_everywhere():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: after an administrator sets a user's password, the
    user's existing session no longer works.**
    """
    login_name, user_id = _create_user()
    _response, user_cookies = login_via_post(wsgi_app=app(), login=login_name, password=_START_PASSWORD)
    _set_temporary_password(user_id=user_id)
    response = get(path="/account/password", cookies=user_cookies)
    testbase.assert_equal(response.status_code, 303)
    testbase.assert_true("/login" in (response.header("Location") or ""))
    return


def test_admin_cannot_reset_their_own_password_here():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: the admin reset page refuses the administrator's own
    account (the self-service page asks for the current password).**
    """
    admin = ensure_seeded_admin()
    response = _set_temporary_password(user_id=admin.user_id, password=_NEW_PASSWORD)
    testbase.assert_equal(response.status_code, 400)
    return


def test_admin_reset_is_audited():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: an admin reset writes audit.user.password_reset with
    the administrator as actor.**
    """
    ensure_audit_wiring()
    admin = ensure_seeded_admin()
    login_name, user_id = _create_user()
    mark = latest_audit_sequence()
    _set_temporary_password(user_id=user_id)
    rows = audit_records_for(kind="audit.user.password_reset", since_sequence=mark)
    testbase.assert_equal([str(row.actor_user_id) for row in rows], [admin.user_id])
    return


# ===========================================================================
# Reset links
# ===========================================================================


def test_reset_link_sets_a_new_password():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: opening a reset link and choosing a password sends the
    user to sign in, and the new password works.**
    """
    login_name, user_id = _create_user()
    _page, secret = _issue_link(user_id=user_id)
    response = _redeem(secret=secret)
    testbase.assert_equal(response.header("Location"), "/login")
    again, _cookies = login_via_post(wsgi_app=app(), login=login_name, password=_NEW_PASSWORD)
    testbase.assert_equal(again.header("Location"), "/")
    return


def test_reset_link_works_only_once():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: a used link is refused the second time.**
    """
    _login, user_id = _create_user()
    _page, secret = _issue_link(user_id=user_id)
    _redeem(secret=secret)
    second = get(path="/password/set/{}".format(secret))
    testbase.assert_equal(second.status_code, 404)
    testbase.assert_true("This link does not work" in second.text)
    return


def test_link_secret_is_stored_only_as_a_hash():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: the database holds the SHA-256 digest of the link
    secret, never the secret.**
    """
    from ccai.pychestrate.webservice.security.auth.models import AuthPasswordToken  # noqa: E402
    _login, user_id = _create_user()
    _page, secret = _issue_link(user_id=user_id)
    db_session = open_db_session()
    try:
        hashes = [row.token_hash for row in db_session.query(AuthPasswordToken).all()]
    finally:
        db_session.close()
    testbase.assert_true(hashlib.sha256(secret.encode("utf-8")).hexdigest() in hashes)
    testbase.assert_equal(secret in hashes, False)
    return


def test_expired_link_is_refused():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: a link past its expiry is refused.**
    """
    from ccai.pychestrate.webservice.security.auth.models import AuthPasswordToken  # noqa: E402
    _login, user_id = _create_user()
    _page, secret = _issue_link(user_id=user_id)
    db_session = open_db_session()
    try:
        row = (
            db_session.query(AuthPasswordToken)
            .filter(AuthPasswordToken.token_hash == hashlib.sha256(secret.encode("utf-8")).hexdigest())
            .one()
        )
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()
    finally:
        db_session.close()
    response = get(path="/password/set/{}".format(secret))
    testbase.assert_equal(response.status_code, 404)
    return


def test_a_new_link_cancels_the_previous_one():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: issuing a second link makes the first one stop
    working.**
    """
    _login, user_id = _create_user()
    _page, first = _issue_link(user_id=user_id)
    _issue_link(user_id=user_id)
    response = get(path="/password/set/{}".format(first))
    testbase.assert_equal(response.status_code, 404)
    return


def test_link_page_is_never_cached_or_referred():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: the link page is sent with Cache-Control: no-store and
    Referrer-Policy: no-referrer so the secret does not leak.**
    """
    _login, user_id = _create_user()
    _page, secret = _issue_link(user_id=user_id)
    response = get(path="/password/set/{}".format(secret))
    testbase.assert_equal(response.header("Cache-Control"), "no-store")
    testbase.assert_equal(response.header("Referrer-Policy"), "no-referrer")
    return


# ===========================================================================
# Invites
# ===========================================================================


def _invite_user() -> tuple:
    login_name = unique_name(prefix="invitee")
    response = post_form(
        path="/admin/users/create",
        fields={
            "username": login_name,
            "email": "{}@example.com".format(login_name),
            "password_setup": "invite",
            "password": "",
            "display_name": "Invitee",
        },
        cookies=admin_cookies(),
    )
    match = _LINK_PATTERN.search(response.text)
    secret = html.unescape(match.group(2)) if match is not None else ""
    rtnval = (response, login_name, secret)
    return rtnval


def test_invite_creates_an_account_that_cannot_sign_in_yet():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: creating a user with an invite shows the invite link
    and leaves the account pending (it cannot sign in).**
    """
    response, login_name, secret = _invite_user()
    testbase.assert_equal(response.status_code, 201)
    testbase.assert_true(len(secret) > 20, "no invite link shown")
    testbase.assert_equal(_user_status(login_name=login_name), "PENDING")
    return


def test_invite_link_activates_the_account():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: setting a password from the invite link activates the
    account and the user can sign in.**
    """
    _response, login_name, secret = _invite_user()
    _redeem(secret=secret)
    testbase.assert_equal(_user_status(login_name=login_name), "ACTIVE")
    again, _cookies = login_via_post(wsgi_app=app(), login=login_name, password=_NEW_PASSWORD)
    testbase.assert_equal(again.header("Location"), "/")
    return


# ===========================================================================
# Self-service change
# ===========================================================================


def test_self_service_change_requires_the_current_password():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: Change password refuses a wrong current password.**
    """
    login_name, _user_id = _create_user()
    _response, cookies = login_via_post(wsgi_app=app(), login=login_name, password=_START_PASSWORD)
    response = post_form(
        path="/account/password",
        fields={"current_password": "Wrong-Password-11!", "password": _NEW_PASSWORD,
                "password_confirm": _NEW_PASSWORD},
        cookies=cookies,
    )
    testbase.assert_equal(response.status_code, 400)
    testbase.assert_true("The current password is not correct." in response.text)
    return


def test_self_service_change_works_and_keeps_this_session():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: a user changes their own password; the session that
    made the change keeps working and the new password signs in.**
    """
    login_name, _user_id = _create_user()
    _response, cookies = login_via_post(wsgi_app=app(), login=login_name, password=_START_PASSWORD)
    response = post_form(
        path="/account/password",
        fields={"current_password": _START_PASSWORD, "password": _NEW_PASSWORD,
                "password_confirm": _NEW_PASSWORD},
        cookies=cookies,
    )
    testbase.assert_equal(response.header("Location"), "/account/password")
    still_signed_in = get(path="/account/password", cookies=merge_cookies(cookies=cookies, response=response))
    testbase.assert_equal(still_signed_in.status_code, 200)
    again, _cookies = login_via_post(wsgi_app=app(), login=login_name, password=_NEW_PASSWORD)
    testbase.assert_equal(again.header("Location"), "/")
    return


def test_self_service_change_signs_out_other_sessions():
    """
    **Feature: password lifecycle (ADM-04)**
    **Property: after a password change the user's other sessions no
    longer work.**
    """
    login_name, _user_id = _create_user()
    _first, cookies_a = login_via_post(wsgi_app=app(), login=login_name, password=_START_PASSWORD)
    _second, cookies_b = login_via_post(wsgi_app=app(), login=login_name, password=_START_PASSWORD)
    post_form(
        path="/account/password",
        fields={"current_password": _START_PASSWORD, "password": _NEW_PASSWORD,
                "password_confirm": _NEW_PASSWORD},
        cookies=cookies_a,
    )
    response = get(path="/account/password", cookies=cookies_b)
    testbase.assert_equal(response.status_code, 303)
    return
