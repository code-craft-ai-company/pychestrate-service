"""
.. module:: test_p26u_orchestration_bundles_ui_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Browser regression tests for the orchestration and
               insights bundle views (September 2026 audit fixes).

.. moduleauthor:: Code Craft AI LLC

Each test loads a committed ``pyc-*`` bundle (the served
``index.js``) into Chromium through :mod:`_bundle_harness`, which
answers the bundle's REST calls from a scripted :class:`FakeApi`
and records what the view sent. No server and no network are
involved, so these run in the default single-host suite (unlike the
phase-11 / phase-12 tests, which need a live deploy).

Every scenario runs on the harness browser's own thread
(:meth:`ThreadedBrowser.run`) and returns plain values; the
assertions run in the test thread.

Sections are named after the audit finding they guard.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List, Optional

from ccai import testbase
from ccai.testbase.resourcelifespan import ResourceLifespan

from ccai.tests.singlehost.pychestrate.webservice.phase10._bundle_harness import (
    FakeApi,
    ThreadedBrowser,
    create_threaded_bundle_browser,
    mount_element,
    open_bundle_page,
    wait_for_request,
)


testbase.originate.parameter(
    create_threaded_bundle_browser,
    identifier="bundle_browser",
    life_span=ResourceLifespan.Session,
)


PROJECT_ID: str = "00000000-0000-4000-8000-0000000b0001"


# ---------------------------------------------------------------------------
# ORC-29 -- inbound webhook secrets are write-only
# ---------------------------------------------------------------------------


INTEGRATIONS_PATH: str = "/api/v1/webhooks/in/integrations"
IN_DELIVERIES_PATH: str = "/api/v1/webhooks/in/deliveries"


def _webhooks_api(*, integrations: Optional[List[Dict[str, Any]]] = None) -> FakeApi:
    api = FakeApi()
    api.respond(
        method="GET",
        path=INTEGRATIONS_PATH,
        body={"items": integrations if integrations is not None else [], "meta": {}},
    )
    api.respond(method="GET", path=IN_DELIVERIES_PATH, body={"items": [], "meta": {}})
    api.respond(
        method="POST",
        path=INTEGRATIONS_PATH,
        status=201,
        body={"webhook_id": "00000000-0000-4000-8000-0000000b0002"},
    )
    return api


def _open_webhooks(*, browser: Any, api: FakeApi) -> Any:
    context, page = open_bundle_page(browser=browser, api=api, bundle="pyc-ops-bundle")
    mount_element(page=page, tag="pyc-webhooks")
    page.wait_for_selector('[data-role="project-input"]')
    page.fill('[data-role="project-input"] input', PROJECT_ID)
    page.dispatch_event('[data-role="project-input"]', "change")
    wait_for_request(page=page, api=api, method="GET", path=INTEGRATIONS_PATH)
    rtnval = (context, page)
    return rtnval


def _submit_inbound_form(*, page: Any, secret: str) -> None:
    page.click('[data-role="inbound-create-toggle"]')
    page.wait_for_selector('[data-role="inbound-form"]')
    page.fill('[data-role="inbound-provider"] input', "generic")
    page.fill('[data-role="inbound-hook"] input', "ops")
    page.fill('[data-role="inbound-secret"] input', secret)
    page.click('[data-role="inbound-submit"]')
    return


def test_webhooks_create_sends_the_shared_secret_as_write_only_secret(
        bundle_browser: ThreadedBrowser
    ):
    """
    **Feature: audit ORC-29 / pyc-ops-bundle**
    **Property: the inbound create form sends the typed shared secret
    in the write-only 'secret' field, never as 'secret_ref'.**
    """
    api = _webhooks_api()

    def _scenario(browser: Any) -> Any:
        context, page = _open_webhooks(browser=browser, api=api)
        try:
            _submit_inbound_form(page=page, secret="k3y-orc29")
            posted = wait_for_request(
                page=page, api=api, method="POST", path=INTEGRATIONS_PATH,
            )
        finally:
            context.close()
        rtnval = posted[0].body
        return rtnval

    body = bundle_browser.run(_scenario)
    testbase.assert_equal(
        (body.get("secret"), "secret_ref" in body),
        ("k3y-orc29", False),
    )
    return


def test_webhooks_create_clears_the_secret_field_after_sending(
        bundle_browser: ThreadedBrowser
    ):
    """
    **Feature: audit ORC-29 / pyc-ops-bundle**
    **Property: the shared-secret field is emptied once the create
    request has been sent, so the key does not linger in the page.**
    """
    api = _webhooks_api()

    def _scenario(browser: Any) -> Any:
        context, page = _open_webhooks(browser=browser, api=api)
        try:
            _submit_inbound_form(page=page, secret="k3y-orc29")
            wait_for_request(page=page, api=api, method="POST", path=INTEGRATIONS_PATH)
            page.wait_for_timeout(300)
            rtnval = page.evaluate(
                "() => document.querySelector('[data-role=\"inbound-secret\"]').value",
            )
        finally:
            context.close()
        return rtnval

    remaining = bundle_browser.run(_scenario)
    testbase.assert_equal(remaining, "")
    return


def test_webhooks_table_shows_vault_status_instead_of_the_secret(
        bundle_browser: ThreadedBrowser
    ):
    """
    **Feature: audit ORC-29 / pyc-ops-bundle**
    **Property: the integrations table marks a configured secret as
    'in vault' from secret_configured.**
    """
    api = _webhooks_api(integrations=[{
        "webhook_id": "00000000-0000-4000-8000-0000000b0003",
        "project_id": PROJECT_ID,
        "provider": "generic",
        "hook_name": "ops",
        "secret_ref": "webhooks.in.generic.ops.00000000-0000-4000-8000-0000000b0003.secret",
        "secret_configured": True,
        "enabled": True,
        "receiver_path": "/api/v1/webhooks/in/generic/ops",
    }])

    def _scenario(browser: Any) -> Any:
        context, page = _open_webhooks(browser=browser, api=api)
        try:
            page.wait_for_selector('[data-role="integration-secret"]', timeout=5000)
            rtnval = page.inner_text('[data-role="integration-secret"]')
        finally:
            context.close()
        return rtnval

    chip_text = bundle_browser.run(_scenario)
    testbase.assert_equal(chip_text.strip(), "in vault")
    return


def test_webhooks_create_failure_shows_the_server_detail(
        bundle_browser: ThreadedBrowser
    ):
    """
    **Feature: audit ORC-29 / pyc-ops-bundle**
    **Property: a refused create surfaces the server's problem detail
    (here: the caller may not store project secrets) instead of a bare
    'check the fields'.**
    """
    api = _webhooks_api()
    api.respond(
        method="POST",
        path=INTEGRATIONS_PATH,
        status=403,
        body={
            "type": "about:blank",
            "title": "Forbidden",
            "status": 403,
            "detail": "You may not store secrets for this project.\nPROJECT_ID: x",
        },
    )

    def _scenario(browser: Any) -> Any:
        context, page = _open_webhooks(browser=browser, api=api)
        try:
            _submit_inbound_form(page=page, secret="k3y-orc29")
            page.wait_for_selector('[data-role="toast"][data-tone="error"]', timeout=5000)
            rtnval = page.inner_text('[data-role="toast"][data-tone="error"]')
        finally:
            context.close()
        return rtnval

    toast_text = bundle_browser.run(_scenario)
    testbase.assert_equal(
        "You may not store secrets for this project." in toast_text, True,
    )
    return
