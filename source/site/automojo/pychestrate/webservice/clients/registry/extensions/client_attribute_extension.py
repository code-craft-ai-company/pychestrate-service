"""
.. module:: clients.registry.extensions.client_attribute_extension
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ResourceExtension base declaring a client attribute kind.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, ClassVar, Dict

from automojo.pychestrate.webservice.extensions.resource_extension import ResourceExtension


class ClientAttributeExtension(ResourceExtension):
    """
        Base class declaring a single typed attribute kind. Subclasses set:

        - ``attribute_kind_name``: canonical key (``"os"``, ``"cpu_arch"``, ...).
        - ``value_schema``: JSON-schema dict the registry validates
          submitted values against.
        - ``display_label``: human-facing label for UI use.
        - ``searchable``: hint that the attribute should be indexed for
          filtered queries (operators may choose to honor this).
    """

    resource_extension_name: ClassVar[str] = "client_attribute_extension"
    attribute_kind_name: ClassVar[str] = ""
    value_schema: ClassVar[Dict[str, Any]] = {}
    display_label: ClassVar[str] = ""
    searchable: ClassVar[bool] = False
