"""
.. module:: test_p26e_makefile_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the service Makefile, development/select-tests and
               development/lint (audit findings CLI-15, CLI-16, CLI-19).

.. moduleauthor:: Code Craft AI LLC

* CLI-15 -- bare ``make`` ran ``rm -fr dist``; there was no help, test or
  lint target, and ``db-downgrade`` rolled back without asking.
* CLI-16 -- ``make dist-publish`` ran a bare ``poetry publish`` (public
  PyPI) for proprietary code.
* CLI-19 -- testbase's two silent traps (``--includes=...phase1`` also
  runs phase10-19; ``--excludes`` does nothing): ``make test`` /
  ``development/select-tests`` avoid them and ``development/lint`` flags
  them.

Nothing here may touch the checkout, a database, a package index or the
network -- including when the Makefile regresses to its old behaviour:
make runs from a temporary directory (``make -f <repo>/Makefile -C
<tmp>``, which links only the read-only inputs ``make test`` needs) with
a fake virtual environment whose ``alembic`` / ``poetry`` / ``testbase``
are stubs that log their arguments.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re
import shutil
import subprocess
import sys
import tempfile

from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ccai import testbase

from ccai.testshared.skip_helper import skip_test


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    root = here
    while not (root / "Makefile").is_file() or not (root / "development").is_dir():
        if root.parent == root:
            raise AssertionError("repository root not found above {}".format(here))
        root = root.parent
    return root


REPO_ROOT = _repo_root()
DEVELOPMENT = REPO_ROOT / "development"

# Variables a parent make (or a developer's shell) could pass to the make
# under test; each test sets what it needs explicitly.
MAKE_ENVIRONMENT_NOISE = (
    "MAKEFLAGS", "MFLAGS", "MAKELEVEL", "MAKEOVERRIDES",
    "SELECT", "EXCLUDE", "REPOSITORY", "CONFIRM", "TEST_OUTPUT", "VENV", "POETRY",
)

POETRY_STUB = r"""
printf 'poetry %s\n' "$*" >> "$STUB_LOG"
if [ "$1" = "config" ]; then
    name="${2#repositories.}"
    name="${name%.url}"
    url="$(awk -v n="$name" '$1 == n { print $2 }' "$STUB_REPOS")"
    if [ -z "$url" ]; then
        echo "There is no $name repository defined" >&2
        exit 1
    fi
    echo "$url"
fi
exit 0
"""

ALEMBIC_STUB = r"""
printf 'alembic %s\n' "$*" >> "$STUB_LOG"
exit 0
"""

TESTBASE_STUB = r"""
printf 'testbase %s\n' "$*" >> "$STUB_LOG"
if [ "$1" = "testing" ] && [ "$2" = "run" ]; then
    out=""
    for arg in "$@"; do
        case "$arg" in
            --output=*) out="${arg#--output=}" ;;
        esac
    done
    mkdir -p "$out"
    printf '{"result": "%s"}\n' "${STUB_RESULT:-PASSED}" > "$out/testrun_summary.json"
fi
exit 0
"""


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if path is None:
        skip_test(reason="'{}' is not installed".format(tool))
    return path


def _run(
        argv: List[str],
        *,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        unset: Sequence[str] = (),
        stdin: str = ""
    ) -> subprocess.CompletedProcess:
    merged = {name: value for name, value in os.environ.items() if name not in unset}
    merged.update(env or {})
    # Never the checkout: nothing run here should resolve paths from it.
    rtnval = subprocess.run(
        argv, cwd=cwd or tempfile.gettempdir(), env=merged, input=stdin,
        capture_output=True, text=True, timeout=120,
    )
    return rtnval


def _write_stub(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + body.lstrip("\n"), encoding="utf-8")
    os.chmod(str(path), 0o755)
    return


def _fake_repo(*scripts: str) -> Path:
    """
        A temporary directory shaped like the repository, holding copies of
        the named development scripts (they resolve the repository from
        their own location).
    """
    root = Path(tempfile.mkdtemp(prefix="pyc-devtools-"))
    (root / "development").mkdir()
    for script in scripts:
        shutil.copy2(str(DEVELOPMENT / script), str(root / "development" / script))
    return root


class _MakeSandbox:
    """
        Runs the repository Makefile from a temporary directory (which
        links only the read-only inputs 'make test' needs) with VENV
        pointing at a fake virtual environment whose tools are logging
        stubs, so no recipe can change the checkout.
    """

    def __init__(self, repositories: Optional[Dict[str, str]] = None):
        self.root = Path(tempfile.mkdtemp(prefix="pyc-make-"))
        self.workdir = self.root / "checkout"
        self.workdir.mkdir()
        for name in ("development", "source"):
            os.symlink(str(REPO_ROOT / name), str(self.workdir / name))
        self.venv = self.root / "venv"
        self.bin = self.venv / "bin"
        self.bin.mkdir(parents=True)
        self.log = self.root / "calls.log"
        self.repositories = self.root / "repositories.txt"
        self.repositories.write_text(
            "".join("{} {}\n".format(name, url) for name, url in (repositories or {}).items()),
            encoding="utf-8",
        )
        _write_stub(self.bin / "python", 'exec "{}" "$@"\n'.format(sys.executable))
        _write_stub(self.bin / "alembic", ALEMBIC_STUB)
        _write_stub(self.bin / "poetry", POETRY_STUB)
        _write_stub(self.bin / "testbase", TESTBASE_STUB)
        return

    def make(self, *args: str, env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
        make = _require("make")
        merged = {
            "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
            "STUB_LOG": str(self.log),
            "STUB_REPOS": str(self.repositories),
            "PYCHESTRATE_DATABASE_URL": "sqlite:///" + str(self.root / "db.sqlite"),
        }
        merged.update(env or {})
        argv = [
            make, "--no-print-directory", "-f", str(REPO_ROOT / "Makefile"), "-C", str(self.workdir),
            "VENV=" + str(self.venv), "POETRY=" + str(self.bin / "poetry"),
        ] + list(args)
        rtnval = _run(argv, cwd=str(self.workdir), env=merged, unset=MAKE_ENVIRONMENT_NOISE)
        return rtnval

    def calls(self, prefix: str = "") -> List[str]:
        if not self.log.exists():
            return []
        lines = self.log.read_text(encoding="utf-8").splitlines()
        rtnval = [line for line in lines if line.startswith(prefix)]
        return rtnval

    def close(self) -> None:
        shutil.rmtree(str(self.root), ignore_errors=True)
        return


# ===========================================================================
# CLI-15: help, targets, and db-downgrade
# ===========================================================================


def test_bare_make_prints_the_target_list():
    """
    **Feature: service Makefile (CLI-15)**
    **Property: 'make' with no target prints the target list (help is the
    default goal) and runs nothing -- it used to run 'rm -fr dist'.**
    """
    sandbox = _MakeSandbox()
    try:
        result = sandbox.make()
        testbase.assert_equal(
            (result.returncode, result.stdout.startswith("usage: make <target>"),
             "rm -fr" in result.stdout, sandbox.calls()),
            (0, True, False, []),
        )
    finally:
        sandbox.close()
    return


def test_help_lists_the_everyday_targets():
    """
    **Feature: service Makefile (CLI-15)**
    **Property: the help names setup, dev, test, lint and docs.**
    """
    sandbox = _MakeSandbox()
    try:
        output = sandbox.make("help").stdout
    finally:
        sandbox.close()
    listed = [line.split()[0] for line in output.splitlines() if line.startswith("  ")]
    testbase.assert_equal(
        [target for target in ("setup", "dev", "test", "lint", "docs") if target not in listed], []
    )
    return


def test_every_documented_target_is_phony():
    """
    **Feature: service Makefile (CLI-15)**
    **Property: every target with a '## ' description is declared .PHONY,
    so a file of the same name cannot shadow it.**
    """
    text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    phony_block = text.split(".PHONY:", 1)[1].split("\n\n", 1)[0].replace("\\\n", " ")
    phony = set(phony_block.split())
    documented = [
        match.group(1) for match in
        (re.match(r"^([a-zA-Z0-9_-]+):.*## ", line) for line in text.splitlines()) if match
    ]
    testbase.assert_equal((len(documented) > 10, [t for t in documented if t not in phony]), (True, []))
    return


def test_db_downgrade_without_confirm_rolls_nothing_back():
    """
    **Feature: service Makefile (CLI-15)**
    **Property: 'make db-downgrade' without CONFIRM=1 exits non-zero,
    asks for CONFIRM=1, and never invokes 'alembic downgrade'.**
    """
    sandbox = _MakeSandbox()
    try:
        result = sandbox.make("db-downgrade")
        testbase.assert_equal(
            (result.returncode != 0, "CONFIRM=1" in result.stderr,
             [call for call in sandbox.calls("alembic") if "downgrade" in call]),
            (True, True, []),
        )
    finally:
        sandbox.close()
    return


def test_db_downgrade_with_confirm_rolls_back_one_revision():
    """
    **Feature: service Makefile (CLI-15)**
    **Property: with CONFIRM=1 the target runs the venv's alembic
    'downgrade -1' once.**
    """
    sandbox = _MakeSandbox()
    try:
        result = sandbox.make("db-downgrade", "CONFIRM=1")
        testbase.assert_equal(
            (result.returncode, sandbox.calls("alembic")),
            (0, ["alembic -c alembic.ini downgrade -1"]),
        )
    finally:
        sandbox.close()
    return


# ===========================================================================
# CLI-16: dist-publish
# ===========================================================================


PRIVATE_INDEX = "https://pkgs.example.invalid/pypi/"


def _publish_attempt(*args: str, repositories: Optional[Dict[str, str]] = None):
    sandbox = _MakeSandbox(repositories=repositories)
    try:
        result = sandbox.make("dist-publish", *args)
        uploads = sandbox.calls("poetry publish")
    finally:
        sandbox.close()
    return result, uploads


def test_dist_publish_without_a_repository_uploads_nothing():
    """
    **Feature: service Makefile (CLI-16)**
    **Property: 'make dist-publish' without REPOSITORY exits non-zero,
    says why (a bare 'poetry publish' goes to public PyPI), and never
    runs 'poetry publish'.**
    """
    result, uploads = _publish_attempt()
    testbase.assert_equal(
        (result.returncode != 0, "public PyPI" in result.stderr, uploads), (True, True, [])
    )
    return


def test_dist_publish_refuses_the_public_index_by_name():
    """
    **Feature: service Makefile (CLI-16)**
    **Property: REPOSITORY=pypi is refused even with CONFIRM=1.**
    """
    result, uploads = _publish_attempt("REPOSITORY=pypi", "CONFIRM=1", repositories={"pypi": PRIVATE_INDEX})
    testbase.assert_equal(
        (result.returncode != 0, "refusing to publish to the public index" in result.stderr, uploads),
        (True, True, []),
    )
    return


def test_dist_publish_refuses_a_repository_that_points_at_pypi():
    """
    **Feature: service Makefile (CLI-16)**
    **Property: a repository whose URL is on pypi.org is refused even with
    CONFIRM=1.**
    """
    result, uploads = _publish_attempt(
        "REPOSITORY=mirror", "CONFIRM=1", repositories={"mirror": "https://upload.pypi.org/legacy/"}
    )
    testbase.assert_equal(
        (result.returncode != 0, "points at public PyPI" in result.stderr, uploads), (True, True, [])
    )
    return


def test_dist_publish_refuses_an_unknown_repository():
    """
    **Feature: service Makefile (CLI-16)**
    **Property: a REPOSITORY that poetry does not know is refused before
    anything is uploaded.**
    """
    result, uploads = _publish_attempt("REPOSITORY=nosuch", "CONFIRM=1", repositories={"private": PRIVATE_INDEX})
    testbase.assert_equal(
        (result.returncode != 0, "no repository named 'nosuch'" in result.stderr, uploads),
        (True, True, []),
    )
    return


def test_dist_publish_without_confirm_uploads_nothing():
    """
    **Feature: service Makefile (CLI-16)**
    **Property: with a private repository but no CONFIRM=1 the target says
    what it would upload where, exits non-zero, and uploads nothing.**
    """
    result, uploads = _publish_attempt("REPOSITORY=private", repositories={"private": PRIVATE_INDEX})
    testbase.assert_equal(
        (result.returncode != 0,
         "would upload dist/* to 'private' ({})".format(PRIVATE_INDEX) in result.stderr, uploads),
        (True, True, []),
    )
    return


def test_dist_publish_with_confirm_uploads_to_the_named_repository():
    """
    **Feature: service Makefile (CLI-16)**
    **Property: REPOSITORY=<private> CONFIRM=1 runs exactly
    'poetry publish --repository <private>'.**
    """
    result, uploads = _publish_attempt("REPOSITORY=private", "CONFIRM=1", repositories={"private": PRIVATE_INDEX})
    testbase.assert_equal((result.returncode, uploads), (0, ["poetry publish --repository private"]))
    return


# ===========================================================================
# CLI-19: make test, development/select-tests, development/lint
# ===========================================================================


def _select(*args: str) -> List[str]:
    result = _run([sys.executable, str(DEVELOPMENT / "select-tests")] + list(args))
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    rtnval = [line[len("--includes="):] for line in result.stdout.splitlines()]
    return rtnval


def test_selecting_phase1_does_not_select_phase10():
    """
    **Feature: make test (CLI-19)**
    **Property: selecting phase1 yields only phase1 modules (testbase's
    own --includes=...phase1 also runs phase10-phase19).**
    """
    modules = _select("--select", "phase1")
    testbase.assert_equal((len(modules) > 0, [m for m in modules if ".webservice.phase1." not in m]), (True, []))
    return


def test_excluded_modules_are_left_out():
    """
    **Feature: make test (CLI-19)**
    **Property: --exclude removes the modules (testbase's own --excludes is
    a no-op).**
    """
    modules = _select("--exclude", "phase11", "--exclude", "phase12")
    testbase.assert_equal(
        (len(modules) > 100, [m for m in modules if ".phase11." in m or ".phase12." in m]), (True, [])
    )
    return


def test_no_selection_is_the_whole_suite_as_one_include():
    """
    **Feature: make test (CLI-19)**
    **Property: with no selection the whole single-host suite is one safe
    include.**
    """
    testbase.assert_equal(_select(), ["ccai.tests.singlehost"])
    return


def test_make_test_passes_exact_includes_to_testbase():
    """
    **Feature: make test (CLI-19)**
    **Property: 'make test SELECT=phase1' runs the venv's testbase with one
    --includes per phase1 module and nothing from phase10-19, and exits 0
    when the run passes.**
    """
    sandbox = _MakeSandbox()
    try:
        result = sandbox.make("test", "SELECT=phase1", "TEST_OUTPUT=" + str(sandbox.root / "out"))
        runs = sandbox.calls("testbase testing run")
    finally:
        sandbox.close()
    includes = [token for token in (runs[0].split() if runs else []) if token.startswith("--includes=")]
    testbase.assert_equal(
        (result.returncode, len(runs), len(includes) > 0,
         [token for token in includes if ".webservice.phase1." not in token]),
        (0, 1, True, []),
    )
    return


def test_make_test_fails_when_the_run_fails():
    """
    **Feature: make test (CLI-19)**
    **Property: when the run's summary is not PASSED, 'make test' exits
    non-zero.**
    """
    sandbox = _MakeSandbox()
    try:
        result = sandbox.make(
            "test", "SELECT=phase1", "TEST_OUTPUT=" + str(sandbox.root / "out"), env={"STUB_RESULT": "FAILED"}
        )
    finally:
        sandbox.close()
    testbase.assert_equal((result.returncode != 0, "make test: FAILED" in result.stderr), (True, True))
    return


def test_make_test_rejects_an_unknown_selector():
    """
    **Feature: make test (CLI-19)**
    **Property: a SELECT that matches nothing fails before testbase runs
    (instead of silently running zero tests).**
    """
    sandbox = _MakeSandbox()
    try:
        result = sandbox.make("test", "SELECT=phase_does_not_exist", "TEST_OUTPUT=" + str(sandbox.root / "out"))
        runs = sandbox.calls("testbase")
    finally:
        sandbox.close()
    testbase.assert_equal((result.returncode != 0, runs), (True, []))
    return


def _lint_sample(command: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        sample = os.path.join(tmp, "sample.mk")
        with open(sample, "w", encoding="utf-8") as fh:
            fh.write("run:\n\ttestbase testing run --root source/testroots/ccai \\\n\t  " + command + "\n")
        rtnval = _run([sys.executable, str(DEVELOPMENT / "lint"), "--no-syntax", "--traps", sample])
    return rtnval


def test_lint_flags_an_include_that_prefixes_sibling_packages():
    """
    **Feature: make lint (CLI-19)**
    **Property: development/lint reports --includes=...phase1 because it
    also runs phase10-phase19.**
    """
    result = _lint_sample("--includes=ccai.tests.singlehost.pychestrate.webservice.phase1")
    testbase.assert_equal((result.returncode, "also runs phase10" in result.stdout), (1, True))
    return


def test_lint_flags_excludes():
    """
    **Feature: make lint (CLI-19)**
    **Property: development/lint reports --excludes because testbase
    ignores it.**
    """
    result = _lint_sample(
        "--includes=ccai.tests.singlehost --excludes=ccai.tests.singlehost.pychestrate.webservice.phase11"
    )
    testbase.assert_equal((result.returncode, "ignored by testbase" in result.stdout), (1, True))
    return


def test_lint_accepts_module_includes():
    """
    **Feature: make lint (CLI-19)**
    **Property: a command that lists an exact module include is not
    reported.**
    """
    result = _lint_sample(
        "--includes=ccai.tests.singlehost.pychestrate.webservice.phase10.test_p26e_makefile_m1"
    )
    testbase.assert_equal((result.returncode, result.stdout.strip()), (0, "lint: ok"))
    return


def test_repository_test_commands_avoid_the_traps():
    """
    **Feature: make lint (CLI-19)**
    **Property: the CI workflows, the Makefile, AGENTS.md and the user
    guide contain no testbase command that falls into either trap.**
    """
    result = _run([sys.executable, str(DEVELOPMENT / "lint"), "--no-syntax"])
    testbase.assert_equal((result.returncode, result.stdout.strip()), (0, "lint: ok"))
    return


def test_lint_reports_python_syntax_errors():
    """
    **Feature: make lint (CLI-15)**
    **Property: the syntax check names a Python file that does not parse.**
    """
    root = _fake_repo("lint")
    try:
        (root / "source").mkdir()
        (root / "source" / "broken.py").write_text("def broken(:\n", encoding="utf-8")
        result = _run([sys.executable, str(root / "development" / "lint"), "--traps"], cwd=str(root))
    finally:
        shutil.rmtree(str(root), ignore_errors=True)
    testbase.assert_equal(
        (result.returncode, result.stdout.startswith("source/broken.py:1: syntax error")), (1, True)
    )
    return



def test_selection_and_lint_tools_answer_help():
    """
    **Feature: make test / make lint (CLI-19)**
    **Property: select-tests and lint answer --help with exit 0 and a
    usage line.**
    """
    outcomes = {}
    for script in ("select-tests", "lint"):
        result = _run([sys.executable, str(DEVELOPMENT / script), "--help"])
        outcomes[script] = (result.returncode, "usage:" in result.stdout)
    testbase.assert_equal(outcomes, {name: (0, True) for name in outcomes})
    return
