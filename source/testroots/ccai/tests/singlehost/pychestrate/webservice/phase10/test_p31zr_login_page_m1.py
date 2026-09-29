"""
.. module:: test_p31zr_login_page_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The sign-in page is a sign-in page (XC-08, ADM-35).

.. moduleauthor:: Code Craft AI LLC

The page was titled "Login - Pychestrate Configuration", greeted everyone with
"Welcome Back" in an h2 and called the product a configuration panel; a failed
attempt cleared the username and showed the error above the card; and a person
who was already signed in was shown the form again. It now has one h1 ("Sign in
to Pychestrate") and a neutral line, the tab says "Sign in · Pychestrate", the
username survives a failed attempt (and the cursor goes to the password), the
error is inside the card and announced at once, and a signed-in visitor is sent
on (to a safe ``next``, or home).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    fetch_login_form_token,
    logged_in_cookies,
    login_via_post,
)


def _get_login(query: str = "", cookies=None):
    handle = ensure_app()
    return drive_request(wsgi_app=handle.wsgi_app, method="GET", path="/login", query_string=query, cookies=cookies)


def test_the_page_has_one_sign_in_heading_a_neutral_line_and_a_tab_that_says_sign_in():
    """
    **Feature: sign-in page (XC-08)**
    **Property: an anonymous GET /login answers 200 with exactly one h1
    "Sign in to Pychestrate", the tab title "Sign in · Pychestrate", and none
    of "Welcome Back", "configuration panel" or "Login - Pychestrate".**
    """
    body = _get_login().text

    testbase.assert_equal(
        (len(re.findall(r"<h1[ >]", body)), "<h1>Sign in to Pychestrate</h1>" in body,
         "<title>Sign in · Pychestrate</title>" in body,
         [phrase for phrase in ("Welcome Back", "configuration panel", "Login - Pychestrate") if phrase in body]),
        (1, True, True, []),
    )
    return


def test_a_failed_sign_in_keeps_the_username_puts_the_error_in_the_card_and_moves_the_cursor_to_the_password():
    """
    **Feature: sign-in page (ADM-35)**
    **Property: after a wrong password the answer is 401 and the form still
    holds the username; the error is a ``role="alert"`` element inside the
    login card and no flash element sits above it; the autofocus moves from
    the username to the password.**
    """
    handle = ensure_app()
    response, _cookies = login_via_post(wsgi_app=handle.wsgi_app, login="pat.example", password="not-the-password")
    body = response.text
    card = body[body.index('class="login-container"'):] if 'class="login-container"' in body else ""
    before_card = body[:body.index('class="login-container"')] if 'class="login-container"' in body else body
    username_input = re.search(r'<input[^>]*id="username"[^>]*>', body, re.S)
    password_input = re.search(r'<input[^>]*id="password"[^>]*>', body, re.S)

    testbase.assert_equal(
        (response.status_code,
         username_input is not None and 'value="pat.example"' in username_input.group(0) and "autofocus" not in username_input.group(0),
         password_input is not None and "autofocus" in password_input.group(0),
         'role="alert"' in card, 'role="alert"' in before_card, "pyc-flashes" in body),
        (401, True, True, True, False, False),
    )
    return


def test_a_form_left_empty_is_refused_with_the_username_kept():
    """
    **Feature: sign-in page (ADM-35)**
    **Property: a submission with a username and no password answers 400,
    says both are required inside the card, and keeps the username.**
    """
    handle = ensure_app()
    form_cookies, token = fetch_login_form_token(wsgi_app=handle.wsgi_app)
    response = drive_request(
        wsgi_app=handle.wsgi_app, method="POST", path="/login",
        body="username=pat.example&password=&csrf_token={}".format(token).encode("utf-8"),
        cookies=form_cookies, headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    body = response.text

    testbase.assert_equal(
        (response.status_code, 'value="pat.example"' in body, "Username and password are required." in body,
         body.index("Username and password are required.") > body.index('class="login-container"')),
        (400, True, True, True),
    )
    return


def test_someone_already_signed_in_is_sent_on_and_never_to_another_site():
    """
    **Feature: sign-in page (ADM-35)**
    **Property: GET /login with a live session answers 303 to /, to a safe
    ``next`` when given one, and to / for a ``next`` that points off the site.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    plain = _get_login(cookies=cookies)
    onward = _get_login(query="next=/projects", cookies=cookies)
    foreign = _get_login(query="next=//evil.example/x", cookies=cookies)

    testbase.assert_equal(
        (plain.status_code, plain.header("Location"), onward.header("Location"), foreign.header("Location")),
        (303, "/", "/projects", "/"),
    )
    return


def test_a_dead_session_cookie_still_gets_the_form():
    """
    **Feature: sign-in page (ADM-35)**
    **Property: a session cookie that is junk, and one that is validly signed
    but names a session the store no longer holds (a signed-out tab), both get
    the sign-in form, not a redirect (a loop with the shell's bounce to /login).**
    """
    from ccai.pychestrate.webservice.webinterface.foundation.cookie_session import COOKIE_NAME
    from ccai.pychestrate.webservice.webinterface.site_shell import catchall_route

    handle = ensure_app()
    junk = _get_login(cookies={COOKIE_NAME: "not-a-real-cookie"})

    live_cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    original = catchall_route._is_session_row_alive
    try:
        catchall_route._is_session_row_alive = lambda *, session: False
        signed_out = _get_login(cookies=live_cookies)
    finally:
        catchall_route._is_session_row_alive = original
    live = _get_login(cookies=live_cookies)

    testbase.assert_equal(
        (junk.status_code, "Sign in to Pychestrate" in junk.text, signed_out.status_code, "Sign in to Pychestrate" in signed_out.text,
         live.status_code),
        (200, True, 200, True, 303),
    )
    return
