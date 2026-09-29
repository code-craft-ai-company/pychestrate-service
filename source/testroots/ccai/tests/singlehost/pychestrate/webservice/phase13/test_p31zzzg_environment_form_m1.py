"""
.. module:: test_p31zzzg_environment_form_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Registering an environment offers the real kinds and their fields (ORC-17).

.. moduleauthor:: Code Craft AI LLC

The form asked for a kind name (its placeholder named a kind that does not
exist) and a JSON object whose example was invalid for the only kind there is.
It now lists the loaded kinds, shows the chosen kind's own fields (required ones
starred), builds the attributes object from them, and falls back to a typed
kind and a JSON box, with valid examples, only when the kinds cannot be listed.
The page is opened in a browser against stubbed API answers and the request the
form sends is captured.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import re

from typing import Any, Dict, List, Tuple

from playwright.sync_api import Browser

from ccai import testbase

from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    FAKE_ORIGIN,
    READY_TIMEOUT_MS,
    install_site_routes,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

PROJECT_ID: str = "0f6c2c1e-6666-4000-8000-000000000001"

K8S = {
    "kind": "k8s-cluster",
    "fields": [
        {"name": "cluster_id", "label": "Cluster id", "type": "text", "required": True, "hint": "prod-east-1"},
        {"name": "region", "label": "Region", "type": "text", "required": True, "hint": "us-east-1"},
        {"name": "api_endpoint", "label": "API endpoint", "type": "url", "required": True, "hint": "https://k8s.example.com:6443"},
        {"name": "node_pool_count", "label": "Node pools", "type": "number", "required": False, "hint": "0", "integer": True, "min": 0},
        {"name": "capability_tags", "label": "Capability tags", "type": "tags", "required": False, "hint": "gpu, arm64"},
    ],
}


def _open(browser: Browser, kinds: List[Dict[str, Any]]) -> Tuple[Any, List[Dict[str, Any]]]:
    posts: List[Dict[str, Any]] = []
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", "pyc-infra-bundle"],
        api_stubs={
            "/api/v1/projects": {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}},
            "/api/v1/projects/{}/environments".format(PROJECT_ID): {"items": [], "meta": {"page": 1, "per_page": 25, "total": 0}},
            "/api/v1/environment-kinds": {"items": kinds},
            "/api/v1/me/permissions": {"permissions": ["system:environments.read", "system:environments.write"]},
        },
    )

    def environments(route: Any) -> None:
        request = route.request
        if request.method == "POST":
            posts.append(json.loads(request.post_data))
            route.fulfill(status=201, headers={"Content-Type": "application/json"}, body=json.dumps({"environment_id": "e1", "name": "x", "kind_name": "k8s-cluster"}).encode("utf-8"))
        else:
            route.fallback()

    context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/projects/" + PROJECT_ID + r"/environments(\?.*)?$"), environments)
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + "/environments?project_id=" + PROJECT_ID)
    page.wait_for_selector('[data-role="register-toggle"]')
    page.wait_for_timeout(800)
    page.locator('[data-role="register-toggle"]').click()
    page.wait_for_selector('[data-role="register-form"]')
    page.wait_for_timeout(800)
    return page, posts


def _fill(page: Any, role: str, value: str) -> None:
    page.fill('[data-role="{}"] input'.format(role), value)


def test_the_form_offers_the_loaded_kind_and_its_fields_and_sends_them_as_attributes(browser: Browser):
    """
    **Feature: registry-fed forms (ORC-17)**
    **Property: with the kinds listed, the Kind control is a list holding
    ``k8s-cluster`` (no typed kind, no JSON box), its five fields are shown with
    the required ones starred, and submitting sends ``kind_name`` and an
    ``attrs`` object built from them: text as text, the number as a number, the
    tags as a list.**
    """
    page, posts = _open(browser, [K8S])
    try:
        options = page.evaluate("() => [...document.querySelectorAll('[data-role=\"register-kind\"] mj-option')].map((o) => o.getAttribute('value'))")
        typed_kind = page.locator('mj-text-field[data-role="register-kind"]').count()
        json_box = page.locator('[data-role="register-attrs"]').count()
        labels = page.evaluate("() => [...document.querySelectorAll('[data-role=\"register-attrs-region\"] label')].map((l) => l.firstChild.textContent.trim())")
        _fill(page, "register-name", "prod-east")
        _fill(page, "register-field-cluster_id", "prod-east-1")
        _fill(page, "register-field-region", "us-east-1")
        _fill(page, "register-field-api_endpoint", "https://k8s.example.test:6443")
        _fill(page, "register-field-node_pool_count", "3")
        _fill(page, "register-field-capability_tags", "gpu, arm64, gpu")
        page.get_by_role("button", name="Register Environment").last.click()
        page.wait_for_timeout(800)
    finally:
        page.context.close()

    testbase.assert_equal(
        (options, typed_kind, json_box, labels, posts),
        (
            ["k8s-cluster"], 0, 0,
            ["Cluster id *", "Region *", "API endpoint *", "Node pools", "Capability tags (comma-separated)"],
            [{
                "name": "prod-east", "kind_name": "k8s-cluster",
                "attrs": {"cluster_id": "prod-east-1", "region": "us-east-1", "api_endpoint": "https://k8s.example.test:6443", "node_pool_count": 3, "capability_tags": ["gpu", "arm64", "gpu"]},
            }],
        ),
    )
    return


def test_a_missing_required_field_is_named_and_nothing_is_sent(browser: Browser):
    """
    **Feature: registry-fed forms (ORC-17)**
    **Property: leaving a starred field empty shows "<label> is required." and
    sends no request.**
    """
    page, posts = _open(browser, [K8S])
    try:
        _fill(page, "register-name", "prod-east")
        _fill(page, "register-field-cluster_id", "prod-east-1")
        page.get_by_role("button", name="Register Environment").last.click()
        page.wait_for_timeout(500)
        message = page.locator('[data-role="register-status"]').inner_text()
    finally:
        page.context.close()

    testbase.assert_equal((message, posts), ("Region is required.", []))
    return


def test_without_a_kind_list_the_form_falls_back_and_its_examples_are_valid(browser: Browser):
    """
    **Feature: registry-fed forms (ORC-17)**
    **Property: when no kind can be listed the form has a typed kind and a JSON
    box; neither placeholder names a kind that does not exist ("terraform") or
    an attributes example the kind would refuse.**
    """
    page, _posts = _open(browser, [])
    try:
        kind_placeholder = page.locator('mj-text-field[data-role="register-kind"]').get_attribute("placeholder")
        json_placeholder = page.locator('[data-role="register-attrs"]').get_attribute("placeholder")
    finally:
        page.context.close()

    testbase.assert_equal((kind_placeholder, json_placeholder, "terraform" in (kind_placeholder or "")), ("kind name", "{}", False))
    return


def test_the_kind_fields_sit_on_their_own_row_at_a_readable_width(browser: Browser):
    """
    **Feature: registry-fed forms (ORC-17)**
    **Property: the kind's fields are laid out on their own full-width row below
    the name and kind (not squeezed beside them), each input is wide enough to
    read an example in, and the labels use the same type as the name field's
    (they once inherited the monospace style of the read-only attributes box).**
    """
    page, _posts = _open(browser, [K8S])
    try:
        page.wait_for_timeout(500)
        boxes = page.evaluate(
            """() => {
                const rect = (selector) => document.querySelector(selector).getBoundingClientRect();
                const form = rect('[data-role="register-form"]');
                const name = rect('[data-role="register-name"]');
                const kind = rect('[data-role="register-kind"]');
                const region = rect('[data-role="register-attrs-region"]');
                const widths = [...document.querySelectorAll('[data-role^="register-field-"]')].map((el) => el.getBoundingClientRect().width);
                const font = (el) => getComputedStyle(el).fontFamily;
                return {
                    form_width: form.width, region_width: region.width, region_top: region.top,
                    controls_bottom: Math.max(name.bottom, kind.bottom), narrowest: Math.min(...widths), count: widths.length,
                    field_font: font(document.querySelector('[data-role="register-attrs-region"] label')),
                    name_font: font(document.querySelector('[data-role="register-form"] label')),
                };
            }"""
        )
    finally:
        page.context.close()

    testbase.assert_equal(
        (
            boxes["count"],
            boxes["region_top"] >= boxes["controls_bottom"] - 1,
            boxes["region_width"] >= boxes["form_width"] * 0.95,
            boxes["narrowest"] >= 200,
            boxes["field_font"] == boxes["name_font"],
        ),
        (5, True, True, True, True),
    )
    return


def test_a_count_the_kind_would_refuse_is_named_before_anything_is_sent(browser: Browser):
    """
    **Feature: registry-fed forms (ORC-17)**
    **Property: a fractional or negative node-pool count shows "Node pools must
    be a whole number." or "Node pools must be 0 or more." and sends no
    request; a required-only registration sends just the three required
    attributes (the optional ones are left out, not sent empty).**
    """
    page, posts = _open(browser, [K8S])
    try:
        _fill(page, "register-name", "prod-east")
        _fill(page, "register-field-cluster_id", "prod-east-1")
        _fill(page, "register-field-region", "us-east-1")
        _fill(page, "register-field-api_endpoint", "https://k8s.example.test:6443")
        messages = []
        for value in ("2.5", "-1"):
            _fill(page, "register-field-node_pool_count", value)
            page.get_by_role("button", name="Register Environment").last.click()
            page.wait_for_timeout(400)
            messages.append(page.locator('[data-role="register-status"]').inner_text())
        sent_before = len(posts)
        _fill(page, "register-field-node_pool_count", "")
        page.get_by_role("button", name="Register Environment").last.click()
        page.wait_for_timeout(800)
    finally:
        page.context.close()

    testbase.assert_equal(
        (messages, sent_before, [post["attrs"] for post in posts]),
        (
            ["Node pools must be a whole number.", "Node pools must be 0 or more."], 0,
            [{"cluster_id": "prod-east-1", "region": "us-east-1", "api_endpoint": "https://k8s.example.test:6443"}],
        ),
    )
    return
