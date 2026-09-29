"""
.. module:: webinterface.foundation.url_for
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``url_for``-shaped URL builder for the
               webworks-side consumer web UI.

.. moduleauthor:: Code Craft AI LLC

The blueprint jinja2 templates call
``url_for('config.dashboard')`` / ``url_for('config.user_detail',
user_id='u-1')`` etc. to build links. Webworks has no built-in
``url_for`` helper, so this module exposes a ``url_for`` callable
the templating environment binds as a global.

This module owns the registry + builder:

* :func:`register_endpoint` -- per-blueprint route registration
  helper. Each blueprint's ``register_*_routes`` function calls
  this once per route to register the
  ``"<blueprint>.<endpoint>" -> "<url-pattern>"`` mapping.

* :func:`url_for` -- the jinja2-callable. Looks up the endpoint,
  substitutes path-param placeholders with caller-supplied
  values, returns the URL string.

* :func:`install_url_for_global` -- attaches :func:`url_for` to
  a :class:`jinja2.Environment` as a global so templates can
  call it without explicit context threading.

* :func:`reset_registry_for_testing` -- clears the registry
  between tests so cross-test state never bleeds.

Pattern handling
----------------

Webworks path patterns use ``{name}`` / ``{name:converter}``
placeholders. The shim drops the converter qualifier when
substituting -- so a registered pattern of
``/config/users/{user_id}`` returns
``/config/users/u-1`` for ``url_for('config.user_detail',
user_id='u-1')``.

Kwargs that do not match a path placeholder are appended as a
URL-encoded query string (matching flask's ``url_for``
behavior) -- so ``url_for('config.users_list', page=2)`` on a
placeholder-free pattern returns ``/admin/users?page=2``.
Kwargs whose value is ``None`` are skipped, and insertion
order is preserved.

Missing kwargs raise KeyError so a typo in a template surfaces
loudly rather than producing a half-substituted URL.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re
import urllib.parse

from typing import Any, Dict, List, Tuple

import jinja2


_endpoint_registry: Dict[str, str] = {}


# Match ``{name}`` or ``{name:converter}`` placeholders in
# webworks route patterns. Captures the name only.
_PLACEHOLDER_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)(?::[^}]+)?\}")


def register_endpoint(*, endpoint: str, pattern: str) -> None:
    """
        Register an endpoint name → URL pattern mapping. Per-
        blueprint registration helpers call this once per route
        before they call ``app.attach_route``.

        :param endpoint: ``"blueprint.action"`` style name (e.g.
                         ``"config.dashboard"``).
        :param pattern: Webworks route pattern (e.g.
                        ``"/config/users/{user_id}"``).

        :returns: None.
        :raises: ValueError on empty endpoint / pattern.
    """
    if endpoint is None or len(endpoint) == 0:
        raise ValueError("register_endpoint requires non-empty endpoint")
    if pattern is None or len(pattern) == 0:
        raise ValueError("register_endpoint requires non-empty pattern")
    _endpoint_registry[endpoint] = pattern
    return


def url_for(endpoint: str, **kwargs: Any) -> str:
    """
        Build a URL from a registered endpoint name + caller-
        supplied kwargs. Matches the
        ``url_for(endpoint, **values)`` shape the templates were
        written against: kwargs matching path-param placeholders
        are substituted into the path, and every remaining kwarg
        is appended as a URL-encoded query string. Kwargs whose
        value is ``None`` are skipped; insertion order is
        preserved. A list or tuple value is written once per item
        (``tags=a&tags=b``); an empty one writes nothing.

        :param endpoint: Registered endpoint name.
        :param kwargs: Path-param substitutions + query-string
                       parameters.

        :returns: Substituted URL string, with a query string
                  when non-placeholder kwargs were passed.
        :raises: KeyError on unknown endpoint or missing
                 path-param kwarg.
    """
    if endpoint not in _endpoint_registry:
        raise KeyError(
            "Unknown url_for endpoint: {!r}. Registered: {}".format(
                endpoint, sorted(_endpoint_registry.keys())
            )
        )

    pattern = _endpoint_registry[endpoint]

    placeholder_names = set(_PLACEHOLDER_PATTERN.findall(pattern))

    def _substitute(match: "re.Match[str]") -> str:
        name = match.group(1)
        if name not in kwargs:
            raise KeyError(
                "url_for({!r}) missing path-param: {!r}".format(
                    endpoint, name
                )
            )
        rtnval = str(kwargs[name])
        return rtnval

    rtnval = _PLACEHOLDER_PATTERN.sub(_substitute, pattern)

    query_items: List[Tuple[str, str]] = []
    for name, value in kwargs.items():
        if name in placeholder_names:
            continue
        if value is None:
            continue
        if isinstance(value, (list, tuple, set, frozenset)):
            # A multi-valued parameter (the tags of a filter) is written
            # once per value, the way a form submits it.
            for item in value:
                query_items.append((name, str(item)))
            continue
        query_items.append((name, str(value)))

    if len(query_items) > 0:
        query_string = urllib.parse.urlencode(query_items)
        if "?" in rtnval:
            rtnval = rtnval + "&" + query_string
        else:
            rtnval = rtnval + "?" + query_string

    return rtnval


def install_url_for_global(*, environment: jinja2.Environment) -> None:
    """
        Attach :func:`url_for` to a jinja2 environment as a
        global so templates can call ``{{ url_for('...') }}``
        without explicit context threading.

        :param environment: Configured jinja2 environment.

        :returns: None.
    """
    environment.globals["url_for"] = url_for
    return


def reset_registry_for_testing() -> None:
    """
        Clear the endpoint registry. Tests call this in cleanup
        so cross-test registrations never bleed.

        :returns: None.
    """
    global _endpoint_registry
    _endpoint_registry = {}
    return


def get_registry_snapshot() -> Dict[str, str]:
    """
        Return a copy of the current endpoint → pattern registry.
        For diagnostics + tests.

        :returns: Dict copy.
    """
    rtnval = dict(_endpoint_registry)
    return rtnval


__all__ = [
    "register_endpoint",
    "url_for",
    "install_url_for_global",
    "reset_registry_for_testing",
    "get_registry_snapshot",
]
