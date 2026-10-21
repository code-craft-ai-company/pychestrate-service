"""
Sphinx configuration for the Pychestrate user manual.

Build it with warnings as errors, as the ``docs`` CI workflow does::

    sphinx-build -W --keep-going -b html userguide .output/docs/userguide-html

That builds the manual alone, and needs nothing but Sphinx. The whole
site also has the REST API reference (ReDoc, from
``specs/openapi/pychestrate.yaml``) and the plugin catalog (one page per
published protocol and resource extension). Those need the service's
code and dependencies, so they are added by a tag::

    sphinx-build -W --keep-going -t reference -b html userguide .output/docs/site

(``make docs`` runs that.) The catalog pages are written into
``userguide/extensions/`` and the reference into ``userguide/_reference/``
while the site is built; neither is committed. The build stops when the
catalog is empty.

The manual is written to read well both here and on GitHub, which renders
each ``.rst`` file on its own and drops Sphinx-only roles and directives.
So chapters link to each other with plain hyperlinks to the ``.rst`` file
(``\\`Getting Started <02-00-getting-started.rst>\\`_``) instead of
``:doc:`` or ``:ref:``, and the index carries explicit links beside a
hidden toctree. :class:`RstFileLinks` rewrites those hyperlinks at build
time: a link to another chapter becomes a link to its HTML page, and a
link to a file outside the manual (``../DEVELOPING.md``) becomes a link
to that file in the repository. A link to a chapter that does not exist
is a build warning.
"""

import json
import os
import re
import sys
import tempfile

from docutils import nodes
from sphinx import addnodes
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
    "_reference",
    "Thumbs.db",
    ".DS_Store",
]

#: True for ``-t reference``: the whole site, with the REST API reference
#: and the plugin catalog.
REFERENCE_BUILD = tags.has("reference")

extensions = []
html_extra_path = []

#: The plugin catalog (``extensions/index``) is generated, and only by the whole-site build. A plain build (no ``-t reference``)
#: has no catalog, so the two ``:doc:`Plugin Catalog <extensions/index>``` links in ``11-00-extensions.rst`` have nothing to point
#: at and read as plain text; Sphinx would otherwise fail ``-W`` on them with "unknown document". (``only`` blocks do not help:
#: Sphinx resolves references before it drops them.) The whole-site build still resolves, and with ``-W`` checks, every ``:doc:`` link.
suppress_warnings = []
if REFERENCE_BUILD is not True:
    suppress_warnings.append("ref.doc")

if REFERENCE_BUILD is True:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "source", "site"))
    sys.path.insert(0, os.path.join(_REPO_ROOT, "source", "packages"))
    # Loading the service creates its state directory; keep that out of
    # the reader's home.
    os.environ.setdefault("PYCHESTRATE_PRESENCE_DIR", tempfile.mkdtemp(prefix="pychestrate-docs-"))
    extensions.append("ccai.pychestrate.webservice.extension.docs_ext")

html_theme = "alabaster"
html_title = "Pychestrate User Manual"

#: Where links from the manual to other repository files point in the
#: built HTML (GitHub resolves the same relative links itself).
pychestrate_repository_url = "https://github.com/code-craft-ai-company/pychestrate-service/blob/main/"

#: The OpenAPI document. A link to it goes to the file on GitHub, and to
#: the rendered reference in a site built with ``-t reference``.
OPENAPI_DOCUMENT = os.path.join(_REPO_ROOT, "specs", "openapi", "pychestrate.yaml")

#: Directory, next to this file, the reference is generated into.
REFERENCE_DIRECTORY = "_reference"
API_REFERENCE_DIRECTORY = "api-reference"


class RstFileLinks(SphinxPostTransform):
    """
        Rewrite plain hyperlinks to repository files into links that work
        in the built HTML.
    """

    default_priority = 5

    def _hidden_by_only(self, *, node: nodes.Node) -> bool:
        """
            Whether ``node`` sits inside an ``only`` block this build
            leaves out (a link to the plugin catalog when the catalog
            was not built). Sphinx drops such blocks after this
            transform runs, so a link in one must not be checked.

            :param node: A node of the current document.

            :returns: True when a surrounding ``only`` is false.
        """
        parent = node.parent
        while parent is not None:
            if isinstance(parent, addnodes.only):
                if self.app.builder.tags.eval_condition(parent["expr"]) is False:
                    return True
            parent = parent.parent
        return False

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
            if self._hidden_by_only(node=reference) is True:
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

            if REFERENCE_BUILD is True and target == OPENAPI_DOCUMENT:
                # The reference sits at the site root, beside the manual's
                # front page; reach it from wherever this chapter is.
                front_page = self.app.builder.get_relative_uri(self.env.docname, self.config.root_doc)
                prefix = os.path.dirname(front_page)
                if len(prefix) > 0:
                    prefix += "/"
                reference["refuri"] = prefix + API_REFERENCE_DIRECTORY + "/index.html"
                continue

            if os.path.exists(target) is False:
                _logger.warning("link to a missing file: %s", uri, location=reference)
                continue
            repository_path = os.path.relpath(target, _REPO_ROOT).replace(os.sep, "/")
            reference["refuri"] = self.config.pychestrate_repository_url + repository_path + suffix
        return


def _build_api_reference(app) -> None:
    """
        Write the REST API reference into ``_reference/api-reference`` and
        have Sphinx copy it to the site root: the OpenAPI document as
        JSON, the ReDoc script the service bundles, and a page that shows
        one with the other. Served over HTTP the page loads the document
        from beside it, so it works from any host and needs no network.

        :param app: The Sphinx application.

        :returns: None.
    """
    import yaml
    from ccai.webworks.openapi.assets import AssetResolver
    from ccai.webworks.openapi.redoc import REDOC_HTML_TEMPLATE

    out_directory = os.path.join(app.confdir, REFERENCE_DIRECTORY, API_REFERENCE_DIRECTORY)
    os.makedirs(out_directory, exist_ok=True)

    with open(OPENAPI_DOCUMENT, "r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    with open(os.path.join(out_directory, "openapi.json"), "w", encoding="utf-8") as handle:
        json.dump(document, handle, default=str)

    script = AssetResolver().resolve("redoc", "redoc.standalone.js")
    if script is None:
        raise RuntimeError("The ReDoc script that webworks bundles was not found.")
    with open(os.path.join(out_directory, "redoc.standalone.js"), "wb") as handle:
        handle.write(script)

    page = REDOC_HTML_TEMPLATE.format(
        title="Pychestrate REST API", spec_url="openapi.json", static_path=".", extra_config="",
    )
    with open(os.path.join(out_directory, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(page)

    app.config.html_extra_path.append(os.path.join(app.confdir, REFERENCE_DIRECTORY))
    return


def setup(app):
    """
        Register the link rewriter and its configuration value, and in a
        reference build the generator of the REST API reference.

        :param app: The Sphinx application.

        :returns: Extension metadata.
    """
    app.add_config_value("pychestrate_repository_url", pychestrate_repository_url, "html")
    app.add_post_transform(RstFileLinks)
    if REFERENCE_BUILD is True:
        app.connect("builder-inited", _build_api_reference)
    rtnval = {"parallel_read_safe": True, "parallel_write_safe": True}
    return rtnval
