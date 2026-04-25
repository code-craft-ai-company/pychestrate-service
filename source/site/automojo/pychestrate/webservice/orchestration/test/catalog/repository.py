"""
.. module:: orchestration.test.catalog.repository
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: TestCatalogRepository — CRUD helpers.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.orchestration.test.catalog.models import (
    TestCatalogEntry,
)


def find_entry(
        *,
        db_session: DbSession,
        project_id: str,
        importer_tag: str,
        entry_key: str
    ) -> Optional[TestCatalogEntry]:
    """
        Look up by the natural key.
    """
    rtnval = (
        db_session.query(TestCatalogEntry)
        .filter(TestCatalogEntry.project_id == project_id)
        .filter(TestCatalogEntry.importer_tag == importer_tag)
        .filter(TestCatalogEntry.entry_key == entry_key)
        .first()
    )
    return rtnval


def find_by_id(
        *,
        db_session: DbSession,
        entry_id: str
    ) -> Optional[TestCatalogEntry]:
    """
        Fetch by entry_id.
    """
    rtnval = (
        db_session.query(TestCatalogEntry)
        .filter(TestCatalogEntry.entry_id == entry_id)
        .first()
    )
    return rtnval


def list_entries(
        *,
        db_session: DbSession,
        project_id: str,
        include_retired: bool = False,
        importer_tag: Optional[str] = None,
        capability_tag: Optional[str] = None
    ) -> List[TestCatalogEntry]:
    """
        Return entries for a project. Filters in-process when the
        backend lacks JSON-array containment support (SQLite tests
        do not).
    """
    query = (
        db_session.query(TestCatalogEntry)
        .filter(TestCatalogEntry.project_id == project_id)
    )
    if include_retired is False:
        query = query.filter(TestCatalogEntry.retired.is_(False))
    if importer_tag is not None:
        query = query.filter(TestCatalogEntry.importer_tag == importer_tag)
    rows = query.order_by(TestCatalogEntry.entry_key.asc()).all()
    if capability_tag is not None:
        rows = [
            row for row in rows
            if capability_tag in (row.required_capability_tags or [])
        ]
    rtnval = list(rows)
    return rtnval
