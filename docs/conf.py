"""
Sphinx configuration for the Pychestrate documentation site.

The docs site renders the externally-stable plugin API surface
catalog into per-entry pages. Pages are emitted at build time by the
``automojo.pychestrate.webservice.extension.docs_ext`` Sphinx extension
and committed alongside the rest of the docs tree on release.

Run ``make -C docs html`` from the repository root to build.
"""

import os
import sys


_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "source", "site"))
sys.path.insert(0, os.path.join(_REPO_ROOT, "source", "packages"))


project = "Pychestrate"
author = "Automation Mojo LLC"
copyright = "2025, Automation Mojo LLC"
release = "0.1.0"


extensions = [
    "automojo.pychestrate.webservice.extension.docs_ext",
]


master_doc = "index"


exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
]


html_theme = "alabaster"
