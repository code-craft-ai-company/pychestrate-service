"""
.. module:: blueprints
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Web interface blueprints for Pychestrate (webworks).

.. moduleauthor:: Automation Mojo LLC

The consumer-facing web UI is fully ported to webworks. The
three blueprints (``/config`` / ``/resources`` / ``/projects``)
each expose a top-level ``register_*_routes`` registrar that
:mod:`app_pychestrate_main` invokes during app construction.

::

    from automojo.pychestrate.webservice.webinterface.blueprints.config.routes import (
        register_config_routes,
    )
    from automojo.pychestrate.webservice.webinterface.blueprints.resources.routes import (
        register_resources_routes,
    )
    from automojo.pychestrate.webservice.webinterface.blueprints.projects.routes import (
        register_projects_routes,
    )

This package imports without pulling any legacy framework into
the webworks process.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
