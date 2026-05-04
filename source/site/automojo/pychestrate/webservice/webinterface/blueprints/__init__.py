"""
.. module:: blueprints
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Web interface blueprints for Pychestrate

.. moduleauthor:: Automation Mojo LLC

The consumer-facing ``/config`` UI is fully ported to webworks
(:mod:`webinterface.blueprints.config.routes` and its
``routes_*`` siblings). The remaining ``/resources`` and
``/projects`` blueprints are still flask-shaped and pending
their own ports (slated as PR E + PR F).

:func:`register_web_blueprints` is dead code under the webworks
runtime -- nothing in :mod:`app_pychestrate_main` calls it. The
function is preserved for external consumers that may still
hand a Flask application to the legacy registration shape; it
lazy-imports flask so importing this module does NOT pull
flask into the webworks process.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


def register_web_blueprints(app):
    """
        LEGACY: register the still-flask ``/resources`` and
        ``/projects`` blueprints with a Flask application. The
        consumer ``/config`` blueprint is no longer registered
        here -- it lives on webworks (see
        :func:`automojo.pychestrate.webservice.webinterface.blueprints.config.routes.register_config_routes`).

        This function is intentionally dead code under the
        webworks runtime and is retained only so an external
        flask consumer (if any) can still wire the unported
        blueprints. Once PR E + PR F port resources and projects
        to webworks, this function and its callers should be
        deleted.

        :param app: Flask application instance.
    """
    from .resources import resources_blueprint
    from .projects import projects_blueprint

    app.register_blueprint(resources_blueprint)
    app.register_blueprint(projects_blueprint)
