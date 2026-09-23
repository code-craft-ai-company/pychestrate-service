"""
.. module:: test_watch_events
    :platform: Darwin, Linux, Unix
    :synopsis: Tests that project watches fire: repository fetches find
               new commits, branches and tags, and finished builds report
               their result.

.. moduleauthor:: Code Craft AI LLC

``WatchManager.process_event`` had no callers, so no watch ever fired,
and its actions called manager methods that do not exist
(``trigger_build_by_spec_id``) as a user named ``"system"``. These tests
run against a real (in-memory, foreign-key enforcing) database and a
local bare git repository.

**Feature: projects (PRJ-10 watches)**
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

from typing import Any, Dict, List, Optional

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from ccai import testbase

from ccai.pychestrate.core.managers.build_manager import (
    BuildAlreadyFinishedError,
    BuildManager,
    BuildTriggerRequest,
    JobStatus,
)
from ccai.pychestrate.core.managers.repository_manager import RepositoryManager
from ccai.pychestrate.core.managers.watch_manager import (
    WatchAction,
    WatchActionConfig,
    WatchCondition,
    WatchCreateRequest,
    WatchManager,
    WatchTriggerSource,
    WatchValidationError,
)
from ccai.pychestrate.core.orm import (
    Project,
    ProjectBuild,
    ProjectBuildSpec,
    ProjectInfraSpec,
    ProjectPipelineRun,
    ProjectReleasePipeline,
    ProjectRepository,
    ProjectRepositoryRef,
    ProjectTestJob,
    ProjectTestSpec,
    ProjectWatch,
    ProjectWatchTriggerLog,
    PychestrateModelBase,
    User,
)


_GIT_ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)


def _git(*args: str, cwd: str) -> str:
    completed = subprocess.run(
        ["git"] + list(args), cwd=cwd, env=_GIT_ENV, capture_output=True, text=True,
        timeout=60, check=True,
    )
    rtnval = completed.stdout.strip()
    return rtnval


class _Origin:
    """
        A bare repository (the "remote") and a clone to change it from.
    """

    def __init__(self) -> None:
        self.root = tempfile.mkdtemp(prefix="pyc-watch-origin-")
        self.work = os.path.join(self.root, "work")
        self.bare = os.path.join(self.root, "origin.git")
        _git("init", "-q", "-b", "main", self.work, cwd=self.root)
        self.commit(branch="main", message="Initial commit")
        _git("clone", "-q", "--bare", self.work, self.bare, cwd=self.root)
        return

    @property
    def url(self) -> str:
        return "file://" + self.bare

    def commit(self, *, branch: str, message: str) -> str:
        # (The first commit is made on the unborn main branch.)
        if _git("symbolic-ref", "--short", "HEAD", cwd=self.work) != branch:
            _git("checkout", "-q", branch, cwd=self.work)
        with open(os.path.join(self.work, "CHANGES.txt"), "a") as changes:
            changes.write(message + "\n")
        _git("add", "CHANGES.txt", cwd=self.work)
        _git("-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", message,
             cwd=self.work)
        if os.path.isdir(self.bare):
            _git("push", "-q", self.bare, "{0}:refs/heads/{0}".format(branch), cwd=self.work)
        rtnval = _git("rev-parse", "HEAD", cwd=self.work)
        return rtnval

    def branch(self, *, name: str) -> str:
        _git("branch", name, "main", cwd=self.work)
        _git("push", "-q", self.bare, "{0}:refs/heads/{0}".format(name), cwd=self.work)
        rtnval = _git("rev-parse", name, cwd=self.work)
        return rtnval

    def tag(self, *, name: str) -> str:
        _git("-c", "user.name=T", "-c", "user.email=t@example.invalid", "tag", "-a", "-m", name, name,
             "main", cwd=self.work)
        _git("push", "-q", self.bare, "refs/tags/{0}:refs/tags/{0}".format(name), cwd=self.work)
        rtnval = _git("rev-parse", "main", cwd=self.work)
        return rtnval

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
        return


class _Scenario:
    """
        A project owned by a user, with one repository pointing at an
        :class:`_Origin`, a build specification building it, a test
        specification, an infrastructure specification and a pipeline.
    """

    def __init__(self) -> None:
        engine = sa.create_engine("sqlite://")

        @sa.event.listens_for(engine, "connect")
        def _enforce_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
            dbapi_connection.execute("PRAGMA foreign_keys=ON")
            return

        PychestrateModelBase.metadata.create_all(engine)
        self.session = sessionmaker(bind=engine)()
        self.owner = User(
            id=uuid.uuid4(), first_name="Owner", last_name="One", display_name="Owner One",
            email="owner@example.invalid", login="owner-one", status="active", authtype="internal",
        )
        self.session.add(self.owner)
        self.session.flush()
        self.origin = _Origin()
        self.project = self._add(Project(name="alpha", owner_id=self.owner.id, metadata_json={}))
        self.repository = self._add(ProjectRepository(
            project_id=self.project.id, name="repo", url=self.origin.url, auth_type="none",
            default_branch="main",
        ))
        self.build_spec = self._add(ProjectBuildSpec(
            project_id=self.project.id, repository_id=self.repository.id, name="nightly", branch="main",
        ))
        self.test_spec = self._add(ProjectTestSpec(
            project_id=self.project.id, name="smoke", framework="pytest", test_command="pytest",
        ))
        self.infra_spec = self._add(ProjectInfraSpec(project_id=self.project.id, name="stage", provider="docker"))
        self.pipeline = self._add(ProjectReleasePipeline(project_id=self.project.id, name="ship"))
        self.session.commit()
        return

    def _add(self, row: Any) -> Any:
        self.session.add(row)
        self.session.flush()
        return row

    def watch(
            self, *, name: str, trigger: WatchTriggerSource, action: WatchAction, target_id: int,
            conditions: Optional[WatchCondition] = None, source_id: Optional[int] = None,
            parameters: Optional[Dict[str, Any]] = None
        ) -> int:
        response = WatchManager(self.session).create_watch(
            self.project.id,
            WatchCreateRequest(
                name=name,
                trigger_source=trigger,
                source_id=source_id if source_id is not None else self.repository.id,
                conditions=conditions or WatchCondition(),
                actions=[WatchActionConfig(action=action, target_id=target_id, parameters=parameters or {})],
            ),
            str(self.owner.id),
        )
        return response.id

    def fetch(self) -> Any:
        rtnval = RepositoryManager(self.session).fetch_latest(self.repository.id)
        return rtnval

    def logs(self, watch_id: int) -> List[Any]:
        rtnval = self.session.query(ProjectWatchTriggerLog).filter(
            ProjectWatchTriggerLog.watch_id == watch_id
        ).all()
        return rtnval

    def builds(self) -> List[Any]:
        rtnval = self.session.query(ProjectBuild).order_by(ProjectBuild.id).all()
        return rtnval

    def close(self) -> None:
        self.session.close()
        self.origin.close()
        return


def test_the_first_fetch_records_the_refs_and_fires_nothing():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: the first fetch of a repository records its branches and
    tags without starting any watch (announcing every existing ref would
    start a build for each).**
    """
    scenario = _Scenario()
    try:
        watch_id = scenario.watch(
            name="build-on-push", trigger=WatchTriggerSource.REPOSITORY_COMMIT,
            action=WatchAction.TRIGGER_BUILD, target_id=scenario.build_spec.id,
        )
        fetched = scenario.fetch()
        outcome = (
            fetched.refs_first_recorded,
            fetched.ref_changes,
            len(scenario.logs(watch_id)),
            [(ref.kind, ref.name) for ref in scenario.session.query(ProjectRepositoryRef).all()],
        )
    finally:
        scenario.close()

    testbase.assert_equal(outcome, (True, [], 0, [("branch", "main")]))
    return


def test_a_new_commit_fires_the_commit_watch_and_builds_that_commit():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: after a new commit on main, a fetch fires the
    "new commits" watch, which starts a build of that branch and commit
    with trigger type "watch".**
    """
    scenario = _Scenario()
    try:
        scenario.watch(
            name="build-on-push", trigger=WatchTriggerSource.REPOSITORY_COMMIT,
            action=WatchAction.TRIGGER_BUILD, target_id=scenario.build_spec.id,
        )
        scenario.fetch()
        new_sha = scenario.origin.commit(branch="main", message="Second")
        fetched = scenario.fetch()
        outcome = (
            fetched.watches_triggered,
            [(b.branch, b.commit_sha, b.trigger_type) for b in scenario.builds()],
        )
    finally:
        scenario.close()

    testbase.assert_equal(outcome, (1, [("main", new_sha, "watch")]))
    return


def test_watch_actions_run_as_the_project_owner_when_nobody_is_named():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: an action started by an event nobody initiated runs as
    the project's owner (it used to use the user id "system", which is
    not a user and failed).**
    """
    scenario = _Scenario()
    try:
        scenario.watch(
            name="build-on-push", trigger=WatchTriggerSource.REPOSITORY_COMMIT,
            action=WatchAction.TRIGGER_BUILD, target_id=scenario.build_spec.id,
        )
        scenario.fetch()
        scenario.origin.commit(branch="main", message="Second")
        scenario.fetch()
        triggered_by = [str(b.triggered_by_id) for b in scenario.builds()]
        owner = str(scenario.owner.id)
    finally:
        scenario.close()

    testbase.assert_equal(triggered_by, [owner])
    return


def test_a_new_branch_fires_the_branch_watch():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: a fetch that finds a new branch fires the "new branch"
    watch with that branch in its event.**
    """
    scenario = _Scenario()
    try:
        watch_id = scenario.watch(
            name="on-branch", trigger=WatchTriggerSource.REPOSITORY_BRANCH,
            action=WatchAction.TRIGGER_TEST_JOB, target_id=scenario.test_spec.id,
        )
        scenario.fetch()
        scenario.origin.branch(name="feature/login")
        scenario.fetch()
        events = [log.trigger_event_json.get("branch") for log in scenario.logs(watch_id)]
    finally:
        scenario.close()

    testbase.assert_equal(events, ["feature/login"])
    return


def test_a_new_tag_fires_only_the_tag_watches_that_match():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: a new tag v1.0.0 fires the tag watch whose pattern is
    ^v and not the one whose pattern is ^release-.**
    """
    scenario = _Scenario()
    try:
        matching = scenario.watch(
            name="on-version-tag", trigger=WatchTriggerSource.REPOSITORY_TAG,
            action=WatchAction.TRIGGER_PIPELINE, target_id=scenario.pipeline.id,
            conditions=WatchCondition(tag_pattern="^v"),
        )
        other = scenario.watch(
            name="on-release-tag", trigger=WatchTriggerSource.REPOSITORY_TAG,
            action=WatchAction.TRIGGER_PIPELINE, target_id=scenario.pipeline.id,
            conditions=WatchCondition(tag_pattern="^release-"),
        )
        scenario.fetch()
        scenario.origin.tag(name="v1.0.0")
        scenario.fetch()
        fired = (len(scenario.logs(matching)), len(scenario.logs(other)))
    finally:
        scenario.close()

    testbase.assert_equal(fired, (1, 0))
    return


def test_a_commit_on_a_branch_the_watch_does_not_match_fires_nothing():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: with branch pattern ^main$, a new commit on dev does not
    fire the watch.**
    """
    scenario = _Scenario()
    try:
        scenario.origin.branch(name="dev")
        watch_id = scenario.watch(
            name="main-only", trigger=WatchTriggerSource.REPOSITORY_COMMIT,
            action=WatchAction.TRIGGER_BUILD, target_id=scenario.build_spec.id,
            conditions=WatchCondition(branch_pattern="^main$"),
        )
        scenario.fetch()
        scenario.origin.commit(branch="dev", message="On dev")
        scenario.fetch()
        fired = len(scenario.logs(watch_id))
    finally:
        scenario.close()

    testbase.assert_equal(fired, 0)
    return


def test_a_failing_action_is_logged_and_the_fetch_still_succeeds():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: when a watch's action fails, the trigger log records the
    failure and the fetch still records the new commit.**
    """
    scenario = _Scenario()
    try:
        watch_id = scenario.watch(
            name="bad-infra", trigger=WatchTriggerSource.REPOSITORY_COMMIT,
            action=WatchAction.TRIGGER_INFRA_JOB, target_id=scenario.infra_spec.id,
            parameters={"action": "explode"},
        )
        scenario.fetch()
        new_sha = scenario.origin.commit(branch="main", message="Second")
        fetched = scenario.fetch()
        logs = scenario.logs(watch_id)
        outcome = (
            fetched.last_commit_sha == new_sha,
            [(log.success, bool(log.error_message)) for log in logs],
        )
    finally:
        scenario.close()

    testbase.assert_equal(outcome, (True, [(False, True)]))
    return


def test_a_pipeline_action_starts_a_watch_triggered_run():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: the "start a release pipeline" action creates a pipeline
    run with trigger type "watch" (the manager had no such type and was
    passed a plain string).**
    """
    scenario = _Scenario()
    try:
        scenario.watch(
            name="ship-on-tag", trigger=WatchTriggerSource.REPOSITORY_TAG,
            action=WatchAction.TRIGGER_PIPELINE, target_id=scenario.pipeline.id,
        )
        scenario.fetch()
        scenario.origin.tag(name="v2.0.0")
        scenario.fetch()
        runs = [run.trigger_type for run in scenario.session.query(ProjectPipelineRun).all()]
    finally:
        scenario.close()

    testbase.assert_equal(runs, ["watch"])
    return


def _started_build(scenario: _Scenario) -> Any:
    build = BuildManager(scenario.session).trigger_build(
        BuildTriggerRequest(spec_id=scenario.build_spec.id), str(scenario.owner.id)
    )
    return build


def test_a_failed_build_fires_the_build_completion_watch_with_its_build():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: completing a build as failed fires the build-completion
    watch waiting for failures, whose test job runs against that build.**
    """
    scenario = _Scenario()
    try:
        scenario.watch(
            name="test-failures", trigger=WatchTriggerSource.BUILD_COMPLETION,
            source_id=scenario.build_spec.id,
            action=WatchAction.TRIGGER_TEST_JOB, target_id=scenario.test_spec.id,
            conditions=WatchCondition(build_status="failed"),
        )
        build = _started_build(scenario)
        BuildManager(scenario.session).complete_build(build.id, JobStatus.FAILED)
        jobs = [job.build_id for job in scenario.session.query(ProjectTestJob).all()]
    finally:
        scenario.close()

    testbase.assert_equal(jobs, [build.id])
    return


def test_a_succeeded_build_does_not_fire_a_watch_for_failures():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: a build that succeeded does not fire a watch that waits
    for failed builds.**
    """
    scenario = _Scenario()
    try:
        watch_id = scenario.watch(
            name="test-failures", trigger=WatchTriggerSource.BUILD_COMPLETION,
            source_id=scenario.build_spec.id,
            action=WatchAction.TRIGGER_TEST_JOB, target_id=scenario.test_spec.id,
            conditions=WatchCondition(build_status="failed"),
        )
        build = _started_build(scenario)
        BuildManager(scenario.session).complete_build(build.id, JobStatus.SUCCEEDED)
        fired = len(scenario.logs(watch_id))
    finally:
        scenario.close()

    testbase.assert_equal(fired, 0)
    return


def test_a_cancelled_build_fires_nothing():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: cancelling a build does not fire build-completion
    watches, even those waiting for any result.**
    """
    scenario = _Scenario()
    try:
        watch_id = scenario.watch(
            name="after-any-build", trigger=WatchTriggerSource.BUILD_COMPLETION,
            source_id=scenario.build_spec.id,
            action=WatchAction.TRIGGER_TEST_JOB, target_id=scenario.test_spec.id,
        )
        build = _started_build(scenario)
        BuildManager(scenario.session).cancel_build(build.id, str(scenario.owner.id))
        fired = len(scenario.logs(watch_id))
    finally:
        scenario.close()

    testbase.assert_equal(fired, 0)
    return


def test_a_finished_build_cannot_be_completed_again():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: reporting the result of a build that already finished
    raises BuildAlreadyFinishedError (and fires nothing twice).**
    """
    scenario = _Scenario()
    try:
        build = _started_build(scenario)
        manager = BuildManager(scenario.session)
        manager.complete_build(build.id, JobStatus.SUCCEEDED)
        raised = False
        try:
            manager.complete_build(build.id, JobStatus.FAILED)
        except BuildAlreadyFinishedError:
            raised = True
    finally:
        scenario.close()

    testbase.assert_equal(raised, True)
    return


def test_a_watch_cannot_run_the_build_that_starts_it():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: a build-completion watch that would run a build of its
    own specification is refused (each build would start another).**
    """
    scenario = _Scenario()
    try:
        raised = None
        try:
            scenario.watch(
                name="loop", trigger=WatchTriggerSource.BUILD_COMPLETION,
                source_id=scenario.build_spec.id,
                action=WatchAction.TRIGGER_BUILD, target_id=scenario.build_spec.id,
            )
        except WatchValidationError as refusal:
            raised = refusal.error_code
    finally:
        scenario.close()

    testbase.assert_equal(raised, "WATCH_TRIGGERS_ITSELF")
    return


def test_watch_test_reports_which_conditions_apply():
    """
    **Feature: projects (PRJ-10 watch test)**
    **Property: test_watch reports, per condition, whether it applies to
    the watch and whether the sample matches it, without running
    anything.**
    """
    scenario = _Scenario()
    try:
        watch_id = scenario.watch(
            name="main-only", trigger=WatchTriggerSource.REPOSITORY_COMMIT,
            action=WatchAction.TRIGGER_BUILD, target_id=scenario.build_spec.id,
            conditions=WatchCondition(branch_pattern="^main$"),
        )
        result = WatchManager(scenario.session).test_watch(watch_id, {"branch": "dev"})
        branch = result["condition_results"]["branch_pattern"]
        outcome = (
            result["would_trigger"],
            (branch["applies"], branch["matches"]),
            result["condition_results"]["tag_pattern"]["applies"],
            len(scenario.builds()),
        )
    finally:
        scenario.close()

    testbase.assert_equal(outcome, (False, (True, False), False, 0))
    return


def test_removing_a_repository_forgets_its_refs():
    """
    **Feature: projects (PRJ-10 watches)**
    **Property: removing a fetched repository also removes the branches
    and tags recorded for it (the foreign key would refuse otherwise).**
    """
    scenario = _Scenario()
    try:
        scenario.session.delete(scenario.build_spec)
        scenario.session.commit()
        scenario.fetch()
        RepositoryManager(scenario.session).remove_repository(scenario.repository.id, str(scenario.owner.id))
        left = scenario.session.query(ProjectRepositoryRef).count()
    finally:
        scenario.close()

    testbase.assert_equal(left, 0)
    return
