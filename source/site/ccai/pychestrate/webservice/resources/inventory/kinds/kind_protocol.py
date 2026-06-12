"""
.. module:: resources.inventory.kinds.kind_protocol
    :synopsis: ``resource_kind`` factory contract.

A resource-kind extension declares the shape of the
caller-supplied identity + attributes for one kind of resource
(device, ip-block, license, custom-equipment), validates and
normalizes input, and renders a stable identity hash for
uniqueness enforcement.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib

from typing import Any, Mapping

from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


class ResourceKindProtocol(FactoryProtocolBase):
    """
        Contract for resource-kind extensions.
    """

    factory_protocol_name: str = "resource_kind"
    protocol_schema_version: int = 1

    # 8-plugin-api Requirement 2 advertises this surface as
    # ``ResourceKindExtension`` (resource-extension shape). The
    # in-tree implementation took the factory-protocol shape — same
    # semantic surface (a discoverable set of typed kinds), different
    # extension mechanism. The catalog publishes the actual
    # implementation under ``factory: resource_kind``; the spec
    # naming will be reconciled in a future doc pass.
    is_published: bool = True
    published_docs_url: str = "https://docs.pychestrate.io/plugin-api/resource_kind"
    published_reference: str = (
        "ccai.pychestrate.webservice.resources.inventory.kinds.device_kind"
        ".DeviceResourceKind"
    )

    @classmethod
    def kind_name(cls) -> str:
        """
            Stable identifier the resource row's ``kind`` column
            stores.
        """
        raise NotImplementedError("Subclasses must implement kind_name")

    @classmethod
    def normalize(
            cls,
            *,
            attributes: Mapping[str, Any]
        ) -> Mapping[str, Any]:
        """
            Return a sanitized + canonicalized attribute dict.
            Implementations strip surrounding whitespace, fold
            case, and reject unknown keys.

            :raises: SemanticError on validation failure.
        """
        raise NotImplementedError("Subclasses must implement normalize")

    @classmethod
    def identity_hash(
            cls,
            *,
            attributes: Mapping[str, Any]
        ) -> str:
        """
            Render the identity hash used for the per-kind unique
            constraint. Implementations select the subset of
            attributes that uniquely identify the resource (e.g.
            MAC address, ipv4 + cidr) and hash them
            deterministically.

            :returns: Lowercase-hex SHA-256 digest.
        """
        raise NotImplementedError("Subclasses must implement identity_hash")


def hash_attribute_subset(
        *,
        attributes: Mapping[str, Any],
        identity_keys: tuple
    ) -> str:
    """
        Helper for kind impls — concatenates the values of
        ``identity_keys`` from ``attributes`` (in tuple order)
        with ``\\x1f`` separators and SHA-256s the result.
    """
    parts = []
    for key in identity_keys:
        value = attributes.get(key, "")
        parts.append(str(value).strip().lower())
    payload = "\x1f".join(parts).encode("utf-8")
    rtnval = hashlib.sha256(payload).hexdigest()
    return rtnval
