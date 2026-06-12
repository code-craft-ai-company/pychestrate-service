"""
.. module:: ccai.testshared.factories.browsers.playwright_browser
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Session-scoped Playwright Browser factory for
               testbase-driven UI tests.

.. moduleauthor:: Code Craft AI LLC

Launches one ``sync_playwright().chromium`` process for the
whole test run (Playwright browser launch is ~1 second; sharing
it across tests keeps the suite snappy). Tests take a fresh
``BrowserContext`` per function for cookie isolation.

The factory is wired into the test tree via
``testbase.originate.parameter(...)`` at
``phase11/__init__.py`` (and any other phase that needs a
browser). See ``AGENTS.md`` / ``# Resource Lifespan`` for the
broader pattern.

Constraints supported by ``create_playwright_browser``:

* ``headless`` (bool, default True) -- set False to watch tests
  run locally during debugging.
* ``browser`` (str, default ``"chromium"``) -- one of
  ``"chromium"``, ``"firefox"``, ``"webkit"``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, Generator, Optional

from playwright.sync_api import Browser, sync_playwright

from ccai import testbase


DEFAULT_BROWSER: str = "chromium"
DEFAULT_HEADLESS: bool = True


@testbase.register.resource_factory()
def create_playwright_browser(
        constraints: Optional[Dict[str, Any]] = None,
    ) -> Generator[Browser, None, None]:
    """
        Yield a session-scoped Playwright Browser.

        The Playwright handle is started + the chosen browser
        launched on the way in; on the way out both are closed
        in reverse order. Failures during yield rebroadcast as
        normal exceptions; the cleanup runs from the ``finally``
        branches regardless.

        :param constraints: Optional dict overrides:

            * ``headless`` -- default True; pass False to launch
              with a visible window when debugging locally.
            * ``browser`` -- default ``"chromium"``; alternative
              values ``"firefox"`` or ``"webkit"``.

        :yields: A configured :class:`Browser` instance.
    """
    if constraints is None:
        constraint_map: Dict[str, Any] = {}
    else:
        constraint_map = constraints

    headless = bool(constraint_map.get("headless", DEFAULT_HEADLESS))
    browser_name = str(constraint_map.get("browser", DEFAULT_BROWSER))

    playwright_handle = sync_playwright().start()
    try:
        browser_type = getattr(playwright_handle, browser_name)
        browser = browser_type.launch(headless=headless)
        try:
            yield browser
        finally:
            browser.close()
    finally:
        playwright_handle.stop()
    return


__all__ = [
    "DEFAULT_BROWSER",
    "DEFAULT_HEADLESS",
    "create_playwright_browser",
]
