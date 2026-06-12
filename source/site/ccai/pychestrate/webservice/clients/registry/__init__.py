"""
.. module:: clients.registry
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Client registry — authoritative server-side view of enrolled clients.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.clients.registry.extensions.client_attribute_extension import (
    ClientAttributeExtension,
)
from ccai.pychestrate.webservice.clients.registry.extensions.concurrency_attribute import (
    ConcurrencyAttribute,
)
from ccai.pychestrate.webservice.clients.registry.extensions.cpu_arch_attribute import (
    CpuArchAttribute,
)
from ccai.pychestrate.webservice.clients.registry.extensions.os_kind_attribute import (
    OsKindAttribute,
)
from ccai.pychestrate.webservice.extensions.registry import register_resource_extension


def register_builtin_extensions() -> None:
    """
        Register the in-tree ``ClientAttributeExtension`` kinds.

        :returns: None.
    """
    register_resource_extension(
        base_class=ClientAttributeExtension, extension=OsKindAttribute,
    )
    register_resource_extension(
        base_class=ClientAttributeExtension, extension=CpuArchAttribute,
    )
    register_resource_extension(
        base_class=ClientAttributeExtension, extension=ConcurrencyAttribute,
    )
    return
