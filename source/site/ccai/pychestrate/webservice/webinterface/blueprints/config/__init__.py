"""
.. module:: config
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Configuration management web interface blueprint
               (webworks-side).

.. moduleauthor:: Code Craft AI LLC

This package owns the consumer-facing ``/config`` web UI.
The webworks-native handlers + registrar live in
:mod:`webinterface.blueprints.config.routes`.

This ``__init__`` is intentionally side-effect free -- importing
the package does not construct any blueprint object. Callers
that need the routes registrar import
``register_config_routes`` directly:

::

    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
        register_config_routes,
    )
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"
