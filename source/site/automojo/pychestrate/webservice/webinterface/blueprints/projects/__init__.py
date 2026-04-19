"""
.. module:: projects
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Project management web interface blueprints

.. moduleauthor:: Automation Mojo LLC

This package provides web interface blueprints for project management:
- Project management pages (list, create, edit, detail)
- Repository management pages
- Build specification and execution pages
- Infrastructure specification and job pages
- Test specification and job pages
- Release pipeline and release pages
- Calendar event management pages
- Watch configuration pages

All data modifications use postback URLs as per project conventions.

Requirements: 13.1
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import Blueprint

# Create the projects blueprint
projects_blueprint = Blueprint(
    'projects',
    __name__,
    template_folder='templates',
    static_folder='static',
    url_prefix='/projects'
)

# Import and register route modules
from . import endpoints
