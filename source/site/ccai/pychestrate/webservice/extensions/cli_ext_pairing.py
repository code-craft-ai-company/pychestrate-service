"""
.. module:: extensions.cli_ext_pairing
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Pair ``pyc ext`` verbs with the extension routes this
               process mounts.

.. moduleauthor:: Code Craft AI LLC

An extension pack contributes both halves of ``pyc ext <ext-name>
<verb>``: a :class:`CLISubcommandExtension` descriptor (the verb and
its arguments, on the CLI side) and a :class:`RestEndpointExtension`
route (``/api/v1/ext/<ext-name>/<verb>``, on the server side). The
pairing convention is ``path_suffix == "/<verb>"``.

The ``pyc`` CLI itself resolves routes from the server's
``GET /api/v1/ext`` listing (see :mod:`ccai.pychestrate.cli.extensions.discovery`)
and must not import service modules -- it is also packaged on its own,
standard library only. This module keeps the in-process walk of both
subclass trees for the service, its tests and tooling that check a
pack's two halves agree.
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
from ccai.pychestrate.cli.extensions.discovery import (
    find_descriptor,
    find_subcommand_class,
)
from ccai.pychestrate.webservice.extensions.ext_router import (
    MountedRoute,
    mount_extension_routes,
)


@dataclass(frozen=True)
class ResolvedExtCommand:
    """
        Bundle returned by :func:`resolve_ext_command` carrying every
        piece needed to drive a single ``pyc ext`` call in-process.

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
        ``pyc ext <ext_name> <verb>`` invocation in this process.

        :param ext_name: ``ext_name`` segment under ``pyc ext``.
        :param verb: Subcommand verb supplied on the command line.

        :returns: Populated :class:`ResolvedExtCommand` when both
                  halves resolve; ``None`` when either lookup misses.
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


__all__ = [
    "ResolvedExtCommand",
    "find_mounted_route_for_verb",
    "resolve_ext_command",
]
