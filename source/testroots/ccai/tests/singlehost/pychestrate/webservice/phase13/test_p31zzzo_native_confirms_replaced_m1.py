"""
.. module:: test_p31zzzo_native_confirms_replaced_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bundle views ask in the shell's dialog, not the browser's confirm box (XC-15).

.. moduleauthor:: Code Craft AI LLC

Sixteen places in the bundle views (cancel a run, revoke a client, delete a pool,
release a reservation, retire a resource, disable a flag or a webhook, delete a
secret, and so on) called ``window.confirm``. They now ask through
``shared/confirm.js``, which reaches the shell's own modal dialog (Cancel
focused, the deed named on the acting button, Escape means no) and falls back to
the browser's box only when nothing answers. A static check keeps the native call
out of every bundle source; browser tests drive five representative shapes (an
async action, a table-row action, a synchronous handler, a delete and a state
change) and check that Cancel sends nothing and confirming sends the request.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

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
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

#: The two places that may call the browser's box: the helper's fallback, and the shell's own
#: dialog when the page cannot show a <dialog>.
ALLOWED = (os.path.join("shared", "confirm.js"), os.path.join("pyc-site-shell", "chrome", "confirm-delegate.js"))

RUN_ID: str = "0f6c2c1e-cccc-4000-8000-000000000001"
POOL_ID: str = "0f6c2c1e-cccc-4000-8000-000000000002"
CLIENT_ID: str = "0f6c2c1e-cccc-4000-8000-000000000003"
RESOURCE_ID: str = "0f6c2c1e-cccc-4000-8000-000000000004"
PROJECT_ID: str = "0f6c2c1e-cccc-4000-8000-000000000005"


def test_no_bundle_source_calls_the_native_confirm_box():
    """
    **Feature: shell confirmation (XC-15)**
    **Property: no bundle source under static/javascript (the built index.js files
    and the vendored component library aside) calls ``window.confirm``, except the
    helper's fallback (``shared/confirm.js``) and the shell's own dialog fallback.**
    """
    root = os.path.join(SITE_DIRECTORIES.DIR_STATIC, "javascript")
    found: List[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        if "pyc-mj-lib" in dirpath:
            continue
        for name in filenames:
            path = os.path.join(dirpath, name)
            relative = os.path.relpath(path, root)
            if not name.endswith(".js") or name == "index.js" or relative in ALLOWED:
                continue
            with open(path, encoding="utf-8") as handle:
                if "window.confirm(" in handle.read():
                    found.append(relative)

    testbase.assert_equal(found, [])
    return


def _open(browser: Browser, *, path: str, bundle: str, stubs: Dict[str, Any]) -> Any:
    """Open ``path``; every request that is not a GET is collected on ``page.mutations`` as "METHOD /path"."""
    mutations: List[str] = []
    native: List[str] = []
    context = browser.new_context(**DESKTOP)
    install_site_routes(context, bundle_names=["pyc-site-shell", bundle], api_stubs=dict({"/api/v1/projects": {"items": [], "meta": {"total": 0}}}, **stubs))
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.on(
        "request",
        lambda request: mutations.append("{} {}".format(request.method, request.url[len(FAKE_ORIGIN):].split("?")[0]))
        if request.method != "GET" and "/api/v1/_metrics" not in request.url else None,
    )
    page.on("dialog", lambda dialog: (native.append(dialog.message), dialog.dismiss()))
    page.mutations = mutations
    page.native = native
    page.goto(FAKE_ORIGIN + path)
    return page


def _drive(page: Any, selector: str, typed: str = "") -> Dict[str, Any]:
    """
        Click ``selector``, read the shell's dialog, cancel it, click again, confirm it. When the dialog asks the
        person to type ``typed`` first, its confirming button is checked to be off until the text is right.

        :returns: the dialog's message and acting label, the mutations after Cancel, and after confirming, and (for
                  type-to-confirm) whether the confirming button was off at the start, after a wrong text and after
                  the right one.
    """
    page.wait_for_selector(selector)
    page.wait_for_timeout(500)
    page.locator(selector).first.click()
    page.wait_for_selector("dialog.pyc-confirm[open]")
    message = page.locator("dialog.pyc-confirm .pyc-confirm__message").inner_text().replace("\n\n", " ")
    label = page.locator('[data-role="confirm-accept"]').inner_text()
    page.locator('[data-role="confirm-cancel"]').click()
    page.wait_for_timeout(400)
    after_cancel = list(page.mutations)
    page.locator(selector).first.click()
    page.wait_for_selector("dialog.pyc-confirm[open]")
    gate: Any = None
    if typed:
        accept = page.locator('[data-role="confirm-accept"]')
        at_start = accept.is_disabled()
        page.locator('[data-role="confirm-typed"]').fill(typed[:-1])
        after_wrong = accept.is_disabled()
        page.locator('[data-role="confirm-typed"]').fill(typed)
        gate = [at_start, after_wrong, accept.is_disabled()]
    page.locator('[data-role="confirm-accept"]').click()
    page.wait_for_timeout(800)
    return {"message": message, "label": label, "after_cancel": after_cancel, "after_confirm": list(page.mutations), "native": list(page.native), "gate": gate}


def test_cancelling_a_run_asks_in_the_shells_dialog(browser: Browser):
    """
    **Feature: shell confirmation (XC-15)**
    **Property: "Cancel run" asks "Cancel this run? ..." in the shell's dialog (the
    acting button says "Yes, cancel the run", so it cannot be mistaken for the
    dialog's own Cancel); Cancel sends nothing; confirming POSTs the cancel; the
    browser's box is never used.**
    """
    run = {"run_id": RUN_ID, "project_id": PROJECT_ID, "state": "running", "job_type": "testbase", "created_at": "2026-09-29T10:00:00+00:00", "started_at": "2026-09-29T10:00:05+00:00", "progress_summary": {"percent_complete": 10}}
    page = _open(browser, path="/runs/" + RUN_ID, bundle="pyc-runs-bundle", stubs={"/api/v1/runs/" + RUN_ID: run})
    try:
        seen = _drive(page, '[data-role="cancel-button"]')
    finally:
        page.context.close()

    testbase.assert_equal(
        (seen["message"], seen["label"], seen["after_cancel"], "POST /api/v1/runs/{}/cancel".format(RUN_ID) in seen["after_confirm"], seen["native"]),
        ("Cancel this run? A cancellation request will be sent to the orchestrator.", "Yes, cancel the run", [], True, []),
    )
    return


def test_revoking_a_client_from_a_table_row_asks_in_the_shells_dialog(browser: Browser):
    """
    **Feature: shell confirmation (XC-15)**
    **Property: a client row's Revoke asks what revoking does ("the pod it backs
    stops receiving work"), Cancel sends nothing, and confirming POSTs the revoke.**
    """
    client = {
        "client_id": CLIENT_ID, "pod_name": "lab-pod", "status": "ACTIVE", "liveness_state": "ALIVE", "project_id": PROJECT_ID,
        "created_at": "2026-09-29T10:00:00+00:00", "last_seen": "2026-09-29T10:05:00+00:00", "capabilities": [],
    }
    page = _open(browser, path="/clients", bundle="pyc-pods-bundle", stubs={"/api/v1/clients": [client], "/api/v1/me/permissions": {"permissions": ["system:clients.read", "system:clients.write"]}})
    try:
        seen = _drive(page, '[data-role="revoke-action"]')
    finally:
        page.context.close()

    testbase.assert_equal(
        (seen["message"].startswith("Revoke client "), "the pod it backs stops receiving work" in seen["message"], seen["label"], seen["after_cancel"], any(item.startswith("POST /api/v1/clients/") and item.endswith("/revoke") for item in seen["after_confirm"]), seen["native"]),
        (True, True, "Revoke client", [], True, []),
    )
    return


def test_disabling_a_flag_asks_in_the_shells_dialog_and_enabling_does_not(browser: Browser):
    """
    **Feature: shell confirmation (XC-15)**
    **Property: the flag toggle is a synchronous handler; turning a flag off asks
    ("Set flag ... to disabled?") in the shell's dialog, Cancel sends nothing and
    confirming PATCHes; turning a flag on sends the PATCH without asking.**
    """
    flags = [
        {"flag_key": "beta.search", "state": "enabled", "description": "Search beta", "updated_at": "2026-09-29T10:00:00+00:00"},
        {"flag_key": "beta.export", "state": "disabled", "description": "Export beta", "updated_at": "2026-09-29T10:00:00+00:00"},
    ]
    page = _open(browser, path="/admin/feature-flags", bundle="pyc-admin-bundle", stubs={"/api/v1/flags": flags, "/api/v1/me/permissions": {"permissions": ["system:flags.admin"]}})
    try:
        page.wait_for_selector('[data-flag-key="beta.export"] [data-role="toggle"]')
        page.wait_for_timeout(500)
        page.locator('[data-flag-key="beta.export"] [data-role="toggle"]').click()
        page.wait_for_timeout(800)
        enabling = (list(page.mutations), page.locator("dialog.pyc-confirm[open]").count())
        page.locator('[data-flag-key="beta.search"] [data-role="toggle"]').click()
        page.wait_for_selector("dialog.pyc-confirm[open]")
        message = page.locator("dialog.pyc-confirm .pyc-confirm__message").inner_text().replace("\n\n", " ")
        label = page.locator('[data-role="confirm-accept"]').inner_text()
        page.locator('[data-role="confirm-cancel"]').click()
        page.wait_for_timeout(400)
        after_cancel = list(page.mutations)
        page.locator('[data-flag-key="beta.search"] [data-role="toggle"]').click()
        page.wait_for_selector("dialog.pyc-confirm[open]")
        page.locator('[data-role="confirm-accept"]').click()
        page.wait_for_timeout(800)
        after_confirm = list(page.mutations)
        native = list(page.native)
    finally:
        page.context.close()

    testbase.assert_equal(
        (enabling, message, label, after_cancel == enabling[0], after_confirm, native),
        (
            (["PATCH /api/v1/flags/beta.export"], 0), "Set flag \"beta.search\" to disabled?", "Disable flag", True,
            ["PATCH /api/v1/flags/beta.export", "PATCH /api/v1/flags/beta.search"], [],
        ),
    )
    return


def test_deleting_a_pool_asks_in_the_shells_dialog(browser: Browser):
    """
    **Feature: shell confirmation (XC-15)**
    **Property: a pool's Delete asks what goes and what stays in the shell's
    dialog and asks the person to type the pool's name: the confirming button is off at
    first and after a wrong text, on after the right one; Cancel sends nothing;
    confirming DELETEs the pool.**
    """
    pool = {"pool_id": POOL_ID, "name": "lab-a", "description": "", "created_at": "2026-09-29T10:00:00+00:00", "project_id": PROJECT_ID}
    page = _open(
        browser, path="/resource-pools/" + POOL_ID, bundle="pyc-resources-bundle",
        stubs={
            "/api/v1/resource-pools/" + POOL_ID: pool, "/api/v1/resource-pools/{}/resources".format(POOL_ID): {"items": [], "meta": {"total": 0}},
            "/api/v1/me/permissions": {"permissions": ["system:resource_pools.read", "system:resource_pools.write", "system:resources.read"]},
        },
    )
    try:
        seen = _drive(page, '[data-role="delete-pool"]', typed="lab-a")
    finally:
        page.context.close()

    testbase.assert_equal(
        (seen["message"], seen["label"], seen["after_cancel"], "DELETE /api/v1/resource-pools/" + POOL_ID in seen["after_confirm"], seen["native"], seen["gate"]),
        (
            "Delete the pool lab-a? This permanently removes the pool and its membership rows and cannot be undone. The member resources themselves are not deleted.",
            "Delete pool", [], True, [], [True, True, False],
        ),
    )
    return


def test_deleting_a_secret_asks_for_its_name_before_it_can_be_confirmed(browser: Browser):
    """
    **Feature: shell confirmation (XC-15)**
    **Property: a secret's Delete asks the person to type the secret's name: the confirming button is off at
    first and after a wrong text and on after the right one, Cancel sends nothing, and confirming DELETEs the
    secret; the browser's box is never used.**
    """
    secret = {
        "secret_ref": "ci/deploy-token", "backend_name": "local", "scope_kind": "ORG", "scope_ref": "", "current_version_id": "v1",
        "created_at": "2026-09-29T10:00:00+00:00", "updated_at": "2026-09-29T10:00:00+00:00", "description": "",
    }
    page = _open(browser, path="/secrets", bundle="pyc-secrets-bundle", stubs={"/api/v1/secrets": [secret]})
    try:
        seen = _drive(page, '[data-role="delete-action"]', typed="ci/deploy-token")
    finally:
        page.context.close()

    testbase.assert_equal(
        (seen["message"], seen["label"], seen["after_cancel"], any(item.startswith("DELETE /api/v1/secrets/") for item in seen["after_confirm"]), seen["native"], seen["gate"]),
        ("Delete the secret ci/deploy-token? This removes every version and cannot be undone.", "Delete secret", [], True, [], [True, True, False]),
    )
    return
