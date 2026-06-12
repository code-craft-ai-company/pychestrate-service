"""
.. module:: retention.repository
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Repository for 2-retention-policies rows.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.retention.models import (
    PolicyScopeLevel,
    PolicyState,
    RetentionPolicy,
)


def insert_policy(*, db_session: DbSession, policy: RetentionPolicy) -> RetentionPolicy:
    """
        Persist a new :class:`RetentionPolicy` row.

        :param db_session: Active SQLAlchemy session.
        :param policy: The policy to persist.

        :returns: The persisted row.
    """
    db_session.add(policy)
    db_session.flush()
    rtnval = policy
    return rtnval


def get_policy_by_id(
        *,
        db_session: DbSession,
        policy_id: str
    ) -> Optional[RetentionPolicy]:
    """
        Look up a policy by id.

        :param db_session: Active SQLAlchemy session.
        :param policy_id: Target id.

        :returns: The :class:`RetentionPolicy` or None.
    """
    rtnval = (
        db_session.query(RetentionPolicy)
        .filter(RetentionPolicy.policy_id == policy_id)
        .first()
    )
    return rtnval


def get_policy_by_name(
        *,
        db_session: DbSession,
        scope_level: PolicyScopeLevel,
        project_id: Optional[str],
        name: str
    ) -> Optional[RetentionPolicy]:
    """
        Look up a policy by its scope + name uniqueness key.

        :param db_session: Active SQLAlchemy session.
        :param scope_level: Scope.
        :param project_id: Project id when scope_level=PROJECT, else None.
        :param name: Policy name.

        :returns: The :class:`RetentionPolicy` or None.
    """
    query = db_session.query(RetentionPolicy).filter(
        RetentionPolicy.scope_level == scope_level
    )
    if project_id is None:
        query = query.filter(RetentionPolicy.project_id.is_(None))
    else:
        query = query.filter(RetentionPolicy.project_id == project_id)
    query = query.filter(RetentionPolicy.name == name)

    rtnval = query.first()
    return rtnval


def list_policies(
        *,
        db_session: DbSession,
        scope_level: Optional[PolicyScopeLevel],
        project_id: Optional[str],
        state: Optional[PolicyState]
    ) -> List[RetentionPolicy]:
    """
        Return policies matching the supplied filters.
    """
    query = db_session.query(RetentionPolicy)

    if scope_level is not None:
        query = query.filter(RetentionPolicy.scope_level == scope_level)
    if project_id is not None:
        query = query.filter(RetentionPolicy.project_id == project_id)
    if state is not None:
        query = query.filter(RetentionPolicy.state == state)

    query = query.order_by(RetentionPolicy.created_at.asc())

    rtnval = query.all()
    return rtnval
