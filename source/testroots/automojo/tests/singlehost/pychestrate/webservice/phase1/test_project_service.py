"""
.. module:: test_project_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Unit tests for 2-projects M1+M2 EARS requirements.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.messaging.event_bus import subscribe
from automojo.pychestrate.webservice.projects import service as project_service
from automojo.pychestrate.webservice.projects.events import ProjectEventTopics
from automojo.pychestrate.webservice.projects.exceptions import (
    LastAdminRemovalError,
    MemberBindingNotFoundError,
    MetadataFieldValidationError,
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    ProjectStateTransitionError,
    SlugValidationError,
)
from automojo.pychestrate.webservice.projects.models import Project, ProjectState
from automojo.pychestrate.webservice.projects.service import PROJECT_OWNER_ROLE

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


# =============================================================================
# Requirement 1 — Project creation with owner and audit event
# =============================================================================


def test_create_project_persists_and_publishes_event():
    """
    **Feature: 2-projects M1 (Requirement 1)**
    **Property: POST /projects persists a Project row and publishes
    entity.project.created once after commit.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        received = []
        subscribe(
            topic=ProjectEventTopics.PROJECT_CREATED,
            subscriber=lambda evt: received.append(evt),
        )

        created = project_service.create_project(
            db_session=session,
            slug="alpha-project",
            display_name="Alpha",
            description="First project",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )

        testbase.assert_equal(created.slug, "alpha-project")
        testbase.assert_equal(created.state, ProjectState.ACTIVE)
        testbase.assert_equal(len(received), 1)
        testbase.assert_equal(received[0].payload["slug"], "alpha-project")
    finally:
        session.close()
    return


def test_create_project_duplicate_slug_raises_conflict():
    """
    **Feature: 2-projects M1 (Requirement 1.2)**
    **Property: A second create against the same slug raises
    ProjectAlreadyExistsError and does not publish a second event.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        received = []
        subscribe(
            topic=ProjectEventTopics.PROJECT_CREATED,
            subscriber=lambda evt: received.append(evt),
        )

        project_service.create_project(
            db_session=session,
            slug="duplicate",
            display_name="One",
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
                slug="duplicate",
                display_name="Two",
                description="",
                owning_group_id=None,
                template_id=None,
                template_version=None,
                actor_user_id=None,
            )
        except ProjectAlreadyExistsError as xcpt:
            raised = True
            testbase.assert_equal("SLUG: duplicate" in str(xcpt), True)

        testbase.assert_equal(raised, True)
        testbase.assert_equal(len(received), 1)
    finally:
        session.close()
    return


def test_create_project_invalid_slug_raises_slug_validation():
    """
    **Feature: 2-projects M1 (Requirement 1.2)**
    **Property: A slug that fails canonicalization raises
    SlugValidationError with a multi-line message.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        raised = False
        try:
            project_service.create_project(
                db_session=session,
                slug="1bad-leading-digit",
                display_name="Bad",
                description="",
                owning_group_id=None,
                template_id=None,
                template_version=None,
                actor_user_id=None,
            )
        except SlugValidationError as xcpt:
            raised = True
            testbase.assert_equal("PATTERN:" in str(xcpt), True)

        testbase.assert_equal(raised, True)
    finally:
        session.close()
    return


# =============================================================================
# Requirement 2 — Archive and delete lifecycle
# =============================================================================


def test_archive_project_sets_state_and_publishes_event():
    """
    **Feature: 2-projects M2 (Requirement 2.1)**
    **Property: Archive transitions state=ARCHIVED, stamps archived_at,
    and publishes entity.project.archived.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        received = []
        subscribe(
            topic=ProjectEventTopics.PROJECT_ARCHIVED,
            subscriber=lambda evt: received.append(evt),
        )

        project_service.create_project(
            db_session=session,
            slug="archive-target",
            display_name="Target",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )

        archived = project_service.archive_project(
            db_session=session, slug="archive-target", actor_user_id=None,
        )

        testbase.assert_equal(archived.state, ProjectState.ARCHIVED)
        testbase.assert_equal(archived.archived_at is not None, True)
        testbase.assert_equal(len(received), 1)
    finally:
        session.close()
    return


def test_delete_project_requires_archived_state():
    """
    **Feature: 2-projects M2 (Requirement 2.3)**
    **Property: Deleting an active project raises
    ProjectStateTransitionError with the 'must be archived' text.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        project_service.create_project(
            db_session=session,
            slug="delete-guard",
            display_name="Guard",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )

        raised = False
        try:
            project_service.delete_project(
                db_session=session, slug="delete-guard", actor_user_id=None,
            )
        except ProjectStateTransitionError as xcpt:
            raised = True
            testbase.assert_equal("must be archived" in str(xcpt), True)

        testbase.assert_equal(raised, True)
    finally:
        session.close()
    return


def test_delete_project_after_archive_cascades_and_publishes_event():
    """
    **Feature: 2-projects M2 (Requirement 2.2)**
    **Property: Delete on an archived project removes the row and
    publishes entity.project.deleted.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        received = []
        subscribe(
            topic=ProjectEventTopics.PROJECT_DELETED,
            subscriber=lambda evt: received.append(evt),
        )

        project_service.create_project(
            db_session=session,
            slug="del-flow",
            display_name="Flow",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )
        project_service.archive_project(
            db_session=session, slug="del-flow", actor_user_id=None,
        )
        project_service.delete_project(
            db_session=session, slug="del-flow", actor_user_id=None,
        )

        remaining = session.query(Project).filter(Project.slug == "del-flow").first()
        testbase.assert_equal(remaining, None)
        testbase.assert_equal(len(received), 1)
    finally:
        session.close()
    return


def test_unarchive_project_restores_active_state():
    """
    **Feature: 2-projects M2 (Requirement 2 extension)**
    **Property: Unarchive returns state=ACTIVE and publishes
    entity.project.unarchived.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        received = []
        subscribe(
            topic=ProjectEventTopics.PROJECT_UNARCHIVED,
            subscriber=lambda evt: received.append(evt),
        )

        project_service.create_project(
            db_session=session,
            slug="round-trip",
            display_name="RT",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )
        project_service.archive_project(
            db_session=session, slug="round-trip", actor_user_id=None,
        )

        restored = project_service.unarchive_project(
            db_session=session, slug="round-trip", actor_user_id=None,
        )

        testbase.assert_equal(restored.state, ProjectState.ACTIVE)
        testbase.assert_equal(restored.archived_at, None)
        testbase.assert_equal(len(received), 1)
    finally:
        session.close()
    return


# =============================================================================
# Requirement 3 — Member add/remove with role binding
# =============================================================================


def test_add_member_inserts_binding_and_publishes_event():
    """
    **Feature: 2-projects M2 (Requirement 3.1)**
    **Property: add_member inserts a ProjectMemberBinding and publishes
    entity.project.member_added with the role name.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        received = []
        subscribe(
            topic=ProjectEventTopics.PROJECT_MEMBER_ADDED,
            subscriber=lambda evt: received.append(evt),
        )

        project_service.create_project(
            db_session=session,
            slug="membership",
            display_name="Members",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )
        user_id = new_uuid()

        binding = project_service.add_member(
            db_session=session,
            slug="membership",
            user_id=user_id,
            role_name=PROJECT_OWNER_ROLE,
            actor_user_id=None,
        )

        testbase.assert_equal(binding.role_name, PROJECT_OWNER_ROLE)
        testbase.assert_equal(len(received), 1)
        testbase.assert_equal(received[0].payload["role_name"], PROJECT_OWNER_ROLE)
    finally:
        session.close()
    return


def test_remove_last_owner_raises_last_admin_error_without_force():
    """
    **Feature: 2-projects M2 (Requirement 3.3)**
    **Property: Removing the only ProjectOwner binding raises
    LastAdminRemovalError unless force=True is passed.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        project_service.create_project(
            db_session=session,
            slug="last-admin",
            display_name="Last Admin",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )
        user_id = new_uuid()
        project_service.add_member(
            db_session=session,
            slug="last-admin",
            user_id=user_id,
            role_name=PROJECT_OWNER_ROLE,
            actor_user_id=None,
        )

        raised = False
        try:
            project_service.remove_member(
                db_session=session,
                slug="last-admin",
                user_id=user_id,
                role_name=PROJECT_OWNER_ROLE,
                actor_user_id=None,
                force=False,
            )
        except LastAdminRemovalError as xcpt:
            raised = True
            testbase.assert_equal("force=True" in str(xcpt), True)

        testbase.assert_equal(raised, True)
    finally:
        session.close()
    return


def test_force_true_allows_removing_last_owner():
    """
    **Feature: 2-projects M2 (Requirement 3.3 force override)**
    **Property: Passing force=True bypasses the last-admin safeguard
    and publishes entity.project.member_removed.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        received = []
        subscribe(
            topic=ProjectEventTopics.PROJECT_MEMBER_REMOVED,
            subscriber=lambda evt: received.append(evt),
        )

        project_service.create_project(
            db_session=session,
            slug="forced",
            display_name="Forced",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )
        user_id = new_uuid()
        project_service.add_member(
            db_session=session,
            slug="forced",
            user_id=user_id,
            role_name=PROJECT_OWNER_ROLE,
            actor_user_id=None,
        )

        project_service.remove_member(
            db_session=session,
            slug="forced",
            user_id=user_id,
            role_name=PROJECT_OWNER_ROLE,
            actor_user_id=None,
            force=True,
        )

        remaining = project_service.list_members(db_session=session, slug="forced")
        testbase.assert_equal(len(remaining), 0)
        testbase.assert_equal(len(received), 1)
    finally:
        session.close()
    return


def test_remove_member_missing_binding_raises_not_found():
    """
    **Feature: 2-projects M2 (Requirement 3.3 preconditions)**
    **Property: remove_member raises MemberBindingNotFoundError when
    no binding exists for the (user, role).**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        project_service.create_project(
            db_session=session,
            slug="nobinding",
            display_name="NB",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )

        raised = False
        try:
            project_service.remove_member(
                db_session=session,
                slug="nobinding",
                user_id=new_uuid(),
                role_name="project-viewer",
                actor_user_id=None,
            )
        except MemberBindingNotFoundError:
            raised = True

        testbase.assert_equal(raised, True)
    finally:
        session.close()
    return


# =============================================================================
# Requirement 4 — ProjectMetadataFieldExtension contributes typed fields
# =============================================================================


def test_patch_project_accepts_registered_extension_field():
    """
    **Feature: 2-projects M2 (Requirement 4.1–4.2)**
    **Property: A payload whose key matches a registered
    ProjectMetadataFieldExtension is persisted on the Project.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        project_service.create_project(
            db_session=session,
            slug="meta-ok",
            display_name="Meta",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )

        updated = project_service.patch_project(
            db_session=session,
            slug="meta-ok",
            display_name=None,
            description=None,
            extension_fields={"cost_center": "ENG-001"},
            actor_user_id=None,
        )

        testbase.assert_equal(
            updated.extension_fields.get("cost_center", None), "ENG-001",
        )
    finally:
        session.close()
    return


def test_patch_project_rejects_unknown_extension_field():
    """
    **Feature: 2-projects M2 (Requirement 4.2)**
    **Property: A payload containing a key not registered by any
    ProjectMetadataFieldExtension is rejected with
    MetadataFieldValidationError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        project_service.create_project(
            db_session=session,
            slug="meta-bad",
            display_name="BadMeta",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )

        raised = False
        try:
            project_service.patch_project(
                db_session=session,
                slug="meta-bad",
                display_name=None,
                description=None,
                extension_fields={"not_a_field": "x"},
                actor_user_id=None,
            )
        except MetadataFieldValidationError as xcpt:
            raised = True
            testbase.assert_equal("FIELD_NAME: not_a_field" in str(xcpt), True)

        testbase.assert_equal(raised, True)
    finally:
        session.close()
    return


def test_read_project_not_found_raises():
    """
    **Feature: 2-projects M1**
    **Property: read_project_by_slug raises ProjectNotFoundError
    when no row matches the canonical slug.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        raised = False
        try:
            project_service.read_project_by_slug(
                db_session=session, slug="ghost",
            )
        except ProjectNotFoundError:
            raised = True

        testbase.assert_equal(raised, True)
    finally:
        session.close()
    return


def test_cascade_user_deleted_removes_all_bindings():
    """
    **Feature: 2-projects M2 (T2.9)**
    **Property: cascade_user_deleted removes every
    ProjectMemberBinding for the given user.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        project_service.create_project(
            db_session=session,
            slug="cascade",
            display_name="Cascade",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )
        user_id = new_uuid()
        project_service.add_member(
            db_session=session,
            slug="cascade",
            user_id=user_id,
            role_name="project-editor",
            actor_user_id=None,
        )

        removed = project_service.cascade_user_deleted(
            db_session=session, user_id=user_id,
        )

        testbase.assert_equal(removed, 1)
        remaining = project_service.list_members(db_session=session, slug="cascade")
        testbase.assert_equal(len(remaining), 0)
    finally:
        session.close()
    return
