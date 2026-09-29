"""
.. module:: test_p31zzzn_charts_and_tiles_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Charts read as times, are named, and dashboard tiles are what they say they are (ORC-15).

.. moduleauthor:: Code Craft AI LLC

The chart component draws an x value as the text it is given, so the raw ISO
timestamps ("2026-09-29T10:00:00.000Z") were printed in full and overprinted each
other. Axis labels are now times of day (or "MM-DD HH:MM" for a series longer than
a day) in the viewer's zone; the chart has an accessible name and, on the
timeseries page, a title. On a dashboard, a "single number" tile shows its latest
value instead of a chart, a tile keeps the range it was configured with, and tile
titles show the metric as words with the storage name on hover. The real pages
are opened in a browser against stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import datetime
import re

from typing import Any, Dict, List

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


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

PROJECT_ID: str = "0f6c2c1e-bbbb-4000-8000-000000000001"
BOARD_ID: str = "0f6c2c1e-bbbb-4000-8000-0000000000d1"
METRIC: str = "pychestrate_resource_reservation_granted_total"
START = datetime.datetime(2026, 9, 29, 10, 0, 0, tzinfo=datetime.timezone.utc)

TICK_TEXTS = """() => {
    const chart = document.querySelector('mj-chart');
    const texts = [...chart.shadowRoot.querySelectorAll('svg text')];
    return texts.map((t) => {const r = t.getBoundingClientRect(); return {text: t.textContent, left: r.left, right: r.right};});
}"""


def _points(count: int, step_minutes: int) -> List[Dict[str, Any]]:
    return [
        {"observed_at": (START + datetime.timedelta(minutes=step_minutes * index)).isoformat(), "value": float(5 + index % 7)}
        for index in range(count)
    ]


def _timeseries_page(browser: Browser, points: List[Dict[str, Any]]) -> Any:
    page = open_shell_page(
        browser, path="/timeseries", bundle_names=["pyc-site-shell", "pyc-metrics-bundle"],
        api_stubs={
            "/api/v1/metrics/catalog": {"items": [{"name": METRIC, "kind": "counter"}]},
            "/api/v1/metrics/timeseries": {"points": points, "metric": METRIC},
        },
        **DESKTOP,
    )
    page.wait_for_selector("mj-chart", timeout=8000)
    page.wait_for_timeout(1500)
    return page


def _x_ticks(page: Any, pattern: str) -> List[Dict[str, Any]]:
    return [tick for tick in page.evaluate(TICK_TEXTS) if re.match(pattern, tick["text"])]


def test_the_time_axis_reads_as_times_and_no_label_overprints_another(browser: Browser):
    """
    **Feature: chart axes (ORC-15)**
    **Property: a two-hour series has "HH:MM" labels (no "T", "Z" or zone text),
    a series over three days has "MM-DD HH:MM" labels, and in both no two labels
    overlap horizontally.**
    """
    page = _timeseries_page(browser, _points(24, 5))
    try:
        same_day = _x_ticks(page, r"^\d{2}:\d{2}$")
        raw = [tick["text"] for tick in page.evaluate(TICK_TEXTS) if "T" in tick["text"] or "Z" in tick["text"] or "GMT" in tick["text"]]
    finally:
        page.context.close()
    page = _timeseries_page(browser, _points(37, 120))
    try:
        multi_day = _x_ticks(page, r"^\d{2}-\d{2} \d{2}:\d{2}$")
    finally:
        page.context.close()

    def overlaps(ticks: List[Dict[str, Any]]) -> bool:
        ordered = sorted(ticks, key=lambda tick: tick["left"])
        return any(ordered[i]["right"] > ordered[i + 1]["left"] for i in range(len(ordered) - 1))

    testbase.assert_equal(
        (len(same_day) >= 4, raw, overlaps(same_day), len(multi_day) >= 4, overlaps(multi_day)),
        (True, [], False, True, False),
    )
    return


def test_the_chart_has_an_accessible_name_and_the_page_gives_it_a_title(browser: Browser):
    """
    **Feature: chart axes (ORC-15)**
    **Property: the chart figure is named "<metric as words> over time, times in
    <zone>", and the timeseries page shows the metric as words as its title with
    the range and the zone as its subtitle; the raw ``pychestrate_...`` name is not
    the title.**
    """
    page = _timeseries_page(browser, _points(24, 5))
    try:
        info = page.evaluate(
            """() => {
                const chart = document.querySelector('mj-chart');
                const title = chart.querySelector('mj-chart-title');
                const root = title.shadowRoot;
                return {label: chart.getAttribute('aria-label'), role: chart.getAttribute('role'),
                        title: root.querySelector('.title').textContent, subtitle: root.querySelector('.subtitle').textContent};
            }"""
        )
    finally:
        page.context.close()

    testbase.assert_equal(
        (info["role"], re.match(r"^Resource reservation granted total over time, times in .+$", info["label"]) is not None, info["title"], re.match(r"^Last 24 hours · times in .+$", info["subtitle"]) is not None),
        ("figure", True, "Resource reservation granted total", True),
    )
    return


def _tile(tile_id: str, kind: str, metric: str, range_seconds: Any = None) -> Dict[str, Any]:
    config: Dict[str, Any] = {"metric_name": metric, "label_filter": {}}
    if range_seconds is not None:
        config["range_seconds"] = range_seconds
    return {"tile_id": tile_id, "kind": kind, "x": 0, "y": 0, "w": 1, "h": 1, "config": config}


def test_a_single_number_tile_shows_its_latest_value_and_tiles_keep_their_ranges(browser: Browser):
    """
    **Feature: dashboard tiles (ORC-15)**
    **Property: a "single number" tile shows the latest value (42.5, not the
    earlier ones) with when it was read and no chart; a line chart tile draws a
    chart; each tile asks for the range it was configured with (1 hour, 2 hours,
    and 7 days when it has none); tile titles are the metric as words with the
    storage name on hover.**
    """
    asked: Dict[str, Dict[str, str]] = {}

    def series(query: Dict[str, str]) -> Any:
        asked[query["metric"]] = query
        points = [
            {"observed_at": "2026-09-29T10:00:00+00:00", "value": 7.0},
            {"observed_at": "2026-09-29T12:00:00+00:00", "value": 42.5},
            {"observed_at": "2026-09-29T11:00:00+00:00", "value": 9.0},
        ]
        return {"points": points, "metric": query["metric"]}

    board = {
        "dashboard_id": BOARD_ID, "project_id": PROJECT_ID, "name": "Ops", "version": 1, "tiles": [
            _tile("t1", "metric-single-stat", "pychestrate_stat_metric", 3600),
            _tile("t2", "metric-line-chart", "pychestrate_chart_metric", 7200),
            _tile("t3", "metric-line-chart", "pychestrate_default_metric"),
        ],
    }
    page = open_shell_page(
        browser, path="/dashboards/{}?project_id={}".format(BOARD_ID, PROJECT_ID), bundle_names=["pyc-site-shell", "pyc-metrics-bundle"],
        api_stubs={
            "/api/v1/projects/{}/dashboards/{}".format(PROJECT_ID, BOARD_ID): board,
            "/api/v1/metrics/timeseries": series,
        },
        **DESKTOP,
    )
    try:
        page.wait_for_selector('[data-role="tile-stat-value"]', timeout=8000)
        page.wait_for_selector('[data-role="dashboard-tile"] mj-chart')
        tiles = page.locator('[data-role="dashboard-tile"]')
        stat_tile = tiles.nth(0)
        info = {
            "titles": [tiles.nth(index).locator(".pyc-metrics__tile-title").inner_text() for index in range(3)],
            "hover": tiles.nth(0).locator(".pyc-metrics__tile-title").get_attribute("title"),
            "value": stat_tile.locator('[data-role="tile-stat-value"]').inner_text(),
            "caption": stat_tile.locator(".pyc-metrics__stat-caption").inner_text(),
            "stat_has_chart": stat_tile.locator("mj-chart").count(),
            "charts": [tiles.nth(index).locator("mj-chart").count() for index in (1, 2)],
        }
    finally:
        page.context.close()

    def span_seconds(metric: str) -> int:
        query = asked[metric]
        start = datetime.datetime.fromisoformat(query["from"].replace("Z", "+00:00"))
        end = datetime.datetime.fromisoformat(query["to"].replace("Z", "+00:00"))
        return round((end - start).total_seconds())

    testbase.assert_equal(
        (
            info["titles"], info["hover"], info["value"], re.match(r"^as of \d{2}:\d{2}:\d{2} .+$", info["caption"]) is not None, info["stat_has_chart"], info["charts"],
            span_seconds("pychestrate_stat_metric"), span_seconds("pychestrate_chart_metric"), span_seconds("pychestrate_default_metric"),
        ),
        (["Stat metric", "Chart metric", "Default metric"], "pychestrate_stat_metric", "42.5", True, 0, [1, 1], 3600, 7200, 7 * 24 * 3600),
    )
    return


def test_the_editor_shows_a_tile_as_words_and_its_kind_by_name(browser: Browser):
    """
    **Feature: dashboard tiles (ORC-15)**
    **Property: the editor's tile card reads "<metric as words> · Line chart"
    (not the storage name and "metric-line-chart"), with the storage name on hover.**
    """
    board = {
        "dashboard_id": BOARD_ID, "project_id": PROJECT_ID, "name": "Ops", "version": 1,
        "tiles": [_tile("t1", "metric-line-chart", METRIC), _tile("t2", "metric-single-stat", "pychestrate_stat_metric")],
    }
    page = open_shell_page(
        browser, path="/dashboards/{}/edit?project_id={}".format(BOARD_ID, PROJECT_ID), bundle_names=["pyc-site-shell", "pyc-metrics-bundle"],
        api_stubs={"/api/v1/projects/{}/dashboards/{}".format(PROJECT_ID, BOARD_ID): board, "/api/v1/metrics/catalog": {"items": [{"name": METRIC, "kind": "counter"}]}},
        **DESKTOP,
    )
    try:
        page.wait_for_selector(".pyc-metrics__tile-title", timeout=8000)
        titles = [page.locator(".pyc-metrics__tile-title").nth(index).inner_text() for index in range(2)]
        hover = page.locator(".pyc-metrics__tile-title").first.get_attribute("title")
    finally:
        page.context.close()

    testbase.assert_equal(
        (titles, hover),
        (["Resource reservation granted total · Line chart", "Stat metric · Single number"], METRIC),
    )
    return
