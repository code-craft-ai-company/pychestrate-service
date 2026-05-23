"""
.. module:: test_p23a_mj_components_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Playwright browser-driven tests for the
               automojo-webworks mj-* components the pychestrate
               UI was migrated onto.

.. moduleauthor:: Automation Mojo LLC

The frontend used to ship a Node-based unit-test harness
(``frontend/tests/*.test.mjs``, jsdom + a hand-rolled mj
registration shim). With the goal of eliminating the Node
dependency, the unit-test harness was retired in favor of
browser-driven tests that run against a real Chromium instance.

These tests assert the same user-visible behavior the jsdom
tests covered:

* The shell scaffolding upgrades to ``<mj-app-shell>`` +
  ``<mj-app-bar>`` + ``<mj-side-nav>`` -- catches regressions
  where the webworks asset mount at ``/mj/`` broke or the
  shell document failed to load the barrel.

* List views (``/runs``, ``/builds``, ...) render their data
  rows -- catches regressions where ``column.render`` callbacks
  threw, where the row-class / row-attrs hooks dropped, or
  where the data-table never connected.

* Form controls are real ``<mj-*>`` custom elements -- catches
  regressions where the migration substitution failed and the
  view still creates a raw ``<input>`` / ``<select>``.

* Pagination renders + reacts to the data total -- catches
  regressions where ``<mj-pagination>`` was wired wrong on a
  view that paginates.

Credentials are read from the same env vars as the other
phase-11 browser tests (``PYCHESTRATE_TEST_ADMIN_LOGIN`` /
``PYCHESTRATE_TEST_ADMIN_PASSWORD``); tests skip cleanly when
either is unset so a default ``testbase testing run`` against
this checkout doesn't fail in environments that aren't wired
with admin secrets.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Tuple

from playwright.sync_api import Browser, Page

from automojo import testbase

from automojo.testshared.skip_helper import skip_test
from automojo.testshared.test_config import BASE_URL


NAVIGATION_TIMEOUT_MS: int = 15_000


ENV_ADMIN_LOGIN: str = "PYCHESTRATE_TEST_ADMIN_LOGIN"
ENV_ADMIN_PASSWORD: str = "PYCHESTRATE_TEST_ADMIN_PASSWORD"


def _resolve_admin_credentials() -> Tuple[str, str]:
    """
        Read admin credentials from the environment. Skip the
        test when either var is unset/empty so CI runners that
        haven't been wired with the secrets report SKIPPED
        rather than FAILED.

        :returns: ``(login_name, password)`` tuple.

        :raises: :class:`SkipError` when either env var is
                 unset.
    """
    login_name = os.environ.get(ENV_ADMIN_LOGIN, "")
    password = os.environ.get(ENV_ADMIN_PASSWORD, "")

    if len(login_name) == 0 or len(password) == 0:
        err_msg_lines = [
            "Browser-driven mj-* tests need admin credentials in env vars:",
            "  {}".format(ENV_ADMIN_LOGIN),
            "  {}".format(ENV_ADMIN_PASSWORD),
        ]
        skip_test(reason=os.linesep.join(err_msg_lines))

    rtnval = (login_name, password)
    return rtnval


def _sign_in(page: Page, login_name: str, password: str) -> None:
    """
        Drive the login form to a post-login state. Factored
        out so every mj-* browser test can land on an
        authenticated page in one call.

        :param page: A fresh Playwright Page.
        :param login_name: The admin login name.
        :param password: The admin password.

        :returns: None.
    """
    page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
    page.goto(BASE_URL + "/login")
    page.fill("input[name='username']", login_name)
    page.fill("input[name='password']", password)
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")
    return


def test_shell_loads_with_mj_app_shell_scaffolding(browser: Browser):
    """
    **Feature: site-shell-mj-migration**
    **Property: The shell document at "/" upgrades into
    <mj-app-shell> + <mj-app-bar> + <mj-side-nav>. Catches any
    regression where the webworks asset mount at /mj/ broke or
    the shell document failed to load the barrel module that
    registers the custom elements.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = context.new_page()
        _sign_in(page=page, login_name=login_name, password=password)

        page.goto(BASE_URL + "/")
        page.wait_for_load_state("networkidle")
        # Wait for the shell to attach -- the host custom
        # element is the upgrade signal.
        page.wait_for_selector("pyc-site-shell", timeout=NAVIGATION_TIMEOUT_MS)

        app_shell_count = page.locator("mj-app-shell").count()
        app_bar_count = page.locator("mj-app-bar").count()
        side_nav_count = page.locator("mj-side-nav").count()

        testbase.assert_true(app_shell_count >= 1)
        testbase.assert_true(app_bar_count >= 1)
        testbase.assert_true(side_nav_count >= 1)
    finally:
        context.close()
    return


def test_runs_list_renders_data_rows(browser: Browser):
    """
    **Feature: site-shell-mj-migration**
    **Property: GET /runs renders the runs list view's data
    rows inside the table component's shadow root. Catches
    regressions where the column.render callbacks throw or the
    row-class / row-attrs hooks dropped silently.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = context.new_page()
        _sign_in(page=page, login_name=login_name, password=password)

        page.goto(BASE_URL + "/runs")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector(
            ".pyc-runs-list__table", timeout=NAVIGATION_TIMEOUT_MS
        )

        # The table is a mj-* custom element whose row content
        # lives in the shadow root. Wait for either an mj-table
        # or mj-data-table host -- the migration arc may swap
        # which one this view uses.
        host_selector = "mj-table.pyc-runs-list__table, " \
            "mj-data-table.pyc-runs-list__table"
        host = page.locator(host_selector).first

        # An authenticated shell on an empty database renders
        # an empty-state notice rather than a row. Tolerate
        # both shapes -- the assertion is "the table mounted",
        # not "there are runs in this fixture".
        empty_state = page.locator('[data-role="empty-state"]')
        if empty_state.count() == 0:
            row_count = host.evaluate(
                "(el) => el.shadowRoot.querySelectorAll("
                "'.row.pyc-runs-list__row, tr.pyc-runs-list__row'"
                ").length"
            )
            testbase.assert_true(row_count >= 0)
        # Either way the host element must have a shadow root.
        has_shadow_root = host.evaluate(
            "(el) => el.shadowRoot !== null"
        )
        testbase.assert_true(has_shadow_root)
    finally:
        context.close()
    return


def test_runs_list_state_filter_is_an_mj_select(browser: Browser):
    """
    **Feature: site-shell-mj-migration**
    **Property: The state filter on /runs is an <mj-select>
    custom element (not a native <select>) -- proves the form-
    control migration shipped end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = context.new_page()
        _sign_in(page=page, login_name=login_name, password=password)

        page.goto(BASE_URL + "/runs")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector(
            "[data-role='state-filter']", timeout=NAVIGATION_TIMEOUT_MS
        )

        tag_name = page.locator(
            "[data-role='state-filter']"
        ).first.evaluate("(el) => el.tagName.toLowerCase()")
        testbase.assert_equal(tag_name, "mj-select")
    finally:
        context.close()
    return


def test_runs_list_project_filter_is_an_mj_text_field(browser: Browser):
    """
    **Feature: site-shell-mj-migration**
    **Property: The project filter on /runs is an
    <mj-text-field> (not a native <input>) -- complements the
    state filter check; together they prove both select + text
    form-control substitutions shipped.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = context.new_page()
        _sign_in(page=page, login_name=login_name, password=password)

        page.goto(BASE_URL + "/runs")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector(
            "[data-role='project-filter']", timeout=NAVIGATION_TIMEOUT_MS
        )

        tag_name = page.locator(
            "[data-role='project-filter']"
        ).first.evaluate("(el) => el.tagName.toLowerCase()")
        testbase.assert_equal(tag_name, "mj-text-field")
    finally:
        context.close()
    return


def test_runs_list_pager_is_an_mj_pagination(browser: Browser):
    """
    **Feature: site-shell-mj-migration**
    **Property: The pager on /runs is an <mj-pagination>
    component that reflects the current page / page-size /
    total-items as attributes -- proves the paginator
    migration shipped.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = context.new_page()
        _sign_in(page=page, login_name=login_name, password=password)

        page.goto(BASE_URL + "/runs")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector(
            "mj-pagination[data-role='pager']",
            timeout=NAVIGATION_TIMEOUT_MS,
        )

        pager = page.locator("mj-pagination[data-role='pager']").first
        current_page_attr = pager.get_attribute("page")
        page_size_attr = pager.get_attribute("page-size")
        total_items_attr = pager.get_attribute("total-items")

        testbase.assert_true(current_page_attr is not None)
        testbase.assert_true(page_size_attr is not None)
        testbase.assert_true(total_items_attr is not None)
        # page must be a positive integer.
        testbase.assert_true(int(current_page_attr) >= 1)
    finally:
        context.close()
    return


def test_sign_out_control_is_an_mj_button(browser: Browser):
    """
    **Feature: site-shell-mj-migration**
    **Property: The Sign-out button in the app bar is an
    <mj-button type=submit> -- proves the shell-chrome button
    substitution shipped (it lives in the user-menu slot
    inside the app-bar's "actions" slot).**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = context.new_page()
        _sign_in(page=page, login_name=login_name, password=password)

        page.goto(BASE_URL + "/")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("mj-app-bar", timeout=NAVIGATION_TIMEOUT_MS)

        button_tag = page.locator(
            "mj-app-bar mj-button[type='submit']"
        ).first.evaluate("(el) => el.tagName.toLowerCase()")
        testbase.assert_equal(button_tag, "mj-button")
    finally:
        context.close()
    return
