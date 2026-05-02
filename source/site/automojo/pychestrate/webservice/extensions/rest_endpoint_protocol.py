"""
.. module:: extensions.rest_endpoint_protocol
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``RestEndpointExtension`` resource base for ``8-rest-api-v1``.

.. moduleauthor:: Automation Mojo LLC

Layer 8 publishes ``RestEndpointExtension`` as the resource base
external packs subclass to add routes under
``/api/v1/ext/<ext-name>/...``. Each subclass declares an
``ext_name`` and returns a tuple of :class:`RestEndpointDescriptor`
rows from :meth:`declare_endpoints`. The router (M2) discovers every
loaded subclass through ``ResourceExtension.__subclasses__``;
collision on ``ext_name`` / suffix is rejected at startup with
``ConfigurationError``.

The base lives under :mod:`extensions` (alongside
:class:`FactoryProtocolBase` and :class:`ResourceExtension`) rather
than under ``restapi`` so it does not depend on Flask at import time;
the M2 router can be Flask-, ASGI-, or stdlib-backed without
changing extension authoring.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import ClassVar, Tuple

from automojo.pychestrate.webservice.extensions.resource_extension import ResourceExtension


HTTP_METHOD_GET: str = "GET"
HTTP_METHOD_POST: str = "POST"
HTTP_METHOD_PUT: str = "PUT"
HTTP_METHOD_PATCH: str = "PATCH"
HTTP_METHOD_DELETE: str = "DELETE"


_VALID_HTTP_METHODS: Tuple[str, ...] = (
    HTTP_METHOD_GET,
    HTTP_METHOD_POST,
    HTTP_METHOD_PUT,
    HTTP_METHOD_PATCH,
    HTTP_METHOD_DELETE,
)


@dataclass(frozen=True)
class RestEndpointDescriptor:
    """
        Single ``method`` + ``path_suffix`` pair an extension claims.

        :param method: HTTP method (uppercase, must be one of
                       :data:`_VALID_HTTP_METHODS`).
        :param path_suffix: Path appended to the extension namespace
                            (e.g., ``"/echo"`` becomes
                            ``/api/v1/ext/<ext-name>/echo``). Must
                            start with ``/``.
        :param required_permissions: RBAC permission keys the router
                                     enforces before dispatching.
        :param required_capabilities: Sandbox capability keys the host
                                      must have granted (per
                                      ``E-extension-sandbox``).
        :param description: Operator-facing summary surfaced in the
                            catalog entry / Sphinx docs.
    """
    method: str
    path_suffix: str
    required_permissions: Tuple[str, ...]
    required_capabilities: Tuple[str, ...]
    description: str


class RestEndpointExtension(ResourceExtension):
    """
        Base class for an extension contributing REST routes.

        Subclasses set :attr:`ext_name` (segment under
        ``/api/v1/ext/``) and override :meth:`declare_endpoints` to
        return a non-empty tuple of :class:`RestEndpointDescriptor`.
    """

    resource_extension_name: ClassVar[str] = "rest_endpoint"
    ext_name: ClassVar[str] = ""

    is_published: ClassVar[bool] = True
    published_docs_url: ClassVar[str] = (
        "https://docs.pychestrate.io/plugin-api/RestEndpointExtension"
    )
    published_reference: ClassVar[str] = (
        "automojo.pychestrate.webservice.extensions.rest_endpoint_example"
        ".ExampleEchoEndpoints"
    )

    @classmethod
    def declare_endpoints(cls) -> Tuple[RestEndpointDescriptor, ...]:
        """
            Return the descriptors this extension contributes.

            :returns: Tuple of :class:`RestEndpointDescriptor`.
        """
        raise NotImplementedError("Subclasses must implement declare_endpoints")


def is_valid_http_method(*, method: str) -> bool:
    """
        Return True if ``method`` is one of the supported HTTP verbs.

        :param method: Method name (case-sensitive uppercase).

        :returns: Boolean.
    """
    rtnval = method in _VALID_HTTP_METHODS
    return rtnval
