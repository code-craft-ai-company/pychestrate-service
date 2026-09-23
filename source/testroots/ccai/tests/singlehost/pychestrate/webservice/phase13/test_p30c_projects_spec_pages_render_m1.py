"""
.. module:: test_p30c_projects_spec_pages_render_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Render the build-spec and pipeline pages under
               StrictUndefined with data produced by the real managers.

.. moduleauthor:: Code Craft AI LLC

The render-smoke suite (p30a) feeds hand-written fixtures whose build
steps carry every key, so it never saw the shape the create form's own
example produces (no ``continue_on_failure``). That shape made the spec
page fail with a bare 500. These tests build the spec and the pipeline
through :class:`BuildManager` / :class:`ReleaseManager` from minimal,
user-typed definitions and render the real templates.

**Feature: projects (PRJ-02 build-spec page)**
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

from ccai.pychestrate.core.managers.build_manager import (
    BuildManager,
    BuildSpecCreateRequest,
)
from ccai.pychestrate.core.managers.release_manager import (
    ReleaseManager,
    ReleasePipelineCreateRequest,
)
from ccai.pychestrate.core.orm import (
    Project,
    ProjectRepository,
    PychestrateModelBase,
)
from ccai.testshared.factories.webui.dataclass_fixtures import MODE_POPULATED
from ccai.testshared.factories.webui.template_contexts import (
    build_template_context,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    strict_environment,
    undeclared_variables,
)


def _session_with_repository() -> Any:
    engine = sa.create_engine("sqlite://")
    PychestrateModelBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    project = Project(name="alpha", owner_id=uuid.uuid4(), metadata_json={})
    session.add(project)
    session.flush()
    repository = ProjectRepository(
        project_id=project.id, name="repo", url="https://example.com/repo.git",
        auth_type="none", default_branch="main",
    )
    session.add(repository)
    session.commit()
    ids: Dict[str, int] = {"project": project.id, "repository": repository.id}
    rtnval = (session, ids)
    return rtnval


def _render(*, template_name: str, overrides: Dict[str, Any]) -> str:
    env = strict_environment()
    context = build_template_context(
        template_name=template_name,
        variable_names=undeclared_variables(template_name=template_name),
        mode=MODE_POPULATED,
    )
    context.update(overrides)
    rtnval = env.get_template(template_name).render(context)
    return rtnval


def test_build_spec_page_renders_a_spec_created_from_the_form_example():
    """
    **Feature: projects (PRJ-02 build-spec page)**
    **Property: projects/builds/spec_detail.html renders under
    StrictUndefined for a spec created through BuildManager from the
    create form's example steps (which omit continue_on_failure), and
    shows both steps.**
    """
    session, ids = _session_with_repository()
    manager = BuildManager(session)
    created = manager.create_spec(
        ids["project"],
        BuildSpecCreateRequest(
            name="nightly",
            repository_id=ids["repository"],
            steps=[
                {"name": "checkout", "type": "checkout", "config": {}},
                {"name": "compile", "type": "script", "config": {"script": "make build"}},
            ],
        ),
        "u-1",
    )

    html = _render(
        template_name="projects/builds/spec_detail.html",
        overrides={"spec": manager.get_spec(created.id)},
    )

    testbase.assert_equal(("checkout" in html, "compile" in html), (True, True))
    return


def test_pipeline_page_renders_stages_typed_without_optional_fields():
    """
    **Feature: projects (PRJ-02 pipeline page)**
    **Property: projects/releases/pipeline_detail.html renders under
    StrictUndefined for a pipeline whose stages were saved without
    requires_approval / continue_on_failure.**
    """
    session, ids = _session_with_repository()
    manager = ReleaseManager(session)
    created = manager.create_pipeline(
        ids["project"],
        ReleasePipelineCreateRequest(
            name="ship",
            stages=[{"name": "package-it", "type": "package"}],
            triggers=["manual"],
        ),
        "u-1",
    )

    html = _render(
        template_name="projects/releases/pipeline_detail.html",
        overrides={"pipeline": manager.get_pipeline(created.id)},
    )

    testbase.assert_equal("package-it" in html, True)
    return
