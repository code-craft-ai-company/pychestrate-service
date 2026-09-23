"""
.. module:: test_p31h_adm_admin_table_layout_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Row actions stay reachable and headers stay over their
               columns on the Sessions and Secrets tables (audit ADM-14).

.. moduleauthor:: Code Craft AI LLC

At 1440px the Sessions page's Terminate button sat at x~1526 and the
Secrets page's Reveal / Rotate / Delete buttons were off-screen; the
Secrets grid (``mj-data-table``) scrolled its rows sideways under a
header that stayed put, so values sat under the wrong headings. The
Sessions page now pins its Actions column and keeps its cells compact;
the Secrets view renders a native table (header and rows in one scroll
container) with a pinned Actions column. The live layout was checked
in Chromium; these tests pin the pieces that produce it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from datetime import datetime, timedelta, timezone

from ccai import testbase

from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    get,
)


_NOW = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)

_SECRETS_BUNDLE_DIR = os.path.join(
    SITE_DIRECTORIES.DIR_STATIC, "javascript", "pyc-secrets-bundle"
)


def _read_bundle_file(*, name: str) -> str:
    with open(os.path.join(_SECRETS_BUNDLE_DIR, name), encoding="utf-8") as handle:
        rtnval = handle.read()
    return rtnval


def _describe(*, value: datetime) -> str:
    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_sessions import (  # noqa: E402
        describe_relative_time,
    )
    rtnval = describe_relative_time(value=value, now=_NOW)
    return rtnval


def _sessions_page() -> str:
    response = get(path="/admin/sessions", cookies=admin_cookies())
    testbase.assert_equal(response.status_code, 200)
    rtnval = response.text
    return rtnval


def test_the_sessions_actions_column_is_pinned():
    """
    **Feature: admin table layout (ADM-14)**
    **Property: the Sessions Actions header and cells carry the class
    the page pins to the right edge of the scroll container.**
    """
    text = _sessions_page()
    testbase.assert_true(
        '<th scope="col" class="pyc-sessions-actions">Actions</th>' in text,
        "actions header not pinned",
    )
    testbase.assert_true('<td class="pyc-sessions-actions">' in text, "actions cell not pinned")
    rule = re.search(r"\.pyc-sessions-actions\s*\{[^}]*position:\s*sticky", text)
    testbase.assert_true(rule is not None, "no sticky rule for the actions column")
    return


def test_the_sessions_times_read_relative_to_now():
    """
    **Feature: admin table layout (ADM-14)**
    **Property: a fresh session reads "just now" / "in 29 min"-style
    times instead of three wrapping full timestamps.**
    """
    text = _sessions_page()
    testbase.assert_true("just now" in text, "last-active time is not relative")
    testbase.assert_true(re.search(r"in (29|30) min", text) is not None, "end time is not relative")
    return


def test_relative_time_in_minutes():
    """
    **Feature: admin table layout (ADM-14)**
    **Property: an instant 4 minutes ago reads "4 min ago".**
    """
    testbase.assert_equal(
        _describe(value=_NOW - timedelta(minutes=4, seconds=10)),
        "4 min ago",
    )
    return


def test_relative_time_in_hours_and_minutes():
    """
    **Feature: admin table layout (ADM-14)**
    **Property: a future instant reads "in 2 h 5 min".**
    """
    testbase.assert_equal(
        _describe(value=_NOW + timedelta(hours=2, minutes=5)),
        "in 2 h 5 min",
    )
    return


def test_relative_time_treats_naive_values_as_utc():
    """
    **Feature: admin table layout (ADM-14)**
    **Property: a naive timestamp (as SQLite returns) under a minute
    old reads "just now".**
    """
    naive = (_NOW - timedelta(seconds=20)).replace(tzinfo=None)
    testbase.assert_equal(_describe(value=naive), "just now")
    return


def test_the_secrets_view_no_longer_uses_the_drifting_grid():
    """
    **Feature: admin table layout (ADM-14)**
    **Property: the Secrets view builds a native table (header and rows
    in one scroll container), not the mj-data-table grid whose header
    does not scroll with its rows.**
    """
    source = _read_bundle_file(name="secrets-view.js")
    testbase.assert_equal('createElement("mj-data-table")' in source, False)
    testbase.assert_true('createElement("table")' in source, "no native table")
    testbase.assert_true('createElement("thead")' in source, "no table header")
    return


def test_the_secrets_actions_column_is_pinned():
    """
    **Feature: admin table layout (ADM-14)**
    **Property: the Secrets stylesheet pins the Actions column to the
    right edge of the table region.**
    """
    css = _read_bundle_file(name="pyc-secrets-bundle.css")
    rule = re.search(r"\.pyc-secrets__col-actions\s*\{[^}]*position:\s*sticky", css)
    testbase.assert_true(rule is not None, "no sticky rule for the secrets actions column")
    return


def test_the_served_secrets_bundle_is_rebuilt_from_the_source():
    """
    **Feature: admin table layout (ADM-14)**
    **Property: the committed bundle the browser loads carries the
    native table, not the old grid.**
    """
    built = _read_bundle_file(name="index.js")
    testbase.assert_equal('createElement("mj-data-table")' in built, False)
    testbase.assert_true("_build_header_cell" in built, "bundle not rebuilt")
    return
