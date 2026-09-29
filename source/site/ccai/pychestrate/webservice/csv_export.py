"""
.. module:: csv_export
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: CSV attachments that are safe to open in a spreadsheet (ORG-F22).

.. moduleauthor:: Code Craft AI LLC

A manager or an auditor wants a list in a spreadsheet. This module turns rows
into a CSV attachment, and makes every cell safe to open: a value that starts
with ``=``, ``+``, ``-``, ``@``, a tab or a carriage return would be read by a
spreadsheet as a formula, so it is written with a leading apostrophe. A run's
job name is chosen by whoever wrote the job, so it is not trusted.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import csv
import io

from typing import Any, Dict, Iterable, List, Sequence

from ccai.webworks.routing.response import Response


#: Characters that make a spreadsheet read a cell as a formula.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def spreadsheet_safe(value: Any) -> str:
    """
        A cell's text, defused against formula injection.

        :param value: Any cell value; ``None`` is an empty cell.

        :returns: The text to write.
    """
    if value is None:
        return ""
    text = str(value)
    if text.startswith(FORMULA_PREFIXES):
        return "'" + text
    return text


def render_csv(*, columns: Sequence[str], rows: Iterable[Dict[str, Any]]) -> bytes:
    """
        Serialise rows (dicts keyed by column name) as UTF-8 CSV with a header.

        :param columns: Column names, in order.
        :param rows: Row dictionaries; a missing key is an empty cell.

        :returns: The file body.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(list(columns))
    for row in rows:
        writer.writerow([spreadsheet_safe(row.get(column, None)) for column in columns])
    return buffer.getvalue().encode("utf-8")


def csv_response(*, filename: str, body: bytes, truncated: bool = False) -> Response:
    """
        A CSV download.

        :param filename: The suggested file name.
        :param body: The file body.
        :param truncated: ``True`` when the export stopped at its row limit
                          (also sent as ``X-Export-Truncated``).

    :returns: A 200 response with an attachment disposition.
    """
    headers: Dict[str, str] = {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="{}"'.format(filename),
        "Cache-Control": "no-store",
    }
    if truncated:
        headers["X-Export-Truncated"] = "true"
    return Response(status_code=200, body=body, headers=headers)


__all__: List[str] = ["FORMULA_PREFIXES", "csv_response", "render_csv", "spreadsheet_safe"]
