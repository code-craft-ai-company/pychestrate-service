"""
.. module:: extensions.rest_endpoint_example
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference :class:`RestEndpointExtension` shipped in-tree.

.. moduleauthor:: Code Craft AI LLC

Contributes a minimal ``GET /api/v1/ext/example/echo`` returning
``{"message": ...}``. Serves as the published reference for
``RestEndpointExtension`` so external authors can copy the shape: a
descriptor names its handler (``handler_name``) and the host mounts the
route at startup.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, ClassVar, Tuple

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
        handler_name="handle_echo",
    )

    @classmethod
    def declare_endpoints(cls) -> Tuple[RestEndpointDescriptor, ...]:
        rtnval: Tuple[RestEndpointDescriptor, ...] = (cls._ECHO_DESCRIPTOR,)
        return rtnval

    @classmethod
    def handle_echo(cls, *, request: Any) -> dict:
        """
            Serve ``GET /api/v1/ext/example/echo?message=...``.

            :param request: The webworks request.

            :returns: Dictionary with the echoed message.
        """
        message = request.query_params.get("message", "")
        rtnval = cls.echo(message=str(message) if message is not None else "")
        return rtnval

    @classmethod
    def echo(cls, *, message: str) -> dict:
        """
            The echo itself, separate from request parsing so it can be
            called directly.

            :param message: Caller-supplied message string.

            :returns: Dictionary with the echoed message.
        """
        rtnval = {"message": message}
        return rtnval
