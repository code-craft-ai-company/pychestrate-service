"""
.. module:: test_p26f_development_scripts_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the development scripts (audit finding CLI-17).

.. moduleauthor:: Code Craft AI LLC

The scripts ignored ``--help``, made changes before validating their
input, printed a literal ``$ENV_FILE``, appended to
``.venv/bin/activate`` on every run, ran an unpinned esbuild and
discarded its errors, and stored ``$GITHUB_TOKEN`` in
``~/.git-credentials`` with a global 'store' helper.

Nothing here may touch the checkout, the user's HOME or git
configuration, a database or the network -- including when a script
regresses to its old behaviour (the old ``codex-container-setup``
ignored ``--help`` and rewrote the global git configuration):

* every script that is executed runs as a copy inside a temporary
  directory, with stub tools first on ``PATH`` and, for anything that
  may call git, a throw-away ``HOME`` and ``GIT_CONFIG_GLOBAL``;
* ``setup-environment``, ``seed-test-admin.sh`` and ``run-website.sh``
  are never executed: they are checked statically, or (for
  ``setup-environment``'s helpers) loaded from a copy without running
  its main.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import ast
import contextlib
import io
import os
import re
import shutil
import subprocess
import tempfile
import types

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

GIT_ENVIRONMENT_NOISE = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
    "GIT_ASKPASS", "SSH_ASKPASS",
)

NPX_STUB = r"""
printf 'npx %s\n' "$*" >> "$STUB_LOG"
echo 'X [ERROR] stub-esbuild: Could not resolve "./missing.js"' >&2
exit 1
"""

PYTHON3_STUB = r"""
cat > /dev/null
printf '%s\n' "$STUB_MJ_INDEX"
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


# ===========================================================================
# CLI-17: setup-environment (checked in-process; never executed)
# ===========================================================================


def _load_setup_environment() -> types.ModuleType:
    """
        The script's definitions, without running its main (it is guarded
        by ``if __name__ == "__main__"``) and without writing bytecode.
        The code is loaded from a copy in an empty temporary repository, so
        even a regression that ran main at import could only reach that
        copy (where it stops: there is no repository-setup/ or .env).
    """
    root = _fake_repo("setup-environment")
    try:
        path = root / "development" / "setup-environment"
        module = types.ModuleType("setup_environment_under_test")
        module.__file__ = str(path)
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
    finally:
        shutil.rmtree(str(root), ignore_errors=True)
    return module


def _parse_arguments_outcome(argv: List[str]):
    module = _load_setup_environment()
    out = io.StringIO()
    err = io.StringIO()
    code = None
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            module.parse_arguments(argv)
        except SystemExit as xcpt:
            code = xcpt.code
    return code, out.getvalue(), err.getvalue()


def test_setup_environment_answers_help():
    """
    **Feature: development scripts (CLI-17)**
    **Property: setup-environment's argument parsing answers --help with
    the usage and exit status 0.**
    """
    code, out, _err = _parse_arguments_outcome(["--help"])
    testbase.assert_equal((code, out.startswith("usage: development/setup-environment")), (0, True))
    return


def test_setup_environment_rejects_unknown_arguments():
    """
    **Feature: development scripts (CLI-17)**
    **Property: an unknown argument exits 2 with a message (it used to be
    ignored and the script went on to change the checkout).**
    """
    code, _out, err = _parse_arguments_outcome(["bogus"])
    testbase.assert_equal((code, "unknown argument 'bogus'" in err), (2, True))
    return


def test_setup_environment_validates_before_creating_anything():
    """
    **Feature: development scripts (CLI-17)**
    **Property: in setup_environment_main, parsing the arguments and every
    input check (repository config, .env, PYTHON_VERSION, custom CLI) come
    before the first directory is created.**
    """
    text = (DEVELOPMENT / "setup-environment").read_text(encoding="utf-8")
    tree = ast.parse(text)
    main = next(
        (node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "setup_environment_main"),
        None,
    )
    markers = (
        "Repository config file not found",
        "Development environment file not found",
        "'PYTHON_VERSION' variable should be set",
    )
    first_line: Dict[str, int] = {}
    for node in ast.walk(main) if main is not None else []:
        keys = []
        if isinstance(node, ast.Call):
            keys.append(ast.unparse(node.func))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            keys.extend(marker for marker in markers if marker in node.value)
        for key in keys:
            first_line[key] = min(node.lineno, first_line.get(key, node.lineno))
    created = first_line.get("os.makedirs")
    checks = ("parse_arguments",) + markers + ("validate_custom_cli",)
    testbase.assert_equal(
        {check: created is not None and first_line.get(check, created) < created for check in checks},
        {check: True for check in checks},
    )
    return


def test_setup_environment_errors_show_real_paths():
    """
    **Feature: development scripts (CLI-17)**
    **Property: the 'location=' error lines interpolate the path (they used
    to print a literal 'location=$ENV_FILE').**
    """
    text = (DEVELOPMENT / "setup-environment").read_text(encoding="utf-8")
    testbase.assert_equal((text.count("location=$"), text.count("location={")), (0, 3))
    return


def _legacy_activate_edit(env_file: str, alias: str = "", script: str = "", venv_python: str = "") -> str:
    """What earlier versions appended to bin/activate on every run."""
    text = "\nif [ -f {0} ]\nthen\n    set -a\n    source {0}\n    set +a\nfi\n\n\n".format(env_file)
    if alias:
        text += "# Create an alias for the {0} command\nfunction {0}() {{\n    {1} {2} $@ \n}}\nexport -f {0}".format(
            alias, venv_python, script
        )
    return text


def test_activate_customization_is_idempotent():
    """
    **Feature: development scripts (CLI-17)**
    **Property: customizing the activate script repeatedly leaves one .env
    loader, and removes the unmarked copies older versions appended.**
    """
    module = _load_setup_environment()
    with tempfile.TemporaryDirectory() as tmp:
        activate = Path(tmp) / "activate"
        activate.write_text("# venv\n" + _legacy_activate_edit("/repo/.env") * 2, encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            for _attempt in range(3):
                module.customize_activation_script(str(activate), "/repo/.env", "", "")
        text = activate.read_text(encoding="utf-8")
    testbase.assert_equal(
        (text.startswith("# venv\n"), text.count("source /repo/.env"), text.count(module.CUSTOMIZATION_BEGIN)),
        (True, 1, 1),
    )
    return


def test_activate_customization_keeps_one_cli_alias():
    """
    **Feature: development scripts (CLI-17)**
    **Property: with a custom CLI configured, repeated runs leave exactly
    one alias function.**
    """
    module = _load_setup_environment()
    with tempfile.TemporaryDirectory() as tmp:
        activate = Path(tmp) / "activate"
        venv_python = os.path.join(tmp, module.PYTHON_CMD)
        legacy = _legacy_activate_edit("/repo/.env", "pyc", "/repo/cli.py", venv_python)
        activate.write_text("# venv\n" + legacy + legacy, encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            for _attempt in range(2):
                module.customize_activation_script(str(activate), "/repo/.env", "pyc", "/repo/cli.py")
        text = activate.read_text(encoding="utf-8")
    testbase.assert_equal((text.count("function pyc()"), text.count("source /repo/.env")), (1, 1))
    return


# ===========================================================================
# CLI-17: seed-test-admin.sh and run-website.sh (checked statically)
# ===========================================================================


def test_seed_test_admin_checks_arguments_before_creating_secrets():
    """
    **Feature: development scripts (CLI-17)**
    **Property: seed-test-admin.sh handles --help, rejects unknown
    arguments and requires a password before it creates the dev-secrets
    directory (it used to generate secrets first).**
    """
    text = (DEVELOPMENT / "seed-test-admin.sh").read_text(encoding="utf-8")
    first_secret = text.find('mkdir -p "${SECRETS_DIR}"')
    positions = {
        "help": text.find("-h|--help)"),
        "unknown argument": text.find("unknown argument"),
        "password": text.find("a password is required"),
    }
    testbase.assert_equal(
        {name: 0 <= position < first_secret for name, position in positions.items()},
        {name: True for name in positions},
    )
    return


def test_run_website_answers_help_before_starting_the_server():
    """
    **Feature: development scripts (CLI-17)**
    **Property: run-website.sh handles --help before the line that starts
    the server, and starts it with the repository's .venv interpreter.**
    """
    lines = (DEVELOPMENT / "run-website.sh").read_text(encoding="utf-8").splitlines()
    help_line = next((index for index, line in enumerate(lines) if "-h|--help)" in line), None)
    start_line = next((index for index, line in enumerate(lines) if line.startswith("exec ")), None)
    testbase.assert_equal(
        (help_line is not None and start_line is not None and help_line < start_line,
         any('".venv/bin/python"' in line for line in lines)),
        (True, True),
    )
    return


def test_changed_shell_scripts_parse():
    """
    **Feature: development scripts (CLI-17)**
    **Property: 'bash -n' (parse only, nothing runs) accepts every shell
    script this change edited.**
    """
    bash = _require("bash")
    outcomes = {
        script: _run([bash, "-n", str(DEVELOPMENT / script)]).returncode
        for script in ("build-frontend.sh", "codex-container-setup", "run-website.sh", "seed-test-admin.sh")
    }
    testbase.assert_equal(outcomes, {script: 0 for script in outcomes})
    return


# ===========================================================================
# CLI-17: build-frontend.sh (a copy, with stub npx / python3)
# ===========================================================================


class _FrontendSandbox:

    def __init__(self):
        self.root = _fake_repo("build-frontend.sh")
        self.stubs = self.root / "stubs"
        self.stubs.mkdir()
        self.log = self.root / "calls.log"
        self.mj_index = self.root / "mj" / "index.js"
        self.mj_index.parent.mkdir()
        self.mj_index.write_text("export {};\n", encoding="utf-8")
        _write_stub(self.stubs / "npx", NPX_STUB)
        _write_stub(self.stubs / "python3", PYTHON3_STUB)
        return

    def run(self, *args: str) -> subprocess.CompletedProcess:
        bash = _require("bash")
        env = {
            "PATH": str(self.stubs) + os.pathsep + os.environ.get("PATH", ""),
            "STUB_LOG": str(self.log),
            "STUB_MJ_INDEX": str(self.mj_index),
        }
        rtnval = _run(
            [bash, str(self.root / "development" / "build-frontend.sh")] + list(args),
            cwd=str(self.root), env=env, unset=("ESBUILD", "ESBUILD_VERSION", "VIRTUAL_ENV"),
        )
        return rtnval

    def calls(self) -> List[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def close(self) -> None:
        shutil.rmtree(str(self.root), ignore_errors=True)
        return


def test_build_frontend_runs_a_pinned_esbuild():
    """
    **Feature: development scripts (CLI-17)**
    **Property: build-frontend.sh asks npx for an exact esbuild version
    (it used to run whatever 'npx --yes esbuild' resolved to).**
    """
    sandbox = _FrontendSandbox()
    try:
        sandbox.run()
        calls = sandbox.calls()
    finally:
        sandbox.close()
    testbase.assert_equal(
        (len(calls), bool(calls) and re.match(r"^npx --yes esbuild@\d+\.\d+\.\d+ ", calls[0]) is not None),
        (1, True),
    )
    return


def test_build_frontend_shows_esbuild_errors_and_stops():
    """
    **Feature: development scripts (CLI-17)**
    **Property: when esbuild fails its error reaches the terminal and the
    build exits non-zero (the output used to go to /dev/null).**
    """
    sandbox = _FrontendSandbox()
    try:
        result = sandbox.run()
    finally:
        sandbox.close()
    testbase.assert_equal(
        (result.returncode != 0, "stub-esbuild: Could not resolve" in result.stdout + result.stderr),
        (True, True),
    )
    return


def test_build_frontend_help_builds_nothing():
    """
    **Feature: development scripts (CLI-17)**
    **Property: 'build-frontend.sh --help' prints the usage, exits 0, and
    never runs esbuild.**
    """
    sandbox = _FrontendSandbox()
    try:
        result = sandbox.run("--help")
        calls = sandbox.calls()
    finally:
        sandbox.close()
    testbase.assert_equal((result.returncode, "usage:" in result.stdout, calls), (0, True, []))
    return


# ===========================================================================
# CLI-17: codex-container-setup (a copy, with a throw-away HOME)
# ===========================================================================


class _CodexSandbox:

    TOKEN = "ghp_" + "Z" * 36

    def __init__(self):
        self.root = _fake_repo("codex-container-setup")
        self.home = self.root / "home"
        self.home.mkdir()
        self.gitconfig = self.home / ".gitconfig"
        return

    def environment(self, token: str) -> Dict[str, str]:
        rtnval = {
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "GIT_CONFIG_GLOBAL": str(self.gitconfig),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CEILING_DIRECTORIES": str(self.root.parent),
            "GITHUB_TOKEN": token,
        }
        return rtnval

    def run(self, token: str, *args: str) -> subprocess.CompletedProcess:
        bash = _require("bash")
        _require("git")
        rtnval = _run(
            [bash, str(self.root / "development" / "codex-container-setup")] + list(args),
            cwd=str(self.root), env=self.environment(token), unset=GIT_ENVIRONMENT_NOISE,
        )
        return rtnval

    def credential_fill(self, host: str) -> subprocess.CompletedProcess:
        git = _require("git")
        rtnval = _run(
            [git, "credential", "fill"], cwd=str(self.root), env=self.environment(self.TOKEN),
            unset=GIT_ENVIRONMENT_NOISE, stdin="protocol=https\nhost={}\n\n".format(host),
        )
        return rtnval

    def files_containing(self, needle: str) -> List[str]:
        return [
            str(path.relative_to(self.root)) for path in self.root.rglob("*")
            if path.is_file() and needle in path.read_text(encoding="utf-8", errors="ignore")
        ]

    def close(self) -> None:
        shutil.rmtree(str(self.root), ignore_errors=True)
        return


def test_codex_setup_never_writes_the_token_to_disk():
    """
    **Feature: development scripts (CLI-17)**
    **Property: after codex-container-setup no file contains $GITHUB_TOKEN
    and ~/.git-credentials does not exist (the token used to be stored
    there with a global 'store' helper).**
    """
    sandbox = _CodexSandbox()
    try:
        sandbox.run(sandbox.TOKEN)
        outcome = (sandbox.files_containing(sandbox.TOKEN), (sandbox.home / ".git-credentials").exists())
    finally:
        sandbox.close()
    testbase.assert_equal(outcome, ([], False))
    return


def test_codex_setup_helper_gives_git_the_token_for_github():
    """
    **Feature: development scripts (CLI-17)**
    **Property: the configured helper answers git's credential request for
    https://github.com with $GITHUB_TOKEN from the environment.**
    """
    sandbox = _CodexSandbox()
    try:
        sandbox.run(sandbox.TOKEN)
        answer = sandbox.credential_fill("github.com")
    finally:
        sandbox.close()
    testbase.assert_equal(
        (answer.returncode, "username=x-access-token" in answer.stdout, "password=" + sandbox.TOKEN in answer.stdout),
        (0, True, True),
    )
    return


def test_codex_setup_helper_is_scoped_to_github():
    """
    **Feature: development scripts (CLI-17)**
    **Property: the helper gives the token to no other host.**
    """
    sandbox = _CodexSandbox()
    try:
        sandbox.run(sandbox.TOKEN)
        answer = sandbox.credential_fill("git.example.invalid")
    finally:
        sandbox.close()
    testbase.assert_equal(sandbox.TOKEN in answer.stdout, False)
    return


def test_codex_setup_without_a_token_changes_nothing():
    """
    **Feature: development scripts (CLI-17)**
    **Property: with no GITHUB_TOKEN the script exits 1 before touching the
    git configuration.**
    """
    sandbox = _CodexSandbox()
    try:
        result = sandbox.run("")
        outcome = (result.returncode, sandbox.gitconfig.exists())
    finally:
        sandbox.close()
    testbase.assert_equal(outcome, (1, False))
    return


def test_codex_setup_help_changes_nothing():
    """
    **Feature: development scripts (CLI-17)**
    **Property: 'codex-container-setup --help' prints the usage and exits 0
    without touching the git configuration, even with a token set (it
    used to ignore --help and configure git).**
    """
    sandbox = _CodexSandbox()
    try:
        result = sandbox.run(sandbox.TOKEN, "--help")
        outcome = (result.returncode, "usage:" in result.stdout, sandbox.gitconfig.exists(),
                   (sandbox.home / ".git-credentials").exists())
    finally:
        sandbox.close()
    testbase.assert_equal(outcome, (0, True, False, False))
    return
