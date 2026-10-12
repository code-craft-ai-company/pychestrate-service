"""
.. module:: webinterface.blueprints.resources.utilization
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: How much each lab resource was in use over a period (audit finding ORG-F22).

.. moduleauthor:: Code Craft AI LLC

A lab manager's first questions about the equipment are which resources are busy, which sit idle, and
how long people keep them. The allocation pages list who holds what now and what was held, but not that
answer. This module turns allocations into one row per resource over a chosen period.

The numbers are about *time in use*, not a count of check-outs:

* each allocation is clipped to the period (one that began before it, or is still held, counts for the
  part inside it);
* overlapping allocations of one resource are merged before they are added up, so a resource shared by
  three people at the same hour is in use for one hour, not three;
* an allocation with no check-in time ends when its lease expected it to end if it is no longer active,
  and at the end of the period if it still is.

The functions take and return plain data (no database session), so they are tested without one.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


#: The periods the page offers, in days.
PERIOD_CHOICES: Tuple[int, ...] = (7, 30, 90, 365)

#: The period shown when none (or an unknown one) is asked for.
DEFAULT_PERIOD_DAYS: int = 30

#: Columns of the CSV export.
EXPORT_COLUMNS: Tuple[str, ...] = (
    "resource", "pool", "allocations", "hours_in_use", "percent_in_use", "last_checked_out", "period_days",
)


@dataclass(frozen=True)
class ResourceRef:
    """
        A resource as the report needs it.

        :ivar resource_id: The resource's id.
        :ivar name: Its name.
        :ivar pool: The name of the pool it belongs to, or ``""``.
    """
    resource_id: int
    name: str
    pool: str = ""


@dataclass(frozen=True)
class AllocationSpan:
    """
        One allocation as the report needs it.

        :ivar resource_id: The resource that was held.
        :ivar checkout_time: When it was checked out.
        :ivar actual_checkin: When it was checked in, or ``None``.
        :ivar expected_checkin: When the lease was meant to end, or ``None``.
        :ivar status: ``active``, ``released``, ``expired`` or ``forced``.
    """
    resource_id: int
    checkout_time: datetime
    actual_checkin: Optional[datetime] = None
    expected_checkin: Optional[datetime] = None
    status: str = "active"


@dataclass(frozen=True)
class ResourceUsage:
    """
        What became of one resource over the period.

        :ivar resource_id: The resource's id.
        :ivar name: Its name.
        :ivar pool: Its pool's name, or ``""``.
        :ivar allocations: How many allocations overlap the period.
        :ivar hours_in_use: Hours it was in use (overlaps merged), inside the period.
        :ivar percent_in_use: ``hours_in_use`` as a share of the period, 0 to 100.
        :ivar last_checked_out: The latest check-out inside the period, or ``None``.
        :ivar in_use_now: Whether an allocation is active at the end of the period.
    """
    resource_id: int
    name: str
    pool: str
    allocations: int
    hours_in_use: float
    percent_in_use: float
    last_checked_out: Optional[datetime]
    in_use_now: bool


@dataclass(frozen=True)
class UtilizationReport:
    """
        The whole report.

        :ivar period_days: The period's length in days.
        :ivar window_start: Start of the period (UTC).
        :ivar window_end: End of the period (UTC).
        :ivar rows: One :class:`ResourceUsage` per resource, busiest first.
        :ivar allocations: Allocations overlapping the period, over every resource.
        :ivar resources_total: How many resources there are.
        :ivar resources_used: How many of them were in use at some point in the period.
        :ivar hours_in_use: Hours in use, summed over resources.
        :ivar average_hours: The average time one allocation was held inside the period, in hours.
        :ivar peak_at_once: The most allocations held at the same moment.
    """
    period_days: int
    window_start: datetime
    window_end: datetime
    rows: List[ResourceUsage]
    allocations: int
    resources_total: int
    resources_used: int
    hours_in_use: float
    average_hours: float
    peak_at_once: int


def parse_period_days(raw: Any) -> int:
    """
        Read the ``?days=`` value.

        :param raw: The raw query value (text) or ``None``.

        :returns: One of :data:`PERIOD_CHOICES`; :data:`DEFAULT_PERIOD_DAYS` for anything else.
    """
    try:
        days = int(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_PERIOD_DAYS
    return days if days in PERIOD_CHOICES else DEFAULT_PERIOD_DAYS


def _aware(value: datetime) -> datetime:
    """Treat a naive datetime as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _span_end(span: AllocationSpan, window_end: datetime) -> datetime:
    """When an allocation ended, or the end of the period if it still holds."""
    if span.actual_checkin is not None:
        return _aware(span.actual_checkin)
    if span.status == "active":
        return window_end
    if span.expected_checkin is not None:
        return _aware(span.expected_checkin)
    return _aware(span.checkout_time)


def _clip(span: AllocationSpan, window_start: datetime, window_end: datetime) -> Optional[Tuple[datetime, datetime]]:
    """The part of an allocation inside the period, or ``None`` when it has none."""
    start = max(_aware(span.checkout_time), window_start)
    end = min(_span_end(span, window_end), window_end)
    if end < start or _aware(span.checkout_time) > window_end:
        return None
    if end == start and _aware(span.checkout_time) < window_start:
        return None
    return (start, end)


def merge_intervals(intervals: Iterable[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
    """
        Join overlapping or touching intervals.

        :param intervals: ``(start, end)`` pairs in any order.

        :returns: Disjoint pairs in order.
    """
    merged: List[Tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if len(merged) > 0 and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _peak(intervals: Sequence[Tuple[datetime, datetime]]) -> int:
    """The most intervals open at the same moment (one that ends as another begins does not overlap it)."""
    events: List[Tuple[datetime, int]] = []
    for start, end in intervals:
        events.append((start, 1))
        events.append((end, -1))
    events.sort(key=lambda event: (event[0], event[1]))
    current = 0
    peak = 0
    for _moment, change in events:
        current += change
        peak = max(peak, current)
    return peak


def compute_utilization(
        *,
        resources: Sequence[ResourceRef],
        spans: Sequence[AllocationSpan],
        period_days: int,
        now: Optional[datetime] = None
    ) -> UtilizationReport:
    """
        Work out how long each resource was in use over the last ``period_days`` days.

        :param resources: Every resource to report on (one with no allocation reads as idle).
        :param spans: The allocations to consider; those outside the period are ignored.
        :param period_days: The period's length in days.
        :param now: The end of the period; ``None`` for the current time.

        :returns: The report, with the busiest resource first (ties by name).
    """
    window_end = _aware(now) if now is not None else datetime.now(timezone.utc)
    window_start = window_end - timedelta(days=period_days)
    period_hours = float(period_days) * 24.0

    clipped_by_resource: Dict[int, List[Tuple[datetime, datetime]]] = {}
    checkouts_by_resource: Dict[int, List[datetime]] = {}
    active_now: Dict[int, bool] = {}
    every_interval: List[Tuple[datetime, datetime]] = []
    for span in spans:
        clipped = _clip(span, window_start, window_end)
        if clipped is None:
            continue
        clipped_by_resource.setdefault(span.resource_id, []).append(clipped)
        every_interval.append(clipped)
        checkout = _aware(span.checkout_time)
        if checkout >= window_start:
            checkouts_by_resource.setdefault(span.resource_id, []).append(checkout)
        if span.status == "active" and span.actual_checkin is None:
            active_now[span.resource_id] = True

    rows: List[ResourceUsage] = []
    for resource in resources:
        intervals = clipped_by_resource.get(resource.resource_id, [])
        hours = sum((end - start).total_seconds() for start, end in merge_intervals(intervals)) / 3600.0
        checkouts = checkouts_by_resource.get(resource.resource_id, [])
        rows.append(ResourceUsage(
            resource_id=resource.resource_id, name=resource.name, pool=resource.pool,
            allocations=len(intervals), hours_in_use=round(hours, 1),
            percent_in_use=round(min(100.0, hours / period_hours * 100.0), 1) if period_hours > 0 else 0.0,
            last_checked_out=max(checkouts) if len(checkouts) > 0 else None,
            in_use_now=active_now.get(resource.resource_id, False),
        ))
    rows.sort(key=lambda row: (-row.percent_in_use, -row.allocations, row.name.lower()))

    known = {resource.resource_id for resource in resources}
    counted = [interval for resource_id, items in clipped_by_resource.items() if resource_id in known for interval in items]
    total_seconds = sum((end - start).total_seconds() for start, end in counted)
    return UtilizationReport(
        period_days=period_days, window_start=window_start, window_end=window_end, rows=rows,
        allocations=len(counted), resources_total=len(resources),
        resources_used=sum(1 for row in rows if row.allocations > 0),
        hours_in_use=round(sum(row.hours_in_use for row in rows), 1),
        average_hours=round(total_seconds / 3600.0 / len(counted), 1) if len(counted) > 0 else 0.0,
        peak_at_once=_peak(counted),
    )


def export_records(report: UtilizationReport) -> List[Dict[str, Any]]:
    """
        The report as rows for :func:`ccai.pychestrate.webservice.csv_export.render_csv`.

        :param report: The report.

        :returns: One record per resource, keyed by :data:`EXPORT_COLUMNS`.
    """
    return [
        {
            "resource": row.name, "pool": row.pool, "allocations": row.allocations, "hours_in_use": row.hours_in_use,
            "percent_in_use": row.percent_in_use,
            "last_checked_out": row.last_checked_out.isoformat() if row.last_checked_out is not None else "",
            "period_days": report.period_days,
        }
        for row in report.rows
    ]


__all__ = [
    "AllocationSpan",
    "DEFAULT_PERIOD_DAYS",
    "EXPORT_COLUMNS",
    "PERIOD_CHOICES",
    "ResourceRef",
    "ResourceUsage",
    "UtilizationReport",
    "compute_utilization",
    "export_records",
    "merge_intervals",
    "parse_period_days",
]
