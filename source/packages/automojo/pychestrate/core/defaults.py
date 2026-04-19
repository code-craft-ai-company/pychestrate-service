__author__ = "Myron Walker"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []

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
