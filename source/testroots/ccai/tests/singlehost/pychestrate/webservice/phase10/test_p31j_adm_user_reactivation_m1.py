"""
.. module:: test_p31j_adm_user_reactivation_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reactivating a user is an explicit action, an inactive
               account is shown neutrally, and edits move "Updated"
               (audit ADM-26).

.. moduleauthor:: Code Craft AI LLC

Reactivation was only possible by ticking "Active" in the edit form,
the user list showed "Inactive" in the same red as an error, and the
"Updated" timestamp never changed on edit. These tests drive the real
app as an administrator.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import time

from ccai import testbase

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
    login_via_post,
)


_PASSWORD: str = "Granite-Harbor-47!"


def _create_user(*, invite: bool = False) -> str:
    login_name = unique_name(prefix="react")
    fields = {"username": login_name, "email": "{}@example.com".format(login_name),
              "display_name": "Reactivation Probe"}
    if invite is True:
        fields["password_setup"] = "invite"
    else:
        fields["password"] = _PASSWORD
    response = post_form(path="/admin/users/create", fields=fields, cookies=admin_cookies())
    testbase.assert_true(response.status_code in (201, 303), response.status_code)
    return login_name


def _user_row(*, login_name: str):
    from ccai.pychestrate.webservice.identity.users.models import IdentityUser  # noqa: E402
    db_session = open_db_session()
    try:
        row = db_session.query(IdentityUser).filter(IdentityUser.login_name == login_name).one()
        rtnval = (str(row.user_id), row.status.name, row.updated_at)
    finally:
        db_session.close()
    return rtnval


def _deactivate(*, user_id: str) -> None:
    response = post_form(path="/admin/users/{}/deactivate".format(user_id), fields={},
                         cookies=admin_cookies())
    testbase.assert_equal(response.status_code, 303)
    return


def _reactivate(*, user_id: str, fields=None):
    rtnval = post_form(path="/admin/users/{}/reactivate".format(user_id), fields=fields or {},
                       cookies=admin_cookies())
    return rtnval


def _list_row_html(*, login_name: str) -> str:
    response = get(path="/admin/users", cookies=admin_cookies(), query={"search": login_name})
    testbase.assert_equal(response.status_code, 200)
    text = response.text
    start = text.index(">{}</a>".format(login_name))
    rtnval = text[start:text.index("</tr>", start)]
    return rtnval


def test_a_deactivated_user_offers_reactivate_in_the_list():
    """
    **Feature: user reactivation (ADM-26)**
    **Property: the user list offers a Reactivate button for a
    deactivated user.**
    """
    login_name = _create_user()
    user_id, _status, _updated = _user_row(login_name=login_name)
    _deactivate(user_id=user_id)
    row_html = _list_row_html(login_name=login_name)
    testbase.assert_true("/admin/users/{}/reactivate".format(user_id) in row_html, row_html)
    return


def test_inactive_is_shown_with_a_neutral_badge():
    """
    **Feature: user reactivation (ADM-26)**
    **Property: "Inactive" is a neutral badge, not the error red.**
    """
    login_name = _create_user()
    user_id, _status, _updated = _user_row(login_name=login_name)
    _deactivate(user_id=user_id)
    row_html = _list_row_html(login_name=login_name)
    testbase.assert_true('<span class="badge badge-secondary">Inactive</span>' in row_html, row_html)
    testbase.assert_equal("badge-danger" in row_html, False)
    return


def test_reactivate_lets_the_user_sign_in_again():
    """
    **Feature: user reactivation (ADM-26)**
    **Property: after Reactivate the account is active and its
    password signs in again.**
    """
    login_name = _create_user()
    user_id, _status, _updated = _user_row(login_name=login_name)
    _deactivate(user_id=user_id)
    response = _reactivate(user_id=user_id)
    testbase.assert_equal(response.status_code, 303)
    testbase.assert_equal(_user_row(login_name=login_name)[1], "ACTIVE")
    login_response, _cookies = login_via_post(wsgi_app=app(), login=login_name, password=_PASSWORD)
    testbase.assert_equal(login_response.status_code, 303)
    return


def test_reactivate_is_recorded_in_the_audit_log():
    """
    **Feature: user reactivation (ADM-26)**
    **Property: a reactivation is recorded as audit.user.reactivated
    for that user.**
    """
    ensure_audit_wiring()
    login_name = _create_user()
    user_id, _status, _updated = _user_row(login_name=login_name)
    _deactivate(user_id=user_id)
    since = latest_audit_sequence()
    _reactivate(user_id=user_id)
    records = audit_records_for(kind="audit.user.reactivated", since_sequence=since)
    logins = [record.payload_json.get("login_name") for record in records]
    testbase.assert_true(login_name in logins, logins)
    return


def test_reactivate_moves_the_updated_timestamp():
    """
    **Feature: user reactivation (ADM-26)**
    **Property: reactivating a user moves its updated_at forward.**
    """
    login_name = _create_user()
    user_id, _status, _updated = _user_row(login_name=login_name)
    _deactivate(user_id=user_id)
    before = _user_row(login_name=login_name)[2]
    time.sleep(0.01)
    _reactivate(user_id=user_id)
    after = _user_row(login_name=login_name)[2]
    testbase.assert_true(after > before, (before, after))
    return


def test_editing_a_user_moves_the_updated_timestamp():
    """
    **Feature: user reactivation (ADM-26)**
    **Property: saving a changed display name moves updated_at
    forward.**
    """
    login_name = _create_user()
    user_id, _status, before = _user_row(login_name=login_name)
    time.sleep(0.01)
    response = post_form(
        path="/admin/users/{}/edit".format(user_id),
        fields={"email": "{}@example.com".format(login_name), "display_name": "Renamed Probe",
                "is_active": "on"},
        cookies=admin_cookies(),
    )
    testbase.assert_equal(response.status_code, 303)
    after = _user_row(login_name=login_name)[2]
    testbase.assert_true(after > before, (before, after))
    return


def test_deactivating_moves_the_updated_timestamp():
    """
    **Feature: user reactivation (ADM-26)**
    **Property: deactivating a user moves its updated_at forward.**
    """
    login_name = _create_user()
    user_id, _status, before = _user_row(login_name=login_name)
    time.sleep(0.01)
    _deactivate(user_id=user_id)
    after = _user_row(login_name=login_name)[2]
    testbase.assert_true(after > before, (before, after))
    return


def test_reactivating_a_cancelled_invitation_returns_it_to_invited():
    """
    **Feature: user reactivation (ADM-26)**
    **Property: an invited account that was deactivated before it set
    a password comes back as invited (not active) and the flash says
    to send a new invite link.**
    """
    login_name = _create_user(invite=True)
    user_id, status, _updated = _user_row(login_name=login_name)
    testbase.assert_equal(status, "PENDING")
    _deactivate(user_id=user_id)
    response = _reactivate(user_id=user_id)
    testbase.assert_equal(_user_row(login_name=login_name)[1], "PENDING")
    follow = get(path="/admin/users", cookies=merge_cookies(cookies=admin_cookies(), response=response))
    testbase.assert_true("new invite link" in html.unescape(follow.text), follow.text[:1500])
    return


def test_reactivate_from_the_detail_page_returns_there():
    """
    **Feature: user reactivation (ADM-26)**
    **Property: a Reactivate posted from the detail page
    (return_to=detail) redirects back to that page; anything else goes
    to the list.**
    """
    login_name = _create_user()
    user_id, _status, _updated = _user_row(login_name=login_name)
    _deactivate(user_id=user_id)
    response = _reactivate(user_id=user_id, fields={"return_to": "detail"})
    location = response.header("Location") or ""
    testbase.assert_equal(location.split("?")[0].endswith("/admin/users/{}".format(user_id)), True)
    return
