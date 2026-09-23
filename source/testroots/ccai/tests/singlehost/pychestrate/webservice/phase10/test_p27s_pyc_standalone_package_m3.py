"""
.. module:: test_p27s_pyc_standalone_package_m3
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``pyc`` as its own standard-library-only package, with
               one version source and ``pyc version`` (audit finding
               CLI-11).

.. moduleauthor:: Code Craft AI LLC

The audit found ``pyc --version`` failed under a plain Python on the
private ``ccai.errors`` package (the CLI imported service modules),
three different version strings (0.1.0, ``__version__`` 1.0.0, a
``pyc-cli/1.0`` User-Agent), no way to learn the server's version, and
no way to install the CLI on its own.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import shutil
import subprocess
import sys
import tempfile
import tomllib

from pathlib import Path
from typing import Any, Dict

from ccai import testbase

from ccai.pychestrate.cli import exit_codes, version
from ccai.pychestrate.webservice.api import openapi_document
from ccai.testshared.factories.pyc.pyc_harness import (
    PycFakeServer,
    PycSandbox,
    find_repository_root,
    run_pyc,
)


#: Runs in a Python started with -I -S (no site-packages, no
#: PYTHONPATH): only the standard library and a copy of the CLI
#: package are importable.
_STANDALONE_PROBE = r"""
import io, json, sys
sys.path.insert(0, sys.argv[1])
from ccai.pychestrate.cli import entry
from ccai.pychestrate.cli.extensions.cli_subcommand import CLISubcommandExtension
codes = {}
for name, argv in (("version", ["--version"]), ("help", ["--help"]),
                   ("api-help", ["help", "projects", "list"]), ("ext-help", ["ext", "example", "--help"])):
    out, err = io.StringIO(), io.StringIO()
    codes[name] = entry.main(argv=argv, stdout=out, stderr=err, environ={"HOME": sys.argv[2],
                             "XDG_CONFIG_HOME": sys.argv[2], "XDG_CACHE_HOME": sys.argv[2]})
foreign = sorted(name for name in sys.modules
                 if name.startswith("ccai.") and name not in ("ccai.pychestrate",)
                 and not name.startswith("ccai.pychestrate.cli"))
print(json.dumps({"codes": codes, "foreign": foreign,
                  "extension_base": CLISubcommandExtension.__bases__[0].__module__}))
"""


def _run_standalone_probe() -> Dict[str, Any]:
    """
        Copy the CLI package alone into a temporary tree and run
        :data:`_STANDALONE_PROBE` against it in an isolated Python.

        :returns: The probe's report.
    """
    cli_source = find_repository_root() / "source" / "site" / "ccai" / "pychestrate" / "cli"
    with tempfile.TemporaryDirectory(prefix="pyc-standalone-") as tmp:
        target = Path(tmp) / "site" / "ccai" / "pychestrate" / "cli"
        shutil.copytree(cli_source, target, ignore=shutil.ignore_patterns("__pycache__"))
        home = Path(tmp) / "home"
        home.mkdir()
        completed = subprocess.run(
            [sys.executable, "-I", "-S", "-B", "-c", _STANDALONE_PROBE, str(Path(tmp) / "site"), str(home)],
            capture_output=True, text=True, timeout=120,
        )
    if completed.returncode != 0:
        raise AssertionError("standalone probe failed:\n{}".format(completed.stderr))
    rtnval = json.loads(completed.stdout.strip().splitlines()[-1])
    return rtnval


def _standalone_pyproject() -> Dict[str, Any]:
    path = find_repository_root() / "packages" / "pychestrate-cli" / "pyproject.toml"
    with open(path, "rb") as fh:
        rtnval = tomllib.load(fh)
    return rtnval


# ===========================================================================
# Standard library only
# ===========================================================================


def test_cli_runs_with_only_the_standard_library():
    """
    **Feature: standalone pyc (CLI-11)**
    **Property: the CLI package alone, under a Python with no
    site-packages, answers --version, --help, API help and extension
    help with exit 0 (it used to fail importing ccai.errors).**
    """
    report = _run_standalone_probe()
    testbase.assert_equal(report["codes"], {"version": 0, "help": 0, "api-help": 0, "ext-help": 0})
    return


def test_cli_imports_no_service_module():
    """
    **Feature: standalone pyc (CLI-11)**
    **Property: running the CLI imports no ccai module outside
    ccai.pychestrate.cli (no webservice, webworks, errors ...).**
    """
    report = _run_standalone_probe()
    testbase.assert_equal(report["foreign"], [])
    return


def test_standalone_extension_base_needs_no_service():
    """
    **Feature: standalone pyc (CLI-11)**
    **Property: without the service installed, CLISubcommandExtension
    derives from the CLI's own stand-in base.**
    """
    report = _run_standalone_probe()
    testbase.assert_equal(report["extension_base"], "ccai.pychestrate.cli.extensions.cli_subcommand")
    return


# ===========================================================================
# Packaging
# ===========================================================================


def test_standalone_package_installs_the_pyc_command():
    """
    **Feature: standalone pyc (CLI-11)**
    **Property: packages/pychestrate-cli declares the 'pyc' console
    script (entry:console_main) and no dependencies.**
    """
    project = _standalone_pyproject()["project"]
    testbase.assert_equal(
        (project["name"], project["scripts"], project["dependencies"]),
        ("pychestrate-cli", {"pyc": "ccai.pychestrate.cli.entry:console_main"}, []),
    )
    return


def test_standalone_package_takes_its_version_from_the_cli():
    """
    **Feature: standalone pyc (CLI-11)**
    **Property: the package's version is read from
    ccai.pychestrate.cli.version.PYC_VERSION (one version source).**
    """
    pyproject = _standalone_pyproject()
    testbase.assert_equal(
        (pyproject["project"]["dynamic"], pyproject["tool"]["setuptools"]["dynamic"]["version"]),
        (["version"], {"attr": "ccai.pychestrate.cli.version.PYC_VERSION"}),
    )
    return


def test_standalone_package_contains_exactly_the_cli():
    """
    **Feature: standalone pyc (CLI-11)**
    **Property: the package finds its sources in source/site and
    includes only ccai.pychestrate.cli and its subpackages.**
    """
    setuptools_config = _standalone_pyproject()["tool"]["setuptools"]
    where = (find_repository_root() / "packages" / "pychestrate-cli" / setuptools_config["packages"]["find"]["where"][0])
    testbase.assert_equal(
        ((where.resolve() / "ccai" / "pychestrate" / "cli" / "entry.py").is_file(),
         setuptools_config["packages"]["find"]["include"]),
        (True, ["ccai.pychestrate.cli", "ccai.pychestrate.cli.*"]),
    )
    return


# ===========================================================================
# One version, and the server's
# ===========================================================================


def test_version_banner_is_the_cli_version():
    """
    **Feature: pyc version (CLI-11)**
    **Property: 'pyc --version' prints PYC_VERSION.**
    """
    sandbox = PycSandbox()
    try:
        rc, out, _err = run_pyc(sandbox=sandbox, argv=["--version"])
        testbase.assert_equal((rc, out), (exit_codes.EXIT_OK, "pyc {}\n".format(version.PYC_VERSION)))
    finally:
        sandbox.close()
    return


def test_user_agent_names_the_cli_version():
    """
    **Feature: pyc version (CLI-11)**
    **Property: requests send 'User-Agent: pyc/<PYC_VERSION> ...' (it
    was 'pyc-cli/1.0' whatever the version).**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer({("GET", "/api/v1/me"): {"login_name": "dana"}})
        run_pyc(sandbox=sandbox, argv=["whoami"], opener=server)
        testbase.assert_equal(
            server.requests[-1]["headers"]["user-agent"].startswith("pyc/{} ".format(version.PYC_VERSION)), True
        )
    finally:
        sandbox.close()
    return


def _document_with_versions() -> Dict[str, Any]:
    rtnval = {
        "openapi": "3.1.0",
        "info": {"title": "Pychestrate", "version": "0.0.16-preview", "x-service-version": "0.0.7-preview"},
        "paths": {},
    }
    return rtnval


def test_version_command_reports_pyc_service_and_api_versions():
    """
    **Feature: pyc version (CLI-11)**
    **Property: 'pyc version' prints pyc's version, the server URL, the
    service version and the API version read from the server.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer({("GET", "/api/v1/_meta/openapi.json"): _document_with_versions()})
        rc, out, _err = run_pyc(sandbox=sandbox, argv=["version"], opener=server)
        lines = [line.split() for line in out.splitlines()]
        testbase.assert_equal(
            (rc, lines[0][:2], lines[2], lines[3]),
            (exit_codes.EXIT_OK, ["pyc", version.PYC_VERSION], ["service", "0.0.7-preview"],
             ["api", "0.0.16-preview"]),
        )
    finally:
        sandbox.close()
    return


def test_version_command_prints_json_on_request():
    """
    **Feature: pyc version (CLI-11)**
    **Property: 'pyc version -o json' prints the versions as one object.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer({("GET", "/api/v1/_meta/openapi.json"): _document_with_versions()})
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["version", "-o", "json"], opener=server)
        report = json.loads(out)
        testbase.assert_equal(
            (report["pyc"], report["service_version"], report["api_version"]),
            (version.PYC_VERSION, "0.0.7-preview", "0.0.16-preview"),
        )
    finally:
        sandbox.close()
    return


def test_version_command_without_a_server_reports_pyc_alone():
    """
    **Feature: pyc version (CLI-11)**
    **Property: with nothing configured, 'pyc version' prints pyc's
    version, notes that no server is configured, and exits 0.**
    """
    sandbox = PycSandbox()
    try:
        rc, out, err = run_pyc(sandbox=sandbox, argv=["version"], opener=PycFakeServer())
        testbase.assert_equal(
            (rc, out.startswith("pyc      {}".format(version.PYC_VERSION)), "no server is configured" in err),
            (exit_codes.EXIT_OK, True, True),
        )
    finally:
        sandbox.close()
    return


def test_served_openapi_document_names_the_service_version():
    """
    **Feature: pyc version (CLI-11)**
    **Property: the document served at /api/v1/_meta/openapi.json names
    the service's pyproject version as info.x-service-version.**
    """
    openapi_document.reset_cache_for_testing()
    try:
        document = openapi_document.load_served_document()
        expected = openapi_document.read_service_version(pyproject_path=find_repository_root() / "pyproject.toml")
        testbase.assert_equal(
            (document["info"].get("x-service-version"), expected is not None), (expected, True)
        )
    finally:
        openapi_document.reset_cache_for_testing()
    return


def test_service_version_is_read_from_the_poetry_section_only():
    """
    **Feature: pyc version (CLI-11)**
    **Property: read_service_version takes [tool.poetry] version, not a
    'version' key of another section.**
    """
    with tempfile.TemporaryDirectory() as tmp:
        pyproject = Path(tmp) / "pyproject.toml"
        pyproject.write_text(
            '[tool.other]\nversion = "9.9.9"\n\n[tool.poetry]\nname = "svc"\nversion = "1.2.3-preview"\n',
            encoding="utf-8",
        )
        testbase.assert_equal(openapi_document.read_service_version(pyproject_path=pyproject), "1.2.3-preview")
    return
