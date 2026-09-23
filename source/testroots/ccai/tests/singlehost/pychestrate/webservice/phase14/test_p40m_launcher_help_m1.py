"""
.. module:: test_p40m_launcher_help_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests that the local launchers and rehome-repository answer
               --help without side effects, and that dev-up says where to go.

.. moduleauthor:: Code Craft AI LLC

Audit finding CLI-17. ``dev-up --help`` would have booted the server,
``run-staging-gunicorn --help`` was an unknown-argument error, and
``rehome-repository`` ran (and printed from) its Python check before
parsing its arguments. ``dev-up`` also never printed the URL to open.

Every script runs as a copy inside a throw-away directory shaped like the
repository, so nothing touches the checkout or the home directory.

**Feature: development scripts (CLI-17)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import shutil
import subprocess
import sys
import tempfile

from pathlib import Path
from typing import List, Tuple

from ccai import testbase


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "development" / "dev-up").is_file():
            return parent
    raise RuntimeError("repository root not found above {}".format(here))


REPO_ROOT = _repo_root()


def _fake_repo(*relative_paths: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix="pyc-launchers-"))
    for relative in relative_paths:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(REPO_ROOT / relative), str(target))
    return root


def _run(root: Path, argv: List[str]) -> Tuple[int, str, str, bool]:
    """
        Run ``argv`` (a script path relative to ``root`` first) with a
        throw-away HOME; returns (exit code, stdout, stderr, whether .cache
        was created).
    """
    home = tempfile.mkdtemp(prefix="pyc-launchers-home-")
    env = dict(os.environ)
    env["HOME"] = home
    env.pop("PYCHESTRATE_RUNTIME_ENVIRONMENT", None)
    command = list(argv)
    command[0] = str(root / command[0])
    if command[0].endswith("rehome-repository"):
        command.insert(0, sys.executable)
    proc = subprocess.run(command, cwd=str(root), env=env, capture_output=True, text=True, timeout=60)
    rtnval = (proc.returncode, proc.stdout, proc.stderr, (root / ".cache").exists())
    shutil.rmtree(home, ignore_errors=True)
    return rtnval


def test_dev_up_help_prints_usage_and_starts_nothing():
    """
    **Feature: development scripts (CLI-17)**
    **Property: dev-up --help prints its usage, exits 0, and creates no
    secrets, database or cache.**
    """
    root = _fake_repo("development/dev-up")
    try:
        code, out, _, cache = _run(root, ["development/dev-up", "--help"])
    finally:
        shutil.rmtree(str(root), ignore_errors=True)
    testbase.assert_equal((code, out.startswith("usage: development/dev-up"), cache), (0, True, False))
    return


def test_dev_up_refuses_an_unknown_argument_before_acting():
    """
    **Feature: development scripts (CLI-17)**
    **Property: an unknown argument is refused with exit 2 before anything
    is created.**
    """
    root = _fake_repo("development/dev-up")
    try:
        code, _, err, cache = _run(root, ["development/dev-up", "--port=9000"])
    finally:
        shutil.rmtree(str(root), ignore_errors=True)
    testbase.assert_equal((code, "unknown argument: --port=9000" in err, cache), (2, True, False))
    return


def test_dev_up_prints_the_url_and_the_setup_token_path_before_starting():
    """
    **Feature: development scripts (CLI-17)**
    **Property: dev-up announces the URL to open and where the setup
    wizard's token is before it starts the server.**
    """
    lines = (REPO_ROOT / "development" / "dev-up").read_text(encoding="utf-8").splitlines()
    url_line = next((i for i, line in enumerate(lines) if 'echo "dev-up: open http://' in line), None)
    token_line = next((i for i, line in enumerate(lines) if "initial-admin-token\"" in line and "echo" in line), None)
    start_line = next((i for i, line in enumerate(lines) if line.startswith("exec ")), None)
    testbase.assert_equal(
        (url_line is not None and token_line is not None and start_line is not None,
         url_line is not None and start_line is not None and url_line < start_line,
         token_line is not None and start_line is not None and token_line < start_line),
        (True, True, True),
    )
    return


def test_run_staging_gunicorn_help_prints_usage_and_generates_nothing():
    """
    **Feature: development scripts (CLI-17)**
    **Property: run-staging-gunicorn --help prints its usage, exits 0, and
    generates no secrets.**
    """
    root = _fake_repo("development/run-staging-gunicorn")
    try:
        code, out, _, cache = _run(root, ["development/run-staging-gunicorn", "--help"])
    finally:
        shutil.rmtree(str(root), ignore_errors=True)
    testbase.assert_equal(
        (code, out.startswith("usage: development/run-staging-gunicorn"), "--provision-only" in out, cache),
        (0, True, True, False),
    )
    return


def test_rehome_repository_help_has_no_side_effects():
    """
    **Feature: development scripts (CLI-17)**
    **Property: rehome-repository --help prints only its usage (no stray
    output from the Python check), exits 0, and creates no .cache.**
    """
    root = _fake_repo("repository-setup/rehome-repository")
    try:
        code, out, _, cache = _run(root, ["repository-setup/rehome-repository", "--help"])
    finally:
        shutil.rmtree(str(root), ignore_errors=True)
    testbase.assert_equal(
        (code, out.startswith("usage: rehome-repository"), "test" in out.split(), cache), (0, True, False, False),
    )
    return
