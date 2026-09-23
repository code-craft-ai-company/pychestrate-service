"""
.. module:: test_release_template_manager_create_release
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for creating a release from a release template

.. moduleauthor:: Code Craft AI LLC

A release template carries a project's release defaults. Creating a
release from one must apply them, record where the release came from,
and hold the version to the template's pattern.

**Feature: projects (PRJ-09 release from template)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from typing import Any, Dict

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from ccai import testbase

from ccai.pychestrate.core.managers.release_template_manager import (
    ReleaseTemplateManager,
    ReleaseTemplateNotFoundError,
    ReleaseTemplateValidationError,
)
from ccai.pychestrate.core.orm import (
    Project,
    ProjectRelease,
    ProjectRepository,
    PychestrateModelBase,
)


def _projects_with_template() -> Any:
    """
        Two projects; "alpha" has a release template with every default
        set and the version pattern ``^\\d+\\.\\d+\\.\\d+$``.

        :returns: Tuple of (session, manager, ids).
    """
    engine = sa.create_engine("sqlite://")
    PychestrateModelBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    ids: Dict[str, int] = {}
    for name in ("alpha", "beta"):
        project = Project(name=name, owner_id=uuid.uuid4(), metadata_json={})
        session.add(project)
        session.flush()
        ids[name] = project.id
    # The template's default repositories must be the project's own.
    for repo_id in (3, 4):
        session.add(ProjectRepository(
            id=repo_id, project_id=ids["alpha"], name="repo-{}".format(repo_id),
            url="https://example.invalid/repo-{}.git".format(repo_id), auth_type="none",
            default_branch="main",
        ))
    session.commit()
    manager = ReleaseTemplateManager(db_session=session)
    template = manager.create(
        ids["alpha"],
        name="standard",
        description="Quarterly release",
        default_channel="stable",
        version_pattern=r"^\d+\.\d+\.\d+$",
        default_repo_ids=[3, 4],
        default_pipeline={"stages": ["build"]},
        default_schedule={"cron": "0 0 * * 1"},
    )
    ids["template"] = template.id
    rtnval = (session, manager, ids)
    return rtnval


def test_create_release_from_template_records_the_template_defaults():
    """
    **Feature: projects (PRJ-09 release from template)**
    **Property: the draft release's metadata carries the template's id
    and name and its channel, version pattern, repositories, pipeline
    and schedule.**
    """
    session, manager, ids = _projects_with_template()

    release = manager.create_release_from_template(
        ids["alpha"], ids["template"], version="1.4.0", user_id=str(uuid.uuid4()),
    )

    testbase.assert_equal(
        release.metadata,
        {
            "template_id": ids["template"],
            "template_name": "standard",
            "channel": "stable",
            "version_pattern": r"^\d+\.\d+\.\d+$",
            "repository_ids": [3, 4],
            "pipeline": {"stages": ["build"]},
            "schedule": {"cron": "0 0 * * 1"},
        },
    )
    return


def test_create_release_from_template_defaults_the_name_from_the_template():
    """
    **Feature: projects (PRJ-09 release from template)**
    **Property: without a name, the release is named "<template> <version>"
    and takes the template's description.**
    """
    session, manager, ids = _projects_with_template()

    release = manager.create_release_from_template(ids["alpha"], ids["template"], version="2.0.0")

    testbase.assert_equal(
        (release.name, release.description), ("standard 2.0.0", "Quarterly release")
    )
    return


def test_create_release_from_template_refuses_a_version_outside_the_pattern():
    """
    **Feature: projects (PRJ-09 release from template)**
    **Property: a semantic version that does not match the template's
    pattern (a pre-release against ``x.y.z``) is refused on the version
    field and no release is created.**
    """
    session, manager, ids = _projects_with_template()

    refused_field = None
    try:
        manager.create_release_from_template(ids["alpha"], ids["template"], version="1.4.0-rc1")
    except ReleaseTemplateValidationError as refusal:
        refused_field = refusal.field

    testbase.assert_equal((refused_field, session.query(ProjectRelease).count()), ("version", 0))
    return


def test_create_release_from_template_requires_a_version():
    """
    **Feature: projects (PRJ-09 release from template)**
    **Property: a blank version is refused with MISSING_VERSION.**
    """
    session, manager, ids = _projects_with_template()

    error_code = None
    try:
        manager.create_release_from_template(ids["alpha"], ids["template"], version="   ")
    except ReleaseTemplateValidationError as refusal:
        error_code = refusal.error_code

    testbase.assert_equal(error_code, "MISSING_VERSION")
    return


def test_create_release_from_template_refuses_another_projects_template():
    """
    **Feature: projects (PRJ-09 release from template)**
    **Property: project beta cannot create a release from project
    alpha's template.**
    """
    session, manager, ids = _projects_with_template()

    refused = False
    try:
        manager.create_release_from_template(ids["beta"], ids["template"], version="1.0.0")
    except ReleaseTemplateNotFoundError:
        refused = True

    testbase.assert_equal(refused, True)
    return
