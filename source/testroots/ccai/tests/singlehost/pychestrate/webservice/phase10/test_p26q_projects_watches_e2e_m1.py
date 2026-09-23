"""
.. module:: test_p26q_projects_watches_e2e_m1
    :platform: Darwin, Linux, Unix
    :synopsis: End-to-end tests for project watches in the consumer UI
               (PRJ-10).

.. moduleauthor:: Code Craft AI LLC

Watches never fired -- nothing called ``WatchManager.process_event`` --
and the watch page's Test button failed with a Python ``TypeError``.
These tests drive the real app: a repository served on 127.0.0.1
(:mod:`_git_http_server`), a watch created through the form, and the
repository's Fetch button finding a new commit.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from typing import Any, Dict

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_app,
    ensure_seeded_admin,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._git_http_server import (
    PrivateGitServer,
    isolated_git_config,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
    get_page,
    open_db_session,
    post_form,
)


def _add_specs(*, project_id: int, repository_id: int) -> Dict[str, int]:
    """
        A build specification building the repository and a test
        specification, straight into the database.
    """
    from ccai.pychestrate.core.orm import ProjectBuildSpec, ProjectTestSpec  # noqa: E402

    db_session = open_db_session()
    try:
        build_spec = ProjectBuildSpec(
            project_id=project_id, repository_id=repository_id, name="nightly", branch="main",
        )
        test_spec = ProjectTestSpec(
            project_id=project_id, name="smoke", framework="pytest", test_command="pytest",
        )
        db_session.add(build_spec)
        db_session.add(test_spec)
        db_session.commit()
        rtnval = {"build_spec": build_spec.id, "test_spec": test_spec.id}
    finally:
        db_session.close()
    return rtnval


def _setup(*, server: PrivateGitServer) -> Dict[str, Any]:
    """
        A project with the served repository, a build and a test
        specification, and a watch that builds new commits on main.
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id = create_project_via_ui(wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj10")
    created = post_form(
        wsgi_app=handle.wsgi_app,
        path="/projects/{}/repositories/create".format(project_id),
        cookies=cookies,
        fields={
            "name": "app", "url": server.url, "auth_type": "none", "credential_secret_ref": "",
            "default_branch": "main", "description": "",
        },
    )
    repository_id = int((created.header("Location") or "").rstrip("/").split("/")[-1])
    specs = _add_specs(project_id=project_id, repository_id=repository_id)
    watch = post_form(
        wsgi_app=handle.wsgi_app,
        path="/projects/{}/watches/create".format(project_id),
        cookies=cookies,
        fields={
            "name": "build-main-{}".format(uuid.uuid4().hex[:6]),
            "description": "",
            "event_type": "repository_commit",
            "repository_id": str(repository_id),
            "source_spec_id": "",
            "branch_pattern": "^main$",
            "tag_pattern": "",
            "build_status": "any",
            "action_type": "trigger_build",
            "action_spec_id": str(specs["build_spec"]),
            "action_target_id": "",
            "enabled": "true",
        },
    )
    watch_id = int((watch.header("Location") or "").rstrip("/").split("/")[-1])
    rtnval = {
        "wsgi_app": handle.wsgi_app,
        "cookies": cookies,
        "project_id": project_id,
        "repository_id": repository_id,
        "watch_id": watch_id,
        "specs": specs,
    }
    return rtnval


def _fetch(*, setup: Dict[str, Any]) -> str:
    """
        Press Fetch on the repository page and return the page it
        redirects to (with the flash).
    """
    response = post_form(
        wsgi_app=setup["wsgi_app"],
        path="/projects/{}/repositories/{}/fetch".format(setup["project_id"], setup["repository_id"]),
        cookies=setup["cookies"],
        fields={},
    )
    page = get_page(
        wsgi_app=setup["wsgi_app"], path=response.header("Location") or "/", cookies=setup["cookies"],
    )
    return page.text


def test_fetch_reports_the_new_commits_and_the_watch_it_started():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: the first Fetch records the branches; after a push to
    main, Fetch says it found new commits on main and started 1 watch.**
    """
    server = PrivateGitServer(require_auth=False)
    try:
        with isolated_git_config():
            setup = _setup(server=server)
            first = _fetch(setup=setup)
            server.commit(branch="main", message="Second")
            second = _fetch(setup=setup)
    finally:
        server.close()

    testbase.assert_equal(
        (
            "branches and tags are recorded now" in first,
            "new commits on main" in second,
            "1 watch triggered" in second,
        ),
        (True, True, True),
    )
    return


def test_the_watch_builds_the_new_commit_as_the_signed_in_user():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: the watch started by a Fetch creates a build of the new
    commit on main, triggered by the watch on behalf of the user who
    fetched.**
    """
    from ccai.pychestrate.core.orm import ProjectBuild  # noqa: E402

    server = PrivateGitServer(require_auth=False)
    try:
        with isolated_git_config():
            setup = _setup(server=server)
            _fetch(setup=setup)
            new_sha = server.commit(branch="main", message="Second")
            _fetch(setup=setup)
        db_session = open_db_session()
        try:
            builds = [
                (build.branch, build.commit_sha, build.trigger_type, str(build.triggered_by_id))
                for build in db_session.query(ProjectBuild).filter(
                    ProjectBuild.project_id == setup["project_id"]
                ).all()
            ]
        finally:
            db_session.close()
    finally:
        server.close()

    testbase.assert_equal(builds, [("main", new_sha, "watch", ensure_seeded_admin().user_id)])
    return


def test_the_watch_page_lists_the_trigger_in_plain_words():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: after the watch fires, its page lists the trigger as
    "New commits on main" and the action it ran as "Run a build".**
    """
    server = PrivateGitServer(require_auth=False)
    try:
        with isolated_git_config():
            setup = _setup(server=server)
            _fetch(setup=setup)
            server.commit(branch="main", message="Second")
            _fetch(setup=setup)
        page = get_page(
            wsgi_app=setup["wsgi_app"],
            path="/projects/{}/watches/{}".format(setup["project_id"], setup["watch_id"]),
            cookies=setup["cookies"],
        ).text
    finally:
        server.close()

    testbase.assert_equal(
        ("New commits on main" in page, "Run a build: #" in page, "repository_commit" in page),
        (True, True, False),
    )
    return


def test_the_watch_test_shows_each_conditions_result():
    """
    **Feature: projects (PRJ-10 watch test)**
    **Property: testing the watch with branch dev shows that the branch
    condition does not match and that the watch would not run -- and
    starts nothing (it used to fail with a TypeError).**
    """
    from ccai.pychestrate.core.orm import ProjectBuild  # noqa: E402

    server = PrivateGitServer(require_auth=False)
    try:
        with isolated_git_config():
            setup = _setup(server=server)
        response = post_form(
            wsgi_app=setup["wsgi_app"],
            path="/projects/{}/watches/{}/test".format(setup["project_id"], setup["watch_id"]),
            cookies=setup["cookies"],
            fields={"sample_branch": "dev"},
        )
        db_session = open_db_session()
        try:
            builds = db_session.query(ProjectBuild).filter(
                ProjectBuild.project_id == setup["project_id"]
            ).count()
        finally:
            db_session.close()
    finally:
        server.close()

    testbase.assert_equal(
        (response.status_code, "does not match" in response.text, "Would not run" in response.text, builds),
        (200, True, True, 0),
    )
    return


def test_the_watch_form_offers_plain_language_choices():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: the create form names triggers and actions in plain
    words ("A build finishes", "Run a test job") instead of enum values.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id = create_project_via_ui(wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj10-form")

    page = get_page(
        wsgi_app=handle.wsgi_app, path="/projects/{}/watches/create".format(project_id), cookies=cookies,
    ).text

    testbase.assert_equal(
        (">A build finishes</option>" in page, ">Run a test job</option>" in page,
         ">build_completion<" in page, ">trigger_test_job<" in page),
        (True, True, False, False),
    )
    return


def test_a_build_completion_watch_watches_a_build_specification():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: creating a watch for "A build finishes" stores the chosen
    build specification as its source and the chosen build result as its
    condition (the form used to send a repository id for every trigger).**
    """
    from ccai.pychestrate.core.orm import ProjectWatch  # noqa: E402

    server = PrivateGitServer(require_auth=False)
    try:
        with isolated_git_config():
            setup = _setup(server=server)
    finally:
        server.close()
    response = post_form(
        wsgi_app=setup["wsgi_app"],
        path="/projects/{}/watches/create".format(setup["project_id"]),
        cookies=setup["cookies"],
        fields={
            "name": "test-failed-builds",
            "description": "",
            "event_type": "build_completion",
            "repository_id": "",
            "source_spec_id": str(setup["specs"]["build_spec"]),
            "branch_pattern": "",
            "tag_pattern": "",
            "build_status": "failed",
            "action_type": "trigger_test_job",
            "action_spec_id": "",
            "action_target_id": str(setup["specs"]["test_spec"]),
            "enabled": "true",
        },
    )
    watch_id = int((response.header("Location") or "0").rstrip("/").split("/")[-1])
    db_session = open_db_session()
    try:
        watch = db_session.query(ProjectWatch).filter(ProjectWatch.id == watch_id).one()
        stored = (watch.trigger_source, watch.source_id, watch.repository_id, watch.conditions_json.get("build_status"))
    finally:
        db_session.close()

    testbase.assert_equal(
        stored, ("build_completion", setup["specs"]["build_spec"], None, "failed")
    )
    return
