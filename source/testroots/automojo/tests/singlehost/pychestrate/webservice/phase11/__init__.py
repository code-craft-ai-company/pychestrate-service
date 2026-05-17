"""
.. module:: automojo.tests.singlehost.pychestrate.webservice.phase11
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase-11 tests -- deployed-UI smoke + browser-
               driven end-to-end against a live pychestrate
               instance.

.. moduleauthor:: Automation Mojo LLC

Phase 10 covers in-process, no-network unit + e2e against the
WSGI app via :mod:`_e2e_harness`. Phase 11 picks up where that
leaves off: tests that drive real HTTP to a running deploy.

Targets a deployed instance (default ``http://tc-app-server/``;
override via ``PYCHESTRATE_TEST_BASE_URL``). The same suite runs
from a developer Mac, GitHub Actions, or any host that can
reach the target URL.

Two test cohorts:

* ``test_p15a_*`` -- httpx-based HTTP smoke. Fast, no browser
  binary required. Covers status codes, redirect chains,
  cookie roundtrips, JSON contracts.
* ``test_p15b_*`` -- Playwright browser-driven e2e. Renders
  pages with real CSS / JS execution, asserts on title /
  visible elements / form interactions. Slower but catches
  regressions httpx tests cannot.

The browser is originated at SESSION scope below so a single
Playwright launch (~1 second) is amortized across every
phase-11 browser test. Each test takes a fresh
``BrowserContext`` for cookie isolation.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase
from automojo.testbase.resourcelifespan import ResourceLifespan

from automojo.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
    life_span=ResourceLifespan.Session,
)
