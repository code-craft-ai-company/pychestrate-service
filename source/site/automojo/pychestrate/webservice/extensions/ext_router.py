"""
.. module:: extensions.ext_router
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Discover and validate :class:`RestEndpointExtension` mounts.

.. moduleauthor:: Automation Mojo LLC

The router walks every loaded :class:`RestEndpointExtension` subclass,
collects their declared :class:`RestEndpointDescriptor` rows, and
returns a :class:`MountManifest` listing every concrete route the M2
HTTP layer must mount under ``/api/v1/ext/<ext-name>/<suffix>``.

The discovery + validation surface is framework-agnostic on purpose:
it builds a manifest that any future Flask / ASGI / stdlib mount
target can consume without changing extension authoring. Two
collision rules are enforced at startup:

1. Two distinct subclasses MUST NOT share the same ``ext_name``.
2. Two descriptors within a single extension MUST NOT share the same
   ``(method, path_suffix)`` pair.

Both collisions raise ``ConfigurationError`` with a multi-line
message naming the offending classes / descriptors so operators can
trace the conflict.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple, Type

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.webservice.extensions.rest_endpoint_protocol import (
    RestEndpointDescriptor,
    RestEndpointExtension,
    is_valid_http_method,
)


EXTENSION_ROUTE_NAMESPACE_PREFIX: str = "/api/v1/ext/"


@dataclass(frozen=True)
class MountedRoute:
    """
        Single concrete route in a :class:`MountManifest`.

        :param ext_name: Owning extension's ``ext_name``.
        :param method: HTTP method.
        :param path_suffix: Per-extension suffix (always starts with ``/``).
        :param full_path: Fully-qualified path (``/api/v1/ext/<ext-name><suffix>``).
        :param handler_class: The :class:`RestEndpointExtension` subclass
                              that owns this descriptor.
        :param descriptor: Original :class:`RestEndpointDescriptor`.
    """
    ext_name: str
    method: str
    path_suffix: str
    full_path: str
    handler_class: Type[RestEndpointExtension]
    descriptor: RestEndpointDescriptor


@dataclass(frozen=True)
class MountManifest:
    """
        Frozen list of every route discovered by :func:`mount_extension_routes`.

        :param routes: Tuple of :class:`MountedRoute` ordered by
                       ``(ext_name, method, path_suffix)``.
    """
    routes: Tuple[MountedRoute, ...] = field(default_factory=tuple)


def discover_extensions() -> List[Type[RestEndpointExtension]]:
    """
        Return every loaded direct subclass of
        :class:`RestEndpointExtension`, ordered by ``ext_name`` then
        class name.

        :returns: List of subclass types.
    """
    discovered: List[Type[RestEndpointExtension]] = []
    for subclass in RestEndpointExtension.__subclasses__():
        ext_name_value = getattr(subclass, "ext_name", "")
        if ext_name_value is None or len(ext_name_value) == 0:
            continue
        discovered.append(subclass)
    discovered.sort(key=lambda cls: (cls.ext_name, cls.__qualname__))
    rtnval = discovered
    return rtnval


def _ensure_ext_name_uniqueness(
        *,
        extensions: List[Type[RestEndpointExtension]]
    ) -> None:
    """
        Refuse to mount when two subclasses share an ``ext_name``.

        :param extensions: Discovered extension classes.

        :returns: None.
        :raises: ConfigurationError on duplicate ``ext_name``.
    """
    by_name: Dict[str, List[Type[RestEndpointExtension]]] = {}
    for ext_class in extensions:
        bucket = by_name.setdefault(ext_class.ext_name, [])
        bucket.append(ext_class)

    duplicates: List[str] = []
    for ext_name, classes in sorted(by_name.items()):
        if len(classes) > 1:
            duplicates.append(ext_name)

    if len(duplicates) == 0:
        return

    err_msg_lines = ["Two RestEndpointExtension subclasses share an ext_name."]
    for ext_name in duplicates:
        class_qualnames = ", ".join(cls.__qualname__ for cls in by_name[ext_name])
        err_msg_lines.append("EXT_NAME: {}".format(ext_name))
        err_msg_lines.append("  CLASSES: {}".format(class_qualnames))
    err_msg = os.linesep.join(err_msg_lines)
    raise ConfigurationError(err_msg) from None


def _validate_descriptor(
        *,
        ext_class: Type[RestEndpointExtension],
        descriptor: RestEndpointDescriptor
    ) -> None:
    """
        Enforce the per-descriptor invariants documented on
        :class:`RestEndpointDescriptor`.

        :param ext_class: Owning extension class (used in error
                          messages).
        :param descriptor: Descriptor under validation.

        :returns: None.
        :raises: ConfigurationError on any invariant violation.
    """
    if is_valid_http_method(method=descriptor.method) is False:
        err_msg_lines = ["Unsupported HTTP method on RestEndpointDescriptor."]
        err_msg_lines.append("EXT_NAME: {}".format(ext_class.ext_name))
        err_msg_lines.append("CLASS: {}".format(ext_class.__qualname__))
        err_msg_lines.append("METHOD: {!r}".format(descriptor.method))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    if descriptor.path_suffix is None or len(descriptor.path_suffix) == 0:
        err_msg_lines = ["RestEndpointDescriptor requires a non-empty path_suffix."]
        err_msg_lines.append("EXT_NAME: {}".format(ext_class.ext_name))
        err_msg_lines.append("CLASS: {}".format(ext_class.__qualname__))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    if not descriptor.path_suffix.startswith("/"):
        err_msg_lines = ["RestEndpointDescriptor path_suffix must start with '/'."]
        err_msg_lines.append("EXT_NAME: {}".format(ext_class.ext_name))
        err_msg_lines.append("CLASS: {}".format(ext_class.__qualname__))
        err_msg_lines.append("PATH_SUFFIX: {!r}".format(descriptor.path_suffix))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None
    return


def _collect_routes_for_extension(
        *,
        ext_class: Type[RestEndpointExtension]
    ) -> List[MountedRoute]:
    """
        Build :class:`MountedRoute` rows for one extension, refusing
        any internal ``(method, path_suffix)`` collision.

        :param ext_class: Discovered extension class.

        :returns: Ordered list of :class:`MountedRoute`.
        :raises: ConfigurationError on duplicate ``(method, path_suffix)``.
    """
    descriptors = ext_class.declare_endpoints()
    if descriptors is None or len(descriptors) == 0:
        err_msg_lines = ["RestEndpointExtension declared zero endpoints."]
        err_msg_lines.append("EXT_NAME: {}".format(ext_class.ext_name))
        err_msg_lines.append("CLASS: {}".format(ext_class.__qualname__))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    seen_keys: Dict[Tuple[str, str], RestEndpointDescriptor] = {}
    routes: List[MountedRoute] = []
    for descriptor in descriptors:
        _validate_descriptor(ext_class=ext_class, descriptor=descriptor)
        key: Tuple[str, str] = (descriptor.method, descriptor.path_suffix)
        if key in seen_keys:
            err_msg_lines = [
                "Duplicate (method, path_suffix) within a single extension."
            ]
            err_msg_lines.append("EXT_NAME: {}".format(ext_class.ext_name))
            err_msg_lines.append("CLASS: {}".format(ext_class.__qualname__))
            err_msg_lines.append("METHOD: {}".format(descriptor.method))
            err_msg_lines.append("PATH_SUFFIX: {}".format(descriptor.path_suffix))
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg) from None
        seen_keys[key] = descriptor

        full_path = "{}{}{}".format(
            EXTENSION_ROUTE_NAMESPACE_PREFIX,
            ext_class.ext_name,
            descriptor.path_suffix,
        )
        routes.append(
            MountedRoute(
                ext_name=ext_class.ext_name,
                method=descriptor.method,
                path_suffix=descriptor.path_suffix,
                full_path=full_path,
                handler_class=ext_class,
                descriptor=descriptor,
            )
        )

    routes.sort(key=lambda r: (r.method, r.path_suffix))
    rtnval = routes
    return rtnval


def mount_extension_routes(
        *,
        extensions: Optional[Sequence[Type[RestEndpointExtension]]] = None
    ) -> MountManifest:
    """
        Discover every loaded :class:`RestEndpointExtension`, validate
        per-extension descriptors, refuse cross-extension ``ext_name``
        collisions, and return a frozen mount manifest.

        :param extensions: Optional override list of extension classes
                           to mount. ``None`` triggers
                           :func:`discover_extensions`. Tests inject
                           synthetic class lists here to exercise
                           collision and invariant paths without
                           polluting the ``RestEndpointExtension``
                           subclass tree.

        :returns: :class:`MountManifest`.
        :raises: ConfigurationError on any collision or invariant
                 violation.
    """
    if extensions is None:
        resolved_extensions: List[Type[RestEndpointExtension]] = discover_extensions()
    else:
        resolved_extensions = list(extensions)
    _ensure_ext_name_uniqueness(extensions=resolved_extensions)

    all_routes: List[MountedRoute] = []
    for ext_class in resolved_extensions:
        all_routes.extend(_collect_routes_for_extension(ext_class=ext_class))

    all_routes.sort(key=lambda r: (r.ext_name, r.method, r.path_suffix))
    rtnval = MountManifest(routes=tuple(all_routes))
    return rtnval


def manifest_to_jsonable(*, manifest: MountManifest) -> List[Dict]:
    """
        Render a :class:`MountManifest` as a list of JSON-friendly
        dicts. Used by diagnostic endpoints and tests.

        :param manifest: Frozen :class:`MountManifest`.

        :returns: List of dicts (one per :class:`MountedRoute`).
    """
    rendered: List[Dict] = []
    for route in manifest.routes:
        rendered.append(
            {
                "ext_name": route.ext_name,
                "method": route.method,
                "path_suffix": route.path_suffix,
                "full_path": route.full_path,
                "handler_class": route.handler_class.__qualname__,
                "required_permissions": list(route.descriptor.required_permissions),
                "required_capabilities": list(route.descriptor.required_capabilities),
                "description": route.descriptor.description,
            }
        )
    rtnval = rendered
    return rtnval
