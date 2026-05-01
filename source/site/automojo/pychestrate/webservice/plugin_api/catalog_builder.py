"""
.. module:: plugin_api.catalog_builder
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Build the published-surface catalog from class annotations.

.. moduleauthor:: Automation Mojo LLC

Walks the immediate subclasses of :class:`FactoryProtocolBase` and
:class:`ResourceExtension`, filters on ``is_published == True``, and
collects them into an immutable :class:`Catalog`. The walk relies on
the modules that declare protocol classes being imported at startup;
the bootstrap performs side-effect imports of every feature module
before invoking :func:`build_catalog`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Type

from automojo.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase
from automojo.pychestrate.webservice.extensions.resource_extension import ResourceExtension
from automojo.pychestrate.webservice.plugin_api.annotations import (
    PublishedSurfaceMetadata,
    extract_published_metadata,
    is_class_published,
)


CATALOG_KIND_FACTORY: str = "factory_protocol"
CATALOG_KIND_RESOURCE: str = "resource_extension"


@dataclass(frozen=True)
class CatalogEntry:
    """
        Single published-surface entry exposed via the REST endpoint.

        :param name: Protocol name (``factory_protocol_name`` for
                     factories) or resource extension class name (for
                     resource bases).
        :param kind: ``"factory_protocol"`` or ``"resource_extension"``.
        :param protocol_schema_version: Schema version declared on the
                                        class (resource bases default to
                                        1).
        :param metadata: :class:`PublishedSurfaceMetadata` snapshot.
        :param declaring_class_qualname: Fully qualified class name of
                                         the declaring class (used by
                                         the validator to resolve the
                                         on-disk module).
    """
    name: str
    kind: str
    protocol_schema_version: int
    metadata: PublishedSurfaceMetadata
    declaring_class_qualname: str


@dataclass(frozen=True)
class Catalog:
    """
        Frozen view of the published surface.

        :param factory_entries: Entries with kind ``"factory_protocol"``.
        :param resource_entries: Entries with kind
                                 ``"resource_extension"``.
    """
    factory_entries: Tuple[CatalogEntry, ...] = field(default_factory=tuple)
    resource_entries: Tuple[CatalogEntry, ...] = field(default_factory=tuple)


def _walk_published_factory_protocols() -> List[Type[FactoryProtocolBase]]:
    """
        Return every loaded direct subclass of :class:`FactoryProtocolBase`
        whose ``is_published`` flag evaluates True.

        :returns: List of protocol classes ordered by name.
    """
    candidates: List[Type[FactoryProtocolBase]] = []
    for subclass in FactoryProtocolBase.__subclasses__():
        if is_class_published(target_class=subclass) is True:
            candidates.append(subclass)
    candidates.sort(key=lambda cls: getattr(cls, "factory_protocol_name", cls.__name__))
    rtnval = candidates
    return rtnval


def _walk_published_resource_extensions() -> List[Type[ResourceExtension]]:
    """
        Return every loaded direct subclass of :class:`ResourceExtension`
        whose ``is_published`` flag evaluates True.

        :returns: List of resource base classes ordered by class name.
    """
    candidates: List[Type[ResourceExtension]] = []
    for subclass in ResourceExtension.__subclasses__():
        if is_class_published(target_class=subclass) is True:
            candidates.append(subclass)
    candidates.sort(key=lambda cls: cls.__name__)
    rtnval = candidates
    return rtnval


def _qualname(*, target_class: Type) -> str:
    """
        Compute the fully qualified ``module.ClassName`` for a class.

        :param target_class: Class being summarized.

        :returns: Dotted path string.
    """
    module_name = target_class.__module__
    class_name = target_class.__qualname__
    rtnval = "{}.{}".format(module_name, class_name)
    return rtnval


def build_catalog() -> Catalog:
    """
        Assemble the published-surface catalog from currently loaded
        annotations.

        :returns: :class:`Catalog` snapshot.
    """
    factory_entries: List[CatalogEntry] = []
    for protocol_class in _walk_published_factory_protocols():
        metadata = extract_published_metadata(target_class=protocol_class)
        protocol_name = getattr(protocol_class, "factory_protocol_name", protocol_class.__name__)
        schema_version = int(getattr(protocol_class, "protocol_schema_version", 1))
        entry = CatalogEntry(
            name=str(protocol_name),
            kind=CATALOG_KIND_FACTORY,
            protocol_schema_version=schema_version,
            metadata=metadata,
            declaring_class_qualname=_qualname(target_class=protocol_class),
        )
        factory_entries.append(entry)

    resource_entries: List[CatalogEntry] = []
    for resource_class in _walk_published_resource_extensions():
        metadata = extract_published_metadata(target_class=resource_class)
        entry = CatalogEntry(
            name=resource_class.__name__,
            kind=CATALOG_KIND_RESOURCE,
            protocol_schema_version=1,
            metadata=metadata,
            declaring_class_qualname=_qualname(target_class=resource_class),
        )
        resource_entries.append(entry)

    rtnval = Catalog(
        factory_entries=tuple(factory_entries),
        resource_entries=tuple(resource_entries),
    )
    return rtnval


def _entry_to_dict(*, entry: CatalogEntry) -> Dict:
    """
        Render a :class:`CatalogEntry` as a JSON-friendly dict matching
        the contract advertised in
        ``GET /api/v1/plugin-api/_meta/catalog``.

        :param entry: Single :class:`CatalogEntry`.

        :returns: Dictionary with stable keys.
    """
    rtnval = {
        "name": entry.name,
        "kind": entry.kind,
        "protocol_schema_version": entry.protocol_schema_version,
        "min_schema_version": entry.metadata.min_schema_version,
        "status": entry.metadata.status,
        "deprecation_date": entry.metadata.deprecation_date,
        "sunset_date": entry.metadata.sunset_date,
        "docs_url": entry.metadata.docs_url,
        "reference": entry.metadata.reference,
        "declaring_class": entry.declaring_class_qualname,
    }
    return rtnval


def catalog_to_jsonable(*, catalog: Catalog) -> Dict:
    """
        Render a :class:`Catalog` as a JSON-friendly dict.

        :param catalog: Catalog snapshot.

        :returns: Dict with ``factory_protocols`` and ``resource_extensions``
                  arrays.
    """
    factories = [_entry_to_dict(entry=entry) for entry in catalog.factory_entries]
    resources = [_entry_to_dict(entry=entry) for entry in catalog.resource_entries]
    rtnval = {
        "factory_protocols": factories,
        "resource_extensions": resources,
    }
    return rtnval
