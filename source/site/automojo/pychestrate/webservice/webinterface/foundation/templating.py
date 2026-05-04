"""
.. module:: webinterface.foundation.templating
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Jinja2 templating helpers for the webworks-side
               consumer web UI.

.. moduleauthor:: Automation Mojo LLC

The flask blueprints under ``webinterface/blueprints/`` ship
their templates in per-blueprint ``templates/`` subdirectories
(per the flask-restx ``Blueprint(template_folder=...)``
convention). When the blueprints port to webworks the templates
themselves can be reused unchanged -- only the route handlers
and the render-call shape need updating.

This module supplies that render-call shape:

* :func:`build_jinja_environment` -- one-time builder that wires
  a ``ChoiceLoader`` over every per-blueprint ``templates/``
  directory plus an optional shared ``templates/`` root. Returns
  a :class:`jinja2.Environment` ready for handlers to consume.

* :func:`render_template_response` -- the one call a webworks
  handler makes to convert ``(template_name, context)`` into a
  :class:`HTMLResponse`. Mirrors flask's ``render_template``
  signature so blueprint ports stay close to a one-line swap.

* :func:`get_default_environment` -- module-level singleton
  pattern. The bootstrap calls
  :func:`set_default_environment` once at startup with the
  configured environment; handlers call
  ``render_template_response(...)`` without threading the env
  through.

Test seam: every public function accepts an optional
``environment`` kwarg so tests can pass a stub
:class:`jinja2.Environment` without touching the module-level
singleton.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict, List, Optional

import jinja2

from automojo.webworks.routing.response import HTMLResponse


_default_environment: Optional[jinja2.Environment] = None


def build_jinja_environment(
        *,
        template_search_paths: List[str],
        autoescape: bool = True,
        cache_size: int = 400
    ) -> jinja2.Environment:
    """
        Construct a configured :class:`jinja2.Environment`.

        :param template_search_paths: Ordered list of filesystem
                                      directories jinja searches
                                      for templates. Earlier paths
                                      win on collision (per
                                      :class:`jinja2.ChoiceLoader`
                                      semantics).
        :param autoescape: When True, autoescape HTML / XML / SVG
                           extensions. The web UI is HTML so this
                           is the safe default. Mirrors flask's
                           ``select_autoescape``.
        :param cache_size: Number of compiled templates to cache
                           in-process. Set to 0 to disable caching
                           (development convenience).

        :returns: Configured :class:`jinja2.Environment`.
        :raises: ValueError on an empty path list.
    """
    if template_search_paths is None or len(template_search_paths) == 0:
        raise ValueError(
            "build_jinja_environment requires at least one"
            " template search path"
        )

    loaders = []
    for path in template_search_paths:
        loaders.append(jinja2.FileSystemLoader(path))
    combined_loader = jinja2.ChoiceLoader(loaders)

    autoescape_callable = jinja2.select_autoescape(
        enabled_extensions=("html", "htm", "xml", "svg"),
    ) if autoescape is True else False

    rtnval = jinja2.Environment(
        loader=combined_loader,
        autoescape=autoescape_callable,
        cache_size=cache_size,
        keep_trailing_newline=True,
    )
    return rtnval


def set_default_environment(*, environment: jinja2.Environment) -> None:
    """
        Install the supplied environment as the module-level
        default. Subsequent calls to
        :func:`render_template_response` without an explicit
        ``environment=`` use this one.

        :param environment: Configured jinja2 environment.

        :returns: None.
    """
    global _default_environment
    _default_environment = environment
    return


def get_default_environment() -> jinja2.Environment:
    """
        Return the module-level default environment.

        :returns: Configured :class:`jinja2.Environment`.
        :raises: RuntimeError when no default environment has been
                 installed.
    """
    if _default_environment is None:
        raise RuntimeError(
            "No default jinja2 environment configured. Call"
            " set_default_environment(environment=...) once at"
            " startup, or pass environment= to"
            " render_template_response(...)."
        )
    rtnval = _default_environment
    return rtnval


def reset_default_environment_for_testing() -> None:
    """
        Clear the module-level default. Tests call this in
        cleanup so cross-test state never bleeds.

        :returns: None.
    """
    global _default_environment
    _default_environment = None
    return


def render_template_response(
        *,
        template_name: str,
        context: Optional[Dict[str, Any]] = None,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
        environment: Optional[jinja2.Environment] = None
    ) -> HTMLResponse:
    """
        Render a template with the supplied context and return a
        webworks :class:`HTMLResponse`. The webworks port's
        equivalent of flask's
        ``return render_template("foo.html", **ctx)``.

        :param template_name: Template path relative to the search
                              paths (e.g. ``config/users/list.html``).
        :param context: Dict of values made available inside the
                        template. ``None`` becomes an empty dict.
        :param status_code: HTTP status code (default 200).
        :param headers: Optional additional response headers. The
                        ``Content-Type`` header is set by
                        :class:`HTMLResponse`.
        :param environment: Optional environment override
                            (test seam). Defaults to the module-
                            level singleton.

        :returns: :class:`HTMLResponse` carrying the rendered HTML.
        :raises: jinja2.TemplateNotFound when the template is not
                 found by the loader chain. RuntimeError when no
                 environment is available (neither passed in nor
                 set as default).
    """
    if environment is None:
        env = get_default_environment()
    else:
        env = environment

    if context is None:
        render_context: Dict[str, Any] = {}
    else:
        render_context = context

    template = env.get_template(template_name)
    rendered_html = template.render(render_context)
    rtnval = HTMLResponse(
        content=rendered_html,
        status_code=status_code,
        headers=headers,
    )
    return rtnval


def discover_blueprint_template_paths(
        *, blueprints_root: str
    ) -> List[str]:
    """
        Walk a blueprints root directory and return the ordered
        list of ``<blueprint>/templates`` subdirectories that
        exist on disk. Convention: each blueprint package owns its
        own ``templates/`` subfolder, mirroring the flask
        ``Blueprint(template_folder='templates')`` shape.

        :param blueprints_root: Filesystem path to the blueprints
                                root (e.g.
                                ``webinterface/blueprints``).

        :returns: List of template directory paths in alphabetical
                  blueprint order. Empty list when the root does
                  not exist.
    """
    rtnval: List[str] = []
    if blueprints_root is None or len(blueprints_root) == 0:
        return rtnval
    if os.path.isdir(blueprints_root) is False:
        return rtnval

    for entry in sorted(os.listdir(blueprints_root)):
        candidate = os.path.join(blueprints_root, entry, "templates")
        if os.path.isdir(candidate) is True:
            rtnval.append(candidate)
    return rtnval


__all__ = [
    "build_jinja_environment",
    "set_default_environment",
    "get_default_environment",
    "reset_default_environment_for_testing",
    "render_template_response",
    "discover_blueprint_template_paths",
]
