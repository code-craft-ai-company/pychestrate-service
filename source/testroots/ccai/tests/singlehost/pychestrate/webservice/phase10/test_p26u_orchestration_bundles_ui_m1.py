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


# ---------------------------------------------------------------------------
# ORC-06 -- "Import from testbase" sends what the importer reads
# ---------------------------------------------------------------------------


PROJECTS_PATH: str = "/api/v1/projects"
CATALOG_PATH: str = "/api/v1/projects/{}/test-catalog".format(PROJECT_ID)
CATALOG_IMPORT_PATH: str = "/api/v1/projects/{}/test-catalog:import".format(PROJECT_ID)


def _catalog_api(*, import_status: int = 202, import_body: Any = None) -> FakeApi:
    api = FakeApi()
    api.respond(
        method="GET",
        path=PROJECTS_PATH,
        body={"items": [{"project_id": PROJECT_ID, "slug": "p", "display_name": "P"}], "meta": {"total": 1}},
    )
    api.respond(method="GET", path=CATALOG_PATH, body={"items": [], "meta": {"total": 0}})
    api.respond(
        method="POST",
        path=CATALOG_IMPORT_PATH,
        status=import_status,
        body=import_body if import_body is not None else {
            "importer_tag": "testbase-project",
            "started_at": "2026-09-22T00:00:00+00:00",
            "entries_imported": 2,
            "entries_retired": 0,
            "errors": [],
        },
    )
    return api


def _open_catalog_import_form(*, browser: Any, api: FakeApi) -> Any:
    context, page = open_bundle_page(browser=browser, api=api, bundle="pyc-catalog-bundle")
    mount_element(page=page, tag="pyc-test-catalog")
    wait_for_request(page=page, api=api, method="GET", path=CATALOG_PATH)
    page.click('[data-role="import-toggle"]')
    page.wait_for_selector('[data-role="import-form"]')
    rtnval = (context, page)
    return rtnval


def _catalog_import_status(*, page: Any) -> Any:
    page.wait_for_function(
        "() => { const s = document.querySelector('[data-role=\"import-status\"]');"
        " return s !== null && s.textContent.length > 0"
        " && s.textContent.indexOf('running') < 0; }",
        timeout=5000,
    )
    rtnval = page.evaluate(
        "() => { const s = document.querySelector('[data-role=\"import-status\"]');"
        " return {text: s.textContent, tone: s.getAttribute('data-tone')}; }",
    )
    return rtnval


def test_catalog_import_sends_the_pasted_includes(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-06 / pyc-catalog-bundle**
    **Property: the import form posts the pasted includes (one per line)
    with the testbase root and branch in the source the importer reads.**
    """
    api = _catalog_api()

    def _scenario(browser: Any) -> Any:
        context, page = _open_catalog_import_form(browser=browser, api=api)
        try:
            page.fill(
                '[data-role="import-includes"] textarea',
                "ccai.tests.singlehost.feature.test_alpha\n\nccai.tests.singlehost.feature.test_beta\n",
            )
            page.fill('[data-role="import-root"] input', "source/testroots/ccai")
            page.fill('[data-role="import-ref"] input', "main")
            page.click('[data-role="import-submit"]')
            posted = wait_for_request(page=page, api=api, method="POST", path=CATALOG_IMPORT_PATH)
        finally:
            context.close()
        rtnval = posted[0].body
        return rtnval

    body = bundle_browser.run(_scenario)
    testbase.assert_equal(
        body,
        {
            "importer_tag": "testbase-project",
            "source": {
                "includes": [
                    "ccai.tests.singlehost.feature.test_alpha",
                    "ccai.tests.singlehost.feature.test_beta",
                ],
                "root": "source/testroots/ccai",
                "ref": "main",
            },
        },
    )
    return


def test_catalog_import_reports_zero_imported_as_a_failure(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-06 / pyc-catalog-bundle**
    **Property: a summary with entries_imported 0 is shown as "Nothing
    was imported" in the error tone, never as "Import complete".**
    """
    api = _catalog_api(import_body={
        "importer_tag": "testbase-project",
        "started_at": "2026-09-22T00:00:00+00:00",
        "entries_imported": 0,
        "entries_retired": 0,
        "errors": [],
    })

    def _scenario(browser: Any) -> Any:
        context, page = _open_catalog_import_form(browser=browser, api=api)
        try:
            page.fill('[data-role="import-includes"] textarea', "ccai.tests.singlehost.feature.test_alpha")
            page.click('[data-role="import-submit"]')
            rtnval = _catalog_import_status(page=page)
        finally:
            context.close()
        return rtnval

    status = bundle_browser.run(_scenario)
    testbase.assert_equal(
        (status["text"].startswith("Nothing was imported"), status["tone"]),
        (True, "error"),
    )
    return


def test_catalog_import_shows_the_server_refusal(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-06 / pyc-catalog-bundle**
    **Property: a refused import shows the server's reason.**
    """
    api = _catalog_api(
        import_status=422,
        import_body={
            "type": "about:blank",
            "title": "Validation Failed",
            "status": 422,
            "detail": "Nothing to import: the source lists no tests.",
            "entries_imported": 0,
        },
    )

    def _scenario(browser: Any) -> Any:
        context, page = _open_catalog_import_form(browser=browser, api=api)
        try:
            page.fill('[data-role="import-includes"] textarea', "ccai.tests.singlehost.feature.test_alpha")
            page.click('[data-role="import-submit"]')
            rtnval = _catalog_import_status(page=page)
        finally:
            context.close()
        return rtnval

    status = bundle_browser.run(_scenario)
    testbase.assert_equal(
        status["text"],
        "Import failed: Nothing to import: the source lists no tests.",
    )
    return


def test_catalog_import_requires_an_include(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-06 / pyc-catalog-bundle**
    **Property: submitting the import form without an include sends
    nothing and asks for one.**
    """
    api = _catalog_api()

    def _scenario(browser: Any) -> Any:
        context, page = _open_catalog_import_form(browser=browser, api=api)
        try:
            page.fill('[data-role="import-root"] input', "source/testroots/ccai")
            page.click('[data-role="import-submit"]')
            status = _catalog_import_status(page=page)
            posted = api.requests_for(method="POST", path=CATALOG_IMPORT_PATH)
        finally:
            context.close()
        rtnval = (status["text"], len(posted))
        return rtnval

    outcome = bundle_browser.run(_scenario)
    testbase.assert_equal(
        outcome,
        ("List at least one testbase include to import.", 0),
    )
    return
