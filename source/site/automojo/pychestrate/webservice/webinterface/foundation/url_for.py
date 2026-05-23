"""
.. module:: webinterface.foundation.url_for
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``url_for``-shaped URL builder for the
               webworks-side consumer web UI.

.. moduleauthor:: Automation Mojo LLC

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

Missing kwargs raise KeyError so a typo in a template surfaces
loudly rather than producing a half-substituted URL.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from typing import Any, Dict

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
        supplied path-param kwargs. Matches the
        ``url_for(endpoint, **values)`` shape the templates were
        written against.

        :param endpoint: Registered endpoint name.
        :param kwargs: Path-param substitutions.

        :returns: Substituted URL string.
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
