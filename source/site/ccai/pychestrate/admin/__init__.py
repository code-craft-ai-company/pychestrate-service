"""
.. module:: pychestrate.admin
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Operator-facing administrative CLI tooling for Pychestrate.

.. moduleauthor:: Code Craft AI LLC

The ``pychestrate-admin`` console script entry point lives here. It is
deliberately separate from the runtime web-service code under
``pychestrate.webservice`` so service deployments do not pull in CLI
argparse / Jinja2 / file-generation utilities at request time.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"
