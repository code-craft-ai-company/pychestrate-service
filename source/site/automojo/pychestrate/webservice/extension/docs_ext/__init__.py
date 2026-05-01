"""
.. module:: extension.docs_ext
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Sphinx extension that emits per-entry pages for the published catalog.

.. moduleauthor:: Automation Mojo LLC

The Sphinx site rooted at ``docs/`` loads this extension; it walks the
catalog produced by :mod:`automojo.pychestrate.webservice.plugin_api`
and emits one ``.rst`` page per protocol / resource into the
``docs/extensions/protocols/`` and ``docs/extensions/resources/``
directories. M1 ships stub pages — names, schema versions, deprecation
metadata, and reference paths. Full method-signature embedding,
capability tables, and stability filtering arrive in M2 (T2.x).

The extension is intentionally minimal so the build is hermetic — it
imports only declaration modules (already loaded by service bootstrap)
and never executes extension code.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict

from automojo.pychestrate.webservice.extension.docs_ext.catalog_walker import (
    CatalogWalker,
    builtin_template_root,
)


__all__ = [
    "CatalogWalker",
    "builtin_template_root",
    "setup",
]


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

    out_root = Path(str(app.srcdir)) / "extensions"
    walker = CatalogWalker(
        catalog=None,
        out_dir=out_root,
        template_root=None,
        stability_filter=None,
    )
    walker.emit_all()
    return
