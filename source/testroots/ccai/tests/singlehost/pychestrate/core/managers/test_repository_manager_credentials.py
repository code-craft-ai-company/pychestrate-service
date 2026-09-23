"""
.. module:: test_repository_manager_credentials
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests that repository credentials are resolved and handed
               to git

.. moduleauthor:: Code Craft AI LLC

Repositories with ``https_token`` or ``ssh_key`` authentication name a
credential secret. The manager used to resolve it through a legacy
secret manager the web UI never supplied, with a call signature the
manager did not even have, and swallowed the error -- git ran without
credentials and only public repositories worked.

**Feature: projects (PRJ-11 repository credentials)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import stat
import subprocess
import uuid

from typing import Any, Dict, List

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from ccai import testbase

from ccai.pychestrate.core.managers.repository_manager import (
    RepositoryConnectivityError,
    RepositoryCredentialError,
    RepositoryManager,
)
from ccai.pychestrate.core.orm import (
    Project,
    ProjectRepository,
    PychestrateModelBase,
)


TOKEN = "ghp_example_token_value_1234567890"


def _repository(*, auth_type: str, secret_ref: Any, url: str = "https://git.example.invalid/org/repo.git") -> Any:
    """
        An in-memory database with one project and one repository.

        :returns: Tuple of (session, repository).
    """
    engine = sa.create_engine("sqlite://")
    PychestrateModelBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    project = Project(name="alpha", owner_id=uuid.uuid4(), metadata_json={})
    session.add(project)
    session.flush()
    repository = ProjectRepository(
        project_id=project.id, name="repo", url=url, auth_type=auth_type,
        credential_secret_ref=secret_ref, default_branch="main",
    )
    session.add(repository)
    session.commit()
    rtnval = (session, repository)
    return rtnval


def _recording_resolver(*, calls: List[str], value: str = TOKEN) -> Any:
    """
        A credential resolver that records each reference it is asked
        for and answers ``value``.
    """
    def _resolve(secret_ref: str) -> str:
        calls.append(secret_ref)
        return value
    rtnval = _resolve
    return rtnval


def test_the_credential_is_read_through_the_resolver():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: an https_token repository's credential secret reference
    is resolved through the supplied credential_resolver.**
    """
    session, repository = _repository(auth_type="https_token", secret_ref="ci/github-token")
    calls: List[str] = []
    manager = RepositoryManager(session, credential_resolver=_recording_resolver(calls=calls))

    credential = manager._get_credential_for_repository(repository)

    testbase.assert_equal((credential, calls), (TOKEN, ["ci/github-token"]))
    return


def test_a_public_repository_needs_no_credential():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: a repository with authentication "none" resolves no
    credential and never calls the resolver.**
    """
    session, repository = _repository(auth_type="none", secret_ref=None)
    calls: List[str] = []
    manager = RepositoryManager(session, credential_resolver=_recording_resolver(calls=calls))

    credential = manager._get_credential_for_repository(repository)

    testbase.assert_equal((credential, calls), (None, []))
    return


def test_a_missing_credential_reference_is_an_error_not_silence():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: an https_token repository without a secret reference
    raises RepositoryCredentialError instead of running git without
    credentials.**
    """
    session, repository = _repository(auth_type="https_token", secret_ref=None)
    manager = RepositoryManager(session, credential_resolver=_recording_resolver(calls=[]))

    raised = False
    try:
        manager._get_credential_for_repository(repository)
    except RepositoryCredentialError:
        raised = True

    testbase.assert_equal(raised, True)
    return


def test_an_unreadable_secret_stops_the_connectivity_test_before_git_runs():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: when the resolver refuses the secret, test_connectivity
    raises the resolver's RepositoryCredentialError (it used to swallow
    lookup errors and try anonymously).**
    """
    session, repository = _repository(auth_type="https_token", secret_ref="ci/other-team")

    def _refuse(secret_ref: str) -> str:
        raise RepositoryCredentialError("You do not have access to the secret ci/other-team.")

    manager = RepositoryManager(session, credential_resolver=_refuse)

    message = None
    try:
        manager.test_connectivity(repository.id)
    except RepositoryCredentialError as refusal:
        message = refusal.message

    testbase.assert_equal(message, "You do not have access to the secret ci/other-team.")
    return


def _run_askpass(*, access: Dict[str, Any], prompt: str) -> str:
    """
        Ask the GIT_ASKPASS helper what git would be told for ``prompt``.
    """
    completed = subprocess.run(
        [access["env"]["GIT_ASKPASS"], prompt],
        env=access["env"], capture_output=True, text=True, timeout=10,
    )
    rtnval = completed.stdout.strip()
    return rtnval


def test_https_token_is_answered_to_git_through_askpass():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: for https_token, git's password prompt is answered with
    the token and its username prompt with x-access-token, through a
    private GIT_ASKPASS script.**
    """
    session, repository = _repository(auth_type="https_token", secret_ref="ci/github-token")
    manager = RepositoryManager(session, credential_resolver=_recording_resolver(calls=[]))

    with manager._git_access(repository=repository) as access:
        answers = (
            _run_askpass(access=access, prompt="Username for 'https://git.example.invalid': "),
            _run_askpass(access=access, prompt="Password for 'https://x-access-token@git.example.invalid': "),
        )

    testbase.assert_equal(answers, ("x-access-token", TOKEN))
    return


def test_the_token_never_appears_on_the_git_command_line():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: the git options added for https_token carry no part of
    the token (a command line is visible to every local user), and they
    switch configured credential helpers off.**
    """
    session, repository = _repository(auth_type="https_token", secret_ref="ci/github-token")
    manager = RepositoryManager(session, credential_resolver=_recording_resolver(calls=[]))

    with manager._git_access(repository=repository) as access:
        args = list(access["args"])

    testbase.assert_equal(
        (any(TOKEN in arg for arg in args), args), (False, ["-c", "credential.helper="])
    )
    return


def test_the_username_in_the_url_is_used_for_the_token():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: an https URL carrying a user name (bitbucket style) makes
    askpass answer that user name.**
    """
    session, repository = _repository(
        auth_type="https_token", secret_ref="ci/bb", url="https://build-bot@bitbucket.example.invalid/o/r.git",
    )
    manager = RepositoryManager(session, credential_resolver=_recording_resolver(calls=[]))

    with manager._git_access(repository=repository) as access:
        username = _run_askpass(access=access, prompt="Username for 'https://bitbucket.example.invalid': ")

    testbase.assert_equal(username, "build-bot")
    return


def test_an_ssh_key_is_written_privately_and_removed_afterwards():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: for ssh_key, git's ssh command uses the key from a file
    only its owner can read, and the file is gone after the command.**
    """
    key = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----"
    session, repository = _repository(
        auth_type="ssh_key", secret_ref="ci/deploy-key", url="git@git.example.invalid:org/repo.git",
    )
    manager = RepositoryManager(session, credential_resolver=_recording_resolver(calls=[], value=key))

    with manager._git_access(repository=repository) as access:
        ssh_command = access["env"]["GIT_SSH_COMMAND"]
        key_path = ssh_command.split(" -i ", 1)[1].split(" ", 1)[0]
        mode = stat.S_IMODE(os.stat(key_path).st_mode)
        with open(key_path, "r") as key_file:
            written = key_file.read()

    testbase.assert_equal(
        (mode, written.strip() == key, os.path.exists(key_path)), (0o600, True, False)
    )
    return


def test_a_git_failure_is_explained_without_the_token():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: a git authentication failure becomes a message about the
    credential secret, and nothing git printed (which may include the
    token) reaches the user.**
    """
    session, repository = _repository(auth_type="https_token", secret_ref="ci/github-token")
    manager = RepositoryManager(session, credential_resolver=_recording_resolver(calls=[]))
    stderr = "remote: Invalid username or password.\nfatal: Authentication failed for 'https://x:{}@host/'".format(TOKEN)

    message = manager._describe_git_failure(
        repository=repository, action="connect to", stderr=stderr, secrets=[TOKEN]
    )

    testbase.assert_equal(
        (TOKEN in message, "credential" in message, "fatal" in message), (False, True, False)
    )
    return


def test_connectivity_against_a_local_repository_succeeds_without_credentials():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: test_connectivity runs git against a public (local)
    repository and succeeds -- the git plumbing still works for
    repositories without authentication.**
    """
    import tempfile

    workdir = tempfile.mkdtemp(prefix="pyc-repo-test-")
    subprocess.run(["git", "init", "--bare", "-q", workdir], check=True, capture_output=True)
    session, repository = _repository(auth_type="none", secret_ref=None, url="file://" + workdir)
    manager = RepositoryManager(session)

    try:
        result = manager.test_connectivity(repository.id)
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)

    testbase.assert_equal(result, True)
    return


def test_a_connectivity_failure_raises_a_readable_error():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: a URL git cannot reach raises RepositoryConnectivityError
    whose message says it could not connect (not git's raw output).**
    """
    session, repository = _repository(auth_type="none", secret_ref=None, url="file:///nonexistent/pyc-no-repo")
    manager = RepositoryManager(session)

    message = None
    try:
        manager.test_connectivity(repository.id)
    except RepositoryConnectivityError as failure:
        message = failure.message

    testbase.assert_equal(message.startswith("Could not connect to the repository:"), True)
    return
