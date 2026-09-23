"""
.. module:: test_p31g_adm_sessions_page_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The admin sessions page shows real, current information
               (audit ADM-16).

.. moduleauthor:: Code Craft AI LLC

Every "Client IP" on the sessions page was the SHA-256 of an empty
string, the user agent was a hash, the address came from a spoofable
header, and idle-expired sessions were listed as active. These tests
sign in through the real app and read the page.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import urllib.parse

from datetime import datetime, timedelta, timezone

from ccai import testbase

from ccai.pychestrate.webservice.security.auth.client_address import (
    PEER_ADDRESS_HEADER,
)
from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    cookie_session,
)

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    app,
    get,
    open_db_session,
    post_form,
    unique_name,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    decode_session_cookie,
    drive_request,
    fetch_login_form_token,
)


_PASSWORD: str = "Granite-Harbor-47!"
_CHROME_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def _create_user() -> str:
    login_name = unique_name(prefix="sess")
    response = post_form(
        path="/admin/users/create",
        fields={"username": login_name, "email": "{}@example.com".format(login_name),
                "password": _PASSWORD, "display_name": "Session Probe"},
        cookies=admin_cookies(),
    )
    testbase.assert_equal(response.status_code, 303)
    return login_name


def _login_with_headers(*, login_name: str, headers: dict) -> dict:
    """
        Sign in the way a browser behind the given headers would.
        Returns the session cookies.
    """
    from ccai.pychestrate.webservice.security.auth.local_flow import (  # noqa: E402
        reset_backoff_for_testing,
    )
    reset_backoff_for_testing()
    form_cookies, token = fetch_login_form_token(wsgi_app=app())
    body = urllib.parse.urlencode({
        "username": login_name, "password": _PASSWORD, "csrf_token": token,
    }).encode("utf-8")
    request_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    request_headers.update(headers)
    response = drive_request(
        wsgi_app=app(), method="POST", path="/login", body=body,
        cookies=form_cookies, headers=request_headers,
    )
    testbase.assert_equal(response.status_code, 303)
    rtnval = response.collect_set_cookies()
    return rtnval


def _session_id(*, cookies: dict) -> str:
    payload = decode_session_cookie(cookie_value=cookies[cookie_session.COOKIE_NAME])
    rtnval = str(payload[auth_guard.SESSION_TOKEN_KEY])
    return rtnval


def _recorded_client(*, session_id: str):
    from ccai.pychestrate.webservice.security.auth.models import AuthSessionClient  # noqa: E402
    db_session = open_db_session()
    try:
        row = (
            db_session.query(AuthSessionClient)
            .filter(AuthSessionClient.session_id == session_id)
            .first()
        )
        rtnval = (row.client_address, row.user_agent) if row is not None else (None, None)
    finally:
        db_session.close()
    return rtnval


def _sessions_page(*, username: str) -> str:
    response = get(path="/admin/sessions", cookies=admin_cookies(), query={"username": username})
    testbase.assert_equal(response.status_code, 200)
    rtnval = response.text
    return rtnval


def test_sign_in_behind_the_proxy_records_the_forwarded_client():
    """
    **Feature: sessions page (ADM-16)**
    **Property: a sign-in that arrives through the trusted local proxy
    records the client address the proxy forwarded.**
    """
    login_name = _create_user()
    cookies = _login_with_headers(login_name=login_name, headers={
        PEER_ADDRESS_HEADER: "127.0.0.1",
        "X-Forwarded-For": "198.51.100.23",
        "User-Agent": _CHROME_MAC,
    })
    address, _agent = _recorded_client(session_id=_session_id(cookies=cookies))
    testbase.assert_equal(address, "198.51.100.23")
    return


def test_a_forwarded_header_from_an_untrusted_peer_is_ignored():
    """
    **Feature: sessions page (ADM-16)**
    **Property: a client talking to the service directly cannot choose
    its recorded address with X-Forwarded-For.**
    """
    login_name = _create_user()
    cookies = _login_with_headers(login_name=login_name, headers={
        PEER_ADDRESS_HEADER: "203.0.113.50",
        "X-Forwarded-For": "10.9.9.9",
    })
    address, _agent = _recorded_client(session_id=_session_id(cookies=cookies))
    testbase.assert_equal(address, "203.0.113.50")
    return


def test_the_page_shows_the_address_and_a_readable_browser():
    """
    **Feature: sessions page (ADM-16)**
    **Property: the sessions page shows the recorded address and
    "Chrome 128 on macOS", not hashes.**
    """
    login_name = _create_user()
    _login_with_headers(login_name=login_name, headers={
        PEER_ADDRESS_HEADER: "127.0.0.1",
        "X-Forwarded-For": "198.51.100.24",
        "User-Agent": _CHROME_MAC,
    })
    text = _sessions_page(username=login_name)
    testbase.assert_true("198.51.100.24" in text, "address not shown")
    testbase.assert_true("Chrome 128 on macOS" in text, "browser not shown")
    return


def test_idle_expired_sessions_are_not_listed():
    """
    **Feature: sessions page (ADM-16)**
    **Property: a session idle past its timeout is no longer listed as
    active.**
    """
    from ccai.pychestrate.webservice.security.auth.models import AuthSession  # noqa: E402
    login_name = _create_user()
    cookies = _login_with_headers(login_name=login_name, headers={
        PEER_ADDRESS_HEADER: "127.0.0.1", "X-Forwarded-For": "198.51.100.25",
    })
    session_id = _session_id(cookies=cookies)
    db_session = open_db_session()
    try:
        row = db_session.query(AuthSession).filter(AuthSession.session_id == session_id).one()
        row.last_seen_at = datetime.now(timezone.utc) - timedelta(
            seconds=int(row.idle_timeout_seconds) + 60
        )
        db_session.commit()
    finally:
        db_session.close()
    text = _sessions_page(username=login_name)
    testbase.assert_equal("198.51.100.25" in text, False)
    testbase.assert_true("No active sessions found" in text, "idle session still listed")
    return


def test_sessions_are_grouped_under_their_user():
    """
    **Feature: sessions page (ADM-16)**
    **Property: each user's sessions sit under one heading row naming
    the user and the count.**
    """
    login_name = _create_user()
    for suffix in ("26", "27"):
        _login_with_headers(login_name=login_name, headers={
            PEER_ADDRESS_HEADER: "127.0.0.1", "X-Forwarded-For": "198.51.100." + suffix,
        })
    text = _sessions_page(username=login_name)
    testbase.assert_true('scope="rowgroup"' in text, "no user group heading")
    testbase.assert_true("2 sessions" in text, text[:2000])
    return


def test_the_viewers_own_session_is_marked():
    """
    **Feature: sessions page (ADM-16)**
    **Property: the administrator's own session is labelled "This
    session".**
    """
    from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (  # noqa: E402
        ensure_seeded_admin,
    )
    admin = ensure_seeded_admin()
    text = _sessions_page(username=admin.login)
    testbase.assert_true("This session" in text, "own session not marked")
    return
