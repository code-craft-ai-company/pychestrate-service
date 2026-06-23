"""
.. module:: tagging.repository
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Repository for :class:`TagAssignment` rows.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.tagging.models import TagAssignment


def insert_assignment(*, db_session: DbSession, assignment: TagAssignment) -> TagAssignment:
    """
        Persist a new tag assignment.

        :param db_session: Active SQLAlchemy session.
        :param assignment: The row to persist.

        :returns: The persisted row.
    """
    db_session.add(assignment)
    db_session.flush()
    rtnval = assignment
    return rtnval


def get_assignment(
        *,
        db_session: DbSession,
        entity_kind: str,
        entity_id: str,
        taxonomy_name: str,
        canonical_value: str
    ) -> Optional[TagAssignment]:
    """
        Look up a single assignment tuple.

        :param db_session: Active SQLAlchemy session.
        :param entity_kind: Entity kind (``project`` at M1).
        :param entity_id: Entity id.
        :param taxonomy_name: Taxonomy name.
        :param canonical_value: Canonical tag value.

        :returns: The :class:`TagAssignment` or None.
    """
    rtnval = (
        db_session.query(TagAssignment)
        .filter(TagAssignment.entity_kind == entity_kind)
        .filter(TagAssignment.entity_id == entity_id)
        .filter(TagAssignment.taxonomy_name == taxonomy_name)
        .filter(TagAssignment.canonical_value == canonical_value)
        .first()
    )
    return rtnval


def delete_assignment(*, db_session: DbSession, assignment: TagAssignment) -> None:
    """
        Remove an existing assignment.

        :param db_session: Active SQLAlchemy session.
        :param assignment: The row to delete.

        :returns: None.
    """
    db_session.delete(assignment)
    db_session.flush()
    return


def list_for_entity(
        *,
        db_session: DbSession,
        entity_kind: str,
        entity_id: str
    ) -> List[TagAssignment]:
    """
        Return every tag assigned to a particular entity.

        :param db_session: Active SQLAlchemy session.
        :param entity_kind: Entity kind (``project`` at M1).
        :param entity_id: Entity id.

        :returns: List of :class:`TagAssignment` rows.
    """
    query = db_session.query(TagAssignment).filter(
        TagAssignment.entity_kind == entity_kind
    )
    query = query.filter(TagAssignment.entity_id == entity_id)
    query = query.order_by(TagAssignment.taxonomy_name.asc(), TagAssignment.canonical_value.asc())

    rtnval = query.all()
    return rtnval


def list_for_kind(
        *,
        db_session: DbSession,
        entity_kind: str
    ) -> List[TagAssignment]:
    """
        Return every assignment rows for a given entity kind.

        :param db_session: Active SQLAlchemy session.
        :param entity_kind: Entity kind to scope the query to.

        :returns: List of :class:`TagAssignment` rows.
    """
    query = db_session.query(TagAssignment).filter(
        TagAssignment.entity_kind == entity_kind
    )
    query = query.order_by(TagAssignment.entity_id.asc())
    rtnval = query.all()
    return rtnval


def delete_for_entity(
        *,
        db_session: DbSession,
        entity_kind: str,
        entity_id: str
    ) -> int:
    """
        Remove every assignment targeting a given entity.

        :param db_session: Active SQLAlchemy session.
        :param entity_kind: Entity kind (``project`` at M1).
        :param entity_id: Entity id.

        :returns: Count of removed rows.
    """
    query = db_session.query(TagAssignment).filter(TagAssignment.entity_kind == entity_kind)
    query = query.filter(TagAssignment.entity_id == entity_id)
    removed = query.delete(synchronize_session=False)
    db_session.flush()

    rtnval = int(removed)
    return rtnval
