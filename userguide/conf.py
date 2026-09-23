"""
Sphinx configuration for the Pychestrate user manual.

Build it with warnings as errors, as the ``docs`` CI workflow does::

    sphinx-build -W --keep-going -b html userguide .output/userguide-html

The manual is written to read well both here and on GitHub, which renders
each ``.rst`` file on its own and drops Sphinx-only roles and directives.
So chapters link to each other with plain hyperlinks to the ``.rst`` file
(``\\`Getting Started <02-00-getting-started.rst>\\`_``) instead of
``:doc:`` or ``:ref:``, and the index carries explicit links beside a
hidden toctree. :class:`RstFileLinks` rewrites those hyperlinks at build
time: a link to another chapter becomes a link to its HTML page, and a
link to a file outside the manual (``../CONTRIBUTING.md``) becomes a link
to that file in the repository. A link to a chapter that does not exist
is a build warning.
"""

import os
import re

from docutils import nodes
from sphinx.transforms.post_transforms import SphinxPostTransform
from sphinx.util import logging


_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, ".."))

_logger = logging.getLogger(__name__)


def _read_package_version(*, pyproject_path: str) -> str:
    """
        Return the package version declared in ``pyproject.toml``
        (``[project].version`` or ``[tool.poetry].version``).

        :param pyproject_path: Path to ``pyproject.toml``.

        :returns: The version string.
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


project = "Pychestrate User Manual"
author = "Code Craft AI LLC"
copyright = "2020-2026, Code Craft AI"
release = _read_package_version(pyproject_path=os.path.join(_REPO_ROOT, "pyproject.toml"))
version = ".".join(release.split(".")[:2])

root_doc = "userguide"
master_doc = "userguide"

exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
]

html_theme = "alabaster"
html_title = "Pychestrate User Manual"

#: Where links from the manual to other repository files point in the
#: built HTML (GitHub resolves the same relative links itself).
pychestrate_repository_url = "https://github.com/code-craft-ai-company/pychestrate-service/blob/main/"


class RstFileLinks(SphinxPostTransform):
    """
        Rewrite plain hyperlinks to repository files into links that work
        in the built HTML.
    """

    default_priority = 5

    def run(self, **kwargs) -> None:
        """
            Rewrite every relative ``refuri`` in the current document.

            :returns: None.
        """
        finder = getattr(self.document, "findall", None) or self.document.traverse
        source_dir = os.path.dirname(self.env.doc2path(self.env.docname))
        for reference in list(finder(nodes.reference)):
            uri = reference.get("refuri", "")
            if len(uri) == 0 or "://" in uri or uri.startswith(("#", "mailto:")):
                continue

            path, _, anchor = uri.partition("#")
            suffix = "#" + anchor if len(anchor) > 0 else ""
            target = os.path.normpath(os.path.join(source_dir, path))
            relative_to_manual = os.path.relpath(target, self.env.srcdir)

            if path.endswith(".rst") and relative_to_manual.startswith("..") is False:
                docname = relative_to_manual[:-len(".rst")].replace(os.sep, "/")
                if docname not in self.env.found_docs:
                    _logger.warning("link to a missing chapter: %s", uri, location=reference)
                    continue
                reference["refuri"] = self.app.builder.get_relative_uri(self.env.docname, docname) + suffix
                continue

            if os.path.exists(target) is False:
                _logger.warning("link to a missing file: %s", uri, location=reference)
                continue
            repository_path = os.path.relpath(target, _REPO_ROOT).replace(os.sep, "/")
            reference["refuri"] = self.config.pychestrate_repository_url + repository_path + suffix
        return


def setup(app):
    """
        Register the link rewriter and its configuration value.

        :param app: The Sphinx application.

        :returns: Extension metadata.
    """
    app.add_config_value("pychestrate_repository_url", pychestrate_repository_url, "html")
    app.add_post_transform(RstFileLinks)
    rtnval = {"parallel_read_safe": True, "parallel_write_safe": True}
    return rtnval
