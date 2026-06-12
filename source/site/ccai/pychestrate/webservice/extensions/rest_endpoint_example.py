"""
.. module:: extensions.rest_endpoint_example
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference :class:`RestEndpointExtension` shipped in-tree.

.. moduleauthor:: Code Craft AI LLC

Contributes a minimal ``GET /api/v1/ext/example/echo`` returning
``{"message": ...}``. Serves as the published reference for
``RestEndpointExtension`` so external authors can copy the shape; the
M2 router uses the descriptors here to verify discovery + dispatch
end-to-end.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import ClassVar, Tuple

from ccai.pychestrate.webservice.extensions.rest_endpoint_protocol import (
    HTTP_METHOD_GET,
    RestEndpointDescriptor,
    RestEndpointExtension,
)


class ExampleEchoEndpoints(RestEndpointExtension):
    """
        Reference :class:`RestEndpointExtension` exposing
        ``GET /api/v1/ext/example/echo``.
    """

    ext_name: ClassVar[str] = "example"

    _ECHO_DESCRIPTOR: ClassVar[RestEndpointDescriptor] = RestEndpointDescriptor(
        method=HTTP_METHOD_GET,
        path_suffix="/echo",
        required_permissions=tuple(),
        required_capabilities=tuple(),
        description="Echo the caller-supplied 'message' query parameter back.",
    )

    @classmethod
    def declare_endpoints(cls) -> Tuple[RestEndpointDescriptor, ...]:
        rtnval: Tuple[RestEndpointDescriptor, ...] = (cls._ECHO_DESCRIPTOR,)
        return rtnval

    @classmethod
    def echo(cls, *, message: str) -> dict:
        """
            Reference handler used once the M2 router is wired.

            :param message: Caller-supplied message string.

            :returns: Dictionary with the echoed message.
        """
        rtnval = {"message": message}
        return rtnval
