"""
.. module:: extensions.registry
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: In-process registry for factory protocols and resource extensions.

.. moduleauthor:: Code Craft AI LLC

Provides the ``SuperFactory``-style lookups used by Pychestrate services to
resolve extension implementations. The registry is explicit: Phase 0.5
tasks register reference implementations with
:func:`register_factory_implementation` and
:func:`register_resource_extension`; on-disk discovery of external
``pychestrate-ext-<name>`` packages is deferred to a later milestone.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import threading

from typing import Callable, Dict, List, Optional, Tuple, Type

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase
from ccai.pychestrate.webservice.extensions.resource_extension import ResourceExtension


_REGISTRY_LOCK = threading.RLock()
_FACTORY_IMPLEMENTATIONS: Dict[str, List[Type[FactoryProtocolBase]]] = {}
_RESOURCE_EXTENSIONS: Dict[Type[ResourceExtension], List[Type[ResourceExtension]]] = {}


def register_factory_implementation(*, implementation: Type[FactoryProtocolBase]) -> None:
    """
        Register a concrete :class:`FactoryProtocolBase` implementation.

        :param implementation: The concrete implementation class.

        :returns: None.
        :raises: ConfigurationError if the class does not declare ``factory_protocol_name``.
    """
    protocol_name = getattr(implementation, "factory_protocol_name", "")
    if protocol_name is None or len(protocol_name) == 0:
        err_msg_lines = ["Cannot register factory implementation with empty 'factory_protocol_name'."]
        err_msg_lines.append("IMPLEMENTATION: {}".format(implementation.__qualname__))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg)

    with _REGISTRY_LOCK:
        bucket = _FACTORY_IMPLEMENTATIONS.setdefault(protocol_name, [])
        if implementation in bucket:
            return
        bucket.append(implementation)
        bucket.sort(key=lambda impl: getattr(impl, "PRECEDENCE", 1000))

    return


def unregister_factory_implementation(*, implementation: Type[FactoryProtocolBase]) -> None:
    """
        Remove a previously registered factory implementation.

        :param implementation: The class that was registered.

        :returns: None.
    """
    protocol_name = getattr(implementation, "factory_protocol_name", "")
    with _REGISTRY_LOCK:
        bucket = _FACTORY_IMPLEMENTATIONS.get(protocol_name, None)
        if bucket is None:
            return
        if implementation in bucket:
            bucket.remove(implementation)

    return


def list_factory_implementations(*, factory_protocol_name: str) -> Tuple[Type[FactoryProtocolBase], ...]:
    """
        Return the ordered tuple of implementations for a named protocol.

        :param factory_protocol_name: The protocol name declared by the base class.

        :returns: Tuple of implementation classes ordered by PRECEDENCE (ascending).
    """
    with _REGISTRY_LOCK:
        bucket = _FACTORY_IMPLEMENTATIONS.get(factory_protocol_name, [])
        rtnval = tuple(bucket)

    return rtnval


def resolve_factory_implementation(
        *,
        factory_protocol_name: str,
        predicate: Optional[Callable[[Type[FactoryProtocolBase]], bool]]
    ) -> Type[FactoryProtocolBase]:
    """
        Return the highest-priority implementation matching the predicate.

        :param factory_protocol_name: The protocol name declared by the base class.
        :param predicate: Optional callable used to filter implementations. When None,
                          the first registered implementation is returned.

        :returns: The resolved implementation class.
        :raises: ConfigurationError when no implementation matches.
    """
    with _REGISTRY_LOCK:
        bucket = _FACTORY_IMPLEMENTATIONS.get(factory_protocol_name, [])
        candidates = list(bucket)

    matched: Optional[Type[FactoryProtocolBase]] = None
    for impl in candidates:
        if predicate is None:
            matched = impl
            break
        if predicate(impl) is True:
            matched = impl
            break

    if matched is None:
        err_msg_lines = ["No implementation found for factory protocol."]
        err_msg_lines.append("PROTOCOL: {}".format(factory_protocol_name))
        err_msg_lines.append("CANDIDATES: {}".format(len(candidates)))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg)

    return matched


def register_resource_extension(*, base_class: Type[ResourceExtension], extension: Type[ResourceExtension]) -> None:
    """
        Register a concrete resource extension under its declared base class.

        :param base_class: The :class:`ResourceExtension` subclass declaring the category.
        :param extension: The concrete subclass contributing a kind.

        :returns: None.
    """
    with _REGISTRY_LOCK:
        bucket = _RESOURCE_EXTENSIONS.setdefault(base_class, [])
        if extension in bucket:
            return
        bucket.append(extension)

    return


def list_resource_extensions(*, base_class: Type[ResourceExtension]) -> Tuple[Type[ResourceExtension], ...]:
    """
        Return the registered resource extensions for a given category.

        :param base_class: The resource extension category.

        :returns: Tuple of concrete extension classes in registration order.
    """
    with _REGISTRY_LOCK:
        bucket = _RESOURCE_EXTENSIONS.get(base_class, [])
        rtnval = tuple(bucket)

    return rtnval


def reset_registry_for_testing() -> None:
    """
        Clear both registries. Intended for use by the test suite only.

        :returns: None.
    """
    with _REGISTRY_LOCK:
        _FACTORY_IMPLEMENTATIONS.clear()
        _RESOURCE_EXTENSIONS.clear()

    return
