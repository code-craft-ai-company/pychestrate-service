"""
.. module:: resources.inventory.kinds.device_kind
    :synopsis: DeviceResourceKind reference impl.

Identifies a physical or virtual device by its hostname plus an
optional MAC address. M1 ships a permissive validator — non-empty
hostname is the only hard requirement; M2 extends with stricter
syntax checks per attribute key.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Mapping

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.resources.inventory.kinds.kind_protocol import (
    ResourceKindProtocol,
    hash_attribute_subset,
)


DEVICE_KIND: str = "device"
DEVICE_IDENTITY_KEYS: tuple = ("hostname", "mac_address")
DEVICE_ALLOWED_ATTRIBUTES: frozenset = frozenset((
    "hostname",
    "mac_address",
    "ipv4",
    "ipv6",
    "vendor",
    "model",
    "location",
    "notes",
))


class DeviceResourceKind(ResourceKindProtocol):
    """
        Reference resource-kind for general-purpose devices.
    """

    factory_protocol_name: str = "resource_kind"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def kind_name(cls) -> str:
        rtnval = DEVICE_KIND
        return rtnval

    @classmethod
    def normalize(
            cls,
            *,
            attributes: Mapping[str, Any]
        ) -> Mapping[str, Any]:
        if attributes is None:
            attributes = {}
        normalized = {}
        unknown = []
        for key, value in attributes.items():
            if key not in DEVICE_ALLOWED_ATTRIBUTES:
                unknown.append(key)
                continue
            if value is None:
                continue
            text = str(value).strip()
            if len(text) == 0:
                continue
            normalized[key] = text

        if len(unknown) > 0:
            err_lines = ["DeviceResourceKind: unknown attribute keys."]
            err_lines.append("UNKNOWN: {}".format(sorted(unknown)))
            err_lines.append("ALLOWED: {}".format(sorted(DEVICE_ALLOWED_ATTRIBUTES)))
            err_msg = os.linesep.join(err_lines)
            raise SemanticError(err_msg) from None

        hostname = normalized.get("hostname", "")
        if len(hostname) == 0:
            err_lines = ["DeviceResourceKind: 'hostname' is required."]
            err_msg = os.linesep.join(err_lines)
            raise SemanticError(err_msg) from None

        rtnval = normalized
        return rtnval

    @classmethod
    def identity_hash(
            cls,
            *,
            attributes: Mapping[str, Any]
        ) -> str:
        rtnval = hash_attribute_subset(
            attributes=attributes,
            identity_keys=DEVICE_IDENTITY_KEYS,
        )
        return rtnval
