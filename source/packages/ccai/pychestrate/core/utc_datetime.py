"""
.. module:: utc_datetime
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A SQLAlchemy datetime column type that always stores and returns
               timezone-aware UTC values, on every database.

.. moduleauthor:: Code Craft AI LLC

SQLite has no time zone storage. For a ``DateTime(timezone=True)`` column,
SQLAlchemy writes the wall-clock digits of the value it is given and reads them
back as a *naive* datetime. Code that compares such a value with ``utc_now()``
(which is aware) raises ``TypeError: can't subtract offset-naive and
offset-aware datetimes``, and an aware value in any zone other than UTC is
stored with the wrong digits.

:class:`UtcDateTime` closes both gaps at the ORM boundary:

* every bound value is converted to UTC before it is written or compared (a
  naive value is taken to be UTC already, which is how the rows have always
  been written), and
* every value read back is timezone-aware UTC (a naive value from SQLite gets
  UTC attached; an aware value from PostgreSQL ``timestamptz`` is converted to
  UTC so callers always see one shape).

The column DDL is unchanged (the implementation type is ``DateTime``), so
adopting the type needs no schema migration.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Any, Optional

from sqlalchemy.types import DateTime, TypeDecorator

from ccai.pychestrate.core.defaults import ensure_utc


class UtcDateTime(TypeDecorator):
    """
        A ``DateTime`` column that always hands back timezone-aware UTC
        datetimes and always stores UTC, whatever the database. Declare it
        exactly like ``DateTime``: ``Column('x', UtcDateTime(timezone=True))``.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        """
            Convert a datetime bound to the column (an insert, an update or a
            comparison) to aware UTC. Values that are not datetimes pass
            through to the implementation type unchanged.

            :param value: The Python value being bound.
            :param dialect: The active SQLAlchemy dialect.

            :returns: The aware UTC datetime, or ``value`` unchanged.
        """
        if isinstance(value, datetime):
            rtnval = ensure_utc(value)
            return rtnval
        return value

    def process_result_value(self, value: Any, dialect: Any) -> Optional[datetime]:
        """
            Return a column value read from the database as aware UTC.

            :param value: The value the implementation type produced.
            :param dialect: The active SQLAlchemy dialect.

            :returns: The aware UTC datetime, or ``None``.
        """
        if isinstance(value, datetime):
            rtnval = ensure_utc(value)
            return rtnval
        return value


__all__ = [
    "UtcDateTime",
]
