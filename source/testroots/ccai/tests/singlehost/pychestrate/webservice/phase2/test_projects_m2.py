"""
.. module:: test_projects_m2
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 2-projects M2 behaviour.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.messaging.event_bus import subscribe
from ccai.pychestrate.webservice.projects import service as project_service
from ccai.pychestrate.webservice.projects.exceptions import (
    LastAdminRemovalError,
    MemberBindingNotFoundError,
    MetadataFieldValidationError,
    ProjectStateTransitionError,
)
from ccai.pychestrate.webservice.projects.models import ProjectState

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)
from ccai.tests.singlehost.pychestrate.webservice.phase2.fixtures import (
    reset_phase2_runtime,
)


def _create(session) -> str:
    """
        Helper: create a project and return its slug.
    """
    proj = project_service.create_project(
        db_session=session,
        slug="m2-project",
        display_name="M2 Project",
        description="",
        owning_group_id=None,
        template_id=None,
        template_version=None,
        actor_user_id=None,
    )
    return proj.slug


def test_archive_and_unarchive_cycle():
    """
    **Feature: 2-projects (M2)**
    **Property: archive moves to ARCHIVED + emits; unarchive returns to ACTIVE.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(topic="entity.project.archived", subscriber=lambda e: received.append(e))

    slug = _create(session)
    archived = project_service.archive_project(
        db_session=session, slug=slug, actor_user_id=None,
    )
    testbase.assert_equal(archived.state, ProjectState.ARCHIVED)
    testbase.assert_equal(len(received), 1)

    unarchived = project_service.unarchive_project(
        db_session=session, slug=slug, actor_user_id=None,
    )
    testbase.assert_equal(unarchived.state, ProjectState.ACTIVE)
    return


def test_delete_requires_archive():
    """
    **Feature: 2-projects (M2)**
    **Property: delete_project on an ACTIVE project raises
    ProjectStateTransitionError; after archive, delete succeeds and emits.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(topic="entity.project.deleted", subscriber=lambda e: received.append(e))

    slug = _create(session)
    raised = False
    try:
        project_service.delete_project(
            db_session=session, slug=slug, actor_user_id=None,
        )
    except ProjectStateTransitionError:
        raised = True
    testbase.assert_equal(raised, True)

    project_service.archive_project(db_session=session, slug=slug, actor_user_id=None)
    project_service.delete_project(db_session=session, slug=slug, actor_user_id=None)
    testbase.assert_equal(len(received), 1)
    return


def test_add_and_remove_member_with_last_admin_safeguard():
    """
    **Feature: 2-projects (M2)**
    **Property: removing the last ProjectOwner raises LastAdminRemovalError.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    slug = _create(session)
    owner_id = new_uuid()
    viewer_id = new_uuid()

    project_service.add_member(
        db_session=session, slug=slug, user_id=owner_id,
        role_name="project-owner", actor_user_id=None,
    )
    project_service.add_member(
        db_session=session, slug=slug, user_id=viewer_id,
        role_name="Viewer", actor_user_id=None,
    )

    members = project_service.list_members(db_session=session, slug=slug)
    testbase.assert_equal(len(members), 2)

    raised = False
    try:
        project_service.remove_member(
            db_session=session, slug=slug, user_id=owner_id,
            role_name="project-owner", actor_user_id=None,
        )
    except LastAdminRemovalError:
        raised = True
    testbase.assert_equal(raised, True)

    project_service.remove_member(
        db_session=session, slug=slug, user_id=viewer_id,
        role_name="Viewer", actor_user_id=None,
    )

    raised2 = False
    try:
        project_service.remove_member(
            db_session=session, slug=slug, user_id=viewer_id,
            role_name="Viewer", actor_user_id=None,
        )
    except MemberBindingNotFoundError:
        raised2 = True
    testbase.assert_equal(raised2, True)
    return


def test_patch_project_validates_extension_field():
    """
    **Feature: 2-projects (M2)**
    **Property: PATCH rejects unknown extension fields.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    slug = _create(session)

    updated = project_service.patch_project(
        db_session=session, slug=slug,
        display_name=None, description=None,
        extension_fields={"cost_center": "ABC-123"},
        actor_user_id=None,
    )
    testbase.assert_equal(updated.extension_fields.get("cost_center"), "ABC-123")

    raised = False
    try:
        project_service.patch_project(
            db_session=session, slug=slug,
            display_name=None, description=None,
            extension_fields={"unknown_field": "x"},
            actor_user_id=None,
        )
    except MetadataFieldValidationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_cascade_user_deleted_removes_bindings():
    """
    **Feature: 2-projects (M2)**
    **Property: cascade_user_deleted drops every binding for the user.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    slug = _create(session)
    user_id = new_uuid()

    project_service.add_member(
        db_session=session, slug=slug, user_id=user_id,
        role_name="Viewer", actor_user_id=None,
    )
    testbase.assert_equal(len(project_service.list_members(db_session=session, slug=slug)), 1)

    removed = project_service.cascade_user_deleted(db_session=session, user_id=user_id)
    testbase.assert_equal(removed, 1)
    testbase.assert_equal(len(project_service.list_members(db_session=session, slug=slug)), 0)
    return
