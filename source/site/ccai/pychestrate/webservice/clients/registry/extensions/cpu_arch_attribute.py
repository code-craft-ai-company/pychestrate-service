"""
.. module:: clients.registry.extensions.cpu_arch_attribute
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``cpu_arch`` client attribute — reported CPU architecture.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.clients.registry.extensions.client_attribute_extension import (
    ClientAttributeExtension,
)


class CpuArchAttribute(ClientAttributeExtension):
    """
        Reports the agent host's CPU architecture.
    """

    resource_extension_name: str = "client_attribute_extension"
    attribute_kind_name: str = "cpu_arch"
    display_label: str = "CPU Architecture"
    searchable: bool = True
    value_schema: dict = {
        "type": "string",
        "enum": ["x86_64", "arm64", "riscv64", "other"],
    }
