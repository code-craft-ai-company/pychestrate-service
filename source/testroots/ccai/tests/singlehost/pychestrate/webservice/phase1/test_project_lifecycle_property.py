"""
.. module:: test_project_lifecycle_property
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Lifecycle invariant test for 2-projects (TT-2 Property 2).

.. moduleauthor:: Code Craft AI LLC

The real ``hypothesis.stateful`` tooling is not in the dependency set.
Instead, we drive a deterministic state machine over 64 scenarios that
cycle ``create → N random member add/remove ops → archive → delete``
and then assert that zero :class:`ProjectMemberBinding` rows remain for
the project id that was deleted. This implements the property from
``specs/2-projects/requirements.md`` Property 2 without the external
dependency.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.projects import service as project_service
from ccai.pychestrate.webservice.projects.exceptions import LastAdminRemovalError
from ccai.pychestrate.webservice.projects.models import (
    Project,
    ProjectMemberBinding,
)
from ccai.pychestrate.webservice.projects.service import PROJECT_OWNER_ROLE

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


_SCENARIOS: int = 64
_SEED: int = 20260424
_ROLES = (PROJECT_OWNER_ROLE, "project-editor", "project-viewer")
_OP_CHOICES = ("add", "remove")


def _run_scenario(*, session, rng: random.Random, scenario_ix: int) -> None:
    """
        Execute one create → ops → archive → delete cycle and assert
        zero member bindings remain afterwards.

        :param session: Active SQLAlchemy session.
        :param rng: Seeded PRNG for deterministic op selection.
        :param scenario_ix: Scenario index; used to build unique slugs.

        :returns: None.
    """
    slug = "lifecycle-{:04d}".format(scenario_ix)
    project_service.create_project(
        db_session=session,
        slug=slug,
        display_name="Lifecycle {}".format(scenario_ix),
        description="",
        owning_group_id=None,
        template_id=None,
        template_version=None,
        actor_user_id=None,
    )

    project = project_service.read_project_by_slug(db_session=session, slug=slug)
    project_id = str(project.project_id)

    op_count = rng.randint(0, 32)
    user_pool = [new_uuid() for _ in range(4)]

    for _ in range(op_count):
        op = rng.choice(_OP_CHOICES)
        user_id = rng.choice(user_pool)
        role = rng.choice(_ROLES)

        if op == "add":
            project_service.add_member(
                db_session=session,
                slug=slug,
                user_id=user_id,
                role_name=role,
                actor_user_id=None,
            )
        else:
            try:
                project_service.remove_member(
                    db_session=session,
                    slug=slug,
                    user_id=user_id,
                    role_name=role,
                    actor_user_id=None,
                    force=True,
                )
            except Exception:  # noqa: BLE001 — expected for missing bindings
                # remove against a non-existent binding raises
                # MemberBindingNotFoundError which is fine for the
                # lifecycle invariant; we only care about post-delete
                # emptiness.
                continue

    project_service.archive_project(
        db_session=session, slug=slug, actor_user_id=None,
    )
    project_service.delete_project(
        db_session=session, slug=slug, actor_user_id=None,
    )

    orphan_count = (
        session.query(ProjectMemberBinding)
        .filter(ProjectMemberBinding.project_id == project_id)
        .count()
    )
    testbase.assert_equal(orphan_count, 0)

    project_row = (
        session.query(Project).filter(Project.project_id == project_id).first()
    )
    testbase.assert_equal(project_row, None)
    return


def test_create_then_delete_leaves_no_orphans():
    """
    **Feature: 2-projects TT-2 (Property 2)**
    **Property: For every scenario of create → random add/remove →
    archive → delete, zero project member bindings remain for the
    deleted project id.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        rng = random.Random(_SEED)
        for ix in range(_SCENARIOS):
            _run_scenario(session=session, rng=rng, scenario_ix=ix)
    finally:
        session.close()
    return


def test_last_admin_safeguard_respected_without_force():
    """
    **Feature: 2-projects TT-2 (companion to Property 2)**
    **Property: Without force=True the single-owner removal is
    rejected, so the invariant that a project always has at least
    one owner holds while state=ACTIVE.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        slug = "safeguard"
        project_service.create_project(
            db_session=session,
            slug=slug,
            display_name="Safeguard",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )
        owner_user_id = new_uuid()
        project_service.add_member(
            db_session=session,
            slug=slug,
            user_id=owner_user_id,
            role_name=PROJECT_OWNER_ROLE,
            actor_user_id=None,
        )

        raised = False
        try:
            project_service.remove_member(
                db_session=session,
                slug=slug,
                user_id=owner_user_id,
                role_name=PROJECT_OWNER_ROLE,
                actor_user_id=None,
                force=False,
            )
        except LastAdminRemovalError:
            raised = True

        testbase.assert_equal(raised, True)
        remaining = project_service.list_members(db_session=session, slug=slug)
        testbase.assert_equal(len(remaining), 1)
    finally:
        session.close()
    return
