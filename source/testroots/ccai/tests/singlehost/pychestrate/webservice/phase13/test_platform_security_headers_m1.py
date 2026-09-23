"""
.. module:: test_platform_security_headers_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Regression locks for the security response headers
               (audit ADM-32).

.. moduleauthor:: Code Craft AI LLC

Before ADM-32 no response carried a CSP, frame protection, nosniff,
a referrer policy or no-store, and pressing Back after signing out
showed the cached users list. These tests pin the WSGI layer that now
adds them:

* HTML gets a CSP whose script nonce is the one the templates rendered,
  with no 'unsafe-inline' / 'unsafe-eval' for scripts;
* pages are not framable (frame-ancestors 'none' + X-Frame-Options),
  except the /embed/ views meant for third-party frames;
* nosniff and Referrer-Policy on every response;
* no-store on HTML / JSON unless the handler chose its own caching;
* HSTS only on production HTTPS;
* every inline <script> in the templates carries the nonce and no
  template uses inline event handlers;
* both entry points wrap the application.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from typing import Any, Dict, List, Optional, Tuple

import jinja2

from ccai import testbase

from ccai.pychestrate.webservice.hardening import security_headers
from ccai.pychestrate.webservice.hardening.platform_wsgi import (
    wrap_platform_wsgi_application,
)
from ccai.pychestrate.webservice.webinterface.foundation.templating import (
    install_template_globals,
)


def _inner_app(*, content_type: str, extra_headers: Optional[List[Tuple[str, str]]] = None) -> Any:
    """
        A WSGI app that renders ``csp_nonce()`` into its body the way a
        template would.
    """
    def _app(environ: Dict[str, Any], start_response: Any) -> Any:
        body = security_headers.csp_nonce().encode("utf-8")
        headers = [("Content-Type", content_type)] + list(extra_headers or [])
        start_response("200 OK", headers)
        return [body]

    return _app


def _call(
        *,
        app: Any,
        path: str = "/admin/users",
        environ_extra: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[str, str], bytes]:
    captured: Dict[str, Any] = {}

    def start_response(status: str, headers: List[Tuple[str, str]], exc_info: Any = None) -> Any:
        captured["headers"] = headers
        return lambda chunk: None

    environ: Dict[str, Any] = {"PATH_INFO": path, "REQUEST_METHOD": "GET", "wsgi.url_scheme": "http"}
    environ.update(environ_extra or {})
    body = b"".join(app(environ, start_response))
    headers = {name: value for name, value in captured["headers"]}
    return headers, body


def _wrapped(**kwargs: Any) -> Any:
    rtnval = security_headers.wrap_wsgi_application_with_security_headers(
        wsgi_app=_inner_app(content_type=kwargs.pop("content_type", "text/html; charset=utf-8"),
                            extra_headers=kwargs.pop("extra_headers", None)),
        **kwargs,
    )
    return rtnval


def _directive(policy: str, name: str) -> str:
    for directive in policy.split(";"):
        directive = directive.strip()
        if directive.startswith(name + " "):
            return directive
    return ""


# ---------------------------------------------------------------------------
# CSP
# ---------------------------------------------------------------------------


def test_html_response_carries_a_csp_with_the_rendered_nonce():
    """
    **Feature: security headers (ADM-32)**
    **Property: the CSP's script-src allows exactly the nonce the
    templates rendered for this response.**
    """
    headers, body = _call(app=_wrapped())
    script_src = _directive(headers["Content-Security-Policy"], "script-src")
    testbase.assert_equal(script_src, "script-src 'self' 'nonce-{}'".format(body.decode("utf-8")))
    return


def test_script_policy_allows_no_inline_or_eval():
    """
    **Feature: security headers (ADM-32)**
    **Property: script-src contains neither 'unsafe-inline' nor
    'unsafe-eval'.**
    """
    headers, _ = _call(app=_wrapped())
    script_src = _directive(headers["Content-Security-Policy"], "script-src")
    testbase.assert_equal(("unsafe-inline" in script_src, "unsafe-eval" in script_src), (False, False))
    return


def test_each_response_gets_a_fresh_nonce():
    """
    **Feature: security headers (ADM-32)**
    **Property: two requests get two different nonces.**
    """
    app = _wrapped()
    _, first = _call(app=app)
    _, second = _call(app=app)
    testbase.assert_not_equal(first, second)
    return


def test_csp_blocks_plugins_and_foreign_form_targets():
    """
    **Feature: security headers (ADM-32)**
    **Property: the policy sets object-src 'none', base-uri 'self' and
    form-action 'self'.**
    """
    headers, _ = _call(app=_wrapped())
    policy = headers["Content-Security-Policy"]
    testbase.assert_equal(
        (_directive(policy, "object-src"), _directive(policy, "base-uri"), _directive(policy, "form-action")),
        ("object-src 'none'", "base-uri 'self'", "form-action 'self'"),
    )
    return


def test_json_response_carries_no_csp():
    """
    **Feature: security headers (ADM-32)**
    **Property: the document policy is only attached to HTML.**
    """
    headers, _ = _call(app=_wrapped(content_type="application/json"), path="/api/v1/me")
    testbase.assert_equal("Content-Security-Policy" in headers, False)
    return


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------


def test_pages_cannot_be_framed():
    """
    **Feature: security headers (ADM-32)**
    **Property: an ordinary page answers frame-ancestors 'none' and
    X-Frame-Options: DENY.**
    """
    headers, _ = _call(app=_wrapped())
    testbase.assert_equal(
        (_directive(headers["Content-Security-Policy"], "frame-ancestors"), headers.get("X-Frame-Options")),
        ("frame-ancestors 'none'", "DENY"),
    )
    return


def test_embed_views_stay_framable():
    """
    **Feature: security headers (ADM-32)**
    **Property: /embed/ views (signed, meant for third-party iframes)
    answer frame-ancestors * and no X-Frame-Options.**
    """
    headers, _ = _call(app=_wrapped(), path="/embed/run_detail")
    testbase.assert_equal(
        (_directive(headers["Content-Security-Policy"], "frame-ancestors"), "X-Frame-Options" in headers),
        ("frame-ancestors *", False),
    )
    return


# ---------------------------------------------------------------------------
# nosniff / referrer / caching / HSTS
# ---------------------------------------------------------------------------


def test_every_response_is_nosniff_with_a_referrer_policy():
    """
    **Feature: security headers (ADM-32)**
    **Property: a static JavaScript response also carries
    X-Content-Type-Options: nosniff and Referrer-Policy: same-origin.**
    """
    headers, _ = _call(app=_wrapped(content_type="text/javascript"), path="/static/javascript/x.js")
    testbase.assert_equal(
        (headers.get("X-Content-Type-Options"), headers.get("Referrer-Policy")),
        ("nosniff", "same-origin"),
    )
    return


def test_html_is_not_stored_by_the_browser():
    """
    **Feature: security headers (ADM-32)**
    **Property: an HTML page with no caching policy of its own is sent
    Cache-Control: no-store, so Back after sign-out re-requests it.**
    """
    headers, _ = _call(app=_wrapped())
    testbase.assert_equal(headers.get("Cache-Control"), "no-store")
    return


def test_api_json_is_not_stored_by_the_browser():
    """
    **Feature: security headers (ADM-32)**
    **Property: an API JSON response with no caching policy is sent
    Cache-Control: no-store.**
    """
    headers, _ = _call(app=_wrapped(content_type="application/json"), path="/api/v1/secrets")
    testbase.assert_equal(headers.get("Cache-Control"), "no-store")
    return


def test_handler_caching_policy_is_kept():
    """
    **Feature: security headers (ADM-32)**
    **Property: a response that already declares Cache-Control (static
    assets) keeps its own value.**
    """
    app = _wrapped(
        content_type="text/css",
        extra_headers=[("Cache-Control", "public, max-age=31536000, immutable")],
    )
    headers, _ = _call(app=app, path="/static/styles/a.css")
    testbase.assert_equal(headers.get("Cache-Control"), "public, max-age=31536000, immutable")
    return


def test_hsts_is_sent_on_production_https():
    """
    **Feature: security headers (ADM-32)**
    **Property: with HSTS enabled, a request forwarded as HTTPS gets
    Strict-Transport-Security.**
    """
    headers, _ = _call(app=_wrapped(hsts_enabled=True), environ_extra={"HTTP_X_FORWARDED_PROTO": "https"})
    testbase.assert_equal(headers.get("Strict-Transport-Security"), security_headers.HSTS_VALUE)
    return


def test_hsts_is_not_sent_outside_production():
    """
    **Feature: security headers (ADM-32)**
    **Property: the platform layer only enables HSTS in the production
    runtime environment.**
    """
    app = wrap_platform_wsgi_application(
        wsgi_app=_inner_app(content_type="text/html"), runtime_environment="staging",
    )
    headers, _ = _call(app=app, environ_extra={"wsgi.url_scheme": "https"})
    testbase.assert_equal("Strict-Transport-Security" in headers, False)
    return


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def test_templates_can_call_csp_nonce():
    """
    **Feature: security headers (ADM-32)**
    **Property: install_template_globals installs csp_nonce, which
    renders the active request's nonce.**
    """
    environment = jinja2.Environment(loader=jinja2.DictLoader({"t.html": "{{ csp_nonce() }}"}))
    install_template_globals(environment=environment)
    security_headers.set_active_csp_nonce(nonce="abc123")
    rendered = environment.get_template("t.html").render()
    testbase.assert_equal(rendered, "abc123")
    return


def _template_files() -> List[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    site = os.path.normpath(os.path.join(here, "..", "..", "..", "..", "..", "..", "..", "site"))
    found: List[str] = []
    for current, _, files in os.walk(site):
        for name in files:
            if name.endswith(".html"):
                found.append(os.path.join(current, name))
    rtnval = sorted(found)
    return rtnval


_SCRIPT_TAG = re.compile(r"<script\b([^>]*)>", re.IGNORECASE)
_EVENT_HANDLER = re.compile(r"\son[a-z]+\s*=\s*[\"']", re.IGNORECASE)


def test_every_inline_script_in_the_templates_carries_the_nonce():
    """
    **Feature: security headers (ADM-32)**
    **Property: every executable inline <script> in a template (no src,
    not a JSON data block) has nonce="{{ csp_nonce() }}" -- otherwise
    the CSP would block it.**
    """
    missing: List[str] = []
    for path in _template_files():
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
        for match in _SCRIPT_TAG.finditer(text):
            attributes = match.group(1)
            if "src=" in attributes or "application/json" in attributes:
                continue
            if 'nonce="{{ csp_nonce() }}"' not in attributes:
                missing.append("{}: {}".format(os.path.basename(path), match.group(0)))
    testbase.assert_equal(missing, [])
    return


def test_no_template_uses_inline_event_handlers():
    """
    **Feature: security headers (ADM-32)**
    **Property: no template carries on*="..." handler attributes, which
    a nonce cannot cover (use data-confirm / delegated listeners).**
    """
    offenders: List[str] = []
    for path in _template_files():
        with open(path, "r", encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if _EVENT_HANDLER.search(line):
                    offenders.append("{}:{}".format(os.path.basename(path), number))
    testbase.assert_equal(offenders, [])
    return


def test_nginx_template_sends_hsts_once_on_https():
    """
    **Feature: security headers (ADM-32)**
    **Property: the nginx HTTPS server block adds HSTS (always) and hides
    the upstream copy so the header appears once.**
    """
    here = os.path.dirname(os.path.abspath(__file__))
    template = os.path.normpath(os.path.join(
        here, "..", "..", "..", "..", "..", "..", "..", "..", "deployment", "pychestrate.nginx.conf.template",
    ))
    with open(template, "r", encoding="utf-8") as handle:
        text = handle.read()
    https_block = text[text.index("listen 443 ssl"):]
    testbase.assert_equal(
        (
            re.search(r'add_header\s+Strict-Transport-Security\s+"max-age=\d+"\s+always;', https_block) is not None,
            "proxy_hide_header Strict-Transport-Security;" in https_block,
        ),
        (True, True),
    )
    return


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_both_entry_points_wrap_the_platform_layers():
    """
    **Feature: security headers (ADM-32)**
    **Property: app_pychestrate_main wraps the WSGI app with
    wrap_platform_wsgi_application in the built-in server entry point
    and in the gunicorn factory.**
    """
    here = os.path.dirname(os.path.abspath(__file__))
    main_path = os.path.normpath(
        os.path.join(here, "..", "..", "..", "..", "..", "..", "..", "site", "app_pychestrate_main.py")
    )
    with open(main_path, "r", encoding="utf-8") as handle:
        text = handle.read()
    website_main = text[text.index("def pychestrate_website_main"):text.index("def build_wsgi_application_for_production")]
    factory = text[text.index("def build_wsgi_application_for_production"):]
    testbase.assert_equal(
        ("wrap_platform_wsgi_application(" in website_main, "wrap_platform_wsgi_application(" in factory),
        (True, True),
    )
    return
