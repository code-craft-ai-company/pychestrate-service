"""
.. module:: test_p32k_form_drafts_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: What a person typed survives an expired sign-in or form token (XC-11).

.. moduleauthor:: Code Craft AI LLC

A form submitted after the sign-in cookie expired, or with a stale anti-forgery token,
answered with a redirect that threw away everything typed (a build specification, a
release template). The service now keeps the fields of such a form for ten minutes
(never a secret-looking field, and only for the form paths that hold none), carries the
draft's token through the redirect and the sign-in, and hands the draft back once, to the
page it was for, so the shell can put it in the form. These tests cover the store, the
capture, the redirect addresses and the whole path through the application.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import io
import json
import re
import urllib.parse

from datetime import timedelta
from typing import Any, Dict, List, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ccai import testbase

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base
from ccai.pychestrate.webservice.security.auth.models import UiFormDraft
from ccai.pychestrate.webservice.webinterface.foundation import form_drafts

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    logged_in_cookies,
)


def _factory() -> Any:
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    PychestratePhase1Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_secret_looking_fields_and_empty_values_are_never_kept_and_sizes_are_bounded():
    """
    **Feature: form drafts (XC-11)**
    **Property: a field whose name says password, secret, token, credential, csrf,
    pepper, otp, mfa or private is dropped (any case), as is an empty value; an over-long
    value is clipped, and no more than 200 fields or 100000 characters are kept.**
    """
    pairs = [
        ("name", "Nightly build"), ("description", ""), ("Password", "hunter2"), ("api_token", "abc"), ("csrf_token", "t"),
        ("client_secret", "s"), ("credential_ref", "c"), ("Private_Key", "k"), ("steps", "x" * 25000), ("branch", "main"),
    ]
    kept = form_drafts.keepable_fields(pairs)
    many = form_drafts.keepable_fields([("f{}".format(i), "v") for i in range(500)])
    big = form_drafts.keepable_fields([("a{}".format(i), "y" * 20000) for i in range(20)])

    testbase.assert_equal(
        ([name for name, _v in kept], len(dict(kept)["steps"]), len(many), len(big)),
        (["name", "steps", "branch"], form_drafts.MAX_VALUE_CHARS, form_drafts.MAX_FIELDS, 5),
    )
    return


def test_a_draft_is_read_once_only_by_its_path_and_only_while_it_lasts():
    """
    **Feature: form drafts (XC-11)**
    **Property: a saved draft comes back once, for the path it was saved for and no
    other (a wrong path leaves it in place), then is gone; an expired one is removed
    and returns nothing; only a digest of the token is stored; a made-up or short token
    finds nothing; saving clears expired rows.**
    """
    factory = _factory()
    pairs = [("name", "Alpha"), ("description", "long text")]
    token = form_drafts.save_draft(path="/projects/create", pairs=pairs, session_factory=factory)

    wrong = form_drafts.take_draft(token=token, path="/projects/other", session_factory=factory)
    first = form_drafts.take_draft(token=token, path="/projects/create", session_factory=factory)
    second = form_drafts.take_draft(token=token, path="/projects/create", session_factory=factory)

    stale_token = form_drafts.save_draft(path="/projects/create", pairs=pairs, session_factory=factory)
    session = factory()
    row = session.query(UiFormDraft).one()
    stored_hash, token_in_row = row.token_hash, token in json.dumps([row.token_hash, row.path, row.fields])
    row.expires_at = utc_now() - timedelta(minutes=1)
    session.commit()
    session.close()
    expired = form_drafts.take_draft(token=stale_token, path="/projects/create", session_factory=factory)
    junk = [form_drafts.take_draft(token=value, path="/projects/create", session_factory=factory) for value in ("short", "x" * 40, "")]

    old_token = form_drafts.save_draft(path="/projects/a", pairs=pairs, session_factory=factory)
    session = factory()
    session.query(UiFormDraft).update({"expires_at": utc_now() - timedelta(minutes=5)})
    session.commit()
    session.close()
    form_drafts.save_draft(path="/projects/b", pairs=pairs, session_factory=factory)
    session = factory()
    left = [row.path for row in session.query(UiFormDraft).all()]
    session.close()

    testbase.assert_equal(
        (wrong, first, second, expired, junk, len(stored_hash), token_in_row, left),
        (None, pairs, None, None, [None, None, None], 64, False, ["/projects/b"]),
    )
    return


def test_a_form_with_nothing_to_keep_is_not_stored():
    """
    **Feature: form drafts (XC-11)**
    **Property: a form whose every field is empty or secret-looking saves nothing and
    returns no token.**
    """
    factory = _factory()
    token = form_drafts.save_draft(path="/projects/create", pairs=[("password", "x"), ("name", "")], session_factory=factory)
    session = factory()
    count = session.query(UiFormDraft).count()
    session.close()

    testbase.assert_equal((token, count), (None, 0))
    return


def test_the_redirect_address_carries_the_draft_and_a_sign_in_address_carries_it_in_next():
    """
    **Feature: form drafts (XC-11)**
    **Property: an ordinary redirect address gains ``draft=<token>`` (an existing query is
    kept); a sign-in address gains it inside its ``next`` so it is still there after
    signing in (and an off-site ``next`` is left alone); asking for a draft with no form
    captured changes nothing.**
    """
    token = "tok-" + "x" * 30
    ordinary = form_drafts.with_draft_token("/projects/7/edit?tab=main", token)
    sign_in = form_drafts.with_draft_token("/login?next=/projects/7/edit%3Ftab%3Dmain", token)
    off_site = form_drafts.with_draft_token("/login?next=//evil.example/x", token)

    ordinary_query = urllib.parse.parse_qs(urllib.parse.urlsplit(ordinary).query)
    sign_in_next = urllib.parse.parse_qs(urllib.parse.urlsplit(sign_in).query)["next"][0]
    next_parts = urllib.parse.urlsplit(sign_in_next)
    next_query = urllib.parse.parse_qs(next_parts.query)

    testbase.assert_equal(
        (
            ordinary.startswith("/projects/7/edit?"), sorted(ordinary_query), ordinary_query["draft"], next_parts.path, sorted(next_query),
            sorted(urllib.parse.parse_qs(urllib.parse.urlsplit(off_site).query)), form_drafts.want_draft("/projects/create"),
        ),
        (True, ["draft", "tab"], [token], "/projects/7/edit", ["draft", "tab"], ["draft", "next"], "/projects/create"),
    )
    return


def test_the_wsgi_wrapper_notes_a_kept_form_hands_the_body_on_and_forgets_it():
    """
    **Feature: form drafts (XC-11)**
    **Property: for a urlencoded POST to a kept path the wrapped application still reads
    the whole body and sees the form noted while it runs; the form is forgotten as soon
    as the response is ready and when the application raises; another method, another
    path, a multipart body or an oversized one is passed through without being noted.**
    """
    seen: List[Any] = []

    def _app(environ: Dict[str, Any], start_response: Any) -> List[bytes]:
        captured = getattr(form_drafts._CURRENT, "value", None)
        seen.append((environ["wsgi.input"].read(), None if captured is None else (captured.path, captured.pairs)))
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ok"]

    def _explode(environ: Dict[str, Any], start_response: Any) -> List[bytes]:
        environ["wsgi.input"].read()
        raise RuntimeError("boom")

    wrapped = form_drafts.wrap_wsgi_app_with_form_capture(wsgi_app=_app)

    def _call(app: Any, *, method: str = "POST", path: str = "/projects/create", content_type: str = "application/x-www-form-urlencoded", body: bytes = b"name=Alpha&x=1") -> Any:
        environ = {
            "REQUEST_METHOD": method, "PATH_INFO": path, "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body),
        }
        return app(environ, lambda status, headers, exc_info=None: None)

    result = _call(wrapped)
    during = seen[-1]
    after = getattr(form_drafts._CURRENT, "value", None)

    passed_through = []
    for kwargs in (
        {"method": "GET"}, {"path": "/admin/secrets"}, {"content_type": "multipart/form-data; boundary=x"},
        {"body": b"a=" + b"b" * (form_drafts.MAX_BODY_BYTES + 10)},
    ):
        _call(wrapped, **kwargs)
        passed_through.append(seen[-1][1])

    raised = False
    try:
        _call(form_drafts.wrap_wsgi_app_with_form_capture(wsgi_app=_explode))
    except RuntimeError:
        raised = True
    after_error = getattr(form_drafts._CURRENT, "value", None)

    testbase.assert_equal(
        (during, result, after, passed_through, raised, after_error),
        ((b"name=Alpha&x=1", ("/projects/create", [("name", "Alpha"), ("x", "1")])), [b"ok"], None, [None, None, None, None], True, None),
    )
    return


def test_the_wrapper_saves_the_draft_after_the_handler_and_puts_the_token_in_the_redirect():
    """
    **Feature: form drafts (XC-11)**
    **Property: when the application asks for a draft and answers with a redirect, the
    wrapper saves the form and the ``Location`` it sends carries the token (inside ``next``
    for a sign-in address); a redirect nobody asked a draft for, an answer that is not a
    redirect and a form with nothing worth keeping are passed on unchanged and store
    nothing.**
    """
    factory = _factory()

    def _redirecting(location: str, ask: bool, status: str = "302 Found") -> Any:
        def _app(environ: Dict[str, Any], start_response: Any) -> List[bytes]:
            environ["wsgi.input"].read()
            if ask:
                form_drafts.want_draft(location)
            start_response(status, [("Location", location), ("Set-Cookie", "a=b")])
            return [b""]
        return form_drafts.wrap_wsgi_app_with_form_capture(wsgi_app=_app, session_factory=factory)

    def _run(app: Any, body: bytes) -> Tuple[str, Dict[str, str]]:
        sent: Dict[str, Any] = {}
        environ = {"REQUEST_METHOD": "POST", "PATH_INFO": "/projects/create", "CONTENT_TYPE": "application/x-www-form-urlencoded", "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
        app(environ, lambda status, headers, exc_info=None: sent.update(status=status, headers=dict(headers)))
        return sent["status"], sent["headers"]

    asked = _run(_redirecting("/projects/create", True), b"name=Alpha")
    sign_in = _run(_redirecting("/login?next=/projects/create", True), b"name=Beta")
    not_asked = _run(_redirecting("/projects/create", False), b"name=Gamma")
    not_a_redirect = _run(_redirecting("/projects/create", True, status="200 OK"), b"name=Delta")
    nothing_to_keep = _run(_redirecting("/projects/create", True), b"password=x")
    session = factory()
    stored = sorted(fields[0][1] for (fields,) in session.query(UiFormDraft.fields).all())
    session.close()

    testbase.assert_equal(
        (
            asked[0], asked[1]["Location"].startswith("/projects/create?draft="), asked[1]["Set-Cookie"],
            urllib.parse.unquote(sign_in[1]["Location"]).startswith("/login?next=/projects/create?draft="),
            not_asked[1]["Location"], not_a_redirect[1]["Location"], nothing_to_keep[1]["Location"], stored,
        ),
        ("302 Found", True, "a=b", True, "/projects/create", "/projects/create", "/projects/create", ["Alpha", "Beta"]),
    )
    return


def _post(handle: Any, cookies: Dict[str, str], path: str, fields: List[Tuple[str, str]]) -> Any:
    body = urllib.parse.urlencode(fields).encode("utf-8")
    return drive_request(
        wsgi_app=handle.wsgi_app, method="POST", path=path, body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, cookies=cookies,
    )


def _island(html: str) -> Any:
    found = re.search(r'<script type="application/json" id="pyc-form-draft">(.*?)</script>', html, re.S)
    return json.loads(found.group(1).replace("\\u0026", "&").replace("\\u0027", "'").replace("\\u003c", "<").replace("\\u003e", ">")) if found else None


def test_a_stale_form_token_comes_back_to_the_form_with_what_was_typed():
    """
    **Feature: form drafts (XC-11)**
    **Property: a project create form posted with a wrong token is redirected to
    /projects/create?draft=<token>; opening that address shows the typed name and
    description in the page's draft data (a password-named field is not in it); a second
    open, or the same token on another page, shows none.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)

    refused = _post(handle, cookies, "/projects/create", [("csrf_token", "stale"), ("name", "Typed-Name"), ("description", "A long description"), ("password", "hunter2")])
    location = refused.header("Location") or ""
    parts = urllib.parse.urlsplit(location)
    token = urllib.parse.parse_qs(parts.query).get("draft", [""])[0]

    elsewhere = drive_request(wsgi_app=handle.wsgi_app, method="GET", path="/projects/list", query_string="draft=" + token, cookies=cookies)
    first = drive_request(wsgi_app=handle.wsgi_app, method="GET", path=parts.path, query_string=parts.query, cookies=cookies)
    second = drive_request(wsgi_app=handle.wsgi_app, method="GET", path=parts.path, query_string=parts.query, cookies=cookies)

    testbase.assert_equal(
        (refused.status_code, parts.path, len(token) > 20, _island(elsewhere.text), _island(first.text), _island(second.text), "hunter2" in first.text, token in first.text),
        (302, "/projects/create", True, None, [["name", "Typed-Name"], ["description", "A long description"]], None, False, False),
    )
    return


def test_an_expired_sign_in_sends_the_person_to_sign_in_and_back_with_the_draft():
    """
    **Feature: form drafts (XC-11)**
    **Property: a project create form posted with no session is redirected to the sign-in
    page whose ``next`` is /projects/create?draft=<token>; after signing in, opening
    that address shows what was typed.**
    """
    handle = ensure_app()
    signed_in = logged_in_cookies(wsgi_app=handle.wsgi_app)

    refused = _post(handle, {}, "/projects/create", [("name", "Typed-Before-Expiry"), ("description", "Kept across sign-in")])
    location = urllib.parse.urlsplit(refused.header("Location") or "")
    target = urllib.parse.parse_qs(location.query).get("next", [""])[0]
    target_parts = urllib.parse.urlsplit(target)
    reopened = drive_request(wsgi_app=handle.wsgi_app, method="GET", path=target_parts.path, query_string=target_parts.query, cookies=signed_in)

    testbase.assert_equal(
        (refused.status_code in (302, 303), location.path.endswith("/login"), target_parts.path, sorted(urllib.parse.parse_qs(target_parts.query)), _island(reopened.text)),
        (True, True, "/projects/create", ["draft"], [["name", "Typed-Before-Expiry"], ["description", "Kept across sign-in"]]),
    )
    return


def test_forms_that_may_hold_secrets_are_not_kept():
    """
    **Feature: form drafts (XC-11)**
    **Property: a secret created with a stale token, and a project form whose only
    fields are secret-looking, are refused as before, with no draft in the redirect.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)

    secret = _post(handle, cookies, "/admin/secrets", [("csrf_token", "stale"), ("name", "db"), ("value", "s3cret")])
    only_secret = _post(handle, cookies, "/projects/create", [("csrf_token", "stale"), ("password", "hunter2")])

    testbase.assert_equal(
        ["draft=" in (response.header("Location") or "") for response in (secret, only_secret)],
        [False, False],
    )
    return


def test_both_production_app_builders_wrap_the_application():
    """
    **Feature: form drafts (XC-11)**
    **Property: the development entry point and the production WSGI factory in
    app_pychestrate_main each apply the form capture wrapper (the harness applies it
    too, so the tests above exercise the same stack).**
    """
    import os

    root = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isfile(os.path.join(root, "source", "site", "app_pychestrate_main.py")) and root != os.path.dirname(root):
        root = os.path.dirname(root)
    with open(os.path.join(root, "source", "site", "app_pychestrate_main.py"), encoding="utf-8") as handle:
        source = handle.read()

    testbase.assert_equal(
        (source.count("wrap_wsgi_app_with_form_capture(wsgi_app="), "form_drafts import" in source or "foundation.form_drafts import" in source),
        (2, True),
    )
    return
