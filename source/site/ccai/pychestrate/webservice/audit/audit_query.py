"""
.. module:: audit.audit_query
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Filtered, cursor-paged reads of the canonical audit store.

.. moduleauthor:: Code Craft AI LLC

The admin Audit Logs page and its CSV / JSONL export read
``audit_records`` through this module. Records are returned newest
first. Paging uses the monotonic ``sequence_number`` as a cursor
(``before_sequence`` for older pages, ``after_sequence`` for newer
ones), so a page stays stable while new records are written.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator, List, Optional, Tuple

from ccai.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension
from ccai.pychestrate.webservice.audit.models import AuditRecord
from ccai.pychestrate.webservice.extensions.registry import list_resource_extensions


DEFAULT_PAGE_SIZE: int = 50
MAX_PAGE_SIZE: int = 200

#: Upper bound on one export; the newest records win.
MAX_EXPORT_RECORDS: int = 50000

_EXPORT_CHUNK_SIZE: int = 500


@dataclass(frozen=True)
class AuditQuery:
    """
        Filters for an audit read. Every filter is optional.

        :param kinds: Exact audit kinds to include (empty = all).
        :param actor_user_id: Only records whose actor is this user.
        :param target_contains: Case-insensitive substring of the
                                target reference (``projects:5``,
                                ``user:<id>``).
        :param since: Only records written at or after this time.
        :param until: Only records written at or before this time.
        :param before_sequence: Only records older than this sequence
                                number (the "older" cursor).
        :param after_sequence: Only records newer than this sequence
                               number (the "newer" cursor).
        :param limit: Page size.
    """
    kinds: Tuple[str, ...] = ()
    actor_user_id: Optional[str] = None
    target_contains: Optional[str] = None
    since: Optional[datetime] = None
    until: Optional[datetime] = None
    before_sequence: Optional[int] = None
    after_sequence: Optional[int] = None
    limit: int = DEFAULT_PAGE_SIZE


@dataclass(frozen=True)
class AuditPage:
    """
        One page of records, newest first.

        :param records: The page's :class:`AuditRecord` rows.
        :param total: Records matching the filters (all pages).
        :param has_older: More records exist past the page's oldest.
        :param has_newer: More records exist past the page's newest.
    """
    records: List[Any] = field(default_factory=list)
    total: int = 0
    has_older: bool = False
    has_newer: bool = False

    @property
    def oldest_sequence(self) -> Optional[int]:
        if len(self.records) == 0:
            return None
        rtnval = int(self.records[-1].sequence_number)
        return rtnval

    @property
    def newest_sequence(self) -> Optional[int]:
        if len(self.records) == 0:
            return None
        rtnval = int(self.records[0].sequence_number)
        return rtnval


@dataclass(frozen=True)
class AuditKindView:
    """
        One registered audit kind, for the page's action filter.

        :param kind: The kind (``audit.user.created``).
        :param area: The kind's area (``user``).
        :param description: The pack's description.
    """
    kind: str
    area: str
    description: str


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """
        Treat a naive datetime as UTC.

        :param value: Datetime or None.

        :returns: Aware datetime or None.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        rtnval = value.replace(tzinfo=timezone.utc)
        return rtnval
    return value


def _filtered_query(*, db_session: Any, audit_query: AuditQuery) -> Any:
    """
        The ``audit_records`` query with every filter except the
        cursors applied.

        :param db_session: Active SQLAlchemy session.
        :param audit_query: The filters.

        :returns: A SQLAlchemy query.
    """
    import uuid as _uuid  # noqa: E402

    query = db_session.query(AuditRecord)
    if len(audit_query.kinds) > 0:
        query = query.filter(AuditRecord.kind.in_(list(audit_query.kinds)))
    if audit_query.actor_user_id is not None:
        try:
            actor_uuid = _uuid.UUID(str(audit_query.actor_user_id))
        except ValueError:
            actor_uuid = None
        if actor_uuid is None:
            # Not a user id: nothing can match.
            query = query.filter(AuditRecord.sequence_number < 0)
        else:
            query = query.filter(AuditRecord.actor_user_id == actor_uuid)
    if audit_query.target_contains is not None and len(audit_query.target_contains) > 0:
        pattern = "%{}%".format(audit_query.target_contains.lower())
        query = query.filter(AuditRecord.target_ref.ilike(pattern))
    since = _as_utc(audit_query.since)
    if since is not None:
        query = query.filter(AuditRecord.written_at >= since)
    until = _as_utc(audit_query.until)
    if until is not None:
        query = query.filter(AuditRecord.written_at <= until)
    return query


def count_audit_records(*, db_session: Any, audit_query: AuditQuery) -> int:
    """
        Number of records matching the filters (cursors ignored).

        :param db_session: Active SQLAlchemy session.
        :param audit_query: The filters.

        :returns: The count.
    """
    rtnval = int(_filtered_query(db_session=db_session, audit_query=audit_query).count())
    return rtnval


def query_audit_page(*, db_session: Any, audit_query: AuditQuery) -> AuditPage:
    """
        One page of records matching the filters, newest first, starting
        at the cursor.

        :param db_session: Active SQLAlchemy session.
        :param audit_query: The filters and cursor.

        :returns: :class:`AuditPage`.
    """
    limit = int(audit_query.limit)
    if limit < 1:
        limit = DEFAULT_PAGE_SIZE
    if limit > MAX_PAGE_SIZE:
        limit = MAX_PAGE_SIZE

    base = _filtered_query(db_session=db_session, audit_query=audit_query)
    total = int(base.count())

    if audit_query.after_sequence is not None:
        # "Newer" page: the ``limit`` records just after the cursor,
        # returned newest first.
        rows = (
            base.filter(AuditRecord.sequence_number > int(audit_query.after_sequence))
            .order_by(AuditRecord.sequence_number.asc())
            .limit(limit + 1)
            .all()
        )
        has_newer = len(rows) > limit
        rows = list(reversed(rows[:limit]))
        has_older = True
    else:
        query = base
        if audit_query.before_sequence is not None:
            query = query.filter(AuditRecord.sequence_number < int(audit_query.before_sequence))
        rows = (
            query.order_by(AuditRecord.sequence_number.desc())
            .limit(limit + 1)
            .all()
        )
        has_older = len(rows) > limit
        rows = rows[:limit]
        has_newer = audit_query.before_sequence is not None

    if len(rows) > 0 and has_newer is True:
        newest = int(rows[0].sequence_number)
        has_newer = base.filter(AuditRecord.sequence_number > newest).first() is not None
    if len(rows) > 0 and has_older is True and audit_query.after_sequence is not None:
        oldest = int(rows[-1].sequence_number)
        has_older = base.filter(AuditRecord.sequence_number < oldest).first() is not None

    rtnval = AuditPage(
        records=rows,
        total=total,
        has_older=has_older,
        has_newer=has_newer,
    )
    return rtnval


def iter_audit_records(
        *,
        db_session: Any,
        audit_query: AuditQuery,
        max_records: int = MAX_EXPORT_RECORDS
    ) -> Iterator[Any]:
    """
        Every record matching the filters, newest first, read in chunks
        (for export). Cursors in ``audit_query`` are ignored.

        :param db_session: Active SQLAlchemy session.
        :param audit_query: The filters.
        :param max_records: Stop after this many records.

        :returns: Iterator of :class:`AuditRecord`.
    """
    base = _filtered_query(db_session=db_session, audit_query=audit_query)
    emitted = 0
    before: Optional[int] = None
    while emitted < max_records:
        query = base
        if before is not None:
            query = query.filter(AuditRecord.sequence_number < before)
        chunk_size = min(_EXPORT_CHUNK_SIZE, max_records - emitted)
        rows = (
            query.order_by(AuditRecord.sequence_number.desc())
            .limit(chunk_size)
            .all()
        )
        if len(rows) == 0:
            break
        for row in rows:
            yield row
            emitted = emitted + 1
        before = int(rows[-1].sequence_number)
        if len(rows) < chunk_size:
            break
    return


def list_audit_kinds() -> List[AuditKindView]:
    """
        Every registered audit kind, sorted by area then kind -- the
        choices of the page's action filter (the legacy page listed
        event types nothing ever wrote).

        :returns: List of :class:`AuditKindView`.
    """
    seen = set()
    rtnval: List[AuditKindView] = []
    for pack in list_resource_extensions(base_class=AuditEventTypeExtension):
        kind = str(getattr(pack, "kind", ""))
        if len(kind) == 0 or kind in seen:
            continue
        seen.add(kind)
        parts = kind.split(".")
        area = parts[1] if len(parts) > 2 else "other"
        rtnval.append(AuditKindView(
            kind=kind,
            area=area,
            description=str(getattr(pack, "description", "")),
        ))
    rtnval.sort(key=lambda view: (view.area, view.kind))
    return rtnval


__all__ = [
    "AuditKindView",
    "AuditPage",
    "AuditQuery",
    "DEFAULT_PAGE_SIZE",
    "MAX_EXPORT_RECORDS",
    "MAX_PAGE_SIZE",
    "count_audit_records",
    "iter_audit_records",
    "list_audit_kinds",
    "query_audit_page",
]
