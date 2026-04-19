"""
.. module:: resources
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Resource management web interface blueprints

.. moduleauthor:: Automation Mojo LLC

This package provides web interface blueprints for resource management:
- Resource management pages (list, create, edit, detail)
- Pool management pages
- IP pool management pages
- Allocation viewing pages
- Reservation management pages
- Health monitoring pages

All data modifications use postback URLs as per project conventions.

Requirements: 11.1
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import Blueprint

# Create the resources blueprint
resources_blueprint = Blueprint(
    'resources',
    __name__,
    template_folder='templates',
    static_folder='static',
    url_prefix='/resources'
)

# Import and register route modules
from . import endpoints
