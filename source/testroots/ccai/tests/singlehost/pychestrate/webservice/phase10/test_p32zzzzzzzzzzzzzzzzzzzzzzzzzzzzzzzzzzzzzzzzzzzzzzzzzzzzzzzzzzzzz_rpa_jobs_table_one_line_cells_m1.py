"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_rpa_jobs_table_one_line_cells_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The RPA jobs table keeps a job's id, type, status, time and link on one line each.

.. moduleauthor:: Code Craft AI LLC

With real jobs the table broke each id into three lines ("bed / 376 / e1") and wrapped the type and the time, because nine columns did not fit and every cell may break anywhere. The short-value cells are
now marked ``nowrap`` (the long specification name absorbs the squeeze), the mode and a second "View" button (the id already links to the job) are gone, and the version sits beside the type.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from ccai import testbase

from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES


def _template() -> str:
    path = os.path.join(os.path.dirname(SITE_DIRECTORIES.DIR_STATIC), "blueprints", "projects", "templates", "projects", "rpa", "list.html")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_the_columns_are_the_seven_that_fit_and_every_short_cell_keeps_its_line():
    """
    **Feature: RPA jobs list layout**
    **Property: the headers are Job, Specification, Type, Status, Duration, Started and Logs; of a job's seven cells every one but the specification's is marked ``nowrap``; the empty
    row spans all seven; the job's id is the link to it and the only row action is Logs.**
    """
    html = _template()
    headers = re.findall(r'<th scope="col">([^<]*)</th>', html)
    before_empty, after_empty = html.split('<td colspan="', 1)
    row = before_empty.split("{% for job in jobs %}", 1)[1]
    cells = re.findall(r"<td([^>]*)>", row)
    colspan = re.match(r"(\d+)", after_empty).group(1)

    testbase.assert_equal(
        (headers, ["nowrap" in cell for cell in cells], colspan, row.count("rpa_detail"), row.count("rpa_logs"), "btn" in row.split("rpa_logs")[1].split(">")[0]),
        (
            ["Job", "Specification", "Type", "Status", "Duration", "Started", "Logs"],
            [True, False, True, True, True, True, True],
            "7", 1, 1, False,
        ),
    )
    return
