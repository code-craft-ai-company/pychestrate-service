"""
.. module:: resources
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Resource management web interface blueprint
               (webworks-side).

.. moduleauthor:: Automation Mojo LLC

The flask-era ``/resources`` blueprint is being ported to
webworks across PRs E1/E2/E3/E4. The webworks-native handlers
+ registrar live in :mod:`webinterface.blueprints.resources.routes`;
the legacy ``endpoints.py`` (1,657 LOC) is retained until the
port completes and gets deleted in PR E4.

This ``__init__`` is intentionally side-effect free -- importing
the package no longer constructs a flask :class:`Blueprint` (the
runtime no longer hosts flask). Callers that need the routes
registrar import ``register_resources_routes`` directly:

::

    from automojo.pychestrate.webservice.webinterface.blueprints.resources.routes import (
        register_resources_routes,
    )
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
