"""
.. module:: tests.singlehost.pychestrate.webservice.phase3.fixtures
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Shared test fixtures for Phase-3 tests.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.phase3_bootstrap import (
    register_phase3_builtin_extensions,
)

from ccai.tests.singlehost.pychestrate.webservice.phase2.fixtures import (
    reset_phase2_runtime,
)


def reset_phase3_runtime() -> None:
    """
        Reset the Phase-2 runtime (which resets Phase-1) and then
        register every Phase-3 built-in extension.

        :returns: None.
    """
    reset_phase2_runtime()
    register_phase3_builtin_extensions()
    return
