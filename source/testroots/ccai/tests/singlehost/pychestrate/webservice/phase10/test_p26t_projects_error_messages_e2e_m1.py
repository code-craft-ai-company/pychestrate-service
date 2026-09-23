"""
.. module:: test_p26t_projects_error_messages_e2e_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: End-to-end tests that the projects pages never show raw
               exception text (PRJ-29).

.. moduleauthor:: Code Craft AI LLC

The projects handlers flashed ``str(exc)`` for any failure, so SQL
errors, Python ``TypeError`` text and git output reached users. Each
test here makes one manager call fail with an internal error whose text
must stay in the server log, and checks that the page shows a reference
an administrator can look up instead.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from contextlib import contextmanager
from typing import Any, Dict, Iterator

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.webinterface.blueprints.projects import (
    routes as projects_routes,
    routes_builds,
    routes_release_templates,
    routes_repositories,
    routes_watches,
)
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


#: Internal error text that must never reach a page.
_INTERNAL = 'psycopg2.errors.UndefinedTable: relation "secret_table" does not exist'


class _Exploding:
    """
        A manager whose ``method`` fails with an internal error; every
        other attribute is the real manager's.
    """

    def __init__(self, real: Any, method: str) -> None:
        self._real = real
        self._method = method
        return

    def __getattr__(self, name: str) -> Any:
        if name == self._method:
            def _boom(*args: Any, **kwargs: Any) -> Any:
                raise RuntimeError(_INTERNAL)
            return _boom
        return getattr(self._real, name)


@contextmanager
def _exploding(module: Any, seam: str, method: str) -> Iterator[None]:
    """
        While the block runs, managers built through ``module.seam``
        fail in ``method``.
    """
    original = getattr(module, seam)
    patch = create_module_patch(module, seam)
    mock = patch.activate()

    def _builder(**kwargs: Any) -> Any:
        return _Exploding(original(**kwargs), method)

    mock.configure(side_effect=_builder)
    try:
        yield
    finally:
        patch.deactivate()
    return


def _setup() -> Dict[str, Any]:
    from ccai.pychestrate.core.orm import (  # noqa: E402
        ProjectBuild, ProjectBuildSpec, ProjectRepository, ProjectWatch,
    )

    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id = create_project_via_ui(wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj29")
    db_session = open_db_session()
    try:
        repository = ProjectRepository(
            project_id=project_id, name="app", url="https://git.example.invalid/app.git",
            auth_type="none", default_branch="main",
        )
        spare = ProjectRepository(
            project_id=project_id, name="spare", url="https://git.example.invalid/spare.git",
            auth_type="none", default_branch="main",
        )
        db_session.add(repository)
        db_session.add(spare)
        db_session.flush()
        spec = ProjectBuildSpec(project_id=project_id, repository_id=repository.id, name="nightly")
        db_session.add(spec)
        db_session.flush()
        build = ProjectBuild(
            project_id=project_id, spec_id=spec.id, spec_version=1, branch="main", commit_sha="abc1234",
            status="pending", trigger_type="manual", triggered_by_id=ensure_seeded_admin().user_id,
        )
        watch = ProjectWatch(
            project_id=project_id, name="build-on-push", trigger_source="repository_commit",
            source_id=repository.id, repository_id=repository.id, conditions_json={},
            actions_json=[{"action": "trigger_build", "target_id": spec.id, "parameters": {}}],
            enabled=True, trigger_count=0,
        )
        db_session.add(build)
        db_session.add(watch)
        db_session.commit()
        rtnval = {
            "wsgi_app": handle.wsgi_app, "cookies": cookies, "project_id": project_id,
            "spec_id": spec.id, "build_id": build.id, "watch_id": watch.id, "spare_id": spare.id,
        }
    finally:
        db_session.close()
    return rtnval


def _page_after(setup: Dict[str, Any], response: Any) -> str:
    """
        The page the user sees after a POST: the redirect target, or the
        re-rendered form.
    """
    location = response.header("Location")
    if location:
        rtnval = get_page(wsgi_app=setup["wsgi_app"], path=location, cookies=setup["cookies"]).text
    else:
        rtnval = response.text
    return rtnval


def _hides_internal_error(page: str) -> Any:
    rtnval = (_INTERNAL in page, "secret_table" in page, "reference:" in page)
    return rtnval


def test_creating_a_project_hides_an_internal_error():
    """
    **Feature: projects (PRJ-29 error messages)**
    **Property: when creating a project fails internally, the form shows
    a log reference and not the error text.**
    """
    setup = _setup()
    with _exploding(projects_routes, "_build_project_manager", "create_project"):
        response = post_form(
            wsgi_app=setup["wsgi_app"], path="/projects/create", cookies=setup["cookies"],
            fields={"name": "prj29-" + uuid.uuid4().hex[:6], "description": "", "metadata": ""},
        )

    testbase.assert_equal(_hides_internal_error(_page_after(setup, response)), (False, False, True))
    return


def test_adding_a_member_hides_an_internal_error():
    """
    **Feature: projects (PRJ-29 error messages)**
    **Property: when adding a member fails internally, the page shows a
    log reference and not the error text.**
    """
    setup = _setup()
    with _exploding(projects_routes, "_build_project_manager", "add_member"):
        response = post_form(
            wsgi_app=setup["wsgi_app"], path="/projects/{}/members/add".format(setup["project_id"]),
            cookies=setup["cookies"],
            fields={"user_id": ensure_seeded_admin().user_id, "role": "viewer"},
        )

    testbase.assert_equal(_hides_internal_error(_page_after(setup, response)), (False, False, True))
    return


def test_choosing_no_member_is_still_explained():
    """
    **Feature: projects (PRJ-29 error messages)**
    **Property: a problem with the form itself keeps its message ("Choose
    a user to add to the project.") and gets no reference.**
    """
    setup = _setup()
    response = post_form(
        wsgi_app=setup["wsgi_app"], path="/projects/{}/members/add".format(setup["project_id"]),
        cookies=setup["cookies"], fields={"user_id": "", "role": "viewer"},
    )
    page = _page_after(setup, response)

    testbase.assert_equal(
        ("Choose a user to add to the project." in page, "reference:" in page), (True, False)
    )
    return


def test_running_a_build_hides_an_internal_error():
    """
    **Feature: projects (PRJ-29 error messages)**
    **Property: when triggering a build fails internally, the page shows
    a log reference and not the error text.**
    """
    setup = _setup()
    with _exploding(routes_builds, "_build_build_manager", "trigger_build"):
        response = post_form(
            wsgi_app=setup["wsgi_app"], path="/projects/{}/builds/trigger".format(setup["project_id"]),
            cookies=setup["cookies"], fields={"spec_id": str(setup["spec_id"]), "branch": "main", "commit_sha": ""},
        )

    testbase.assert_equal(_hides_internal_error(_page_after(setup, response)), (False, False, True))
    return


def test_cancelling_a_build_hides_an_internal_error():
    """
    **Feature: projects (PRJ-29 error messages)**
    **Property: when cancelling a build fails internally, the page shows
    a log reference and not the error text.**
    """
    setup = _setup()
    with _exploding(routes_builds, "_build_build_manager", "cancel_build"):
        response = post_form(
            wsgi_app=setup["wsgi_app"],
            path="/projects/{}/builds/{}/cancel".format(setup["project_id"], setup["build_id"]),
            cookies=setup["cookies"], fields={},
        )

    testbase.assert_equal(_hides_internal_error(_page_after(setup, response)), (False, False, True))
    return


def test_creating_a_watch_hides_an_internal_error():
    """
    **Feature: projects (PRJ-29 error messages)**
    **Property: when creating a watch fails internally, the form shows a
    log reference and not the error text.**
    """
    setup = _setup()
    with _exploding(routes_watches, "_build_watch_manager", "create_watch"):
        response = post_form(
            wsgi_app=setup["wsgi_app"], path="/projects/{}/watches/create".format(setup["project_id"]),
            cookies=setup["cookies"],
            fields={
                "name": "another", "description": "", "event_type": "repository_commit",
                "repository_id": str(setup["spare_id"]), "source_spec_id": "", "branch_pattern": "",
                "tag_pattern": "", "build_status": "any", "action_type": "send_notification",
                "action_spec_id": "", "action_target_id": "", "enabled": "true",
            },
        )

    testbase.assert_equal(_hides_internal_error(_page_after(setup, response)), (False, False, True))
    return


def test_deleting_a_watch_hides_an_internal_error():
    """
    **Feature: projects (PRJ-29 error messages)**
    **Property: when deleting a watch fails internally, the page shows a
    log reference and not the error text.**
    """
    setup = _setup()
    with _exploding(routes_watches, "_build_watch_manager", "delete_watch"):
        response = post_form(
            wsgi_app=setup["wsgi_app"],
            path="/projects/{}/watches/{}/delete".format(setup["project_id"], setup["watch_id"]),
            cookies=setup["cookies"], fields={},
        )

    testbase.assert_equal(_hides_internal_error(_page_after(setup, response)), (False, False, True))
    return


def test_creating_a_release_template_hides_an_internal_error():
    """
    **Feature: projects (PRJ-29 error messages)**
    **Property: when creating a release template fails internally, the
    form shows a log reference and not the error text.**
    """
    setup = _setup()
    with _exploding(routes_release_templates, "_build_template_manager", "create"):
        response = post_form(
            wsgi_app=setup["wsgi_app"],
            path="/projects/{}/release-templates/create".format(setup["project_id"]),
            cookies=setup["cookies"],
            fields={
                "name": "standard", "description": "", "default_channel": "", "version_pattern": "",
                "default_repo_ids": "", "default_pipeline": "", "default_schedule": "",
            },
        )

    testbase.assert_equal(_hides_internal_error(_page_after(setup, response)), (False, False, True))
    return


def test_removing_a_repository_hides_an_internal_error():
    """
    **Feature: projects (PRJ-29 error messages)**
    **Property: when removing a repository fails internally, the page
    shows a log reference and not the error text.**
    """
    setup = _setup()
    with _exploding(routes_repositories, "_build_repository_manager", "remove_repository"):
        response = post_form(
            wsgi_app=setup["wsgi_app"],
            path="/projects/{}/repositories/{}/delete".format(setup["project_id"], setup["spare_id"]),
            cookies=setup["cookies"], fields={},
        )

    testbase.assert_equal(_hides_internal_error(_page_after(setup, response)), (False, False, True))
    return
