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
   flag argument lists (:func:`find_subcommand_class`,
   :func:`find_descriptor`).
2. ``(ext_name, verb)`` -> the route the server mounts, from the
   server's own ``GET /api/v1/ext`` listing
   (:func:`parse_ext_listing` / :func:`find_listed_route`). The pairing
   convention is ``path_suffix == "/<verb>"`` — a CLI verb maps
   directly to its REST suffix segment.

The CLI process is not the server: the extension packs installed next
to ``pyc`` need not be the ones the server loaded, so the route half
always comes from the server's listing. The in-process walk of the
service's own route manifest lives with the service
(:mod:`ccai.pychestrate.webservice.extensions.cli_ext_pairing`); this
module imports nothing outside the standard library and the CLI
package.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Any, List, Optional, Tuple, Type

from ccai.pychestrate.cli.extensions.cli_subcommand import (
    CLISubcommandDescriptor,
    CLISubcommandExtension,
)


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


@dataclass(frozen=True)
class ListedExtRoute:
    """
        One route from the server's ``GET /api/v1/ext`` listing.

        :param ext_name: Owning extension's ``ext_name``.
        :param method: HTTP method.
        :param path_suffix: Per-extension suffix (``/echo``).
        :param full_path: ``/api/v1/ext/<ext_name><suffix>``.
    """
    ext_name: str
    method: str
    path_suffix: str
    full_path: str


def parse_ext_listing(*, body: Any) -> Tuple[List[ListedExtRoute], Optional[str]]:
    """
        Parse the server's extension listing. Accepts the
        ``{"items": [...], "dynamic_mount": ...}`` shape of
        ``/api/v1/ext`` and the bare list of
        ``/api/v1/plugin-api/_meta/mounts``.

        :param body: Decoded response body.

        :returns: ``(routes, dynamic_mount)``; ``dynamic_mount`` is the
                  server's statement about whether it serves the
                  listed routes (``"deferred"`` when it does not yet).
    """
    items: Any = body
    dynamic_mount: Optional[str] = None
    if isinstance(body, dict):
        items = body.get("items", [])
        raw_mount = body.get("dynamic_mount", None)
        dynamic_mount = str(raw_mount) if raw_mount is not None else None
    routes: List[ListedExtRoute] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            routes.append(
                ListedExtRoute(
                    ext_name=str(item.get("ext_name", "")),
                    method=str(item.get("method", "GET")).upper(),
                    path_suffix=str(item.get("path_suffix", "")),
                    full_path=str(item.get("full_path", "")),
                )
            )
    rtnval = (routes, dynamic_mount)
    return rtnval


def find_listed_route(
        *,
        routes: List[ListedExtRoute],
        ext_name: str,
        verb: str
    ) -> Optional[ListedExtRoute]:
    """
        The listed route for ``pyc ext <ext_name> <verb>`` (suffix
        ``/<verb>``), or ``None``.

        :param routes: Parsed listing.
        :param ext_name: Extension name.
        :param verb: Subcommand verb.

        :returns: Route or ``None``.
    """
    expected_suffix = "/{}".format(verb)
    for route in routes:
        if route.ext_name == ext_name and route.path_suffix == expected_suffix:
            return route
    return None


__all__ = [
    "ListedExtRoute",
    "find_descriptor",
    "find_listed_route",
    "find_subcommand_class",
    "parse_ext_listing",
]
