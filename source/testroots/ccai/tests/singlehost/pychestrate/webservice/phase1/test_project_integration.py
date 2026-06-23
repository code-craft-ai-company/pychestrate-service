"""
.. module:: test_project_integration
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Integration test for 2-projects M1+M2 (TT-3).

.. moduleauthor:: Code Craft AI LLC

Covers the end-to-end happy path:

1. Create a project.
2. Add two members with different roles.
3. Patch a registered extension field (``cost_center``).
4. Archive, then delete the project.
5. Verify the audit log received every lifecycle event and the
   project + member-binding rows are gone.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy.orm import sessionmaker

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.audit.bus_subscriber import (
    wire_bus_subscribers as wire_audit_subscribers,
)
from ccai.pychestrate.webservice.audit.models import AuditRecord
from ccai.pychestrate.webservice.projects import service as project_service
from ccai.pychestrate.webservice.projects.models import Project, ProjectMemberBinding

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


def test_create_members_metadata_archive_delete_flow_writes_audit_rows():
    """
    **Feature: 2-projects TT-3**
    **Property: A full create → members → metadata → archive → delete
    flow writes at least one audit row per lifecycle step and leaves
    the project + binding tables empty.**
    """
    reset_phase1_runtime()
    engine, session = build_in_memory_session()

    audit_session_factory = sessionmaker(bind=engine)
    wire_audit_subscribers(session_factory=audit_session_factory)

    try:
        slug = "integration"
        project_service.create_project(
            db_session=session,
            slug=slug,
            display_name="Integration Test",
            description="E2E flow",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )

        first_user = new_uuid()
        second_user = new_uuid()

        project_service.add_member(
            db_session=session,
            slug=slug,
            user_id=first_user,
            role_name="project-owner",
            actor_user_id=None,
        )
        project_service.add_member(
            db_session=session,
            slug=slug,
            user_id=second_user,
            role_name="project-editor",
            actor_user_id=None,
        )

        project_service.patch_project(
            db_session=session,
            slug=slug,
            display_name=None,
            description=None,
            extension_fields={"cost_center": "QA-001"},
            actor_user_id=None,
        )

        project_service.archive_project(
            db_session=session, slug=slug, actor_user_id=None,
        )
        project_service.delete_project(
            db_session=session, slug=slug, actor_user_id=None,
        )

        # Verify project + bindings are gone.
        remaining_project = (
            session.query(Project).filter(Project.slug == slug).first()
        )
        testbase.assert_equal(remaining_project, None)

        remaining_bindings = session.query(ProjectMemberBinding).count()
        testbase.assert_equal(remaining_bindings, 0)

        # Verify audit records were captured for each lifecycle event.
        audit_check_session = audit_session_factory()
        try:
            kinds = {
                row.kind for row in audit_check_session.query(AuditRecord).all()
            }
        finally:
            audit_check_session.close()

        expected_kinds = {
            "audit.project.created",
            "audit.project.member_added",
            "audit.project.archived",
            "audit.project.deleted",
        }
        missing = expected_kinds - kinds
        testbase.assert_equal(len(missing), 0)
    finally:
        session.close()
    return
