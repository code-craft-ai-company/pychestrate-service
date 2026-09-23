"""
.. module:: test_p27u_deploy_script_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``deployment/deploy-alpha-to-host.sh`` arguments and
               ``--dry-run`` (audit finding CLI-21).

.. moduleauthor:: Code Craft AI LLC

The audit found the deploy script defaulted to the author's host, user
and tailnet name, had no ``--dry-run`` before ``rsync --delete`` and
the sudo steps, accepted only ``--key=value``, left two flags out of
its usage text, and demanded a GitHub token even when
``pyproject.toml`` names no git source.

Nothing here deploys anything or reaches the network: the script runs
as a copy inside a temporary directory shaped like the repository
(it resolves the repository from its own location), with stub ``ssh``
/ ``rsync`` / ``scp`` / ``curl`` / ``sudo`` first on ``PATH`` that only
log their arguments, a stub ``development/build-frontend.sh``, and a
throw-away ``HOME``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import shutil
import subprocess
import tempfile

from pathlib import Path
from typing import Dict, List, Optional

from ccai import testbase

from ccai.testshared.factories.pyc.pyc_harness import find_repository_root
from ccai.testshared.skip_helper import skip_test


DEPLOYMENT_FILES = (
    "deploy-alpha-to-host.sh",
    "pychestrate.nginx.conf.template",
    "pychestrate.service.template",
    "pychestrate-backup.service.template",
    "pychestrate-backup.timer.template",
    "pychestrate.logrotate.template",
)

EVERY_OPTION = (
    "--host", "--user", "--port", "--proxy-port", "--public-hostname", "--client-ca-path",
    "--skip-system-setup", "--dry-run", "--help",
)

PYPROJECT_WITH_GIT_SOURCES = (
    '[tool.poetry]\nname = "svc"\nversion = "0.0.1"\n\n'
    '[tool.poetry.dependencies]\n'
    'codecraftai-errors = { git = "https://github.com/automationmojo/codecraftai-errors.git", branch = "main" }\n'
)

PYPROJECT_WITH_AN_INDEX = (
    '[tool.poetry]\nname = "svc"\nversion = "0.0.1"\n\n'
    '[tool.poetry.dependencies]\n'
    'codecraftai-errors = { version = "<2.0.0", source = "codecraftai" }\n'
)

#: Logs its name and arguments; ssh / rsync succeed (rsync --version
#: answers like rsync 3), everything else fails loudly.
STUB_SCRIPT = r"""
name="$(basename "$0")"
printf '%s %s\n' "$name" "$*" >> "$STUB_LOG"
case "$name" in
    rsync)
        case "$*" in *--version*) echo "rsync  version 3.2.7  protocol version 31" ;; esac
        exit 0 ;;
    ssh) exit 0 ;;
esac
exit 99
"""

FRONTEND_STUB = r"""#!/bin/sh
printf 'build-frontend %s\n' "$*" >> "$STUB_LOG"
exit 99
"""


class _DeploySandbox:
    """
        A temporary repository holding a copy of the deploy script and
        its templates, with stub tools first on PATH.
    """

    def __init__(self, *, pyproject: str = PYPROJECT_WITH_GIT_SOURCES) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="pyc-deploy-"))
        source = find_repository_root() / "deployment"
        (self.root / "deployment").mkdir()
        for name in DEPLOYMENT_FILES:
            shutil.copy2(str(source / name), str(self.root / "deployment" / name))
        (self.root / "development").mkdir()
        frontend = self.root / "development" / "build-frontend.sh"
        frontend.write_text(FRONTEND_STUB, encoding="utf-8")
        os.chmod(str(frontend), 0o755)
        (self.root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
        self.stubs = self.root / "stubs"
        self.stubs.mkdir()
        for tool in ("ssh", "rsync", "scp", "curl", "sudo"):
            stub = self.stubs / tool
            stub.write_text("#!/bin/sh\n" + STUB_SCRIPT.lstrip("\n"), encoding="utf-8")
            os.chmod(str(stub), 0o755)
        self.home = self.root / "home"
        self.home.mkdir()
        self.log = self.root / "calls.log"
        return

    def run(self, *args: str, token: Optional[str] = "fake-token-value") -> subprocess.CompletedProcess:
        bash = shutil.which("bash")
        if bash is None:
            skip_test(reason="bash is not installed")
        env: Dict[str, str] = {
            "PATH": str(self.stubs) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(self.home),
            "STUB_LOG": str(self.log),
            "LANG": "C",
        }
        if token is not None:
            env["CODECRAFTAI_REPO_TOKEN"] = token
        rtnval = subprocess.run(
            [bash, str(self.root / "deployment" / "deploy-alpha-to-host.sh")] + list(args),
            cwd=str(self.root), env=env, capture_output=True, text=True, timeout=120,
        )
        return rtnval

    def calls(self) -> List[str]:
        if not self.log.exists():
            return []
        rtnval = self.log.read_text(encoding="utf-8").splitlines()
        return rtnval

    def close(self) -> None:
        shutil.rmtree(str(self.root), ignore_errors=True)
        return


def _changing_calls(calls: List[str]) -> List[str]:
    """
        The logged calls that could change something: anything but the
        read-only SSH probes, ``rsync --version`` and ``rsync --dry-run``.
    """
    changing = []
    for call in calls:
        if call.startswith("ssh ") and ("BatchMode=yes" in call or call.endswith("bash -ls")):
            continue
        if call.startswith("rsync ") and ("--version" in call or "--dry-run" in call):
            continue
        changing.append(call)
    rtnval = changing
    return rtnval


# ===========================================================================
# Arguments and usage
# ===========================================================================


def test_deploy_script_parses():
    """
    **Feature: deploy script (CLI-21)**
    **Property: 'bash -n' accepts the script.**
    """
    bash = shutil.which("bash")
    if bash is None:
        skip_test(reason="bash is not installed")
    completed = subprocess.run([bash, "-n", str(find_repository_root() / "deployment" / "deploy-alpha-to-host.sh")],
                               capture_output=True, text=True, timeout=60)
    testbase.assert_equal((completed.returncode, completed.stderr), (0, ""))
    return


def test_help_lists_every_option_the_parser_accepts():
    """
    **Feature: deploy script (CLI-21)**
    **Property: --help (generated from the option table) names every
    option, including --public-hostname and --client-ca-path, which the
    old usage block left out.**
    """
    sandbox = _DeploySandbox()
    try:
        completed = sandbox.run("--help")
        missing = [option for option in EVERY_OPTION if option not in completed.stdout]
        testbase.assert_equal((completed.returncode, missing, sandbox.calls()), (0, [], []))
    finally:
        sandbox.close()
    return


def test_host_and_user_are_required():
    """
    **Feature: deploy script (CLI-21)**
    **Property: without --host and --user the script exits 1 before
    doing anything (it used to default to the author's host and user).**
    """
    sandbox = _DeploySandbox()
    try:
        completed = sandbox.run("--dry-run")
        testbase.assert_equal(
            (completed.returncode, "--host and --user are required" in completed.stderr, sandbox.calls()),
            (1, True, []),
        )
    finally:
        sandbox.close()
    return


def test_no_author_specific_values_remain():
    """
    **Feature: deploy script (CLI-21)**
    **Property: the script names no particular host, user or tailnet.**
    """
    text = (find_repository_root() / "deployment" / "deploy-alpha-to-host.sh").read_text(encoding="utf-8")
    found = [value for value in ("tc-app-server", "tailb75ce6", "myron") if value in text]
    testbase.assert_equal(found, [])
    return


def test_space_separated_values_are_accepted():
    """
    **Feature: deploy script (CLI-21)**
    **Property: '--host HOST --user USER' works as well as the '='
    form.**
    """
    sandbox = _DeploySandbox()
    try:
        completed = sandbox.run("--host", "app.example.test", "--user", "deploy", "--dry-run")
        testbase.assert_equal(
            (completed.returncode, "target       : deploy@app.example.test" in completed.stdout), (0, True)
        )
    finally:
        sandbox.close()
    return


def test_equals_values_still_work():
    """
    **Feature: deploy script (CLI-21)**
    **Property: '--host=HOST --user=USER' still works.**
    """
    sandbox = _DeploySandbox()
    try:
        completed = sandbox.run("--host=app.example.test", "--user=deploy", "--dry-run")
        testbase.assert_equal(
            (completed.returncode, "target       : deploy@app.example.test" in completed.stdout), (0, True)
        )
    finally:
        sandbox.close()
    return


def test_option_missing_its_value_is_rejected():
    """
    **Feature: deploy script (CLI-21)**
    **Property: '--host' with no value exits 1 naming the option.**
    """
    sandbox = _DeploySandbox()
    try:
        completed = sandbox.run("--user", "deploy", "--host")
        testbase.assert_equal(
            (completed.returncode, "--host needs a value" in completed.stderr, sandbox.calls()), (1, True, [])
        )
    finally:
        sandbox.close()
    return


def test_unknown_argument_is_rejected():
    """
    **Feature: deploy script (CLI-21)**
    **Property: a misspelled option exits 1 before doing anything.**
    """
    sandbox = _DeploySandbox()
    try:
        completed = sandbox.run("--host", "h", "--user", "u", "--dryrun")
        testbase.assert_equal(
            (completed.returncode, "Unknown argument: --dryrun" in completed.stderr, sandbox.calls()), (1, True, [])
        )
    finally:
        sandbox.close()
    return


def test_public_hostname_defaults_to_the_host():
    """
    **Feature: deploy script (CLI-21)**
    **Property: without --public-hostname the certificate name is the
    --host value (it used to be the author's tailnet name).**
    """
    sandbox = _DeploySandbox()
    try:
        completed = sandbox.run("--host", "app.example.test", "--user", "deploy", "--dry-run")
        testbase.assert_equal("public name  : app.example.test" in completed.stdout, True)
    finally:
        sandbox.close()
    return


# ===========================================================================
# --dry-run
# ===========================================================================


def test_dry_run_changes_nothing():
    """
    **Feature: deploy script (CLI-21)**
    **Property: --dry-run runs only read-only checks (the SSH probe and
    rsync --dry-run) and no local build, copy, remote command or probe,
    and finishes with exit 0.**
    """
    sandbox = _DeploySandbox()
    try:
        completed = sandbox.run("--host", "app.example.test", "--user", "deploy", "--dry-run")
        testbase.assert_equal(
            (completed.returncode, _changing_calls(sandbox.calls()), "DRY RUN COMPLETE" in completed.stdout),
            (0, [], True),
        )
    finally:
        sandbox.close()
    return


def test_dry_run_previews_what_the_sync_would_delete():
    """
    **Feature: deploy script (CLI-21)**
    **Property: --dry-run asks rsync itself for an itemized --dry-run of
    the --delete sync.**
    """
    sandbox = _DeploySandbox()
    try:
        sandbox.run("--host", "app.example.test", "--user", "deploy", "--dry-run")
        sync_calls = [call for call in sandbox.calls() if call.startswith("rsync ") and "--delete" in call]
        testbase.assert_equal(
            (len(sync_calls), all("--dry-run --itemize-changes" in call for call in sync_calls)), (1, True)
        )
    finally:
        sandbox.close()
    return


def test_dry_run_shows_the_remote_scripts():
    """
    **Feature: deploy script (CLI-21)**
    **Property: --dry-run prints the script it would run on the host
    (the migration step's alembic upgrade).**
    """
    sandbox = _DeploySandbox()
    try:
        completed = sandbox.run("--host", "app.example.test", "--user", "deploy", "--dry-run")
        testbase.assert_equal(
            ("would run on deploy@app.example.test" in completed.stdout,
             "alembic -c alembic.ini upgrade head" in completed.stdout),
            (True, True),
        )
    finally:
        sandbox.close()
    return


def test_dry_run_never_prints_the_token():
    """
    **Feature: deploy script (CLI-21)**
    **Property: the dry run's account of the git-credential step masks
    CODECRAFTAI_REPO_TOKEN.**
    """
    sandbox = _DeploySandbox()
    try:
        completed = sandbox.run("--host", "app.example.test", "--user", "deploy", "--dry-run",
                                token="ghp_secret_token_value")
        testbase.assert_equal(
            ("ghp_secret_token_value" in completed.stdout + completed.stderr, "x-access-token:***" in completed.stdout),
            (False, True),
        )
    finally:
        sandbox.close()
    return


def test_dry_run_with_skip_system_setup_changes_nothing():
    """
    **Feature: deploy script (CLI-21)**
    **Property: the CI form (--skip-system-setup) dry-runs too: only the
    read-only probes run.**
    """
    sandbox = _DeploySandbox()
    try:
        completed = sandbox.run("--host", "app.example.test", "--user", "deploy", "--skip-system-setup", "--dry-run")
        testbase.assert_equal((completed.returncode, _changing_calls(sandbox.calls())), (0, []))
    finally:
        sandbox.close()
    return


# ===========================================================================
# The token follows pyproject.toml
# ===========================================================================


def test_token_is_required_while_pyproject_names_git_sources():
    """
    **Feature: deploy script (CLI-21)**
    **Property: with git-source dependencies and no
    CODECRAFTAI_REPO_TOKEN the script exits 2 before contacting the
    host.**
    """
    sandbox = _DeploySandbox(pyproject=PYPROJECT_WITH_GIT_SOURCES)
    try:
        completed = sandbox.run("--host", "h", "--user", "u", "--dry-run", token=None)
        testbase.assert_equal((completed.returncode, sandbox.calls()), (2, []))
    finally:
        sandbox.close()
    return


def test_no_token_is_needed_without_git_sources():
    """
    **Feature: deploy script (CLI-21)**
    **Property: when pyproject.toml resolves the packages from an index,
    the script needs no token and skips the git-credential step (the
    header's git-source story used to be required regardless).**
    """
    sandbox = _DeploySandbox(pyproject=PYPROJECT_WITH_AN_INDEX)
    try:
        completed = sandbox.run("--host", "h", "--user", "u", "--dry-run", token=None)
        testbase.assert_equal(
            (completed.returncode, "Step 3/8: SKIPPED" in completed.stdout), (0, True)
        )
    finally:
        sandbox.close()
    return
