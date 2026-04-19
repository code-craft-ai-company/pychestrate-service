"""
.. module:: config
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Configuration management web interface blueprints

.. moduleauthor:: Automation Mojo LLC

This package provides web interface blueprints for system configuration management:
- User management pages
- Role management pages
- Global variable management pages
- Secret management pages
- Session management pages
- Audit log viewer

Requirements: 10.1
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import Blueprint

# Create the config blueprint
config_blueprint = Blueprint(
    'config',
    __name__,
    template_folder='templates',
    static_folder='static',
    url_prefix='/config'
)

# Import and register route modules
from . import endpoints

