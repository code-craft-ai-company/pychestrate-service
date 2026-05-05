"""
.. module:: projects
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Project management web interface blueprint
               (webworks).

.. moduleauthor:: Automation Mojo LLC

The consumer-facing ``/projects`` UI on webworks. The complete
route surface lives in
:mod:`webinterface.blueprints.projects.routes` (dashboard +
project core + members) plus its per-feature siblings:

* :mod:`webinterface.blueprints.projects.routes_repositories`
* :mod:`webinterface.blueprints.projects.routes_builds`
* :mod:`webinterface.blueprints.projects.routes_infrastructure`
* :mod:`webinterface.blueprints.projects.routes_tests`
* :mod:`webinterface.blueprints.projects.routes_releases`
* :mod:`webinterface.blueprints.projects.routes_calendar`
* :mod:`webinterface.blueprints.projects.routes_watches`

This ``__init__`` is intentionally side-effect free -- importing
the package does not construct a flask :class:`Blueprint`
(the runtime no longer hosts flask). Callers wire the routes
via :func:`register_projects_routes`:

::

    from automojo.pychestrate.webservice.webinterface.blueprints.projects.routes import (
        register_projects_routes,
    )
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
