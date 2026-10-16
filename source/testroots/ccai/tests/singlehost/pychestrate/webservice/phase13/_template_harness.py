"""
.. module:: tests.singlehost.pychestrate.webservice.phase13._template_harness
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Shared scaffolding for the template guardrail tests.

.. moduleauthor:: Code Craft AI LLC

Builds one strict jinja environment over every consumer-UI
template directory, registers the four blueprints' routes against
a fake app so ``url_for`` resolves, and enumerates templates with
the top-level variables each one reads (following ``extends`` /
``include`` / ``import`` so a child template's context also covers
its base).

Cached at module level: the environment and the route registry
are process-global by design, and building them once keeps the
~200 generated tests fast.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from typing import Callable, Dict, List, Optional, Set, Tuple

import jinja2

from jinja2 import meta, nodes

from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES
from ccai.pychestrate.webservice.webinterface.foundation import static_files
from ccai.pychestrate.webservice.webinterface.foundation import url_for as url_for_module
from ccai.pychestrate.webservice.webinterface.foundation.templating import (
    build_jinja_environment,
    discover_blueprint_template_paths,
    install_template_globals,
)
from ccai.pychestrate.webservice.webinterface.site_shell.shell_document import (
    get_shell_template_search_path,
)


URL_FOR_LITERAL_PATTERN = re.compile(r"""url_for\(\s*['"]([A-Za-z0-9_.]+)['"]""")


class FakeApp:
    """
        Minimal stand-in for the webworks app: records
        ``attach_route`` registrations and returns the handler
        unchanged so registrars can run without a server.
    """

    def __init__(self) -> None:
        self.routes: List[Tuple[str, Tuple[str, ...], Callable]] = []
        return

    def attach_route(
            self, path: str, methods: Optional[List[str]] = None, **kwargs
        ) -> Callable:
        resolved_methods = tuple(methods if methods is not None else ["GET"])

        def decorator(func: Callable) -> Callable:
            self.routes.append((path, resolved_methods, func))
            return func

        return decorator


_environment: Optional[jinja2.Environment] = None
_template_paths: Optional[List[str]] = None
_routes_registered: bool = False


def template_search_paths() -> List[str]:
    """
        Every directory the production bootstrap hands to jinja:
        each blueprint's ``templates/`` plus the site-shell
        template directory.

        :returns: Ordered list of directories.
    """
    global _template_paths
    if _template_paths is None:
        paths = discover_blueprint_template_paths(
            blueprints_root=SITE_DIRECTORIES.DIR_BLUEPRINTS,
        )
        paths = list(paths) + [get_shell_template_search_path()]
        _template_paths = paths
    rtnval = list(_template_paths)
    return rtnval


def ensure_routes_registered() -> None:
    """
        Run every blueprint's route registrar against a
        :class:`FakeApp` so the ``url_for`` endpoint registry is
        populated the same way production populates it.

        :returns: None.
    """
    global _routes_registered
    # Other tests reset the ``url_for`` registry; the flag alone would then leave it empty for every later render.
    if _routes_registered is True and len(url_for_module.get_registry_snapshot()) > 0:
        return

    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
        register_config_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes import (
        register_projects_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes import (
        register_resources_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.setup.routes import (
        register_setup_routes,
    )

    app = FakeApp()
    register_setup_routes(app=app)
    register_config_routes(app=app)
    register_projects_routes(app=app)
    register_resources_routes(app=app)
    _routes_registered = True
    return


def strict_environment() -> jinja2.Environment:
    """
        The shared ``StrictUndefined`` environment with ``url_for``
        installed as a global.

        :returns: Configured environment.
    """
    global _environment
    ensure_routes_registered()
    if _environment is None:
        env = build_jinja_environment(
            template_search_paths=template_search_paths(),
            strict_undefined=True,
        )
        install_template_globals(environment=env)
        _environment = env
    rtnval = _environment
    return rtnval


def enumerate_templates() -> List[str]:
    """
        Every ``.html`` template, as the loader-relative name the
        handlers use (``config/users/list.html``).

        :returns: Sorted list of template names.
    """
    names: Set[str] = set()
    for root in template_search_paths():
        for dirpath, _dirnames, filenames in os.walk(root):
            for filename in filenames:
                if filename.endswith(".html") is False:
                    continue
                full = os.path.join(dirpath, filename)
                names.add(os.path.relpath(full, root).replace(os.sep, "/"))
    rtnval = sorted(names)
    return rtnval


def template_source(*, template_name: str) -> str:
    env = strict_environment()
    source, _filename, _uptodate = env.loader.get_source(env, template_name)
    return source


def undeclared_variables(*, template_name: str) -> List[str]:
    """
        Top-level variables ``template_name`` reads, including those
        read by the templates it extends, includes, or imports.
        Environment globals (``url_for``) are excluded.

        :param template_name: Loader-relative template name.

        :returns: Sorted variable names.
    """
    env = strict_environment()
    seen: Set[str] = set()
    pending: List[str] = [template_name]
    names: Set[str] = set()
    while len(pending) > 0:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        ast = env.parse(template_source(template_name=current))
        names |= set(meta.find_undeclared_variables(ast))
        # ``{% import "x.html" as alias %}`` binds ``alias`` itself;
        # jinja's meta pass reports it as undeclared when the import
        # precedes the first block, so subtract import targets.
        for import_node in ast.find_all(nodes.Import):
            names.discard(import_node.target)
        for from_import in ast.find_all(nodes.FromImport):
            for imported in from_import.names:
                alias = imported[1] if isinstance(imported, tuple) else imported
                names.discard(alias)
        for referenced in meta.find_referenced_templates(ast):
            if referenced is not None and referenced not in seen:
                pending.append(referenced)
    for global_name in env.globals:
        names.discard(global_name)
    rtnval = sorted(names)
    return rtnval


def url_for_endpoints_in_template(*, template_name: str) -> List[str]:
    """
        Endpoint names passed as string literals to ``url_for`` in
        one template (and its bases).

        :returns: Sorted unique endpoint names.
    """
    env = strict_environment()
    seen: Set[str] = set()
    pending: List[str] = [template_name]
    endpoints: Set[str] = set()
    while len(pending) > 0:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        source = template_source(template_name=current)
        endpoints |= set(URL_FOR_LITERAL_PATTERN.findall(source))
        ast = env.parse(source)
        for referenced in meta.find_referenced_templates(ast):
            if referenced is not None and referenced not in seen:
                pending.append(referenced)
    rtnval = sorted(endpoints)
    return rtnval


def slugify(template_name: str) -> str:
    rtnval = re.sub(r"[^a-z0-9]+", "_", template_name.lower()).strip("_")
    return rtnval


__all__ = [
    "FakeApp",
    "template_search_paths",
    "ensure_routes_registered",
    "strict_environment",
    "enumerate_templates",
    "undeclared_variables",
    "url_for_endpoints_in_template",
    "slugify",
]
