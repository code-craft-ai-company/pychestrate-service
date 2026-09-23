"""
.. module:: test_p30c_remediation_regressions_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Regression locks for the UI remediation fixes that do
               not need a database or a browser.

.. moduleauthor:: Code Craft AI LLC

Each test pins one property the remediation introduced: content-hashed
static URLs with immutable caching, ETag revalidation, a 404 (not a
sign-in prompt) for unknown paths, segment-boundary bundle prefixes,
shell-wrapped resources handlers, the admin bundle mount point, the
referer-aware deny redirect, and the shared template filters.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum
import os
import tempfile

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.foundation import (
    static_files,
    templating,
)
from ccai.pychestrate.webservice.webinterface.site_shell import (
    bundle_registry,
    catchall_route,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    FakeApp,
)


class _Mapping:
    def __init__(self, values: Optional[Dict[str, str]] = None) -> None:
        self._values = values if values is not None else {}
        return

    def get(self, key: str, default: Any = None) -> Any:
        rtnval = self._values.get(key, default)
        return rtnval


class _FakeRequest:
    def __init__(
            self,
            *,
            path: str = "/",
            path_params: Optional[Dict[str, str]] = None,
            query: Optional[Dict[str, str]] = None,
            headers: Optional[Dict[str, str]] = None
        ) -> None:
        self.path = path
        self.path_params = path_params if path_params is not None else {}
        self.query_params = _Mapping(query)
        self.headers = _Mapping(headers)
        return


def _static_root_with_file(*, name: str, content: bytes) -> str:
    root = tempfile.mkdtemp(prefix="pyc-static-")
    with open(os.path.join(root, name), "wb") as fh:
        fh.write(content)
    return root


# ---------------------------------------------------------------------------
# Static assets (audit A-3 / L-2)
# ---------------------------------------------------------------------------


def test_static_url_appends_a_content_hash():
    """
    **Feature: ui-remediation static caching**
    **Property: build_static_url returns /static/<path>?v=<hash> for
    a file that exists, and the hash changes when the content does.**
    """
    root = _static_root_with_file(name="a.css", content=b"body{}")
    static_files.configure_static_url_root(static_root=root)
    try:
        first = static_files.build_static_url("a.css")
        testbase.assert_true(first.startswith("/static/a.css?v="), first)
        with open(os.path.join(root, "a.css"), "wb") as fh:
            fh.write(b"body{color:red}")
        os.utime(os.path.join(root, "a.css"), (1, 1))
        second = static_files.build_static_url("a.css")
        testbase.assert_true(first != second, "hash did not change with content")
    finally:
        static_files.configure_static_url_root(static_root=root)
    return


def test_versioned_static_response_is_immutable_and_carries_an_etag():
    """
    **Feature: ui-remediation static caching**
    **Property: a request with ?v= is served with a one-year immutable
    Cache-Control and an ETag; a bare request is served no-cache.**
    """
    root = _static_root_with_file(name="b.js", content=b"console.log(1)")
    versioned = static_files.serve_static_file(
        request=_FakeRequest(path_params={"filepath": "b.js"}, query={"v": "abc"}),
        static_root=root,
    )
    testbase.assert_equal(versioned.status_code, 200)
    testbase.assert_true("immutable" in versioned.headers["Cache-Control"])
    testbase.assert_true(versioned.headers["ETag"].startswith('"'))
    bare = static_files.serve_static_file(
        request=_FakeRequest(path_params={"filepath": "b.js"}),
        static_root=root,
    )
    testbase.assert_equal(bare.headers["Cache-Control"], "no-cache")
    return


def test_matching_if_none_match_yields_304():
    """
    **Feature: ui-remediation static caching**
    **Property: a request whose If-None-Match equals the asset's ETag
    receives 304 with an empty body.**
    """
    root = _static_root_with_file(name="c.css", content=b"p{}")
    first = static_files.serve_static_file(
        request=_FakeRequest(path_params={"filepath": "c.css"}),
        static_root=root,
    )
    etag = first.headers["ETag"]
    second = static_files.serve_static_file(
        request=_FakeRequest(path_params={"filepath": "c.css"}, headers={"If-None-Match": etag}),
        static_root=root,
    )
    testbase.assert_equal(second.status_code, 304)
    return


# ---------------------------------------------------------------------------
# Catch-all + bundle prefixes (audit L-4 / S-21)
# ---------------------------------------------------------------------------


def test_bundle_prefix_matching_respects_segment_boundaries():
    """
    **Feature: ui-remediation shell routing**
    **Property: /admins does not load the admin bundle; /admin and
    /admin/users do.**
    """
    bundle_registry.install_default_bundles()
    testbase.assert_true("pyc-admin-bundle" in bundle_registry.bundles_for(path="/admin"))
    testbase.assert_true("pyc-admin-bundle" in bundle_registry.bundles_for(path="/admin/users"))
    testbase.assert_true("pyc-admin-bundle" not in bundle_registry.bundles_for(path="/admins"))
    return


def test_unknown_path_is_not_a_known_shell_route():
    """
    **Feature: ui-remediation catch-all**
    **Property: the shell root and bundle-owned paths are known shell
    routes; a mistyped path is not, so anonymous visitors get a 404
    instead of a sign-in redirect.**
    """
    testbase.assert_equal(catchall_route._is_known_shell_route(path="/"), True)
    testbase.assert_equal(catchall_route._is_known_shell_route(path="/runs"), True)
    testbase.assert_equal(catchall_route._is_known_shell_route(path="/runs/42"), True)
    testbase.assert_equal(catchall_route._is_known_shell_route(path="/nonexistent-page"), False)
    return


def test_not_found_response_for_browser_path_is_html_with_home_link():
    """
    **Feature: ui-remediation error pages**
    **Property: a browser-facing 404 is a complete HTML document that
    says "Page not found" and links home; API-ish paths stay plain
    text.**
    """
    templating.reset_default_environment_for_testing()
    html_response = catchall_route._build_not_found_response(
        path="/nonexistent-page", request=_FakeRequest(path="/nonexistent-page")
    )
    testbase.assert_equal(html_response.status_code, 404)
    body = html_response._body.decode("utf-8")
    testbase.assert_true("Page not found" in body)
    testbase.assert_true('href="/"' in body)
    api_response = catchall_route._build_not_found_response(
        path="/api/v1/nope", request=_FakeRequest(path="/api/v1/nope")
    )
    testbase.assert_equal(api_response.status_code, 404)
    testbase.assert_true(api_response.headers["Content-Type"].startswith("text/plain"))
    return


# ---------------------------------------------------------------------------
# Shell wrapping + admin mount point (audit R-1 / S-1)
# ---------------------------------------------------------------------------


def test_every_resources_handler_renders_inside_the_shell():
    """
    **Feature: ui-remediation resources in the shell**
    **Property: every route the resources blueprint attaches is the
    shell-wrapping handler, not the bare fragment renderer.**
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes import (
        register_resources_routes,
    )
    app = FakeApp()
    register_resources_routes(app=app)
    testbase.assert_true(len(app.routes) > 0)
    bare = [path for path, _methods, handler in app.routes if not handler.__name__.endswith("_in_shell")]
    testbase.assert_equal(bare, [])
    return


def test_admin_bundle_routes_render_the_mount_point_not_the_dashboard():
    """
    **Feature: ui-remediation admin landing**
    **Property: /admin, /admin/overview, /admin/feature-flags,
    /admin/extensions and /admin/system-health map to the bundle mount
    handler; only /admin/dashboard renders the dashboard cards.**
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import routes as config_routes
    table = config_routes._HANDLERS_BY_ENDPOINT
    for endpoint in ("config.dashboard_root", "config.admin_overview", "config.feature_flags", "config.extension_registry", "config.system_health"):
        testbase.assert_equal(table[endpoint] is config_routes.handle_bundle_mount, True, endpoint)
    testbase.assert_equal(table["config.dashboard"] is config_routes.handle_dashboard, True)
    return


def test_deny_redirect_prefers_same_origin_referer():
    """
    **Feature: ui-remediation permission denials (P-44)**
    **Property: a denied request goes back to a same-origin Referer,
    never to a cross-origin one and never to the denied URL itself.**
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import routes as config_routes

    class _Auth:
        def __init__(self, request: Any) -> None:
            self.request = request

    same = _Auth(_FakeRequest(path="/projects/7/watches/create", headers={"Referer": "/projects/7/watches", "Host": "pyc.local"}))
    testbase.assert_equal(config_routes._deny_redirect_target(auth=same, fallback_url="/fallback"), "/projects/7/watches")
    absolute = _Auth(_FakeRequest(path="/x", headers={"Referer": "https://pyc.local/projects/7", "Host": "pyc.local"}))
    testbase.assert_equal(config_routes._deny_redirect_target(auth=absolute, fallback_url="/fallback"), "/projects/7")
    foreign = _Auth(_FakeRequest(path="/x", headers={"Referer": "https://evil.example/steal", "Host": "pyc.local"}))
    testbase.assert_equal(config_routes._deny_redirect_target(auth=foreign, fallback_url="/fallback"), "/fallback")
    self_loop = _Auth(_FakeRequest(path="/projects/7/watches/create", headers={"Referer": "/projects/7/watches/create?x=1", "Host": "pyc.local"}))
    testbase.assert_equal(config_routes._deny_redirect_target(auth=self_loop, fallback_url="/fallback"), "/fallback")
    return


# ---------------------------------------------------------------------------
# Shared template filters (audit P-23 / P-41 / R-23)
# ---------------------------------------------------------------------------


def test_format_datetime_renders_a_time_element_and_a_placeholder_for_none():
    """
    **Feature: ui-remediation shared filters**
    **Property: format_datetime emits <time datetime=ISO> with the
    zone spelled out, and an em dash for None.**
    """
    rendered = str(templating.format_datetime_filter(datetime(2026, 9, 4, 13, 45, tzinfo=timezone.utc)))
    testbase.assert_true(rendered.startswith('<time datetime="2026-09-04T13:45:00+00:00"'), rendered)
    testbase.assert_true("2026-09-04 13:45 UTC" in rendered, rendered)
    testbase.assert_equal(templating.format_datetime_filter(None), templating.DISPLAY_PLACEHOLDER)
    return


def test_status_tone_is_consistent_for_enums_and_strings():
    """
    **Feature: ui-remediation shared filters**
    **Property: the same status value maps to the same tone whether it
    arrives as an Enum member or a plain string; unknown values fall
    back to secondary; exclusive allocation mode is not red.**
    """
    class _St(str, enum.Enum):
        RUNNING = "running"
        FAILED = "failed"

    testbase.assert_equal(templating.status_tone_filter(_St.RUNNING), "info")
    testbase.assert_equal(templating.status_tone_filter("running"), "info")
    testbase.assert_equal(templating.status_tone_filter(_St.FAILED), "danger")
    testbase.assert_equal(templating.status_tone_filter("exclusive"), "info")
    testbase.assert_equal(templating.status_tone_filter("something-new"), "secondary")
    testbase.assert_equal(templating.enum_value_filter(_St.RUNNING), "running")
    return


def test_display_filter_replaces_none_and_blank_with_a_dash():
    """
    **Feature: ui-remediation shared filters**
    **Property: display renders None and whitespace-only strings as an
    em dash and passes other values through unchanged.**
    """
    testbase.assert_equal(templating.display_filter(None), templating.DISPLAY_PLACEHOLDER)
    testbase.assert_equal(templating.display_filter("   "), templating.DISPLAY_PLACEHOLDER)
    testbase.assert_equal(templating.display_filter(0), 0)
    testbase.assert_equal(templating.display_filter("alpha"), "alpha")
    return


# ---------------------------------------------------------------------------
# Secrets bundle input events (audit B-1)
# ---------------------------------------------------------------------------


def test_secrets_view_listens_for_component_change_events():
    """
    **Feature: ui-remediation secrets bundle**
    **Property: the scope-reference and name-filter fields listen for
    the mj-change event the text-field component emits, not the
    native change event that never leaves its shadow root.**
    """
    from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES
    source_path = os.path.join(
        SITE_DIRECTORIES.DIR_STATIC, "javascript", "pyc-secrets-bundle", "secrets-view.js"
    )
    with open(source_path, encoding="utf-8") as fh:
        source = fh.read()
    testbase.assert_true('addEventListener("mj-change"' in source)
    testbase.assert_equal('input.addEventListener("change"' in source, False)
    return


def test_every_template_table_header_is_a_well_formed_thead():
    """
    **Feature: UI remediation regression locks (XC-16)**
    **Property: no server template carries the mangled
    ``<th scope="col"ead>`` left by a find-and-replace, and every
    ``<thead>`` it opens is closed -- so tables render one header row,
    not a stray empty one.**
    """
    import re

    from ccai.pychestrate.webservice import webinterface

    root = os.path.dirname(os.path.abspath(webinterface.__file__))
    malformed = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            if filename.endswith(".html") is False:
                continue
            path = os.path.join(dirpath, filename)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            opened = len(re.findall(r"<thead\b", text))
            closed = len(re.findall(r"</thead>", text))
            if 'scope="col"ead' in text or opened != closed:
                malformed.append(os.path.relpath(path, root))
    testbase.assert_equal(sorted(malformed), [])
    return
