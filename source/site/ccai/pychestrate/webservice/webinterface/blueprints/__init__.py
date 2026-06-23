"""
.. module:: blueprints
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Web interface blueprints for Pychestrate (webworks).

.. moduleauthor:: Code Craft AI LLC

The consumer-facing web UI is fully ported to webworks. The
three blueprints (``/config`` / ``/resources`` / ``/projects``)
each expose a top-level ``register_*_routes`` registrar that
:mod:`app_pychestrate_main` invokes during app construction.

::

    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
        register_config_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes import (
        register_resources_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes import (
        register_projects_routes,
    )

This package imports without pulling any legacy framework into
the webworks process.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"
