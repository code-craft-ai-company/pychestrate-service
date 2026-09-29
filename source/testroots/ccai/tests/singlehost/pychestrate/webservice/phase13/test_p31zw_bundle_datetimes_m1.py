"""
.. module:: test_p31zw_bundle_datetimes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Every bundle formats a time the way the glossary says (XC-14).

.. moduleauthor:: Code Craft AI LLC

Bundle views called ``toLocaleString()``: "9/22/2026, 4:34:12 PM", 12-hour, no
zone, a different shape in every locale, while the server pages show
"2026-09-22 23:21 UTC"; and ``new Date(text)`` read a timestamp without a zone
designator as the viewer's local time, shifting it by their UTC offset. One
shared formatter (``shared/datetime.js``, bundled into each bundle) now
renders "YYYY-MM-DD HH:MM ZONE", 24-hour, in the viewer's zone, reads a
zone-less server time as UTC, and stamps "as of" with the zone. The real
modules are imported in a browser with a fixed zone and locale.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict, List, Tuple

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


#: (module under /static/javascript, exported formatter)
FORMATTERS: List[Tuple[str, str]] = [
    ("pyc-builds-bundle/builds-list-view.js", "format_timestamp"),
    ("pyc-catalog-bundle/catalog-view.js", "format_timestamp"),
    ("pyc-infra-bundle/environments-view.js", "format_timestamp"),
    ("pyc-infra-bundle/guards-view.js", "format_guard_timestamp"),
    ("pyc-ops-bundle/release-channels-view.js", "format_release_timestamp"),
    ("pyc-ops-bundle/webhooks-view.js", "format_webhook_timestamp"),
    ("pyc-pipelines-bundle/pipelines-list-view.js", "format_timestamp"),
    ("pyc-pods-bundle/clients-list-view.js", "format_timestamp"),
    ("pyc-pods-bundle/pods-list-view.js", "format_timestamp"),
    ("pyc-runs-bundle/runs-list-view.js", "format_timestamp"),
    ("pyc-secrets-bundle/secrets-view.js", "format_timestamp"),
    ("pyc-resources-bundle/resource-pools-view.js", "format_timestamp"),
]

PACIFIC: Dict[str, Any] = {"timezone_id": "America/Los_Angeles", "locale": "en-US"}
BERLIN: Dict[str, Any] = {"timezone_id": "Europe/Berlin", "locale": "en-US"}


def _run(browser: Browser, script: str, arg: Any, **context: Any) -> Any:
    page = open_shell_page(browser, **context)
    try:
        return page.evaluate(script, arg)
    finally:
        page.context.close()


FORMAT_ALL_JS: str = """async ([modules, value]) => {
    const out = {};
    for (const [module, fn] of modules) {
        const loaded = await import('/static/javascript/' + module);
        out[module + ':' + fn] = loaded[fn](value);
    }
    return out;
}"""


def test_every_bundle_shows_a_server_time_in_the_glossary_form_with_the_zone(browser: Browser):
    """
    **Feature: bundle date-times (XC-14)**
    **Property: in a Pacific-time browser with a US locale (12-hour by
    default), each of the twelve bundle formatters turns the server time
    "2026-09-22T23:21:05Z" into "2026-09-22 16:21 PDT".**
    """
    shown = _run(browser, FORMAT_ALL_JS, [[list(pair) for pair in FORMATTERS], "2026-09-22T23:21:05Z"], **PACIFIC)

    testbase.assert_equal(
        {key: value for key, value in shown.items() if value != "2026-09-22 16:21 PDT"}, {}
    )
    return


def test_a_time_without_a_zone_is_read_as_utc_not_as_the_viewers_local_time(browser: Browser):
    """
    **Feature: bundle date-times (XC-14, RES-20)**
    **Property: "2026-09-22T23:21:05" and "2026-09-22 23:21:05", which the
    server sends without a zone, read as 23:21 UTC in every bundle: 16:21
    PDT for a Pacific viewer, 01:21 the next day for a Berlin viewer.**
    """
    modules = [list(pair) for pair in FORMATTERS]
    pacific = _run(browser, FORMAT_ALL_JS, [modules, "2026-09-22T23:21:05"], **PACIFIC)
    spaced = _run(browser, FORMAT_ALL_JS, [modules, "2026-09-22 23:21:05"], **PACIFIC)
    berlin = _run(browser, FORMAT_ALL_JS, [modules, "2026-09-22T23:21:05"], **BERLIN)

    testbase.assert_equal(
        (set(pacific.values()), set(spaced.values()), {value.rsplit(" ", 1)[0] for value in berlin.values()}),
        ({"2026-09-22 16:21 PDT"}, {"2026-09-22 16:21 PDT"}, {"2026-09-23 01:21"}),
    )
    return


def test_a_missing_time_is_a_dash_and_text_that_is_not_a_time_is_left_alone(browser: Browser):
    """
    **Feature: bundle date-times (XC-14)**
    **Property: null and the empty string read as an em dash, and "soon"
    is shown as "soon", in every bundle.**
    """
    modules = [list(pair) for pair in FORMATTERS]
    results = [_run(browser, FORMAT_ALL_JS, [modules, value], **PACIFIC) for value in (None, "", "soon")]

    testbase.assert_equal(
        [set(result.values()) for result in results],
        [{"—"}, {"—"}, {"soon"}],
    )
    return


def test_the_as_of_stamp_is_24_hour_with_the_zone(browser: Browser):
    """
    **Feature: bundle date-times (XC-14)**
    **Property: the pods views' "as of" clock reads "16:21:05 PDT" for a
    Pacific viewer, where it read "4:21:05 PM".**
    """
    shown = _run(
        browser,
        """async () => {
            const loaded = await import('/static/javascript/pyc-pods-bundle/pods-list-view.js');
            return loaded.format_clock_time(new Date(Date.UTC(2026, 8, 22, 23, 21, 5)));
        }""",
        None,
        **PACIFIC,
    )

    testbase.assert_equal(shown, "16:21:05 PDT")
    return


def test_no_bundle_source_formats_a_time_with_the_locale_any_more():
    """
    **Feature: bundle date-times (XC-14)**
    **Property: no bundle source (or built bundle) under static/javascript
    calls toLocaleString, toLocaleTimeString or toLocaleDateString.**
    """
    root = os.path.join(SITE_DIRECTORIES.DIR_STATIC, "javascript")
    found = []
    for dirpath, _dirnames, filenames in os.walk(root):
        if "pyc-mj-lib" in dirpath:
            continue
        for name in filenames:
            if not name.endswith(".js"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for call in ("toLocaleString(", "toLocaleTimeString(", "toLocaleDateString("):
                if call in text:
                    found.append((os.path.relpath(path, root), call))

    testbase.assert_equal(found, [])
    return
