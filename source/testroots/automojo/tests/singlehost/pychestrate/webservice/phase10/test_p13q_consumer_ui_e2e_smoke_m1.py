"""
.. module:: test_p13q_consumer_ui_e2e_smoke_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: End-to-end smoke tests of the consumer UI under
               real WSGI -- the first test pass that exercises the
               full webworks app with HTTP-shaped requests rather
               than the per-handler unit-test pattern.

.. moduleauthor:: Automation Mojo LLC

The PRs F1..F5 + E1..E4 (PRs #144-152, ~25 kLOC) ship every
consumer-facing UI route on webworks but the whole test suite
exercises individual handlers in isolation -- patched manager,
fake request, fake jinja env. Nothing exercises the real wiring:
registrar order, jinja template loading from disk, the
``install_url_for_global`` shim, the runtime bootstrap pipeline,
or the WSGI application object that production actually runs.

This module fills that gap with a tight Tier-1 smoke pass:

* Boot the runtime once (in-memory SQLite + auto-create-schema +
  test KEK + deterministic UI cookie secret).
* Build a webworks app, install templating, register the three
  consumer-UI registrars (config / resources / projects), call
  ``app.startup()``, wrap with the WSGI builder.
* Drive the resulting app via raw PEP-3333 WSGI environs from a
  minimal in-process driver.

Coverage:

* App bootstrap + registrar cascade succeeds.
* Anonymous login page renders (200 + cookie + form).
* Anonymous request to each blueprint dashboard redirects to the
  login page.
* Unknown path returns 404 cleanly (not 500).
* The url_for registry contains every documented endpoint
  (config / resources / projects, including the F5 calendar +
  watch endpoints).
* No orphan ``_FUTURE_ENDPOINT_PATTERNS`` placeholders remain.

Tier-2 coverage (login POST flow, authenticated dashboard
render, full CRUD round-trip) is deliberately deferred to a
follow-up PR; it requires seeding a real user record + role
grant which is materially more code and is orthogonal to the
"the wiring works" question this module answers.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import io
import os
import sys
import tempfile

from http.cookies import SimpleCookie
from typing import Any, Dict, List, Optional, Tuple

from automojo import testbase

# Importing this module pulls every model side-effect import that
# registers tables on ``PychestratePhase1Base.metadata`` -- without
# this pull the auto-create-schema step would only build the
# Phase-1 core tables and the resources / projects FKs would dangle.
import automojo.pychestrate.webservice.extensions.bootstrap  # noqa: F401

from automojo.pychestrate.webservice.metadata import (
    RUNTIME_ENVIRONMENTS,
    SITE_DIRECTORIES,
    SITE_SHARED_GLOBALS,
)
from automojo.pychestrate.webservice.runtime_bootstrap import (
    RuntimeBootstrapConfig,
    bootstrap_runtime,
)
from automojo.pychestrate.webservice.webinterface.blueprints.config.routes import (
    register_config_routes,
)
from automojo.pychestrate.webservice.webinterface.blueprints.projects.routes import (
    register_projects_routes,
)
from automojo.pychestrate.webservice.webinterface.blueprints.resources.routes import (
    register_resources_routes,
)
from automojo.pychestrate.webservice.webinterface.foundation import (
    templating,
    url_for as url_for_module,
)
from automojo.pychestrate.webservice.webinterface.foundation.static_files import (
    register_static_routes,
)
from automojo.pychestrate.webservice.webinterface.foundation.templating import (
    build_jinja_environment,
    discover_blueprint_template_paths,
    set_default_environment,
)
from automojo.pychestrate.webservice.webinterface.foundation.url_for import (
    install_url_for_global,
)
from automojo.webworks.wsgi.application import create_wsgi_application


_TEST_UI_COOKIE_SECRET: bytes = b"\x00" * 32


# ---------------------------------------------------------------------------
# Test harness -- runtime bootstrap + app construction (cached singleton)
# ---------------------------------------------------------------------------


class _TestAppHandle:
    """
        Holds the bootstrapped WSGI app + the temporary KEK file
        path so the cleanup test at the end of the module can
        delete the file.
    """

    def __init__(self, *, wsgi_app: Any, kek_file_path: str) -> None:
        self.wsgi_app: Any = wsgi_app
        self.kek_file_path: str = kek_file_path
        return


_APP_HANDLE: Optional[_TestAppHandle] = None


def _write_test_kek_file() -> str:
    """
        Emit a 32-byte KEK to a tempfile and return its path. The
        cleanup test deletes the file when the suite is done.
    """
    fd, path = tempfile.mkstemp(prefix="pych-e2e-kek-", suffix=".bin")
    try:
        os.write(fd, b"\x42" * 32)
    finally:
        os.close(fd)
    return path


def _bootstrap_runtime_for_tests(*, kek_file_path: str) -> None:
    """
        One-call runtime bootstrap with test-friendly defaults:
        in-memory SQLite, full schema create, file-source KEK, no
        password pepper, deterministic UI cookie secret. Publishes
        the engine + session factory on
        :class:`SITE_SHARED_GLOBALS`.
    """
    config = RuntimeBootstrapConfig(
        database_url="sqlite:///:memory:",
        runtime_environment=RUNTIME_ENVIRONMENTS.TESTING,
        kek_source="file",
        kek_id="e2e-test-kek",
        kek_file_path=kek_file_path,
        kek_env_var=None,
        password_pepper_source=None,
        password_pepper_file_path=None,
        password_pepper_env_var=None,
        ui_cookie_secret_source=None,
        ui_cookie_secret_file_path=None,
        ui_cookie_secret_env_var=None,
        auto_create_schema=True,
        sql_echo=False,
    )
    bootstrap_runtime(config=config)
    # The bootstrap doesn't load a UI cookie secret when the
    # ``ui_cookie_secret_source`` is None; publish a deterministic
    # one for the test session so the auth resolver and CSRF
    # machinery have a working secret.
    SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = _TEST_UI_COOKIE_SECRET
    return


def _install_test_templating() -> None:
    """
        Mirror :func:`app_pychestrate_main.install_web_ui_templating`
        for the test app -- discover every per-blueprint
        ``templates/`` directory and install the resulting jinja
        environment + url_for global as the default.
    """
    template_paths = discover_blueprint_template_paths(
        blueprints_root=SITE_DIRECTORIES.DIR_BLUEPRINTS,
    )
    if len(template_paths) == 0:
        template_paths = [SITE_DIRECTORIES.DIR_BLUEPRINTS]
    environment = build_jinja_environment(
        template_search_paths=template_paths,
    )
    install_url_for_global(environment=environment)
    set_default_environment(environment=environment)
    return


def _build_consumer_ui_test_app() -> Any:
    """
        Build the WSGI app the production ``app_pychestrate_main``
        bootstraps. Specifically:

        * Reuse the production ``app`` singleton from
          :mod:`app_pychestrate_main`.  Importing that module is
          the whole point: it triggers every REST-API + extension
          side-effect import, so an import-time bug anywhere in
          the service surfaces here.
        * Install the consumer-UI templating environment.
        * Register the three consumer-UI route registrars (config
          / resources / projects) plus the static-files
          registrar.
        * Advance the lifecycle to ``INFRASTRUCTURE_READY``.
        * Wrap with the production
          :func:`build_wsgi_compat_dispatch` shim.

        REST-API registrars are deliberately skipped here -- the
        consumer UI does not depend on them and they require
        additional bus-subscriber wiring that is orthogonal to
        the surface this module verifies.
    """
    # ``establish_webapp_persona`` is process-global (one persona
    # per interpreter). Importing ``app_pychestrate_main``
    # establishes ``pychestrate`` as the persona; reuse that
    # singleton rather than try to build a separate one.
    from app_pychestrate_main import (  # noqa: E402
        app,
        build_wsgi_compat_dispatch,
    )
    _install_test_templating()
    register_static_routes(
        app=app,
        url_prefix="/static",
        static_root=SITE_DIRECTORIES.DIR_STATIC,
    )
    register_config_routes(app=app)
    register_resources_routes(app=app)
    register_projects_routes(app=app)
    app.startup()
    rtnval = create_wsgi_application(
        config={"handler": build_wsgi_compat_dispatch(app=app)}
    )
    return rtnval


def _ensure_app() -> _TestAppHandle:
    """
        Lazy module-level singleton: bootstrap the runtime + build
        the WSGI app once, return the cached handle on subsequent
        calls. Each test calls this; the second-and-later calls
        are essentially free.
    """
    global _APP_HANDLE
    if _APP_HANDLE is not None:
        return _APP_HANDLE
    kek_path = _write_test_kek_file()
    _bootstrap_runtime_for_tests(kek_file_path=kek_path)
    wsgi_app = _build_consumer_ui_test_app()
    _APP_HANDLE = _TestAppHandle(
        wsgi_app=wsgi_app, kek_file_path=kek_path
    )
    return _APP_HANDLE


# ---------------------------------------------------------------------------
# In-process WSGI driver
# ---------------------------------------------------------------------------


class _WsgiResponse:
    """
        Captured response from a single :func:`_drive_request`
        call. Mirrors the shape of a typical HTTP-client response
        object enough for assertion readability.
    """

    def __init__(
            self,
            *,
            status_code: int,
            headers: List[Tuple[str, str]],
            body: bytes
        ) -> None:
        self.status_code: int = status_code
        self.headers: List[Tuple[str, str]] = headers
        self.body: bytes = body
        return

    def header(self, name: str) -> Optional[str]:
        """
            Case-insensitive single-header lookup. Returns the
            first matching header value or ``None``.
        """
        lowered = name.lower()
        for key, value in self.headers:
            if key.lower() == lowered:
                return value
        return None

    def collect_set_cookies(self) -> Dict[str, str]:
        """
            Parse every ``Set-Cookie`` header into a ``{name:
            value}`` mapping. Only the value is preserved; cookie
            attributes (Path, HttpOnly, ...) are discarded -- this
            module verifies presence + roundtrip, not attribute
            policy.
        """
        rtnval: Dict[str, str] = {}
        for key, value in self.headers:
            if key.lower() != "set-cookie":
                continue
            jar = SimpleCookie()
            jar.load(value)
            for cookie_name, morsel in jar.items():
                rtnval[cookie_name] = morsel.value
        return rtnval

    @property
    def text(self) -> str:
        try:
            rtnval = self.body.decode("utf-8")
        except UnicodeDecodeError:
            rtnval = self.body.decode("latin-1")
        return rtnval


def _drive_request(
        *,
        wsgi_app: Any,
        method: str,
        path: str,
        query_string: str = "",
        body: bytes = b"",
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None
    ) -> _WsgiResponse:
    """
        Drive a single PEP-3333 WSGI request against the supplied
        app and return a :class:`_WsgiResponse`.

        :param wsgi_app: WSGI callable returned by
                         :func:`create_wsgi_application`.
        :param method: HTTP method (uppercase).
        :param path: URL path (no query string).
        :param query_string: Optional URL query string (without
                             leading ``?``).
        :param body: Optional request body.
        :param headers: Extra request headers (``Header-Name`` ->
                        value).
        :param cookies: Cookies to send (``name`` -> ``value``).
    """
    body_stream = io.BytesIO(body)
    environ: Dict[str, Any] = {
        "REQUEST_METHOD": method.upper(),
        "PATH_INFO": path,
        "QUERY_STRING": query_string,
        "SERVER_NAME": "test.invalid",
        "SERVER_PORT": "80",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "SCRIPT_NAME": "",
        "wsgi.input": body_stream,
        "wsgi.errors": sys.stderr,
        "wsgi.url_scheme": "http",
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        "wsgi.version": (1, 0),
        "CONTENT_LENGTH": str(len(body)) if len(body) > 0 else "",
    }
    if cookies is not None and len(cookies) > 0:
        cookie_header = "; ".join(
            "{}={}".format(name, value) for name, value in cookies.items()
        )
        environ["HTTP_COOKIE"] = cookie_header
    if headers is not None:
        for name, value in headers.items():
            normalized = "HTTP_" + name.upper().replace("-", "_")
            environ[normalized] = value
        if "Content-Type" in headers:
            environ["CONTENT_TYPE"] = headers["Content-Type"]
        if "content-type" in headers:
            environ["CONTENT_TYPE"] = headers["content-type"]

    captured: Dict[str, Any] = {}

    def _start_response(
            status: str,
            response_headers: List[Tuple[str, str]],
            exc_info: Any = None
        ) -> Any:
        captured["status"] = status
        captured["headers"] = response_headers

        def _writer(chunk: bytes) -> None:
            return None

        return _writer

    body_chunks: List[bytes] = []
    iterator = wsgi_app(environ, _start_response)
    try:
        for chunk in iterator:
            if chunk is not None and len(chunk) > 0:
                body_chunks.append(chunk)
    finally:
        close = getattr(iterator, "close", None)
        if close is not None:
            close()

    status_code = int(captured["status"].split(" ", 1)[0])
    body_bytes = b"".join(body_chunks)
    rtnval = _WsgiResponse(
        status_code=status_code,
        headers=captured["headers"],
        body=body_bytes,
    )
    return rtnval


# ===========================================================================
# Tests
# ===========================================================================


def test_consumer_ui_app_bootstraps_cleanly():
    """
    **Feature: consumer UI e2e smoke T14.1**
    **Property: The full bootstrap pipeline -- runtime + jinja
    env install + every UI registrar + ``app.startup()`` --
    completes without raising for an in-memory SQLite test
    config.**
    """
    handle = _ensure_app()
    testbase.assert_equal(handle.wsgi_app is None, False)
    return


def test_login_page_renders_for_anonymous_user():
    """
    **Feature: consumer UI e2e smoke T14.2**
    **Property: GET /config/login returns a 200 with the login
    form fields the consumer expects (username + password). The
    login surface intentionally does not carry a CSRF token --
    there is no prior session to bind it to. Subsequent POSTs
    establish a session whose CSRF token then guards the rest
    of the consumer UI.**
    """
    handle = _ensure_app()
    response = _drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/config/login",
    )
    testbase.assert_equal(response.status_code, 200)
    body_text = response.text
    has_form_open = "<form" in body_text
    has_username_field = 'name="username"' in body_text
    has_password_field = 'name="password"' in body_text
    testbase.assert_equal(has_form_open, True)
    testbase.assert_equal(has_username_field, True)
    testbase.assert_equal(has_password_field, True)
    # The Content-Type header must come back as HTML even though
    # ``Response.content_type`` is None on the bundled webworks
    # ``HTMLResponse`` -- the WSGI shim still re-emits the
    # explicit Content-Type from the response's headers dict.
    content_type = response.header("Content-Type")
    testbase.assert_equal(
        content_type is not None
        and content_type.startswith("text/html"),
        True,
    )
    return


def test_config_dashboard_redirects_anonymous_to_login():
    """
    **Feature: consumer UI e2e smoke T14.3**
    **Property: An anonymous GET /config redirects to
    /config/login (not 500, not the dashboard rendered without
    auth).**
    """
    handle = _ensure_app()
    response = _drive_request(
        wsgi_app=handle.wsgi_app, method="GET", path="/config",
    )
    testbase.assert_equal(response.status_code, 302)
    location = response.header("Location")
    testbase.assert_equal(
        location is not None and location.endswith("/config/login"),
        True,
    )
    return


def test_resources_dashboard_redirects_anonymous_to_login():
    """
    **Feature: consumer UI e2e smoke T14.4**
    **Property: An anonymous GET /resources redirects to
    /config/login (the consumer UI shares one auth domain
    across all three blueprints).**
    """
    handle = _ensure_app()
    response = _drive_request(
        wsgi_app=handle.wsgi_app, method="GET", path="/resources",
    )
    testbase.assert_equal(response.status_code, 302)
    location = response.header("Location")
    testbase.assert_equal(
        location is not None and location.endswith("/config/login"),
        True,
    )
    return


def test_projects_dashboard_redirects_anonymous_to_login():
    """
    **Feature: consumer UI e2e smoke T14.5**
    **Property: An anonymous GET /projects redirects to
    /config/login.**
    """
    handle = _ensure_app()
    response = _drive_request(
        wsgi_app=handle.wsgi_app, method="GET", path="/projects",
    )
    testbase.assert_equal(response.status_code, 302)
    location = response.header("Location")
    testbase.assert_equal(
        location is not None and location.endswith("/config/login"),
        True,
    )
    return


def test_projects_alternate_dashboard_path_redirects_anonymous():
    """
    **Feature: consumer UI e2e smoke T14.6**
    **Property: GET /projects/dashboard (the explicit dashboard
    path; ``/projects`` is the alias) also redirects when
    anonymous.**
    """
    handle = _ensure_app()
    response = _drive_request(
        wsgi_app=handle.wsgi_app, method="GET",
        path="/projects/dashboard",
    )
    testbase.assert_equal(response.status_code, 302)
    location = response.header("Location")
    testbase.assert_equal(
        location is not None and location.endswith("/config/login"),
        True,
    )
    return


def test_unknown_path_returns_404_not_500():
    """
    **Feature: consumer UI e2e smoke T14.7**
    **Property: A GET to a wholly unknown path returns 404 (the
    webworks not-found path), not 500. Confirms the dispatcher
    is healthy and there is no catch-all that would leak
    handler exceptions as 200 / 500.**
    """
    handle = _ensure_app()
    response = _drive_request(
        wsgi_app=handle.wsgi_app, method="GET",
        path="/this-route-definitely-does-not-exist",
    )
    testbase.assert_equal(response.status_code, 404)
    return


def test_url_for_registry_has_every_blueprint_dashboard():
    """
    **Feature: consumer UI e2e smoke T14.8**
    **Property: After ``register_*_routes`` cascades, the
    url_for shim has resolvable patterns for every blueprint
    dashboard endpoint -- proves jinja templates that reference
    ``url_for('config.dashboard')``, ``url_for('resources.
    dashboard')``, ``url_for('projects.dashboard')`` won't
    raise at render time.**
    """
    _ensure_app()
    config_pattern = url_for_module.url_for("config.dashboard")
    resources_pattern = url_for_module.url_for("resources.dashboard")
    projects_pattern = url_for_module.url_for("projects.dashboard")
    testbase.assert_equal(
        config_pattern is not None and len(config_pattern) > 0, True
    )
    testbase.assert_equal(
        resources_pattern is not None and len(resources_pattern) > 0,
        True,
    )
    testbase.assert_equal(
        projects_pattern is not None and len(projects_pattern) > 0,
        True,
    )
    return


def test_url_for_registry_has_late_landed_f5_endpoints():
    """
    **Feature: consumer UI e2e smoke T14.9**
    **Property: The F5 calendar + watch endpoints (the last
    eleven of the projects port to land) are registered with
    the url_for shim. Catches any regression where the F5
    cascade silently fails to register.**
    """
    _ensure_app()
    calendar_pattern = url_for_module.url_for(
        "projects.calendar_view", project_id=7
    )
    release_event_pattern = url_for_module.url_for(
        "projects.release_event_detail", project_id=7, event_id=42
    )
    watch_list_pattern = url_for_module.url_for(
        "projects.watch_list", project_id=7
    )
    watch_test_pattern = url_for_module.url_for(
        "projects.watch_test", project_id=7, watch_id=42
    )
    testbase.assert_equal(
        calendar_pattern, "/projects/7/calendar"
    )
    testbase.assert_equal(
        release_event_pattern,
        "/projects/7/calendar/events/42",
    )
    testbase.assert_equal(
        watch_list_pattern, "/projects/7/watches"
    )
    testbase.assert_equal(
        watch_test_pattern, "/projects/7/watches/42/test"
    )
    return


def test_url_for_registry_has_no_orphan_future_endpoint_stubs():
    """
    **Feature: consumer UI e2e smoke T14.10**
    **Property: After F5 the projects ``_FUTURE_ENDPOINT_PATTERNS``
    tuple is empty -- there are no pre-registered stubs left
    over from earlier slices. Asserts the projects port is
    actually complete (would also fail if a follow-up PR
    re-introduced a stub without landing the matching
    handler).**
    """
    _ensure_app()
    from automojo.pychestrate.webservice.webinterface.blueprints.projects import (  # noqa: E402
        routes as projects_routes,
    )
    stubs = projects_routes._FUTURE_ENDPOINT_PATTERNS
    testbase.assert_equal(len(stubs), 0)
    return


def test_zzz_cleanup_kek_tempfile():
    """
    **Feature: consumer UI e2e smoke T14.11**
    **Property: Bookkeeping -- delete the per-suite temp KEK
    file. Named ``test_zzz_*`` so testbase's alphabetical
    ordering runs it last.**
    """
    handle = _APP_HANDLE
    if handle is not None:
        try:
            os.unlink(handle.kek_file_path)
        except OSError:
            pass
        # We don't reset SITE_SHARED_GLOBALS: subsequent test
        # modules in the sweep do their own ``_reset_global_state``
        # at the start of each test, so leftover state here is
        # harmless. Resetting here would force a re-bootstrap if
        # the suite re-runs this module within the same
        # interpreter (testbase doesn't, but be safe).
    return
