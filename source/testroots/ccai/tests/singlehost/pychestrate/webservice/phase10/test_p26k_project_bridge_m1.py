"""
.. module:: test_p26k_project_bridge_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: One owner for projects (PRJ-06): the web UI's projects and
               the project registry stay linked.

.. moduleauthor:: Code Craft AI LLC

Projects created in the web UI existed only in the legacy ``projects``
table, and projects created over REST only in the registry
(``projects_projects``), so neither side saw the other's. The registry
now owns project identity and :mod:`projects.bridge` keeps a linked
web-UI project for every registry project, and vice versa.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re
import uuid

from datetime import timedelta
from typing import Any, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from ccai import testbase

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.managers.project_manager import (
    ProjectCreateRequest,
    ProjectUpdateRequest,
)
from ccai.pychestrate.core.orm import (
    Project as LegacyProject,
    ProjectMember,
    PychestrateModelBase,
    User,
)
from ccai.pychestrate.webservice.messaging.event_bus import reset_for_testing as reset_event_bus
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base
from ccai.pychestrate.webservice.projects import bridge
from ccai.pychestrate.webservice.projects import service as project_service
from ccai.pychestrate.webservice.projects.legacy_identity import derived_project_uuid
from ccai.pychestrate.webservice.projects.models import Project, ProjectState
from ccai.pychestrate.webservice.webinterface.blueprints.config import routes_enrollment
from ccai.pychestrate.webservice.webinterface.blueprints.projects.project_access import (
    build_access_aware_project_manager,
)


def _session() -> Any:
    reset_event_bus()
    engine = sa.create_engine("sqlite://")
    PychestrateModelBase.metadata.create_all(engine)
    PychestratePhase1Base.metadata.create_all(engine)
    rtnval = sessionmaker(bind=engine)()
    return rtnval


def _user(session: Any, *, login: str, age_days: int = 0) -> str:
    user = User(
        id=uuid.uuid4(), first_name="First", last_name=login, email="{}@example.test".format(login),
        login=login, created_at=utc_now() - timedelta(days=age_days),
    )
    session.add(user)
    session.commit()
    rtnval = str(user.id)
    return rtnval


def _legacy(session: Any, *, name: str, owner: str) -> int:
    project = LegacyProject(name=name, description="about " + name, owner_id=uuid.UUID(owner), metadata_json={})
    session.add(project)
    session.commit()
    rtnval = int(project.id)
    return rtnval


def _registry(session: Any, *, slug: str, display_name: str) -> Project:
    project = Project(
        project_id=str(uuid.uuid4()), slug=slug, display_name=display_name, description="",
        state=ProjectState.ACTIVE, extension_fields={}, created_at=utc_now(), updated_at=utc_now(),
    )
    session.add(project)
    session.commit()
    rtnval = project
    return rtnval


def _registry_for_legacy(session: Any, legacy_id: int) -> Any:
    rtnval = session.query(Project).filter(Project.legacy_proj_id == legacy_id).first()
    return rtnval


def test_reconcile_links_same_named_projects_and_creates_missing_halves():
    """
    **Feature: project bridge (PRJ-06)**
    **Property: a UI project and a registry project of the same name are
    linked; a UI-only project gets a registry project under its derived
    UUID; a registry-only project gets a UI project owned by the earliest
    user; a second pass changes nothing.**
    """
    session = _session()
    owner = _user(session, login="first-admin", age_days=10)
    _user(session, login="later-user")
    orchestrate = _legacy(session, name="Orchestrate", owner=owner)
    my_app = _legacy(session, name="My App v2", owner=owner)
    registry_orchestrate = _registry(session, slug="orchestrate", display_name="Orchestrate")
    api_only = _registry(session, slug="api-only", display_name="API only")

    report = bridge.reconcile_project_links(db_session=session)
    second = bridge.reconcile_project_links(db_session=session)

    my_app_registry = _registry_for_legacy(session, my_app)
    api_only_legacy = session.query(LegacyProject).filter(LegacyProject.id == api_only.legacy_proj_id).first()
    api_only_owner_role = (
        session.query(ProjectMember.role)
        .filter(ProjectMember.project_id == api_only_legacy.id)
        .filter(ProjectMember.user_id == uuid.UUID(owner))
        .scalar()
    )
    testbase.assert_equal(
        (report.linked, report.registry_created, report.legacy_created, report.skipped),
        ([(orchestrate, "orchestrate")], [my_app], ["api-only"], []),
    )
    testbase.assert_equal(
        (str(_registry_for_legacy(session, orchestrate).project_id), str(my_app_registry.project_id),
         my_app_registry.slug, my_app_registry.display_name,
         api_only_legacy.name, str(api_only_legacy.owner_id), api_only_owner_role),
        (str(registry_orchestrate.project_id), derived_project_uuid(my_app), "my-app-v2", "My App v2",
         "api-only", owner, "owner"),
    )
    testbase.assert_equal(
        (second.linked, second.registry_created, second.legacy_created, second.skipped), ([], [], [], []),
    )
    return


def test_ui_create_update_delete_keeps_the_registry_project_in_step():
    """
    **Feature: project bridge (PRJ-06)**
    **Property: creating a project on the UI's manager creates its
    registry project (derived UUID, slug from the name); a rename and a
    new description reach the registry (the slug stays); deleting the UI
    project deletes the registry project.**
    """
    session = _session()
    owner = _user(session, login="ui-owner")
    manager = build_access_aware_project_manager(db_session=session)

    created = manager.create_project(ProjectCreateRequest(name="Lab_Tools", description="tools"), owner)
    registry = _registry_for_legacy(session, created.id)
    first = (str(registry.project_id), registry.slug, registry.display_name, registry.description)

    manager.update_project(created.id, ProjectUpdateRequest(name="Lab_Tools_2", description="more tools"), owner)
    session.expire_all()
    registry = _registry_for_legacy(session, created.id)
    renamed = (registry.slug, registry.display_name, registry.description)

    manager.delete_project(created.id, owner)
    session.expire_all()
    remaining = session.query(Project).filter(Project.project_id == first[0]).count()

    testbase.assert_equal(
        (first, renamed, remaining),
        ((derived_project_uuid(created.id), "lab-tools", "Lab_Tools", "tools"),
         ("lab-tools", "Lab_Tools_2", "more tools"), 0),
    )
    return


def test_rest_create_patch_delete_keeps_the_ui_project_in_step():
    """
    **Feature: project bridge (PRJ-06)**
    **Property: a project created through the registry service (REST /
    MCP) gets a UI project owned by its creator; a new description
    reaches it; deleting the registry project deletes it.**
    """
    session = _session()
    creator = _user(session, login="api-creator")
    project = project_service.create_project(
        db_session=session, slug="svc-proj", display_name="Service project", description="first",
        owning_group_id=None, template_id=None, template_version=None, actor_user_id=creator,
    )
    legacy_id = project.legacy_proj_id
    legacy = session.query(LegacyProject).filter(LegacyProject.id == legacy_id).first()
    created = (legacy.name, str(legacy.owner_id))

    project_service.patch_project(
        db_session=session, slug="svc-proj", display_name=None, description="second",
        extension_fields=None, actor_user_id=creator,
    )
    session.expire_all()
    described = session.query(LegacyProject.description).filter(LegacyProject.id == legacy_id).scalar()

    project_service.archive_project(db_session=session, slug="svc-proj", actor_user_id=creator)
    project_service.delete_project(db_session=session, slug="svc-proj", actor_user_id=creator)
    session.expire_all()
    remaining = session.query(LegacyProject).filter(LegacyProject.id == legacy_id).count()

    testbase.assert_equal(
        (created, described, remaining),
        (("svc-proj", creator), "second", 0),
    )
    return


def test_project_refs_resolve_to_the_registry_uuid():
    """
    **Feature: project bridge (PRJ-06)**
    **Property: a UI project id resolves to its linked registry UUID, an
    unlinked one to its derived UUID, and a UUID to itself.**
    """
    session = _session()
    owner = _user(session, login="ref-owner")
    linked = _legacy(session, name="linked", owner=owner)
    registry = _registry(session, slug="linked", display_name="linked")
    bridge.reconcile_project_links(db_session=session)
    unlinked_ref = "9999"

    testbase.assert_equal(
        (bridge.registry_project_uuid_for_ref(db_session=session, project_ref=str(linked)),
         bridge.registry_project_uuid_for_ref(db_session=session, project_ref=unlinked_ref),
         bridge.registry_project_uuid_for_ref(db_session=session, project_ref=str(registry.project_id).upper())),
        (str(registry.project_id), derived_project_uuid(unlinked_ref), str(registry.project_id)),
    )
    return


def test_enrollment_picker_lists_each_project_once_under_its_registry_uuid():
    """
    **Feature: project bridge (PRJ-06)**
    **Property: the enrollment token picker offers each project once, as
    its registry project (a linked UI project is not listed a second
    time under its derived UUID).**
    """
    session = _session()
    owner = _user(session, login="picker-owner")
    legacy_id = _legacy(session, name="Orchestrate", owner=owner)
    registry = _registry(session, slug="orchestrate", display_name="Orchestrate")
    bridge.reconcile_project_links(db_session=session)

    choices = routes_enrollment._list_project_choices(db_session=session)
    testbase.assert_equal(
        [(choice.label, choice.value) for choice in choices],
        [("Orchestrate", str(registry.project_id))],
    )
    testbase.assert_equal(_registry_for_legacy(session, legacy_id).slug, "orchestrate")
    return


def test_slug_for_legacy_name_always_yields_a_valid_slug():
    """
    **Feature: project bridge (PRJ-06)**
    **Property: any legacy name maps onto the registry slug pattern.**
    """
    pattern = r"^[a-z][a-z0-9-]{1,62}$"
    names = ["Orchestrate", "My App v2", "9lives", "--x--", "", "a", "x" * 200, "Über_Proj.1"]
    slugs = [bridge.slug_for_legacy_name(name=name, legacy_proj_id=7) for name in names]
    testbase.assert_equal(
        ([re.match(pattern, slug) is not None for slug in slugs], slugs[:4]),
        ([True] * len(names), ["orchestrate", "my-app-v2", "project-9lives", "project-7"]),
    )
    return
