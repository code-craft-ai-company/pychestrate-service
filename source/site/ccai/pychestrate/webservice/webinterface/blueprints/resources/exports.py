"""
.. module:: webinterface.blueprints.resources.exports
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Spreadsheet downloads for the lab lists (audit finding ORG-F22).

.. moduleauthor:: Code Craft AI LLC

A lab manager or an auditor wants the inventory, the bookings and the allocation history in a spreadsheet, not a page at a time. The Resources,
Reservations and Allocation History pages (and Roles, in its own module) download the whole filtered list as CSV with ``?format=csv``.

What every export does, so a person can rely on it:

* it holds **every** row the page's filters match, not one page, up to :data:`EXPORT_MAX_ROWS`; a longer list is cut and the response says so
  (``X-Export-Truncated: true``);
* every cell is written so a spreadsheet cannot read it as a formula (a device name or a reservation's reason is typed by a person);
* it needs the same permission as the page, and carries the page's filters;
* it holds nothing a person could not read on the page: a resource's metadata (which can hold addresses and credentials) is not exported.

The functions take plain data and return plain data, so they are tested without a database.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlencode


#: The most rows one export holds; the file says when it was cut.
EXPORT_MAX_ROWS: int = 5000

#: How many rows to read from the manager per call.
EXPORT_PAGE_SIZE: int = 200

RESOURCE_COLUMNS: Tuple[str, ...] = (
    "name", "type", "pool", "health", "in_use", "capacity", "tags", "description", "created_at",
)

ALLOCATION_COLUMNS: Tuple[str, ...] = (
    "id", "resource", "resource_type", "user", "job_id", "mode", "status", "checked_out", "expected_check_in", "checked_in",
    "duration_minutes", "reason", "forced_by", "force_reason",
)

RESERVATION_COLUMNS: Tuple[str, ...] = (
    "id", "resource", "user", "job_id", "mode", "status", "start", "end", "reason", "created_at",
)


def wants_csv(raw_format: Any) -> bool:
    """
        Whether ``?format=`` asks for a spreadsheet.

        :param raw_format: The raw query value or ``None``.

        :returns: ``True`` for ``csv`` (any case).
    """
    return str(raw_format or "").strip().lower() == "csv"


def collect_rows(fetch_page: Callable[[int, int], Tuple[List[Any], int]]) -> Tuple[List[Any], bool]:
    """
        Read every row of a paged list, up to :data:`EXPORT_MAX_ROWS`.

        :param fetch_page: ``(offset, limit) -> (rows, total)`` for the page's filters.

        :returns: ``(rows, truncated)``; ``truncated`` is ``True`` when more rows matched than were kept.
    """
    rows: List[Any] = []
    total = 0
    while len(rows) <= EXPORT_MAX_ROWS:
        page, total = fetch_page(len(rows), min(EXPORT_PAGE_SIZE, EXPORT_MAX_ROWS + 1 - len(rows)))
        if len(page) == 0:
            break
        rows.extend(page)
        if len(rows) >= total:
            break
    return rows[:EXPORT_MAX_ROWS], len(rows) > EXPORT_MAX_ROWS


def _when(value: Optional[datetime]) -> str:
    return value.isoformat() if value is not None else ""


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def resource_records(resources: Iterable[Any]) -> List[Dict[str, Any]]:
    """
        Resources as export rows. A resource's metadata is left out on purpose: it can hold addresses and credentials.

        :param resources: ``ResourceResponse`` items.

        :returns: One record per resource, keyed by :data:`RESOURCE_COLUMNS`.
    """
    return [
        {
            "name": item.name, "type": _text(item.resource_type), "pool": _text(item.pool_name), "health": _text(item.health_status),
            "in_use": item.current_allocations, "capacity": item.capacity, "tags": "; ".join(sorted(item.tags or [])),
            "description": _text(item.description), "created_at": _when(item.created_at),
        }
        for item in resources
    ]


def allocation_records(allocations: Iterable[Any]) -> List[Dict[str, Any]]:
    """
        Allocations as export rows.

        :param allocations: ``AllocationResponse`` items.

        :returns: One record per allocation, keyed by :data:`ALLOCATION_COLUMNS`.
    """
    return [
        {
            "id": item.id, "resource": item.resource_name, "resource_type": _text(item.resource_type), "user": _text(item.username),
            "job_id": _text(item.job_id), "mode": _text(item.mode), "status": _text(item.status), "checked_out": _when(item.checkout_time),
            "expected_check_in": _when(item.expected_checkin), "checked_in": _when(item.actual_checkin),
            "duration_minutes": "" if item.duration_minutes is None else item.duration_minutes, "reason": _text(item.reason),
            "forced_by": _text(item.forced_by), "force_reason": _text(item.force_reason),
        }
        for item in allocations
    ]


def reservation_records(reservations: Iterable[Any]) -> List[Dict[str, Any]]:
    """
        Reservations as export rows.

        :param reservations: ``ReservationResponse`` items.

        :returns: One record per reservation, keyed by :data:`RESERVATION_COLUMNS`.
    """
    return [
        {
            "id": item.id, "resource": item.resource_name, "user": _text(item.username), "job_id": _text(item.job_id),
            "mode": _text(item.mode), "status": _text(item.status), "start": _when(item.start_time), "end": _when(item.end_time),
            "reason": _text(item.reason), "created_at": _when(item.created_at),
        }
        for item in reservations
    ]


def csv_download(*, base_name: str, columns: Sequence[str], records: Iterable[Dict[str, Any]], truncated: bool) -> Any:
    """
        Wrap export rows as a CSV attachment named ``pychestrate-<base_name>-<date>.csv``.

        :param base_name: What the file holds (``resources``, ``reservations``, ...).
        :param columns: The header, in order.
        :param records: One dict per row.
        :param truncated: Whether the list was cut at :data:`EXPORT_MAX_ROWS`.

        :returns: The download response.
    """
    from ccai.pychestrate.webservice.csv_export import csv_response, render_csv  # noqa: E402

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return csv_response(
        filename="pychestrate-{}-{}.csv".format(base_name, stamp), body=render_csv(columns=columns, rows=records), truncated=truncated,
    )


def export_url(path: str, params: Iterable[Tuple[str, Any]]) -> str:
    """
        The address of a list's CSV: its path, the filters that are set, and ``format=csv``.

        :param path: The list's path.
        :param params: ``(name, value)`` pairs; those with no value are left out.

        :returns: ``path?...&format=csv``.
    """
    kept = [(name, str(value)) for name, value in params if value is not None and str(value) != ""]
    return path + "?" + urlencode(kept + [("format", "csv")])


__all__ = [
    "ALLOCATION_COLUMNS",
    "EXPORT_MAX_ROWS",
    "EXPORT_PAGE_SIZE",
    "RESERVATION_COLUMNS",
    "RESOURCE_COLUMNS",
    "allocation_records",
    "collect_rows",
    "csv_download",
    "export_url",
    "reservation_records",
    "resource_records",
    "wants_csv",
]
