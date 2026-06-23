"""
.. module:: plugin_api.annotations
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Class-level ``is_published`` annotations and reader helpers.

.. moduleauthor:: Code Craft AI LLC

Each published factory protocol (subclass of
:class:`FactoryProtocolBase`) and resource extension base (subclass of
:class:`ResourceExtension`) declares a small set of class attributes
describing how the surface participates in the externally-stable
plugin API. The reader helpers in this module pull those attributes
into a :class:`PublishedSurfaceMetadata` snapshot the catalog builder
and validator consume.

Annotations declared on a class:

* ``is_published: bool`` — opt-in flag.
* ``published_status: str`` — ``supported`` |
  ``deprecated`` | ``removed-in-next-major``.
* ``published_min_schema_version: int`` — earliest
  ``protocol_schema_version`` operators may load.
* ``published_deprecation_date: Optional[str]`` — ISO-8601 date the
  surface entered ``deprecated`` status.
* ``published_sunset_date: Optional[str]`` — ISO-8601 date the
  surface is removed at the next major bump.
* ``published_docs_url: str`` — public docs link
  (rendered into the catalog response).
* ``published_reference: str`` — dotted path to the in-tree reference
  implementation (factory) or to the in-tree first kind (resource).
  The validator resolves this path at startup; absence is fatal.

Defaults: when a class does not declare ``is_published`` it is treated
as ``False``. This keeps internal-only protocols out of the catalog
without per-class boilerplate.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Optional, Type


PUBLISHED_STATUS_SUPPORTED: str = "supported"
PUBLISHED_STATUS_DEPRECATED: str = "deprecated"
PUBLISHED_STATUS_REMOVED_IN_NEXT_MAJOR: str = "removed-in-next-major"


_VALID_PUBLISHED_STATUSES = (
    PUBLISHED_STATUS_SUPPORTED,
    PUBLISHED_STATUS_DEPRECATED,
    PUBLISHED_STATUS_REMOVED_IN_NEXT_MAJOR,
)


@dataclass(frozen=True)
class PublishedSurfaceMetadata:
    """
        Snapshot of every published-surface annotation read from a class.

        :param status: One of the :data:`_VALID_PUBLISHED_STATUSES`.
        :param min_schema_version: Minimum
                                   ``protocol_schema_version``
                                   currently honored.
        :param deprecation_date: ISO-8601 date string or None.
        :param sunset_date: ISO-8601 date string or None.
        :param docs_url: External documentation URL.
        :param reference: Dotted import path to the in-tree reference.
    """
    status: str
    min_schema_version: int
    deprecation_date: Optional[str]
    sunset_date: Optional[str]
    docs_url: str
    reference: str


def is_class_published(*, target_class: Type) -> bool:
    """
        Return True if ``target_class`` opts into the published surface.

        :param target_class: Factory protocol or resource extension base
                             class to inspect.

        :returns: Boolean flag value or False when the attribute is
                  absent.
    """
    flag_value = getattr(target_class, "is_published", False)
    rtnval = bool(flag_value)
    return rtnval


def extract_published_metadata(*, target_class: Type) -> PublishedSurfaceMetadata:
    """
        Read every published annotation off ``target_class``.

        :param target_class: A class previously gated by
                             :func:`is_class_published`.

        :returns: :class:`PublishedSurfaceMetadata` snapshot.
    """
    raw_status = getattr(target_class, "published_status", PUBLISHED_STATUS_SUPPORTED)
    if raw_status not in _VALID_PUBLISHED_STATUSES:
        normalized_status = PUBLISHED_STATUS_SUPPORTED
    else:
        normalized_status = raw_status

    raw_min_schema = getattr(target_class, "published_min_schema_version", 1)
    try:
        min_schema_version = int(raw_min_schema)
    except (TypeError, ValueError):
        min_schema_version = 1

    deprecation_date = getattr(target_class, "published_deprecation_date", None)
    sunset_date = getattr(target_class, "published_sunset_date", None)
    docs_url = getattr(target_class, "published_docs_url", "")
    reference = getattr(target_class, "published_reference", "")

    rtnval = PublishedSurfaceMetadata(
        status=normalized_status,
        min_schema_version=min_schema_version,
        deprecation_date=deprecation_date,
        sunset_date=sunset_date,
        docs_url=str(docs_url),
        reference=str(reference),
    )
    return rtnval
