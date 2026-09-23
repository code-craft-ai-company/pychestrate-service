"""
.. module:: test_p27t_pyc_vocabulary_m3
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: One vocabulary for ``pyc`` (audit finding CLI-20):
               plural REST nouns, the "server URL" spelling, XDG
               paths.

.. moduleauthor:: Code Craft AI LLC

The audit found pyc's own text teaching the singular ``project list``
while REST says ``/projects``, pyc and the pod client disagreeing on
``--server-url`` / ``--service-url``, and both keeping files in
home-directory dot folders (``~/.pychestrate``) shared with the
service's log. The pod client's half lives in the pychestrate-client
repository.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from pathlib import Path

from ccai import testbase

from ccai.pychestrate.cli import exit_codes
from ccai.testshared.factories.pyc.pyc_harness import (
    SERVER,
    TOKEN,
    PycFakeServer,
    PycSandbox,
    run_pyc,
)


def test_unknown_command_teaches_plural_rest_nouns():
    """
    **Feature: pyc vocabulary (CLI-20)**
    **Property: the unknown-command error gives 'pyc projects list' as
    the example, not the singular 'project list'.**
    """
    sandbox = PycSandbox()
    try:
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["bogus-noun", "list"])
        testbase.assert_equal(
            (rc, "'pyc projects list'" in err, "'project list'" in err),
            (exit_codes.EXIT_USAGE_ERROR, True, False),
        )
    finally:
        sandbox.close()
    return


def test_top_help_teaches_plural_rest_nouns():
    """
    **Feature: pyc vocabulary (CLI-20)**
    **Property: 'pyc --help' shows plural nouns and no 'project list'
    line of its own.**
    """
    sandbox = PycSandbox()
    try:
        _rc, out, _err = run_pyc(sandbox=sandbox, argv=["--help"])
        testbase.assert_equal(
            ("'pyc projects list'" in out, "  project list" in out), (True, False)
        )
    finally:
        sandbox.close()
    return


def test_singular_noun_still_reaches_the_plural_command():
    """
    **Feature: pyc vocabulary (CLI-20)**
    **Property: 'pyc project list' still runs 'projects list'.**
    """
    sandbox = PycSandbox()
    try:
        sandbox.log_in()
        server = PycFakeServer({("GET", "/api/v1/projects"): {"items": []}})
        rc, _out, _err = run_pyc(sandbox=sandbox, argv=["project", "list"], opener=server)
        testbase.assert_equal((rc, server.paths()[-1]), (exit_codes.EXIT_OK, "/api/v1/projects"))
    finally:
        sandbox.close()
    return


def test_client_spelling_of_the_server_url_points_at_pycs():
    """
    **Feature: pyc vocabulary (CLI-20)**
    **Property: 'pyc login --service-url URL' (the pod client's spelling)
    exits 2 suggesting '--server-url'.**
    """
    sandbox = PycSandbox()
    try:
        rc, _out, err = run_pyc(sandbox=sandbox, argv=["login", "--service-url", SERVER, "--with-token"],
                                stdin_text=TOKEN + "\n", opener=PycFakeServer())
        testbase.assert_equal(
            (rc, "did you mean '--server-url'?" in err), (exit_codes.EXIT_USAGE_ERROR, True)
        )
    finally:
        sandbox.close()
    return


def test_login_keeps_its_files_in_the_xdg_directories():
    """
    **Feature: pyc vocabulary (CLI-20)**
    **Property: after 'pyc login' the credentials are under
    $XDG_CONFIG_HOME/pychestrate and the command list under
    $XDG_CACHE_HOME/pychestrate, and nothing is written to ~/.pychestrate
    (the directory the service's log uses).**
    """
    sandbox = PycSandbox()
    try:
        me = {"login_name": "dana", "authentication": {"method": "api_token"}}
        document = {"openapi": "3.1.0", "info": {"version": "1"}, "paths": {}}
        server = PycFakeServer({("GET", "/api/v1/me"): me, ("GET", "/api/v1/_meta/openapi.json"): document})
        run_pyc(sandbox=sandbox, argv=["login", "--server-url", SERVER, "--with-token"],
                stdin_text=TOKEN + "\n", opener=server, environ={"PYC_OPENAPI_CACHE_DIR": ""})
        home = Path(sandbox.environ["HOME"])
        cached = list((Path(sandbox.environ["XDG_CACHE_HOME"]) / "pychestrate" / "openapi").glob("*.json"))
        testbase.assert_equal(
            (sandbox.credentials_path.is_file(), len(cached), (home / ".pychestrate").exists()),
            (True, 1, False),
        )
    finally:
        sandbox.close()
    return
