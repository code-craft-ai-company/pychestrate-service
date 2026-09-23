"""
.. module:: test_project_input_validation
    :platform: Darwin, Linux, Unix
    :synopsis: Tests that project inputs are validated when saved:
               branch names, commit SHAs, repository URLs, regular
               expressions and repository ids.

.. moduleauthor:: Code Craft AI LLC

The projects pages accepted "not-a-sha!!" as a commit, "([unclosed" as a
version pattern, any text as a repository URL and repository ids that
do not exist, and a fetch reported "updated" for a default branch the
repository does not have. Each error now names the field it concerns,
so the pages can show it next to the input.

**Feature: projects (PRJ-24 input validation)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import shutil
import subprocess
import tempfile
import uuid

from typing import Any, Dict

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from ccai import testbase

from ccai.pychestrate.core.managers.build_manager import (
    BuildManager,
    BuildSpecCreateRequest,
    BuildSpecValidationError,
    BuildTriggerRequest,
    BuildValidationError,
)
from ccai.pychestrate.core.managers.git_validation import (
    commit_sha_problem,
    ref_name_problem,
    regex_problem,
    repository_url_problem,
)
from ccai.pychestrate.core.managers.release_template_manager import (
    ReleaseTemplateManager,
    ReleaseTemplateValidationError,
)
from ccai.pychestrate.core.managers.repository_manager import (
    RepositoryAuthType,
    RepositoryCreateRequest,
    RepositoryManager,
    RepositoryUpdateRequest,
    RepositoryValidationError,
)
from ccai.pychestrate.core.managers.watch_manager import (
    InvalidPatternError,
    WatchAction,
    WatchActionConfig,
    WatchCondition,
    WatchCreateRequest,
    WatchManager,
    WatchTriggerSource,
)
from ccai.pychestrate.core.orm import (
    Project,
    ProjectBuildSpec,
    ProjectRepository,
    PychestrateModelBase,
)


def _scenario() -> Dict[str, Any]:
    engine = sa.create_engine("sqlite://")
    PychestrateModelBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    project = Project(name="alpha", owner_id=uuid.uuid4(), metadata_json={})
    session.add(project)
    session.flush()
    repository = ProjectRepository(
        project_id=project.id, name="repo", url="https://example.invalid/r.git", auth_type="none",
        default_branch="main",
    )
    session.add(repository)
    session.flush()
    spec = ProjectBuildSpec(project_id=project.id, repository_id=repository.id, name="nightly")
    session.add(spec)
    session.commit()
    rtnval = {"session": session, "project": project.id, "repository": repository.id, "spec": spec.id}
    return rtnval


def _raised(call: Any) -> Any:
    """
        Run ``call`` and return ``(error class name, field)`` of what it
        raised, or None.
    """
    try:
        call()
    except Exception as error:
        return (type(error).__name__, getattr(error, "field", None))
    return None


def test_git_names_are_checked_like_git_does():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: branch names with spaces, '..', '~' or a trailing '/'
    are refused and ordinary names (main, release/1.2, feature/x-y) are
    accepted.**
    """
    refused = [ref_name_problem(name=name) is not None for name in ("my branch", "a..b", "x~1", "feature/", "-x")]
    accepted = [ref_name_problem(name=name) is None for name in ("main", "release/1.2", "feature/x-y")]

    testbase.assert_equal((all(refused), all(accepted)), (True, True))
    return


def test_commit_shas_are_hexadecimal():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: "not-a-sha!!" is refused as a commit and 7 to 40
    hexadecimal characters are accepted.**
    """
    testbase.assert_equal(
        (commit_sha_problem(value="not-a-sha!!") is not None,
         commit_sha_problem(value="abc1234") is None,
         commit_sha_problem(value="0123456789abcdef0123456789abcdef01234567") is None),
        (True, True, True),
    )
    return


def test_repository_urls_must_be_git_urls():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: plain text is not a repository URL; https, ssh and
    git@host:path URLs are; an SSH key needs an SSH URL.**
    """
    testbase.assert_equal(
        (repository_url_problem(url="not a url") is not None,
         repository_url_problem(url="https://github.com/org/repo.git") is None,
         repository_url_problem(url="git@github.com:org/repo.git") is None,
         repository_url_problem(url="https://github.com/org/repo.git", ssh_only=True) is not None),
        (True, True, True, True),
    )
    return


def test_regular_expressions_must_compile():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: "([unclosed" is reported as an invalid regular
    expression with the reason; "^v\\d+" is accepted.**
    """
    problem = regex_problem(pattern="([unclosed", what="version pattern")

    testbase.assert_equal(
        ("version pattern" in (problem or ""), regex_problem(pattern=r"^v\d+") is None), (True, True)
    )
    return


def test_a_repository_with_a_garbage_url_is_refused_on_the_url_field():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: adding a repository whose URL is not a Git URL raises a
    validation error for the url field.**
    """
    scenario = _scenario()
    manager = RepositoryManager(scenario["session"])

    outcome = _raised(lambda: manager.add_repository(
        scenario["project"],
        RepositoryCreateRequest(name="bad", url="just some words", auth_type=RepositoryAuthType.NONE),
        str(uuid.uuid4()),
    ))

    testbase.assert_equal(outcome, ("RepositoryValidationError", "url"))
    return


def test_a_repository_default_branch_must_be_a_branch_name():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: changing a repository's default branch to "no such
    branch!" is refused on the default_branch field.**
    """
    scenario = _scenario()
    manager = RepositoryManager(scenario["session"])

    outcome = _raised(lambda: manager.update_repository(
        scenario["repository"], RepositoryUpdateRequest(default_branch="no such branch!"), str(uuid.uuid4()),
    ))

    testbase.assert_equal(outcome, ("RepositoryValidationError", "default_branch"))
    return


def test_a_build_of_a_bogus_commit_is_refused():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: triggering a build of commit "not-a-sha!!" raises a
    validation error for commit_sha and creates no build.**
    """
    scenario = _scenario()
    manager = BuildManager(scenario["session"])

    outcome = _raised(lambda: manager.trigger_build(
        BuildTriggerRequest(spec_id=scenario["spec"], commit_sha="not-a-sha!!"), str(uuid.uuid4()),
    ))

    testbase.assert_equal(
        (outcome, manager.list_builds(project_id=scenario["project"]).total),
        (("BuildValidationError", "commit_sha"), 0),
    )
    return


def test_a_build_specification_branch_must_be_a_branch_name():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: a build specification for branch "a..b" is refused on
    the branch field.**
    """
    scenario = _scenario()
    manager = BuildManager(scenario["session"])

    outcome = _raised(lambda: manager.create_spec(
        scenario["project"],
        BuildSpecCreateRequest(name="other", repository_id=scenario["repository"], branch="a..b", steps=[]),
        str(uuid.uuid4()),
    ))

    testbase.assert_equal(outcome, ("BuildSpecValidationError", "branch"))
    return


def test_a_release_template_version_pattern_must_compile():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: a release template with version pattern "([unclosed" is
    refused on the version_pattern field.**
    """
    scenario = _scenario()
    manager = ReleaseTemplateManager(db_session=scenario["session"])

    outcome = _raised(lambda: manager.create(
        scenario["project"], name="standard", version_pattern="([unclosed", default_repo_ids=[],
    ))

    testbase.assert_equal(outcome, ("ReleaseTemplateValidationError", "version_pattern"))
    return


def test_a_release_template_cannot_name_a_repository_of_no_project():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: a release template whose default repositories include
    an id that is not one of the project's repositories is refused on
    default_repo_ids.**
    """
    scenario = _scenario()
    manager = ReleaseTemplateManager(db_session=scenario["session"])

    outcome = _raised(lambda: manager.create(
        scenario["project"], name="standard", default_repo_ids=[scenario["repository"], 999],
    ))

    testbase.assert_equal(outcome, ("ReleaseTemplateValidationError", "default_repo_ids"))
    return


def test_a_watch_pattern_error_names_its_field():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: a watch whose branch pattern is not a regular
    expression is refused with the reason, on the branch_pattern
    field.**
    """
    scenario = _scenario()

    error = None
    try:
        WatchManager(scenario["session"]).create_watch(
            scenario["project"],
            WatchCreateRequest(
                name="bad-pattern", trigger_source=WatchTriggerSource.REPOSITORY_COMMIT,
                source_id=scenario["repository"], conditions=WatchCondition(branch_pattern="([unclosed"),
                actions=[WatchActionConfig(action=WatchAction.TRIGGER_BUILD, target_id=scenario["spec"])],
            ),
            str(uuid.uuid4()),
        )
    except InvalidPatternError as refusal:
        error = refusal

    testbase.assert_equal(
        (error.field, "not a valid regular expression" in error.message), ("branch_pattern", True)
    )
    return


def test_a_fetch_that_cannot_find_the_default_branch_is_an_error():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: fetching a repository whose default branch does not
    exist raises a validation error for default_branch naming the
    branches it has, and records nothing (it used to report
    "updated").**
    """
    root = tempfile.mkdtemp(prefix="pyc-validation-")
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    try:
        work = os.path.join(root, "work")
        subprocess.run(["git", "init", "-q", "-b", "trunk", work], env=env, check=True, capture_output=True)
        with open(os.path.join(work, "README"), "w") as readme:
            readme.write("x\n")
        subprocess.run(["git", "add", "README"], cwd=work, env=env, check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "x"],
                       cwd=work, env=env, check=True, capture_output=True)
        scenario = _scenario()
        session = scenario["session"]
        repository = session.query(ProjectRepository).filter(ProjectRepository.id == scenario["repository"]).one()
        repository.url = "file://" + work
        session.commit()

        message = None
        try:
            RepositoryManager(session).fetch_latest(scenario["repository"])
        except RepositoryValidationError as refusal:
            message = (refusal.field, "no branch named 'main'" in refusal.message, "trunk" in refusal.message)
        fetched_at = session.query(ProjectRepository).filter(
            ProjectRepository.id == scenario["repository"]
        ).one().last_fetch_time
    finally:
        shutil.rmtree(root, ignore_errors=True)

    testbase.assert_equal((message, fetched_at), (("default_branch", True, True), None))
    return


def test_completing_a_build_with_an_unknown_result_is_a_validation_error():
    """
    **Feature: projects (PRJ-24 input validation)**
    **Property: complete_build with a result other than succeeded or
    failed raises BuildValidationError (the class it raised did not
    exist, so this was a NameError).**
    """
    scenario = _scenario()
    manager = BuildManager(scenario["session"])
    build = manager.trigger_build(BuildTriggerRequest(spec_id=scenario["spec"]), str(uuid.uuid4()))

    outcome = _raised(lambda: manager.complete_build(build.id, "exploded"))

    testbase.assert_equal(outcome, ("BuildValidationError", "status"))
    return
