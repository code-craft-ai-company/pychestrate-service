"""
.. module:: extensions.sandbox.repository
    :synopsis: CRUD helpers for extension capability grants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.extensions.sandbox.models import (
    ExtensionCapabilityGrant,
)


def upsert_grant(
        *,
        db_session: DbSession,
        ext_name: str,
        capability: str,
        source: str,
        granted_by: Optional[str],
        granted_at: datetime
    ) -> ExtensionCapabilityGrant:
    """
        Insert (or revive) a grant. A previously-revoked row is
        reset — ``revoked_at`` cleared — and the source +
        granted-by columns are stamped to reflect the current
        actor.
    """
    row = (
        db_session.query(ExtensionCapabilityGrant)
        .filter(ExtensionCapabilityGrant.ext_name == ext_name)
        .filter(ExtensionCapabilityGrant.capability == capability)
        .first()
    )
    if row is None:
        row = ExtensionCapabilityGrant(
            ext_name=ext_name,
            capability=capability,
            source=source,
            granted_at=granted_at,
            granted_by=granted_by,
            revoked_at=None,
            revoked_by=None,
            revoked_reason=None,
        )
        db_session.add(row)
    else:
        row.source = source
        row.granted_by = granted_by
        if row.revoked_at is not None:
            row.granted_at = granted_at
            row.revoked_at = None
            row.revoked_by = None
            row.revoked_reason = None
    db_session.flush()
    return row


def find_grant(
        *,
        db_session: DbSession,
        ext_name: str,
        capability: str
    ) -> Optional[ExtensionCapabilityGrant]:
    rtnval = (
        db_session.query(ExtensionCapabilityGrant)
        .filter(ExtensionCapabilityGrant.ext_name == ext_name)
        .filter(ExtensionCapabilityGrant.capability == capability)
        .first()
    )
    return rtnval


def mark_revoked(
        *,
        db_session: DbSession,
        ext_name: str,
        capability: str,
        revoked_by: Optional[str],
        reason: str,
        revoked_at: datetime
    ) -> Optional[ExtensionCapabilityGrant]:
    row = (
        db_session.query(ExtensionCapabilityGrant)
        .filter(ExtensionCapabilityGrant.ext_name == ext_name)
        .filter(ExtensionCapabilityGrant.capability == capability)
        .first()
    )
    if row is None:
        return None
    if row.revoked_at is not None:
        return row
    row.revoked_at = revoked_at
    row.revoked_by = revoked_by
    row.revoked_reason = reason
    db_session.flush()
    return row


def list_active_for_extension(
        *,
        db_session: DbSession,
        ext_name: str
    ) -> List[ExtensionCapabilityGrant]:
    rows = (
        db_session.query(ExtensionCapabilityGrant)
        .filter(ExtensionCapabilityGrant.ext_name == ext_name)
        .filter(ExtensionCapabilityGrant.revoked_at.is_(None))
        .order_by(ExtensionCapabilityGrant.capability.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def list_all_grants(
        *,
        db_session: DbSession,
        ext_name: str
    ) -> List[ExtensionCapabilityGrant]:
    rows = (
        db_session.query(ExtensionCapabilityGrant)
        .filter(ExtensionCapabilityGrant.ext_name == ext_name)
        .order_by(ExtensionCapabilityGrant.capability.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def list_active_grants(
        *,
        db_session: DbSession
    ) -> List[ExtensionCapabilityGrant]:
    rows = (
        db_session.query(ExtensionCapabilityGrant)
        .filter(ExtensionCapabilityGrant.revoked_at.is_(None))
        .order_by(
            ExtensionCapabilityGrant.ext_name.asc(),
            ExtensionCapabilityGrant.capability.asc(),
        )
        .all()
    )
    rtnval = list(rows)
    return rtnval
