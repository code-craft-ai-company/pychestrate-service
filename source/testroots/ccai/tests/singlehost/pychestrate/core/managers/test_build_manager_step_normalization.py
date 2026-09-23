"""
.. module:: test_build_manager_step_normalization
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Build steps and pipeline stages always carry their optional
               fields

.. moduleauthor:: Code Craft AI LLC

The build-spec create form's own example steps omit
``continue_on_failure``. The spec was saved as typed, and the spec page
(rendered under ``StrictUndefined``) then failed with a bare 500 on the
missing key. The managers now fill the optional fields when a spec or
pipeline is saved and when one is read, so older rows are covered too.

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
    normalize_build_steps,
)
from ccai.pychestrate.core.managers.release_manager import (
    normalize_pipeline_stages,
)
from ccai.pychestrate.core.orm import (
    Project,
    ProjectBuildSpec,
    ProjectRepository,
    PychestrateModelBase,
)


#: The example the create form offers, verbatim: no continue_on_failure.
FORM_EXAMPLE_STEPS = [
    {"name": "checkout", "type": "checkout", "config": {}},
    {"name": "build", "type": "script", "config": {"script": "make build"}},
]


def _project_with_repository() -> Any:
    """
        An in-memory database with one project and one repository.

        :returns: Tuple of (session, ids).
    """
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


def test_normalize_build_steps_fills_the_optional_fields():
    """
    **Feature: projects (PRJ-02 build-spec page)**
    **Property: a step without ``config`` / ``continue_on_failure`` gets
    ``{}`` / ``False``.**
    """
    normalized = normalize_build_steps([{"name": "build", "type": "script"}])

    testbase.assert_equal(
        normalized,
        [{"name": "build", "type": "script", "config": {}, "continue_on_failure": False}],
    )
    return


def test_normalize_build_steps_keeps_values_that_were_given():
    """
    **Feature: projects (PRJ-02 build-spec page)**
    **Property: normalization never overrides a value the step already
    carries.**
    """
    step = {"name": "lint", "type": "script", "config": {"script": "make lint"}, "continue_on_failure": True}

    normalized = normalize_build_steps([dict(step)])

    testbase.assert_equal(normalized, [step])
    return


def test_create_spec_stores_the_form_example_with_every_field():
    """
    **Feature: projects (PRJ-02 build-spec page)**
    **Property: a spec created from the form's own example steps is read
    back with ``continue_on_failure`` present on every step.**
    """
    session, ids = _project_with_repository()
    manager = BuildManager(session)
    created = manager.create_spec(
        ids["project"],
        BuildSpecCreateRequest(name="nightly", repository_id=ids["repository"], steps=list(FORM_EXAMPLE_STEPS)),
        "u-1",
    )

    stored = session.query(ProjectBuildSpec).filter(ProjectBuildSpec.id == created.id).first()

    testbase.assert_equal(
        [step.get("continue_on_failure") for step in stored.steps_json], [False, False]
    )
    return


def test_get_spec_fills_optional_fields_on_rows_saved_without_them():
    """
    **Feature: projects (PRJ-02 build-spec page)**
    **Property: a spec row stored before normalization (steps lacking
    ``continue_on_failure``) is returned with the field filled in.**
    """
    session, ids = _project_with_repository()
    legacy = ProjectBuildSpec(
        project_id=ids["project"], repository_id=ids["repository"], name="legacy",
        branch="main", steps_json=list(FORM_EXAMPLE_STEPS), environment_json={},
        timeout_minutes=60, version=1,
    )
    session.add(legacy)
    session.commit()

    response = BuildManager(session).get_spec(legacy.id)

    testbase.assert_equal(
        [step["continue_on_failure"] for step in response.steps], [False, False]
    )
    return


def test_normalize_pipeline_stages_fills_the_optional_fields():
    """
    **Feature: projects (PRJ-02 pipeline page)**
    **Property: a pipeline stage without ``config`` /
    ``requires_approval`` / ``continue_on_failure`` gets ``{}`` /
    ``False`` / ``False`` -- the pipeline page reads all three.**
    """
    normalized = normalize_pipeline_stages([{"name": "build", "type": "build"}])

    testbase.assert_equal(
        normalized,
        [{
            "name": "build", "type": "build", "config": {},
            "requires_approval": False, "continue_on_failure": False,
        }],
    )
    return
