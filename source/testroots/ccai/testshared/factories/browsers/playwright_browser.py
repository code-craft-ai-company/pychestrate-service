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


import os

from typing import Any, Dict, Generator, Optional

from playwright.sync_api import Browser, sync_playwright

from ccai import testbase


DEFAULT_BROWSER: str = "chromium"
DEFAULT_HEADLESS: bool = True
DEFAULT_SLOW_MO_MS: int = 0

#: Env vars that override the defaults at run time without editing the
#: per-phase ``originate.parameter`` call. An explicit ``constraints``
#: value still wins over the env var (per-test intent beats run-wide
#: toggle); the env var beats the hard default.
ENV_HEADLESS: str = "PYCHESTRATE_TEST_HEADLESS"
ENV_SLOW_MO_MS: str = "PYCHESTRATE_TEST_SLOW_MO"


def _resolve_headless(*, constraint_map: Dict[str, Any]) -> bool:
    """
        Resolve the headless flag: explicit constraint wins, then the
        :data:`ENV_HEADLESS` env var (``0``/``false``/``no`` ->
        headed), then :data:`DEFAULT_HEADLESS`.

        :param constraint_map: Resolved constraint dict.

        :returns: Whether to launch headless.
    """
    if "headless" in constraint_map:
        rtnval = bool(constraint_map["headless"])
        return rtnval
    raw = os.environ.get(ENV_HEADLESS, None)
    if raw is not None and len(raw) > 0:
        normalized = raw.strip().lower()
        rtnval = normalized not in ("0", "false", "no")
        return rtnval
    rtnval = DEFAULT_HEADLESS
    return rtnval


def _resolve_slow_mo_ms(*, constraint_map: Dict[str, Any]) -> int:
    """
        Resolve the slow-motion delay (milliseconds Playwright waits
        between operations so a human can watch): explicit constraint
        wins, then the :data:`ENV_SLOW_MO_MS` env var, then
        :data:`DEFAULT_SLOW_MO_MS` (0 = full speed).

        :param constraint_map: Resolved constraint dict.

        :returns: Slow-motion delay in milliseconds.
    """
    if "slow_mo" in constraint_map:
        rtnval = int(constraint_map["slow_mo"])
        return rtnval
    raw = os.environ.get(ENV_SLOW_MO_MS, None)
    if raw is not None and len(raw) > 0:
        try:
            rtnval = int(raw.strip())
            return rtnval
        except ValueError:
            rtnval = DEFAULT_SLOW_MO_MS
            return rtnval
    rtnval = DEFAULT_SLOW_MO_MS
    return rtnval


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

    headless = _resolve_headless(constraint_map=constraint_map)
    slow_mo_ms = _resolve_slow_mo_ms(constraint_map=constraint_map)
    browser_name = str(constraint_map.get("browser", DEFAULT_BROWSER))

    playwright_handle = sync_playwright().start()
    try:
        browser_type = getattr(playwright_handle, browser_name)
        browser = browser_type.launch(headless=headless, slow_mo=slow_mo_ms)
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
    "DEFAULT_SLOW_MO_MS",
    "ENV_HEADLESS",
    "ENV_SLOW_MO_MS",
    "create_playwright_browser",
]
