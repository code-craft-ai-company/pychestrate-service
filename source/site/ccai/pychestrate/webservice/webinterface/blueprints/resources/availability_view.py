"""
.. module:: availability_view
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Lays out a week of reservations and check-outs as free/busy
               rows, one per resource (RES-43).

.. moduleauthor:: Code Craft AI LLC

Pure functions with no framework or database in them: they take the
resources, reservations and current holders a route has already read and
return what the availability template draws. The week starts on Monday
and runs from local midnight to local midnight in the viewer's zone, so
a week that contains a daylight-saving change is 167 or 169 hours long
and every position is a share of the real length of the week.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple


#: Narrowest a block is drawn, as a share of the week, so a short booking
#: can still be seen and hovered.
MINIMUM_BLOCK_PERCENT = 0.4

KIND_RESERVED_EXCLUSIVE = "reserved-exclusive"
KIND_RESERVED_SHARED = "reserved-shared"
KIND_CHECKED_OUT = "checked-out"

KIND_LABELS: Dict[str, str] = {
    KIND_RESERVED_EXCLUSIVE: "Reserved (exclusive)",
    KIND_RESERVED_SHARED: "Reserved (shared)",
    KIND_CHECKED_OUT: "Checked out",
}


@dataclass(frozen=True)
class DayColumn:
    """One day of the week: where it starts and how wide it is, in percent of the week."""
    label: str
    left_percent: float
    width_percent: float
    is_today: bool


@dataclass(frozen=True)
class WeekWindow:
    """
        A Monday-to-Monday week in the viewer's zone.

        :param zone_name: The IANA zone the week is in.
        :param monday: The local date the week starts on.
        :param start_utc: The instant the week starts.
        :param end_utc: The instant the week ends (next Monday, local midnight).
        :param days: The seven day columns.
        :param now_percent: Where "now" falls, or None when it is outside the week.
        :param previous_monday: The Monday a week earlier.
        :param next_monday: The Monday a week later.
    """
    zone_name: str
    monday: date
    start_utc: datetime
    end_utc: datetime
    days: Tuple[DayColumn, ...]
    now_percent: Optional[float]
    previous_monday: date
    next_monday: date

    @property
    def total_seconds(self) -> float:
        rtnval = (self.end_utc - self.start_utc).total_seconds()
        return rtnval

    @property
    def title(self) -> str:
        last_day = self.monday + timedelta(days=6)
        rtnval = "{} to {}".format(self.monday.strftime("%d %b %Y"), last_day.strftime("%d %b %Y"))
        return rtnval


@dataclass
class Block:
    """
        One booking on a resource's row.

        :param kind: One of the ``KIND_*`` values.
        :param who: The login of the person, or None when unknown.
        :param start: When it starts (UTC, aware).
        :param end: When it ends (UTC, aware), or None for a check-out with no timeout.
        :param left_percent: Where it starts, as a share of the week.
        :param width_percent: How wide it is, as a share of the week.
        :param lane: The line it is drawn on, so overlapping blocks do not hide each other.
        :param reservation_id: The reservation's id, or None for a check-out.
        :param status: The reservation's status, or ``active`` for a check-out.
        :param job_id: The job the booking is for, or None.
        :param tooltip: The sentence shown when the block is hovered (the route writes it in the viewer's zone).
    """
    kind: str
    who: Optional[str]
    start: datetime
    end: Optional[datetime]
    left_percent: float
    width_percent: float
    lane: int = 0
    reservation_id: Optional[int] = None
    status: str = ""
    job_id: Optional[str] = None
    starts_before_week: bool = False
    ends_after_week: bool = False
    tooltip: str = ""


@dataclass
class ResourceRow:
    """A resource and its blocks for the week."""
    resource_id: int
    name: str
    health_status: str
    blocks: List[Block] = field(default_factory=list)
    lanes: int = 1


def _as_utc(value: datetime) -> datetime:
    """An aware UTC copy of ``value`` (a naive value is UTC, which is how the database keeps them)."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    rtnval = value.astimezone(timezone.utc)
    return rtnval


def monday_of(day: date) -> date:
    """The Monday of the week that contains ``day``."""
    rtnval = day - timedelta(days=day.weekday())
    return rtnval


def week_window(*, anchor: date, zone: Any, zone_name: str, now: datetime) -> WeekWindow:
    """
        The week (Monday to Monday) that contains ``anchor`` in ``zone``.

        :param anchor: Any local date in the week.
        :param zone: The ``tzinfo`` the week is in.
        :param zone_name: The zone's IANA name, kept for display.
        :param now: The current instant, for the "now" marker and today's column.

        :returns: The window, with every position as a share of the week's real length.
    """
    monday = monday_of(anchor)
    now_utc = _as_utc(now)
    bounds = [
        datetime.combine(monday + timedelta(days=offset), time.min, tzinfo=zone).astimezone(timezone.utc)
        for offset in range(8)
    ]
    start_utc = bounds[0]
    end_utc = bounds[7]
    total = (end_utc - start_utc).total_seconds()
    today = now_utc.astimezone(zone).date()
    days = []
    for offset in range(7):
        left = (bounds[offset] - start_utc).total_seconds() / total * 100.0
        width = (bounds[offset + 1] - bounds[offset]).total_seconds() / total * 100.0
        local_day = monday + timedelta(days=offset)
        days.append(DayColumn(
            label=local_day.strftime("%a %d %b"), left_percent=left, width_percent=width,
            is_today=local_day == today,
        ))
    now_percent = None
    if start_utc <= now_utc < end_utc:
        now_percent = (now_utc - start_utc).total_seconds() / total * 100.0
    rtnval = WeekWindow(
        zone_name=zone_name, monday=monday, start_utc=start_utc, end_utc=end_utc, days=tuple(days),
        now_percent=now_percent, previous_monday=monday - timedelta(days=7), next_monday=monday + timedelta(days=7),
    )
    return rtnval


def _place(*, start: datetime, end: Optional[datetime], window: WeekWindow) -> Optional[Tuple[float, float, bool, bool]]:
    """
        Where a span falls in the week.

        :returns: ``(left percent, width percent, starts before the week,
                  ends after the week)``, or None when it does not overlap
                  the week. A span with no end runs to the end of the week.
    """
    span_end = window.end_utc if end is None else end
    if start >= window.end_utc or span_end <= window.start_utc:
        return None
    visible_start = max(start, window.start_utc)
    visible_end = min(span_end, window.end_utc)
    total = window.total_seconds
    left = (visible_start - window.start_utc).total_seconds() / total * 100.0
    width = (visible_end - visible_start).total_seconds() / total * 100.0
    width = max(width, MINIMUM_BLOCK_PERCENT)
    if left + width > 100.0:
        left = 100.0 - width
    rtnval = (left, width, start < window.start_utc, end is None or end > window.end_utc)
    return rtnval


def _assign_lanes(blocks: List[Block]) -> int:
    """
        Give each block the first line on which it overlaps nothing, so a
        shared reservation next to another does not hide it.

        :returns: The number of lines used (at least one).
    """
    lane_ends: List[float] = []
    for block in sorted(blocks, key=lambda item: (item.left_percent, item.width_percent)):
        block_end = block.left_percent + block.width_percent
        placed = False
        for index, lane_end in enumerate(lane_ends):
            if lane_end <= block.left_percent:
                block.lane = index
                lane_ends[index] = block_end
                placed = True
                break
        if not placed:
            block.lane = len(lane_ends)
            lane_ends.append(block_end)
    rtnval = max(len(lane_ends), 1)
    return rtnval


def build_rows(
        *,
        resources: Sequence[Any],
        reservations: Sequence[Any],
        holders: Dict[int, List[Dict[str, Any]]],
        window: WeekWindow
    ) -> List[ResourceRow]:
    """
        One row per resource with its reservations and current check-outs
        for the week.

        :param resources: Objects with ``id``, ``name`` and ``health_status``.
        :param reservations: Reservation responses (``resource_id``,
                             ``username``, ``start_time``, ``end_time``,
                             ``mode``, ``status``, ``id``, ``job_id``).
        :param holders: ``ResourceManager.get_current_holders`` output.
        :param window: The week.

        :returns: The rows, in the order the resources were given.
    """
    rows: Dict[int, ResourceRow] = {}
    ordered: List[ResourceRow] = []
    for resource in resources:
        health = getattr(resource, "health_status", "online")
        row = ResourceRow(
            resource_id=resource.id, name=resource.name, health_status=str(getattr(health, "value", health)),
        )
        rows[resource.id] = row
        ordered.append(row)

    for reservation in reservations:
        row = rows.get(reservation.resource_id)
        if row is None:
            continue
        start = _as_utc(reservation.start_time)
        end = _as_utc(reservation.end_time)
        placed = _place(start=start, end=end, window=window)
        if placed is None:
            continue
        left, width, before, after = placed
        row.blocks.append(Block(
            kind=KIND_RESERVED_SHARED if reservation.mode == "shared" else KIND_RESERVED_EXCLUSIVE,
            who=reservation.username, start=start, end=end, left_percent=left, width_percent=width,
            reservation_id=reservation.id, status=reservation.status, job_id=reservation.job_id,
            starts_before_week=before, ends_after_week=after,
        ))

    for resource_id, held in holders.items():
        row = rows.get(resource_id)
        if row is None:
            continue
        for holder in held:
            checkout = holder.get("checkout_time")
            expected = holder.get("expected_checkin")
            if checkout is None:
                continue
            start = _as_utc(checkout)
            end = _as_utc(expected) if expected is not None else None
            placed = _place(start=start, end=end, window=window)
            if placed is None:
                continue
            left, width, before, after = placed
            row.blocks.append(Block(
                kind=KIND_CHECKED_OUT, who=holder.get("username"), start=start, end=end,
                left_percent=left, width_percent=width, status="active", job_id=holder.get("job_id"),
                starts_before_week=before, ends_after_week=after,
            ))

    for row in ordered:
        row.lanes = _assign_lanes(row.blocks)
    return ordered
