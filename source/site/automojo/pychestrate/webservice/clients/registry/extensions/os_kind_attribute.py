"""
.. module:: clients.registry.extensions.os_kind_attribute
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``os`` client attribute — operating system family + version.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.clients.registry.extensions.client_attribute_extension import (
    ClientAttributeExtension,
)


class OsKindAttribute(ClientAttributeExtension):
    """
        Reports operating system family + version the agent runs on.
    """

    resource_extension_name: str = "client_attribute_extension"
    attribute_kind_name: str = "os"
    display_label: str = "Operating System"
    searchable: bool = True
    value_schema: dict = {
        "type": "object",
        "required": ["family", "version"],
        "properties": {
            "family": {"enum": ["linux", "macos", "windows", "other"]},
            "version": {"type": "string", "minLength": 1, "maxLength": 128},
        },
        "additionalProperties": False,
    }
