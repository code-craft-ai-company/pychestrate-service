"""
.. module:: cli.exit_codes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Enumerated exit codes the ``pyc`` command emits.

.. moduleauthor:: Automation Mojo LLC

The mapping is shared between the entry-point dispatcher and the
exception translation layer so every code path returns a documented
number. Tests assert on these codes by name.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


EXIT_OK: int = 0
EXIT_USAGE_ERROR: int = 2
EXIT_AUTHENTICATION_ERROR: int = 3
EXIT_NOT_FOUND: int = 4
EXIT_CONFLICT: int = 5
EXIT_RATE_LIMITED: int = 6
EXIT_SERVER_ERROR: int = 7
EXIT_CREDENTIALS_PERMISSIONS_ERROR: int = 13
