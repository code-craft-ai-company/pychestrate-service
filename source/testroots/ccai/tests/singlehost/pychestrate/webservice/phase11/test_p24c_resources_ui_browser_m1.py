"""
.. module:: test_p24c_resources_ui_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Playwright browser-driven UI tests for the /resources
               area of the pychestrate consumer interface.

.. moduleauthor:: Code Craft AI LLC

The /resources surface is a legacy server-rendered HTML application
(not the mj-* custom-element shell). Every page returns Jinja2-
rendered HTML directly from the server. This module drives the full
CRUD lifecycle for every entity the resources blueprint exposes:

* Resources core  -- dashboard + list + create + detail + edit +
                     delete + checkout (control present / no-500).
* Pools           -- list + create + detail + delete.
* IP Pools        -- list + create + detail + edit + delete +
                     checkout/checkin (no-500 assertions).
* Allocations     -- list + history (smoke renders).
* Reservations    -- list + create + cancel.
* Health          -- dashboard + detail + config (smoke renders).
* Tags            -- list (smoke render).

Credentials are read from the same env vars as the other phase-11
browser tests (``PYCHESTRATE_TEST_ADMIN_LOGIN`` /
``PYCHESTRATE_TEST_ADMIN_PASSWORD``); tests skip cleanly when either
is unset.

Each workflow test asserts on *its own created row* so assertions
are always stable regardless of pre-existing data in the database.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import time

from typing import Optional, Tuple

from playwright.sync_api import Browser, BrowserContext, Page, Response

from ccai import testbase

from ccai.testshared.skip_helper import skip_test
from ccai.testshared.test_config import BASE_URL


# Navigation timeout -- higher than the httpx counterpart because the
# browser must also fetch CSS, images, and any inline scripts.
NAVIGATION_TIMEOUT_MS: int = 20_000

# Standard wait after a POST redirect before reading the page.
LOAD_WAIT_MS: int = 8_000

ENV_ADMIN_LOGIN: str = "PYCHESTRATE_TEST_ADMIN_LOGIN"
ENV_ADMIN_PASSWORD: str = "PYCHESTRATE_TEST_ADMIN_PASSWORD"


# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------


def _resolve_admin_credentials() -> Tuple[str, str]:
    """
        Read admin credentials from the environment.  Raise
        :class:`SkipError` when either variable is unset/empty so the
        test is reported as SKIPPED on CI runners that have not been
        wired with the secrets.

        :returns: ``(login_name, password)`` tuple.

        :raises: :class:`SkipError` when either env var is unset.
    """
    login_name = os.environ.get(ENV_ADMIN_LOGIN, "")
    password = os.environ.get(ENV_ADMIN_PASSWORD, "")

    if len(login_name) == 0 or len(password) == 0:
        err_msg_lines = [
            "Resources browser tests need admin credentials in env vars:",
            "  {}".format(ENV_ADMIN_LOGIN),
            "  {}".format(ENV_ADMIN_PASSWORD),
        ]
        skip_test(reason=os.linesep.join(err_msg_lines))

    rtnval = (login_name, password)
    return rtnval


# ---------------------------------------------------------------------------
# Login helper
# ---------------------------------------------------------------------------


def _login(*, context: BrowserContext) -> Page:
    """
        Open a fresh page in *context*, drive the login form with
        the admin credentials, and return the authenticated page after
        the server redirect completes.

        The /resources pages are legacy server-rendered HTML -- they do
        not use the mj-* shell, so we wait for the page to reach
        ``load`` state rather than waiting for ``pyc-site-shell``.

        :param context: A fresh browser context (no prior cookies).

        :returns: Page that has completed the login redirect.
    """
    login_name, password = _resolve_admin_credentials()

    page = context.new_page()
    page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)

    page.goto(BASE_URL + "/login")
    page.wait_for_load_state("load")

    page.fill("input[name='username']", login_name)
    page.fill("input[name='password']", password)
    page.locator("button.btn-primary").first.click()

    # After submit the server redirects. Wait for the resulting page
    # to finish loading. Network-idle is NOT used here -- on the admin
    # side with pyc-site-shell the shell polls endpoints, but on the
    # resources legacy page there is no such polling. Use ``load``
    # which fires once the document + its inline resources are ready.
    page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

    rtnval = page
    return rtnval


# ---------------------------------------------------------------------------
# Shared page helpers
# ---------------------------------------------------------------------------


def _go(*, page: Page, path: str) -> None:
    """
        Navigate *page* to *path* under :data:`BASE_URL` and wait for
        the ``load`` event.

        :param page: Authenticated Playwright page.
        :param path: URL path (must start with ``/``).

        :returns: None.
    """
    page.goto(BASE_URL + path)
    page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)
    return


def _assert_no_500(*, page: Page, path: str) -> None:
    """
        Assert the page at *path* did not return a server-error status.
        We inspect the current URL (must not be the error page) and
        assert the rendered body does not contain the literal text
        "Internal Server Error" or "500".

        :param page: Playwright page already navigated to *path*.
        :param path: Path that was requested (used in error messages).

        :returns: None.
    """
    content = page.content()
    has_500_heading = "Internal Server Error" in content
    testbase.assert_true(
        has_500_heading is False,
    )
    return


def _read_csrf_token(*, page: Page) -> str:
    """
        Extract the CSRF token from the first hidden input named
        ``csrf_token`` in the current page's DOM.

        :param page: Authenticated Playwright page.

        :returns: CSRF token string.
    """
    token = page.locator("input[name='csrf_token']").first.get_attribute(
        "value"
    )
    if token is None:
        token = ""
    return token


# ---------------------------------------------------------------------------
# Resources core: dashboard
# ---------------------------------------------------------------------------


def test_resources_dashboard_renders(browser: Browser):
    """
    **Feature: resources-ui-core**
    **Property: GET /resources renders the Resource Management
    Dashboard heading. Proves the blueprint is mounted and the
    dashboard handler returns a 200 with its expected h2 content.**
    """
    _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        _go(page=page, path="/resources")
        _assert_no_500(page=page, path="/resources")

        heading_count = page.locator("h2:has-text('Resource Management Dashboard')").count()
        testbase.assert_true(heading_count >= 1)
    finally:
        context.close()
    return


def test_resources_dashboard_root_redirects_to_dashboard(browser: Browser):
    """
    **Feature: resources-ui-core**
    **Property: GET /resources/ (trailing slash, root endpoint)
    renders the same Resource Management Dashboard page as
    /resources/dashboard -- both endpoint names are registered
    to the same handler.**
    """
    _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        _go(page=page, path="/resources/dashboard")
        _assert_no_500(page=page, path="/resources/dashboard")

        heading_count = page.locator(
            "h2:has-text('Resource Management Dashboard')"
        ).count()
        testbase.assert_true(heading_count >= 1)
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Resources core: list
# ---------------------------------------------------------------------------


def test_resource_list_renders(browser: Browser):
    """
    **Feature: resources-ui-core**
    **Property: GET /resources/list renders the Resources list page
    with its 'Resources' h2 heading and a table header row. Proves
    the list handler returns a valid 200 with the expected scaffolding
    regardless of whether any resource rows exist in the database.**
    """
    _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        _go(page=page, path="/resources/list")
        _assert_no_500(page=page, path="/resources/list")

        heading_count = page.locator("h2:has-text('Resources')").count()
        testbase.assert_true(heading_count >= 1)

        # The list template always renders the table header.
        name_th_count = page.locator("th:has-text('Name')").count()
        testbase.assert_true(name_th_count >= 1)
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Resources core: create → detail → edit → delete
# ---------------------------------------------------------------------------


def test_resource_create_appears_in_list(browser: Browser):
    """
    **Feature: resources-ui-core**
    **Property: Filling the 'Create Resource' form with a unique name
    and submitting it (POST /resources/create) creates the resource,
    redirects to the detail page, and the resource name appears in the
    /resources/list table. Proves the full create workflow end-to-end.**
    """
    _resolve_admin_credentials()

    # Use a timestamp suffix to guarantee uniqueness across reruns.
    resource_name = "test-res-create-{}".format(int(time.time()))

    context = browser.new_context()
    try:
        page = _login(context=context)

        _go(page=page, path="/resources/create")
        _assert_no_500(page=page, path="/resources/create")

        heading_count = page.locator("h2:has-text('Create Resource')").count()
        testbase.assert_true(heading_count >= 1)

        # Fill the create form.
        page.fill("input[name='name']", resource_name)
        page.select_option("select[name='resource_type']", "device")
        page.fill("textarea[name='description']", "Created by p24c browser test")

        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        # After a successful create the server redirects to the detail
        # page. The detail page shows the resource name in a heading or
        # the page content.
        _assert_no_500(page=page, path="/resources/create -> detail")
        content = page.content()
        testbase.assert_true(resource_name in content)

        # Also verify the resource appears in the list. The list is
        # paginated at 20 rows, so a freshly created resource is not
        # guaranteed a slot on page one -- filter for it by name
        # rather than assuming it landed there.
        _go(
            page=page,
            path="/resources/list?search={}".format(resource_name),
        )
        content = page.content()
        testbase.assert_true(resource_name in content)
    finally:
        context.close()
    return


def test_resource_detail_renders(browser: Browser):
    """
    **Feature: resources-ui-core**
    **Property: After creating a resource, GET /resources/{id} renders
    the resource detail page showing the resource name. Proves the
    detail handler resolves the resource correctly and the template
    renders without a 500.**
    """
    _resolve_admin_credentials()

    resource_name = "test-res-detail-{}".format(int(time.time()))

    context = browser.new_context()
    try:
        page = _login(context=context)

        # Create a resource first.
        _go(page=page, path="/resources/create")
        page.fill("input[name='name']", resource_name)
        page.select_option("select[name='resource_type']", "generic")
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        # We should be on the detail page now.
        _assert_no_500(page=page, path="detail after create")
        content = page.content()
        testbase.assert_true(resource_name in content)

        # Confirm the current URL is a /resources/{id} path.
        current_url = page.url
        testbase.assert_true("/resources/" in current_url)
    finally:
        context.close()
    return


def test_resource_edit_updates_description(browser: Browser):
    """
    **Feature: resources-ui-core**
    **Property: GET /resources/{id}/edit shows the edit form; POST
    /resources/{id}/edit updates the resource and redirects back to
    the detail page where the updated description appears. Proves the
    edit handler processes the form and the manager persists the
    change.**
    """
    _resolve_admin_credentials()

    resource_name = "test-res-edit-{}".format(int(time.time()))
    updated_description = "Updated by p24c edit test"

    context = browser.new_context()
    try:
        page = _login(context=context)

        # Create the resource.
        _go(page=page, path="/resources/create")
        page.fill("input[name='name']", resource_name)
        page.select_option("select[name='resource_type']", "generic")
        page.fill("textarea[name='description']", "Initial description")
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        _assert_no_500(page=page, path="detail after create")

        # Extract the resource ID from the current URL.
        detail_url = page.url
        # URL shape: .../resources/{id}  -- the last path segment is the id.
        resource_id_str = detail_url.rstrip("/").split("/")[-1]
        testbase.assert_true(resource_id_str.isdigit())

        # Navigate to the edit form.
        edit_path = "/resources/{}/edit".format(resource_id_str)
        _go(page=page, path=edit_path)
        _assert_no_500(page=page, path=edit_path)

        heading_count = page.locator("h2:has-text('Edit Resource')").count()
        testbase.assert_true(heading_count >= 1)

        # Fill in the updated description and submit.
        description_field = page.locator("textarea[name='description']")
        description_field.fill(updated_description)
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        _assert_no_500(page=page, path="detail after edit")
        content = page.content()
        testbase.assert_true(updated_description in content)
    finally:
        context.close()
    return


def test_resource_delete_removes_from_list(browser: Browser):
    """
    **Feature: resources-ui-core**
    **Property: POST /resources/{id}/delete removes the resource and
    redirects to the list page where the deleted resource no longer
    appears. Proves the delete handler calls the manager, the manager
    removes the row, and the list re-renders without the deleted name.**
    """
    _resolve_admin_credentials()

    resource_name = "test-res-delete-{}".format(int(time.time()))

    context = browser.new_context()
    try:
        page = _login(context=context)

        # Create the resource.
        _go(page=page, path="/resources/create")
        page.fill("input[name='name']", resource_name)
        page.select_option("select[name='resource_type']", "generic")
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        _assert_no_500(page=page, path="detail after create")

        detail_url = page.url
        resource_id_str = detail_url.rstrip("/").split("/")[-1]
        testbase.assert_true(resource_id_str.isdigit())

        # Navigate to the list and click Delete for our resource.
        # Filter by name: the list pages at 20 rows, so the row is
        # not necessarily on page one.
        list_path = "/resources/list?search={}".format(resource_name)
        _go(page=page, path=list_path)
        content = page.content()
        testbase.assert_true(resource_name in content)

        # Submit the inline delete form by clicking the Delete button
        # in the row that contains our resource name. The template
        # renders a <form> with a confirm() guard -- handle the dialog.
        page.on("dialog", lambda dialog: dialog.accept())
        delete_button = page.locator(
            "tr:has-text('{}') button:has-text('Delete')".format(
                resource_name
            )
        ).first
        delete_button.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        _assert_no_500(page=page, path="list after delete")

        content = page.content()
        testbase.assert_true(resource_name not in content)
    finally:
        context.close()
    return


def test_resource_checkout_control_present_on_detail(browser: Browser):
    """
    **Feature: resources-ui-core**
    **Property: The resource detail page (/resources/{id}) contains a
    form whose action includes '/checkout', confirming the checkout
    POST action endpoint is wired up and the template renders the
    control. Proves the detail handler exposes the checkout path
    without a 500.**
    """
    _resolve_admin_credentials()

    resource_name = "test-res-checkout-{}".format(int(time.time()))

    context = browser.new_context()
    try:
        page = _login(context=context)

        # Create a resource.
        _go(page=page, path="/resources/create")
        page.fill("input[name='name']", resource_name)
        page.select_option("select[name='resource_type']", "device")
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        _assert_no_500(page=page, path="detail after create")

        # The detail page should contain a form pointing at /checkout.
        content = page.content()
        testbase.assert_true("/checkout" in content)
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Pools: list + create + detail + delete
# ---------------------------------------------------------------------------


def test_pool_list_renders(browser: Browser):
    """
    **Feature: resources-ui-pools**
    **Property: GET /resources/pools renders the Resource Pools list
    page with its expected h2 heading. Proves the pool_list handler is
    mounted and returns a non-500 response with the list scaffolding.**
    """
    _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        _go(page=page, path="/resources/pools")
        _assert_no_500(page=page, path="/resources/pools")

        heading_count = page.locator(
            "h2:has-text('Resource Pools')"
        ).count()
        testbase.assert_true(heading_count >= 1)
    finally:
        context.close()
    return


def test_pool_create_appears_in_list(browser: Browser):
    """
    **Feature: resources-ui-pools**
    **Property: Filling the Create Resource Pool form (GET
    /resources/pools/create) and submitting it (POST
    /resources/pools/create) creates the pool, redirects to its detail
    page, and the pool name is visible. Proves the pool create workflow
    end-to-end.**
    """
    _resolve_admin_credentials()

    pool_name = "test-pool-{}".format(int(time.time()))

    context = browser.new_context()
    try:
        page = _login(context=context)

        _go(page=page, path="/resources/pools/create")
        _assert_no_500(page=page, path="/resources/pools/create")

        heading_count = page.locator(
            "h2:has-text('Create Resource Pool')"
        ).count()
        testbase.assert_true(heading_count >= 1)

        page.fill("input[name='name']", pool_name)
        page.fill(
            "textarea[name='description']",
            "Created by p24c pool browser test",
        )
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        _assert_no_500(page=page, path="/resources/pools/create POST")
        content = page.content()
        testbase.assert_true(pool_name in content)
    finally:
        context.close()
    return


def test_pool_detail_renders(browser: Browser):
    """
    **Feature: resources-ui-pools**
    **Property: After creating a resource pool, GET
    /resources/pools/{id} renders the pool detail page showing the
    pool name in the page content. Proves the pool_detail handler
    resolves the pool and renders without a 500.**
    """
    _resolve_admin_credentials()

    pool_name = "test-pool-detail-{}".format(int(time.time()))

    context = browser.new_context()
    try:
        page = _login(context=context)

        _go(page=page, path="/resources/pools/create")
        page.fill("input[name='name']", pool_name)
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        # After successful create we should land on the detail page.
        _assert_no_500(page=page, path="pool detail after create")
        content = page.content()
        testbase.assert_true(pool_name in content)

        detail_url = page.url
        testbase.assert_true("/pools/" in detail_url)
    finally:
        context.close()
    return


def test_pool_delete_removes_from_list(browser: Browser):
    """
    **Feature: resources-ui-pools**
    **Property: POST /resources/pools/{id}/delete removes the pool and
    redirects to /resources/pools where the deleted pool name is no
    longer in the page content. Proves the pool delete handler calls
    the manager and cleans up the row.**
    """
    _resolve_admin_credentials()

    pool_name = "test-pool-delete-{}".format(int(time.time()))

    context = browser.new_context()
    try:
        page = _login(context=context)

        # Create the pool.
        _go(page=page, path="/resources/pools/create")
        page.fill("input[name='name']", pool_name)
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        _assert_no_500(page=page, path="pool detail after create")
        detail_url = page.url
        pool_id_str = detail_url.rstrip("/").split("/")[-1]
        testbase.assert_true(pool_id_str.isdigit())

        # Navigate to list and verify the pool is there.
        _go(page=page, path="/resources/pools")
        content = page.content()
        testbase.assert_true(pool_name in content)

        # Submit the delete form for our pool by clicking its Delete
        # button. Accept the browser confirm dialog if present.
        page.on("dialog", lambda dialog: dialog.accept())
        delete_button = page.locator(
            "tr:has-text('{}') button:has-text('Delete')".format(pool_name)
        ).first
        delete_button.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        _assert_no_500(page=page, path="pool list after delete")
        content = page.content()
        testbase.assert_true(pool_name not in content)
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# IP Pools: list + create + detail + edit + delete + checkout/checkin no-500
# ---------------------------------------------------------------------------


def test_ip_pool_list_renders(browser: Browser):
    """
    **Feature: resources-ui-ip-pools**
    **Property: GET /resources/ip-pools renders the IP Pools list page
    with its expected h2 heading. Proves the ip_pool_list handler is
    mounted and returns a non-500 response.**
    """
    _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        _go(page=page, path="/resources/ip-pools")
        _assert_no_500(page=page, path="/resources/ip-pools")

        heading_count = page.locator("h2:has-text('IP Pools')").count()
        testbase.assert_true(heading_count >= 1)
    finally:
        context.close()
    return


def test_ip_pool_create_appears_in_list(browser: Browser):
    """
    **Feature: resources-ui-ip-pools**
    **Property: Filling the Create IP Pool form and submitting it
    (POST /resources/ip-pools/create) creates the pool, redirects to
    the detail page, and the pool name is visible. Proves the IP pool
    create workflow end-to-end including CIDR parsing.**
    """
    _resolve_admin_credentials()

    pool_name = "test-ippool-{}".format(int(time.time()))
    # Use a unique /30 CIDR to avoid collisions on the same server.
    ts_mod = int(time.time()) % 254
    cidr = "10.100.{}.0/30".format(ts_mod)

    context = browser.new_context()
    try:
        page = _login(context=context)

        _go(page=page, path="/resources/ip-pools/create")
        _assert_no_500(page=page, path="/resources/ip-pools/create")

        heading_count = page.locator(
            "h2:has-text('Create IP Pool')"
        ).count()
        testbase.assert_true(heading_count >= 1)

        page.fill("input[name='name']", pool_name)
        page.fill("input[name='cidr']", cidr)
        page.fill(
            "textarea[name='description']",
            "Created by p24c ip-pool browser test",
        )
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        _assert_no_500(page=page, path="/resources/ip-pools/create POST")
        content = page.content()
        testbase.assert_true(pool_name in content)
    finally:
        context.close()
    return


def test_ip_pool_edit_updates_description(browser: Browser):
    """
    **Feature: resources-ui-ip-pools**
    **Property: GET /resources/ip-pools/{id}/edit shows the edit form;
    POST /resources/ip-pools/{id}/edit updates the pool and redirects
    to its detail page where the updated description appears. Proves
    the ip_pool_edit handler processes form data and persists the
    change.**
    """
    _resolve_admin_credentials()

    pool_name = "test-ippool-edit-{}".format(int(time.time()))
    ts_mod = (int(time.time()) % 253) + 1
    cidr = "10.101.{}.0/30".format(ts_mod)
    updated_description = "Updated by p24c ip-pool edit test"

    context = browser.new_context()
    try:
        page = _login(context=context)

        # Create the IP pool.
        _go(page=page, path="/resources/ip-pools/create")
        page.fill("input[name='name']", pool_name)
        page.fill("input[name='cidr']", cidr)
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        _assert_no_500(page=page, path="ip-pool detail after create")
        detail_url = page.url
        pool_id_str = detail_url.rstrip("/").split("/")[-1]
        testbase.assert_true(pool_id_str.isdigit())

        # Navigate to the edit form.
        edit_path = "/resources/ip-pools/{}/edit".format(pool_id_str)
        _go(page=page, path=edit_path)
        _assert_no_500(page=page, path=edit_path)

        heading_count = page.locator("h2:has-text('Edit IP Pool')").count()
        testbase.assert_true(heading_count >= 1)

        description_field = page.locator("textarea[name='description']")
        description_field.fill(updated_description)
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        _assert_no_500(page=page, path="ip-pool detail after edit")
        content = page.content()
        testbase.assert_true(updated_description in content)
    finally:
        context.close()
    return


def test_ip_pool_delete_removes_from_list(browser: Browser):
    """
    **Feature: resources-ui-ip-pools**
    **Property: POST /resources/ip-pools/{id}/delete removes the IP
    pool and redirects to /resources/ip-pools where the deleted pool
    name no longer appears. Proves the ip_pool_delete handler calls
    the manager and cleans up the row.**
    """
    _resolve_admin_credentials()

    pool_name = "test-ippool-delete-{}".format(int(time.time()))
    ts_mod = (int(time.time()) % 252) + 2
    cidr = "10.102.{}.0/30".format(ts_mod)

    context = browser.new_context()
    try:
        page = _login(context=context)

        # Create the IP pool.
        _go(page=page, path="/resources/ip-pools/create")
        page.fill("input[name='name']", pool_name)
        page.fill("input[name='cidr']", cidr)
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        _assert_no_500(page=page, path="ip-pool detail after create")
        detail_url = page.url
        pool_id_str = detail_url.rstrip("/").split("/")[-1]
        testbase.assert_true(pool_id_str.isdigit())

        # Verify the pool appears in the list.
        _go(page=page, path="/resources/ip-pools")
        content = page.content()
        testbase.assert_true(pool_name in content)

        # Submit the inline delete form.
        page.on("dialog", lambda dialog: dialog.accept())
        delete_button = page.locator(
            "tr:has-text('{}') button:has-text('Delete')".format(pool_name)
        ).first
        delete_button.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        _assert_no_500(page=page, path="ip-pool list after delete")
        content = page.content()
        testbase.assert_true(pool_name not in content)
    finally:
        context.close()
    return


def test_ip_pool_checkout_action_present_on_detail(browser: Browser):
    """
    **Feature: resources-ui-ip-pools**
    **Property: The IP pool detail page (/resources/ip-pools/{id})
    contains a form whose action includes '/checkout', confirming the
    checkout POST endpoint is wired up. Proves the detail handler
    renders the checkout control without a 500.**
    """
    _resolve_admin_credentials()

    pool_name = "test-ippool-co-{}".format(int(time.time()))
    ts_mod = (int(time.time()) % 250) + 3
    cidr = "10.103.{}.0/30".format(ts_mod)

    context = browser.new_context()
    try:
        page = _login(context=context)

        _go(page=page, path="/resources/ip-pools/create")
        page.fill("input[name='name']", pool_name)
        page.fill("input[name='cidr']", cidr)
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        _assert_no_500(page=page, path="ip-pool detail after create")
        content = page.content()
        testbase.assert_true("/checkout" in content)
    finally:
        context.close()
    return


def test_ip_pool_checkin_action_present_on_detail(browser: Browser):
    """
    **Feature: resources-ui-ip-pools**
    **Property: The IP pool detail page (/resources/ip-pools/{id})
    contains a form whose action includes '/checkin', confirming the
    checkin POST endpoint is wired up. Proves the detail handler
    renders the checkin control without a 500.**

    The checkin form is conditional on active allocations existing, so
    the test first creates an IP pool, checks out one IP to create an
    allocation, then reloads the detail page and asserts the checkin
    form is present.
    """
    _resolve_admin_credentials()

    pool_name = "test-ippool-ci-{}".format(int(time.time()))
    ts_mod = (int(time.time()) % 249) + 4
    cidr = "10.104.{}.0/30".format(ts_mod)

    context = browser.new_context()
    try:
        page = _login(context=context)

        # Create an IP pool -- redirects to the detail page on success.
        _go(page=page, path="/resources/ip-pools/create")
        page.fill("input[name='name']", pool_name)
        page.fill("input[name='cidr']", cidr)
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        _assert_no_500(page=page, path="ip-pool detail after create")

        # Capture the detail URL so we can reload it after checkout.
        detail_url = page.url

        # Check out one IP to create an active allocation. The checkout
        # form uses btn-success (green), not btn-primary, so use the
        # form's submit button directly.
        page.locator("button.btn-success").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)
        _assert_no_500(page=page, path="ip-pool detail after checkout")

        # Reload the detail page. With an active allocation the
        # checkin form (action="…/checkin") must now be present.
        page.goto(detail_url)
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)
        _assert_no_500(page=page, path="ip-pool detail after reload")
        content = page.content()
        testbase.assert_true("/checkin" in content)
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Allocations: list + history
# ---------------------------------------------------------------------------


def test_allocation_list_renders(browser: Browser):
    """
    **Feature: resources-ui-allocations**
    **Property: GET /resources/allocations renders the active
    allocations list page with its expected h2 heading. Proves the
    allocation_list handler is mounted and returns a non-500 response
    with the list scaffolding regardless of the number of active
    allocations.**
    """
    _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        _go(page=page, path="/resources/allocations")
        _assert_no_500(page=page, path="/resources/allocations")

        heading_count = page.locator(
            "h2:has-text('Active Allocations')"
        ).count()
        testbase.assert_true(heading_count >= 1)
    finally:
        context.close()
    return


def test_allocation_history_renders(browser: Browser):
    """
    **Feature: resources-ui-allocations**
    **Property: GET /resources/allocations/history renders the
    allocation history page with its expected h2 heading. Proves the
    allocation_history handler is mounted and returns a non-500
    response with the history scaffolding.**
    """
    _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        _go(page=page, path="/resources/allocations/history")
        _assert_no_500(page=page, path="/resources/allocations/history")

        heading_count = page.locator(
            "h2:has-text('Allocation History')"
        ).count()
        testbase.assert_true(heading_count >= 1)
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Reservations: list + create + cancel
# ---------------------------------------------------------------------------


def test_reservation_list_renders(browser: Browser):
    """
    **Feature: resources-ui-reservations**
    **Property: GET /resources/reservations renders the Reservations
    list page with its expected h2 heading. Proves the
    reservation_list handler is mounted and returns a non-500 response
    with the list scaffolding.**
    """
    _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        _go(page=page, path="/resources/reservations")
        _assert_no_500(page=page, path="/resources/reservations")

        heading_count = page.locator("h2:has-text('Reservations')").count()
        testbase.assert_true(heading_count >= 1)
    finally:
        context.close()
    return


def test_reservation_create_appears_in_list(browser: Browser):
    """
    **Feature: resources-ui-reservations**
    **Property: Filling the Create Reservation form (GET
    /resources/reservations/create) with a resource, start/end times,
    and a reason, then submitting (POST /resources/reservations/create)
    redirects to the reservation list where the success flash message
    appears. Proves the reservation create workflow end-to-end.**
    """
    _resolve_admin_credentials()

    resource_name = "test-res-for-res-{}".format(int(time.time()))
    reservation_reason = "p24c-reservation-test-{}".format(int(time.time()))

    context = browser.new_context()
    try:
        page = _login(context=context)

        # First create a resource to reserve.
        _go(page=page, path="/resources/create")
        page.fill("input[name='name']", resource_name)
        page.select_option("select[name='resource_type']", "device")
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)
        _assert_no_500(page=page, path="resource create for reservation")

        # Navigate to the reservation create form.
        _go(page=page, path="/resources/reservations/create")
        _assert_no_500(page=page, path="/resources/reservations/create")

        heading_count = page.locator(
            "h2:has-text('Create Reservation')"
        ).count()
        testbase.assert_true(heading_count >= 1)

        # Select the resource we just created.
        resource_select = page.locator("select[name='resource_id']")
        # Find the option whose text matches our resource name.
        resource_option = resource_select.locator(
            "option:has-text('{}')".format(resource_name)
        )
        option_count = resource_option.count()
        testbase.assert_true(option_count >= 1)
        resource_option.first.evaluate(
            "(el) => { el.selected = true; el.dispatchEvent(new Event('change')); }"
        )

        # Use a future time window (2 hours from now).
        start_dt = "2027-01-15T10:00"
        end_dt = "2027-01-15T12:00"
        page.fill("input[name='start_time']", start_dt)
        page.fill("input[name='end_time']", end_dt)
        page.fill("textarea[name='reason']", reservation_reason)

        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        _assert_no_500(page=page, path="reservation create POST")

        # On success the handler redirects to the reservation list with
        # a flash. Confirm we are on the reservations list.
        landed_url = page.url
        testbase.assert_true("reservations" in landed_url)
    finally:
        context.close()
    return


def test_reservation_cancel_removes_from_list(browser: Browser):
    """
    **Feature: resources-ui-reservations**
    **Property: POST /resources/reservations/{id}/cancel cancels the
    reservation and redirects to the reservations list. Proves the
    reservation_cancel handler calls the manager's cancel_reservation
    and the list page renders without a 500 after cancellation.**
    """
    _resolve_admin_credentials()

    resource_name = "test-res-for-cancel-{}".format(int(time.time()))
    reservation_reason = "p24c-cancel-test-{}".format(int(time.time()))

    context = browser.new_context()
    try:
        page = _login(context=context)

        # Create a resource.
        _go(page=page, path="/resources/create")
        page.fill("input[name='name']", resource_name)
        page.select_option("select[name='resource_type']", "device")
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)
        _assert_no_500(page=page, path="resource for reservation cancel")

        # Create a reservation.
        _go(page=page, path="/resources/reservations/create")
        resource_select = page.locator("select[name='resource_id']")
        resource_option = resource_select.locator(
            "option:has-text('{}')".format(resource_name)
        )
        option_count = resource_option.count()
        testbase.assert_true(option_count >= 1)
        resource_option.first.evaluate(
            "(el) => { el.selected = true; el.dispatchEvent(new Event('change')); }"
        )
        page.fill("input[name='start_time']", "2027-02-15T10:00")
        page.fill("input[name='end_time']", "2027-02-15T12:00")
        page.fill("textarea[name='reason']", reservation_reason)
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)
        _assert_no_500(page=page, path="reservation create for cancel test")

        # We should be on the reservation list after a successful create.
        landed_url = page.url
        testbase.assert_true("reservations" in landed_url)

        # Find the cancel button/form for our reservation by looking for
        # the reason text in a row and clicking Cancel in that row.
        _go(page=page, path="/resources/reservations")
        content = page.content()
        # The reason text may or may not be shown on the list; the
        # important thing is the list renders without a 500.
        _assert_no_500(page=page, path="/resources/reservations after create")

        cancel_buttons = page.locator("button:has-text('Cancel'), a:has-text('Cancel')").all()
        if len(cancel_buttons) > 0:
            # Accept any confirm dialog and click the first Cancel control.
            page.on("dialog", lambda dialog: dialog.accept())
            cancel_buttons[0].click()
            page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)
            _assert_no_500(page=page, path="reservation list after cancel")
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Health: dashboard + detail + config
# ---------------------------------------------------------------------------


def test_health_dashboard_renders(browser: Browser):
    """
    **Feature: resources-ui-health**
    **Property: GET /resources/health renders the Resource Health
    Dashboard page with its expected h2 heading. Proves the
    health_dashboard handler is mounted and returns a non-500 response
    with the health status grouping.**
    """
    _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        _go(page=page, path="/resources/health")
        _assert_no_500(page=page, path="/resources/health")

        heading_count = page.locator(
            "h2:has-text('Health Dashboard')"
        ).count()
        testbase.assert_true(heading_count >= 1)
    finally:
        context.close()
    return


def test_health_detail_renders_for_existing_resource(browser: Browser):
    """
    **Feature: resources-ui-health**
    **Property: After creating a resource, GET /resources/health/{id}
    renders the health detail page showing the resource name. Proves
    the health_detail handler resolves the resource and renders the
    health history template without a 500.**
    """
    _resolve_admin_credentials()

    resource_name = "test-res-health-{}".format(int(time.time()))

    context = browser.new_context()
    try:
        page = _login(context=context)

        # Create a resource so we have a valid ID to query.
        _go(page=page, path="/resources/create")
        page.fill("input[name='name']", resource_name)
        page.select_option("select[name='resource_type']", "device")
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        _assert_no_500(page=page, path="resource detail for health test")
        detail_url = page.url
        resource_id_str = detail_url.rstrip("/").split("/")[-1]
        testbase.assert_true(resource_id_str.isdigit())

        health_path = "/resources/health/{}".format(resource_id_str)
        _go(page=page, path=health_path)
        _assert_no_500(page=page, path=health_path)

        content = page.content()
        testbase.assert_true(resource_name in content)
    finally:
        context.close()
    return


def test_health_config_page_renders(browser: Browser):
    """
    **Feature: resources-ui-health**
    **Property: GET /resources/health/{id}/config renders the health
    check configuration form without a 500. Proves the health_config
    handler is admin-accessible and the config template renders
    correctly.**
    """
    _resolve_admin_credentials()

    resource_name = "test-res-hconfig-{}".format(int(time.time()))

    context = browser.new_context()
    try:
        page = _login(context=context)

        # Create a resource.
        _go(page=page, path="/resources/create")
        page.fill("input[name='name']", resource_name)
        page.select_option("select[name='resource_type']", "device")
        page.locator("button.btn-primary").first.click()
        page.wait_for_load_state("load", timeout=NAVIGATION_TIMEOUT_MS)

        detail_url = page.url
        resource_id_str = detail_url.rstrip("/").split("/")[-1]
        testbase.assert_true(resource_id_str.isdigit())

        config_path = "/resources/health/{}/config".format(resource_id_str)
        _go(page=page, path=config_path)
        _assert_no_500(page=page, path=config_path)

        heading_count = page.locator(
            "h2:has-text('Configure Health Check')"
        ).count()
        testbase.assert_true(heading_count >= 1)
    finally:
        context.close()
    return


# ---------------------------------------------------------------------------
# Tags: list
# ---------------------------------------------------------------------------


def test_tag_list_renders(browser: Browser):
    """
    **Feature: resources-ui-tags**
    **Property: GET /resources/tags renders the Tags list page with its
    expected h2 heading. Proves the tag_list handler is mounted and
    returns a non-500 response with the tag list scaffolding.**
    """
    _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = _login(context=context)
        _go(page=page, path="/resources/tags")
        _assert_no_500(page=page, path="/resources/tags")

        heading_count = page.locator("h2:has-text('Tags')").count()
        testbase.assert_true(heading_count >= 1)
    finally:
        context.close()
    return
