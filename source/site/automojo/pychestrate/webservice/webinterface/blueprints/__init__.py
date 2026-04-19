"""
.. module:: blueprints
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Web interface blueprints for Pychestrate

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


def register_web_blueprints(app):
    """
    Register all web interface blueprints with the Flask application.
    
    :param app: The Flask application instance
    """
    from .config import config_blueprint
    from .resources import resources_blueprint
    from .projects import projects_blueprint
    
    app.register_blueprint(config_blueprint)
    app.register_blueprint(resources_blueprint)
    app.register_blueprint(projects_blueprint)

