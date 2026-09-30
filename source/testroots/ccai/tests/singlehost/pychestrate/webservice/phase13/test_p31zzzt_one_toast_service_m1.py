"""
.. module:: test_p31zzzt_one_toast_service_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: One toast service for the bundle views (ORC-41).

.. moduleauthor:: Code Craft AI LLC

Fourteen views built their own toast and the copies disagreed: some stacked and some
replaced, only two marked their region as a live region (so a failure was never
announced to a screen reader elsewhere), a message stayed until dismissed, and it
stayed when the person moved to another tab. ``shared/toast.js`` is now the one
service: a single toast at a time, announced (an error is an ``alert``), a plain
success going away by itself, and cleared when a view changes what it shows. The
helper is tested on its own in a browser, a static check keeps the per-view copies
out, and two real views prove the wiring.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from typing import Any, Dict, List

from playwright.sync_api import Browser

from ccai import testbase

from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES

from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    FAKE_ORIGIN,
    READY_TIMEOUT_MS,
    install_site_routes,
    open_fixture_page,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

HELPER = "async (script) => { const m = await import('/static/javascript/shared/toast.js'); const region = document.getElementById('region'); return await (new Function('m', 'region', 'return (async () => {' + script + '})()'))(m, region); }"


def _helper_page(browser: Browser) -> Any:
    return open_fixture_page(browser, body_html='<div id="region"></div>', **DESKTOP)


def test_one_toast_at_a_time_and_announced(browser: Browser):
    """
    **Feature: one toast service (ORC-41)**
    **Property: the region becomes a polite live region; a success or neutral toast
    is a ``status`` and an error toast an ``alert``; showing a second toast replaces
    the first (one child); the dismiss button removes it; the markup keeps the
    ``data-role``, ``data-tone`` and class names the views' stylesheets use.**
    """
    page = _helper_page(browser)
    try:
        info = page.evaluate(
            HELPER,
            """
            m.show_toast(region, 'Saved.', 'ok', {class_prefix: 'pyc-x', auto_dismiss_ms: 0});
            const first = {role: region.firstElementChild.getAttribute('role'), region_role: region.getAttribute('role'), live: region.getAttribute('aria-live'),
                           tone: region.firstElementChild.getAttribute('data-tone'), data_role: region.firstElementChild.getAttribute('data-role'), cls: region.firstElementChild.className,
                           message_cls: region.firstElementChild.firstElementChild.className};
            m.show_toast(region, 'Failed.', 'error', {class_prefix: 'pyc-x', auto_dismiss_ms: 0});
            const second = {count: region.children.length, role: region.firstElementChild.getAttribute('role'), text: region.firstElementChild.firstElementChild.textContent};
            region.querySelector('mj-button').click();
            return {first, second, after_dismiss: region.children.length, label: 'Dismiss'};
            """,
        )
    finally:
        page.context.close()

    testbase.assert_equal(
        (info["first"], info["second"], info["after_dismiss"]),
        (
            {"role": "status", "region_role": "status", "live": "polite", "tone": "ok", "data_role": "toast", "cls": "pyc-x__toast", "message_cls": "pyc-x__toast-message"},
            {"count": 1, "role": "alert", "text": "Failed."},
            0,
        ),
    )
    return


def test_a_plain_success_goes_away_by_itself_and_an_error_or_a_link_does_not(browser: Browser):
    """
    **Feature: one toast service (ORC-41)**
    **Property: after its delay a success toast is gone; an error toast and a toast
    with a link are still there (a person must read the first and may still want
    the second); a newer toast is not removed by an older toast's timer.**
    """
    page = _helper_page(browser)
    try:
        info = page.evaluate(
            HELPER,
            """
            const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
            const seen = {};
            m.show_toast(region, 'ok', 'ok', {auto_dismiss_ms: 120});
            await wait(350);
            seen.success = region.children.length;
            m.show_toast(region, 'bad', 'error', {auto_dismiss_ms: 120});
            await wait(350);
            seen.error = region.children.length;
            m.show_toast(region, 'started', 'ok', {auto_dismiss_ms: 120, link: {href: '/runs/1', text: 'View run', data_role: 'run-link'}});
            await wait(350);
            seen.link = [region.children.length, region.querySelector('a').getAttribute('href'), region.querySelector('a').getAttribute('data-role')];
            m.show_toast(region, 'old', 'ok', {auto_dismiss_ms: 150});
            await wait(60);
            m.show_toast(region, 'new', 'ok', {auto_dismiss_ms: 2000});
            await wait(300);
            seen.newer_survives = region.firstElementChild ? region.firstElementChild.firstElementChild.textContent : null;
            m.clear_toasts(region);
            seen.cleared = region.children.length;
            return seen;
            """,
        )
    finally:
        page.context.close()

    testbase.assert_equal(
        info,
        {"success": 0, "error": 1, "link": [1, "/runs/1", "run-link"], "newer_survives": "new", "cleared": 0},
    )
    return


def test_no_bundle_view_builds_its_own_toast():
    """
    **Feature: one toast service (ORC-41)**
    **Property: no bundle source builds a ``__toast`` element itself (every view goes
    through ``shared/toast.js``), and none keeps a stack limit.**
    """
    root = os.path.join(SITE_DIRECTORIES.DIR_STATIC, "javascript")
    own: List[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        if "pyc-mj-lib" in dirpath:
            continue
        for name in filenames:
            if not name.endswith(".js") or name == "index.js":
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            if re.search(r'classList\.add\("pyc-[a-z-]+__toast"\)', text) or "TOAST_STACK_LIMIT" in text:
                own.append(os.path.relpath(path, root))

    testbase.assert_equal(own, [])
    return


def _stubbed(browser: Browser, path: str, bundle: str, stubs: Dict[str, Any], status_for_delete: int = 0) -> Any:
    context = browser.new_context(**DESKTOP)
    install_site_routes(context, bundle_names=["pyc-site-shell", bundle], api_stubs=stubs)
    if status_for_delete != 0:
        context.route(
            re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/projects/[^/]+/slos/[^/?]+(\?.*)?$"),
            lambda route: route.fulfill(status=status_for_delete, headers={"Content-Type": "application/json"}, body=b"{}") if route.request.method == "DELETE" else route.fallback(),
        )
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + path)
    return page


def test_a_real_view_announces_a_failure_and_keeps_one_toast(browser: Browser):
    """
    **Feature: one toast service (ORC-41)**
    **Property: on the SLO list, two refused deletes in a row leave exactly one
    toast (an ``alert``) in a region that is a live region; before this the SLO
    view's region had no live-region attributes at all.**
    """
    project = "0f6c2c1e-ffff-4000-8000-000000000001"
    slo = {"slo_id": "0f6c2c1e-ffff-4000-8000-0000000000a1", "project_id": project, "name": "API", "kind": "availability_ratio", "target": 0.999, "window_seconds": 86400, "definition_config": {}}
    page = _stubbed(
        browser, "/slos?project_id=" + project, "pyc-metrics-bundle",
        {"/api/v1/projects": {"items": [{"project_id": project, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}}, "/api/v1/projects/{}/slos".format(project): {"items": [slo], "meta": {"total": 1}}},
        status_for_delete=403,
    )
    try:
        page.wait_for_selector('[data-role="delete-slo"]')
        page.wait_for_timeout(500)
        for _round in range(2):
            page.locator('[data-role="delete-slo"]').first.click()
            page.wait_for_selector("dialog.pyc-confirm[open]")
            page.locator('[data-role="confirm-accept"]').click()
            page.wait_for_timeout(700)
        state = page.evaluate(
            """() => {
                const region = document.querySelector('[data-role="toast-region"]');
                return {count: region.children.length, region_role: region.getAttribute('role'), live: region.getAttribute('aria-live'),
                        role: region.firstElementChild.getAttribute('role'), tone: region.firstElementChild.getAttribute('data-tone')};
            }"""
        )
    finally:
        page.context.close()

    testbase.assert_equal(state, {"count": 1, "region_role": "status", "live": "polite", "role": "alert", "tone": "error"})
    return


def test_a_toast_does_not_follow_the_person_to_the_other_webhooks_tab(browser: Browser):
    """
    **Feature: one toast service (ORC-41)**
    **Property: a toast shown on the Inbound tab is gone after moving to Outbound.**
    """
    page = _stubbed(
        browser, "/webhooks", "pyc-ops-bundle",
        {"/api/v1/webhooks/in/integrations": {"items": [], "meta": {"total": 0}}, "/api/v1/webhooks/out/subscriptions": {"items": [], "meta": {"total": 0}}},
    )
    try:
        page.wait_for_selector('pyc-webhooks [data-role="tab-outbound"]')
        page.wait_for_timeout(800)
        page.evaluate("() => document.querySelector('pyc-webhooks')._show_toast('Integration disabled.', 'ok')")
        before = page.locator('[data-role="toast"]').count()
        page.locator('[data-role="tab-outbound"]').click()
        page.wait_for_timeout(500)
        after = page.locator('[data-role="toast"]').count()
    finally:
        page.context.close()

    testbase.assert_equal((before, after), (1, 0))
    return
