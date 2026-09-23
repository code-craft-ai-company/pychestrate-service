"""
Sphinx configuration for the Pychestrate plugin-catalog site.

The docs site renders the externally-stable plugin API surface
catalog into per-entry pages. Pages are emitted at build time by the
``ccai.pychestrate.webservice.extension.docs_ext`` Sphinx extension.

Run ``make -C docs html`` from the repository root to build.

The release number is read from ``pyproject.toml`` so the package, the
built documentation, and the CHANGELOG / git tag cut from the same
commit all name the same version.
"""

import os
import re
import sys


_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "source", "site"))
sys.path.insert(0, os.path.join(_REPO_ROOT, "source", "packages"))


def _read_package_version(*, pyproject_path: str) -> str:
    """
        Return the package version declared in ``pyproject.toml``
        (``[project].version`` or ``[tool.poetry].version``).

        :param pyproject_path: Path to ``pyproject.toml``.

        :returns: The version string, e.g. ``0.0.7-preview``.
        :raises: RuntimeError when no version is declared.
    """
    with open(pyproject_path, "rb") as handle:
        content = handle.read()

    try:
        import tomllib
    except ModuleNotFoundError:
        tomllib = None

    if tomllib is not None:
        pyproject = tomllib.loads(content.decode("utf-8"))
        candidates = [
            pyproject.get("project", {}).get("version", None),
            pyproject.get("tool", {}).get("poetry", {}).get("version", None),
        ]
        for candidate in candidates:
            if candidate is not None:
                return candidate
    else:
        match = re.search(r'^version\s*=\s*"([^"]+)"', content.decode("utf-8"), re.MULTILINE)
        if match is not None:
            return match.group(1)

    raise RuntimeError("pyproject.toml declares no version: {}".format(pyproject_path))


project = "Pychestrate"
author = "Code Craft AI LLC"
copyright = "2020-2026, Code Craft AI"
release = _read_package_version(pyproject_path=os.path.join(_REPO_ROOT, "pyproject.toml"))
version = ".".join(release.split(".")[:2])


extensions = [
    "ccai.pychestrate.webservice.extension.docs_ext",
]


master_doc = "index"


exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
]


html_theme = "alabaster"
