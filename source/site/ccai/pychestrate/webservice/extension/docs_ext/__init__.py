"""
.. module:: extension.docs_ext
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Sphinx extension that emits per-entry pages for the published catalog.

.. moduleauthor:: Code Craft AI LLC

A Sphinx site that loads this extension gets one ``.rst`` page per
published protocol and resource extension, written into
``<source dir>/extensions/protocols/`` and
``<source dir>/extensions/resources/``. The user manual's site does so
when it is built with ``-t reference``. M1 ships stub pages -- names,
schema versions, deprecation metadata, and reference paths. Full
method-signature embedding, capability tables, and stability filtering
arrive in M2 (T2.x).

The catalog is what the running service publishes, so the extension
registers the built-in factory implementations and resource extensions
first, exactly as the service does at start. Without that the catalog
holds nothing in a build process (it is filled by importing the
declaring modules), and the site used to come out as an index and two
empty category pages. A build now stops when either category is empty.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List

from ccai.pychestrate.webservice.extension.docs_ext.catalog_walker import (
    CatalogWalker,
    builtin_template_root,
)
from ccai.pychestrate.webservice.plugin_api.catalog_builder import Catalog


__all__ = [
    "CatalogWalker",
    "builtin_template_root",
    "check_catalog_not_empty",
    "load_builtin_declarations",
    "write_catalog_front_page",
    "setup",
]


def load_builtin_declarations() -> None:
    """
        Load the service the way it starts, so the catalog covers what
        the running service publishes: import the application module
        (which imports every declaring module) and register the built-in
        factory implementations and resource extensions. Registering the
        three bootstrap phases alone misses the backup, RPA and metric
        declarations, which only the full import reaches. Safe to call
        more than once. ``source/site`` must be on ``sys.path``.

        :returns: None.
    """
    import app_pychestrate_main  # noqa: E402

    app_pychestrate_main.register_service_extensions()
    return


#: The catalog's front page: reached from a link in the manual, and
#: listing the two category indexes the walker writes.
CATALOG_FRONT_PAGE: str = """:orphan:

Plugin Catalog
==============

The factory protocols and resource extensions an extension package can
target: the externally stable surface of Pychestrate. Each page gives the
schema version, its support status, and where the built-in implementation
lives. The `Extensions <../11-00-extensions.rst>`_ guide explains how to
write one.

.. toctree::
    :maxdepth: 1

    protocols/index
    resources/index
"""


def write_catalog_front_page(*, out_dir: Any) -> None:
    """
        Write ``index.rst`` beside the ``protocols`` and ``resources``
        directories, so the catalog has one page to link to.

        :param out_dir: The directory the walker emitted into.

        :returns: None.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.rst").write_text(CATALOG_FRONT_PAGE, encoding="utf-8")
    return


def check_catalog_not_empty(*, catalog: Catalog) -> None:
    """
        Refuse to build a site from a catalog with nothing in one of its
        categories: that is a build that lost its declarations, not a
        product with nothing to document.

        :param catalog: The catalog about to be rendered.

        :returns: None.
        :raises: sphinx.errors.ExtensionError when either category is
                 empty.
    """
    empty: List[str] = []
    if len(catalog.factory_entries) == 0:
        empty.append("factory protocols")
    if len(catalog.resource_entries) == 0:
        empty.append("resource extensions")
    if len(empty) > 0:
        from sphinx.errors import ExtensionError  # noqa: E402

        err_msg = (
            "The plugin catalog has no {}. The built-in extensions were not"
            " registered before the catalog was read."
        ).format(" and no ".join(empty))
        raise ExtensionError(err_msg)
    return


def setup(app: Any) -> Dict[str, Any]:
    """
        Sphinx extension entry point.

        Hooks the ``builder-inited`` event so the catalog walker emits
        pages before Sphinx scans the source tree.

        :param app: The Sphinx application object.

        :returns: Sphinx-required metadata mapping.
    """
    app.connect("builder-inited", _on_builder_inited)
    rtnval: Dict[str, Any] = {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
    return rtnval


def _on_builder_inited(app: Any) -> None:
    """
        Render every catalog entry as a stub page under
        ``app.srcdir / "extensions"``.

        :param app: Active Sphinx application.

        :returns: None.
    """
    from pathlib import Path

    from ccai.pychestrate.webservice.plugin_api.runtime import get_active_catalog

    load_builtin_declarations()
    catalog = get_active_catalog()
    check_catalog_not_empty(catalog=catalog)

    out_root = Path(str(app.srcdir)) / "extensions"
    walker = CatalogWalker(
        catalog=catalog,
        out_dir=out_root,
        template_root=None,
        stability_filter=None,
    )
    walker.emit_all()
    write_catalog_front_page(out_dir=out_root)
    return
