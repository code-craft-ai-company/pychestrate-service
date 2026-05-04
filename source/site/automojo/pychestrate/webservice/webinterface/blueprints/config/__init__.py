"""
.. module:: config
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Configuration management web interface blueprint
               (webworks-side).

.. moduleauthor:: Automation Mojo LLC

This package owns the consumer-facing ``/config`` web UI. The
flask-era scaffold (``endpoints.py`` + the flask
``config_blueprint`` object) is being ported to webworks across
PRs D1/D2/D3/D4. The webworks-native handlers + registrar live
in :mod:`webinterface.blueprints.config.routes`; the legacy
``endpoints.py`` is dead code that will be deleted at the end
of D4 once every flask handler has a webworks counterpart.

This ``__init__`` is intentionally side-effect free -- importing
the package no longer constructs a flask :class:`Blueprint` (the
runtime no longer hosts flask). Callers that need the routes
registrar import ``register_config_routes`` directly:

::

    from automojo.pychestrate.webservice.webinterface.blueprints.config.routes import (
        register_config_routes,
    )
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
