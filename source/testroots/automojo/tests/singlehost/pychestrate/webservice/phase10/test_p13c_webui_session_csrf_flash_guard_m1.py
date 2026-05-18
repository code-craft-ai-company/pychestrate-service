"""
.. module:: test_p13c_webui_session_csrf_flash_guard_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the cookie-session / CSRF / flash /
               auth-guard foundation pieces.

.. moduleauthor:: Automation Mojo LLC

This suite covers the four foundation modules slated for the
config blueprint port (the actual route ports land in PR C2).
Tests cover the cookie sign/verify cycle, tamper detection, the
CSRF token primitives + constant-time compare, the flash queue
add/consume/peek shape, and the login + CSRF guards including
the redirect + flash side-effects.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Dict, List, Optional

from automojo import testbase
from automojo.webworks.routing.response import RedirectResponse, Response

from automojo.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    cookie_session,
    csrf,
    flash,
)


# ---------------------------------------------------------------------------
# Test stubs
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(
        self,
        *,
        cookies: Optional[Dict[str, str]] = None
    ) -> None:
        self.cookies: Dict[str, str] = cookies if cookies is not None else {}
        return


class _CookieRecord:
    def __init__(self) -> None:
        self.set_calls: List[Dict[str, Any]] = []
        self.delete_calls: List[Dict[str, Any]] = []
        return


class _FakeResponse:
    """
        Captures cookie writes the helpers issue. Mirrors the
        webworks Response.set_cookie + delete_cookie surface
        without actually wiring the SimpleCookie storage.
    """

    def __init__(self) -> None:
        self.cookies = _CookieRecord()
        return

    def set_cookie(
        self,
        name: str,
        value: str,
        max_age: Optional[int] = None,
        path: str = "/",
        secure: bool = False,
        httponly: bool = False,
        samesite: Optional[str] = None,
    ) -> None:
        self.cookies.set_calls.append({
            "name": name,
            "value": value,
            "max_age": max_age,
            "path": path,
            "secure": secure,
            "httponly": httponly,
            "samesite": samesite,
        })
        return

    def delete_cookie(
        self,
        name: str,
        path: str = "/",
        domain: Optional[str] = None,
    ) -> None:
        self.cookies.delete_calls.append({
            "name": name,
            "path": path,
            "domain": domain,
        })
        return


_TEST_SECRET: bytes = b"\x00" * 32


# ===========================================================================
# cookie_session
# ===========================================================================


def test_sign_then_verify_round_trips_payload():
    """
    **Feature: web UI foundation T1.2 (cookie session)**
    **Property: A signed payload round-trips through verify into
    the same dict.**
    """
    payload = {"user_id": "u-1", "csrf_token": "abc", "n": 7}
    cookie_value = cookie_session.sign_session_payload(
        payload=payload, secret=_TEST_SECRET
    )
    decoded = cookie_session.verify_session_payload(
        cookie_value=cookie_value, secret=_TEST_SECRET
    )
    testbase.assert_equal(decoded, payload)
    return


def test_verify_rejects_tampered_payload():
    """
    **Feature: web UI foundation T1.2 (cookie session)**
    **Property: A payload whose b64 chunk has been mutated fails
    verification (returns None) -- HMAC catches the tamper.**
    """
    cookie_value = cookie_session.sign_session_payload(
        payload={"user_id": "u-1"}, secret=_TEST_SECRET
    )
    payload_b64, signature_b64 = cookie_value.rsplit(".", 1)
    # Flip the first base64 character of the payload.
    if payload_b64[0] == "A":
        mutated_payload = "B" + payload_b64[1:]
    else:
        mutated_payload = "A" + payload_b64[1:]
    tampered = mutated_payload + "." + signature_b64
    decoded = cookie_session.verify_session_payload(
        cookie_value=tampered, secret=_TEST_SECRET
    )
    testbase.assert_equal(decoded, None)
    return


def test_verify_rejects_tampered_signature():
    """
    **Feature: web UI foundation T1.2 (cookie session)**
    **Property: A payload whose signature chunk has been mutated
    fails verification.**
    """
    cookie_value = cookie_session.sign_session_payload(
        payload={"user_id": "u-1"}, secret=_TEST_SECRET
    )
    payload_b64, signature_b64 = cookie_value.rsplit(".", 1)
    mutated_signature = signature_b64[:-2] + "AA"
    if mutated_signature == signature_b64:
        mutated_signature = signature_b64[:-2] + "BB"
    tampered = payload_b64 + "." + mutated_signature
    decoded = cookie_session.verify_session_payload(
        cookie_value=tampered, secret=_TEST_SECRET
    )
    testbase.assert_equal(decoded, None)
    return


def test_verify_rejects_signature_made_with_different_secret():
    """
    **Feature: web UI foundation T1.2 (cookie session)**
    **Property: A signature produced with a different secret
    fails verification with the deployment's secret.**
    """
    other_secret = b"\xff" * 32
    cookie_value = cookie_session.sign_session_payload(
        payload={"user_id": "u-1"}, secret=other_secret
    )
    decoded = cookie_session.verify_session_payload(
        cookie_value=cookie_value, secret=_TEST_SECRET
    )
    testbase.assert_equal(decoded, None)
    return


def test_verify_returns_none_on_missing_or_malformed_input():
    """
    **Feature: web UI foundation T1.2 (cookie session)**
    **Property: None / empty / no-separator / empty-half cookie
    values all decode to None rather than raising.**
    """
    for bad in (None, "", "no-dot-here", ".only-signature", "only-payload."):
        decoded = cookie_session.verify_session_payload(
            cookie_value=bad, secret=_TEST_SECRET
        )
        testbase.assert_equal(decoded, None)
    return


def test_sign_refuses_short_secret():
    """
    **Feature: web UI foundation T1.2 (cookie session)**
    **Property: A secret < 16 bytes raises ValueError.**
    """
    raised = False
    try:
        cookie_session.sign_session_payload(
            payload={"x": 1}, secret=b"short"
        )
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_read_session_from_request_returns_empty_dict_on_no_cookie():
    """
    **Feature: web UI foundation T1.2 (cookie session)**
    **Property: A request with no UI cookie yields an empty dict
    so handlers can treat the result uniformly.**
    """
    request = _FakeRequest(cookies={})
    session = cookie_session.read_session_from_request(
        request=request, secret=_TEST_SECRET
    )
    testbase.assert_equal(session, {})
    return


def test_write_session_to_response_sets_secure_httponly_lax_by_default():
    """
    **Feature: web UI foundation T1.2 (cookie session)**
    **Property: The default cookie attributes are
    Secure + HttpOnly + SameSite=Lax per OWASP guidance.**
    """
    response = _FakeResponse()
    cookie_session.write_session_to_response(
        response=response,
        payload={"user_id": "u-1"},
        secret=_TEST_SECRET,
    )
    testbase.assert_equal(len(response.cookies.set_calls), 1)
    call = response.cookies.set_calls[0]
    testbase.assert_equal(call["name"], cookie_session.COOKIE_NAME)
    testbase.assert_equal(call["secure"], True)
    testbase.assert_equal(call["httponly"], True)
    testbase.assert_equal(call["samesite"], "Lax")
    return


def test_clear_session_cookie_on_response_calls_delete():
    """
    **Feature: web UI foundation T1.2 (cookie session)**
    **Property: clear_session_cookie_on_response invokes
    response.delete_cookie with the documented cookie name.**
    """
    response = _FakeResponse()
    cookie_session.clear_session_cookie_on_response(response=response)
    testbase.assert_equal(len(response.cookies.delete_calls), 1)
    testbase.assert_equal(
        response.cookies.delete_calls[0]["name"],
        cookie_session.COOKIE_NAME,
    )
    return


# ===========================================================================
# csrf
# ===========================================================================


def test_generate_csrf_token_returns_distinct_values():
    """
    **Feature: web UI foundation T1.3 (CSRF)**
    **Property: Two consecutive generate_csrf_token calls produce
    distinct tokens (overwhelmingly likely with secrets module
    output).**
    """
    a = csrf.generate_csrf_token()
    b = csrf.generate_csrf_token()
    testbase.assert_equal(a != b, True)
    testbase.assert_equal(len(a) > 32, True)
    return


def test_extract_token_from_form_returns_string_or_none():
    """
    **Feature: web UI foundation T1.3 (CSRF)**
    **Property: extract returns the string token; None for
    missing / empty / non-string / None form.**
    """
    testbase.assert_equal(
        csrf.extract_token_from_form(form={"csrf_token": "tok"}), "tok"
    )
    testbase.assert_equal(csrf.extract_token_from_form(form={}), None)
    testbase.assert_equal(
        csrf.extract_token_from_form(form={"csrf_token": ""}), None
    )
    testbase.assert_equal(
        csrf.extract_token_from_form(form={"csrf_token": 7}), None
    )
    testbase.assert_equal(csrf.extract_token_from_form(form=None), None)
    return


def test_is_token_valid_uses_constant_time_compare():
    """
    **Feature: web UI foundation T1.3 (CSRF)**
    **Property: Equal non-empty tokens validate; mismatches and
    empty / None values do not.**
    """
    token = csrf.generate_csrf_token()
    testbase.assert_equal(
        csrf.is_token_valid(submitted=token, expected=token), True
    )
    testbase.assert_equal(
        csrf.is_token_valid(submitted=token, expected=token + "x"), False
    )
    testbase.assert_equal(
        csrf.is_token_valid(submitted=None, expected=token), False
    )
    testbase.assert_equal(
        csrf.is_token_valid(submitted=token, expected=None), False
    )
    testbase.assert_equal(
        csrf.is_token_valid(submitted="", expected=token), False
    )
    return


def test_get_or_create_token_in_session_creates_when_absent_and_marks_mutated():
    """
    **Feature: web UI foundation T1.3 (CSRF)**
    **Property: When the session has no CSRF token, get_or_create
    mints one, stores it, and returns mutated=True so the
    handler knows to re-write the session cookie.**
    """
    session: Dict[str, Any] = {}
    token, mutated = csrf.get_or_create_token_in_session(session=session)
    testbase.assert_equal(len(token) > 0, True)
    testbase.assert_equal(mutated, True)
    testbase.assert_equal(session[csrf.SESSION_KEY], token)
    return


def test_get_or_create_token_in_session_returns_existing_when_present():
    """
    **Feature: web UI foundation T1.3 (CSRF)**
    **Property: An already-stored token is returned unchanged
    with mutated=False.**
    """
    session: Dict[str, Any] = {csrf.SESSION_KEY: "preset-token"}
    token, mutated = csrf.get_or_create_token_in_session(session=session)
    testbase.assert_equal(token, "preset-token")
    testbase.assert_equal(mutated, False)
    return


def test_rotate_csrf_token_replaces_existing_value():
    """
    **Feature: web UI foundation T1.3 (CSRF)**
    **Property: rotate produces a new token AND overwrites the
    session entry. Used after privilege change so the new
    session can't reuse the pre-change token.**
    """
    session: Dict[str, Any] = {csrf.SESSION_KEY: "old-token"}
    new_token = csrf.rotate_csrf_token(session=session)
    testbase.assert_equal(new_token != "old-token", True)
    testbase.assert_equal(session[csrf.SESSION_KEY], new_token)
    return


# ===========================================================================
# flash
# ===========================================================================


def test_add_flash_appends_to_session_queue():
    """
    **Feature: web UI foundation T1.4 (flash messages)**
    **Property: add_flash appends a (category, message) pair to
    the session-stored queue. Multiple adds preserve order.**
    """
    session: Dict[str, Any] = {}
    flash.add_flash(session=session, message="first", category="info")
    flash.add_flash(session=session, message="second", category="warning")
    queue = session[flash.SESSION_KEY]
    testbase.assert_equal(len(queue), 2)
    testbase.assert_equal(queue[0], ["info", "first"])
    testbase.assert_equal(queue[1], ["warning", "second"])
    return


def test_consume_flashes_drains_and_returns_tuples():
    """
    **Feature: web UI foundation T1.4 (flash messages)**
    **Property: consume_flashes returns the queue as
    list[tuple(category, message)] AND clears the session entry.**
    """
    session: Dict[str, Any] = {}
    flash.add_flash(session=session, message="hello", category="success")
    flash.add_flash(session=session, message="bye", category="info")
    consumed = flash.consume_flashes(session=session)
    testbase.assert_equal(len(consumed), 2)
    testbase.assert_equal(consumed[0], ("success", "hello"))
    testbase.assert_equal(consumed[1], ("info", "bye"))
    testbase.assert_equal(flash.SESSION_KEY in session, False)
    return


def test_consume_flashes_returns_empty_when_no_queue():
    """
    **Feature: web UI foundation T1.4 (flash messages)**
    **Property: consume on an empty session returns [] and is
    a no-op on the session dict.**
    """
    session: Dict[str, Any] = {}
    consumed = flash.consume_flashes(session=session)
    testbase.assert_equal(consumed, [])
    return


def test_consume_flashes_tolerates_corrupted_queue_entries():
    """
    **Feature: web UI foundation T1.4 (flash messages)**
    **Property: A queue entry that is not a valid pair is
    silently skipped on consume; the session entry is still
    cleared. Defensive against tampered cookie payloads.**
    """
    session: Dict[str, Any] = {
        flash.SESSION_KEY: [
            ["info", "valid"],
            "not-a-list",
            ["only-one"],
            ["warning", "also-valid"],
        ]
    }
    consumed = flash.consume_flashes(session=session)
    testbase.assert_equal(len(consumed), 2)
    testbase.assert_equal(consumed[0], ("info", "valid"))
    testbase.assert_equal(consumed[1], ("warning", "also-valid"))
    return


def test_peek_flashes_does_not_drain():
    """
    **Feature: web UI foundation T1.4 (flash messages)**
    **Property: peek returns the queue but leaves the session
    entry in place.**
    """
    session: Dict[str, Any] = {}
    flash.add_flash(session=session, message="m", category="info")
    peeked = flash.peek_flashes(session=session)
    testbase.assert_equal(len(peeked), 1)
    testbase.assert_equal(flash.SESSION_KEY in session, True)
    return


# ===========================================================================
# auth_guard
# ===========================================================================


def test_is_authenticated_requires_user_id_and_session_token():
    """
    **Feature: web UI foundation T1.5 (auth guard)**
    **Property: Both user_id AND session_token must be non-empty
    strings -- mirrors the flask login_required check exactly.**
    """
    testbase.assert_equal(auth_guard.is_authenticated(session={}), False)
    testbase.assert_equal(
        auth_guard.is_authenticated(session={"user_id": "u-1"}), False
    )
    testbase.assert_equal(
        auth_guard.is_authenticated(
            session={"user_id": "u-1", "session_token": "t-1"}
        ),
        True,
    )
    testbase.assert_equal(
        auth_guard.is_authenticated(
            session={"user_id": "", "session_token": "t-1"}
        ),
        False,
    )
    testbase.assert_equal(
        auth_guard.is_authenticated(
            session={"user_id": "u-1", "session_token": ""}
        ),
        False,
    )
    return


def test_require_login_or_redirect_returns_none_when_authenticated():
    """
    **Feature: web UI foundation T1.5 (auth guard)**
    **Property: An authenticated session yields None so the
    handler proceeds.**
    """
    session = {"user_id": "u-1", "session_token": "t-1"}
    result = auth_guard.require_login_or_redirect(
        session=session, login_url="/login"
    )
    testbase.assert_equal(result, None)
    return


def test_require_login_or_redirect_redirects_anonymous_to_login_url():
    """
    **Feature: web UI foundation T1.5 (auth guard)**
    **Property: An anonymous session yields a 302 RedirectResponse
    to the configured login URL.**
    """
    session: Dict[str, Any] = {}
    result = auth_guard.require_login_or_redirect(
        session=session, login_url="/login"
    )
    is_redirect = isinstance(result, RedirectResponse)
    testbase.assert_equal(is_redirect, True)
    testbase.assert_equal(result.status_code, 302)
    testbase.assert_equal(result.headers["Location"], "/login")
    return


def test_require_login_or_redirect_queues_flash_message_when_supplied():
    """
    **Feature: web UI foundation T1.5 (auth guard)**
    **Property: The optional flash_message is queued on the
    session before the redirect is built. The handler then
    re-writes the session cookie on the redirect response.**
    """
    session: Dict[str, Any] = {}
    auth_guard.require_login_or_redirect(
        session=session,
        login_url="/login",
        flash_message="Please log in to access this page.",
    )
    queue = session[flash.SESSION_KEY]
    testbase.assert_equal(len(queue), 1)
    testbase.assert_equal(queue[0][0], "warning")
    testbase.assert_equal(queue[0][1], "Please log in to access this page.")
    return


def test_enforce_csrf_or_redirect_returns_none_on_valid_token():
    """
    **Feature: web UI foundation T1.5 (auth guard)**
    **Property: When the form's csrf_token matches the session's
    expected token, the guard returns None and the handler
    proceeds.**
    """
    session = {csrf.SESSION_KEY: "expected-tok"}
    form = {"csrf_token": "expected-tok"}
    result = auth_guard.enforce_csrf_or_redirect(
        form=form, session=session, fallback_url="/admin/dashboard"
    )
    testbase.assert_equal(result, None)
    return


def test_enforce_csrf_or_redirect_redirects_on_mismatch_and_flashes_error():
    """
    **Feature: web UI foundation T1.5 (auth guard)**
    **Property: A mismatched token returns a 302 redirect to the
    fallback_url AND queues an error-category flash. Mirrors the
    flask @validate_csrf decorator behavior of bouncing back
    with an error.**
    """
    session = {csrf.SESSION_KEY: "expected-tok"}
    form = {"csrf_token": "wrong-tok"}
    result = auth_guard.enforce_csrf_or_redirect(
        form=form,
        session=session,
        fallback_url="/admin/users",
    )
    is_redirect = isinstance(result, RedirectResponse)
    testbase.assert_equal(is_redirect, True)
    testbase.assert_equal(result.status_code, 302)
    testbase.assert_equal(result.headers["Location"], "/admin/users")
    queue = session[flash.SESSION_KEY]
    testbase.assert_equal(len(queue), 1)
    testbase.assert_equal(queue[0][0], "error")
    return


def test_enforce_csrf_or_redirect_redirects_when_form_is_none():
    """
    **Feature: web UI foundation T1.5 (auth guard)**
    **Property: A None form is treated as "no token" and fails
    validation. Defensive for handlers that don't decode the
    body before calling the guard.**
    """
    session = {csrf.SESSION_KEY: "expected-tok"}
    result = auth_guard.enforce_csrf_or_redirect(
        form=None, session=session, fallback_url="/x"
    )
    is_redirect = isinstance(result, RedirectResponse)
    testbase.assert_equal(is_redirect, True)
    return


def test_enforce_csrf_or_redirect_redirects_when_session_has_no_token():
    """
    **Feature: web UI foundation T1.5 (auth guard)**
    **Property: A session without an expected token fails the
    check. Catches the case where a handler tried to validate
    CSRF on a session that was never primed with a token.**
    """
    session: Dict[str, Any] = {}
    result = auth_guard.enforce_csrf_or_redirect(
        form={"csrf_token": "anything"},
        session=session,
        fallback_url="/x",
    )
    is_redirect = isinstance(result, RedirectResponse)
    testbase.assert_equal(is_redirect, True)
    return
