"""
.. module:: pychestrate.cli
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``pyc`` CLI consuming Pychestrate's REST API.

.. moduleauthor:: Automation Mojo LLC

The CLI is a separate Python package living under
``source/site/automojo/pychestrate/cli/``. M1 ships the parser,
credentials loader, transport, and the reference ``pyc project list``
command end-to-end. Subsequent milestones layer in OIDC device
login, four output formats, resumable downloads, and the
``CLISubcommandExtension`` surface.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
