"""
.. module:: projects
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Project management web interface blueprint
               (webworks-side).

.. moduleauthor:: Automation Mojo LLC

The flask-era ``/projects`` blueprint is being ported to
webworks across PRs F1/F2/F3/F4/F5. The webworks-native
handlers + registrar live in
:mod:`webinterface.blueprints.projects.routes`; the legacy
``endpoints.py`` (2,529 LOC) is retained until the port
completes and gets deleted in PR F5.

This ``__init__`` is intentionally side-effect free -- importing
the package no longer constructs a flask :class:`Blueprint` (the
runtime no longer hosts flask). Callers that need the routes
registrar import ``register_projects_routes`` directly:

::

    from automojo.pychestrate.webservice.webinterface.blueprints.projects.routes import (
        register_projects_routes,
    )
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
