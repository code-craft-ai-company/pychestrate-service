"""
.. module:: extensions.rest_endpoint_protocol
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``RestEndpointExtension`` resource base for ``8-rest-api-v1``.

.. moduleauthor:: Code Craft AI LLC

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
than under ``restapi`` so it does not depend on a specific web
framework at import time; the M2 router can be webworks-, ASGI-,
or stdlib-backed without changing extension authoring.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Any, Callable, ClassVar, Optional, Tuple

from ccai.pychestrate.webservice.extensions.resource_extension import ResourceExtension


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
        :param handler_name: Name of the extension's classmethod that
                             serves the route. The host calls it as
                             ``handler(request=request)``; it returns a
                             JSON-serializable value (answered 200) or a
                             webworks ``Response``. A descriptor without
                             one is listed but not mounted, unless the
                             extension overrides
                             :meth:`RestEndpointExtension.handle_request`.
    """
    method: str
    path_suffix: str
    required_permissions: Tuple[str, ...]
    required_capabilities: Tuple[str, ...]
    description: str
    handler_name: str = ""


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
        "ccai.pychestrate.webservice.extensions.rest_endpoint_example"
        ".ExampleEchoEndpoints"
    )

    @classmethod
    def declare_endpoints(cls) -> Tuple[RestEndpointDescriptor, ...]:
        """
            Return the descriptors this extension contributes.

            :returns: Tuple of :class:`RestEndpointDescriptor`.
        """
        raise NotImplementedError("Subclasses must implement declare_endpoints")

    @classmethod
    def handle_request(cls, *, descriptor: RestEndpointDescriptor, request: Any) -> Any:
        """
            Serve one request for ``descriptor``. The host has already
            checked the caller's authentication, the descriptor's
            ``required_permissions`` and the extension's capability grants.
            The default calls the classmethod named by
            ``descriptor.handler_name`` with ``request=request``; override
            it to dispatch some other way.

            :param descriptor: The descriptor of the route being served.
            :param request: The webworks request.

            :returns: A JSON-serializable value or a webworks ``Response``.
            :raises: NotImplementedError when the descriptor names no
                     handler the extension has.
        """
        handler = _named_handler(ext_class=cls, descriptor=descriptor)
        if handler is None:
            err_msg = "{} declares no handler for {} {}.".format(
                cls.__qualname__, descriptor.method, descriptor.path_suffix,
            )
            raise NotImplementedError(err_msg)
        rtnval = handler(request=request)
        return rtnval

    @classmethod
    def serves(cls, *, descriptor: RestEndpointDescriptor) -> bool:
        """
            Whether the host can mount ``descriptor``: the extension names a
            handler it has, or overrides :meth:`handle_request`.

            :param descriptor: One of this extension's descriptors.

            :returns: Boolean.
        """
        overridden = cls.handle_request.__func__ is not RestEndpointExtension.handle_request.__func__
        rtnval = overridden or _named_handler(ext_class=cls, descriptor=descriptor) is not None
        return rtnval


def _named_handler(*, ext_class: type, descriptor: RestEndpointDescriptor) -> Optional[Callable[..., Any]]:
    """
        The callable ``descriptor.handler_name`` names on ``ext_class``, or
        ``None``.
    """
    if len(descriptor.handler_name or "") == 0:
        return None
    candidate = getattr(ext_class, descriptor.handler_name, None)
    rtnval = candidate if callable(candidate) else None
    return rtnval


def is_valid_http_method(*, method: str) -> bool:
    """
        Return True if ``method`` is one of the supported HTTP verbs.

        :param method: Method name (case-sensitive uppercase).

        :returns: Boolean.
    """
    rtnval = method in _VALID_HTTP_METHODS
    return rtnval
