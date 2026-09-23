"""
.. module:: test_p26r_projects_build_specs_e2e_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: End-to-end tests for editing and deleting build
               specifications, and removing repositories (PRJ-18).

.. moduleauthor:: Code Craft AI LLC

Build specifications could be created but never edited or deleted, so a
repository they referenced could not be removed either, and the
repository's Remove confirmation claimed the specifications "will stop
working".
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Dict

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_app,
    ensure_seeded_admin,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
    get_page,
    open_db_session,
    post_form,
)


def _setup(*, with_build: bool = False) -> Dict[str, Any]:
    """
        A project with a repository and a build specification created
        through the forms (and, when asked, one finished build).
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id = create_project_via_ui(wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj18")
    repository = post_form(
        wsgi_app=handle.wsgi_app,
        path="/projects/{}/repositories/create".format(project_id),
        cookies=cookies,
        fields={
            "name": "app", "url": "https://git.example.invalid/app.git", "auth_type": "none",
            "credential_secret_ref": "", "default_branch": "main", "description": "",
        },
    )
    repository_id = int((repository.header("Location") or "").rstrip("/").split("/")[-1])
    spec = post_form(
        wsgi_app=handle.wsgi_app,
        path="/projects/{}/builds/specs/create".format(project_id),
        cookies=cookies,
        fields={
            "name": "nightly", "repository_id": str(repository_id), "branch": "main",
            "timeout_minutes": "60", "steps": "[]", "environment": "{}", "description": "",
        },
    )
    spec_id = int((spec.header("Location") or "").rstrip("/").split("/")[-1])
    if with_build is True:
        from ccai.pychestrate.core.orm import ProjectBuild  # noqa: E402
        db_session = open_db_session()
        try:
            db_session.add(ProjectBuild(
                project_id=project_id, spec_id=spec_id, spec_version=1, branch="main",
                commit_sha="abc1234", status="succeeded", trigger_type="manual",
                triggered_by_id=ensure_seeded_admin().user_id,
            ))
            db_session.commit()
        finally:
            db_session.close()
    rtnval = {
        "wsgi_app": handle.wsgi_app, "cookies": cookies, "project_id": project_id,
        "repository_id": repository_id, "spec_id": spec_id,
    }
    return rtnval


def _spec_row(spec_id: int) -> Any:
    from ccai.pychestrate.core.orm import ProjectBuildSpec  # noqa: E402

    db_session = open_db_session()
    try:
        spec = db_session.query(ProjectBuildSpec).filter(ProjectBuildSpec.id == spec_id).first()
        rtnval = None if spec is None else (spec.version, spec.branch, spec.steps_json)
    finally:
        db_session.close()
    return rtnval


def test_editing_a_build_specification_saves_the_next_version():
    """
    **Feature: projects (PRJ-18 build specification edit)**
    **Property: the edit form saves the changes as version 2 and says
    so.**
    """
    setup = _setup()
    steps = [{"name": "build", "type": "script", "config": {"script": "make"}}]
    response = post_form(
        wsgi_app=setup["wsgi_app"],
        path="/projects/{}/builds/specs/{}/edit".format(setup["project_id"], setup["spec_id"]),
        cookies=setup["cookies"],
        fields={
            "name": "nightly", "repository_id": str(setup["repository_id"]), "branch": "release",
            "timeout_minutes": "45", "steps": json.dumps(steps), "environment": "{}", "description": "",
        },
    )
    page = get_page(
        wsgi_app=setup["wsgi_app"], path=response.header("Location") or "/", cookies=setup["cookies"],
    ).text
    version, branch, stored_steps = _spec_row(setup["spec_id"])

    testbase.assert_equal(
        ("saved as version 2" in page, version, branch, [step["name"] for step in stored_steps]),
        (True, 2, "release", ["build"]),
    )
    return


def test_the_edit_form_shows_bad_json_as_an_error():
    """
    **Feature: projects (PRJ-18 build specification edit)**
    **Property: steps that are not JSON are refused with 400 and a
    message; the specification keeps version 1.**
    """
    setup = _setup()
    response = post_form(
        wsgi_app=setup["wsgi_app"],
        path="/projects/{}/builds/specs/{}/edit".format(setup["project_id"], setup["spec_id"]),
        cookies=setup["cookies"],
        fields={
            "name": "nightly", "repository_id": str(setup["repository_id"]), "branch": "main",
            "timeout_minutes": "60", "steps": "[not json", "environment": "{}", "description": "",
        },
    )

    testbase.assert_equal(
        (response.status_code, "Invalid JSON" in response.text, _spec_row(setup["spec_id"])[0]),
        (400, True, 1),
    )
    return


def test_deleting_a_build_specification_removes_it_with_its_builds():
    """
    **Feature: projects (PRJ-18 build specification delete)**
    **Property: Delete removes a specification that ran a build (with
    the build) and says how many builds went.**
    """
    setup = _setup(with_build=True)
    response = post_form(
        wsgi_app=setup["wsgi_app"],
        path="/projects/{}/builds/specs/{}/delete".format(setup["project_id"], setup["spec_id"]),
        cookies=setup["cookies"],
        fields={},
    )
    page = get_page(
        wsgi_app=setup["wsgi_app"], path=response.header("Location") or "/", cookies=setup["cookies"],
    ).text

    testbase.assert_equal(
        ("deleted with its 1 build" in page, _spec_row(setup["spec_id"])),
        (True, None),
    )
    return


def test_the_repository_page_explains_why_it_cannot_be_removed():
    """
    **Feature: projects (PRJ-18 repository removal)**
    **Property: while a build specification builds the repository, its
    page names the specification instead of offering Remove (whose copy
    claimed the specifications would "stop working").**
    """
    setup = _setup()
    page = get_page(
        wsgi_app=setup["wsgi_app"],
        path="/projects/{}/repositories/{}".format(setup["project_id"], setup["repository_id"]),
        cookies=setup["cookies"],
    ).text

    testbase.assert_equal(
        ("cannot be removed while build specifications build it: nightly" in page,
         "will stop working" in page,
         "/delete" in page.split("Last Commit")[0]),
        (True, False, False),
    )
    return


def test_a_repository_is_removed_once_its_specification_is_deleted():
    """
    **Feature: projects (PRJ-18 repository removal)**
    **Property: after its build specification is deleted, the
    repository can be removed.**
    """
    from ccai.pychestrate.core.orm import ProjectRepository  # noqa: E402

    setup = _setup(with_build=True)
    post_form(
        wsgi_app=setup["wsgi_app"],
        path="/projects/{}/builds/specs/{}/delete".format(setup["project_id"], setup["spec_id"]),
        cookies=setup["cookies"],
        fields={},
    )
    post_form(
        wsgi_app=setup["wsgi_app"],
        path="/projects/{}/repositories/{}/delete".format(setup["project_id"], setup["repository_id"]),
        cookies=setup["cookies"],
        fields={},
    )
    db_session = open_db_session()
    try:
        left = db_session.query(ProjectRepository).filter(
            ProjectRepository.id == setup["repository_id"]
        ).count()
    finally:
        db_session.close()

    testbase.assert_equal(left, 0)
    return
