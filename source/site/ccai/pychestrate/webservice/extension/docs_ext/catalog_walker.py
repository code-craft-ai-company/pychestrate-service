"""
.. module:: extension.docs_ext.catalog_walker
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Render Sphinx ``.rst`` pages from the published catalog.

.. moduleauthor:: Code Craft AI LLC

The walker accepts a :class:`Catalog` snapshot (or builds the active
one via :mod:`plugin_api.runtime` when none is supplied), iterates
both factory and resource entries, and renders each as a single
``.rst`` page using the M1 stub Jinja templates. Output is written
under ``<out_dir>/protocols/<name>.rst`` and
``<out_dir>/resources/<name>.rst``; an ``index.rst`` per category
references the generated files via ``toctree``.

The walker is hermetic: it never imports the implementation modules
referenced by ``published_reference`` — only the declaration modules
the service bootstrap already loaded.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from pathlib import Path
from typing import List, Optional

import jinja2

from ccai.pychestrate.webservice.extension.docs_ext.models import (
    PAGE_KIND_PROTOCOL,
    PAGE_KIND_RESOURCE,
    DocPage,
)
from ccai.pychestrate.webservice.plugin_api.catalog_builder import (
    Catalog,
    CatalogEntry,
)
from ccai.pychestrate.webservice.plugin_api.runtime import get_active_catalog


PROTOCOL_TEMPLATE_NAME: str = "protocol_page.rst.jinja"
RESOURCE_TEMPLATE_NAME: str = "resource_page.rst.jinja"
PROTOCOL_INDEX_TEMPLATE_NAME: str = "protocols_index.rst.jinja"
RESOURCE_INDEX_TEMPLATE_NAME: str = "resources_index.rst.jinja"


def builtin_template_root() -> Path:
    """
        Return the absolute path to the in-tree template directory.

        :returns: Path to the package's ``templates/`` directory.
    """
    rtnval = Path(__file__).parent / "templates"
    return rtnval


def _entry_to_page(*, entry: CatalogEntry) -> DocPage:
    """
        Translate a :class:`CatalogEntry` to a :class:`DocPage`.

        :param entry: Catalog entry from the runtime catalog.

        :returns: :class:`DocPage` for rendering.
    """
    if entry.kind == "factory_protocol":
        kind = PAGE_KIND_PROTOCOL
    else:
        kind = PAGE_KIND_RESOURCE
    rtnval = DocPage(
        name=entry.name,
        kind=kind,
        status=entry.metadata.status,
        schema_version=entry.protocol_schema_version,
        min_schema_version=entry.metadata.min_schema_version,
        deprecation_date=entry.metadata.deprecation_date,
        sunset_date=entry.metadata.sunset_date,
        docs_url=entry.metadata.docs_url,
        reference=entry.metadata.reference,
        declaring_class=entry.declaring_class_qualname,
    )
    return rtnval


def _build_environment(*, template_root: Path) -> jinja2.Environment:
    """
        Build a Jinja2 environment rooted at the template directory.

        :param template_root: Directory containing the M1 templates.

        :returns: Configured :class:`jinja2.Environment`.
    """
    loader = jinja2.FileSystemLoader(str(template_root))
    rtnval = jinja2.Environment(
        loader=loader,
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
        undefined=jinja2.StrictUndefined,
    )
    return rtnval


class CatalogWalker:
    """
        Render :class:`Catalog` entries as ``.rst`` stub pages.
    """

    def __init__(
            self,
            *,
            catalog: Optional[Catalog],
            out_dir: Path,
            template_root: Optional[Path],
            stability_filter: Optional[str]
        ) -> None:
        """
            :param catalog: Optional :class:`Catalog` snapshot. ``None``
                            triggers a load from
                            :mod:`plugin_api.runtime`.
            :param out_dir: Destination directory; subdirectories
                            ``protocols/`` and ``resources/`` are created
                            under it.
            :param template_root: Optional override for the template
                                  directory. ``None`` uses the in-tree
                                  templates shipped with the extension.
            :param stability_filter: M2 hook — currently ignored. M1
                                     emits every entry regardless of
                                     ``status``.
        """
        self._catalog: Catalog = catalog if catalog is not None else get_active_catalog()
        self._out_dir: Path = out_dir
        self._template_root: Path = (
            template_root if template_root is not None else builtin_template_root()
        )
        self._stability_filter: Optional[str] = stability_filter
        self._environment: jinja2.Environment = _build_environment(
            template_root=self._template_root
        )
        return

    def _render_page(
            self,
            *,
            page: DocPage,
            template_name: str,
            destination: Path
        ) -> Path:
        """
            Render one :class:`DocPage` to a file.

            :param page: Page to render.
            :param template_name: Jinja template filename.
            :param destination: Absolute output path.

            :returns: ``destination`` for caller convenience.
        """
        template = self._environment.get_template(template_name)
        body = template.render(page=page)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(body, encoding="utf-8")
        rtnval = destination
        return rtnval

    def emit_protocol_pages(self) -> List[Path]:
        """
            Render one ``.rst`` page per published factory protocol.

            :returns: List of written paths in catalog order.
        """
        written: List[Path] = []
        for entry in self._catalog.factory_entries:
            page = _entry_to_page(entry=entry)
            destination = self._out_dir / "protocols" / "{}.rst".format(page.name)
            self._render_page(
                page=page, template_name=PROTOCOL_TEMPLATE_NAME, destination=destination
            )
            written.append(destination)
        rtnval = written
        return rtnval

    def emit_resource_pages(self) -> List[Path]:
        """
            Render one ``.rst`` page per published resource base.

            :returns: List of written paths in catalog order.
        """
        written: List[Path] = []
        for entry in self._catalog.resource_entries:
            page = _entry_to_page(entry=entry)
            destination = self._out_dir / "resources" / "{}.rst".format(page.name)
            self._render_page(
                page=page, template_name=RESOURCE_TEMPLATE_NAME, destination=destination
            )
            written.append(destination)
        rtnval = written
        return rtnval

    def emit_indexes(self) -> List[Path]:
        """
            Render the per-category ``index.rst`` toctree files.

            :returns: List of written index paths.
        """
        protocol_names = [
            entry.name for entry in self._catalog.factory_entries
        ]
        resource_names = [
            entry.name for entry in self._catalog.resource_entries
        ]

        written: List[Path] = []

        protocol_index_path = self._out_dir / "protocols" / "index.rst"
        protocol_index_template = self._environment.get_template(
            PROTOCOL_INDEX_TEMPLATE_NAME
        )
        protocol_index_path.parent.mkdir(parents=True, exist_ok=True)
        protocol_index_path.write_text(
            protocol_index_template.render(names=protocol_names), encoding="utf-8"
        )
        written.append(protocol_index_path)

        resource_index_path = self._out_dir / "resources" / "index.rst"
        resource_index_template = self._environment.get_template(
            RESOURCE_INDEX_TEMPLATE_NAME
        )
        resource_index_path.parent.mkdir(parents=True, exist_ok=True)
        resource_index_path.write_text(
            resource_index_template.render(names=resource_names), encoding="utf-8"
        )
        written.append(resource_index_path)

        rtnval = written
        return rtnval

    def emit_all(self) -> List[Path]:
        """
            Render every page and index in one call.

            :returns: List of all written paths in (protocols, resources,
                      indexes) order.
        """
        written: List[Path] = []
        written.extend(self.emit_protocol_pages())
        written.extend(self.emit_resource_pages())
        written.extend(self.emit_indexes())
        rtnval = written
        return rtnval
