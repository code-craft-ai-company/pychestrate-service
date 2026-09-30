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


# ---------------------------------------------------------------------------
# ORC-14 -- the failed-run rate is not called a flake rate
# ---------------------------------------------------------------------------


TEST_METRICS_PATH: str = "/api/v1/projects/{}/test-metrics".format(PROJECT_ID)


def _test_metrics_api() -> FakeApi:
    api = FakeApi()
    api.respond(
        method="GET",
        path=PROJECTS_PATH,
        body={"items": [{"project_id": PROJECT_ID, "slug": "p", "display_name": "P"}], "meta": {"total": 1}},
    )
    api.respond(
        method="GET",
        path=TEST_METRICS_PATH,
        body={
            "project_id": PROJECT_ID,
            "summary": {
                "run_count": 4,
                "tests_total": 40,
                "tests_passed": 36,
                "tests_failed": 4,
                "tests_skipped": 0,
                "tests_errored": 0,
                "pass_rate": 0.9,
                "fail_rate": 0.1,
                "runs_with_failures": 1,
                "failed_run_rate": 0.25,
                "average_run_duration_seconds": 60.0,
            },
            "recent_runs": [],
            "meta": {"run_limit": 500, "run_count": 4},
        },
    )
    return api


def test_test_metrics_card_is_labelled_failed_run_rate(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-14 / pyc-metrics-bundle**
    **Property: the headline card reads "Failed-run rate" and shows the
    API's failed_run_rate (25%), and no card is called a flake rate.**
    """
    api = _test_metrics_api()

    def _scenario(browser: Any) -> Any:
        context, page = open_bundle_page(browser=browser, api=api, bundle="pyc-metrics-bundle")
        try:
            mount_element(page=page, tag="pyc-test-metrics")
            page.wait_for_selector('[data-role="failed-run-rate"]', timeout=5000)
            rtnval = page.evaluate(
                "() => { const card = document.querySelector('[data-role=\"failed-run-rate\"]');"
                " return {"
                " label: card.querySelector('.pyc-metrics__card-label').textContent,"
                " value: card.querySelector('.pyc-metrics__card-value').textContent,"
                " labels: Array.from(document.querySelectorAll('.pyc-metrics__card-label'))"
                ".map((node) => node.textContent) }; }",
            )
        finally:
            context.close()
        return rtnval

    shown = bundle_browser.run(_scenario)
    flake_labels = [label for label in shown["labels"] if "flake" in label.lower()]
    testbase.assert_equal(
        (shown["label"], shown["value"], flake_labels),
        ("Failed-run rate", "25%", []),
    )
    return


# ---------------------------------------------------------------------------
# ORC-28 -- guards are listed through an environment picker
# ---------------------------------------------------------------------------


ENVIRONMENTS_PATH: str = "/api/v1/projects/{}/environments".format(PROJECT_ID)
GUARDS_PATH: str = "/api/v1/projects/{}/blast-radius-guards".format(PROJECT_ID)
ENVIRONMENT_PROD: str = "00000000-0000-4000-8000-0000000e0001"
ENVIRONMENT_STAGE: str = "00000000-0000-4000-8000-0000000e0002"


def _guards_api(*, environments: Optional[List[Dict[str, Any]]] = None, environments_status: int = 200) -> FakeApi:
    api = FakeApi()
    api.respond(
        method="GET",
        path=PROJECTS_PATH,
        body={"items": [{"project_id": PROJECT_ID, "slug": "p", "display_name": "P"}], "meta": {"total": 1}},
    )
    if environments is None:
        environments = [
            {"environment_id": ENVIRONMENT_PROD, "name": "prod"},
            {"environment_id": ENVIRONMENT_STAGE, "name": "stage"},
        ]
    api.respond(
        method="GET",
        path=ENVIRONMENTS_PATH,
        status=environments_status,
        body={"items": environments, "meta": {"total": len(environments)}},
    )
    api.respond(method="GET", path=GUARDS_PATH, body={"items": [], "meta": {"total": 0}})
    return api


def _open_guards(*, browser: Any, api: FakeApi) -> Any:
    context, page = open_bundle_page(browser=browser, api=api, bundle="pyc-infra-bundle")
    mount_element(page=page, tag="pyc-guards")
    wait_for_request(page=page, api=api, method="GET", path=ENVIRONMENTS_PATH)
    rtnval = (context, page)
    return rtnval


def test_guards_environment_control_lists_the_projects_environments(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-28 / pyc-infra-bundle**
    **Property: the guards view offers the project's environments in a
    picker instead of an "optional" free-text id.**
    """
    api = _guards_api()

    def _scenario(browser: Any) -> Any:
        context, page = _open_guards(browser=browser, api=api)
        try:
            page.wait_for_selector('[data-role="environment-filter"]', timeout=5000)
            rtnval = page.evaluate(
                "() => { const c = document.querySelector('[data-role=\"environment-filter\"]');"
                " return {tag: c.tagName.toLowerCase(),"
                " values: Array.from(c.querySelectorAll('mj-option')).map((o) => o.getAttribute('value'))}; }",
            )
        finally:
            context.close()
        return rtnval

    control = bundle_browser.run(_scenario)
    testbase.assert_equal(
        control,
        {"tag": "mj-select", "values": [ENVIRONMENT_PROD, ENVIRONMENT_STAGE]},
    )
    return


def test_guards_list_is_requested_with_a_complete_environment_id(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-28 / pyc-infra-bundle**
    **Property: the guards list loads for the first environment without
    the user typing an id, and the request carries its full UUID.**
    """
    api = _guards_api()

    def _scenario(browser: Any) -> Any:
        context, page = _open_guards(browser=browser, api=api)
        try:
            requests = wait_for_request(page=page, api=api, method="GET", path=GUARDS_PATH)
        finally:
            context.close()
        rtnval = requests[0].query.get("environment_id")
        return rtnval

    sent = bundle_browser.run(_scenario)
    testbase.assert_equal(sent, ENVIRONMENT_PROD)
    return


def test_guards_partial_typed_environment_id_is_not_sent(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-28 / pyc-infra-bundle**
    **Property: when the environment list cannot be read and the user
    types a partial id, no list request is sent and the view asks for a
    complete environment id.**
    """
    api = _guards_api(environments_status=403)

    def _scenario(browser: Any) -> Any:
        context, page = _open_guards(browser=browser, api=api)
        try:
            page.wait_for_selector('[data-role="environment-filter"] input', timeout=5000)
            page.fill('[data-role="environment-filter"] input', "00000000-0000")
            page.dispatch_event('[data-role="environment-filter"]', "change")
            page.wait_for_selector('[data-role="error-state"]', timeout=5000)
            message = page.inner_text('[data-role="error-state"]')
            sent = api.requests_for(method="GET", path=GUARDS_PATH)
        finally:
            context.close()
        rtnval = (message, len(sent))
        return rtnval

    outcome = bundle_browser.run(_scenario)
    testbase.assert_equal(
        outcome,
        ("Enter a complete environment id (a UUID).", 0),
    )
    return


def test_guards_project_without_environments_says_so(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-28 / pyc-infra-bundle**
    **Property: a project with no environments shows that instead of an
    id field, and no guards request is sent.**
    """
    api = _guards_api(environments=[])

    def _scenario(browser: Any) -> Any:
        context, page = _open_guards(browser=browser, api=api)
        try:
            page.wait_for_selector('[data-role="environment-filter-empty"]', timeout=5000)
            page.wait_for_timeout(300)
            text = page.inner_text('[data-role="environment-filter-empty"]')
            sent = api.requests_for(method="GET", path=GUARDS_PATH)
        finally:
            context.close()
        rtnval = (text, len(sent))
        return rtnval

    outcome = bundle_browser.run(_scenario)
    testbase.assert_equal(
        outcome,
        ("This project has no environments — register one on the Environments page.", 0),
    )
    return


# ---------------------------------------------------------------------------
# ORC-30 -- the build trigger sends the chosen source integration
# ---------------------------------------------------------------------------


SOURCE_INTEGRATIONS_PATH: str = "/api/v1/projects/{}/source-integrations".format(PROJECT_ID)
BUILDS_PATH: str = "/api/v1/projects/{}/builds".format(PROJECT_ID)
INTEGRATION_APP: str = "00000000-0000-4000-8000-0000000f0001"
INTEGRATION_LIB: str = "00000000-0000-4000-8000-0000000f0002"


def _builds_api() -> FakeApi:
    api = FakeApi()
    api.respond(
        method="GET",
        path=PROJECTS_PATH,
        body={"items": [{"project_id": PROJECT_ID, "slug": "p", "display_name": "P"}], "meta": {"total": 1}},
    )
    api.respond(
        method="GET",
        path=SOURCE_INTEGRATIONS_PATH,
        body={"items": [
            {"integration_id": INTEGRATION_APP, "project_id": PROJECT_ID,
             "provider_name": "github", "repo_key": "acme/app"},
            {"integration_id": INTEGRATION_LIB, "project_id": PROJECT_ID,
             "provider_name": "github", "repo_key": "acme/lib"},
        ], "meta": {"total": 2}},
    )
    api.respond(method="GET", path=BUILDS_PATH, body={"items": [], "meta": {"total": 0}})
    api.respond(
        method="POST",
        path=BUILDS_PATH,
        status=202,
        body={"run_id": "00000000-0000-4000-8000-0000000f00aa", "state": "pending"},
    )
    return api


def _trigger_build(*, browser: Any, api: FakeApi, choose: Optional[str]) -> Any:
    """
        Open the trigger form, optionally pick an integration option by
        its visible label, fill a makefile build, submit, and return
        the POST body.
    """
    context, page = open_bundle_page(browser=browser, api=api, bundle="pyc-builds-bundle")
    try:
        mount_element(page=page, tag="pyc-builds-list")
        wait_for_request(page=page, api=api, method="GET", path=SOURCE_INTEGRATIONS_PATH)
        wait_for_request(page=page, api=api, method="GET", path=BUILDS_PATH)
        page.click('[data-role="trigger-toggle"]')
        page.wait_for_selector('[data-role="trigger-form"]')
        if choose is not None:
            page.click('[data-role="trigger-integration"]')
            page.get_by_role("option", name=choose).click()
            page.wait_for_timeout(200)
        page.fill('[data-role="trigger-runner-kind"] input', "makefile")
        page.fill('[data-role="trigger-runner-inputs"] textarea', '{"targets": ["all"]}')
        page.click('[data-role="trigger-submit"]')
        posted = wait_for_request(page=page, api=api, method="POST", path=BUILDS_PATH)
    finally:
        context.close()
    rtnval = posted[0].body
    return rtnval


def test_build_trigger_sends_the_chosen_source_integration(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-30 / pyc-builds-bundle**
    **Property: choosing a source integration in the Trigger Build form
    sends its id as source_integration_id.**
    """
    api = _builds_api()
    body = bundle_browser.run(
        lambda browser: _trigger_build(browser=browser, api=api, choose="github \u00b7 acme/lib"),
    )
    testbase.assert_equal(body.get("source_integration_id"), INTEGRATION_LIB)
    return


def test_build_trigger_sends_the_preselected_integration(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-30 / pyc-builds-bundle**
    **Property: without touching the picker the request carries the
    integration the form shows (the first one).**
    """
    api = _builds_api()
    body = bundle_browser.run(
        lambda browser: _trigger_build(browser=browser, api=api, choose=None),
    )
    testbase.assert_equal(body.get("source_integration_id"), INTEGRATION_APP)
    return


def test_build_trigger_without_integration_omits_it(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-30 / pyc-builds-bundle**
    **Property: choosing "None" sends no source_integration_id.**
    """
    api = _builds_api()
    body = bundle_browser.run(
        lambda browser: _trigger_build(
            browser=browser,
            api=api,
            choose="None \u2014 the runner inputs name the repository",
        ),
    )
    testbase.assert_equal("source_integration_id" in body, False)
    return



# ---------------------------------------------------------------------------
# ORC-04 -- the metrics views speak the registered kinds' contracts
# ---------------------------------------------------------------------------


CATALOG_API_PATH: str = "/api/v1/metrics/catalog"
ALERT_RULES_PATH: str = "/api/v1/projects/{}/metric-alerts".format(PROJECT_ID)
SLOS_PATH: str = "/api/v1/projects/{}/slos".format(PROJECT_ID)
DASHBOARD_ID: str = "00000000-0000-4000-8000-0000000d0001"
DASHBOARD_PATH: str = "/api/v1/projects/{}/dashboards/{}".format(PROJECT_ID, DASHBOARD_ID)
FAILED_METRIC: str = "pychestrate_rpa_jobs_failed_total"
SUBSCRIPTIONS_PATH: str = "/api/v1/webhooks/out/subscriptions"
SUBSCRIPTION_ID: str = "00000000-0000-4000-8000-0000000d0002"
SUBSCRIPTION_TEST_PATH: str = "{}/{}/test".format(SUBSCRIPTIONS_PATH, SUBSCRIPTION_ID)


def _metrics_api(*, alert_rules: Optional[List[Dict[str, Any]]] = None) -> FakeApi:
    api = FakeApi()
    api.respond(
        method="GET",
        path=PROJECTS_PATH,
        body={"items": [{"project_id": PROJECT_ID, "slug": "p", "display_name": "P"}], "meta": {"total": 1}},
    )
    api.respond(
        method="GET",
        path=CATALOG_API_PATH,
        body={"items": [{"name": FAILED_METRIC, "kind": "counter", "label_names": ["project_id"]}]},
    )
    api.respond(
        method="GET",
        path=ALERT_RULES_PATH,
        body={"items": alert_rules if alert_rules is not None else [], "meta": {"total": 0}},
    )
    api.respond(
        method="POST",
        path=ALERT_RULES_PATH,
        status=201,
        body={"rule_id": "00000000-0000-4000-8000-0000000d00aa"},
    )
    api.respond(method="GET", path=SLOS_PATH, body={"items": [], "meta": {"total": 0}})
    api.respond(
        method="POST",
        path=SLOS_PATH,
        status=201,
        body={"slo_id": "00000000-0000-4000-8000-0000000d00bb"},
    )
    return api


def _open_alert_rules(*, browser: Any, api: FakeApi) -> Any:
    context, page = open_bundle_page(browser=browser, api=api, bundle="pyc-metrics-bundle")
    mount_element(page=page, tag="pyc-alert-rules")
    wait_for_request(page=page, api=api, method="GET", path=CATALOG_API_PATH)
    wait_for_request(page=page, api=api, method="GET", path=ALERT_RULES_PATH)
    rtnval = (context, page)
    return rtnval


def _submit_alert_rule(*, page: Any) -> None:
    page.click('[data-role="create-toggle"]')
    page.wait_for_selector('[data-role="create-form"]')
    page.fill('[data-role="create-name"] input', "rpa failures")
    page.fill('[data-role="create-threshold"] input', "0")
    page.click('[data-role="create-submit"]')
    return


def test_alert_rule_form_sends_the_threshold_kind_config(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-04 / pyc-metrics-bundle**
    **Property: the create form sends the config the registered
    threshold kind validates -- metric_name, op, threshold,
    window_seconds -- not metric / comparison.**
    """
    api = _metrics_api()

    def _scenario(browser: Any) -> Any:
        context, page = _open_alert_rules(browser=browser, api=api)
        try:
            _submit_alert_rule(page=page)
            posted = wait_for_request(page=page, api=api, method="POST", path=ALERT_RULES_PATH)
        finally:
            context.close()
        rtnval = posted[0].body
        return rtnval

    body = bundle_browser.run(_scenario)
    testbase.assert_equal(
        (body["kind"], body["config"]),
        ("threshold", {"metric_name": FAILED_METRIC, "op": ">", "threshold": 0, "window_seconds": 3600}),
    )
    return


def test_alert_rule_create_failure_shows_the_server_detail(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-04 / pyc-metrics-bundle**
    **Property: a rejected rule shows the server's reason instead of
    "check the fields".**
    """
    api = _metrics_api()
    api.respond(
        method="POST",
        path=ALERT_RULES_PATH,
        status=422,
        body={"type": "about:blank", "title": "Unprocessable", "status": 422,
              "detail": "invalid config: 'window_seconds' must be a positive integer when present"},
    )

    def _scenario(browser: Any) -> Any:
        context, page = _open_alert_rules(browser=browser, api=api)
        try:
            _submit_alert_rule(page=page)
            page.wait_for_selector('[data-role="toast"][data-tone="error"]', timeout=5000)
            rtnval = page.inner_text('[data-role="toast"][data-tone="error"]')
        finally:
            context.close()
        return rtnval

    toast_text = bundle_browser.run(_scenario)
    testbase.assert_equal("'window_seconds' must be a positive integer" in toast_text, True)
    return


def test_alert_rule_list_shows_the_evaluator_state(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-04 / pyc-metrics-bundle**
    **Property: each rule row shows the alert evaluator's live state
    (here: Firing).**
    """
    api = _metrics_api(alert_rules=[{
        "rule_id": "00000000-0000-4000-8000-0000000d00cc",
        "project_id": PROJECT_ID,
        "name": "rpa failures",
        "kind": "threshold",
        "config": {"metric_name": FAILED_METRIC, "op": ">", "threshold": 0, "window_seconds": 3600},
        "severity": "warning",
        "enabled": True,
        "notification_targets": [],
        "live_state": {"state": "firing", "last_reason": "2.0 > 0.0",
                       "last_evaluated_at": "2026-09-22T23:00:00+00:00", "fire_count": 1},
    }])

    def _scenario(browser: Any) -> Any:
        context, page = _open_alert_rules(browser=browser, api=api)
        try:
            badge = page.wait_for_selector('[data-role="state-badge"]', timeout=5000)
            rtnval = (badge.get_attribute("data-state"), badge.inner_text().strip())
        finally:
            context.close()
        return rtnval

    shown = bundle_browser.run(_scenario)
    testbase.assert_equal(shown, ("firing", "Firing"))
    return


def _open_slos_form(*, browser: Any, api: FakeApi) -> Any:
    context, page = open_bundle_page(browser=browser, api=api, bundle="pyc-metrics-bundle")
    mount_element(page=page, tag="pyc-slos")
    wait_for_request(page=page, api=api, method="GET", path=SLOS_PATH)
    page.click('[data-role="create-toggle"]')
    page.wait_for_selector('[data-role="create-form"]')
    rtnval = (context, page)
    return rtnval


def _submit_slo(*, page: Any) -> None:
    page.fill('[data-role="create-name"] input', "rpa success")
    page.fill('[data-role="create-target"] input', "0.9")
    page.fill('[data-role="create-window"] input', "604800")
    page.fill(
        '[data-role="create-config"] textarea',
        '{"good_metric_name": "pychestrate_rpa_jobs_completed_total",'
        ' "total_metric_name": "pychestrate_rpa_jobs_triggered_total"}',
    )
    page.click('[data-role="create-submit"]')
    return


def test_slo_form_defaults_to_the_registered_kind(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-04 / pyc-metrics-bundle**
    **Property: the create form's kind defaults to availability_ratio
    (the registered SLO kind), so an SLO created without editing the
    kind is accepted.**
    """
    api = _metrics_api()

    def _scenario(browser: Any) -> Any:
        context, page = _open_slos_form(browser=browser, api=api)
        try:
            _submit_slo(page=page)
            posted = wait_for_request(page=page, api=api, method="POST", path=SLOS_PATH)
        finally:
            context.close()
        rtnval = posted[0].body
        return rtnval

    body = bundle_browser.run(_scenario)
    testbase.assert_equal(body["kind"], "availability_ratio")
    return


def test_slo_create_failure_shows_the_server_detail(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-04 / pyc-metrics-bundle**
    **Property: a rejected SLO shows the server's reason instead of
    "check the fields".**
    """
    api = _metrics_api()
    api.respond(
        method="POST",
        path=SLOS_PATH,
        status=422,
        body={"type": "about:blank", "title": "Unprocessable", "status": 422,
              "detail": "invalid definition_config: 'good_metric_name' is required"},
    )

    def _scenario(browser: Any) -> Any:
        context, page = _open_slos_form(browser=browser, api=api)
        try:
            _submit_slo(page=page)
            page.wait_for_selector('[data-role="toast"][data-tone="error"]', timeout=5000)
            rtnval = page.inner_text('[data-role="toast"][data-tone="error"]')
        finally:
            context.close()
        return rtnval

    toast_text = bundle_browser.run(_scenario)
    testbase.assert_equal("'good_metric_name' is required" in toast_text, True)
    return


def test_dashboard_editor_saves_a_tile_the_backend_accepts(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-04 / pyc-metrics-bundle**
    **Property: a tile added in the editor is saved with a registered
    tile kind (metric-line-chart) and a metric_name config.**
    """
    api = _metrics_api()
    api.respond(
        method="GET",
        path=DASHBOARD_PATH,
        body={"dashboard_id": DASHBOARD_ID, "project_id": PROJECT_ID, "name": "ops", "tiles": [], "version": 1},
    )
    api.respond(
        method="PATCH",
        path=DASHBOARD_PATH,
        body={"dashboard_id": DASHBOARD_ID, "version": 2},
    )

    def _scenario(browser: Any) -> Any:
        context, page = open_bundle_page(browser=browser, api=api, bundle="pyc-metrics-bundle")
        try:
            page.evaluate(
                "(path) => history.pushState({}, '', path)",
                "/dashboards/{}/edit".format(DASHBOARD_ID),
            )
            mount_element(page=page, tag="pyc-dashboard-editor")
            wait_for_request(page=page, api=api, method="GET", path=DASHBOARD_PATH)
            wait_for_request(page=page, api=api, method="GET", path=CATALOG_API_PATH)
            page.wait_for_selector('[data-role="add-tile"]', timeout=5000)
            page.wait_for_timeout(200)
            page.click('[data-role="add-tile"]')
            page.click('[data-role="save-layout"]')
            patched = wait_for_request(page=page, api=api, method="PATCH", path=DASHBOARD_PATH)
        finally:
            context.close()
        rtnval = patched[0].body["tiles"][0]
        return rtnval

    tile = bundle_browser.run(_scenario)
    testbase.assert_equal(
        (tile["kind"], tile["config"]),
        ("metric-line-chart", {"metric_name": FAILED_METRIC, "label_filter": {}, "range_seconds": 3600}),
    )
    return


def test_webhooks_test_event_reports_an_undelivered_event(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-04 / pyc-ops-bundle**
    **Property: when the server reports the test event was not
    delivered, the view says so with the reason instead of "queued".**
    """
    api = _webhooks_api()
    api.respond(
        method="GET",
        path=SUBSCRIPTIONS_PATH,
        body={"items": [{
            "subscription_id": SUBSCRIPTION_ID, "project_id": PROJECT_ID, "name": "notifier",
            "url": "http://127.0.0.1:9/hook", "topic_filters": [], "enabled": True,
        }], "meta": {"total": 1}},
    )
    api.respond(
        method="POST",
        path=SUBSCRIPTION_TEST_PATH,
        body={"status": "failed", "delivery": {
            "delivery_id": "00000000-0000-4000-8000-0000000d00dd", "outcome": "failed",
            "response_status": None,
            "response_excerpt": "not sent: the host '127.0.0.1' resolves to a loopback address (127.0.0.1), which webhooks may not target",
        }},
    )
    api.respond(
        method="GET",
        path="{}/{}/deliveries".format(SUBSCRIPTIONS_PATH, SUBSCRIPTION_ID),
        body={"items": [], "meta": {"total": 0}},
    )

    def _scenario(browser: Any) -> Any:
        context, page = _open_webhooks(browser=browser, api=api)
        try:
            page.click('[data-role="tab-outbound"]')
            wait_for_request(page=page, api=api, method="GET", path=SUBSCRIPTIONS_PATH)
            page.click('[data-role="test-event"]')
            page.wait_for_selector('[data-role="toast"][data-tone="error"]', timeout=5000)
            rtnval = page.inner_text('[data-role="toast"][data-tone="error"]')
        finally:
            context.close()
        return rtnval

    toast_text = bundle_browser.run(_scenario)
    testbase.assert_equal(
        toast_text.startswith("Test event was not delivered: not sent:"), True,
    )
    return


# ---------------------------------------------------------------------------
# ORG-F14 -- pages that work only in part say what is missing
# ---------------------------------------------------------------------------


def test_alert_rules_page_says_notifications_are_not_sent(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORG-F14 / pyc-metrics-bundle**
    **Property: the Alert Rules page carries a preview notice saying
    rules are evaluated but no notification is sent.**
    """
    api = _metrics_api()

    def _scenario(browser: Any) -> Any:
        context, page = _open_alert_rules(browser=browser, api=api)
        try:
            notice = page.wait_for_selector('[data-role="preview-notice"]', timeout=5000)
            rtnval = notice.inner_text()
        finally:
            context.close()
        return rtnval

    text = bundle_browser.run(_scenario)
    testbase.assert_equal(
        (text.startswith("Preview:"), "no notification is sent" in text),
        (True, True),
    )
    return


def test_webhooks_page_says_deliveries_start_nothing(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORG-F14 / pyc-ops-bundle**
    **Property: the Webhooks page carries a preview notice saying
    inbound deliveries start nothing and outbound subscriptions get
    test events only.**
    """
    api = _webhooks_api()

    def _scenario(browser: Any) -> Any:
        context, page = _open_webhooks(browser=browser, api=api)
        try:
            notice = page.wait_for_selector('[data-role="preview-notice"]', timeout=5000)
            rtnval = notice.inner_text()
        finally:
            context.close()
        return rtnval

    text = bundle_browser.run(_scenario)
    testbase.assert_equal(
        ("do not start builds or pipelines" in text, "test events only" in text),
        (True, True),
    )
    return


def test_slos_table_calls_the_status_column_achieved(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORG-F14 / pyc-metrics-bundle**
    **Property: the SLO status column shows the achieved ratio and is
    labelled "Achieved", not "Burn-rate" (no burn rate is computed).**
    """
    api = _metrics_api()
    api.respond(
        method="GET",
        path=SLOS_PATH,
        body={"items": [{
            "slo_id": "00000000-0000-4000-8000-0000000d00ee",
            "project_id": PROJECT_ID,
            "name": "rpa success",
            "kind": "availability_ratio",
            "target": 0.9,
            "window_seconds": 604800,
            "status": {"achieved_ratio": 0.95, "breaching": False, "error_budget_remaining_ratio": 0.5,
                       "reason": "good=19 total=20 ratio=0.950000"},
        }], "meta": {"total": 1}},
    )

    def _scenario(browser: Any) -> Any:
        context, page = open_bundle_page(browser=browser, api=api, bundle="pyc-metrics-bundle")
        try:
            mount_element(page=page, tag="pyc-slos")
            page.wait_for_selector('[data-role="burn-indicator"]', timeout=5000)
            rtnval = page.evaluate(
                "() => document.querySelector('[data-role=\"slos-table\"]').columns.map((c) => c.label)",
            )
        finally:
            context.close()
        return rtnval

    labels = bundle_browser.run(_scenario)
    testbase.assert_equal(("Achieved" in labels, "Burn-rate" in labels), (True, False))
    return


# ---------------------------------------------------------------------------
# ORC-31 -- "Pychestrate Updates" explains why publishing is unavailable
# ---------------------------------------------------------------------------


RELEASE_CHANNELS_API_PATH: str = "/api/v1/release-channels"
NO_KEY_REASON: str = (
    "Publishing is unavailable: this server has no release-signing key, and"
    " this release cannot load one at startup, so Pychestrate updates cannot"
    " be signed and published from this server."
)


def _updates_api(*, publishing_available: bool) -> FakeApi:
    api = FakeApi()
    api.respond(
        method="GET",
        path=RELEASE_CHANNELS_API_PATH,
        body={"items": [], "meta": {
            "page": 1, "per_page": 50, "total": 0, "next_cursor": None,
            "publishing_available": publishing_available,
            "publishing_unavailable_reason": None if publishing_available else NO_KEY_REASON,
        }},
    )
    return api


def _open_updates(*, browser: Any, api: FakeApi) -> Any:
    context, page = open_bundle_page(browser=browser, api=api, bundle="pyc-ops-bundle")
    mount_element(page=page, tag="pyc-release-channels")
    wait_for_request(page=page, api=api, method="GET", path=RELEASE_CHANNELS_API_PATH)
    page.wait_for_selector('[data-role="empty-state"]', timeout=5000)
    rtnval = (context, page)
    return rtnval


def test_updates_page_is_titled_pychestrate_updates(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-31 / pyc-ops-bundle**
    **Property: the page is titled "Pychestrate Updates" and says the
    channels carry Pychestrate's own releases, not a project's.**
    """
    api = _updates_api(publishing_available=True)

    def _scenario(browser: Any) -> Any:
        context, page = _open_updates(browser=browser, api=api)
        try:
            rtnval = (
                page.inner_text("pyc-release-channels h1"),
                page.inner_text('[data-role="updates-intro"]'),
            )
        finally:
            context.close()
        return rtnval

    heading, intro = bundle_browser.run(_scenario)
    testbase.assert_equal(
        (heading, intro.startswith("Releases of the Pychestrate service and its pod client")),
        ("Pychestrate Updates", True),
    )
    return


def test_updates_page_explains_why_publishing_is_unavailable(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-31 / pyc-ops-bundle**
    **Property: when the server cannot publish (no signing key) the page
    shows the server's reason and the Publish action is disabled.**
    """
    api = _updates_api(publishing_available=False)

    def _scenario(browser: Any) -> Any:
        context, page = _open_updates(browser=browser, api=api)
        try:
            notice = page.wait_for_selector('[data-role="publishing-unavailable"]', state="visible", timeout=5000)
            rtnval = (
                notice.inner_text(),
                page.get_attribute('[data-role="publish-toggle"]', "disabled") is not None,
            )
        finally:
            context.close()
        return rtnval

    text, disabled = bundle_browser.run(_scenario)
    testbase.assert_equal((text, disabled), (NO_KEY_REASON, True))
    return


def test_updates_publish_failure_shows_the_server_reason(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-31 / pyc-ops-bundle**
    **Property: a refused publish shows the server's problem detail,
    not "HTTP 503".**
    """
    api = _updates_api(publishing_available=True)
    api.respond(
        method="POST",
        path=RELEASE_CHANNELS_API_PATH,
        status=503,
        body={"type": "about:blank", "title": "Service Unavailable", "status": 503,
              "detail": NO_KEY_REASON, "reason": "signing_key_missing"},
    )

    def _scenario(browser: Any) -> Any:
        context, page = _open_updates(browser=browser, api=api)
        try:
            page.click('[data-role="publish-toggle"]')
            page.wait_for_selector('[data-role="publish-form"]')
            page.fill('[data-role="publish-version"] input', "1.4.0")
            page.fill('[data-role="publish-uri"] input', "oci://registry/pychestrate:1.4.0")
            page.fill('[data-role="publish-sha"] input', "a" * 64)
            page.click('[data-role="publish-submit"]')
            page.wait_for_selector('[data-role="toast"][data-tone="error"]', timeout=5000)
            rtnval = page.inner_text('[data-role="toast"][data-tone="error"]')
        finally:
            context.close()
        return rtnval

    toast_text = bundle_browser.run(_scenario)
    testbase.assert_equal(
        (NO_KEY_REASON in toast_text, "HTTP 503" in toast_text),
        (True, False),
    )
    return


# ---------------------------------------------------------------------------
# ORC-39 -- environment detail with drift history; no dead-end drift check
# ---------------------------------------------------------------------------


ENVIRONMENT_ID: str = "00000000-0000-4000-8000-0000000e0039"
ENVIRONMENT_PATH: str = "{}/{}".format(ENVIRONMENTS_PATH, ENVIRONMENT_ID)
ENVIRONMENT_DRIFT_PATH: str = "{}/drift".format(ENVIRONMENT_PATH)
NO_SCHEDULE_REASON: str = (
    "This environment has no drift schedule, and drift schedules cannot be"
    " set up from the API or the UI yet, so a drift check cannot start."
)
DRIFT_PREVIEW: str = (
    "Drift detection is a preview: a drift check is recorded, but nothing"
    " processes it yet, so the run stays pending and reports no drift."
)


def _environment_record() -> Dict[str, Any]:
    rtnval = {
        "environment_id": ENVIRONMENT_ID, "project_id": PROJECT_ID, "kind_name": "terraform",
        "name": "staging", "state": "active", "attrs": {"region": "us-east-1"},
        "last_applied_at": None, "created_at": "2026-09-20T10:00:00+00:00",
    }
    return rtnval


def _drift_run(*, run_id: str, state: str) -> Dict[str, Any]:
    rtnval = {
        "run_id": run_id, "project_id": PROJECT_ID, "environment_id": ENVIRONMENT_ID,
        "checker_name": "terraform", "state": state, "trigger_kind": "manual",
        "scheduled_for": "2026-09-21T10:00:00+00:00", "ran_at": None, "drift_count": None,
        "added": None, "changed": None, "destroyed": None, "final_state_reason": "",
    }
    return rtnval


def _environments_api() -> FakeApi:
    api = FakeApi()
    api.respond(
        method="GET",
        path=PROJECTS_PATH,
        body={"items": [{"project_id": PROJECT_ID, "slug": "p", "display_name": "P"}], "meta": {"total": 1}},
    )
    api.respond(
        method="GET",
        path=ENVIRONMENTS_PATH,
        body={"items": [_environment_record()], "meta": {"total": 1, "page": 1, "per_page": 25}},
    )
    api.respond(
        method="POST",
        path=ENVIRONMENTS_PATH,
        status=201,
        body={"environment_id": "00000000-0000-4000-8000-0000000e0040"},
    )
    api.respond(method="GET", path=ENVIRONMENT_PATH, body=_environment_record())
    api.respond(
        method="GET",
        path=ENVIRONMENT_DRIFT_PATH,
        body={
            "environment_id": ENVIRONMENT_ID,
            "has_report": True,
            "latest_report": _drift_run(run_id="00000000-0000-4000-8000-0000000d0392", state="pending"),
            "history": [
                _drift_run(run_id="00000000-0000-4000-8000-0000000d0392", state="pending"),
                _drift_run(run_id="00000000-0000-4000-8000-0000000d0391", state="pending"),
            ],
            "schedule": None,
            "check_available": False,
            "check_unavailable_reason": NO_SCHEDULE_REASON,
            "dispatch_available": False,
            "detail": DRIFT_PREVIEW,
        },
    )
    return api


def _open_environment_list(*, browser: Any, api: FakeApi) -> Any:
    context, page = open_bundle_page(browser=browser, api=api, bundle="pyc-infra-bundle")
    mount_element(page=page, tag="pyc-environments")
    wait_for_request(page=page, api=api, method="GET", path=ENVIRONMENTS_PATH)
    page.wait_for_selector('[data-environment-id]', timeout=5000)
    rtnval = (context, page)
    return rtnval


def _open_environment_detail(*, browser: Any, api: FakeApi) -> Any:
    context, page = open_bundle_page(browser=browser, api=api, bundle="pyc-infra-bundle")
    page.evaluate(
        "(path) => history.pushState({}, '', path)",
        "/environments/{}?project_id={}".format(ENVIRONMENT_ID, PROJECT_ID),
    )
    mount_element(page=page, tag="pyc-environment-detail")
    wait_for_request(page=page, api=api, method="GET", path=ENVIRONMENT_DRIFT_PATH)
    page.wait_for_selector('[data-role="drift-section"]', timeout=5000)
    rtnval = (context, page)
    return rtnval


def test_environment_name_links_to_its_detail_page(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-39 / pyc-infra-bundle**
    **Property: an environment's name links to its detail page.**
    """
    api = _environments_api()

    def _scenario(browser: Any) -> Any:
        context, page = _open_environment_list(browser=browser, api=api)
        try:
            rtnval = page.get_attribute('[data-role="environment-link"]', "href")
        finally:
            context.close()
        return rtnval

    href = bundle_browser.run(_scenario)
    testbase.assert_equal(href, "/environments/{}?project_id={}".format(ENVIRONMENT_ID, PROJECT_ID))
    return


def test_environment_list_has_no_dead_end_drift_button(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-39 / pyc-infra-bundle**
    **Property: the list no longer offers a row "Check Drift" that
    ended on a 409; the row offers the environment's details.**
    """
    api = _environments_api()

    def _scenario(browser: Any) -> Any:
        context, page = _open_environment_list(browser=browser, api=api)
        try:
            rtnval = (
                page.locator('[data-role="check-drift"]').count(),
                page.locator('[data-role="view-environment"]').count(),
            )
        finally:
            context.close()
        return rtnval

    counts = bundle_browser.run(_scenario)
    testbase.assert_equal(counts, (0, 1))
    return


def test_environment_register_form_is_reset_after_success(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-39 / pyc-infra-bundle**
    **Property: after a successful registration the form is emptied and
    closed, so the next registration starts clean.**
    """
    api = _environments_api()

    def _scenario(browser: Any) -> Any:
        context, page = _open_environment_list(browser=browser, api=api)
        try:
            page.click('[data-role="register-toggle"]')
            page.wait_for_selector('[data-role="register-form"]')
            page.fill('[data-role="register-name"] input', "production")
            page.fill('[data-role="register-kind"] input', "terraform")
            page.click('[data-role="register-submit"]')
            wait_for_request(page=page, api=api, method="POST", path=ENVIRONMENTS_PATH)
            page.wait_for_selector('[data-role="toast"][data-tone="ok"]', timeout=5000)
            rtnval = page.evaluate(
                "() => { const region = document.querySelector('[data-role=\"register-region\"]');"
                " const name = document.querySelector('[data-role=\"register-name\"]');"
                " return {hidden: region.hidden, name: name.value}; }",
            )
        finally:
            context.close()
        return rtnval

    state = bundle_browser.run(_scenario)
    testbase.assert_equal(state, {"hidden": True, "name": ""})
    return


def test_environment_detail_lists_the_drift_history(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-39 / pyc-infra-bundle**
    **Property: the environment detail page lists the environment's
    recorded drift runs.**
    """
    api = _environments_api()

    def _scenario(browser: Any) -> Any:
        context, page = _open_environment_detail(browser=browser, api=api)
        try:
            page.wait_for_selector('[data-role="drift-history-table"]', timeout=5000)
            page.wait_for_timeout(200)
            rtnval = page.locator('[data-role="drift-history-table"] [data-run-id]').count()
        finally:
            context.close()
        return rtnval

    rows = bundle_browser.run(_scenario)
    testbase.assert_equal(rows, 2)
    return


def test_environment_detail_labels_drift_detection_a_preview(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-39 / pyc-infra-bundle**
    **Property: the drift section is headed as a preview and shows why
    (the server's detail).**
    """
    api = _environments_api()

    def _scenario(browser: Any) -> Any:
        context, page = _open_environment_detail(browser=browser, api=api)
        try:
            rtnval = (
                page.inner_text('[data-role="drift-section"] h2'),
                page.inner_text('[data-role="drift-preview-notice"]'),
            )
        finally:
            context.close()
        return rtnval

    heading, notice = bundle_browser.run(_scenario)
    testbase.assert_equal((heading, notice), ("Drift detection (preview)", DRIFT_PREVIEW))
    return


def test_environment_detail_explains_why_drift_cannot_be_checked(bundle_browser: ThreadedBrowser):
    """
    **Feature: audit ORC-39 / pyc-infra-bundle**
    **Property: without a drift schedule "Check Drift" is disabled and
    the page says why, instead of dead-ending on a 409.**
    """
    api = _environments_api()

    def _scenario(browser: Any) -> Any:
        context, page = _open_environment_detail(browser=browser, api=api)
        try:
            rtnval = (
                page.get_attribute('[data-role="check-drift"]', "disabled") is not None,
                page.inner_text('[data-role="check-unavailable-reason"]'),
            )
        finally:
            context.close()
        return rtnval

    disabled, reason = bundle_browser.run(_scenario)
    testbase.assert_equal((disabled, reason), (True, NO_SCHEDULE_REASON))
    return
