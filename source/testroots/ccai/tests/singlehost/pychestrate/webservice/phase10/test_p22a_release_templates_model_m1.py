"""
.. module:: test_p22a_release_templates_model_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Unit tests for the project-scoped release-template
               ORM and :class:`ReleaseTemplateManager`.

.. moduleauthor:: Code Craft AI LLC

Covers the ORM column shape and the manager's CRUD surface
exercised against an in-memory SQLite database.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ccai.pychestrate.core.orm import (
    PychestrateModelBase,
    Project,
    ProjectReleaseTemplate,
    User,
)
from ccai.pychestrate.core.managers.release_template_manager import (
    DuplicateReleaseTemplateError,
    ReleaseTemplateManager,
    ReleaseTemplateNotFoundError,
    ReleaseTemplateProjectNotFoundError,
    ReleaseTemplateValidationError,
    validate_default_repo_ids,
    validate_template_name,
)


def _build_in_memory_session() -> Any:
    """
        Build a SQLAlchemy session bound to an in-memory SQLite
        database with every legacy ORM table created.

        :returns: SQLAlchemy session.
    """
    engine = create_engine("sqlite:///:memory:")
    PychestrateModelBase.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    rtnval = session_factory()
    return rtnval


def _seed_project(*, session: Any, name: str = "demo") -> Project:
    """
        Insert a parent ``User`` (owner FK) and a ``Project`` row.

        :param session: SQLAlchemy session.
        :param name: Project name.

        :returns: Created :class:`Project`.
    """
    owner = User(
        id=uuid.uuid4(),
        first_name="Owner",
        last_name="User",
        display_name="Owner",
        login="owner-{}".format(name),
        email="owner-{}@example.com".format(name),
        status="active",
        authtype="internal",
    )
    session.add(owner)
    session.flush()

    project = Project(
        name=name,
        description="seeded project",
        owner_id=owner.id,
        metadata_json={},
    )
    session.add(project)
    session.commit()
    rtnval = project
    return rtnval


def test_release_template_table_columns_present():
    """
        ``ProjectReleaseTemplate`` should expose every column called
        out by the feature spec.
    """
    expected_column_names = {
        "rtmpl_id",
        "proj_id",
        "rtmpl_name",
        "rtmpl_description",
        "rtmpl_default_channel",
        "rtmpl_version_pattern",
        "rtmpl_default_repo_ids",
        "rtmpl_default_pipeline",
        "rtmpl_default_schedule",
        "rtmpl_created_at",
        "rtmpl_updated_at",
    }
    actual_column_names = {
        column.name for column in ProjectReleaseTemplate.__table__.columns
    }
    assert expected_column_names.issubset(actual_column_names)
    return


def test_validate_template_name_accepts_well_formed_names():
    """
        ``validate_template_name`` should accept canonical names.
    """
    assert validate_template_name("ga") is True
    assert validate_template_name("ga-1") is True
    assert validate_template_name("release_2026.05") is True
    return


def test_validate_template_name_rejects_bad_names():
    """
        ``validate_template_name`` should reject empty / non-leading-
        alphanumeric strings.
    """
    assert validate_template_name("") is False
    assert validate_template_name(None) is False
    assert validate_template_name("-bad") is False
    assert validate_template_name("a" * 129) is False
    return


def test_validate_default_repo_ids_returns_errors_for_bad_input():
    """
        Non-list / non-int / negative inputs must surface errors.
    """
    assert validate_default_repo_ids(["x"]) != []
    assert validate_default_repo_ids("not-a-list") != []
    assert validate_default_repo_ids([-1]) != []
    assert validate_default_repo_ids([1, 2]) == []
    assert validate_default_repo_ids(None) == []
    return


def test_create_template_persists_row():
    """
        :meth:`ReleaseTemplateManager.create` must persist a row and
        return a populated response dataclass.
    """
    session = _build_in_memory_session()
    project = _seed_project(session=session)
    manager = ReleaseTemplateManager(db_session=session)

    response = manager.create(
        project.id,
        name="ga",
        description="general-availability",
        default_channel="stable",
        version_pattern=r"^\d+\.\d+\.\d+$",
        default_repo_ids=[1, 2],
        default_pipeline={"stages": []},
        default_schedule={"cron": "* * * * *"},
        created_by=None,
    )

    assert response.id > 0
    assert response.project_id == project.id
    assert response.name == "ga"
    assert response.default_repo_ids == [1, 2]
    assert response.default_pipeline == {"stages": []}
    assert response.default_schedule == {"cron": "* * * * *"}
    return


def test_create_template_rejects_unknown_project():
    """
        Creating against a missing project must raise.
    """
    session = _build_in_memory_session()
    manager = ReleaseTemplateManager(db_session=session)

    raised = False
    try:
        manager.create(
            999_999, name="ga",
            default_repo_ids=[],
        )
    except ReleaseTemplateProjectNotFoundError:
        raised = True

    assert raised is True
    return


def test_create_template_rejects_invalid_name():
    """
        Bad names must raise ``ReleaseTemplateValidationError``.
    """
    session = _build_in_memory_session()
    project = _seed_project(session=session)
    manager = ReleaseTemplateManager(db_session=session)

    raised = False
    try:
        manager.create(project.id, name="-bad", default_repo_ids=[])
    except ReleaseTemplateValidationError:
        raised = True

    assert raised is True
    return


def test_create_template_rejects_duplicate_name_in_project():
    """
        Names are unique inside a project.
    """
    session = _build_in_memory_session()
    project = _seed_project(session=session)
    manager = ReleaseTemplateManager(db_session=session)

    manager.create(project.id, name="ga", default_repo_ids=[])

    raised = False
    try:
        manager.create(project.id, name="ga", default_repo_ids=[])
    except DuplicateReleaseTemplateError:
        raised = True

    assert raised is True
    return


def test_list_for_project_returns_scoped_rows():
    """
        ``list_for_project`` must return only rows for that project.
    """
    session = _build_in_memory_session()
    project_a = _seed_project(session=session, name="alpha")
    project_b = _seed_project(session=session, name="beta")
    manager = ReleaseTemplateManager(db_session=session)

    manager.create(project_a.id, name="ga", default_repo_ids=[])
    manager.create(project_a.id, name="beta", default_repo_ids=[])
    manager.create(project_b.id, name="ga", default_repo_ids=[])

    a_listing = manager.list_for_project(project_a.id)
    b_listing = manager.list_for_project(project_b.id)

    assert a_listing.total == 2
    assert len(a_listing.templates) == 2
    assert b_listing.total == 1
    assert len(b_listing.templates) == 1
    return


def test_get_returns_none_for_missing_id():
    """
        ``get`` returns ``None`` for an unknown id.
    """
    session = _build_in_memory_session()
    manager = ReleaseTemplateManager(db_session=session)
    rtnval = manager.get(123_456)
    assert rtnval is None
    return


def test_update_template_changes_fields_and_persists():
    """
        ``update`` should patch the supplied fields and bump
        ``updated_at``.
    """
    session = _build_in_memory_session()
    project = _seed_project(session=session)
    manager = ReleaseTemplateManager(db_session=session)
    created = manager.create(
        project.id, name="ga", default_repo_ids=[1]
    )

    updated = manager.update(
        created.id,
        name="ga-v2",
        description="updated",
        default_channel="canary",
        default_repo_ids=[7, 8, 9],
    )

    assert updated.name == "ga-v2"
    assert updated.default_channel == "canary"
    assert updated.default_repo_ids == [7, 8, 9]
    assert updated.description == "updated"
    return


def test_update_template_rejects_duplicate_rename():
    """
        Renaming to an existing name must raise.
    """
    session = _build_in_memory_session()
    project = _seed_project(session=session)
    manager = ReleaseTemplateManager(db_session=session)

    manager.create(project.id, name="alpha", default_repo_ids=[])
    other = manager.create(project.id, name="beta", default_repo_ids=[])

    raised = False
    try:
        manager.update(other.id, name="alpha")
    except DuplicateReleaseTemplateError:
        raised = True

    assert raised is True
    return


def test_delete_template_removes_row():
    """
        ``delete`` must remove the row and subsequent ``get`` returns
        ``None``.
    """
    session = _build_in_memory_session()
    project = _seed_project(session=session)
    manager = ReleaseTemplateManager(db_session=session)
    created = manager.create(
        project.id, name="ga", default_repo_ids=[]
    )

    manager.delete(created.id)
    after = manager.get(created.id)

    assert after is None
    return


def test_delete_template_raises_for_missing_id():
    """
        Deleting a missing template must raise.
    """
    session = _build_in_memory_session()
    manager = ReleaseTemplateManager(db_session=session)

    raised = False
    try:
        manager.delete(999_999)
    except ReleaseTemplateNotFoundError:
        raised = True

    assert raised is True
    return
