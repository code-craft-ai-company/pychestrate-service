"""
.. module:: test_p31k_adm_session_terminate_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Terminating sessions keeps the list view and can end all
               of one user's sessions at once (audit ADM-33).

.. moduleauthor:: Code Craft AI LLC

After one Terminate the sessions list reset to an unfiltered first
page (the next "first" Terminate button was the administrator's own
session), and there was no way to end every session of one user.
These tests drive the real app as an administrator.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html

from typing import Dict, List

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


_PASSWORD: str = "Granite-Harbor-47!"


def _create_user_with_sessions(*, count: int):
    """
        A new user signed in ``count`` times. Returns
        ``(login_name, user_id, [session ids])``.
    """
    login_name = unique_name(prefix="term")
    response = post_form(
        path="/admin/users/create",
        fields={"username": login_name, "email": "{}@example.com".format(login_name),
                "password": _PASSWORD, "display_name": "Terminate Probe"},
        cookies=admin_cookies(),
    )
    testbase.assert_equal(response.status_code, 303)
    session_ids: List[str] = []
    for _ in range(count):
        login_response, cookies = login_via_post(wsgi_app=app(), login=login_name, password=_PASSWORD)
        testbase.assert_equal(login_response.status_code, 303)
        session_ids.append(_session_id(cookies=cookies))
    user_id = _user_id(login_name=login_name)
    rtnval = (login_name, user_id, session_ids)
    return rtnval


def _session_id(*, cookies: Dict[str, str]) -> str:
    payload = decode_session_cookie(cookie_value=cookies[cookie_session.COOKIE_NAME])
    rtnval = str(payload[auth_guard.SESSION_TOKEN_KEY])
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


def _open_session_ids(*, user_id: str) -> List[str]:
    import uuid  # noqa: E402

    from ccai.pychestrate.webservice.security.auth.models import AuthSession  # noqa: E402
    db_session = open_db_session()
    try:
        rows = db_session.query(AuthSession).filter(AuthSession.user_id == uuid.UUID(user_id)).all()
        rtnval = sorted(str(row.session_id) for row in rows)
    finally:
        db_session.close()
    return rtnval


def _list_state(*, username: str = "", page: str = "1", per_page: str = "20") -> Dict[str, str]:
    rtnval = {"list_username": username, "list_page": page, "list_per_page": per_page}
    return rtnval


def test_terminating_a_session_returns_to_the_filtered_view():
    """
    **Feature: session termination (ADM-33)**
    **Property: after Terminate the list comes back with the username
    filter and page it was posted from.**
    """
    login_name, _user, session_ids = _create_user_with_sessions(count=2)
    response = post_form(
        path="/admin/sessions/{}/terminate".format(session_ids[0]),
        fields=_list_state(username=login_name, page="1", per_page="5"),
        cookies=admin_cookies(),
    )
    testbase.assert_equal(response.status_code, 303)
    location = response.header("Location") or ""
    testbase.assert_equal(location, "/admin/sessions?username={}&per_page=5".format(login_name))
    return


def test_a_malformed_list_state_falls_back_to_the_default_view():
    """
    **Feature: session termination (ADM-33)**
    **Property: a page or page size that is not a sane number is
    dropped from the return URL rather than echoed.**
    """
    _login, _user, session_ids = _create_user_with_sessions(count=1)
    response = post_form(
        path="/admin/sessions/{}/terminate".format(session_ids[0]),
        fields=_list_state(page="abc", per_page="100000"),
        cookies=admin_cookies(),
    )
    testbase.assert_equal(response.header("Location"), "/admin/sessions")
    return


def test_terminate_all_is_offered_in_the_user_heading():
    """
    **Feature: session termination (ADM-33)**
    **Property: a user with several sessions gets a "Terminate all"
    button in their heading row, counting all their sessions.**
    """
    login_name, user_id, _sessions = _create_user_with_sessions(count=2)
    response = get(path="/admin/sessions", cookies=admin_cookies(), query={"username": login_name})
    text = html.unescape(response.text)
    testbase.assert_true("/admin/sessions/user/{}/terminate".format(user_id) in text, "no bulk form")
    testbase.assert_true("Terminate all 2" in text, "no bulk button")
    return


def test_terminate_all_ends_every_session_of_the_user():
    """
    **Feature: session termination (ADM-33)**
    **Property: "Terminate all" closes every session of that user and
    returns to the same list view.**
    """
    login_name, user_id, _sessions = _create_user_with_sessions(count=3)
    response = post_form(
        path="/admin/sessions/user/{}/terminate".format(user_id),
        fields=_list_state(username=login_name),
        cookies=admin_cookies(),
    )
    testbase.assert_equal(response.status_code, 303)
    testbase.assert_equal(response.header("Location"), "/admin/sessions?username={}".format(login_name))
    testbase.assert_equal(_open_session_ids(user_id=user_id), [])
    return


def test_terminate_all_says_how_many_sessions_ended():
    """
    **Feature: session termination (ADM-33)**
    **Property: the flash after "Terminate all" names the count and
    the user.**
    """
    login_name, user_id, _sessions = _create_user_with_sessions(count=2)
    cookies = admin_cookies()
    response = post_form(
        path="/admin/sessions/user/{}/terminate".format(user_id),
        fields=_list_state(username=login_name),
        cookies=cookies,
    )
    follow = get(path="/admin/sessions", cookies=merge_cookies(cookies=cookies, response=response),
                 query={"username": login_name})
    testbase.assert_true(
        "Terminated 2 sessions for {}.".format(login_name) in html.unescape(follow.text),
        follow.text[:1500],
    )
    return


def test_terminate_all_is_recorded_under_the_administrator():
    """
    **Feature: session termination (ADM-33)**
    **Property: each session "Terminate all" ends is recorded as
    closed by the administrator (reason admin_terminated).**
    """
    ensure_audit_wiring()
    admin = ensure_seeded_admin()
    _login, user_id, session_ids = _create_user_with_sessions(count=2)
    mark = latest_audit_sequence()
    post_form(path="/admin/sessions/user/{}/terminate".format(user_id), fields=_list_state(),
              cookies=admin_cookies())
    rows = audit_records_for(kind="audit.session.closed", since_sequence=mark)
    closed = sorted(
        str(row.payload_json.get("session_id")) for row in rows
        if row.payload_json.get("reason") == "admin_terminated"
        and str(row.actor_user_id) == admin.user_id
    )
    testbase.assert_equal(closed, sorted(session_ids))
    return


def test_signing_out_other_sessions_keeps_the_current_one():
    """
    **Feature: session termination (ADM-33)**
    **Property: on the administrator's own row the bulk action ends
    their other sessions and keeps the one making the request.**
    """
    admin = ensure_seeded_admin()
    other_response, other_cookies = login_via_post(wsgi_app=app(), login=admin.login,
                                                   password=admin.password)
    testbase.assert_equal(other_response.status_code, 303)
    other_session = _session_id(cookies=other_cookies)
    mine = admin_cookies()
    my_session = _session_id(cookies=mine)
    response = post_form(path="/admin/sessions/user/{}/terminate".format(admin.user_id),
                         fields=_list_state(), cookies=mine)
    testbase.assert_equal(response.status_code, 303)
    open_ids = _open_session_ids(user_id=admin.user_id)
    testbase.assert_equal((my_session in open_ids, other_session in open_ids), (True, False))
    return


def test_a_page_past_the_end_shows_the_last_page():
    """
    **Feature: session termination (ADM-33)**
    **Property: when terminations empty the page being viewed, the list
    shows its last page instead of an empty table.**
    """
    login_name, _user, _sessions = _create_user_with_sessions(count=1)
    response = get(path="/admin/sessions", cookies=admin_cookies(),
                   query={"username": login_name, "page": "9"})
    testbase.assert_equal(response.status_code, 200)
    testbase.assert_equal("No active sessions found" in response.text, False)
    return
