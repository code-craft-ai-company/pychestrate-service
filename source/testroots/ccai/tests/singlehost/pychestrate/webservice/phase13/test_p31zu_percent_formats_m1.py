"""
.. module:: test_p31zu_percent_formats_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SLO and test-rate percentages never read better than they are (ORC-36).

.. moduleauthor:: Code Craft AI LLC

The SLO views rounded every ratio to 0.1% (``toFixed(1)``), so an objective of
99.95% read "100.0%", and the test-metrics views rounded pass, fail and
failed-run rates to whole percents, so a 99.6% pass rate read "100%" and a
0.4% failure rate "0%". The formatters now cut (not round) high ratios to the
precision their nines need, and a rate that is not exactly 0 or 1 reads "<1%"
or ">99%". The real ES modules are imported in a browser and called.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Tuple

from playwright.sync_api import Browser

from ccai import testbase

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


RATIOS: List[Tuple[Any, str]] = [
    (0.9995, "99.95%"),
    (0.99996, "99.996%"),
    (0.9999999, "99.999%"),
    (0.999, "99.9%"),
    (0.995, "99.5%"),
    (0.99, "99.0%"),
    (0.95, "95.0%"),
    (0.12345, "12.3%"),
    (0.5, "50.0%"),
    (1, "100%"),
    (0, "0%"),
    (None, "—"),
    ("x", "—"),
]

RATES: List[Tuple[Any, str]] = [
    (0.996, ">99%"),
    (0.9999, ">99%"),
    (0.004, "<1%"),
    (0.0001, "<1%"),
    (0, "0%"),
    (1, "100%"),
    (0.5, "50%"),
    (0.994, "99%"),
    (0.01, "1%"),
    (None, "—"),
]


def _call(browser: Browser, module: str, function: str, cases: List[Tuple[Any, str]]) -> List[str]:
    """What the real ES module's ``function`` answers for each input of ``cases``."""
    page = open_shell_page(browser)
    try:
        return page.evaluate(
            """async ([module, fn, values]) => {
                const loaded = await import('/static/javascript/pyc-metrics-bundle/' + module);
                return values.map((v) => loaded[fn](v));
            }""",
            [module, function, [value for value, _expected in cases]],
        )
    finally:
        page.context.close()


def test_an_slo_ratio_is_cut_to_the_precision_its_nines_need_and_never_rounded_up_to_perfect(browser: Browser):
    """
    **Feature: percentage formats (ORC-36)**
    **Property: 99.95% reads "99.95%", 99.996% reads "99.996%" and only
    exactly 1 reads "100%"; ordinary ratios keep one decimal; missing or
    non-numeric values read as a dash.**
    """
    shown = _call(browser, "slos-view.js", "format_ratio", RATIOS)

    testbase.assert_equal(list(zip([value for value, _ in RATIOS], shown)), [(value, expected) for value, expected in RATIOS])
    return


def test_a_test_rate_that_is_not_exactly_zero_or_one_never_reads_as_either(browser: Browser):
    """
    **Feature: percentage formats (ORC-36)**
    **Property: a 99.6% pass rate reads ">99%", a 0.4% failure rate reads
    "<1%", exact 0 and 1 read "0%" and "100%", and everything between keeps
    the whole percent.**
    """
    shown = _call(browser, "test-metrics-view.js", "format_rate", RATES)

    testbase.assert_equal(list(zip([value for value, _ in RATES], shown)), [(value, expected) for value, expected in RATES])
    return
