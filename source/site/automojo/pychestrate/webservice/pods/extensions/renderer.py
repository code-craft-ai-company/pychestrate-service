"""
.. module:: pods.extensions.renderer
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: PodMemberRendererExtension base + reference renderers for
               3-pod-topology-view.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, ClassVar, Mapping

from automojo.pychestrate.webservice.extensions.resource_extension import ResourceExtension


class PodMemberRendererExtension(ResourceExtension):
    """
        Base class contributing a topology renderer hint for one member kind.
    """

    resource_extension_name: ClassVar[str] = "pod_member_renderer"
    member_kind: ClassVar[str] = ""
    icon: ClassVar[str] = "generic"
    shape: ClassVar[str] = "box"

    @classmethod
    def render_hint(cls, *, member: Mapping[str, Any]) -> Mapping[str, Any]:
        """
            Produce a renderer hint for the given member payload.

            :param member: Member dict from a pod spec.

            :returns: Dict with ``icon``, ``shape``, and optional
                      ``label``/``color`` keys.
        """
        rtnval = {
            "icon": cls.icon,
            "shape": cls.shape,
            "label": member.get("name", member.get("kind", "")),
        }
        return rtnval


class LinuxHostRenderer(PodMemberRendererExtension):
    """
        Renders linux_host members.
    """
    member_kind: ClassVar[str] = "linux_host"
    icon: ClassVar[str] = "server"
    shape: ClassVar[str] = "rect"


class NetworkSwitchRenderer(PodMemberRendererExtension):
    """
        Renders network_switch members.
    """
    member_kind: ClassVar[str] = "network_switch"
    icon: ClassVar[str] = "switch"
    shape: ClassVar[str] = "diamond"


class GenericRenderer(PodMemberRendererExtension):
    """
        Fallback renderer used for kinds without a dedicated entry.
    """
    member_kind: ClassVar[str] = "*"
    icon: ClassVar[str] = "generic"
    shape: ClassVar[str] = "box"
