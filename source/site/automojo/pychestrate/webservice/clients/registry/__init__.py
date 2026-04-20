"""
.. module:: clients.registry
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Client registry — authoritative server-side view of enrolled clients.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.clients.registry.extensions.client_attribute_extension import (
    ClientAttributeExtension,
)
from automojo.pychestrate.webservice.clients.registry.extensions.concurrency_attribute import (
    ConcurrencyAttribute,
)
from automojo.pychestrate.webservice.clients.registry.extensions.cpu_arch_attribute import (
    CpuArchAttribute,
)
from automojo.pychestrate.webservice.clients.registry.extensions.os_kind_attribute import (
    OsKindAttribute,
)
from automojo.pychestrate.webservice.extensions.registry import register_resource_extension


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
