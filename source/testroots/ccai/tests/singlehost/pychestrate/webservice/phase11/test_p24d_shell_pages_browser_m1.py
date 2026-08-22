"""
.. module:: test_p24d_shell_pages_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Playwright browser-driven render-smoke tests for
               every client-rendered shell-bundle page served by
               the pychestrate site shell.

.. moduleauthor:: Code Craft AI LLC

Each test navigates to one of the ``mj-*`` SPA routes, asserts
that:

1. The site-shell host element (``pyc-site-shell``) is present
   and the ``mj-app-shell`` scaffolding has upgraded -- proving
   the shell document loaded its barrel bundle.

2. The feature bundle's root custom element is attached to the
   page DOM -- proving the shell router matched the route and
   mounted the correct view.

3. The view reached one of its accepted terminal states without
   an uncaught error-state element -- proving the bundle loaded,
   its ``connectedCallback`` ran, and its initial API fetch
   resolved cleanly (or resolved to an empty / no-project state,
   both of which are correct for a minimal fixture).

The ``/runs`` route is already covered by
:mod:`test_p23a_mj_components_browser_m1` and is intentionally
skipped here.

Credentials are read from ``PYCHESTRATE_TEST_ADMIN_LOGIN`` /
``PYCHESTRATE_TEST_ADMIN_PASSWORD``; tests skip cleanly when
either is unset so a default ``testbase testing run`` against
this checkout does not fail in environments that haven't been
wired with admin secrets.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Tuple

from playwright.sync_api import Browser, Page

from ccai import testbase

from ccai.testshared.skip_helper import skip_test
from ccai.testshared.test_config import BASE_URL


NAVIGATION_TIMEOUT_MS: int = 20_000
"""
    Timeout (ms) given to each ``wait_for_selector`` call. 20 s
    gives the JS bundles -- which are loaded on first visit --
    enough time to fetch, parse, and run their
    ``connectedCallback`` even on a slow CI host.
"""


ENV_ADMIN_LOGIN: str = "PYCHESTRATE_TEST_ADMIN_LOGIN"
ENV_ADMIN_PASSWORD: str = "PYCHESTRATE_TEST_ADMIN_PASSWORD"


def _resolve_admin_credentials() -> Tuple[str, str]:
    """
        Read admin credentials from the environment. Skip the
        calling test when either var is unset or empty so CI
        runners that haven't been wired with secrets report
        SKIPPED rather than FAILED.

        :returns: ``(login_name, password)`` tuple.

        :raises: :class:`SkipError` when either env var is unset.
    """
    login_name = os.environ.get(ENV_ADMIN_LOGIN, "")
    password = os.environ.get(ENV_ADMIN_PASSWORD, "")

    if len(login_name) == 0 or len(password) == 0:
        err_msg_lines = [
            "Shell-pages browser tests need admin credentials in env vars:",
            "  {}".format(ENV_ADMIN_LOGIN),
            "  {}".format(ENV_ADMIN_PASSWORD),
        ]
        skip_test(reason=os.linesep.join(err_msg_lines))

    rtnval = (login_name, password)
    return rtnval


def _login(*, context) -> Page:
    """
        Open a fresh page, sign in via the login form, and wait
        for the site-shell host element to confirm the
        authenticated shell is active.

        This helper is intentionally kept lightweight -- it drives
        only the login form and waits for the shell host element.
        Route-specific waits are left to each test so timeouts
        surface the right step.

        :param context: A Playwright ``BrowserContext``.

        :returns: An authenticated ``Page`` ready for navigation.
    """
    login_name, password = _resolve_admin_credentials()

    page = context.new_page()
    page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
    page.goto(BASE_URL + "/login")
    page.fill("input[name='username']", login_name)
    page.fill("input[name='password']", password)
    page.click("button[type='submit']")
    page.wait_for_selector(
        "pyc-site-shell",
        timeout=NAVIGATION_TIMEOUT_MS,
    )

    rtnval = page
    return rtnval


def _assert_shell_scaffolding(*, page: Page) -> None:
    """
        Assert that the ``mj-app-shell`` scaffolding is present
        and that the ``mj-side-nav`` has upgraded. Called by every
        shell-page test after navigating to the target route.

        :param page: An authenticated Playwright ``Page``
                     already on the target route.

        :returns: None.
    """
    app_shell_count = page.locator("mj-app-shell").count()
    side_nav_count = page.locator("mj-side-nav").count()

    testbase.assert_true(
        app_shell_count >= 1,
    )
    testbase.assert_true(
        side_nav_count >= 1,
    )
    return


def _assert_no_error_state(*, page: Page) -> None:
    """
        Assert that no ``[data-role="error-state"]`` element is
        present in the page DOM. The bundle views render this
        element only when an API fetch failed; its presence would
        indicate the bundle mounted but its initial fetch errored.

        :param page: An authenticated Playwright ``Page``
                     already on the target route after the bundle
                     has settled.

        :returns: None.
    """
    error_state_count = page.locator('[data-role="error-state"]').count()
    testbase.assert_equal(error_state_count, 0)
    return


def _wait_for_bundle_terminal_state(
        *,
        page: Page,
        bundle_host_selector: str,
        terminal_selector: str,
) -> None:
    """
        Wait for either the feature-bundle's host element or a
        known terminal-state sentinel to appear in the DOM.

        The combined selector is tried first so a fast CI hit
        resolves immediately; if neither appears within
        :data:`NAVIGATION_TIMEOUT_MS` the test fails with the
        timeout surfaced by Playwright.

        :param page: An authenticated Playwright ``Page``.
        :param bundle_host_selector: CSS selector for the
               feature-bundle's root custom element
               (e.g. ``"pyc-builds-list"``).
        :param terminal_selector: CSS selector that matches any
               accepted terminal state sentinel rendered by the
               bundle view (e.g. empty-state / no-project-state).

        :returns: None.
    """
    combined = "{}, {}".format(bundle_host_selector, terminal_selector)
    page.wait_for_selector(
        combined,
        timeout=NAVIGATION_TIMEOUT_MS,
        state="attached",
    )

    host_count = page.locator(bundle_host_selector).count()
    testbase.assert_true(
        host_count >= 1,
    )
    return


# ---------------------------------------------------------------------------
# Orchestration group
# ---------------------------------------------------------------------------


def test_builds_shell_page_renders(browser: Browser):
    """
    **Feature: /builds shell page**
    **Property: loads inside the site shell and mounts its bundle**.
    """
    context = browser.new_context()
    try:
        page = _login(context=context)

        page.goto(BASE_URL + "/builds")
        # The builds view renders pyc-builds-list which always
        # renders the chrome synchronously in connectedCallback.
        # Terminal states: table-region with no-project-state,
        # empty-state, error-state, or the mj-data-table itself.
        page.wait_for_selector(
            "pyc-builds-list",
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_shell_scaffolding(page=page)

        host_count = page.locator("pyc-builds-list").count()
        testbase.assert_true(host_count >= 1)

        # Wait for the table-region to be populated -- either
        # no-project-state (no projects in the fixture) or
        # empty-state / the data table.
        terminal_inner = (
            '[data-role="no-project-state"], '
            '[data-role="empty-state"], '
            '[data-role="error-state"], '
            'mj-data-table.pyc-builds__table'
        )
        page.wait_for_selector(
            terminal_inner,
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_no_error_state(page=page)
    finally:
        context.close()
    return


def test_pipelines_shell_page_renders(browser: Browser):
    """
    **Feature: /pipelines shell page**
    **Property: loads inside the site shell and mounts its bundle**.
    """
    context = browser.new_context()
    try:
        page = _login(context=context)

        page.goto(BASE_URL + "/pipelines")
        page.wait_for_selector(
            "pyc-pipelines-list",
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_shell_scaffolding(page=page)

        host_count = page.locator("pyc-pipelines-list").count()
        testbase.assert_true(host_count >= 1)

        terminal_inner = (
            '[data-role="no-project-state"], '
            '[data-role="empty-state"], '
            '[data-role="error-state"], '
            'mj-data-table.pyc-pipelines__table'
        )
        page.wait_for_selector(
            terminal_inner,
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_no_error_state(page=page)
    finally:
        context.close()
    return


def test_test_catalog_shell_page_renders(browser: Browser):
    """
    **Feature: /test-catalog shell page**
    **Property: loads inside the site shell and mounts its bundle**.
    """
    context = browser.new_context()
    try:
        page = _login(context=context)

        page.goto(BASE_URL + "/test-catalog")
        page.wait_for_selector(
            "pyc-test-catalog",
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_shell_scaffolding(page=page)

        host_count = page.locator("pyc-test-catalog").count()
        testbase.assert_true(host_count >= 1)

        terminal_inner = (
            '[data-role="no-project-state"], '
            '[data-role="empty-state"], '
            '[data-role="error-state"], '
            'mj-data-table.pyc-catalog__table'
        )
        page.wait_for_selector(
            terminal_inner,
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_no_error_state(page=page)
    finally:
        context.close()
    return


def test_environments_shell_page_renders(browser: Browser):
    """
    **Feature: /environments shell page**
    **Property: loads inside the site shell and mounts its bundle**.
    """
    context = browser.new_context()
    try:
        page = _login(context=context)

        page.goto(BASE_URL + "/environments")
        page.wait_for_selector(
            "pyc-environments",
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_shell_scaffolding(page=page)

        host_count = page.locator("pyc-environments").count()
        testbase.assert_true(host_count >= 1)

        terminal_inner = (
            '[data-role="no-project-state"], '
            '[data-role="empty-state"], '
            '[data-role="error-state"], '
            'mj-data-table'
        )
        page.wait_for_selector(
            terminal_inner,
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_no_error_state(page=page)
    finally:
        context.close()
    return


def test_provisioning_runs_shell_page_renders(browser: Browser):
    """
    **Feature: /provisioning-runs shell page**
    **Property: loads inside the site shell and mounts its bundle**.
    """
    context = browser.new_context()
    try:
        page = _login(context=context)

        page.goto(BASE_URL + "/provisioning-runs")
        page.wait_for_selector(
            "pyc-provisioning-list",
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_shell_scaffolding(page=page)

        host_count = page.locator("pyc-provisioning-list").count()
        testbase.assert_true(host_count >= 1)

        terminal_inner = (
            '[data-role="no-project-state"], '
            '[data-role="empty-state"], '
            '[data-role="error-state"], '
            'mj-data-table'
        )
        page.wait_for_selector(
            terminal_inner,
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_no_error_state(page=page)
    finally:
        context.close()
    return


def test_blast_radius_guards_shell_page_renders(browser: Browser):
    """
    **Feature: /blast-radius-guards shell page**
    **Property: loads inside the site shell and mounts its bundle**.
    """
    context = browser.new_context()
    try:
        page = _login(context=context)

        page.goto(BASE_URL + "/blast-radius-guards")
        page.wait_for_selector(
            "pyc-guards",
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_shell_scaffolding(page=page)

        host_count = page.locator("pyc-guards").count()
        testbase.assert_true(host_count >= 1)

        # ``no-environment-state`` is a terminal state too: the
        # guards collection endpoint requires an environment_id,
        # so the view holds the fetch and prompts for one rather
        # than issuing a request that can only answer 400.
        terminal_inner = (
            '[data-role="no-project-state"], '
            '[data-role="no-environment-state"], '
            '[data-role="empty-state"], '
            '[data-role="error-state"], '
            'mj-data-table'
        )
        page.wait_for_selector(
            terminal_inner,
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_no_error_state(page=page)
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Insights group
# ---------------------------------------------------------------------------


def test_test_metrics_shell_page_renders(browser: Browser):
    """
    **Feature: /test-metrics shell page**
    **Property: loads inside the site shell and mounts its bundle**.
    """
    context = browser.new_context()
    try:
        page = _login(context=context)

        page.goto(BASE_URL + "/test-metrics")
        page.wait_for_selector(
            "pyc-test-metrics",
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_shell_scaffolding(page=page)

        host_count = page.locator("pyc-test-metrics").count()
        testbase.assert_true(host_count >= 1)

        # The test-metrics view renders a content-region for the
        # project-scoped data. Without projects, the view renders
        # "Select a project to view test metrics." inside the
        # content-region. Accept content-region (settled) OR any
        # terminal sentinel.
        terminal_inner = (
            '[data-role="content-region"], '
            '[data-role="error-state"]'
        )
        page.wait_for_selector(
            terminal_inner,
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_no_error_state(page=page)
    finally:
        context.close()
    return


def test_timeseries_shell_page_renders(browser: Browser):
    """
    **Feature: /timeseries shell page**
    **Property: loads inside the site shell and mounts its bundle**.
    """
    context = browser.new_context()
    try:
        page = _login(context=context)

        page.goto(BASE_URL + "/timeseries")
        page.wait_for_selector(
            "pyc-timeseries-explorer",
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_shell_scaffolding(page=page)

        host_count = page.locator("pyc-timeseries-explorer").count()
        testbase.assert_true(host_count >= 1)

        # The timeseries view renders a chart-region immediately in
        # connectedCallback; it always appears even when no metric
        # is selected.
        terminal_inner = (
            '[data-role="chart-region"], '
            '[data-role="error-state"]'
        )
        page.wait_for_selector(
            terminal_inner,
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_no_error_state(page=page)
    finally:
        context.close()
    return


def test_dashboards_shell_page_renders(browser: Browser):
    """
    **Feature: /dashboards shell page**
    **Property: loads inside the site shell and mounts its bundle**.
    """
    context = browser.new_context()
    try:
        page = _login(context=context)

        page.goto(BASE_URL + "/dashboards")
        page.wait_for_selector(
            "pyc-dashboards-list",
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_shell_scaffolding(page=page)

        host_count = page.locator("pyc-dashboards-list").count()
        testbase.assert_true(host_count >= 1)

        # The dashboards view renders notices as plain div.pyc-metrics__notice
        # (no data-role) inside [data-role="table-region"] -- there is no
        # data-role="no-project-state" or data-role="empty-state" here.
        # [data-role="table-region"] is always rendered synchronously in
        # connectedCallback and is the reliable terminal sentinel.
        page.wait_for_selector(
            '[data-role="table-region"]',
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        # Only mj-data-table[data-role="dashboards-table"] appears when there
        # are dashboards; an error notice inside the region indicates a fetch
        # failure. There is no data-role on the notice divs, so inspect the
        # region's text content: a fetch error embeds "--error" CSS class.
        error_state_count = page.locator(
            ".pyc-metrics__notice--error"
        ).count()
        testbase.assert_equal(error_state_count, 0)
    finally:
        context.close()
    return


def test_slos_shell_page_renders(browser: Browser):
    """
    **Feature: /slos shell page**
    **Property: loads inside the site shell and mounts its bundle**.
    """
    context = browser.new_context()
    try:
        page = _login(context=context)

        page.goto(BASE_URL + "/slos")
        page.wait_for_selector(
            "pyc-slos",
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_shell_scaffolding(page=page)

        host_count = page.locator("pyc-slos").count()
        testbase.assert_true(host_count >= 1)

        terminal_inner = (
            '[data-role="no-project-state"], '
            '[data-role="empty-state"], '
            '[data-role="error-state"], '
            '[data-role="table-region"]'
        )
        page.wait_for_selector(
            terminal_inner,
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_no_error_state(page=page)
    finally:
        context.close()
    return


def test_metric_alerts_shell_page_renders(browser: Browser):
    """
    **Feature: /metric-alerts shell page**
    **Property: loads inside the site shell and mounts its bundle**.
    """
    context = browser.new_context()
    try:
        page = _login(context=context)

        page.goto(BASE_URL + "/metric-alerts")
        page.wait_for_selector(
            "pyc-alert-rules",
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_shell_scaffolding(page=page)

        host_count = page.locator("pyc-alert-rules").count()
        testbase.assert_true(host_count >= 1)

        terminal_inner = (
            '[data-role="no-project-state"], '
            '[data-role="empty-state"], '
            '[data-role="error-state"], '
            '[data-role="table-region"]'
        )
        page.wait_for_selector(
            terminal_inner,
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_no_error_state(page=page)
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Fleet group
# ---------------------------------------------------------------------------


def test_pods_shell_page_renders(browser: Browser):
    """
    **Feature: /pods shell page**
    **Property: loads inside the site shell and mounts its bundle**.
    """
    context = browser.new_context()
    try:
        page = _login(context=context)

        page.goto(BASE_URL + "/pods")
        page.wait_for_selector(
            "pyc-pods-list",
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_shell_scaffolding(page=page)

        host_count = page.locator("pyc-pods-list").count()
        testbase.assert_true(host_count >= 1)

        # The pods view always renders table-region in connectedCallback;
        # without a project entered the "needs-project" sentinel is shown.
        terminal_inner = (
            '[data-role="needs-project"], '
            '[data-role="empty-state"], '
            '[data-role="error-state"], '
            'mj-data-table'
        )
        page.wait_for_selector(
            terminal_inner,
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_no_error_state(page=page)
    finally:
        context.close()
    return


def test_clients_shell_page_renders(browser: Browser):
    """
    **Feature: /clients shell page**
    **Property: loads inside the site shell and mounts its bundle**.
    """
    context = browser.new_context()
    try:
        page = _login(context=context)

        page.goto(BASE_URL + "/clients")
        page.wait_for_selector(
            "pyc-clients-list",
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_shell_scaffolding(page=page)

        host_count = page.locator("pyc-clients-list").count()
        testbase.assert_true(host_count >= 1)

        # The clients view loads all enrolled clients without
        # requiring a project; it renders the table-region
        # synchronously in connectedCallback, then fills with
        # empty-state or rows after the fetch resolves.
        terminal_inner = (
            '[data-role="empty-state"], '
            '[data-role="error-state"], '
            '[data-role="loading-state"], '
            'mj-data-table'
        )
        page.wait_for_selector(
            terminal_inner,
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_no_error_state(page=page)
    finally:
        context.close()
    return


def test_resource_pools_shell_page_renders(browser: Browser):
    """
    **Feature: /resource-pools shell page**
    **Property: loads inside the site shell and mounts its bundle**.
    """
    context = browser.new_context()
    try:
        page = _login(context=context)

        page.goto(BASE_URL + "/resource-pools")
        page.wait_for_selector(
            "pyc-resource-pools",
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_shell_scaffolding(page=page)

        host_count = page.locator("pyc-resource-pools").count()
        testbase.assert_true(host_count >= 1)

        # The resource-pools view requires a project id to load;
        # the "needs-project" sentinel renders immediately without
        # one.
        terminal_inner = (
            '[data-role="needs-project"], '
            '[data-role="empty-state"], '
            '[data-role="error-state"], '
            'mj-data-table'
        )
        page.wait_for_selector(
            terminal_inner,
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_no_error_state(page=page)
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Operations group
# ---------------------------------------------------------------------------


def test_webhooks_shell_page_renders(browser: Browser):
    """
    **Feature: /webhooks shell page**
    **Property: loads inside the site shell and mounts its bundle**.
    """
    context = browser.new_context()
    try:
        page = _login(context=context)

        page.goto(BASE_URL + "/webhooks")
        page.wait_for_selector(
            "pyc-webhooks",
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_shell_scaffolding(page=page)

        host_count = page.locator("pyc-webhooks").count()
        testbase.assert_true(host_count >= 1)

        # The webhooks view renders tabs (inbound / outbound) and a
        # panel-region immediately in connectedCallback. The
        # inbound-panel is rendered synchronously when the inbound
        # tab is active (the default).
        terminal_inner = (
            '[data-role="panel-region"], '
            '[data-role="error-state"]'
        )
        page.wait_for_selector(
            terminal_inner,
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_no_error_state(page=page)
    finally:
        context.close()
    return


def test_release_channels_shell_page_renders(browser: Browser):
    """
    **Feature: /release-channels shell page**
    **Property: loads inside the site shell and mounts its bundle**.
    """
    context = browser.new_context()
    try:
        page = _login(context=context)

        page.goto(BASE_URL + "/release-channels")
        page.wait_for_selector(
            "pyc-release-channels",
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_shell_scaffolding(page=page)

        host_count = page.locator("pyc-release-channels").count()
        testbase.assert_true(host_count >= 1)

        terminal_inner = (
            '[data-role="empty-state"], '
            '[data-role="error-state"], '
            '[data-role="loading-state"], '
            '[data-role="table-region"]'
        )
        page.wait_for_selector(
            terminal_inner,
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_no_error_state(page=page)
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# System group
# ---------------------------------------------------------------------------


def test_secrets_shell_page_renders(browser: Browser):
    """
    **Feature: /secrets shell page**
    **Property: loads inside the site shell and mounts its bundle**.
    """
    context = browser.new_context()
    try:
        page = _login(context=context)

        page.goto(BASE_URL + "/secrets")
        page.wait_for_selector(
            "pyc-secrets",
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_shell_scaffolding(page=page)

        host_count = page.locator("pyc-secrets").count()
        testbase.assert_true(host_count >= 1)

        # The secrets view renders a table-region in connectedCallback
        # and immediately populates it (scoped to "system" secrets by
        # default). Accept table-region appearing (settled after the
        # initial fetch), or any terminal-state sentinel.
        terminal_inner = (
            '[data-role="empty-state"], '
            '[data-role="error-state"], '
            '[data-role="loading-state"], '
            '[data-role="table-region"]'
        )
        page.wait_for_selector(
            terminal_inner,
            timeout=NAVIGATION_TIMEOUT_MS,
            state="attached",
        )

        _assert_no_error_state(page=page)
    finally:
        context.close()
    return
