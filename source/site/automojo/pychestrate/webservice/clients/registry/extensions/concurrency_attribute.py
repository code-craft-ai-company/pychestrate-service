"""
.. module:: clients.registry.extensions.concurrency_attribute
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``concurrency`` client attribute — max/current run capacity.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.clients.registry.extensions.client_attribute_extension import (
    ClientAttributeExtension,
)


class ConcurrencyAttribute(ClientAttributeExtension):
    """
        Reports how many jobs the agent can run in parallel and how many
        are currently occupied.
    """

    resource_extension_name: str = "client_attribute_extension"
    attribute_kind_name: str = "concurrency"
    display_label: str = "Concurrency"
    searchable: bool = False
    value_schema: dict = {
        "type": "object",
        "required": ["max_runs", "current_runs"],
        "properties": {
            "max_runs": {"type": "integer", "minimum": 0, "maximum": 65535},
            "current_runs": {"type": "integer", "minimum": 0, "maximum": 65535},
        },
        "additionalProperties": False,
    }
