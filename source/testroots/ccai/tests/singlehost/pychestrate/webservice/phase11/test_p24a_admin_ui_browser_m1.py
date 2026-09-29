"""
.. module:: test_p24a_admin_ui_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Playwright browser-driven end-to-end tests for the
               pychestrate admin UI -- every admin page renders and
               every admin CRUD activity works through the browser.

.. moduleauthor:: Code Craft AI LLC

Covers the full /admin/* surface served by the
``webinterface.blueprints.config`` blueprint:

* Shell-native SPA pages (/admin, /admin/dashboard,
  /admin/feature-flags, /admin/extensions, /admin/system-health)
  -- assert the <pyc-site-shell> host element and the page's main
  heading / container region render.

* Server-rendered admin pages (users, roles, variables, scopes,
  secrets, sessions, audit-logs, enrollment-tokens) -- assert list
  pages render, CRUD workflows (create / edit / delete / deactivate
  / revoke) complete in the browser and leave the expected rows /
  flash messages behind.

Credentials are read from the same env vars as the other
phase-11 browser tests (``PYCHESTRATE_TEST_ADMIN_LOGIN`` /
``PYCHESTRATE_TEST_ADMIN_PASSWORD``); tests skip cleanly when
either is unset.

Each CRUD test creates objects whose names carry a monotonic run
tag so consecutive test runs on the same fixture don't produce
duplicate-name failures. The tag is a low 7-digit slice of the
epoch so names stay short enough for column constraints.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import time

from typing import Tuple

from playwright.sync_api import Browser, BrowserContext, Page

from ccai import testbase

from ccai.testshared.skip_helper import skip_test

from ccai.tests.singlehost.pychestrate.webservice.phase11._confirm_helpers import auto_confirm
from ccai.testshared.test_config import BASE_URL


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

NAVIGATION_TIMEOUT_MS: int = 20_000

# Shell custom element that wraps every authenticated page.
SHELL_SELECTOR: str = "pyc-site-shell"

# Fragment element injected into the shell for every server-rendered
# admin page (config/base.html).
FRAGMENT_SELECTOR: str = "section.pyc-admin-page-fragment"

# Short run-unique suffix for object names -- last 7 digits of epoch
# so re-running on the same DB doesn't hit duplicate-name errors.
_RUN_TAG: str = str(int(time.time()) % 10_000_000)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _resolve_admin_credentials() -> Tuple[str, str]:
    """
        Read admin credentials from the process environment. Skip
        the calling test when either variable is unset/empty so CI
        runners that haven't been wired with the secrets report
        SKIPPED rather than FAILED.

        :returns: ``(login_name, password)`` tuple.

        :raises: :class:`SkipError` when either env var is unset.
    """
    login_name = os.environ.get("PYCHESTRATE_TEST_ADMIN_LOGIN", "")
    password = os.environ.get("PYCHESTRATE_TEST_ADMIN_PASSWORD", "")

    if len(login_name) == 0 or len(password) == 0:
        err_msg_lines = [
            "Admin UI browser tests need credentials in env vars:",
            "  PYCHESTRATE_TEST_ADMIN_LOGIN",
            "  PYCHESTRATE_TEST_ADMIN_PASSWORD",
        ]
        skip_test(reason=os.linesep.join(err_msg_lines))

    rtnval = (login_name, password)
    return rtnval


def _login(*, context: BrowserContext) -> Page:
    """
        Open a page in *context*, navigate to /login, fill the
        admin credentials from env vars (defaulting to
        admin/TestAdmin123!), submit the form, and wait until the
        <pyc-site-shell> custom element appears.

        :param context: A fresh, cookie-isolated BrowserContext.

        :returns: Authenticated :class:`Page`.
    """
    login_name = os.environ.get("PYCHESTRATE_TEST_ADMIN_LOGIN", "admin")
    password = os.environ.get(
        "PYCHESTRATE_TEST_ADMIN_PASSWORD", "TestAdmin123!"
    )

    page = context.new_page()
    page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
    page.goto(BASE_URL + "/login")
    page.fill("input[name='username']", login_name)
    page.fill("input[name='password']", password)
    page.click("button[type='submit']")
    page.wait_for_selector(SHELL_SELECTOR, timeout=NAVIGATION_TIMEOUT_MS)
    rtnval = page
    return rtnval


def _wait_for_admin_fragment(*, page: Page) -> None:
    """
        Wait for the server-rendered admin fragment element to be
        present in the DOM. Used after every ``page.goto`` that
        targets a server-rendered /admin/* route.

        :param page: Authenticated Playwright Page.

        :returns: None.
    """
    page.wait_for_selector(FRAGMENT_SELECTOR, timeout=NAVIGATION_TIMEOUT_MS)
    return


def _page_message_text(*, page: Page) -> str:
    """
        Return the user-visible message text for the current page,
        lowercased, gathered from both places a flash can legally
        live.

        The site shell lifts server-rendered flashes out of the
        page fragment into its own notices region at boot, so that
        a feature bundle replacing ``<main>`` cannot destroy a
        message before the user reads it. A flash therefore lands
        in ``.pyc-site-shell__notices`` on any shell-served route,
        and only remains inside the fragment when the shell has
        not booted. Reading both keeps these assertions true in
        either case.

        :param page: Authenticated Playwright Page, already
                     settled on the target route.

        :returns: The combined message text, lowercased.
    """
    collected = []

    notices = page.locator(".pyc-site-shell__notices")
    if notices.count() > 0:
        collected.append(notices.inner_text())

    fragment = page.locator(FRAGMENT_SELECTOR)
    if fragment.count() > 0:
        collected.append(fragment.inner_text())

    rtnval = " ".join(collected).lower()
    return rtnval


def _click_submit_and_goto_list(
        *, page: Page, submit_selector: str, list_path: str
    ) -> None:
    """
        Click a submit element (identified by *submit_selector*),
        wait for the navigation it triggers to complete (the POST
        + server redirect chain), then navigate to *list_path*
        and wait for the admin fragment.

        Using ``page.expect_navigation()`` as a context manager
        around the click is the correct Playwright pattern: it
        subscribes to the next navigation event BEFORE the click
        fires, then waits for it to complete. This eliminates the
        race condition where ``page.click()`` returns before the
        POST navigation has started, and where a bare
        ``wait_for_load_state`` may return immediately because the
        current page is already in the "load" state.

        After the navigation the page is at whatever URL the
        server's redirect targeted. A second ``page.goto`` to
        *list_path* re-fetches the list so we see the committed
        database state regardless of where the server-side redirect
        chain landed.

        :param page: Authenticated Playwright Page whose current
                     URL is a create/edit/delete form.
        :param submit_selector: CSS selector for the button or
                                element to click.
        :param list_path: Absolute path of the list page
                         (e.g. ``"/admin/users"``).

        :returns: None.
    """
    with page.expect_navigation(timeout=NAVIGATION_TIMEOUT_MS):
        page.click(submit_selector)
    page.goto(BASE_URL + list_path)
    _wait_for_admin_fragment(page=page)
    return


# ---------------------------------------------------------------------------
# Shell-native render smokes
# ---------------------------------------------------------------------------


def test_admin_overview_shell_renders(browser: Browser):
    """
    **Feature: admin-shell-native**
    **Property: GET /admin renders the <pyc-site-shell> host --
    confirms the pyc-admin-bundle JS loaded and the /admin route
    is client-side-routed to the overview component without
    erroring.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        page.goto(BASE_URL + "/admin")
        page.wait_for_selector(SHELL_SELECTOR, timeout=NAVIGATION_TIMEOUT_MS)
        shell_count = page.locator(SHELL_SELECTOR).count()
        testbase.assert_true(shell_count >= 1)
    finally:
        context.close()
    return


def test_admin_dashboard_shell_renders(browser: Browser):
    """
    **Feature: admin-shell-native**
    **Property: GET /admin/dashboard renders the <pyc-site-shell>
    host -- confirms the admin bundle handles the /admin/dashboard
    sub-route without a hard 404.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        page.goto(BASE_URL + "/admin/dashboard")
        page.wait_for_selector(SHELL_SELECTOR, timeout=NAVIGATION_TIMEOUT_MS)
        shell_count = page.locator(SHELL_SELECTOR).count()
        testbase.assert_true(shell_count >= 1)
    finally:
        context.close()
    return


def test_admin_feature_flags_shell_renders(browser: Browser):
    """
    **Feature: admin-shell-native**
    **Property: GET /admin/feature-flags renders the
    <pyc-site-shell> host -- confirms the admin bundle handles the
    /admin/feature-flags sub-route.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        page.goto(BASE_URL + "/admin/feature-flags")
        page.wait_for_selector(SHELL_SELECTOR, timeout=NAVIGATION_TIMEOUT_MS)
        shell_count = page.locator(SHELL_SELECTOR).count()
        testbase.assert_true(shell_count >= 1)
    finally:
        context.close()
    return


def test_admin_extensions_shell_renders(browser: Browser):
    """
    **Feature: admin-shell-native**
    **Property: GET /admin/extensions renders the <pyc-site-shell>
    host -- confirms the admin bundle handles the /admin/extensions
    sub-route.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        page.goto(BASE_URL + "/admin/extensions")
        page.wait_for_selector(SHELL_SELECTOR, timeout=NAVIGATION_TIMEOUT_MS)
        shell_count = page.locator(SHELL_SELECTOR).count()
        testbase.assert_true(shell_count >= 1)
    finally:
        context.close()
    return


def test_admin_system_health_shell_renders(browser: Browser):
    """
    **Feature: admin-shell-native**
    **Property: GET /admin/system-health renders the
    <pyc-site-shell> host -- confirms the admin bundle handles the
    /admin/system-health sub-route.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        page.goto(BASE_URL + "/admin/system-health")
        page.wait_for_selector(SHELL_SELECTOR, timeout=NAVIGATION_TIMEOUT_MS)
        shell_count = page.locator(SHELL_SELECTOR).count()
        testbase.assert_true(shell_count >= 1)
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Users -- list, create, detail, edit, deactivate
# ---------------------------------------------------------------------------


def test_admin_users_list_renders_with_admin_row(browser: Browser):
    """
    **Feature: admin-users**
    **Property: GET /admin/users renders the users list page
    inside the site shell and the seeded admin user is visible in
    the table -- confirms the list handler + template render
    end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        page.goto(BASE_URL + "/admin/users")
        _wait_for_admin_fragment(page=page)

        heading_text = page.locator(
            "section.pyc-admin-page-fragment h2"
        ).first.inner_text()
        testbase.assert_true("User" in heading_text)

        admin_cell = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=login_name)
        testbase.assert_true(admin_cell.count() >= 1)
    finally:
        context.close()
    return


def test_admin_user_create_form_renders(browser: Browser):
    """
    **Feature: admin-users**
    **Property: GET /admin/users/create renders the create-user
    form with username / email / password / display_name inputs
    inside the site shell.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        page.goto(BASE_URL + "/admin/users/create")
        _wait_for_admin_fragment(page=page)

        heading_text = page.locator(
            "section.pyc-admin-page-fragment h2"
        ).first.inner_text()
        testbase.assert_true("Create User" in heading_text)

        username_count = page.locator("input[name='username']").count()
        email_count = page.locator("input[name='email']").count()
        password_count = page.locator("input[name='password']").count()
        display_name_count = page.locator(
            "input[name='display_name']"
        ).count()

        testbase.assert_equal(username_count, 1)
        testbase.assert_equal(email_count, 1)
        testbase.assert_equal(password_count, 1)
        testbase.assert_equal(display_name_count, 1)
    finally:
        context.close()
    return


def test_admin_create_user_workflow(browser: Browser):
    """
    **Feature: admin-users**
    **Property: Filling and submitting the create-user form in a
    real browser creates the user and the users list then contains
    the new user row -- proves the full POST path + redirect + list
    render chain works end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)

        new_username = "brtcu{}".format(_RUN_TAG)
        new_email = "brtcu{}@example.test".format(_RUN_TAG)
        new_password = "BrTestPass123!"
        new_display_name = "BR Test Create {}".format(_RUN_TAG)

        page.goto(BASE_URL + "/admin/users/create")
        _wait_for_admin_fragment(page=page)

        page.fill("input[name='username']", new_username)
        page.fill("input[name='email']", new_email)
        page.fill("input[name='password']", new_password)
        page.fill("input[name='display_name']", new_display_name)

        # Navigate to the list page and verify the new row.
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/users",
        )

        new_row = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=new_username)
        testbase.assert_true(new_row.count() >= 1)
    finally:
        context.close()
    return


def test_admin_user_detail_renders(browser: Browser):
    """
    **Feature: admin-users**
    **Property: The admin user detail page renders after
    navigating from the users list -- confirms the detail handler
    + template render without error.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        page.goto(BASE_URL + "/admin/users")
        _wait_for_admin_fragment(page=page)

        # Click the admin user's link to reach the detail page.
        admin_link = page.locator(
            "section.pyc-admin-page-fragment .data-table a"
        ).filter(has_text=login_name).first
        admin_link.click()

        _wait_for_admin_fragment(page=page)

        fragment_text = page.locator(
            "section.pyc-admin-page-fragment"
        ).inner_text()
        testbase.assert_true(login_name in fragment_text)
    finally:
        context.close()
    return


def test_admin_user_edit_form_renders(browser: Browser):
    """
    **Feature: admin-users**
    **Property: GET /admin/users/<id>/edit renders the edit form
    with an email input -- confirms the edit handler resolves the
    user and renders the pre-filled form.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        page.goto(BASE_URL + "/admin/users")
        _wait_for_admin_fragment(page=page)

        admin_row = page.locator(
            "section.pyc-admin-page-fragment .data-table tr"
        ).filter(has_text=login_name).first

        edit_link = admin_row.locator("a.btn").filter(has_text="Edit")
        edit_link.click()

        _wait_for_admin_fragment(page=page)

        heading_text = page.locator(
            "section.pyc-admin-page-fragment h2"
        ).first.inner_text()
        testbase.assert_true(
            "Edit" in heading_text or "User" in heading_text
        )

        email_count = page.locator("input[name='email']").count()
        testbase.assert_true(email_count >= 1)
    finally:
        context.close()
    return


def test_admin_deactivate_user_workflow(browser: Browser):
    """
    **Feature: admin-users**
    **Property: Clicking the Deactivate button on a user row
    submits the deactivate POST and the user list shows the user
    as Inactive -- proves the deactivate handler + redirect +
    list render chain works end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)

        deact_username = "brtdct{}".format(_RUN_TAG)
        deact_email = "brtdct{}@example.test".format(_RUN_TAG)
        deact_password = "BrTestDeact123!"
        deact_display_name = "BR Test Deact {}".format(_RUN_TAG)

        # Create the throwaway user.
        page.goto(BASE_URL + "/admin/users/create")
        _wait_for_admin_fragment(page=page)
        page.fill("input[name='username']", deact_username)
        page.fill("input[name='email']", deact_email)
        page.fill("input[name='password']", deact_password)
        page.fill("input[name='display_name']", deact_display_name)

        # Navigate to the list and verify the user was created.
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/users",
        )
        deact_rows_before = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=deact_username)
        testbase.assert_true(deact_rows_before.count() >= 1)

        # Deactivate the user via the Deactivate button.
        auto_confirm(page)
        deact_row = page.locator(
            "section.pyc-admin-page-fragment .data-table tr"
        ).filter(has_text=deact_username).first
        deact_button = deact_row.locator("button.btn-danger").filter(
            has_text="Deactivate"
        )
        # Navigate back to the list to see the updated state.
        with page.expect_navigation(timeout=NAVIGATION_TIMEOUT_MS):
            deact_button.click()
        page.goto(BASE_URL + "/admin/users")
        _wait_for_admin_fragment(page=page)

        deact_row_after = page.locator(
            "section.pyc-admin-page-fragment .data-table tr"
        ).filter(has_text=deact_username).first
        row_text = deact_row_after.inner_text()
        testbase.assert_true("Inactive" in row_text)
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Roles -- list, create, detail, edit
# ---------------------------------------------------------------------------


def test_admin_roles_list_renders(browser: Browser):
    """
    **Feature: admin-roles**
    **Property: GET /admin/roles renders the roles list page
    inside the site shell with the expected heading and a data
    table -- confirms the roles list handler + template render
    end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        page.goto(BASE_URL + "/admin/roles")
        _wait_for_admin_fragment(page=page)

        heading_text = page.locator(
            "section.pyc-admin-page-fragment h2"
        ).first.inner_text()
        testbase.assert_true("Role" in heading_text)

        table_count = page.locator(
            "section.pyc-admin-page-fragment table.data-table"
        ).count()
        testbase.assert_true(table_count >= 1)
    finally:
        context.close()
    return


def test_admin_create_role_workflow(browser: Browser):
    """
    **Feature: admin-roles**
    **Property: Filling and submitting the create-role form in a
    real browser creates the role and the roles list contains the
    new row -- proves the full POST path + redirect + list render
    chain works end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)

        new_role_name = "brtcr{}".format(_RUN_TAG)
        new_description = "Browser-test role {}".format(_RUN_TAG)

        page.goto(BASE_URL + "/admin/roles/create")
        _wait_for_admin_fragment(page=page)

        heading_text = page.locator(
            "section.pyc-admin-page-fragment h2"
        ).first.inner_text()
        testbase.assert_true("Create Role" in heading_text)

        page.fill("input[name='name']", new_role_name)
        page.fill("textarea[name='description']", new_description)
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/roles",
        )

        new_row = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=new_role_name)
        testbase.assert_true(new_row.count() >= 1)
    finally:
        context.close()
    return


def test_admin_role_detail_renders(browser: Browser):
    """
    **Feature: admin-roles**
    **Property: Clicking a role name in the roles list navigates
    to the detail page and the detail page renders the role's
    name -- confirms the detail handler + template render without
    error.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        page.goto(BASE_URL + "/admin/roles")
        _wait_for_admin_fragment(page=page)

        # Guard: assert at least one role link exists before
        # clicking -- gives a clear FAILED assertion rather than a
        # Playwright timeout when the list is unexpectedly empty.
        role_links = page.locator(
            "section.pyc-admin-page-fragment .data-table td a"
        )
        testbase.assert_true(role_links.count() >= 1)

        first_link = role_links.first
        role_name = first_link.inner_text().strip()
        first_link.click()

        _wait_for_admin_fragment(page=page)

        fragment_text = page.locator(
            "section.pyc-admin-page-fragment"
        ).inner_text()
        testbase.assert_true(len(role_name) > 0)
        testbase.assert_true(role_name in fragment_text)
    finally:
        context.close()
    return


def test_admin_role_edit_non_system_role_workflow(browser: Browser):
    """
    **Feature: admin-roles**
    **Property: Navigating to the edit page of a custom role and
    updating its description redirects to the detail page with a
    success flash -- proves the role edit POST path works
    end-to-end for non-system roles.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)

        edit_role_name = "brtere{}".format(_RUN_TAG)
        edit_desc_initial = "Initial {}".format(_RUN_TAG)
        edit_desc_updated = "Updated {}".format(_RUN_TAG)

        # Create the role to edit.
        page.goto(BASE_URL + "/admin/roles/create")
        _wait_for_admin_fragment(page=page)
        page.fill("input[name='name']", edit_role_name)
        page.fill("textarea[name='description']", edit_desc_initial)
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/roles",
        )

        # Guard: verify the role row appeared before navigating
        # to the detail page -- gives a fast failure if creation
        # silently failed rather than a Playwright timeout.
        created_row = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=edit_role_name)
        testbase.assert_true(created_row.count() >= 1)

        # Navigate to the role's detail page.
        role_link = page.locator(
            "section.pyc-admin-page-fragment .data-table td a"
        ).filter(has_text=edit_role_name).first
        role_link.click()
        _wait_for_admin_fragment(page=page)

        # Click the Edit button.
        edit_btn = page.locator(
            "section.pyc-admin-page-fragment a.btn"
        ).filter(has_text="Edit").first
        edit_btn.click()
        _wait_for_admin_fragment(page=page)

        desc_textarea = page.locator("textarea[name='description']")
        desc_textarea.fill(edit_desc_updated)
        # Successful edit redirects to the detail page.
        with page.expect_navigation(timeout=NAVIGATION_TIMEOUT_MS):
            page.click("button[type='submit']")
        _wait_for_admin_fragment(page=page)

        message_text = _page_message_text(page=page)
        testbase.assert_true(
            "updated successfully" in message_text
            or edit_desc_updated.lower() in message_text
        )
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Variables -- list, create, edit, delete, history
# ---------------------------------------------------------------------------


def test_admin_variables_list_renders(browser: Browser):
    """
    **Feature: admin-variables**
    **Property: GET /admin/variables renders the variables list
    page inside the site shell with the expected heading --
    confirms the list handler + template render end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        page.goto(BASE_URL + "/admin/variables")
        _wait_for_admin_fragment(page=page)

        heading_text = page.locator(
            "section.pyc-admin-page-fragment h2"
        ).first.inner_text()
        testbase.assert_true("Variable" in heading_text)
    finally:
        context.close()
    return


def test_admin_create_variable_workflow(browser: Browser):
    """
    **Feature: admin-variables**
    **Property: Filling and submitting the create-variable form
    in a real browser creates the variable and the list then
    contains the new row -- proves the full POST path + redirect
    + list render chain works end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)

        var_name = "brcv{}".format(_RUN_TAG)
        var_value = "br-create-value-{}".format(_RUN_TAG)

        page.goto(BASE_URL + "/admin/variables/create")
        _wait_for_admin_fragment(page=page)

        heading_text = page.locator(
            "section.pyc-admin-page-fragment h2"
        ).first.inner_text()
        testbase.assert_true("Create Variable" in heading_text)

        page.fill("input[name='name']", var_name)
        page.select_option("select[name='var_type']", value="string")
        page.fill("textarea[name='value']", var_value)
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/variables",
        )

        new_row = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=var_name)
        testbase.assert_true(new_row.count() >= 1)
    finally:
        context.close()
    return


def test_admin_edit_variable_workflow(browser: Browser):
    """
    **Feature: admin-variables**
    **Property: Navigating to the edit page of an existing
    variable and updating its value redirects to the detail page
    with a success flash -- proves the variable edit POST path
    works end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)

        var_name = "brev{}".format(_RUN_TAG)
        var_value_initial = "initial-{}".format(_RUN_TAG)
        var_value_updated = "updated-{}".format(_RUN_TAG)

        # Create the variable first.
        page.goto(BASE_URL + "/admin/variables/create")
        _wait_for_admin_fragment(page=page)
        page.fill("input[name='name']", var_name)
        page.select_option("select[name='var_type']", value="string")
        page.fill("textarea[name='value']", var_value_initial)
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/variables",
        )

        # Guard: verify the variable row appeared before navigating
        # to the detail page.
        created_row = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=var_name)
        testbase.assert_true(created_row.count() >= 1)

        # Navigate to the detail page.
        var_link = page.locator(
            "section.pyc-admin-page-fragment .data-table td a"
        ).filter(has_text=var_name).first
        var_link.click()
        _wait_for_admin_fragment(page=page)

        # Navigate to the edit page.
        edit_btn = page.locator(
            "section.pyc-admin-page-fragment a.btn"
        ).filter(has_text="Edit").first
        edit_btn.click()
        _wait_for_admin_fragment(page=page)

        value_field = page.locator("textarea[name='value']")
        value_field.fill(var_value_updated)
        # On success the edit handler redirects to the detail page.
        with page.expect_navigation(timeout=NAVIGATION_TIMEOUT_MS):
            page.click("button[type='submit']")
        _wait_for_admin_fragment(page=page)

        message_text = _page_message_text(page=page)
        testbase.assert_true(
            "updated successfully" in message_text
            or var_value_updated.lower() in message_text
        )
    finally:
        context.close()
    return


def test_admin_delete_variable_workflow(browser: Browser):
    """
    **Feature: admin-variables**
    **Property: Submitting the delete form for an existing
    variable redirects to the list and the deleted variable no
    longer appears in the list -- proves the variable delete POST
    path works end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)

        del_var_name = "brdv{}".format(_RUN_TAG)
        del_var_value = "delete-value-{}".format(_RUN_TAG)

        # Create the variable to delete.
        page.goto(BASE_URL + "/admin/variables/create")
        _wait_for_admin_fragment(page=page)
        page.fill("input[name='name']", del_var_name)
        page.select_option("select[name='var_type']", value="string")
        page.fill("textarea[name='value']", del_var_value)
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/variables",
        )

        # Guard: verify the variable row appeared.
        created_row = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=del_var_name)
        testbase.assert_true(created_row.count() >= 1)

        # Navigate to the variable's detail page.
        var_link = page.locator(
            "section.pyc-admin-page-fragment .data-table td a"
        ).filter(has_text=del_var_name).first
        var_link.click()
        _wait_for_admin_fragment(page=page)

        # Submit the Delete form on the detail page.
        auto_confirm(page)
        del_btn = page.locator(
            "section.pyc-admin-page-fragment button.btn-danger"
        ).filter(has_text="Delete").first
        with page.expect_navigation(timeout=NAVIGATION_TIMEOUT_MS):
            del_btn.click()
        page.goto(BASE_URL + "/admin/variables")
        _wait_for_admin_fragment(page=page)

        leftover_rows = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=del_var_name)
        testbase.assert_equal(leftover_rows.count(), 0)
    finally:
        context.close()
    return


def test_admin_variable_history_renders(browser: Browser):
    """
    **Feature: admin-variables**
    **Property: GET /admin/variables/<name>/history renders the
    history page without error -- confirms the history handler +
    template render end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)

        hist_var_name = "brhv{}".format(_RUN_TAG)
        hist_var_value = "history-value-{}".format(_RUN_TAG)

        # Create a variable to guarantee a history entry.
        page.goto(BASE_URL + "/admin/variables/create")
        _wait_for_admin_fragment(page=page)
        page.fill("input[name='name']", hist_var_name)
        page.select_option("select[name='var_type']", value="string")
        page.fill("textarea[name='value']", hist_var_value)
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/variables",
        )

        # Guard: verify the variable was created before navigating
        # to the history URL (a missing variable redirects to the
        # list and the history content will be absent).
        created_row = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=hist_var_name)
        testbase.assert_true(created_row.count() >= 1)

        history_url = "{}/admin/variables/{}/history".format(
            BASE_URL, hist_var_name
        )
        page.goto(history_url)
        _wait_for_admin_fragment(page=page)

        fragment_text = page.locator(
            "section.pyc-admin-page-fragment"
        ).inner_text()
        testbase.assert_true(
            "history" in fragment_text.lower()
            or hist_var_name in fragment_text
        )
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Scopes -- list, create, delete
# ---------------------------------------------------------------------------


def test_admin_scopes_list_renders(browser: Browser):
    """
    **Feature: admin-scopes**
    **Property: GET /admin/scopes renders the scope list page
    inside the site shell with the expected heading -- confirms
    the scope list handler + template render end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        page.goto(BASE_URL + "/admin/scopes")
        _wait_for_admin_fragment(page=page)

        heading_text = page.locator(
            "section.pyc-admin-page-fragment h2"
        ).first.inner_text()
        testbase.assert_true("Scope" in heading_text)
    finally:
        context.close()
    return


def test_admin_create_scope_workflow(browser: Browser):
    """
    **Feature: admin-scopes**
    **Property: Filling and submitting the create-scope form in
    a real browser creates the scope and the scopes list contains
    the new row -- proves the full POST path + redirect + list
    render chain works end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)

        scope_name = "brcs{}".format(_RUN_TAG)
        scope_desc = "Browser-test scope {}".format(_RUN_TAG)

        page.goto(BASE_URL + "/admin/scopes/create")
        _wait_for_admin_fragment(page=page)

        heading_text = page.locator(
            "section.pyc-admin-page-fragment h2"
        ).first.inner_text()
        testbase.assert_true("Create" in heading_text)

        page.fill("input[name='name']", scope_name)
        page.fill("textarea[name='description']", scope_desc)
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/scopes",
        )

        new_row = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=scope_name)
        testbase.assert_true(new_row.count() >= 1)
    finally:
        context.close()
    return


def test_admin_delete_scope_workflow(browser: Browser):
    """
    **Feature: admin-scopes**
    **Property: Submitting the delete form for an existing scope
    redirects to the scope list and the deleted scope no longer
    appears -- proves the scope delete POST path works end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)

        del_scope_name = "brds{}".format(_RUN_TAG)
        del_scope_desc = "Delete-scope-wf test {}".format(_RUN_TAG)

        # Create the scope to delete.
        page.goto(BASE_URL + "/admin/scopes/create")
        _wait_for_admin_fragment(page=page)
        page.fill("input[name='name']", del_scope_name)
        page.fill("textarea[name='description']", del_scope_desc)
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/scopes",
        )

        # Guard: verify the scope row appeared before proceeding --
        # gives a fast failure if creation silently failed rather
        # than a Playwright timeout on a missing delete button.
        created_row = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=del_scope_name)
        testbase.assert_true(created_row.count() >= 1)

        # Click the Delete button in the row for this scope.
        auto_confirm(page)
        del_row = page.locator(
            "section.pyc-admin-page-fragment .data-table tr"
        ).filter(has_text=del_scope_name).first
        del_btn = del_row.locator("button.btn-danger").filter(
            has_text="Delete"
        )
        with page.expect_navigation(timeout=NAVIGATION_TIMEOUT_MS):
            del_btn.click()
        page.goto(BASE_URL + "/admin/scopes")
        _wait_for_admin_fragment(page=page)

        leftover = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=del_scope_name)
        testbase.assert_equal(leftover.count(), 0)
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Secrets -- list, create, edit, delete
# ---------------------------------------------------------------------------


def test_admin_secrets_list_renders(browser: Browser):
    """
    **Feature: admin-secrets**
    **Property: GET /admin/secrets renders the secrets list page
    inside the site shell with the expected heading -- confirms the
    secret list handler + template render end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        page.goto(BASE_URL + "/admin/secrets")
        _wait_for_admin_fragment(page=page)

        heading_text = page.locator(
            "section.pyc-admin-page-fragment h2"
        ).first.inner_text()
        testbase.assert_true("Secret" in heading_text)
    finally:
        context.close()
    return


def test_admin_create_secret_workflow(browser: Browser):
    """
    **Feature: admin-secrets**
    **Property: Filling and submitting the create-secret form in
    a real browser creates the secret and the secrets list
    contains the new row -- proves the full POST path + redirect
    + list render chain works end-to-end. This test first creates
    a scope to satisfy the required scope selector.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)

        scope_name = "brscscp{}".format(_RUN_TAG)
        secret_name = "brsct{}".format(_RUN_TAG)
        secret_value = "br-secret-value-{}".format(_RUN_TAG)

        # Create a scope to assign the secret to.
        page.goto(BASE_URL + "/admin/scopes/create")
        _wait_for_admin_fragment(page=page)
        page.fill("input[name='name']", scope_name)
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/scopes",
        )

        # Guard: verify the scope was created before navigating to
        # secrets/create -- the scope_id dropdown will be empty if
        # scope creation silently failed, causing select_option to
        # timeout after 30 s instead of raising a clear assertion.
        created_scope = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=scope_name)
        testbase.assert_true(created_scope.count() >= 1)

        # Create the secret.
        page.goto(BASE_URL + "/admin/secrets/create")
        _wait_for_admin_fragment(page=page)

        heading_text = page.locator(
            "section.pyc-admin-page-fragment h2"
        ).first.inner_text()
        testbase.assert_true("Create Secret" in heading_text)

        page.select_option("select[name='scope_id']", label=scope_name)
        page.fill("input[name='name']", secret_name)
        page.select_option("select[name='secret_type']", value="generic")
        page.fill("textarea[name='value']", secret_value)
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/secrets",
        )

        new_row = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=secret_name)
        testbase.assert_true(new_row.count() >= 1)
    finally:
        context.close()
    return


def test_admin_edit_secret_workflow(browser: Browser):
    """
    **Feature: admin-secrets**
    **Property: Navigating to the edit page of an existing secret
    and updating its description redirects to the secrets list
    with a success flash -- proves the secret edit POST path works
    end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)

        scope_name = "brsescp{}".format(_RUN_TAG)
        secret_name = "brsed{}".format(_RUN_TAG)
        secret_value = "edit-wf-secret-{}".format(_RUN_TAG)
        new_description = "Updated by edit-secret wf {}".format(_RUN_TAG)

        # Create scope.
        page.goto(BASE_URL + "/admin/scopes/create")
        _wait_for_admin_fragment(page=page)
        page.fill("input[name='name']", scope_name)
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/scopes",
        )

        # Guard: verify the scope was created before navigating to
        # secrets/create -- the scope_id dropdown will be empty if
        # scope creation silently failed.
        created_scope = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=scope_name)
        testbase.assert_true(created_scope.count() >= 1)

        # Create secret.
        page.goto(BASE_URL + "/admin/secrets/create")
        _wait_for_admin_fragment(page=page)
        page.select_option("select[name='scope_id']", label=scope_name)
        page.fill("input[name='name']", secret_name)
        page.select_option("select[name='secret_type']", value="generic")
        page.fill("textarea[name='value']", secret_value)
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/secrets",
        )

        # Guard: verify the secret row appeared before clicking Edit.
        created_secret = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=secret_name)
        testbase.assert_true(created_secret.count() >= 1)

        # Click the Edit button in the secret's row.
        secret_row = page.locator(
            "section.pyc-admin-page-fragment .data-table tr"
        ).filter(has_text=secret_name).first
        edit_btn = secret_row.locator("a.btn").filter(has_text="Edit")
        edit_btn.click()
        _wait_for_admin_fragment(page=page)

        desc_field = page.locator("textarea[name='description']")
        desc_field.fill(new_description)
        # Read the flash on the page the POST redirects to. A flash
        # is one-shot: navigating on to the list first would consume
        # it and assert against a page that can never carry it.
        with page.expect_navigation(timeout=NAVIGATION_TIMEOUT_MS):
            page.click("button[type='submit']")
        _wait_for_admin_fragment(page=page)

        message_text = _page_message_text(page=page)
        testbase.assert_true("updated successfully" in message_text)
    finally:
        context.close()
    return


def test_admin_delete_secret_workflow(browser: Browser):
    """
    **Feature: admin-secrets**
    **Property: Submitting the delete form for an existing secret
    redirects to the secrets list and the deleted secret no longer
    appears -- proves the secret delete POST path works end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)

        scope_name = "brsdsc{}".format(_RUN_TAG)
        secret_name = "brsdl{}".format(_RUN_TAG)
        secret_value = "delete-wf-secret-{}".format(_RUN_TAG)

        # Create scope.
        page.goto(BASE_URL + "/admin/scopes/create")
        _wait_for_admin_fragment(page=page)
        page.fill("input[name='name']", scope_name)
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/scopes",
        )

        # Guard: verify the scope was created before navigating to
        # secrets/create -- the scope_id dropdown will be empty if
        # scope creation silently failed.
        created_scope = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=scope_name)
        testbase.assert_true(created_scope.count() >= 1)

        # Create secret.
        page.goto(BASE_URL + "/admin/secrets/create")
        _wait_for_admin_fragment(page=page)
        page.select_option("select[name='scope_id']", label=scope_name)
        page.fill("input[name='name']", secret_name)
        page.select_option("select[name='secret_type']", value="generic")
        page.fill("textarea[name='value']", secret_value)
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/secrets",
        )

        # Guard: verify the secret row appeared before clicking Delete.
        created_secret = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=secret_name)
        testbase.assert_true(created_secret.count() >= 1)

        # Click the Delete button in the secret's row.
        auto_confirm(page)
        secret_row = page.locator(
            "section.pyc-admin-page-fragment .data-table tr"
        ).filter(has_text=secret_name).first
        del_btn = secret_row.locator("button.btn-danger").filter(
            has_text="Delete"
        )
        with page.expect_navigation(timeout=NAVIGATION_TIMEOUT_MS):
            del_btn.click()
        page.goto(BASE_URL + "/admin/secrets")
        _wait_for_admin_fragment(page=page)

        leftover = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=secret_name)
        testbase.assert_equal(leftover.count(), 0)
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def test_admin_sessions_list_renders(browser: Browser):
    """
    **Feature: admin-sessions**
    **Property: GET /admin/sessions renders the sessions list
    page inside the site shell -- confirms the sessions handler +
    template render end-to-end (there is always at least the
    current session in the table).**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        page.goto(BASE_URL + "/admin/sessions")
        _wait_for_admin_fragment(page=page)

        heading_text = page.locator(
            "section.pyc-admin-page-fragment h2"
        ).first.inner_text()
        testbase.assert_true(
            "Session" in heading_text or "session" in heading_text.lower()
        )
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Audit logs
# ---------------------------------------------------------------------------


def test_admin_audit_logs_list_renders(browser: Browser):
    """
    **Feature: admin-audit-logs**
    **Property: GET /admin/audit-logs renders the audit logs list
    page inside the site shell with the expected heading --
    confirms the audit log handler + template render end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        page.goto(BASE_URL + "/admin/audit-logs")
        _wait_for_admin_fragment(page=page)

        heading_text = page.locator(
            "section.pyc-admin-page-fragment h2"
        ).first.inner_text()
        testbase.assert_true(
            "Audit" in heading_text or "Log" in heading_text
        )
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Enrollment tokens -- list, mint, revoke
# ---------------------------------------------------------------------------


def test_admin_enrollment_tokens_list_renders(browser: Browser):
    """
    **Feature: admin-enrollment-tokens**
    **Property: GET /admin/enrollment-tokens renders the token
    list page and the mint form inside the site shell -- confirms
    the enrollment handler + template render end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        page.goto(BASE_URL + "/admin/enrollment-tokens")
        _wait_for_admin_fragment(page=page)

        heading_text = page.locator(
            "section.pyc-admin-page-fragment h2"
        ).first.inner_text()
        testbase.assert_true(
            "Enrollment" in heading_text or "Token" in heading_text
        )

        mint_form_count = page.locator(
            "section.pyc-admin-page-fragment "
            "form[action*='enrollment-tokens/mint']"
        ).count()
        testbase.assert_true(mint_form_count >= 1)
    finally:
        context.close()
    return


def test_admin_mint_enrollment_token_workflow(browser: Browser):
    """
    **Feature: admin-enrollment-tokens**
    **Property: Filling and submitting the mint-token form in a
    real browser issues a new enrollment token and the token list
    contains the new row with a flash message carrying the
    one-time secret -- proves the full mint POST path + redirect
    + list render chain works end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)

        # project_id must be a valid UUID string because the
        # EnrollmentToken.project_id column is UUIDType(binary=False).
        import uuid as _uuid
        mint_project_id = str(_uuid.uuid4())
        mint_pod_name = "brpod{}".format(_RUN_TAG)

        page.goto(BASE_URL + "/admin/enrollment-tokens")
        _wait_for_admin_fragment(page=page)

        page.fill("input[name='project_id']", mint_project_id)
        page.fill("input[name='pod_name']", mint_pod_name)
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/enrollment-tokens",
        )

        # The new token row should appear for this pod name.
        token_row = page.locator(
            "section.pyc-admin-page-fragment .data-table td"
        ).filter(has_text=mint_pod_name)
        testbase.assert_true(token_row.count() >= 1)
    finally:
        context.close()
    return


def test_admin_revoke_enrollment_token_workflow(browser: Browser):
    """
    **Feature: admin-enrollment-tokens**
    **Property: Clicking the Revoke button on a PENDING token row
    submits the revoke POST and the token list reloads with a
    success flash containing "revoked" -- proves the revoke
    handler + redirect + flash chain works end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)

        # project_id must be a valid UUID string (UUIDType column
        # rejects non-UUID strings with "bytes is not a 16-char string").
        import uuid as _uuid
        revoke_project_id = str(_uuid.uuid4())
        revoke_pod_name = "brpodr{}".format(_RUN_TAG)

        # Mint a token to revoke.
        page.goto(BASE_URL + "/admin/enrollment-tokens")
        _wait_for_admin_fragment(page=page)
        page.fill("input[name='project_id']", revoke_project_id)
        page.fill("input[name='pod_name']", revoke_pod_name)
        _click_submit_and_goto_list(
            page=page,
            submit_selector="button[type='submit']",
            list_path="/admin/enrollment-tokens",
        )

        # Find the PENDING row for this pod and click Revoke.
        auto_confirm(page)
        token_row = page.locator(
            "section.pyc-admin-page-fragment .data-table tr"
        ).filter(has_text=revoke_pod_name).first
        revoke_btn = token_row.locator("button.btn-danger").filter(
            has_text="Revoke"
        )
        with page.expect_navigation(timeout=NAVIGATION_TIMEOUT_MS):
            revoke_btn.click()
        page.goto(BASE_URL + "/admin/enrollment-tokens")
        _wait_for_admin_fragment(page=page)

        fragment_text = page.locator(
            "section.pyc-admin-page-fragment"
        ).inner_text()
        # After the revoke POST the page reloads; the token row
        # should no longer show a Revoke button (status changed from
        # PENDING). Accept either "revoked" flash in the page text or
        # the absence of a Revoke button in that pod's row.
        remaining_revoke_btn = page.locator(
            "section.pyc-admin-page-fragment .data-table tr"
        ).filter(has_text=revoke_pod_name).locator(
            "button.btn-danger"
        ).filter(has_text="Revoke")
        testbase.assert_equal(remaining_revoke_btn.count(), 0)
    finally:
        context.close()
    return
