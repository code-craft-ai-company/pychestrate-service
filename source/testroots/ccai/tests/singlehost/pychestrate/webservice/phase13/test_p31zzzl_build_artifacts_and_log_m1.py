"""
.. module:: test_p31zzzl_build_artifacts_and_log_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A build's files open in the browser and its log is on the page (ORC-12).

.. moduleauthor:: Code Craft AI LLC

The build page linked each artifact's stored path as it stood, which the browser
resolved against the page and which opened nothing, and it showed no log. The
manifest stores the file's path in the run's result tree, which the service
serves at ``/api/v1/runs/{run_id}/artifacts/{path}``; the page now links that
address (opening text and images, downloading the rest), shows storage it does
not serve (``s3://``, ``oci://``) as text, and shows the tail of the build's log
when a small ``.log`` file was uploaded, linking the whole log. The real build
page is opened in a browser against stubbed API answers and a stubbed file
endpoint.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from typing import Any, Dict, List, Optional, Tuple

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

BUILD_ID: str = "aaaaaaaa-2222-4000-8000-000000000001"
PROJECT_ID: str = "aaaaaaaa-2222-4000-8000-000000000002"


def _entry(path: str, *, size: Optional[int] = 100, storage_uri: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"relative_path": path}
    if size is not None:
        payload["size_bytes"] = size
    return {
        "artifact_id": path, "artifact_type": "generic", "artifact_name": path,
        "storage_uri": storage_uri if storage_uri is not None else path, "sha256": "ab" * 32, "payload": payload,
    }


def _open(
        browser: Browser, artifacts: List[Dict[str, Any]], *, state: str = "completed", files: Optional[Dict[str, Tuple[int, str]]] = None
    ) -> Any:
    """
        Open the build page. ``files`` maps a result-tree path to the (status, text) the
        file endpoint answers; the paths asked for are collected on ``page.file_requests``.
    """
    files = files or {}
    asked: List[str] = []
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", "pyc-builds-bundle"],
        api_stubs={
            "/api/v1/projects/{}/builds/{}".format(PROJECT_ID, BUILD_ID): {
                "run_id": BUILD_ID, "project_id": PROJECT_ID, "runner_kind": "makefile", "repro_digest_sha256": "abcdef0123456789",
                "state": state, "started_at": "2026-09-29T10:00:00+00:00", "finished_at": "2026-09-29T10:01:00+00:00" if state == "completed" else None,
            },
            "/api/v1/projects/{}/builds/{}/artifacts".format(PROJECT_ID, BUILD_ID): {"items": artifacts, "meta": {"total": len(artifacts)}},
        },
    )

    def serve(route: Any) -> None:
        path = route.request.url.split("/artifacts/", 1)[1].split("?")[0]
        asked.append(path)
        status, text = files.get(path, (404, ""))
        route.fulfill(status=status, headers={"Content-Type": "text/plain; charset=utf-8"}, body=text.encode("utf-8"))

    context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/runs/" + BUILD_ID + r"/artifacts/.+"), serve)
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.file_requests = asked
    page.goto(FAKE_ORIGIN + "/builds/{}?project_id={}".format(BUILD_ID, PROJECT_ID))
    page.wait_for_selector('[data-role="artifacts-section"]')
    page.wait_for_timeout(1500)
    return page


def test_artifact_rows_link_through_the_run_and_unserved_storage_is_text(browser: Browser):
    """
    **Feature: build artifacts (ORC-12)**
    **Property: a stored path becomes the run's artifact address (each segment
    encoded); text and JSON open in a new tab ("Open"), other files download
    ("Download"); the size is shown; an ``s3://`` or ``oci://`` address has no
    link and reads "Stored at ...".**
    """
    page = _open(browser, [
        _entry("out/app-1.0.tar.gz", size=1536000),
        _entry("reports/summary.json", size=2048),
        _entry("path with space/é.txt", size=12),
        _entry("image", storage_uri="s3://bucket/key", size=None),
        _entry("oci-image", storage_uri="oci://registry.example/img@sha256:abc", size=None),
    ])
    try:
        rows = page.locator('[data-role="artifact-list"] > li')
        seen = []
        for index in range(rows.count()):
            row = rows.nth(index)
            link = row.locator("a")
            seen.append((
                link.get_attribute("href") if link.count() else None,
                link.inner_text() if link.count() else None,
                link.get_attribute("target") if link.count() else None,
                link.get_attribute("download") is not None if link.count() else None,
                row.locator(".pyc-build-detail__artifact-size").inner_text() if row.locator(".pyc-build-detail__artifact-size").count() else None,
                row.locator('[data-role="artifact-stored-at"]').inner_text() if row.locator('[data-role="artifact-stored-at"]').count() else None,
            ))
    finally:
        page.context.close()

    base = "/api/v1/runs/{}/artifacts/".format(BUILD_ID)
    testbase.assert_equal(
        seen,
        [
            (base + "out/app-1.0.tar.gz", "Download", None, True, "1.5 MB", None),
            (base + "reports/summary.json", "Open", "_blank", False, "2 KB", None),
            (base + "path%20with%20space/%C3%A9.txt", "Open", "_blank", False, "12 B", None),
            (None, None, None, None, None, "Stored at s3://bucket/key"),
            (None, None, None, None, None, "Stored at oci://registry.example/img@sha256:abc"),
        ],
    )
    return


def test_a_small_log_is_shown_by_its_tail_and_the_whole_log_is_linked(browser: Browser):
    """
    **Feature: build log (ORC-12)**
    **Property: of two ``.log`` files the one whose name says "build" is used;
    its last 200 lines are shown (not the earlier ones), with the count and a
    link to the whole file, which is fetched once.**
    """
    text = "\n".join("line {:03d}".format(number) for number in range(500)) + "\n"
    page = _open(
        browser, [_entry("other.log", size=10), _entry("build/output.log", size=len(text))],
        files={"build/output.log": (200, text), "other.log": (200, "other\n")},
    )
    try:
        shown = page.locator('[data-role="build-log"]').inner_text()
        note = page.locator('[data-role="log-cut"]').inner_text()
        href = page.locator('[data-role="log-open"]').get_attribute("href")
        asked = list(page.file_requests)
    finally:
        page.context.close()

    testbase.assert_equal(
        (shown.splitlines()[0], shown.splitlines()[-1], len(shown.splitlines()), "line 299" in shown, note, href, asked),
        ("line 300", "line 499", 200, False, "Showing the last 200 lines of 500.", "/api/v1/runs/{}/artifacts/build/output.log".format(BUILD_ID), ["build/output.log"]),
    )
    return


def test_a_big_log_is_linked_not_fetched_and_a_failure_or_absence_is_said(browser: Browser):
    """
    **Feature: build log (ORC-12)**
    **Property: a log over the size limit is not fetched (the section says how
    big it is and links it); a log the file endpoint refuses says it could not
    be loaded and still links it; a build with no ``.log`` file says so; a build
    that has not finished shows no log section.**
    """
    page = _open(browser, [_entry("build.log", size=2 * 1024 * 1024)], files={"build.log": (200, "never fetched")})
    try:
        big = (page.locator('[data-role="log-large"]').inner_text(), page.locator('[data-role="log-open"]').count(), list(page.file_requests))
    finally:
        page.context.close()
    page = _open(browser, [_entry("build.log", size=50)], files={"build.log": (500, "")})
    try:
        refused = (page.locator('[data-role="log-error"]').inner_text(), page.locator('[data-role="log-open"]').count())
    finally:
        page.context.close()
    page = _open(browser, [_entry("out/app.tar.gz")])
    try:
        none = page.locator('[data-role="log-none"]').inner_text()
    finally:
        page.context.close()
    page = _open(browser, [], state="running")
    try:
        running = page.locator('[data-role="log-section"]').inner_text().strip()
    finally:
        page.context.close()

    testbase.assert_equal(
        (big, refused, none, running),
        (("The log is 2 MB, too big to show here.", 1, []), ("Couldn't load the build log.", 1), "This build uploaded no log file.", ""),
    )
    return


def test_the_standard_output_is_the_log_and_a_non_empty_standard_error_is_shown_apart(browser: Browser):
    """
    **Feature: build log (ORC-12)**
    **Property: of ``build-stderr.log`` and ``build-stdout.log`` the standard output is the build log (found on a real build, where both names say "build" and the empty
    standard error was shown as "(the log is empty)"); the standard error is shown under "Error output" with its own link when it has anything in it; each file is
    fetched once.**
    """
    page = _open(
        browser, [_entry("build-stderr.log", size=29), _entry("build-stdout.log", size=26), _entry("build-summary.json", size=40)],
        files={"build-stdout.log": (200, "step 1 ok\nstep 2 ok\n"), "build-stderr.log": (200, "error: something broke\n")},
    )
    try:
        out = page.locator('[data-role="build-log"]').inner_text()
        err = page.locator('[data-role="build-log-errors"]').inner_text()
        heading = page.locator('[data-role="log-errors-heading"]').inner_text()
        out_href = page.locator('[data-role="log-open"]').get_attribute("href")
        err_href = page.locator('[data-role="log-errors-open"]').get_attribute("href")
        asked = sorted(page.file_requests)
    finally:
        page.context.close()

    testbase.assert_equal(
        (out.strip(), err.strip(), heading, out_href, err_href, asked),
        (
            "step 1 ok\nstep 2 ok", "error: something broke", "Error output", "/api/v1/runs/{}/artifacts/build-stdout.log".format(BUILD_ID),
            "/api/v1/runs/{}/artifacts/build-stderr.log".format(BUILD_ID), ["build-stderr.log", "build-stdout.log"],
        ),
    )
    return


def test_an_empty_standard_error_is_not_shown_and_a_lone_standard_error_is_the_log(browser: Browser):
    """
    **Feature: build log (ORC-12)**
    **Property: an empty standard error adds no "Error output" block (the passing build shows only its log); a build whose only log is ``build-stderr.log`` shows it as the
    build log; a standard error too big to show says so and links it.**
    """
    page = _open(
        browser, [_entry("build-stderr.log", size=0), _entry("build-stdout.log", size=12)],
        files={"build-stdout.log": (200, "all good\n"), "build-stderr.log": (200, "")},
    )
    try:
        quiet = (page.locator('[data-role="build-log"]').inner_text().strip(), page.locator('[data-role="build-log-errors"]').count(), page.locator('[data-role="log-errors-heading"]').count())
    finally:
        page.context.close()
    page = _open(browser, [_entry("build-stderr.log", size=20)], files={"build-stderr.log": (200, "only errors here\n")})
    try:
        lone = (page.locator('[data-role="build-log"]').inner_text().strip(), page.locator('[data-role="build-log-errors"]').count())
    finally:
        page.context.close()
    page = _open(
        browser, [_entry("build-stdout.log", size=10), _entry("build-stderr.log", size=3 * 1024 * 1024)],
        files={"build-stdout.log": (200, "fine\n"), "build-stderr.log": (200, "never fetched")},
    )
    try:
        big = (page.locator('[data-role="log-errors-large"]').inner_text(), page.locator('[data-role="log-errors-open"]').count(), list(page.file_requests))
    finally:
        page.context.close()

    testbase.assert_equal(
        (quiet, lone, big),
        (("all good", 0, 0), ("only errors here", 0), ("The error output is 3 MB, too big to show here.", 1, ["build-stdout.log"])),
    )
    return


def test_log_text_is_shown_as_text_and_wraps_inside_the_page(browser: Browser):
    """
    **Feature: build log (ORC-12)**
    **Property: markup in a log is shown as text (no element, no script runs), and
    a very long unbroken line wraps inside the log box instead of widening it.**
    """
    text = "<script>window.pwned=1</script>\n<img src=x onerror=window.pwned=2>\n" + "x" * 900 + "\n"
    page = _open(browser, [_entry("build.log", size=len(text))], files={"build.log": (200, text)})
    try:
        injected = page.locator('[data-role="log-section"] script, [data-role="log-section"] img').count()
        pwned = page.evaluate("() => window.pwned === undefined")
        shown = page.locator('[data-role="build-log"]').inner_text()
        fits = page.evaluate(
            """() => {
                const box = document.querySelector('[data-role="build-log"]');
                return box.scrollWidth <= box.clientWidth + 1 && box.getBoundingClientRect().right <= window.innerWidth;
            }"""
        )
    finally:
        page.context.close()

    testbase.assert_equal((injected, pwned, shown.startswith("<script>window.pwned=1</script>"), fits), (0, True, True, True))
    return
