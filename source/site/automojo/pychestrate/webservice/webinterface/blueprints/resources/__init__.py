"""
.. module:: resources
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Resource management web interface blueprint
               (webworks-side).

.. moduleauthor:: Automation Mojo LLC

The webworks-native handlers + registrar for the ``/resources``
surface live in :mod:`webinterface.blueprints.resources.routes`.

This ``__init__`` is intentionally side-effect free -- importing
the package does not construct any blueprint object. Callers that
need the routes registrar import ``register_resources_routes``
directly:

::

    from automojo.pychestrate.webservice.webinterface.blueprints.resources.routes import (
        register_resources_routes,
    )
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
