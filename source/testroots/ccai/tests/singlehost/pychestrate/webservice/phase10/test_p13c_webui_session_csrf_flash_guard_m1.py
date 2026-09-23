"""
.. module:: test_p13c_webui_session_csrf_flash_guard_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the cookie-session / CSRF / flash /
               auth-guard foundation pieces.

.. moduleauthor:: Code Craft AI LLC

This suite covers the four foundation modules slated for the
config blueprint port (the actual route ports land in PR C2).
Tests cover the cookie sign/verify cycle, tamper detection, the
CSRF token primitives + constant-time compare, the flash queue
add/consume/peek shape, and the login + CSRF guards including
the redirect + flash side-effects.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os

from typing import Any, Dict, List, Optional, Tuple

from ccai import testbase
from ccai.errors.exceptions import ConfigurationError
from ccai.webworks.routing.response import RedirectResponse, Response

from ccai.pychestrate.webservice.webinterface.foundation import (
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


# ===========================================================================
# cookie_session -- Secure-cookie policy (request scheme / trusted proxy)
# ===========================================================================


_SESSION_SET_COOKIE: str = "pychestrate_ui_session=abc.def; HttpOnly; Path=/; SameSite=Lax"


def _https_proxy_environ(*, peer_address: str, forwarded_proto: str) -> Dict[str, Any]:
    """
        A WSGI environ for a request a reverse proxy relayed over plain
        HTTP, announcing the client's scheme in ``X-Forwarded-Proto``.
    """
    rtnval = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/login",
        "wsgi.url_scheme": "http",
        "REMOTE_ADDR": peer_address,
        "HTTP_X_FORWARDED_PROTO": forwarded_proto,
    }
    return rtnval


def _plain_http_environ() -> Dict[str, Any]:
    """
        A WSGI environ for a browser talking plain HTTP to the service.
    """
    rtnval = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/login",
        "wsgi.url_scheme": "http",
        "REMOTE_ADDR": "127.0.0.1",
    }
    return rtnval


def _cookie_setting_wsgi_app(environ: Dict[str, Any], start_response: Any) -> List[bytes]:
    """
        Stand-in for the service: answers every request with a session
        cookie and a content type.
    """
    start_response(
        "303 See Other",
        [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Set-Cookie", _SESSION_SET_COOKIE),
            ("Location", "/"),
        ],
    )
    return [b""]


def _headers_after_policy(
        *,
        runtime_environment: str,
        environ: Dict[str, Any],
        trusted_proxy_addresses: Optional[str] = None
    ) -> List[Tuple[str, str]]:
    """
        Run one request through the Secure-cookie policy wrapper under
        ``runtime_environment`` and return the headers it handed to the
        server's ``start_response``.
    """
    captured: Dict[str, Any] = {}

    def _start_response(status: str, headers: List[Tuple[str, str]], exc_info: Any = None) -> None:
        captured["headers"] = headers
        return None

    saved = os.environ.get("PYCHESTRATE_RUNTIME_ENVIRONMENT", None)
    os.environ["PYCHESTRATE_RUNTIME_ENVIRONMENT"] = runtime_environment
    try:
        wrapped = cookie_session.wrap_wsgi_app_with_secure_cookie_policy(
            wsgi_app=_cookie_setting_wsgi_app,
            trusted_proxy_addresses=trusted_proxy_addresses,
        )
        list(wrapped(environ, _start_response))
    finally:
        if saved is None:
            os.environ.pop("PYCHESTRATE_RUNTIME_ENVIRONMENT", None)
        else:
            os.environ["PYCHESTRATE_RUNTIME_ENVIRONMENT"] = saved

    rtnval = captured["headers"]
    return rtnval


def _set_cookie_value(headers: List[Tuple[str, str]]) -> str:
    """
        The single ``Set-Cookie`` value in ``headers``.
    """
    values = [value for name, value in headers if name.lower() == "set-cookie"]
    testbase.assert_equal(len(values), 1)
    rtnval = values[0]
    return rtnval


def test_environ_is_https_when_wsgi_scheme_is_https():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: A request whose WSGI scheme is https (TLS at the server,
    or a forwarded scheme gunicorn already applied) counts as HTTPS.**
    """
    policy = cookie_session.parse_trusted_proxy_addresses(raw="")
    environ = {"wsgi.url_scheme": "https", "REMOTE_ADDR": "198.51.100.7"}
    testbase.assert_equal(
        cookie_session.environ_is_https(environ=environ, policy=policy), True
    )
    return


def test_environ_is_https_when_loopback_proxy_forwards_https():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: With the default trust list, X-Forwarded-Proto: https
    from a proxy on 127.0.0.1 makes the request count as HTTPS.**
    """
    policy = cookie_session.parse_trusted_proxy_addresses(raw=None)
    environ = _https_proxy_environ(peer_address="127.0.0.1", forwarded_proto="https")
    testbase.assert_equal(
        cookie_session.environ_is_https(environ=environ, policy=policy), True
    )
    return


def test_environ_ignores_forwarded_proto_from_untrusted_peer():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: X-Forwarded-Proto: https from a peer that is not a
    trusted proxy is ignored.**
    """
    policy = cookie_session.parse_trusted_proxy_addresses(raw=None)
    environ = _https_proxy_environ(peer_address="203.0.113.9", forwarded_proto="https")
    testbase.assert_equal(
        cookie_session.environ_is_https(environ=environ, policy=policy), False
    )
    return


def test_environ_is_not_https_when_trusted_proxy_forwards_http():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: A trusted proxy that reports X-Forwarded-Proto: http
    leaves the request counted as plain HTTP.**
    """
    policy = cookie_session.parse_trusted_proxy_addresses(raw=None)
    environ = _https_proxy_environ(peer_address="127.0.0.1", forwarded_proto="http")
    testbase.assert_equal(
        cookie_session.environ_is_https(environ=environ, policy=policy), False
    )
    return


def test_environ_is_https_reads_the_client_facing_forwarded_proto():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: When proxies append to X-Forwarded-Proto, the first
    (client-facing) value decides: "https, http" counts as HTTPS.**
    """
    policy = cookie_session.parse_trusted_proxy_addresses(raw=None)
    environ = _https_proxy_environ(peer_address="127.0.0.1", forwarded_proto="https, http")
    testbase.assert_equal(
        cookie_session.environ_is_https(environ=environ, policy=policy), True
    )
    return


def test_default_trusted_proxies_include_ipv4_mapped_loopback():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: A dual-stack listener's IPv4-mapped loopback peer
    (::ffff:127.0.0.1) is trusted by the default list.**
    """
    policy = cookie_session.parse_trusted_proxy_addresses(raw=None)
    testbase.assert_equal(policy.trusts(peer_address="::ffff:127.0.0.1"), True)
    return


def test_trusted_proxy_network_covers_addresses_inside_it():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: A CIDR entry trusts every address inside the network
    and nothing outside it.**
    """
    policy = cookie_session.parse_trusted_proxy_addresses(raw="10.8.0.0/16")
    testbase.assert_equal(
        (policy.trusts(peer_address="10.8.3.4"), policy.trusts(peer_address="10.9.0.1")),
        (True, False),
    )
    return


def test_trusted_proxy_star_trusts_any_peer():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: "*" trusts X-Forwarded-Proto from any peer.**
    """
    policy = cookie_session.parse_trusted_proxy_addresses(raw="*")
    testbase.assert_equal(policy.trusts(peer_address="198.51.100.20"), True)
    return


def test_empty_trusted_proxy_list_trusts_no_peer():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: Setting PYCHESTRATE_TRUSTED_PROXY_ADDRESSES to an empty
    value trusts no proxy, loopback included.**
    """
    policy = cookie_session.parse_trusted_proxy_addresses(raw="")
    testbase.assert_equal(policy.trusts(peer_address="127.0.0.1"), False)
    return


def test_invalid_trusted_proxy_entry_raises_configuration_error():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: A trust-list entry that is not an address, a network or
    "*" stops startup with a ConfigurationError naming the entry.**
    """
    message = None
    try:
        cookie_session.parse_trusted_proxy_addresses(raw="127.0.0.1, nginx.local")
    except ConfigurationError as xcpt:
        message = str(xcpt)
    testbase.assert_equal(message is not None and "nginx.local" in message, True)
    return


def test_add_secure_attribute_appends_secure_when_absent():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: add_secure_attribute appends "; Secure" to a
    Set-Cookie value that lacks it.**
    """
    secured = cookie_session.add_secure_attribute(set_cookie_value=_SESSION_SET_COOKIE)
    testbase.assert_equal(secured, _SESSION_SET_COOKIE + "; Secure")
    return


def test_add_secure_attribute_does_not_duplicate_secure():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: A Set-Cookie value that already carries Secure is
    returned unchanged.**
    """
    already_secure = "sid=abc; Path=/; Secure; HttpOnly"
    secured = cookie_session.add_secure_attribute(set_cookie_value=already_secure)
    testbase.assert_equal(secured, already_secure)
    return


def test_policy_marks_cookie_secure_for_https_proxy_request_in_staging():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: The documented HTTPS alpha deploy (staging environment,
    nginx on 127.0.0.1 sending X-Forwarded-Proto: https) gets a Secure
    session cookie.**
    """
    headers = _headers_after_policy(
        runtime_environment="staging",
        environ=_https_proxy_environ(peer_address="127.0.0.1", forwarded_proto="https"),
    )
    testbase.assert_equal(_set_cookie_value(headers).endswith("; Secure"), True)
    return


def test_policy_leaves_cookie_unsecured_for_plain_http_in_staging():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: A staging server reached over plain HTTP keeps a cookie
    without Secure, so sign-in still works there.**
    """
    headers = _headers_after_policy(
        runtime_environment="staging",
        environ=_plain_http_environ(),
    )
    testbase.assert_equal(_set_cookie_value(headers), _SESSION_SET_COOKIE)
    return


def test_policy_ignores_https_claim_from_untrusted_peer_in_development():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: In development, X-Forwarded-Proto: https from a peer
    outside the trust list does not change the cookie.**
    """
    headers = _headers_after_policy(
        runtime_environment="development",
        environ=_https_proxy_environ(peer_address="192.0.2.44", forwarded_proto="https"),
    )
    testbase.assert_equal(_set_cookie_value(headers), _SESSION_SET_COOKIE)
    return


def test_policy_honors_configured_proxy_network():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: A proxy listed in the configured trust list (here a
    CIDR network) marks the cookie Secure when it forwards https.**
    """
    headers = _headers_after_policy(
        runtime_environment="staging",
        environ=_https_proxy_environ(peer_address="10.8.0.5", forwarded_proto="https"),
        trusted_proxy_addresses="10.8.0.0/24",
    )
    testbase.assert_equal(_set_cookie_value(headers).endswith("; Secure"), True)
    return


def test_policy_marks_cookie_secure_in_production_even_over_http():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: Production cookies always carry Secure, whatever the
    request scheme.**
    """
    headers = _headers_after_policy(
        runtime_environment="production",
        environ=_plain_http_environ(),
    )
    testbase.assert_equal(_set_cookie_value(headers).endswith("; Secure"), True)
    return


def test_policy_leaves_other_headers_untouched():
    """
    **Feature: DOC-04 secure session cookie**
    **Property: Only Set-Cookie headers change; every other header is
    passed through as the application produced it.**
    """
    headers = _headers_after_policy(
        runtime_environment="production",
        environ=_plain_http_environ(),
    )
    others = [(name, value) for name, value in headers if name.lower() != "set-cookie"]
    testbase.assert_equal(
        others,
        [("Content-Type", "text/html; charset=utf-8"), ("Location", "/")],
    )
    return
