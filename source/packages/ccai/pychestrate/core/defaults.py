__author__ = "Myron Walker"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []

from typing import Optional
from uuid import uuid4

from datetime import datetime, timezone, timedelta

def new_uuid() -> str:
    rtnval = str(uuid4())
    return rtnval

def utc_now() -> datetime:
    """
        Provides the current UTC time. This is used as a default value for datetime fields in models.
        
        :return: datetime
    """
    now = datetime.now(timezone.utc)
    return now

def reset_token_expiration() -> datetime:
    """
        Provides the expiration time for reset tokens. This is set to 24 hours from now.

        :return: datetime
    """
    expiration = utc_now() + timedelta(days=1)
    return expiration

def ensure_utc(value: Optional[datetime]) -> Optional[datetime]:
    """
        Returns a timezone-aware UTC copy of a datetime so it can be compared with
        and subtracted from :func:`utc_now`. A naive value is taken to already be
        in UTC (that is how the database layer stores them); an aware value is
        converted to UTC. ``None`` is returned unchanged.

        :param value: The datetime to normalise, or ``None``.

        :return: The aware UTC datetime, or ``None``.
    """
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        rtnval = value.replace(tzinfo=timezone.utc)
    else:
        rtnval = value.astimezone(timezone.utc)
    return rtnval
