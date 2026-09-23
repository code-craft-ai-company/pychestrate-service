"""
.. module:: test_p24r_resources_bundle_timestamps_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The resources bundle's timestamp formatter, run in a real
               Chromium set to a given time zone (audit finding RES-20).

.. moduleauthor:: Code Craft AI LLC

The resources views formatted REST timestamps with ``new Date(value)
.toLocaleString()``. A timestamp without an offset is local time to
``Date``, so in Los Angeles a pool created at 23:34 UTC (16:34 PDT) showed
as "9/22/2026, 11:34:26 PM". ``format_timestamp`` now reads an offset-less
timestamp as UTC and prints the glossary form in the viewer's zone with the
zone spelled out.

These tests load the served, prebuilt bundle (``index.js``) into a blank
page, so they also catch a bundle that was not rebuilt. No server is
needed.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, List

from playwright.sync_api import Browser

from ccai import testbase

from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES


RESOURCES_BUNDLE_PATH: str = os.path.join(
    SITE_DIRECTORIES.DIR_STATIC, "javascript", "pyc-resources-bundle", "index.js"
)


def _format_in_zone(*, browser: Browser, zone: str, values: List[Any]) -> List[str]:
    """
        Run the built bundle's ``format_timestamp`` over ``values`` in a
        page whose clock is set to ``zone`` (en-US locale).
    """
    with open(RESOURCES_BUNDLE_PATH, "r", encoding="utf-8") as bundle_file:
        source = bundle_file.read()
    context = browser.new_context(timezone_id=zone, locale="en-US")
    try:
        page = context.new_page()
        page.set_content("<!doctype html><html><head></head><body></body></html>")
        page.add_script_tag(
            content=source + "\nwindow.__pycFormatTimestamp = format_timestamp;\n",
            type="module",
        )
        page.wait_for_function("() => typeof window.__pycFormatTimestamp === 'function'")
        rtnval = page.evaluate("(values) => values.map((v) => window.__pycFormatTimestamp(v))", values)
    finally:
        context.close()
    return rtnval


def test_offsetless_timestamp_is_read_as_utc(browser: Browser):
    """
    **Feature: resources (RES-20 bundle timestamps)**
    **Property: in Los Angeles, the offset-less timestamp
    2026-09-22T23:34:26.123456 (UTC) is shown as 2026-09-22 16:34 PDT,
    not shifted to 23:34 local.**
    """
    shown = _format_in_zone(browser=browser, zone="America/Los_Angeles", values=["2026-09-22T23:34:26.123456"])

    testbase.assert_equal(shown, ["2026-09-22 16:34 PDT"])
    return


def test_timestamp_with_an_offset_is_shown_in_the_viewers_zone(browser: Browser):
    """
    **Feature: resources (RES-20 bundle timestamps)**
    **Property: an RFC 3339 timestamp with +00:00 is shown in the
    viewer's zone with the zone named (Los Angeles: 16:34 PDT).**
    """
    shown = _format_in_zone(browser=browser, zone="America/Los_Angeles", values=["2026-09-22T23:34:26+00:00"])

    testbase.assert_equal(shown, ["2026-09-22 16:34 PDT"])
    return


def test_timestamp_crosses_the_date_line_in_the_viewers_zone(browser: Browser):
    """
    **Feature: resources (RES-20 bundle timestamps)**
    **Property: 23:34 UTC on 22 September is shown on 23 September for a
    viewer in Tokyo (08:34 the next day).**
    """
    shown = _format_in_zone(browser=browser, zone="Asia/Tokyo", values=["2026-09-22T23:34:26Z"])

    testbase.assert_equal(shown[0].startswith("2026-09-23 08:34 "), True)
    return


def test_missing_timestamp_is_a_dash(browser: Browser):
    """
    **Feature: resources (RES-20 bundle timestamps)**
    **Property: a missing timestamp renders as an em dash.**
    """
    shown = _format_in_zone(browser=browser, zone="UTC", values=[None])

    testbase.assert_equal(shown, ["—"])
    return
