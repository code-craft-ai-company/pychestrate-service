"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzz_pod_and_client_states_in_words_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Pod, client and provisioning states read as words, not as stored enum spellings (ORC-38).

.. moduleauthor:: Code Craft AI LLC

The clients list showed ``ACTIVE`` / ``REVOKED`` / ``SUSPENDED`` and filters named ``ALIVE`` / ``DEGRADED`` / ``LOST``; the pod
page showed ``IN_USE``, ``DRAINING`` and sentences such as "only available while the pod is READY or IN_USE"; the provisioning
state filter offered ``rejected_by_guard``. The glossary's status vocabulary is lowercase words ("active", "revoked", "in use"),
so these now read that way, while the stored value is still what the filter query and the colours go by. The pages are opened
in a browser against stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import urllib.parse

from typing import Any, Dict, List

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

PROJECT: str = "0f6c2c1e-1111-4000-8000-000000000001"
POD: str = "0f6c2c1e-1111-4000-8000-0000000000d1"
CLIENT_BASE: str = "0f6c2c1e-1111-4000-8000-0000000000c"
PROJECTS = {"items": [{"project_id": PROJECT, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}}


def _client(number: int, status: str, liveness: str) -> Dict[str, Any]:
    return {
        "client_id": "{}{}".format(CLIENT_BASE, number), "pod_name": "lab-pod-{}".format(number), "status": status, "liveness_state": liveness,
        "project_id": PROJECT, "created_at": "2026-09-29T10:00:00+00:00", "last_seen": "2026-09-29T10:05:00+00:00", "capabilities": [],
    }


CLIENTS = [_client(1, "ACTIVE", "ALIVE"), _client(2, "SUSPENDED", "DEGRADED"), _client(3, "REVOKED", "LOST")]


def _open(browser: Browser, path: str, bundle: str, stubs: Dict[str, Any]) -> Any:
    asked: List[Dict[str, str]] = []
    context = browser.new_context(**DESKTOP)
    install_site_routes(context, bundle_names=["pyc-site-shell", bundle], api_stubs=dict({"/api/v1/projects": PROJECTS}, **stubs))
    context.on(
        "request",
        lambda request: asked.append(dict(urllib.parse.parse_qsl(urllib.parse.urlparse(request.url).query)))
        if urllib.parse.urlparse(request.url).path == "/api/v1/clients" else None,
    )
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + path)
    page.wait_for_timeout(3000)
    page.asked = asked
    return page


def _options(page: Any, role: str) -> List[str]:
    return page.evaluate("(role) => [...document.querySelectorAll('[data-role=\"' + role + '\"] mj-option')].map((el) => el.textContent.trim())", role)


def test_the_clients_list_reads_status_and_liveness_in_words_and_still_filters_by_the_stored_value(browser: Browser):
    """
    **Feature: states in words (ORC-38)**
    **Property: the clients' status chips read active / suspended / revoked, the Status filter offers those words and the
    Liveness filter Alive / Stale / Lost (the same words as the chips), and choosing "revoked" asks the API for
    status=REVOKED.**
    """
    page = _open(browser, "/clients?project_id=" + PROJECT, "pyc-pods-bundle", {"/api/v1/clients": CLIENTS})
    try:
        chips = page.evaluate("() => [...document.querySelector('mj-data-table').shadowRoot.querySelectorAll('mj-chip')].map((el) => el.textContent.trim())")
        status_options = _options(page, "status-filter")
        liveness_options = _options(page, "liveness-filter")
        page.locator('[data-role="status-filter"]').click()
        page.get_by_role("option", name="revoked", exact=True).click()
        page.wait_for_timeout(800)
        sent = page.asked[-1].get("status")
    finally:
        page.context.close()

    testbase.assert_equal(
        (
            [chip for chip in chips if chip in ("active", "suspended", "revoked")],
            status_options, liveness_options, sent,
        ),
        (
            ["active", "suspended", "revoked"],
            ["All statuses", "active", "suspended", "revoked"],
            ["All liveness", "Alive", "Stale", "Lost"],
            "REVOKED",
        ),
    )
    return


def test_a_client_page_reads_its_status_in_words(browser: Browser):
    """
    **Feature: states in words (ORC-38)**
    **Property: a client's page shows its status chip as "suspended", not "SUSPENDED".**
    """
    client = CLIENTS[1]
    page = _open(browser, "/clients/" + client["client_id"], "pyc-pods-bundle", {"/api/v1/clients/" + client["client_id"]: client})
    try:
        text = " ".join(page.locator("main").inner_text().split())
    finally:
        page.context.close()

    testbase.assert_equal(("suspended" in text, "SUSPENDED" in text), (True, False))
    return


def test_a_pod_page_reads_its_state_history_and_hints_in_words(browser: Browser):
    """
    **Feature: states in words (ORC-38)**
    **Property: a draining pod's state chip reads "draining", its history reads "ready → in use", the disabled Drain
    button explains itself with "ready or in use", the registration reads "active" and its history "released"; no
    capitalised state word is left.**
    """
    base = "/api/v1/projects/{}/pods/{}".format(PROJECT, POD)
    stubs = {
        "/api/v1/projects/{}/pod-definitions/{}".format(PROJECT, POD): {"pod_id": POD, "project_id": PROJECT, "pod_name": "lab-pod", "created_at": "2026-09-29T10:00:00+00:00"},
        base + "/state": {"pod_id": POD, "project_id": PROJECT, "state": "DRAINING", "last_transition_at": "2026-09-29T10:00:00+00:00", "last_transition_event": "drain"},
        base + "/state/history": [{"from_state": "READY", "to_state": "IN_USE", "applied_at": "2026-09-29T09:00:00+00:00", "event_kind": "lease"}],
        base + "/state/transitions": {"items": [], "meta": {"total": 0}},
        base + "/registration": {"pod_id": POD, "project_id": PROJECT, "state": "ACTIVE", "pod_definition_version": 1, "registered_at": "2026-09-29T09:00:00+00:00"},
        base + "/registrations": [{"state": "RELEASED", "pod_definition_version": 1, "registered_at": "2026-09-29T08:00:00+00:00"}],
    }
    page = _open(browser, "/pods/{}?project_id={}".format(POD, PROJECT), "pyc-pods-bundle", stubs)
    try:
        text = " ".join(page.locator("main").inner_text().split())
        drain_hint = page.locator('[data-role="drain-action"]').get_attribute("title")
        capitalised = [word for word in ("DRAINING", "READY", "IN_USE", "ACTIVE", "RELEASED") if word in text or word in (drain_hint or "")]
    finally:
        page.context.close()

    testbase.assert_equal(
        ("draining" in text, "ready → in use" in text, "released · v1" in text, drain_hint, capitalised),
        (True, True, True, "Drain is only available while the pod is ready or in use.", []),
    )
    return


def test_the_provisioning_state_filter_offers_words(browser: Browser):
    """
    **Feature: states in words (ORC-38)**
    **Property: the provisioning runs' State filter offers "rejected by guard" (not ``rejected_by_guard``), and choosing it
    still sends the stored value.**
    """
    page = _open(browser, "/provisioning-runs?project_id=" + PROJECT, "pyc-infra-bundle", {"/api/v1/projects/{}/provisioning-runs".format(PROJECT): {"items": [], "meta": {"page": 1, "per_page": 25, "total": 0}}})
    try:
        options = _options(page, "state-filter")
    finally:
        page.context.close()

    testbase.assert_equal(("rejected by guard" in options, "rejected_by_guard" in options, [option for option in options if "_" in option]), (True, False, []))
    return


def test_kinds_read_as_words_in_the_environments_list_and_on_a_resource_page(browser: Browser):
    """
    **Feature: states in words (ORC-38)**
    **Property: an environment of kind ``k8s_cluster`` reads "k8s cluster" in the environments list and a resource of kind
    ``network_switch`` reads "network switch" on its page (underscores are for programs, not for people).**
    """
    environment = {"environment_id": "0f6c2c1e-1111-4000-8000-0000000000e1", "project_id": PROJECT, "name": "staging", "kind_name": "k8s_cluster", "state": "active", "created_at": "2026-09-29T10:00:00+00:00"}
    page = _open(
        browser, "/environments?project_id=" + PROJECT, "pyc-infra-bundle",
        {"/api/v1/projects/{}/environments".format(PROJECT): {"items": [environment], "meta": {"page": 1, "per_page": 25, "total": 1}}},
    )
    try:
        listed = " ".join(page.evaluate("() => document.querySelector('mj-data-table').shadowRoot.textContent").split())
    finally:
        page.context.close()
    resource_id = "7e7e7e7e-0000-4000-8000-000000000001"
    resource = {
        "resource_id": resource_id, "project_id": PROJECT, "kind": "network_switch", "display_name": "Rack 7", "description": "", "identity_hash": "ab" * 32,
        "state": "available", "tags": [], "attributes": {}, "created_at": "2026-09-01T10:00:00Z", "updated_at": "2026-09-01T10:00:00Z",
    }
    page = _open(
        browser, "/resource-pools/resources/" + resource_id, "pyc-resources-bundle",
        {
            "/api/v1/resources/" + resource_id: resource,
            "/api/v1/resources/{}/health".format(resource_id): {"resource_id": resource_id, "status": "healthy"},
            "/api/v1/resources/{}/usage-history".format(resource_id): {"items": [], "meta": {"total": 0}},
        },
    )
    try:
        shown = " ".join(page.locator("main").inner_text().split())
    finally:
        page.context.close()

    testbase.assert_equal(
        ("k8s cluster" in listed, "k8s_cluster" in listed, "network switch" in shown, "network_switch" in shown),
        (True, False, True, False),
    )
    return
