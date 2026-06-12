__author__ = "Myron Walker"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []

from sqlalchemy.orm.session import Session
from ccai.automojowebsite.app_automojo_metadata import SITE_SHARED_GLOBALS

def get_database_session() -> Session:
    session = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY()
    return session
