"""
.. module:: pods
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Layer-3 pod specs (definitions, lifecycle, static, topology,
               scoped-config, dynamic) bundled into a single feature package.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
    register_resource_extension,
)
from ccai.pychestrate.webservice.pods.extensions.member_kind import (
    LinuxHost,
    NetworkSwitch,
    PodMemberKindExtension,
    SyntheticRole,
)
from ccai.pychestrate.webservice.pods.extensions.renderer import (
    GenericRenderer,
    LinuxHostRenderer,
    NetworkSwitchRenderer,
    PodMemberRendererExtension,
)
from ccai.pychestrate.webservice.pods.factories.integrity_validator import (
    IntegrityValidator,
)
from ccai.pychestrate.webservice.pods.factories.libvirt_provisioner import (
    LibvirtProvisioner,
)


def register_builtin_extensions() -> None:
    """
        Register the in-tree Layer-3 pod extensions:

        - ``PodSpecValidatorProtocol`` — :class:`IntegrityValidator`.
        - ``PodProvisionerProtocol`` — :class:`LibvirtProvisioner`.
        - ``PodMemberKindExtension`` — LinuxHost, NetworkSwitch, SyntheticRole.
        - ``PodMemberRendererExtension`` — LinuxHostRenderer,
          NetworkSwitchRenderer, GenericRenderer.

        :returns: None.
    """
    register_factory_implementation(implementation=IntegrityValidator)
    register_factory_implementation(implementation=LibvirtProvisioner)
    register_resource_extension(base_class=PodMemberKindExtension, extension=LinuxHost)
    register_resource_extension(base_class=PodMemberKindExtension, extension=NetworkSwitch)
    register_resource_extension(base_class=PodMemberKindExtension, extension=SyntheticRole)
    register_resource_extension(base_class=PodMemberRendererExtension, extension=LinuxHostRenderer)
    register_resource_extension(base_class=PodMemberRendererExtension, extension=NetworkSwitchRenderer)
    register_resource_extension(base_class=PodMemberRendererExtension, extension=GenericRenderer)
    return
