"""
.. module:: test_p13q_consumer_ui_e2e_smoke_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: End-to-end smoke tests of the consumer UI under
               real WSGI -- the first test pass that exercises the
               full webworks app with HTTP-shaped requests rather
               than the per-handler unit-test pattern.

.. moduleauthor:: Automation Mojo LLC

The PRs F1..F5 + E1..E4 (PRs #144-152, ~25 kLOC) ship every
consumer-facing UI route on webworks but the rest of the test
suite exercises individual handlers in isolation -- patched
manager, fake request, fake jinja env. Nothing exercises the
real wiring: registrar order, jinja template loading from
disk, the ``install_url_for_global`` shim, the runtime
bootstrap pipeline, or the WSGI application object production
runs.

This module fills that gap with a tight Tier-1 smoke pass:

* Boot the runtime once (in-memory SQLite + auto-create-schema +
  test KEK + deterministic UI cookie secret).
* Build a webworks app, install templating, register the three
  consumer-UI registrars (config / resources / projects), call
  ``app.startup()``, wrap with the WSGI builder.
* Drive the resulting app via raw PEP-3333 WSGI environs from a
  minimal in-process driver.

The bootstrap + driver scaffolding lives in
:mod:`._e2e_harness`; this module imports the public names and
focuses on the assertions.

Coverage:

* App bootstrap + registrar cascade succeeds.
* Anonymous login page renders (200 + form fields + HTML
  Content-Type).
* Anonymous request to each blueprint dashboard redirects to
  the login page.
* Unknown path returns 404 cleanly (not 500).
* The url_for registry contains every documented endpoint
  (config / resources / projects, including the F5 calendar +
  watch endpoints).
* No orphan ``_FUTURE_ENDPOINT_PATTERNS`` placeholders remain.

Tier-2 coverage (login POST flow, authenticated dashboard
render, full CRUD round-trip) lives in
:mod:`.test_p13r_consumer_ui_e2e_authed_m1`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.pychestrate.webservice.webinterface.foundation import (
    url_for as url_for_module,
)
from automojo.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
)


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
    handle = ensure_app()
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
    handle = ensure_app()
    response = drive_request(
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
    handle = ensure_app()
    response = drive_request(
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
    handle = ensure_app()
    response = drive_request(
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
    handle = ensure_app()
    response = drive_request(
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
    handle = ensure_app()
    response = drive_request(
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
    handle = ensure_app()
    response = drive_request(
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
    ensure_app()
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
    ensure_app()
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
    ensure_app()
    from automojo.pychestrate.webservice.webinterface.blueprints.projects import (  # noqa: E402
        routes as projects_routes,
    )
    stubs = projects_routes._FUTURE_ENDPOINT_PATTERNS
    testbase.assert_equal(len(stubs), 0)
    return
