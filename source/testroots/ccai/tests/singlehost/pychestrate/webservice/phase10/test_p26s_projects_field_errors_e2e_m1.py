"""
.. module:: test_p26s_projects_field_errors_e2e_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: End-to-end tests that the projects forms refuse invalid
               input with the error next to the field (PRJ-24).

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_app,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
    get_page,
    post_form,
)


def _setup() -> Dict[str, Any]:
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id = create_project_via_ui(wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj24")
    rtnval = {"wsgi_app": handle.wsgi_app, "cookies": cookies, "project_id": project_id}
    return rtnval


def _add_repository(setup: Dict[str, Any], *, url: str, default_branch: str = "main") -> Any:
    rtnval = post_form(
        wsgi_app=setup["wsgi_app"],
        path="/projects/{}/repositories/create".format(setup["project_id"]),
        cookies=setup["cookies"],
        fields={
            "name": "app", "url": url, "auth_type": "none", "credential_secret_ref": "",
            "default_branch": default_branch, "description": "",
        },
    )
    return rtnval


def test_a_garbage_repository_url_is_shown_next_to_the_url_field():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: adding a repository with the URL "just some words" is
    refused (400) with the error attached to the URL input (named in its
    aria-describedby after the field's hint, which says what to type).**
    """
    setup = _setup()
    response = _add_repository(setup, url="just some words")

    testbase.assert_equal(
        (response.status_code, 'id="url-error"' in response.text,
         'aria-describedby="url-help url-error"' in response.text),
        (400, True, True),
    )
    return


def test_a_bad_default_branch_is_shown_next_to_its_field():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: a default branch "my branch" is refused with the error
    next to the default branch input.**
    """
    setup = _setup()
    response = _add_repository(setup, url="https://git.example.invalid/app.git", default_branch="my branch")

    testbase.assert_equal(
        (response.status_code, 'id="default_branch-error"' in response.text), (400, True)
    )
    return


def test_a_build_of_a_bogus_commit_is_refused_with_the_reason():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: running a build of commit "not-a-sha!!" is refused and
    the page says why.**
    """
    setup = _setup()
    repository = _add_repository(setup, url="https://git.example.invalid/app.git")
    repository_id = int((repository.header("Location") or "").rstrip("/").split("/")[-1])
    spec = post_form(
        wsgi_app=setup["wsgi_app"],
        path="/projects/{}/builds/specs/create".format(setup["project_id"]),
        cookies=setup["cookies"],
        fields={
            "name": "nightly", "repository_id": str(repository_id), "branch": "main",
            "timeout_minutes": "60", "steps": "[]", "environment": "{}", "description": "",
        },
    )
    spec_id = int((spec.header("Location") or "").rstrip("/").split("/")[-1])
    response = post_form(
        wsgi_app=setup["wsgi_app"],
        path="/projects/{}/builds/trigger".format(setup["project_id"]),
        cookies=setup["cookies"],
        fields={"spec_id": str(spec_id), "branch": "main", "commit_sha": "not-a-sha!!"},
    )
    page = get_page(
        wsgi_app=setup["wsgi_app"], path=response.header("Location") or "/", cookies=setup["cookies"],
    ).text

    testbase.assert_equal("is not a commit SHA" in page, True)
    return


def test_an_invalid_version_pattern_is_shown_next_to_its_field():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: a release template with version pattern "([unclosed" is
    refused with the error next to the version pattern input.**
    """
    setup = _setup()
    response = post_form(
        wsgi_app=setup["wsgi_app"],
        path="/projects/{}/release-templates/create".format(setup["project_id"]),
        cookies=setup["cookies"],
        fields={
            "name": "standard", "description": "", "default_channel": "", "version_pattern": "([unclosed",
            "default_repo_ids": "", "default_pipeline": "", "default_schedule": "",
        },
    )

    testbase.assert_equal(
        (response.status_code, 'id="version_pattern-error"' in response.text,
         "not a valid regular expression" in response.text),
        (400, True, True),
    )
    return


def test_an_invalid_watch_pattern_is_shown_next_to_its_field():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: a watch whose branch pattern is "([unclosed" is refused
    with the error next to the branch pattern input.**
    """
    setup = _setup()
    repository = _add_repository(setup, url="https://git.example.invalid/app.git")
    repository_id = int((repository.header("Location") or "").rstrip("/").split("/")[-1])
    response = post_form(
        wsgi_app=setup["wsgi_app"],
        path="/projects/{}/watches/create".format(setup["project_id"]),
        cookies=setup["cookies"],
        fields={
            "name": "bad-pattern", "description": "", "event_type": "repository_commit",
            "repository_id": str(repository_id), "source_spec_id": "", "branch_pattern": "([unclosed",
            "tag_pattern": "", "build_status": "any", "action_type": "send_notification",
            "action_spec_id": "", "action_target_id": "", "enabled": "true",
        },
    )

    testbase.assert_equal(
        (response.status_code, 'id="branch_pattern-error"' in response.text), (400, True)
    )
    return
