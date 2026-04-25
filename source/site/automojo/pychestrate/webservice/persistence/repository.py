"""
.. module:: persistence.repository
    :synopsis: Generic Repository helper with optimistic concurrency.

The Repository is a thin convenience wrapper that captures the
``load`` / ``load_many`` / ``save`` / ``delete`` patterns used
throughout the Phase-1 services. It is *not* a hard
abstraction — service modules are free to query through the
session directly when their access pattern doesn't fit the
repository shape. The wrapper exists so the common cases stay
uniform and so the optimistic-concurrency surface
(:class:`StaleEntityError`) lands in one place.

The repository works with any SQLAlchemy declarative model that
exposes:

* a single primary-key column whose name the caller supplies
  via :paramref:`id_column`.
* (optional) an integer ``version`` column the wrapper bumps
  on every save when ``optimistic=True``.
* (optional) an ``updated_at`` column the wrapper stamps with
  ``utc_now`` when present.

The wrapper does not own the session lifecycle — the caller
opens the session, hands it to the repository, and decides
when to commit. The :func:`unit_of_work` context manager
provides the matching transaction shape.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from datetime import datetime
from typing import Any, Callable, Generic, Iterable, List, Optional, Sequence, Type, TypeVar

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event
from automojo.pychestrate.webservice.persistence.exceptions import (
    EntityNotFoundError,
    StaleEntityError,
)


T = TypeVar("T")


class Repository(Generic[T]):
    """
        Generic load / save / delete helper for SQLAlchemy
        models. Construct one per (session, model) pair — the
        helper is cheap, intentionally short-lived, and does
        not cache anything across calls.
    """

    def __init__(
            self,
            *,
            db_session: DbSession,
            model: Type[T],
            id_column: str,
            entity_kind: str,
            version_column: Optional[str] = "version",
            updated_at_column: Optional[str] = "updated_at"
        ) -> None:
        self._db_session: DbSession = db_session
        self._model: Type[T] = model
        self._id_column: str = id_column
        self._entity_kind: str = entity_kind
        self._version_column: Optional[str] = version_column
        self._updated_at_column: Optional[str] = updated_at_column
        return

    # ------------------------------------------------------------
    # Load
    # ------------------------------------------------------------

    def load(self, *, entity_id: Any) -> Optional[T]:
        """
            Return the row whose id matches, or ``None`` when
            not present.
        """
        column = getattr(self._model, self._id_column)
        rtnval = (
            self._db_session.query(self._model)
            .filter(column == entity_id)
            .first()
        )
        return rtnval

    def load_many(
            self, *, entity_ids: Sequence[Any]
        ) -> List[T]:
        """
            Return rows matching ``entity_ids``. Missing ids
            are silently omitted; the caller computes the
            difference. Returns an empty list when the input
            is empty.
        """
        if entity_ids is None or len(entity_ids) == 0:
            return []
        column = getattr(self._model, self._id_column)
        rows = (
            self._db_session.query(self._model)
            .filter(column.in_(list(entity_ids)))
            .all()
        )
        rtnval = list(rows)
        return rtnval

    # ------------------------------------------------------------
    # Save
    # ------------------------------------------------------------

    def save(
            self,
            *,
            entity: T,
            optimistic: bool = True,
            emit_lifecycle_event: bool = True
        ) -> T:
        """
            Persist ``entity``. When ``optimistic`` is True,
            the helper compares the in-memory ``version`` with
            the DB row's version (if both exist) and raises
            :class:`StaleEntityError` on mismatch — the M2
            optimistic-concurrency contract.

            When the model carries a ``updated_at`` column,
            the helper stamps it. When the model carries a
            ``version`` column, the helper bumps it.

            ``emit_lifecycle_event=True`` (default) enqueues
            ``entity.<kind>.saved`` through the in-process
            outbox so the message bus observes the write.

            :raises: StaleEntityError when the optimistic
                     check fails.
        """
        if entity is None:
            err_lines = ["Repository.save requires a non-None entity."]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None

        entity_id = getattr(entity, self._id_column, None)
        if entity_id is None:
            err_lines = ["Repository.save entity is missing its id column."]
            err_lines.append("ID_COLUMN: {}".format(self._id_column))
            err_lines.append("ENTITY: {}".format(repr(entity)))
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None

        if optimistic is True:
            self._check_optimistic_concurrency(
                entity=entity, entity_id=entity_id,
            )

        if self._updated_at_column is not None and hasattr(
            entity, self._updated_at_column,
        ):
            try:
                setattr(entity, self._updated_at_column, utc_now())
            except AttributeError:
                # Some descriptor-based attributes refuse direct sets
                # — let the caller stamp manually in that case.
                pass

        if (
            optimistic is True
            and self._version_column is not None
            and hasattr(entity, self._version_column)
        ):
            current_version = int(
                getattr(entity, self._version_column, 0) or 0,
            )
            try:
                setattr(
                    entity,
                    self._version_column,
                    current_version + 1,
                )
            except AttributeError:
                pass

        self._db_session.merge(entity) if entity in self._db_session.deleted else None
        self._db_session.add(entity)
        self._db_session.flush()

        if emit_lifecycle_event is True:
            self._emit_lifecycle_event(
                entity_id=entity_id, action="saved",
            )

        rtnval = entity
        return rtnval

    # ------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------

    def delete(
            self,
            *,
            entity_id: Any,
            expected_version: Optional[int] = None,
            require_existence: bool = False,
            emit_lifecycle_event: bool = True
        ) -> bool:
        """
            Remove the row.

            :param entity_id: PK value to delete.
            :param expected_version: When the model carries a
                                     ``version`` column and
                                     this argument is non-None,
                                     the helper raises
                                     :class:`StaleEntityError`
                                     on mismatch.
            :param require_existence: When ``True`` and no
                                      row matches, raises
                                      :class:`EntityNotFoundError`
                                      instead of returning
                                      ``False``.
            :param emit_lifecycle_event: Enqueue
                                        ``entity.<kind>.deleted``
                                        on success.

            :returns: ``True`` when a row was deleted.
        """
        existing = self.load(entity_id=entity_id)
        if existing is None:
            if require_existence is True:
                err_lines = ["Repository.delete found no matching row."]
                err_lines.append("ID: {}".format(entity_id))
                err_lines.append("KIND: {}".format(self._entity_kind))
                err_msg = os.linesep.join(err_lines)
                raise EntityNotFoundError(err_msg) from None
            return False

        if (
            expected_version is not None
            and self._version_column is not None
            and hasattr(existing, self._version_column)
        ):
            actual_version = int(
                getattr(existing, self._version_column, 0) or 0,
            )
            if actual_version != int(expected_version):
                err_lines = [
                    "Repository.delete optimistic-version check failed.",
                ]
                err_lines.append("ID: {}".format(entity_id))
                err_lines.append("KIND: {}".format(self._entity_kind))
                err_lines.append("EXPECTED: {}".format(expected_version))
                err_lines.append("ACTUAL: {}".format(actual_version))
                err_msg = os.linesep.join(err_lines)
                raise StaleEntityError(err_msg) from None

        self._db_session.delete(existing)
        self._db_session.flush()
        if emit_lifecycle_event is True:
            self._emit_lifecycle_event(
                entity_id=entity_id, action="deleted",
            )
        return True

    # ------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------

    def _check_optimistic_concurrency(
            self, *, entity: T, entity_id: Any
        ) -> None:
        if self._version_column is None:
            return
        if not hasattr(entity, self._version_column):
            return
        in_memory_version = int(
            getattr(entity, self._version_column, 0) or 0,
        )
        existing = self.load(entity_id=entity_id)
        if existing is None:
            # First-write path; nothing to race against.
            return
        if existing is entity:
            # The caller passed the exact same instance the
            # ORM is already tracking; the in-memory version
            # is therefore the DB version.
            return
        actual_version = int(
            getattr(existing, self._version_column, 0) or 0,
        )
        if actual_version != in_memory_version:
            err_lines = ["Optimistic-concurrency check failed."]
            err_lines.append("ID: {}".format(entity_id))
            err_lines.append("KIND: {}".format(self._entity_kind))
            err_lines.append(
                "IN_MEMORY_VERSION: {}".format(in_memory_version),
            )
            err_lines.append(
                "DB_VERSION: {}".format(actual_version),
            )
            err_msg = os.linesep.join(err_lines)
            raise StaleEntityError(err_msg) from None
        return

    def _emit_lifecycle_event(
            self, *, entity_id: Any, action: str
        ) -> None:
        topic = "entity.{}.{}".format(self._entity_kind, action)
        payload = {
            "entity_id": str(entity_id),
            "kind": self._entity_kind,
            "action": action,
            "stamped_at": utc_now().isoformat(),
        }
        enqueue_event(
            db_session=self._db_session,
            event=EntityEvent(
                topic=topic,
                payload=payload,
                source_event_id=new_uuid(),
            ),
        )
        return
