"""
.. module:: agents.extensions.capability_kind
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: CapabilityKindExtension base + reference kinds.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, ClassVar, Dict

from ccai.pychestrate.webservice.extensions.resource_extension import ResourceExtension


class CapabilityKindExtension(ResourceExtension):
    """
        Base class for a capability kind advertised by a client.
    """

    resource_extension_name: ClassVar[str] = "capability_kind"
    kind_name: ClassVar[str] = ""
    sensitive: ClassVar[bool] = False
    value_schema: ClassVar[Dict[str, Any]] = {}


class ToolchainCapability(CapabilityKindExtension):
    """
        Toolchain versions reported by a client.
    """
    kind_name: ClassVar[str] = "toolchain"
    value_schema: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "additionalProperties": {"type": "string"},
    }


class PodMemberOwnershipCapability(CapabilityKindExtension):
    """
        Pod member kinds this client can host.
    """
    kind_name: ClassVar[str] = "pod_member_ownership"
    value_schema: ClassVar[Dict[str, Any]] = {
        "type": "array",
        "items": {"type": "string"},
    }


class ConcurrencyCapability(CapabilityKindExtension):
    """
        Maximum concurrent job slots offered by this client.
    """
    kind_name: ClassVar[str] = "concurrency"
    value_schema: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "required": ["max_parallel_jobs"],
        "properties": {
            "max_parallel_jobs": {"type": "integer", "minimum": 1},
        },
    }


class RpaCapability(CapabilityKindExtension):
    """
        RPA job types a client can run (``"type@version"`` labels) and
        the taskplus engine version it has on ``PATH`` (``null`` when
        absent). Introduced by 6-rpa-orchestration.
    """
    kind_name: ClassVar[str] = "rpa"
    value_schema: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "properties": {
            "job_types": {"type": "array", "items": {"type": "string"}},
            "taskplus": {"type": ["string", "null"]},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
    }
