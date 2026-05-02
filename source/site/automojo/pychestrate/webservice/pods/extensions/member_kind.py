"""
.. module:: pods.extensions.member_kind
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: PodMemberKindExtension base + reference kinds.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, ClassVar, Dict

from automojo.pychestrate.webservice.extensions.resource_extension import ResourceExtension


class PodMemberKindExtension(ResourceExtension):
    """
        Base class contributing one ``kind`` to the pod-member registry.
    """

    resource_extension_name: ClassVar[str] = "pod_member_kind"
    kind_name: ClassVar[str] = ""
    display_label: ClassVar[str] = ""
    value_schema: ClassVar[Dict[str, Any]] = {}

    is_published: ClassVar[bool] = True
    published_docs_url: ClassVar[str] = (
        "https://docs.pychestrate.io/plugin-api/PodMemberKindExtension"
    )
    published_reference: ClassVar[str] = (
        "automojo.pychestrate.webservice.pods.extensions.member_kind.LinuxHost"
    )


class LinuxHost(PodMemberKindExtension):
    """
        A Linux host that reports via the client agent.
    """
    kind_name: ClassVar[str] = "linux_host"
    display_label: ClassVar[str] = "Linux Host"
    value_schema: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "required": ["hostname"],
        "properties": {
            "hostname": {"type": "string", "minLength": 1},
            "distribution": {"type": "string"},
            "kernel": {"type": "string"},
        },
    }


class NetworkSwitch(PodMemberKindExtension):
    """
        A managed network switch.
    """
    kind_name: ClassVar[str] = "network_switch"
    display_label: ClassVar[str] = "Network Switch"
    value_schema: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "required": ["vendor"],
        "properties": {
            "vendor": {"type": "string"},
            "model": {"type": "string"},
            "port_count": {"type": "integer", "minimum": 1},
        },
    }


class SyntheticRole(PodMemberKindExtension):
    """
        A logical role with no physical device.
    """
    kind_name: ClassVar[str] = "synthetic_role"
    display_label: ClassVar[str] = "Synthetic Role"
    value_schema: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "required": ["role"],
        "properties": {"role": {"type": "string"}},
    }
