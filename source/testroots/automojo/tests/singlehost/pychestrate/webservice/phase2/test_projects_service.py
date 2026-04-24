"""
.. module:: test_projects_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 2-projects M1 service surface.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.pychestrate.webservice.messaging.event_bus import subscribe
from automojo.pychestrate.webservice.projects import service as project_service
from automojo.pychestrate.webservice.projects.exceptions import (
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    SlugValidationError,
)
from automojo.pychestrate.webservice.projects.models import ProjectState

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)
from automojo.tests.singlehost.pychestrate.webservice.phase2.fixtures import (
    reset_phase2_runtime,
)


def test_create_project_round_trip_and_event():
    """
    **Feature: 2-projects (M1)**
    **Property: create_project persists a row and publishes
    entity.project.created.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(topic="entity.project.created", subscriber=lambda e: received.append(e))

    project = project_service.create_project(
        db_session=session,
        slug="ExampleProject",
        display_name="Example Project",
        description="Round-trip test project.",
        owning_group_id=None,
        template_id=None,
        template_version=None,
        actor_user_id=None,
    )

    testbase.assert_equal(project.slug, "exampleproject")
    testbase.assert_equal(project.state, ProjectState.ACTIVE)
    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(received[0].payload["slug"], "exampleproject")

    fetched = project_service.read_project_by_slug(db_session=session, slug="exampleproject")
    testbase.assert_equal(str(fetched.project_id), str(project.project_id))
    return


def test_create_project_duplicate_slug_raises():
    """
    **Feature: 2-projects (M1)**
    **Property: A second create_project with the same canonical slug
    raises ProjectAlreadyExistsError.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    project_service.create_project(
        db_session=session,
        slug="dup-proj",
        display_name="First",
        description="",
        owning_group_id=None,
        template_id=None,
        template_version=None,
        actor_user_id=None,
    )

    raised = False
    try:
        project_service.create_project(
            db_session=session,
            slug="DUP-PROJ",
            display_name="Second",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )
    except ProjectAlreadyExistsError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_create_project_invalid_slug_raises():
    """
    **Feature: 2-projects (M1)**
    **Property: A slug that violates the pattern raises SlugValidationError.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        project_service.create_project(
            db_session=session,
            slug="1-bad",
            display_name="Bad Leading Digit",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )
    except SlugValidationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_read_project_missing_raises():
    """
    **Feature: 2-projects (M1)**
    **Property: read_project_by_slug raises ProjectNotFoundError when
    the slug is not present.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        project_service.read_project_by_slug(db_session=session, slug="nope-proj")
    except ProjectNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return
