"""
.. module:: blueprints
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Web interface blueprints for Pychestrate

.. moduleauthor:: Automation Mojo LLC

The consumer-facing ``/config`` and ``/resources`` UIs are
fully ported to webworks
(:mod:`webinterface.blueprints.config.routes` /
:mod:`webinterface.blueprints.resources.routes` and their
``routes_*`` siblings). The remaining ``/projects`` blueprint
is still flask-shaped and pending its own port (slated as
PR F).

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
        LEGACY: register the still-flask ``/projects`` blueprint
        with a Flask application. The consumer ``/config`` and
        ``/resources`` blueprints are no longer registered here
        -- they live on webworks (see
        ``register_config_routes`` /
        ``register_resources_routes``).

        This function is intentionally dead code under the
        webworks runtime and is retained only so an external
        flask consumer (if any) can still wire the unported
        ``/projects`` blueprint. Once PR F ports projects to
        webworks, this function and its callers should be
        deleted.

        :param app: Flask application instance.
    """
    from .projects import projects_blueprint

    app.register_blueprint(projects_blueprint)
