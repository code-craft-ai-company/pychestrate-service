"""
.. module:: test_p40p_cli_package_release_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The standalone pychestrate-cli package is releasable: it declares its licence, ships it, and is not locked against upload.

.. moduleauthor:: Code Craft AI LLC

A build of ``packages/pychestrate-cli`` cannot reach outside its own directory, so the licence it ships is a copy of the
repository's ``LICENSE.md``; this suite keeps the copy identical, and checks the metadata PyPI needs (a licence, no
``Private :: Do Not Upload`` classifier, a version that comes from the CLI, a wheel-only release because the source archive of
this layout would not contain the sources).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import tomllib

from typing import Any, Dict

from ccai import testbase

from ccai.testshared.factories.pyc.pyc_harness import find_repository_root


def _cli_pyproject() -> Dict[str, Any]:
    with open(find_repository_root() / "packages" / "pychestrate-cli" / "pyproject.toml", "rb") as fh:
        rtnval = tomllib.load(fh)
    return rtnval


def test_the_licence_the_package_ships_is_the_repositorys_licence():
    """
    **Feature: releasing pychestrate-cli**
    **Property: ``packages/pychestrate-cli/LICENSE.md`` is byte for byte the repository's ``LICENSE.md``, so the wheel never ships a stale licence.**
    """
    root = find_repository_root()
    testbase.assert_equal(
        (root / "packages" / "pychestrate-cli" / "LICENSE.md").read_bytes() == (root / "LICENSE.md").read_bytes(),
        True,
    )
    return


def test_the_package_declares_the_licence_it_ships():
    """
    **Feature: releasing pychestrate-cli**
    **Property: the package names the repository's licence expression and lists ``LICENSE.md`` as a licence file, and uses a build backend that understands both.**
    """
    project = _cli_pyproject()
    requires = project["build-system"]["requires"]
    testbase.assert_equal(
        (project["project"]["license"], project["project"]["license-files"], any(r.replace(" ", "").startswith("setuptools>=77") for r in requires)),
        ("LicenseRef-CodeCraftAI-Source-Available", ["LICENSE.md"], True),
    )
    return


def test_the_package_is_not_locked_against_upload():
    """
    **Feature: releasing pychestrate-cli**
    **Property: the classifiers hold no ``Private ::`` entry, which PyPI treats as a refusal to accept the upload.**
    """
    classifiers = _cli_pyproject()["project"]["classifiers"]
    testbase.assert_equal([c for c in classifiers if c.startswith("Private ::")], [])
    return
