"""
.. module:: test_p31zzh_server_error_detail_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bundle views show the server's reason when it refuses a request (ORC-08).

.. moduleauthor:: Code Craft AI LLC

Bundle views mapped the status to a fixed sentence and dropped the RFC 7807
``detail``: a run refused because no pod was enrolled said "The environment
cannot accept this action right now", and validating a pipeline without a
commit said "not a valid DAG". A shared reader (``shared/problem-detail.js``)
lets each view keep its sentence as the fallback and show the server's own
words when there are some, ignoring a detail that only repeats the HTTP reason
phrase. The helpers are called in a browser, and two real views are given
refused requests.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os

from typing import Any, Dict

from playwright.sync_api import Browser

from ccai import testbase

from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES
from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    open_shell_page,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

PROJECT_ID: str = "0f6c2c1e-9999-4000-8000-000000000001"
ENVIRONMENT_ID: str = "0f6c2c1e-9999-4000-8000-000000000002"


def _refuse(page: Any, path: str, status: int, detail: str) -> None:
    body = json.dumps({"type": "/errors/x", "title": "x", "status": status, "detail": detail})
    page.context.route(
        "**" + path,
        lambda route: route.fulfill(status=status, headers={"Content-Type": "application/problem+json"}, body=body),
    )
    return


def test_the_reader_returns_one_line_and_ignores_a_bare_reason_phrase(browser: Browser):
    """
    **Feature: server error detail (ORC-08)**
    **Property: a multi-line detail becomes one line; "Not Found" and "Internal
    Server Error" (only the reason phrase) and an empty or missing detail
    read as none; a successful response has none; text that is not JSON has
    none; message_with_detail uses the detail with its prefix, else the
    fallback.**
    """
    page = open_shell_page(browser, **DESKTOP)
    try:
        result = page.evaluate(
            """async () => {
                const m = await import('/static/javascript/shared/problem-detail.js');
                const refused = (status, body) => new Response(typeof body === 'string' ? body : JSON.stringify(body), {status});
                return {
                    multi: await m.read_problem_detail(refused(422, {detail: 'commit_sha: required\\n filename: too long '})),
                    phrase: await m.read_problem_detail(refused(404, {detail: 'Not Found'})),
                    phrase500: await m.read_problem_detail(refused(500, {detail: 'Internal Server Error'})),
                    missing: await m.read_problem_detail(refused(409, {title: 'x'})),
                    ok: await m.read_problem_detail(new Response('{"detail": "x"}', {status: 200})),
                    text: await m.read_problem_detail(refused(502, '<html>Bad gateway</html>')),
                    with_detail: m.message_with_detail('Not started', 'No enrolled pod', 'The environment cannot accept this action.'),
                    without: m.message_with_detail('Not started', '', 'The environment cannot accept this action.'),
                };
            }"""
        )
    finally:
        page.context.close()

    testbase.assert_equal(
        result,
        {"multi": "commit_sha: required filename: too long", "phrase": "", "phrase500": "", "missing": "", "ok": "", "text": "",
         "with_detail": "Not started: No enrolled pod", "without": "The environment cannot accept this action."},
    )
    return


def test_a_refused_provisioning_run_says_why(browser: Browser):
    """
    **Feature: server error detail (ORC-08)**
    **Property: when the server answers 409 "No enrolled pod can take this
    run", the provisioning view's outcome says "Provisioning run not started:
    No enrolled pod can take this run" and not "The environment cannot accept
    this action right now"; a bare 409 keeps the fallback sentence.**
    """
    page = open_shell_page(
        browser, path="/provisioning-runs", bundle_names=["pyc-site-shell", "pyc-infra-bundle"], **DESKTOP,
    )
    try:
        page.wait_for_selector("pyc-provisioning-list", timeout=8000)
        path = "/api/v1/projects/{}/provisioning-runs".format(PROJECT_ID)
        _refuse(page, path, 409, "No enrolled pod can take this run")
        detailed = page.evaluate(
            """async ([pid, env]) => {
                const view = document.querySelector('pyc-provisioning-list');
                view._state.projectId = pid;
                return (await view.triggerProvisioning(env, 'terraform', 'apply', {})).message;
            }""",
            [PROJECT_ID, ENVIRONMENT_ID],
        )
        _refuse(page, path, 409, "Conflict")
        bare = page.evaluate(
            """async ([pid, env]) => {
                const view = document.querySelector('pyc-provisioning-list');
                return (await view.triggerProvisioning(env, 'terraform', 'apply', {})).message;
            }""",
            [PROJECT_ID, ENVIRONMENT_ID],
        )
    finally:
        page.context.close()

    testbase.assert_equal(
        (detailed, bare),
        ("Provisioning run not started: No enrolled pod can take this run", "The environment cannot accept this action right now."),
    )
    return


def test_validating_a_pipeline_without_a_commit_says_which_field(browser: Browser):
    """
    **Feature: server error detail (ORC-08)**
    **Property: a 422 whose detail names the missing commit reads "Pipeline
    not validated: <detail>", not "Pipeline definition is not a valid DAG."**
    """
    page = open_shell_page(
        browser, path="/pipelines", bundle_names=["pyc-site-shell", "pyc-pipelines-bundle"], **DESKTOP,
    )
    try:
        page.wait_for_selector("pyc-pipelines-list", timeout=8000)
        _refuse(page, "/api/v1/projects/{}/pipelines:validate".format(PROJECT_ID), 422, "commit_sha: field required")
        message = page.evaluate(
            """async (pid) => {
                const view = document.querySelector('pyc-pipelines-list');
                view._state.projectId = pid;
                return (await view._do_validate('', 'pipeline.yaml', 'name: x')).message;
            }""",
            PROJECT_ID,
        )
    finally:
        page.context.close()

    testbase.assert_equal(message, "Pipeline not validated: commit_sha: field required")
    return


def test_a_refused_client_revoke_says_why(browser: Browser):
    """
    **Feature: server error detail (ORC-08)**
    **Property: when the server answers a client revoke with 409 and a
    reason, the outcome reads "Client not revoked: <reason>", and a bare
    Forbidden keeps the view's own sentence.**
    """
    client_id = "0f6c2c1e-9999-4000-8000-000000000003"
    page = open_shell_page(browser, path="/clients", bundle_names=["pyc-site-shell", "pyc-pods-bundle"], **DESKTOP)
    try:
        page.wait_for_selector("pyc-clients-list", timeout=8000)
        path = "/api/v1/clients/{}/revoke".format(client_id)
        _refuse(page, path, 409, "This client was already revoked")
        detailed = page.evaluate(
            """async (id) => {
                const m = await import('/static/javascript/pyc-pods-bundle/clients-list-view.js');
                return (await m.perform_client_revoke(id)).message;
            }""",
            client_id,
        )
        _refuse(page, path, 403, "Forbidden")
        bare = page.evaluate(
            """async (id) => {
                const m = await import('/static/javascript/pyc-pods-bundle/clients-list-view.js');
                return (await m.perform_client_revoke(id)).message;
            }""",
            client_id,
        )
    finally:
        page.context.close()

    testbase.assert_equal(
        (detailed, bare != detailed and "Client not revoked" not in bare),
        ("Client not revoked: This client was already revoked", True),
    )
    return


#: Every view whose refusal path now reads the server's detail.
VIEWS_THAT_READ_THE_DETAIL = (
    "pyc-infra-bundle/provisioning-list-view.js",
    "pyc-infra-bundle/environments-view.js",
    "pyc-infra-bundle/guards-view.js",
    "pyc-catalog-bundle/catalog-view.js",
    "pyc-pipelines-bundle/pipelines-list-view.js",
    "pyc-admin-bundle/feature-flags-view.js",
    "pyc-admin-bundle/admin-overview-view.js",
    "pyc-pods-bundle/pod-detail-view.js",
    "pyc-pods-bundle/clients-list-view.js",
    "pyc-metrics-bundle/dashboards-view.js",
    "pyc-ops-bundle/webhooks-view.js",
)


def test_every_view_that_reported_a_fixed_sentence_reads_the_servers_detail():
    """
    **Feature: server error detail (ORC-08)**
    **Property: the eleven views that used to show a fixed sentence for a
    refused request import the shared reader, so a new refusal path cannot
    quietly drop the reason again.**
    """
    root = os.path.join(SITE_DIRECTORIES.DIR_STATIC, "javascript")
    missing = []
    for relative in VIEWS_THAT_READ_THE_DETAIL:
        with open(os.path.join(root, relative), encoding="utf-8") as handle:
            if "shared/problem-detail.js" not in handle.read():
                missing.append(relative)

    testbase.assert_equal(missing, [])
    return
