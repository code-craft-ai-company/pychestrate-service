"""
.. module:: test_p23a_project_bridge_resolver_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Unit tests for the Project-model bridge resolver
               (PR-1 of specs/project-model-bridge.md).

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.projects import repository as projects_repo
from ccai.pychestrate.webservice.projects.models import Project, ProjectState

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


def _make_project(
        *,
        session,
        slug: str,
        legacy_proj_id=None
    ) -> Project:
    """
        Helper: insert a slug-Project with an optional legacy bridge
        id and return it.
    """
    project = Project(
        project_id=new_uuid(),
        slug=slug,
        display_name=slug,
        description="",
        state=ProjectState.ACTIVE,
        legacy_proj_id=legacy_proj_id,
    )
    session.add(project)
    session.flush()
    rtnval = project
    return rtnval


def test_resolve_by_slug_returns_row():
    """
    **Feature: project-model bridge (PR-1)**
    **Property: resolve_project(slug=...) returns the matching row.**
    """
    _engine, session = build_in_memory_session()
    created = _make_project(session=session, slug="alpha", legacy_proj_id=7)

    resolved = projects_repo.resolve_project(
        db_session=session, slug="alpha"
    )
    testbase.assert_true(resolved is not None)
    testbase.assert_equal(str(resolved.project_id), str(created.project_id))
    testbase.assert_equal(resolved.legacy_proj_id, 7)
    return


def test_resolve_by_uuid_returns_row():
    """
    **Feature: project-model bridge (PR-1)**
    **Property: resolve_project(uuid=...) returns the matching row.**
    """
    _engine, session = build_in_memory_session()
    created = _make_project(session=session, slug="beta", legacy_proj_id=11)

    resolved = projects_repo.resolve_project(
        db_session=session, uuid=str(created.project_id)
    )
    testbase.assert_true(resolved is not None)
    testbase.assert_equal(resolved.slug, "beta")
    return


def test_resolve_by_legacy_id_returns_row():
    """
    **Feature: project-model bridge (PR-1)**
    **Property: resolve_project(legacy_id=...) returns the bridged row.**
    """
    _engine, session = build_in_memory_session()
    _make_project(session=session, slug="gamma", legacy_proj_id=42)

    resolved = projects_repo.resolve_project(
        db_session=session, legacy_id=42
    )
    testbase.assert_true(resolved is not None)
    testbase.assert_equal(resolved.slug, "gamma")
    return


def test_resolve_requires_exactly_one_identity():
    """
    **Feature: project-model bridge (PR-1)**
    **Property: passing zero or multiple identity forms raises ValueError.**
    """
    _engine, session = build_in_memory_session()

    raised_none = False
    try:
        projects_repo.resolve_project(db_session=session)
    except ValueError:
        raised_none = True
    testbase.assert_true(raised_none)

    raised_multi = False
    try:
        projects_repo.resolve_project(
            db_session=session, slug="x", legacy_id=1
        )
    except ValueError:
        raised_multi = True
    testbase.assert_true(raised_multi)
    return


def test_resolve_project_ref_sniffs_uuid():
    """
    **Feature: project-model bridge (PR-1)**
    **Property: resolve_project_ref routes a UUID token to the uuid lookup.**
    """
    _engine, session = build_in_memory_session()
    created = _make_project(session=session, slug="delta", legacy_proj_id=3)

    resolved = projects_repo.resolve_project_ref(
        db_session=session, ref=str(created.project_id)
    )
    testbase.assert_true(resolved is not None)
    testbase.assert_equal(resolved.slug, "delta")
    return


def test_resolve_project_ref_sniffs_int():
    """
    **Feature: project-model bridge (PR-1)**
    **Property: an all-digits ref routes to the legacy-id lookup.**
    """
    _engine, session = build_in_memory_session()
    _make_project(session=session, slug="epsilon", legacy_proj_id=99)

    resolved = projects_repo.resolve_project_ref(
        db_session=session, ref="99"
    )
    testbase.assert_true(resolved is not None)
    testbase.assert_equal(resolved.slug, "epsilon")
    return


def test_resolve_project_ref_falls_back_to_slug():
    """
    **Feature: project-model bridge (PR-1)**
    **Property: a non-uuid non-numeric ref routes to the slug lookup.**
    """
    _engine, session = build_in_memory_session()
    _make_project(session=session, slug="zeta-project", legacy_proj_id=None)

    resolved = projects_repo.resolve_project_ref(
        db_session=session, ref="zeta-project"
    )
    testbase.assert_true(resolved is not None)
    testbase.assert_equal(resolved.slug, "zeta-project")
    return


def test_resolve_legacy_proj_id_returns_bridged_int():
    """
    **Feature: project-model bridge (PR-1)**
    **Property: resolve_legacy_proj_id returns the bridged legacy id.**
    """
    _engine, session = build_in_memory_session()
    _make_project(session=session, slug="eta", legacy_proj_id=55)

    legacy_id = projects_repo.resolve_legacy_proj_id(
        db_session=session, ref="eta"
    )
    testbase.assert_equal(legacy_id, 55)
    return


def test_resolve_legacy_proj_id_none_when_unbridged():
    """
    **Feature: project-model bridge (PR-1)**
    **Property: a slug-Project with no legacy counterpart yields None.**
    """
    _engine, session = build_in_memory_session()
    _make_project(session=session, slug="theta", legacy_proj_id=None)

    legacy_id = projects_repo.resolve_legacy_proj_id(
        db_session=session, ref="theta"
    )
    testbase.assert_true(legacy_id is None)
    return


def test_resolve_unknown_ref_returns_none():
    """
    **Feature: project-model bridge (PR-1)**
    **Property: an unresolvable reference returns None, not an error.**
    """
    _engine, session = build_in_memory_session()

    resolved = projects_repo.resolve_project_ref(
        db_session=session, ref="does-not-exist"
    )
    testbase.assert_true(resolved is None)
    return
