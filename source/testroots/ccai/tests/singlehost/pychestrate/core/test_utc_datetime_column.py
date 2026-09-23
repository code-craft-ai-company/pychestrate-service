"""
.. module:: test_utc_datetime_column
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the UtcDateTime column type on SQLite.

.. moduleauthor:: Code Craft AI LLC

``UtcDateTime`` normalises datetimes at the ORM boundary so SQLite (which
stores no time zone) behaves like PostgreSQL ``timestamptz``: values always
come back timezone-aware UTC, and values in other zones are converted to UTC
before they are written or compared (audit finding RES-01).

**Feature: resources (RES-01 UTC datetimes at the ORM boundary)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import Any, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import declarative_base, sessionmaker

from ccai import testbase

from ccai.pychestrate.core.utc_datetime import UtcDateTime


_Base = declarative_base()

_PACIFIC_DAYLIGHT = timezone(timedelta(hours=-7))


class _Stamp(_Base):
    """
        A one-column table for exercising the type in isolation.
    """
    __tablename__ = "utc_datetime_probe"

    id = sa.Column(sa.Integer, primary_key=True)
    at = sa.Column(UtcDateTime(timezone=True), nullable=True)


def _stored(*, value: Any) -> Tuple[Any, int]:
    """
        Store ``value`` in a fresh SQLite database and return
        ``(new_session_factory, row_id)``.
    """
    engine = sa.create_engine("sqlite://")
    _Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    row = _Stamp(at=value)
    session.add(row)
    session.commit()
    row_id = row.id
    session.close()
    rtnval = (factory, row_id)
    return rtnval


def _read_back(*, factory: Any, row_id: int) -> Any:
    session = factory()
    rtnval = session.query(_Stamp).filter(_Stamp.id == row_id).one().at
    session.close()
    return rtnval


def test_aware_utc_value_reads_back_aware():
    """
    **Feature: resources (RES-01 UTC datetimes at the ORM boundary)**
    **Property: an aware UTC value written to SQLite reads back
    timezone-aware (UTC offset zero), not naive.**
    """
    written = datetime(2026, 9, 23, 17, 0, tzinfo=timezone.utc)
    factory, row_id = _stored(value=written)

    value = _read_back(factory=factory, row_id=row_id)

    testbase.assert_equal(value.utcoffset(), timedelta(0))
    return


def test_value_in_another_zone_is_stored_as_the_same_instant_in_utc():
    """
    **Feature: resources (RES-01 UTC datetimes at the ORM boundary)**
    **Property: 10:00 at UTC-7 is stored and read back as 17:00 UTC (the
    same instant), not as 10:00.**
    """
    written = datetime(2026, 9, 23, 10, 0, tzinfo=_PACIFIC_DAYLIGHT)
    factory, row_id = _stored(value=written)

    value = _read_back(factory=factory, row_id=row_id)

    testbase.assert_equal(value, datetime(2026, 9, 23, 17, 0, tzinfo=timezone.utc))
    return


def test_naive_value_is_taken_to_be_utc():
    """
    **Feature: resources (RES-01 UTC datetimes at the ORM boundary)**
    **Property: a naive value is stored as UTC and reads back as that UTC
    instant.**
    """
    factory, row_id = _stored(value=datetime(2026, 9, 23, 17, 0))

    value = _read_back(factory=factory, row_id=row_id)

    testbase.assert_equal(value, datetime(2026, 9, 23, 17, 0, tzinfo=timezone.utc))
    return


def test_comparison_values_are_converted_to_utc():
    """
    **Feature: resources (RES-01 UTC datetimes at the ORM boundary)**
    **Property: a filter bound with a value in another zone compares the
    same instant: ``at < 10:30 UTC-7`` (17:30 UTC) matches the row at
    17:00 UTC and not the row at 18:00 UTC.**
    """
    factory, first_id = _stored(value=datetime(2026, 9, 23, 17, 0, tzinfo=timezone.utc))
    session = factory()
    session.add(_Stamp(at=datetime(2026, 9, 23, 18, 0, tzinfo=timezone.utc)))
    session.commit()

    cutoff = datetime(2026, 9, 23, 10, 30, tzinfo=_PACIFIC_DAYLIGHT)
    matched = [row.id for row in session.query(_Stamp).filter(_Stamp.at < cutoff).all()]
    session.close()

    testbase.assert_equal(matched, [first_id])
    return


def test_null_stays_null():
    """
    **Feature: resources (RES-01 UTC datetimes at the ORM boundary)**
    **Property: a NULL value is stored and read back as None.**
    """
    factory, row_id = _stored(value=None)

    value = _read_back(factory=factory, row_id=row_id)

    testbase.assert_equal(value, None)
    return
