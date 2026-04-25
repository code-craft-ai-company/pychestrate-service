"""
.. module:: test_p13b_persistence_repository_m2
    :synopsis: Tests for P13b — 0-persistence Repository + unit_of_work.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timezone
from typing import List

import sqlalchemy as sa

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.pychestrate.core.defaults import utc_now

from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from automojo.pychestrate.webservice.persistence import (
    EntityNotFoundError,
    PychestratePhase1Base,
    Repository,
    StaleEntityError,
    UnitOfWorkMisuseError,
    reset_uow_for_testing,
    unit_of_work,
)


_TEST_TABLE_BUILT: bool = False


class _PersistenceTestEntity(PychestratePhase1Base):
    """
        Throwaway model used to exercise the Repository
        helper without depending on any real Phase-1 table.
    """
    __tablename__ = "p13b_persistence_test_entity"

    entity_id = Column(String(64), primary_key=True)
    name = Column(String(64), nullable=False, default="")
    version = Column(Integer, nullable=False, default=1)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now,
    )


def _build_session() -> sa.orm.Session:
    engine = sa.create_engine("sqlite://")
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    rtnval = factory()
    return rtnval


def _prepare_runtime() -> None:
    reset_event_bus()
    reset_uow_for_testing()
    return


def _make_repository(*, session) -> Repository:
    return Repository(
        db_session=session,
        model=_PersistenceTestEntity,
        id_column="entity_id",
        entity_kind="persistence_test",
    )


# -------------------------------------
# load / load_many
# -------------------------------------

def test_load_returns_persisted_row():
    """
    **Feature: 0-persistence (M2)**
    **Property: Repository.load returns the persisted row by
    primary key.**
    """
    _prepare_runtime()
    session = _build_session()
    repository = _make_repository(session=session)
    repository.save(
        entity=_PersistenceTestEntity(
            entity_id="alpha", name="Alpha",
        ),
    )
    session.commit()
    fetched = repository.load(entity_id="alpha")
    testbase.assert_equal(fetched.entity_id, "alpha")
    testbase.assert_equal(fetched.name, "Alpha")
    return


def test_load_returns_none_for_unknown_id():
    """
    **Feature: 0-persistence (M2)**
    **Property: Repository.load returns None for an unknown
    id rather than raising.**
    """
    _prepare_runtime()
    session = _build_session()
    repository = _make_repository(session=session)
    fetched = repository.load(entity_id="ghost")
    testbase.assert_equal(fetched, None)
    return


def test_load_many_returns_subset_omitting_unknown_ids():
    """
    **Feature: 0-persistence (M2)**
    **Property: Repository.load_many silently omits ids that
    do not exist.**
    """
    _prepare_runtime()
    session = _build_session()
    repository = _make_repository(session=session)
    repository.save(entity=_PersistenceTestEntity(entity_id="a"))
    repository.save(entity=_PersistenceTestEntity(entity_id="b"))
    session.commit()
    rows = repository.load_many(
        entity_ids=["a", "b", "missing"],
    )
    ids = sorted(r.entity_id for r in rows)
    testbase.assert_equal(ids, ["a", "b"])
    return


def test_load_many_empty_input_returns_empty_list():
    """
    **Feature: 0-persistence (M2)**
    **Property: Repository.load_many with an empty input
    returns an empty list and does not query the DB.**
    """
    _prepare_runtime()
    session = _build_session()
    repository = _make_repository(session=session)
    rows = repository.load_many(entity_ids=[])
    testbase.assert_equal(rows, [])
    return


# -------------------------------------
# save
# -------------------------------------

def test_save_bumps_version_and_stamps_updated_at():
    """
    **Feature: 0-persistence (M2)**
    **Property: a save with optimistic=True bumps the
    version column and stamps updated_at.**
    """
    _prepare_runtime()
    session = _build_session()
    repository = _make_repository(session=session)
    entity = _PersistenceTestEntity(entity_id="alpha", version=1)
    repository.save(entity=entity)
    session.commit()
    testbase.assert_equal(entity.version, 2)
    testbase.assert_equal(entity.updated_at is not None, True)
    return


def test_save_optimistic_concurrency_raises_on_stale_version():
    """
    **Feature: 0-persistence (M2)**
    **Property: a save whose in-memory version is older than
    the persisted row raises StaleEntityError.**
    """
    _prepare_runtime()
    session = _build_session()
    repository = _make_repository(session=session)
    repository.save(
        entity=_PersistenceTestEntity(
            entity_id="dup", name="initial", version=1,
        ),
    )
    session.commit()

    # Bump the persisted row out of band — simulates the
    # other writer landing first.
    persisted = repository.load(entity_id="dup")
    persisted.version = 5
    session.flush()
    session.commit()
    session.expire(persisted)

    # Construct a fresh in-memory entity carrying the *old*
    # version — this is what a stale caller would hand in.
    stale = _PersistenceTestEntity(
        entity_id="dup", name="from-stale", version=1,
    )
    raised = False
    try:
        repository.save(entity=stale)
    except StaleEntityError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_save_emits_lifecycle_event():
    """
    **Feature: 0-persistence (M2)**
    **Property: save emits ``entity.<kind>.saved`` on the bus
    by default; passing emit_lifecycle_event=False suppresses
    the emit.**
    """
    _prepare_runtime()
    session = _build_session()
    repository = _make_repository(session=session)
    received: List[EntityEvent] = []
    subscribe(
        topic="entity.persistence_test.saved",
        subscriber=lambda e: received.append(e),
    )
    repository.save(entity=_PersistenceTestEntity(entity_id="alpha"))
    session.commit()
    testbase.assert_equal(len(received), 1)

    repository.save(
        entity=_PersistenceTestEntity(entity_id="beta"),
        emit_lifecycle_event=False,
    )
    session.commit()
    testbase.assert_equal(len(received), 1)
    return


def test_save_rejects_entity_with_missing_id():
    """
    **Feature: 0-persistence (M2)**
    **Property: save raises ValueError when the entity does
    not carry the configured id column.**
    """
    _prepare_runtime()
    session = _build_session()
    repository = _make_repository(session=session)
    raised = False
    try:
        repository.save(entity=_PersistenceTestEntity())
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# delete
# -------------------------------------

def test_delete_returns_true_when_row_existed():
    """
    **Feature: 0-persistence (M2)**
    **Property: delete returns True on a successful delete
    and False when the id was not found.**
    """
    _prepare_runtime()
    session = _build_session()
    repository = _make_repository(session=session)
    repository.save(entity=_PersistenceTestEntity(entity_id="alpha"))
    session.commit()
    first = repository.delete(entity_id="alpha")
    second = repository.delete(entity_id="alpha")
    testbase.assert_equal(first, True)
    testbase.assert_equal(second, False)
    return


def test_delete_require_existence_raises_on_miss():
    """
    **Feature: 0-persistence (M2)**
    **Property: delete with require_existence=True raises
    EntityNotFoundError when the id is not found.**
    """
    _prepare_runtime()
    session = _build_session()
    repository = _make_repository(session=session)
    raised = False
    try:
        repository.delete(
            entity_id="not-real",
            require_existence=True,
        )
    except EntityNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_delete_optimistic_version_mismatch_raises():
    """
    **Feature: 0-persistence (M2)**
    **Property: delete with expected_version that does not
    match raises StaleEntityError.**
    """
    _prepare_runtime()
    session = _build_session()
    repository = _make_repository(session=session)
    repository.save(
        entity=_PersistenceTestEntity(entity_id="alpha", version=1),
    )
    session.commit()
    raised = False
    try:
        repository.delete(
            entity_id="alpha", expected_version=99,
        )
    except StaleEntityError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_delete_emits_lifecycle_event():
    """
    **Feature: 0-persistence (M2)**
    **Property: delete emits ``entity.<kind>.deleted`` on
    success.**
    """
    _prepare_runtime()
    session = _build_session()
    repository = _make_repository(session=session)
    received: List[EntityEvent] = []
    subscribe(
        topic="entity.persistence_test.deleted",
        subscriber=lambda e: received.append(e),
    )
    repository.save(entity=_PersistenceTestEntity(entity_id="alpha"))
    session.commit()
    repository.delete(entity_id="alpha")
    session.commit()
    testbase.assert_equal(len(received), 1)
    return


# -------------------------------------
# unit_of_work
# -------------------------------------

def test_unit_of_work_commits_on_clean_exit():
    """
    **Feature: 0-persistence (M2)**
    **Property: the outermost unit_of_work commits the
    session on a clean exit; the row is visible in a fresh
    session afterwards.**
    """
    _prepare_runtime()
    session = _build_session()
    with unit_of_work(db_session=session):
        session.add(_PersistenceTestEntity(entity_id="alpha"))
    fresh = sessionmaker(bind=session.bind)()
    try:
        row = (
            fresh.query(_PersistenceTestEntity)
            .filter(_PersistenceTestEntity.entity_id == "alpha")
            .first()
        )
        testbase.assert_equal(row is not None, True)
    finally:
        fresh.close()
    return


def test_unit_of_work_rolls_back_on_exception():
    """
    **Feature: 0-persistence (M2)**
    **Property: an exception inside the outermost
    unit_of_work rolls back the transaction so no row
    persists.**
    """
    _prepare_runtime()
    session = _build_session()
    raised = False
    try:
        with unit_of_work(db_session=session):
            session.add(_PersistenceTestEntity(entity_id="alpha"))
            raise RuntimeError("boom")
    except RuntimeError:
        raised = True
    testbase.assert_equal(raised, True)
    fresh = sessionmaker(bind=session.bind)()
    try:
        row = (
            fresh.query(_PersistenceTestEntity)
            .filter(_PersistenceTestEntity.entity_id == "alpha")
            .first()
        )
        testbase.assert_equal(row, None)
    finally:
        fresh.close()
    return


def test_unit_of_work_nested_savepoint_isolates_inner_failure():
    """
    **Feature: 0-persistence (M2)**
    **Property: an exception inside a nested savepoint rolls
    that savepoint back without aborting the outer
    transaction. Outer-only writes still commit.**
    """
    _prepare_runtime()
    session = _build_session()
    raised = False
    with unit_of_work(db_session=session):
        session.add(_PersistenceTestEntity(entity_id="outer"))
        session.flush()
        try:
            with unit_of_work(db_session=session):
                session.add(
                    _PersistenceTestEntity(entity_id="inner"),
                )
                session.flush()
                raise ValueError("inner fail")
        except ValueError:
            raised = True
    testbase.assert_equal(raised, True)
    fresh = sessionmaker(bind=session.bind)()
    try:
        outer_row = (
            fresh.query(_PersistenceTestEntity)
            .filter(_PersistenceTestEntity.entity_id == "outer")
            .first()
        )
        inner_row = (
            fresh.query(_PersistenceTestEntity)
            .filter(_PersistenceTestEntity.entity_id == "inner")
            .first()
        )
        testbase.assert_equal(outer_row is not None, True)
        testbase.assert_equal(inner_row, None)
    finally:
        fresh.close()
    return


def test_unit_of_work_nested_clean_exit_commits_savepoint():
    """
    **Feature: 0-persistence (M2)**
    **Property: a nested savepoint releases on a clean exit
    and the row is visible after the outer commit.**
    """
    _prepare_runtime()
    session = _build_session()
    with unit_of_work(db_session=session):
        session.add(_PersistenceTestEntity(entity_id="outer"))
        with unit_of_work(db_session=session):
            session.add(_PersistenceTestEntity(entity_id="inner"))
    fresh = sessionmaker(bind=session.bind)()
    try:
        ids = sorted(
            row.entity_id for row in
            fresh.query(_PersistenceTestEntity).all()
        )
        testbase.assert_equal(ids, ["inner", "outer"])
    finally:
        fresh.close()
    return
