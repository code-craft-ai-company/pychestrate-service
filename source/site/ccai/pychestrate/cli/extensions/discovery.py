"""
.. module:: cli.extensions.discovery
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``pyc ext <ext-name> <verb>`` discovery helpers.

.. moduleauthor:: Code Craft AI LLC

When the CLI dispatcher sees a ``pyc ext <ext-name> <verb>``
invocation it needs two lookups:

1. ``(ext_name, verb)`` -> :class:`CLISubcommandDescriptor` from a
   loaded :class:`CLISubcommandExtension` subclass — names the
   wrapped REST ``operation_id`` and the descriptor's positional /
   flag argument lists.
2. ``(ext_name, verb)`` -> :class:`MountedRoute` from the live
   ext-router manifest — names the HTTP method and the
   ``/api/v1/ext/<ext_name><path_suffix>`` URL.

This module performs both walks. The pairing convention M1 enforces
is ``path_suffix == "/<verb>"`` — a CLI verb maps directly to its
REST suffix segment. Subcommands declaring a path that does not
follow the convention surface a clear lookup miss rather than a
silent dispatch.

The walks happen against the live subclass trees (the same path
``mount_extension_routes`` and ``build_catalog`` use), so production
runtimes and tests share the discovery code path. Tests inject
synthetic class lists where needed via the existing
``mount_extension_routes(extensions=...)`` seam.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Optional, Type

from ccai.pychestrate.cli.extensions.cli_subcommand import (
    CLISubcommandDescriptor,
    CLISubcommandExtension,
)
from ccai.pychestrate.webservice.extensions.ext_router import (
    MountedRoute,
    mount_extension_routes,
)


@dataclass(frozen=True)
class ResolvedExtCommand:
    """
        Bundle returned by :func:`resolve_ext_command` carrying every
        piece the dispatcher needs to drive a single ``pyc ext`` call.

        :param ext_name: ``ext_name`` segment under ``pyc ext``.
        :param verb: Subcommand verb supplied on the command line.
        :param subcommand_class: Concrete
                                 :class:`CLISubcommandExtension`
                                 subclass declaring the verb.
        :param descriptor: The matching :class:`CLISubcommandDescriptor`.
        :param mounted_route: The matching :class:`MountedRoute` from
                              the ext-router manifest. Carries the
                              HTTP method and the full URL.
    """
    ext_name: str
    verb: str
    subcommand_class: Type[CLISubcommandExtension]
    descriptor: CLISubcommandDescriptor
    mounted_route: MountedRoute


def find_subcommand_class(*, ext_name: str) -> Optional[Type[CLISubcommandExtension]]:
    """
        Return the loaded :class:`CLISubcommandExtension` subclass for
        ``ext_name``, or ``None`` when no extension claims it.

        :param ext_name: ``ext_name`` segment under ``pyc ext``.

        :returns: Concrete subclass type or None.
    """
    for subclass in CLISubcommandExtension.__subclasses__():
        if getattr(subclass, "ext_name", "") == ext_name:
            rtnval: Optional[Type[CLISubcommandExtension]] = subclass
            return rtnval
    rtnval = None
    return rtnval


def find_descriptor(
        *,
        subcommand_class: Type[CLISubcommandExtension],
        verb: str
    ) -> Optional[CLISubcommandDescriptor]:
    """
        Return the descriptor declaring ``verb`` on
        ``subcommand_class``, or ``None`` on miss.

        :param subcommand_class: Concrete subclass type.
        :param verb: Subcommand verb to look up.

        :returns: :class:`CLISubcommandDescriptor` or None.
    """
    for descriptor in subcommand_class.declare_subcommands():
        if descriptor.verb == verb:
            rtnval: Optional[CLISubcommandDescriptor] = descriptor
            return rtnval
    rtnval = None
    return rtnval


def find_mounted_route_for_verb(
        *,
        ext_name: str,
        verb: str
    ) -> Optional[MountedRoute]:
    """
        Return the :class:`MountedRoute` whose ``ext_name`` and
        ``path_suffix`` match the convention ``"/<verb>"``.

        :param ext_name: ``ext_name`` segment under ``pyc ext``.
        :param verb: Subcommand verb (without leading slash).

        :returns: :class:`MountedRoute` or None.
    """
    expected_path_suffix = "/{}".format(verb)
    manifest = mount_extension_routes(extensions=None)
    for route in manifest.routes:
        if route.ext_name == ext_name and route.path_suffix == expected_path_suffix:
            rtnval: Optional[MountedRoute] = route
            return rtnval
    rtnval = None
    return rtnval


def resolve_ext_command(
        *,
        ext_name: str,
        verb: str
    ) -> Optional[ResolvedExtCommand]:
    """
        Look up the descriptor + mounted route pair for a
        ``pyc ext <ext_name> <verb>`` invocation.

        :param ext_name: ``ext_name`` segment under ``pyc ext``.
        :param verb: Subcommand verb supplied on the command line.

        :returns: Populated :class:`ResolvedExtCommand` when both
                  halves resolve; ``None`` when either lookup misses
                  (the dispatcher renders a tailored diagnostic in
                  that case).
    """
    subcommand_class = find_subcommand_class(ext_name=ext_name)
    if subcommand_class is None:
        rtnval: Optional[ResolvedExtCommand] = None
        return rtnval

    descriptor = find_descriptor(subcommand_class=subcommand_class, verb=verb)
    if descriptor is None:
        rtnval = None
        return rtnval

    mounted_route = find_mounted_route_for_verb(ext_name=ext_name, verb=verb)
    if mounted_route is None:
        rtnval = None
        return rtnval

    rtnval = ResolvedExtCommand(
        ext_name=ext_name,
        verb=verb,
        subcommand_class=subcommand_class,
        descriptor=descriptor,
        mounted_route=mounted_route,
    )
    return rtnval
