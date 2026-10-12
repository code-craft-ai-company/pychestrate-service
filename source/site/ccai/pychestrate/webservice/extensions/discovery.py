"""
.. module:: extensions.discovery
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Load extension packs that are installed next to the service (DOC-11).

.. moduleauthor:: Code Craft AI LLC

The extension guide promised extension points that teams can use "without
forking the service", but the only way to load a pack was to edit the service's
bootstrap code and call the pack's ``register()`` there. This module removes the
edit: a pack declares an *entry point* in the group ``pychestrate.extensions``
in its own ``pyproject.toml``,

.. code-block:: toml

    [tool.poetry.plugins."pychestrate.extensions"]
    my_pack = "my_pack_module:register"

and the service, once the in-tree extensions are registered, imports each
declared object and calls it with no arguments. Installing the pack is what turns
it on; nothing else in the service changes.

A pack runs arbitrary code inside the service, exactly as any installed package
does, so an operator installs only packs they trust. One pack that fails to load
must not stop the others, or (by default) the service: the failure is logged with
the pack's name and reported in the result, and the rest load. An operator who
wants a failure to stop the service sets ``PYCHESTRATE_EXTENSIONS_STRICT=1``;
one who wants none loaded sets ``PYCHESTRATE_LOAD_EXTENSIONS=0``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from dataclasses import dataclass
from importlib import metadata
from typing import Any, Callable, Dict, Iterable, List, Optional


_LOGGER = logging.getLogger(__name__)


#: The entry-point group an extension pack declares.
EXTENSION_ENTRY_POINT_GROUP: str = "pychestrate.extensions"

#: ``0`` (or ``false``/``no``/``off``) turns discovery off.
LOAD_EXTENSIONS_VARIABLE: str = "PYCHESTRATE_LOAD_EXTENSIONS"

#: ``1`` (or ``true``/``yes``/``on``) makes a pack that fails to load stop the service.
STRICT_EXTENSIONS_VARIABLE: str = "PYCHESTRATE_EXTENSIONS_STRICT"

#: What the last discovery did, for the admin pages and ``GET /api/v1/ext``.
_LOAD_REPORT: Dict[str, Any] = {"enabled": True, "packs": []}

_TRUE_WORDS = ("1", "true", "yes", "on")
_FALSE_WORDS = ("0", "false", "no", "off")


@dataclass(frozen=True)
class ExtensionLoadResult:
    """
        What became of one declared extension pack.

        :ivar name: The entry point's name (the key in the pack's ``pyproject.toml``).
        :ivar target: The ``module:attribute`` it points at.
        :ivar loaded: ``True`` when it was imported and its ``register`` ran.
        :ivar error: The failure, as ``ExceptionType: message``, when it did not.
    """
    name: str
    target: str
    loaded: bool
    error: str = ""


class ExtensionLoadError(RuntimeError):
    """Raised in strict mode when a pack does not load; carries the results."""


def discovery_enabled() -> bool:
    """
        Whether the service should look for installed packs. On unless
        ``PYCHESTRATE_LOAD_EXTENSIONS`` is one of ``0``, ``false``, ``no``, ``off``.

        :returns: ``True`` when discovery should run.
    """
    value = os.environ.get(LOAD_EXTENSIONS_VARIABLE, "").strip().lower()
    rtnval = value not in _FALSE_WORDS
    return rtnval


def strict_mode() -> bool:
    """
        Whether a pack that fails to load should stop the service (``PYCHESTRATE_EXTENSIONS_STRICT``
        is ``1``, ``true``, ``yes`` or ``on``).

        :returns: ``True`` in strict mode.
    """
    value = os.environ.get(STRICT_EXTENSIONS_VARIABLE, "").strip().lower()
    rtnval = value in _TRUE_WORDS
    return rtnval


def load_report() -> Dict[str, Any]:
    """
        What the last :func:`discover_and_register_extensions` did, as plain data.

        :returns: ``{"enabled": bool, "packs": [{"name", "target", "loaded", "error"}, ...]}``;
                  ``enabled`` is ``False`` when discovery was turned off, and ``packs`` is
                  empty before discovery has run or when nothing is installed.
    """
    rtnval: Dict[str, Any] = {
        "enabled": bool(_LOAD_REPORT["enabled"]),
        "packs": [dict(pack) for pack in _LOAD_REPORT["packs"]],
    }
    return rtnval


def reset_load_report_for_testing() -> None:
    """Forget the last discovery (tests only)."""
    _LOAD_REPORT["enabled"] = True
    _LOAD_REPORT["packs"] = []
    return


def _remember(*, enabled: bool, results: List["ExtensionLoadResult"]) -> None:
    """Keep what discovery did so the admin pages can show it."""
    _LOAD_REPORT["enabled"] = enabled
    _LOAD_REPORT["packs"] = [
        {"name": result.name, "target": result.target, "loaded": result.loaded, "error": result.error}
        for result in results
    ]
    return


def _installed_entry_points() -> Iterable[Any]:
    """The installed entry points of the extension group, ordered by name."""
    found = metadata.entry_points(group=EXTENSION_ENTRY_POINT_GROUP)
    rtnval = sorted(found, key=lambda entry: entry.name)
    return rtnval


def discover_and_register_extensions(
        *,
        entry_points: Optional[Iterable[Any]] = None,
        strict: Optional[bool] = None
    ) -> List[ExtensionLoadResult]:
    """
        Import every installed extension pack that declares the
        ``pychestrate.extensions`` entry point and call its ``register`` function.

        :param entry_points: The entry points to load; ``None`` reads the installed
                             ones (tests pass their own).
        :param strict: Stop at the first pack that fails to load; ``None`` follows
                       ``PYCHESTRATE_EXTENSIONS_STRICT``.

        :returns: One :class:`ExtensionLoadResult` per declared pack, in name order;
                  empty when discovery is turned off or nothing is installed.
        :raises ExtensionLoadError: In strict mode, when a pack fails to load.
    """
    if discovery_enabled() is False:
        _LOGGER.info("pychestrate.extensions.discovery_disabled: %s is off.", LOAD_EXTENSIONS_VARIABLE)
        _remember(enabled=False, results=[])
        return []

    stop_on_failure = strict_mode() if strict is None else strict
    candidates = list(entry_points) if entry_points is not None else list(_installed_entry_points())
    results: List[ExtensionLoadResult] = []
    for entry in candidates:
        name = str(entry.name)
        target = str(getattr(entry, "value", ""))
        try:
            register: Callable[[], Any] = entry.load()
            if callable(register) is False:
                raise TypeError("entry point '{}' does not point at a callable".format(name))
            register()
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as xcpt:  # noqa: BLE001 -- ccai errors are BaseException subclasses
            failure = "{}: {}".format(type(xcpt).__name__, xcpt)
            results.append(ExtensionLoadResult(name=name, target=target, loaded=False, error=failure))
            _LOGGER.error("pychestrate.extensions.load_failed: name=%s target=%s error=%s", name, target, failure)
            if stop_on_failure is True:
                _remember(enabled=True, results=results)
                raise ExtensionLoadError(
                    "Extension '{}' ({}) failed to load and {} is set: {}".format(
                        name, target, STRICT_EXTENSIONS_VARIABLE, failure)
                ) from xcpt
            continue
        results.append(ExtensionLoadResult(name=name, target=target, loaded=True))
        _LOGGER.info("pychestrate.extensions.loaded: name=%s target=%s", name, target)

    _remember(enabled=True, results=results)
    return results


__all__ = [
    "EXTENSION_ENTRY_POINT_GROUP",
    "ExtensionLoadError",
    "ExtensionLoadResult",
    "LOAD_EXTENSIONS_VARIABLE",
    "STRICT_EXTENSIONS_VARIABLE",
    "discover_and_register_extensions",
    "discovery_enabled",
    "load_report",
    "reset_load_report_for_testing",
    "strict_mode",
]
