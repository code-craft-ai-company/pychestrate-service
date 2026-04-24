"""
.. module:: variables.repository
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Repository for :class:`VariableBinding` rows.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.variables.models import (
    VariableBinding,
    VariableScope,
)


def upsert_binding(*, db_session: DbSession, binding: VariableBinding) -> VariableBinding:
    """
        Persist or replace a variable binding.

        :param db_session: Active SQLAlchemy session.
        :param binding: The fully-populated binding to persist.

        :returns: The persistent row (may be a pre-existing row with mutated
                  ``value_text`` / ``value_type``).
    """
    existing = get_binding(
        db_session=db_session,
        scope=binding.scope,
        scope_id=binding.scope_id,
        name=binding.name,
    )
    if existing is None:
        db_session.add(binding)
        db_session.flush()
        rtnval = binding
        return rtnval

    existing.value_type = binding.value_type
    existing.value_text = binding.value_text
    existing.set_by_user_id = binding.set_by_user_id
    existing.set_at = binding.set_at
    db_session.add(existing)
    db_session.flush()

    rtnval = existing
    return rtnval


def get_binding(
        *,
        db_session: DbSession,
        scope: VariableScope,
        scope_id: str,
        name: str
    ) -> Optional[VariableBinding]:
    """
        Look up a binding by its composite key.

        :param db_session: Active SQLAlchemy session.
        :param scope: Target scope.
        :param scope_id: Scope-local identifier.
        :param name: Variable name.

        :returns: The :class:`VariableBinding` or None.
    """
    normalized_id = scope_id if scope_id is not None else ""

    rtnval = (
        db_session.query(VariableBinding)
        .filter(VariableBinding.scope == scope)
        .filter(VariableBinding.scope_id == normalized_id)
        .filter(VariableBinding.name == name)
        .first()
    )
    return rtnval


def delete_binding(*, db_session: DbSession, binding: VariableBinding) -> None:
    """
        Remove a binding.

        :param db_session: Active SQLAlchemy session.
        :param binding: The row to delete.

        :returns: None.
    """
    db_session.delete(binding)
    db_session.flush()
    return


def list_for_scope(
        *,
        db_session: DbSession,
        scope: VariableScope,
        scope_id: str
    ) -> List[VariableBinding]:
    """
        List all bindings for a given scope.

        :param db_session: Active SQLAlchemy session.
        :param scope: Target scope.
        :param scope_id: Scope-local identifier.

        :returns: List of :class:`VariableBinding` rows.
    """
    normalized_id = scope_id if scope_id is not None else ""

    query = db_session.query(VariableBinding).filter(VariableBinding.scope == scope)
    query = query.filter(VariableBinding.scope_id == normalized_id)
    query = query.order_by(VariableBinding.name.asc())

    rtnval = query.all()
    return rtnval


def delete_for_scope(
        *,
        db_session: DbSession,
        scope: VariableScope,
        scope_id: str
    ) -> int:
    """
        Delete every binding under a given scope.

        :param db_session: Active SQLAlchemy session.
        :param scope: Target scope.
        :param scope_id: Scope-local identifier.

        :returns: Count of removed rows.
    """
    normalized_id = scope_id if scope_id is not None else ""

    query = db_session.query(VariableBinding).filter(VariableBinding.scope == scope)
    query = query.filter(VariableBinding.scope_id == normalized_id)
    removed = query.delete(synchronize_session=False)
    db_session.flush()

    rtnval = int(removed)
    return rtnval
